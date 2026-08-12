from __future__ import annotations

import dataclasses
import json

from backend.backtest_unsold import fetch_prices
from backend.ecos import calculate_rate_score
from backend.macro_store import MacroStore


@dataclasses.dataclass(frozen=True)
class BacktestRow:
    month: str
    price: float
    mortgage_rate: float
    base_rate: float
    score: int


def align_base_rate(month: str, base: list[tuple[str, float]]) -> float | None:
    month_end = f"{month}31"
    eligible = [value for period, value in base if period <= month_end]
    return float(eligible[-1]) if eligible else None


def build_rows(
    mortgage: list[tuple[str, float]],
    base: list[tuple[str, float]],
    prices: dict[str, float],
) -> list[BacktestRow]:
    mortgage = sorted(mortgage)
    base = sorted(base)
    price_months = sorted(prices)
    smoothed = {
        month: sum(prices[item] for item in price_months[max(0, i - 2) : i + 1])
        / min(3, i + 1)
        for i, month in enumerate(price_months)
    }
    rows = []
    values = [float(value) for _, value in mortgage]
    for index, (month, mortgage_rate) in enumerate(mortgage):
        base_rate = align_base_rate(month, base)
        if month not in smoothed or base_rate is None:
            continue
        history = values[max(0, index - 119) : index + 1]
        rows.append(
            BacktestRow(
                month=month,
                price=smoothed[month],
                mortgage_rate=float(mortgage_rate),
                base_rate=base_rate,
                score=calculate_rate_score(history, base_rate),
            )
        )
    return rows


def load_rows() -> list[BacktestRow]:
    store = MacroStore()
    try:
        mortgage = store.rate_series("mortgage_rate_observations")
        base = store.rate_series("base_rate_observations")
    finally:
        store.close()
    if not mortgage or not base:
        raise RuntimeError("No stored ECOS rate observations")
    return build_rows(mortgage, base, fetch_prices())


def confusion(
    rows: list[BacktestRow], horizon: int, decline: float, threshold: int = 65
) -> dict[str, float | int]:
    evaluated = rows[:-horizon]
    actual = [
        min(item.price for item in rows[i + 1 : i + horizon + 1])
        <= row.price * (1 - decline)
        for i, row in enumerate(evaluated)
    ]
    predicted = [row.score >= threshold for row in evaluated]
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(not p and a for p, a in zip(predicted, actual))
    tn = sum(not p and not a for p, a in zip(predicted, actual))
    return {
        "months": len(evaluated),
        "positives": sum(actual),
        "signals": sum(predicted),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
    }


def peak_episodes(
    rows: list[BacktestRow], horizon: int = 12, decline: float = .10,
    threshold: int = 65,
) -> list[dict]:
    candidates = []
    for index, row in enumerate(rows[:-horizon]):
        future_low = min(item.price for item in rows[index + 1 : index + horizon + 1])
        if future_low <= row.price * (1 - decline):
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
        signal_index = next(
            (
                index
                for index in range(max(0, peak_index - 6), min(len(rows), peak_index + 13))
                if rows[index].score >= threshold
            ),
            None,
        )
        episodes.append(
            {
                "peak": peak.month,
                "price": round(peak.price),
                "mortgage_rate": peak.mortgage_rate,
                "base_rate": peak.base_rate,
                "score": peak.score,
                "first_signal": rows[signal_index].month if signal_index is not None else None,
                "offset_months": signal_index - peak_index if signal_index is not None else None,
            }
        )
    return episodes


if __name__ == "__main__":
    rows = load_rows()
    result = {
        "range": [rows[0].month, rows[-1].month],
        "rows": len(rows),
        "latest": dataclasses.asdict(rows[-1]),
        "thresholds_12m_drop_10": {
            str(threshold): confusion(rows, 12, .10, threshold)
            for threshold in (55, 60, 65, 70, 75, 80)
        },
        "future_6m_drop_10": confusion(rows, 6, .10),
        "future_12m_drop_10": confusion(rows, 12, .10),
        "future_12m_drop_15": confusion(rows, 12, .15),
        "episodes": peak_episodes(rows),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
