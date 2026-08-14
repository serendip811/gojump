from __future__ import annotations

from collections.abc import Iterable

from backend.backtest_composite import (
    khai_scores,
    rate_scores,
    subscription_scores,
    volume_scores,
)
from backend.houstat import HoustatObservation
from backend.snapshot import PRICE_BURDEN_WEIGHTS, TRANSITION_WEIGHTS
from backend.subscription import SubscriptionObservation


def _weighted(scores: dict[str, int], weights: dict[str, float]) -> int:
    return round(sum(scores[key] * weight for key, weight in weights.items()))


def build_price_burden_history(
    khai: list[HoustatObservation],
    mortgage: list[tuple[str, float]],
    base: list[tuple[str, float]],
    months: Iterable[str],
) -> list[tuple[str, int]]:
    """Build an as-known-at-the-time burden series, including publication lags."""
    ordered_months = sorted(set(months))
    maps = {
        "pir": khai_scores(khai, ordered_months),
        "rate": rate_scores(mortgage, base, ordered_months),
    }
    return [
        (month, _weighted({key: values[month] for key, values in maps.items()}, PRICE_BURDEN_WEIGHTS))
        for month in ordered_months
        if all(month in values for values in maps.values())
    ]


def build_transition_history(
    volume: list[tuple[str, int]],
    subscription: list[SubscriptionObservation],
    months: Iterable[str],
) -> list[tuple[str, int]]:
    """Build a causal demand-cooling series; future observations are never read."""
    ordered_months = sorted(set(months))
    maps = {
        "volume": volume_scores(volume, ordered_months),
        "subscription": subscription_scores(subscription),
    }
    return [
        (month, _weighted({key: values[month] for key, values in maps.items()}, TRANSITION_WEIGHTS))
        for month in ordered_months
        if all(month in values for values in maps.values())
    ]
