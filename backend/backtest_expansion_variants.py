from __future__ import annotations

import dataclasses

from backend.backtest_composite import CompositeRow, evaluate, load_rows, peak_episodes
from backend.trade_store import TradeStore


VARIANT_MIXES: dict[str, tuple[float, float]] = {
    "raw_level": (1.0, 0.0),
    "amplified_level": (1.0, 0.0),
    "level25_roll75": (.25, .75),
    "level40_roll60": (.40, .60),
    "level60_roll40": (.60, .40),
    "rollover_only": (0.0, 1.0),
}


@dataclasses.dataclass(frozen=True)
class ExpansionPoint:
    month: str
    raw: int
    level: int
    rollover: int


@dataclasses.dataclass(frozen=True)
class VariantResult:
    variant: str
    mode: str
    weight_percent: int
    precision_6m_5: float | None
    recall_6m_5: float | None
    precision_12m_5: float | None
    recall_12m_5: float | None
    precision_12m_10: float | None
    recall_12m_10: float | None
    alerts_12m_5: int
    first_alert_month: str | None
    alert_offset_months: int | None
    latest_score: int


def _clamp(value: float) -> int:
    return round(max(0, min(100, value)))


def expansion_points(history: list[tuple[str, int]], trailing_months: int = 6) -> list[ExpansionPoint]:
    points = []
    for index, (month, raw) in enumerate(history):
        prior = [value for _, value in history[max(0, index - trailing_months + 1) : index + 1]]
        # Observed scores occupy a narrow middle band. Double their distance
        # from neutral so 60 means a meaningful, but not maximal, expansion.
        level = _clamp(50 + (raw - 50) * 2)
        decline_from_peak = max(prior) - raw
        rollover = _clamp(50 + decline_from_peak * 8)
        points.append(ExpansionPoint(month, raw, level, rollover))
    return points


def phase_score(point: ExpansionPoint, variant: str) -> int:
    if variant == "raw_level":
        return point.raw
    level_weight, rollover_weight = VARIANT_MIXES[variant]
    return round(point.level * level_weight + point.rollover * rollover_weight)


def combine_rows(
    rows: list[CompositeRow],
    expansion: dict[str, ExpansionPoint],
    variant: str,
    weight_percent: int,
    mode: str = "weighted",
) -> list[CompositeRow]:
    weight = weight_percent / 100
    result = []
    for row in rows:
        point = expansion.get(row.month)
        if point is None:
            continue
        phase = phase_score(point, variant)
        if mode == "bonus":
            combined = min(100, round(row.score_5 + max(0, phase - 50) * weight))
        elif mode == "weighted":
            combined = round(row.score_5 * (1 - weight) + phase * weight)
        else:
            raise ValueError(f"Unknown combination mode: {mode}")
        result.append(dataclasses.replace(row, score_5=combined))
    return result


def evaluate_variant(
    baseline_rows: list[CompositeRow],
    expansion: dict[str, ExpansionPoint],
    variant: str,
    weight_percent: int,
    mode: str = "weighted",
) -> VariantResult:
    rows = combine_rows(baseline_rows, expansion, variant, weight_percent, mode)
    result_6_5 = evaluate(rows, "score_5", 6, 5, 80)
    result_12_5 = evaluate(rows, "score_5", 12, 5, 80)
    result_12_10 = evaluate(rows, "score_5", 12, 10, 80)
    episodes = peak_episodes(rows, "score_5", 12, 5, 80)
    episode = episodes[0] if episodes else None
    return VariantResult(
        variant, mode, weight_percent,
        result_6_5.precision, result_6_5.recall,
        result_12_5.precision, result_12_5.recall,
        result_12_10.precision, result_12_10.recall,
        result_12_5.alerts,
        episode.first_alert_month if episode else None,
        episode.alert_offset_months if episode else None,
        rows[-1].score_5,
    )


def load_expansion() -> dict[str, ExpansionPoint]:
    store = TradeStore()
    try:
        history = store.liquidity_scores("999912", 240)
    finally:
        store.close()
    return {point.month: point for point in expansion_points(history)}


def main() -> None:
    rows = load_rows()
    expansion = load_expansion()
    common = [row for row in rows if row.month in expansion]
    baseline = evaluate_variant(common, expansion, "raw_level", 0)
    print("baseline", dataclasses.asdict(baseline))
    results = [
        evaluate_variant(common, expansion, variant, weight, mode)
        for mode in ("weighted", "bonus")
        for variant in VARIANT_MIXES
        for weight in (3, 5, 10)
    ]
    results.sort(key=lambda row: (
        -(row.recall_12m_5 or 0), -(row.precision_12m_5 or 0),
        row.alert_offset_months or 0, row.weight_percent,
    ))
    for row in results:
        print(dataclasses.asdict(row))


if __name__ == "__main__":
    main()
