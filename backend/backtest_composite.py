from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable

from backend.backtest_liquidity import KB_PRICE_STAT, SEOUL_APARTMENT_ITEM
from backend.collector import shift_month
from backend.config import load_env
from backend.ecos import EcosClient, calculate_rate_score
from backend.houstat import HoustatObservation, calculate_affordability_score
from backend.kb_supply import SupplyObservation, calculate_supply_score
from backend.macro_store import MacroStore
from backend.snapshot import volume_score_from_history
from backend.subscription import SubscriptionObservation, build_subscription_snapshot
from backend.trade_store import TradeStore


WEIGHTS_5 = {"khai": .25, "volume": .20, "subscription": .15, "rate": .15, "supply": .15}
WEIGHTS_4 = {key: value for key, value in WEIGHTS_5.items() if key != "supply"}


@dataclasses.dataclass(frozen=True)
class CompositeRow:
    month: str
    price: float
    khai: int
    volume: int
    subscription: int
    rate: int
    supply: int
    score_5: int
    score_4: int


@dataclasses.dataclass(frozen=True)
class Evaluation:
    score_name: str
    horizon: int
    decline_percent: float
    threshold: int
    samples: int
    events: int
    alerts: int
    true_positives: int
    precision: float | None
    recall: float | None
    f1: float | None


@dataclasses.dataclass(frozen=True)
class PeakEpisode:
    peak_month: str
    peak_price: float
    future_low_month: str
    decline_percent: float
    first_alert_month: str | None
    alert_offset_months: int | None


def _weighted(scores: dict[str, int], weights: dict[str, float]) -> int:
    total = sum(weights.values())
    return round(sum(scores[key] * weight for key, weight in weights.items()) / total)


def _khai_available_month(period: str) -> str:
    year, quarter = int(period[:4]), int(period[4:])
    release_month = quarter * 3 + 3
    if release_month > 12:
        year, release_month = year + 1, release_month - 12
    return f"{year:04d}{release_month:02d}"


def khai_scores(rows: list[HoustatObservation], months: Iterable[str]) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: row.time)
    result = {}
    for month in months:
        available = [row.value for row in ordered if _khai_available_month(row.time) <= month]
        if available:
            result[month] = calculate_affordability_score(available)
    return result


def volume_scores(history: list[tuple[str, int]], months: Iterable[str]) -> dict[str, int]:
    return {
        month: volume_score_from_history([row for row in history if row[0] <= month])[0]
        for month in months
        if sum(period <= month for period, _ in history) >= 6
    }


def subscription_scores(
    observations: list[SubscriptionObservation],
) -> dict[str, int]:
    snapshot = build_subscription_snapshot(observations)
    return dict(zip(snapshot.history_months, snapshot.history_scores))


def rate_scores(
    mortgage: list[tuple[str, float]],
    base: list[tuple[str, float]],
    months: Iterable[str],
) -> dict[str, int]:
    mortgage = sorted(mortgage)
    base = sorted(base)
    result = {}
    for month in months:
        available_month = shift_month(month, -1)
        eligible_mortgage = [value for period, value in mortgage if period <= available_month]
        eligible_base = [value for period, value in base if period <= f"{available_month}31"]
        if eligible_mortgage and eligible_base:
            result[month] = calculate_rate_score(eligible_mortgage[-120:], eligible_base[-1])
    return result


def supply_scores(rows: list[SupplyObservation], months: Iterable[str]) -> dict[str, int]:
    """Shift annual pre-sale pressure 30 months as an ex-post completion proxy."""
    units = {row.year: row.units for row in rows}
    annual_scores = {}
    for year in sorted(units):
        history = [units[item] for item in sorted(units) if item < year][-5:]
        if len(history) >= 3:
            annual_scores[year] = calculate_supply_score(units[year], sum(history) / len(history))
    result = {}
    for month in months:
        source = shift_month(month, -30)
        if int(source[:4]) in annual_scores:
            result[month] = annual_scores[int(source[:4])]
    return result


def build_rows(
    prices: dict[str, float],
    khai: list[HoustatObservation],
    volume: list[tuple[str, int]],
    subscription: list[SubscriptionObservation],
    mortgage: list[tuple[str, float]],
    base: list[tuple[str, float]],
    pre_sale: list[SupplyObservation],
) -> list[CompositeRow]:
    months = sorted(prices)
    maps = {
        "khai": khai_scores(khai, months),
        "volume": volume_scores(volume, months),
        "subscription": subscription_scores(subscription),
        "rate": rate_scores(mortgage, base, months),
        "supply": supply_scores(pre_sale, months),
    }
    result = []
    for month in months:
        if not all(month in values for values in maps.values()):
            continue
        scores = {key: values[month] for key, values in maps.items()}
        result.append(CompositeRow(
            month, prices[month], scores["khai"], scores["volume"],
            scores["subscription"], scores["rate"], scores["supply"],
            _weighted(scores, WEIGHTS_5), _weighted(scores, WEIGHTS_4),
        ))
    return result


def evaluate(
    rows: list[CompositeRow],
    score_name: str,
    horizon: int,
    decline_percent: float,
    threshold: int,
) -> Evaluation:
    by_month = {row.month: row for row in rows}
    pairs = []
    for row in rows:
        future_months = [shift_month(row.month, offset) for offset in range(1, horizon + 1)]
        if not all(month in by_month for month in future_months):
            continue
        event = min(by_month[month].price for month in future_months) <= row.price * (1 - decline_percent / 100)
        pairs.append((getattr(row, score_name) >= threshold, event))
    tp = sum(alert and event for alert, event in pairs)
    alerts = sum(alert for alert, _ in pairs)
    events = sum(event for _, event in pairs)
    precision = tp / alerts if alerts else None
    recall = tp / events if events else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return Evaluation(
        score_name, horizon, decline_percent, threshold, len(pairs), events, alerts, tp,
        precision, recall, f1,
    )


def peak_episodes(
    rows: list[CompositeRow],
    score_name: str,
    horizon: int = 12,
    decline_percent: float = 5,
    threshold: int = 80,
) -> list[PeakEpisode]:
    candidates: list[int] = []
    for index, row in enumerate(rows):
        future = rows[index + 1 : index + horizon + 1]
        if len(future) == horizon and min(item.price for item in future) <= row.price * (1 - decline_percent / 100):
            candidates.append(index)
    groups: list[list[int]] = []
    for index in candidates:
        if not groups or index > groups[-1][-1] + 1:
            groups.append([index])
        else:
            groups[-1].append(index)
    episodes = []
    for group in groups:
        peak_index = max(group, key=lambda index: rows[index].price)
        peak = rows[peak_index]
        future = rows[peak_index + 1 : peak_index + horizon + 1]
        low = min(future, key=lambda row: row.price)
        alert_indexes = [
            index for index in range(max(0, peak_index - horizon), peak_index + 1)
            if getattr(rows[index], score_name) >= threshold
        ]
        alert_index = alert_indexes[0] if alert_indexes else None
        episodes.append(PeakEpisode(
            peak.month, peak.price, low.month,
            (low.price / peak.price - 1) * 100,
            rows[alert_index].month if alert_index is not None else None,
            alert_index - peak_index if alert_index is not None else None,
        ))
    return episodes


def leave_one_out_scores(rows: list[CompositeRow]) -> dict[str, list[int]]:
    result = {}
    for excluded in WEIGHTS_5:
        weights = {key: value for key, value in WEIGHTS_5.items() if key != excluded}
        result[excluded] = [
            _weighted({key: getattr(row, key) for key in WEIGHTS_5}, weights)
            for row in rows
        ]
    return result


def load_rows() -> list[CompositeRow]:
    load_env()
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        raise RuntimeError("ECOS_API_KEY is required")
    prices = {
        row.time: row.value
        for row in EcosClient(key).fetch_series(
            KB_PRICE_STAT, "M", "201901", "202607", SEOUL_APARTMENT_ITEM
        )
    }
    macro = MacroStore()
    trade = TradeStore()
    try:
        return build_rows(
            prices, macro.khai_series(), trade.monthly_counts(240),
            macro.subscription_series(),
            macro.rate_series("mortgage_rate_observations"),
            macro.rate_series("base_rate_observations"),
            macro.kb_supply_series("kb_pre_sale_observations"),
        )
    finally:
        macro.close()
        trade.close()


def main() -> None:
    rows = load_rows()
    print(f"range={rows[0].month}..{rows[-1].month}, months={len(rows)}")
    for score_name in ("score_5", "score_4"):
        print(f"\n{score_name}")
        for horizon in (6, 12):
            for decline in (5, 10):
                best = None
                for threshold in range(45, 81, 5):
                    result = evaluate(rows, score_name, horizon, decline, threshold)
                    if best is None or (result.f1 or 0) > (best.f1 or 0):
                        best = result
                assert best is not None
                print(dataclasses.asdict(best))
    print("\nselected")
    for row in rows:
        if row.month in {"202012", "202106", "202110", "202201", "202210", "202407", "202507", "202607"}:
            print(dataclasses.asdict(row))
    print("\nepisodes")
    for score_name in ("score_5", "score_4"):
        print(score_name, [dataclasses.asdict(row) for row in peak_episodes(rows, score_name)])


if __name__ == "__main__":
    main()
