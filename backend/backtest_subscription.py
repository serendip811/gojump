from __future__ import annotations

import dataclasses
import json

from backend.backtest_unsold import fetch_prices
from backend.macro_store import MacroStore
from backend.subscription import (
    SubscriptionClient,
    SubscriptionObservation,
    calculate_subscription_score,
)


@dataclasses.dataclass(frozen=True)
class BacktestRow:
    month: str
    price: float
    competition: float | None
    supply_3m: int
    score: int


def month_range(start: str, end: str) -> list[str]:
    year, month = int(start[:4]), int(start[4:])
    end_year, end_month = int(end[:4]), int(end[4:])
    result = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def rolling_rate(
    months: list[str], observations: dict[str, SubscriptionObservation], index: int
) -> tuple[float | None, int]:
    window = months[max(0, index - 2) : index + 1]
    supply = sum(observations[month].general_supply for month in window if month in observations)
    applications = sum(
        observations[month].general_applications for month in window if month in observations
    )
    return (applications / supply if supply else None, supply)


def load_rows(refresh: bool = True) -> list[BacktestRow]:
    store = MacroStore()
    try:
        if refresh:
            store.upsert_subscription(SubscriptionClient().fetch_seoul_history())
        observations = {row.time: row for row in store.subscription_series()}
    finally:
        store.close()
    if not observations:
        raise RuntimeError("No subscription observations are stored")

    prices = fetch_prices()
    price_months = sorted(prices)
    smoothed_prices = {
        month: sum(prices[item] for item in price_months[max(0, i - 2) : i + 1])
        / min(3, i + 1)
        for i, month in enumerate(price_months)
    }
    months = month_range(min(observations), max(observations))
    rates = [rolling_rate(months, observations, i) for i in range(len(months))]
    rows = []
    for i, month in enumerate(months):
        rate, supply = rates[i]
        if month not in smoothed_prices or rate is None:
            continue
        year_ago = rates[i - 12][0] if i >= 12 else None
        rows.append(
            BacktestRow(
                month=month,
                price=smoothed_prices[month],
                competition=rate,
                supply_3m=supply,
                score=calculate_subscription_score(rate, supply, year_ago),
            )
        )
    return rows


def confusion(
    rows: list[BacktestRow], horizon: int, decline: float, threshold: int = 65
) -> dict[str, float | int]:
    prices = fetch_prices()
    price_months = sorted(prices)
    smoothed = {
        month: sum(prices[item] for item in price_months[max(0, i - 2) : i + 1])
        / min(3, i + 1)
        for i, month in enumerate(price_months)
    }
    evaluated: list[tuple[bool, bool]] = []
    for row in rows:
        index = price_months.index(row.month)
        future_months = price_months[index + 1 : index + horizon + 1]
        if len(future_months) < horizon:
            continue
        actual = min(smoothed[month] for month in future_months) <= row.price * (1 - decline)
        evaluated.append((row.score >= threshold, actual))
    tp = sum(predicted and actual for predicted, actual in evaluated)
    fp = sum(predicted and not actual for predicted, actual in evaluated)
    fn = sum(not predicted and actual for predicted, actual in evaluated)
    tn = sum(not predicted and not actual for predicted, actual in evaluated)
    return {
        "months": len(evaluated),
        "positives": tp + fn,
        "signals": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
    }


def selected_months(rows: list[BacktestRow]) -> list[dict]:
    targets = {"202110", "202204", "202210", "202503", "202606"}
    return [
        {
            "month": row.month,
            "competition_3m": round(row.competition or 0, 1),
            "supply_3m": row.supply_3m,
            "score": row.score,
        }
        for row in rows
        if row.month in targets
    ]


if __name__ == "__main__":
    history = SubscriptionClient().fetch_seoul_history()
    rows = load_rows(refresh=True)
    result = {
        "source_range": [history[0].time, history[-1].time],
        "source_rows": len(history),
        "calendar_months": len(rows),
        "latest": dataclasses.asdict(rows[-1]),
        "future_6m_drop_10": confusion(rows, 6, .10),
        "future_12m_drop_10": confusion(rows, 12, .10),
        "future_12m_drop_15": confusion(rows, 12, .15),
        "selected_months": selected_months(rows),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
