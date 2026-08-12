from __future__ import annotations

import csv
import dataclasses
import io
import math
import re
import urllib.request
from collections.abc import Callable


DETAIL_URL = (
    "https://www.data.go.kr/tcs/dss/selectFileDataDetailView.do?publicDataPk=15110988"
)


@dataclasses.dataclass(frozen=True)
class SubscriptionObservation:
    time: str
    general_supply: int
    general_applications: int
    special_supply: int
    special_applications: int

    @property
    def general_rate(self) -> float | None:
        return self.general_applications / self.general_supply if self.general_supply else None


@dataclasses.dataclass(frozen=True)
class SubscriptionSnapshot:
    latest_time: str
    latest_rate: float
    latest_supply_3m: int
    change_1y_percent: float
    score: int
    history_rates: list[float]
    history_scores: list[int]
    history_months: list[str]


def _clamp(value: float) -> float:
    return max(0, min(100, value))


def calculate_subscription_score(
    current_rate: float,
    current_supply: int,
    year_ago_rate: float | None,
) -> int:
    """Return demand-cooling risk; higher means weaker subscription demand."""
    absolute = _clamp(100 - 25 * math.log10(max(current_rate, 1)))
    annual = _clamp(
        50 + math.log((year_ago_rate + 1) / (current_rate + 1)) * 30
    ) if year_ago_rate is not None else 50
    raw = absolute * .50 + annual * .50
    # A single small complex can make a monthly rate extreme. Pull low-sample
    # windows toward neutral until at least 300 homes were offered in 3 months.
    confidence = min(1, current_supply / 300)
    return round(50 + (raw - 50) * confidence)


def _month_range(start: str, end: str) -> list[str]:
    year, month = int(start[:4]), int(start[4:])
    end_year, end_month = int(end[:4]), int(end[4:])
    result = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def build_subscription_snapshot(
    observations: list[SubscriptionObservation],
) -> SubscriptionSnapshot:
    if not observations:
        raise ValueError("Subscription history is empty")
    rows = {row.time: row for row in observations}
    months = _month_range(min(rows), max(rows))
    rates: list[float | None] = []
    supplies: list[int] = []
    for index in range(len(months)):
        window = months[max(0, index - 2) : index + 1]
        supply = sum(rows[month].general_supply for month in window if month in rows)
        applications = sum(
            rows[month].general_applications for month in window if month in rows
        )
        rates.append(applications / supply if supply else None)
        supplies.append(supply)

    valid_indexes = [index for index, rate in enumerate(rates) if rate is not None]
    history_months = [months[index] for index in valid_indexes]
    history_rates = [float(rates[index]) for index in valid_indexes]
    history_scores = []
    for index in valid_indexes:
        rate = float(rates[index])
        year_ago = rates[index - 12] if index >= 12 else None
        history_scores.append(
            calculate_subscription_score(rate, supplies[index], year_ago)
        )
    latest_index = valid_indexes[-1]
    latest_rate = float(rates[latest_index])
    year_ago = rates[latest_index - 12] if latest_index >= 12 else None
    change = ((latest_rate / year_ago) - 1) * 100 if year_ago else 0
    return SubscriptionSnapshot(
        latest_time=months[latest_index],
        latest_rate=latest_rate,
        latest_supply_3m=supplies[latest_index],
        change_1y_percent=change,
        score=history_scores[-1],
        history_rates=history_rates,
        history_scores=history_scores,
        history_months=history_months,
    )


class SubscriptionClient:
    def __init__(self, transport: Callable[[str], bytes] | None = None) -> None:
        self.transport = transport or self._download

    @staticmethod
    def _download(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "GoJump/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def fetch_seoul_history(self) -> list[SubscriptionObservation]:
        html = self.transport(DETAIL_URL).decode("utf-8")
        match = re.search(
            r'https://www\.data\.go\.kr/cmm/cmm/fileDownload\.do\?atchFileId=[^"\']+',
            html,
        )
        if match is None:
            raise RuntimeError("Subscription CSV download URL was not found")
        csv_url = match.group(0).replace("&amp;", "&")
        text = self.transport(csv_url).decode("utf-8-sig")
        rows = []
        for row in csv.DictReader(io.StringIO(text)):
            if row["시도"].strip() != "서울":
                continue
            rows.append(
                SubscriptionObservation(
                    time=row["연월"].replace("-", ""),
                    general_supply=int(row["일반공급 공급세대수"]),
                    general_applications=int(row["일반공급 접수건수"]),
                    special_supply=int(row["특별공급 공급세대수"]),
                    special_applications=int(row["특별공급 접수건수"]),
                )
            )
        if not rows:
            raise RuntimeError("Subscription CSV contains no Seoul observations")
        return sorted(rows, key=lambda row: row.time)
