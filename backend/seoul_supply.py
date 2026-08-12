from __future__ import annotations

import dataclasses
import json
import ssl
import urllib.request
from collections.abc import Callable
from pathlib import Path


SUPPLY_URL = "https://housinginfo.seoul.go.kr/hmpg/mabu/esoc/ovst/ovstTotalDetail.json"
REFERENCE_ANNUAL_UNITS = 35_000
INTERMEDIATE_CERT = Path(__file__).parent / "certs" / "globalsign-gcc-r6-alphassl-ca-2025.pem"


@dataclasses.dataclass(frozen=True)
class SupplySnapshot:
    first_year: int
    first_year_units: int
    second_year: int
    second_year_units: int
    total_units: int
    score: int
    history_scores: list[int]


def calculate_supply_score(annual_units: float, reference: int = REFERENCE_ANNUAL_UNITS) -> int:
    if reference <= 0:
        return 50
    ratio = annual_units / reference
    return max(0, min(100, round(50 + (ratio - 1) * 100)))


class SeoulSupplyClient:
    def __init__(self, transport: Callable[[str], bytes] | None = None) -> None:
        self.transport = transport or self._download

    @staticmethod
    def _download(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            data=b"",
            headers={
                "User-Agent": "GoJump/0.1",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            method="POST",
        )
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(INTERMEDIATE_CERT))
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            return response.read()

    def fetch(self) -> SupplySnapshot:
        data = json.loads(self.transport(SUPPLY_URL))
        detail = data.get("ocvoTotalDetail")
        if not detail:
            raise RuntimeError("Seoul supply endpoint returned an unexpected response")

        first_year = int(detail["yr2"])
        second_year = int(detail["yr1"])
        first_units = int(detail["sum06_sum"])
        second_units = int(detail["sum05_sum"])
        total = int(detail["sum03_sum"])
        if first_units + second_units != total:
            raise RuntimeError("Seoul supply totals are inconsistent")
        annual_average = total / 2
        return SupplySnapshot(
            first_year=first_year,
            first_year_units=first_units,
            second_year=second_year,
            second_year_units=second_units,
            total_units=total,
            score=calculate_supply_score(annual_average),
            history_scores=[
                calculate_supply_score(first_units),
                calculate_supply_score(annual_average),
                calculate_supply_score(second_units),
            ],
        )
