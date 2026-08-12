from __future__ import annotations

import dataclasses
import datetime as dt
import json
import urllib.request
from collections.abc import Callable


MOVE_IN_URL = (
    "https://api.kbland.kr/land-extra/lots/v1/api/aptMovinCnt?"
    "%EA%B8%B0%EA%B0%84%EA%B5%AC%EB%B6%84=1&"
    "%EB%B2%95%EC%A0%95%EB%8F%99%EC%BD%94%EB%93%9C=1100000000"
)
PRE_SALE_URL = (
    "https://api.kbland.kr/land-extra/lots/v1/api/aptSelotCnt?"
    "%EA%B8%B0%EA%B0%84%EA%B5%AC%EB%B6%84=1&"
    "%EC%83%81%EC%84%B8%EB%B9%84%EC%A4%91%EA%B5%AC%EB%B6%84=0&"
    "%EB%B2%95%EC%A0%95%EB%8F%99%EC%BD%94%EB%93%9C=1100000000"
)


@dataclasses.dataclass(frozen=True)
class SupplyObservation:
    year: int
    units: int


@dataclasses.dataclass(frozen=True)
class KBSupplySnapshot:
    move_in: list[SupplyObservation]
    pre_sale: list[SupplyObservation]
    forecast_start_year: int
    reference_annual_units: float
    forecast_average_units: float
    score: int


def calculate_supply_score(annual_units: float, reference: float) -> int:
    if reference <= 0:
        return 50
    return max(0, min(100, round(50 + (annual_units / reference - 1) * 100)))


class KBSupplyClient:
    def __init__(
        self,
        transport: Callable[[str], bytes] | None = None,
        current_year: int | None = None,
    ) -> None:
        self.transport = transport or self._download
        self.current_year = current_year or dt.date.today().year

    @staticmethod
    def _download(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "GoJump/0.1",
                "Accept": "application/json",
                "Origin": "https://data.kbland.kr",
                "Referer": "https://data.kbland.kr/",
                "osType": "HUB",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()

    @staticmethod
    def _parse(payload: bytes) -> list[SupplyObservation]:
        data = json.loads(payload)
        rows = data["dataBody"]["data"]["차트데이터"]
        return [
            SupplyObservation(int(row["일정"]), int(row["합계"]["세대수"]))
            for row in rows
        ]

    def fetch(self) -> KBSupplySnapshot:
        move_in = self._parse(self.transport(MOVE_IN_URL))
        pre_sale = self._parse(self.transport(PRE_SALE_URL))
        actual = [row.units for row in move_in if self.current_year - 10 <= row.year < self.current_year]
        forecast = [row.units for row in move_in if self.current_year <= row.year <= self.current_year + 1]
        if len(actual) < 5 or len(forecast) < 2:
            raise RuntimeError("KB supply history is incomplete")
        reference = sum(actual) / len(actual)
        forecast_average = sum(forecast) / len(forecast)
        return KBSupplySnapshot(
            move_in=move_in,
            pre_sale=pre_sale,
            forecast_start_year=self.current_year,
            reference_annual_units=reference,
            forecast_average_units=forecast_average,
            score=calculate_supply_score(forecast_average, reference),
        )
