from __future__ import annotations

import dataclasses
import datetime as dt
import http.client
import json
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


BASE_URL = "https://houstat.hf.go.kr/research/openapi/SttsApiTblData.do"
KHAI_TABLE = "T186503126543136"


@dataclasses.dataclass(frozen=True)
class HoustatObservation:
    time: str
    value: float


@dataclasses.dataclass(frozen=True)
class AffordabilitySnapshot:
    latest: HoustatObservation
    change_1y: float
    score: int
    history_scores: list[int]
    observations: list[HoustatObservation] = dataclasses.field(default_factory=list)


def _percentile(values: list[float], target: float) -> float:
    if not values:
        return 50
    return sum(value <= target for value in values) / len(values) * 100


def calculate_affordability_score(history: list[float]) -> int:
    """Score K-HAI without adding its mortgage-rate component a second time."""
    if not history:
        return 50
    latest = history[-1]
    prior = history[-5] if len(history) >= 5 else history[0]
    # K-HAI 100 is the published affordability boundary. 200 maps to max risk.
    level = max(0, min(100, latest / 2))
    change_ratio = (latest - prior) / prior if prior else 0
    trend = max(0, min(100, 50 + change_ratio * 250))
    return round(level * .80 + trend * .20)


def _quarter_id(year: int, quarter: int) -> str:
    return f"{year:04d}{quarter:02d}"


def _shift_quarter(period: str, offset: int) -> str:
    year, quarter = int(period[:4]), int(period[4:])
    absolute = year * 4 + quarter - 1 + offset
    return _quarter_id(absolute // 4, absolute % 4 + 1)


class HoustatClient:
    def __init__(
        self,
        api_key: str = "sample",
        transport: Callable[[str], bytes] | None = None,
    ) -> None:
        self.api_key = api_key or "sample"
        self.transport = transport or self._download

    @staticmethod
    def _download(url: str) -> bytes:
        parsed = urllib.parse.urlsplit(url)
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=15)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        try:
            connection.request(
                "GET", path,
                headers={"User-Agent": "curl/8.7.1", "Accept": "application/json"},
            )
            response = connection.getresponse()
            payload = response.read()
            if response.status != 200:
                raise RuntimeError(f"HOUSTAT HTTP {response.status}")
            return payload
        finally:
            connection.close()

    def _url(self, period: str) -> str:
        params = {
            "Type": "json",
            "pIndex": 1,
            "pSize": 20,
            "STATBL_ID": KHAI_TABLE,
            "DTACYCLE_CD": "QY",
            "WRTTIME_IDTFR_ID": period,
        }
        if self.api_key != "sample":
            params["KEY"] = self.api_key
        query = urllib.parse.urlencode(params)
        return f"{BASE_URL}?{query}"

    def _series_url(self) -> str:
        query = urllib.parse.urlencode({
            "KEY": self.api_key,
            "Type": "json",
            "pIndex": 1,
            "pSize": 1_000,
            "STATBL_ID": KHAI_TABLE,
            "DTACYCLE_CD": "QY",
            "ITM_DATANO": 10002,
        })
        return f"{BASE_URL}?{query}"

    def fetch_seoul_series(self) -> list[HoustatObservation]:
        data = json.loads(self.transport(self._series_url()))
        blocks = data.get("SttsApiTblData", [])
        if len(blocks) < 2:
            result = data.get("RESULT", {})
            raise RuntimeError(
                f"HOUSTAT API {result.get('CODE', 'unknown')}: {result.get('MESSAGE', '')}"
            )
        rows = blocks[1].get("row", [])
        return [
            HoustatObservation(time=row["WRTTIME_IDTFR_ID"], value=float(row["DTA_VAL"]))
            for row in rows if row.get("ITM_NM") == "서울"
        ]

    def fetch_seoul(self, period: str) -> HoustatObservation | None:
        data = json.loads(self.transport(self._url(period)))
        direct_result = data.get("RESULT", {})
        if direct_result.get("CODE") == "INFO-200":
            return None
        if direct_result:
            raise RuntimeError(
                f"HOUSTAT API {direct_result.get('CODE')}: {direct_result.get('MESSAGE', '')}"
            )
        blocks = data.get("SttsApiTblData", [])
        if not blocks:
            raise RuntimeError("HOUSTAT API returned an unexpected response")
        head = blocks[0].get("head", [])
        result = next((item["RESULT"] for item in head if "RESULT" in item), {})
        if result.get("CODE") == "INFO-200":
            return None
        if result.get("CODE") not in {None, "INFO-000"}:
            raise RuntimeError(f"HOUSTAT API {result.get('CODE')}: {result.get('MESSAGE', '')}")
        rows = blocks[1].get("row", []) if len(blocks) > 1 else []
        row = next((item for item in rows if item.get("ITM_NM") == "서울"), None)
        if row is None:
            return None
        return HoustatObservation(time=period, value=float(row["DTA_VAL"]))

    def fetch_affordability(self, as_of: dt.date | None = None) -> AffordabilitySnapshot:
        as_of = as_of or dt.date.today()
        current = _quarter_id(as_of.year, (as_of.month - 1) // 3 + 1)
        if self.api_key != "sample":
            all_rows = [row for row in self.fetch_seoul_series() if row.time <= current]
            rows = all_rows[-8:]
        else:
            latest: HoustatObservation | None = None
            latest_period = current
            for offset in range(0, -9, -1):
                latest_period = _shift_quarter(current, offset)
                latest = self.fetch_seoul(latest_period)
                if latest is not None:
                    break
            if latest is None:
                raise RuntimeError("HOUSTAT Seoul K-HAI series is empty")
            periods = [_shift_quarter(latest_period, offset) for offset in range(-7, 1)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = [row for row in pool.map(self.fetch_seoul, periods) if row is not None]
            all_rows = rows
        if not rows:
            raise RuntimeError("HOUSTAT Seoul K-HAI series is empty")
        values = [row.value for row in rows]
        prior = rows[-5] if len(rows) >= 5 else rows[0]
        history = [round(max(0, min(100, value / 2))) for value in values]
        return AffordabilitySnapshot(
            latest=rows[-1],
            change_1y=rows[-1].value - prior.value,
            score=calculate_affordability_score(values),
            history_scores=history,
            observations=all_rows,
        )
