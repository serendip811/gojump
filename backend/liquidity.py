from __future__ import annotations

import dataclasses
import math
from collections import Counter, defaultdict

from backend.collector import shift_month
from backend.trade_store import TradeStore


@dataclasses.dataclass(frozen=True)
class LiquiditySnapshot:
    recent_share_percent: float
    baseline_share_percent: float
    record_high_share_percent: float
    active_group_ratio: float
    score: int
    history_scores: list[int]
    observed_at: str
    history_months: list[str] = dataclasses.field(default_factory=list)


def _group(row: object) -> tuple[str, str, str, str, str, int]:
    return (
        row["district_code"], row["apartment_sequence"], row["legal_dong"],
        row["apartment"], row["land_lot"], int(row["area_bucket"]),
    )


def _clamp(value: float) -> float:
    return max(0, min(100, value))


def calculate_liquidity_score(
    recent_share: float,
    baseline_share: float,
    record_share: float,
    active_ratio: float,
) -> int:
    share_component = _clamp(50 + (recent_share - baseline_share) * 3)
    record_component = _clamp(record_share)
    spread_component = _clamp(50 + (active_ratio - 1) * 50)
    return round(share_component * .50 + record_component * .30 + spread_component * .20)


def analyze_liquidity(store: TradeStore, end_month: str) -> LiquiditySnapshot:
    start_month = shift_month(end_month, -23)
    recent_start = shift_month(end_month, -2)
    rows = store.trades_between(start_month, end_month)
    training = [row for row in rows if row["year_month"] < recent_start]
    recent = [row for row in rows if row["year_month"] >= recent_start]
    if not training or not recent:
        raise RuntimeError("Trade history is insufficient for liquidity analysis")

    counts = Counter(_group(row) for row in training)
    ordered_counts = sorted(counts.values())
    threshold_index = max(0, math.ceil(len(ordered_counts) * .20) - 1)
    threshold = ordered_counts[threshold_index]
    low_groups = {group for group, count in counts.items() if count <= threshold}

    baseline_low = [row for row in training if _group(row) in low_groups]
    recent_low = [row for row in recent if _group(row) in low_groups]
    baseline_share = len(baseline_low) / len(training) * 100
    recent_share = len(recent_low) / len(recent) * 100

    prior_highs: dict[tuple, int] = defaultdict(int)
    for row in training:
        group = _group(row)
        prior_highs[group] = max(prior_highs[group], int(row["amount_10k_krw"]))
    record_count = sum(
        int(row["amount_10k_krw"]) >= prior_highs[_group(row)]
        for row in recent_low if prior_highs[_group(row)] > 0
    )
    record_share = record_count / len(recent_low) * 100 if recent_low else 0

    training_months: dict[str, set[tuple]] = defaultdict(set)
    for row in baseline_low:
        training_months[row["year_month"]].add(_group(row))
    monthly_active = (
        sum(len(groups) for groups in training_months.values()) / 21
        if training_months else 0
    )
    recent_active = len({_group(row) for row in recent_low})
    active_ratio = recent_active / (monthly_active * 3) if monthly_active else 1

    score = calculate_liquidity_score(
        recent_share, baseline_share, record_share, active_ratio
    )
    store.upsert_liquidity_score(end_month, score)
    history = store.liquidity_scores(end_month)
    return LiquiditySnapshot(
        recent_share_percent=recent_share,
        baseline_share_percent=baseline_share,
        record_high_share_percent=record_share,
        active_group_ratio=active_ratio,
        score=score,
        history_scores=[value for _, value in history],
        observed_at=f"{end_month[:4]}년 {int(end_month[4:])}월",
        history_months=[month for month, _ in history],
    )
