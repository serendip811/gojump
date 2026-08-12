from __future__ import annotations

import dataclasses
import datetime as dt
import json
import urllib.parse
import urllib.request
from collections.abc import Callable


BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
BASE_RATE_STAT = "722Y001"
BASE_RATE_ITEM = "0101000"
MORTGAGE_RATE_STAT = "121Y006"
MORTGAGE_RATE_ITEM = "BECBLA0302"
UNSOLD_HOUSING_STAT = "901Y074"
SEOUL_UNSOLD_ITEM = "I410B"
SEOUL_APARTMENT_PRICE_STAT = "901Y093"
APARTMENT_TYPE_ITEM = "H69B"
SEOUL_REGION_ITEM = "R70F"
KB_SEOUL_APARTMENT_PRICE_STAT = "901Y062"
KB_SEOUL_APARTMENT_PRICE_ITEM = "P63ACA"


@dataclasses.dataclass(frozen=True)
class EcosObservation:
    time: str
    value: float
    item_name: str
    unit: str


@dataclasses.dataclass(frozen=True)
class RateSnapshot:
    base_rate: EcosObservation
    mortgage_rate: EcosObservation
    mortgage_change_3m: float
    score: int
    history_scores: list[int]
    mortgage_observations: list[EcosObservation] = dataclasses.field(default_factory=list)
    base_observations: list[EcosObservation] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class UnsoldHousingSnapshot:
    latest: EcosObservation
    change_3m_percent: float
    score: int
    history_scores: list[int]
    observations: list[EcosObservation] = dataclasses.field(default_factory=list)


def _shift_month(year_month: str, offset: int) -> str:
    year, month = int(year_month[:4]), int(year_month[4:])
    absolute = year * 12 + month - 1 + offset
    return f"{absolute // 12:04d}{absolute % 12 + 1:02d}"


def _percentile(values: list[float], target: float) -> float:
    if not values:
        return 50
    return sum(value <= target for value in values) / len(values) * 100


def calculate_rate_score(mortgage_history: list[float], base_rate: float) -> int:
    if not mortgage_history:
        return 50
    latest = mortgage_history[-1]
    prior = mortgage_history[-4] if len(mortgage_history) >= 4 else mortgage_history[0]
    percentile = _percentile(mortgage_history, latest)
    trend = max(0, min(100, 50 + (latest - prior) * 100))
    base_level = max(0, min(100, base_rate / 5 * 100))
    return round(percentile * .70 + trend * .20 + base_level * .10)


def calculate_unsold_score(history: list[float]) -> int:
    if not history:
        return 50
    latest = history[-1]
    prior = history[-4] if len(history) >= 4 else history[0]
    percentile = _percentile(history, latest)
    change_ratio = (latest - prior) / prior if prior else 0
    trend = max(0, min(100, 50 + change_ratio * 200))
    return round(percentile * .75 + trend * .25)


class EcosClient:
    def __init__(
        self,
        api_key: str = "sample",
        transport: Callable[[str], bytes] | None = None,
    ) -> None:
        self.api_key = api_key or "sample"
        self.transport = transport or self._download
        self.page_size = 10 if self.api_key == "sample" else 1_000

    @staticmethod
    def _download(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "GoJump/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def _url(
        self,
        first: int,
        last: int,
        stat_code: str,
        cycle: str,
        start: str,
        end: str,
        item_code: str,
        additional_item_codes: tuple[str, ...] = (),
    ) -> str:
        segments = [
            self.api_key, "json", "kr", str(first), str(last), stat_code,
            cycle, start, end, item_code, *additional_item_codes,
        ]
        return BASE_URL + "/" + "/".join(urllib.parse.quote(value, safe="") for value in segments)

    def fetch_series(
        self,
        stat_code: str,
        cycle: str,
        start: str,
        end: str,
        item_code: str,
        additional_item_codes: tuple[str, ...] = (),
    ) -> list[EcosObservation]:
        rows: list[dict] = []
        first = 1
        while True:
            last = first + self.page_size - 1
            payload = self.transport(
                self._url(
                    first, last, stat_code, cycle, start, end, item_code,
                    additional_item_codes,
                )
            )
            data = json.loads(payload)
            if "RESULT" in data:
                error = data["RESULT"]
                code = error.get("CODE", "unknown")
                message = error.get("MESSAGE", "Unknown ECOS error")
                if code == "INFO-200":
                    return []
                raise RuntimeError(f"ECOS API {code}: {message}")
            block = data.get("StatisticSearch")
            if not block:
                raise RuntimeError("ECOS API returned an unexpected response")
            rows.extend(block.get("row", []))
            total = int(block.get("list_total_count", len(rows)))
            if len(rows) >= total:
                break
            first += self.page_size

        return [
            EcosObservation(
                time=row["TIME"],
                value=float(row["DATA_VALUE"]),
                item_name=row.get("ITEM_NAME1", ""),
                unit=row.get("UNIT_NAME", ""),
            )
            for row in rows
        ]

    def fetch_seoul_apartment_price_index(
        self,
        start: str = "200311",
        end: str = "202503",
    ) -> list[EcosObservation]:
        """Fetch the long, fixed-vintage Seoul apartment sale price index."""
        return self.fetch_series(
            SEOUL_APARTMENT_PRICE_STAT,
            "M",
            start,
            end,
            APARTMENT_TYPE_ITEM,
            (SEOUL_REGION_ITEM,),
        )

    def fetch_kb_seoul_apartment_price_index(
        self,
        start: str = "202012",
        end: str | None = None,
    ) -> list[EcosObservation]:
        """Fetch the current KB Seoul apartment sale price index."""
        end = end or dt.date.today().strftime("%Y%m")
        return self.fetch_series(
            KB_SEOUL_APARTMENT_PRICE_STAT, "M", start, end,
            KB_SEOUL_APARTMENT_PRICE_ITEM,
        )

    def fetch_rates(self, as_of: dt.date | None = None) -> RateSnapshot:
        as_of = as_of or dt.date.today()
        end_month = as_of.strftime("%Y%m")
        start_month = _shift_month(end_month, -120)
        mortgage = self.fetch_series(
            MORTGAGE_RATE_STAT, "M", start_month, end_month, MORTGAGE_RATE_ITEM
        )
        base_start = f"{start_month}01"
        base = self.fetch_series(
            BASE_RATE_STAT, "D", base_start, as_of.strftime("%Y%m%d"), BASE_RATE_ITEM
        )
        if not mortgage or not base:
            raise RuntimeError("ECOS rate series is empty")

        mortgage_values = [row.value for row in mortgage]
        latest = mortgage[-1]
        prior = mortgage[-4] if len(mortgage) >= 4 else mortgage[0]
        score = calculate_rate_score(mortgage_values, base[-1].value)
        history = [round(_percentile(mortgage_values, value)) for value in mortgage_values[-8:]]
        return RateSnapshot(
            base_rate=base[-1],
            mortgage_rate=latest,
            mortgage_change_3m=latest.value - prior.value,
            score=score,
            history_scores=history,
            mortgage_observations=mortgage,
            base_observations=base,
        )

    def fetch_seoul_unsold(self, as_of: dt.date | None = None) -> UnsoldHousingSnapshot:
        as_of = as_of or dt.date.today()
        end_month = as_of.strftime("%Y%m")
        start_month = _shift_month(end_month, -120)
        rows = self.fetch_series(
            UNSOLD_HOUSING_STAT, "M", start_month, end_month, SEOUL_UNSOLD_ITEM
        )
        if not rows:
            raise RuntimeError("ECOS Seoul unsold housing series is empty")
        values = [row.value for row in rows]
        prior = rows[-4] if len(rows) >= 4 else rows[0]
        change = (rows[-1].value - prior.value) / prior.value * 100 if prior.value else 0
        history = [round(_percentile(values, value)) for value in values[-8:]]
        return UnsoldHousingSnapshot(
            latest=rows[-1],
            change_3m_percent=change,
            score=calculate_unsold_score(values),
            history_scores=history,
            observations=rows,
        )
