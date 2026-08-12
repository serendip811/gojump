from __future__ import annotations

import dataclasses
import math
import os
from collections.abc import Iterable

from backend.config import load_env
from backend.ecos import EcosClient, EcosObservation
from backend.kb_supply import KBSupplyClient, SupplyObservation, calculate_supply_score


@dataclasses.dataclass(frozen=True)
class SupplyBacktestRow:
    year: int
    units: int
    reference_units: float
    score: int
    signal_month: str
    return_24m: float | None
    return_36m: float | None
    drawdown_24m: float | None
    drawdown_36m: float | None


@dataclasses.dataclass(frozen=True)
class ClassificationResult:
    horizon_months: int
    score_threshold: int
    decline_threshold: float
    samples: int
    alerts: int
    declines: int
    true_positives: int
    precision: float | None
    recall: float | None


def _shift_month(year_month: str, offset: int) -> str:
    year, month = int(year_month[:4]), int(year_month[4:])
    absolute = year * 12 + month - 1 + offset
    return f"{absolute // 12:04d}{absolute % 12 + 1:02d}"


def _change(start: float, end: float) -> float:
    return (end / start - 1) * 100


def build_rows(
    pre_sale: Iterable[SupplyObservation],
    prices: Iterable[EcosObservation],
    baseline_years: int = 5,
    minimum_history: int = 3,
) -> list[SupplyBacktestRow]:
    """Score each completed year from prior years only, then measure later prices."""
    supply = {row.year: row.units for row in pre_sale}
    price = {row.time: row.value for row in prices}
    result: list[SupplyBacktestRow] = []
    years = sorted(supply)

    for year in years:
        history = [supply[candidate] for candidate in years if candidate < year][-baseline_years:]
        signal_month = f"{year}12"
        if len(history) < minimum_history or signal_month not in price:
            continue
        start = price[signal_month]

        def endpoint(horizon: int) -> float | None:
            value = price.get(_shift_month(signal_month, horizon))
            return None if value is None else _change(start, value)

        def drawdown(horizon: int) -> float | None:
            values = [
                price[month]
                for offset in range(1, horizon + 1)
                if (month := _shift_month(signal_month, offset)) in price
            ]
            return _change(start, min(values)) if len(values) == horizon else None

        reference = sum(history) / len(history)
        result.append(SupplyBacktestRow(
            year=year,
            units=supply[year],
            reference_units=reference,
            score=calculate_supply_score(supply[year], reference),
            signal_month=signal_month,
            return_24m=endpoint(24),
            return_36m=endpoint(36),
            drawdown_24m=drawdown(24),
            drawdown_36m=drawdown(36),
        ))
    return result


def evaluate(
    rows: Iterable[SupplyBacktestRow],
    horizon_months: int,
    score_threshold: int,
    decline_threshold: float = -5,
    use_drawdown: bool = False,
) -> ClassificationResult:
    attribute = ("drawdown" if use_drawdown else "return") + f"_{horizon_months}m"
    eligible = [(row, getattr(row, attribute)) for row in rows]
    eligible = [(row, outcome) for row, outcome in eligible if outcome is not None]
    alerts = [(row, outcome) for row, outcome in eligible if row.score >= score_threshold]
    declines = [(row, outcome) for row, outcome in eligible if outcome <= decline_threshold]
    true_positives = sum(outcome <= decline_threshold for _, outcome in alerts)
    return ClassificationResult(
        horizon_months, score_threshold, decline_threshold, len(eligible), len(alerts),
        len(declines), true_positives,
        true_positives / len(alerts) if alerts else None,
        true_positives / len(declines) if declines else None,
    )


def pearson(values: Iterable[tuple[float, float]]) -> float | None:
    pairs = list(values)
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def move_in_price_correlation(
    move_in: Iterable[SupplyObservation],
    prices: Iterable[EcosObservation],
) -> tuple[int, float | None]:
    price = {row.time: row.value for row in prices}
    pairs: list[tuple[float, float]] = []
    for row in move_in:
        start, end = price.get(f"{row.year}01"), price.get(f"{row.year}12")
        if start is not None and end is not None:
            pairs.append((row.units, _change(start, end)))
    return len(pairs), pearson(pairs)


def main() -> None:
    load_env()
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        raise SystemExit("ECOS_API_KEY is required")
    supply = KBSupplyClient().fetch()
    prices = EcosClient(key).fetch_seoul_apartment_price_index()
    rows_5y = build_rows(supply.pre_sale, prices, baseline_years=5, minimum_history=3)

    print("5y baseline: year units reference score return24 return36 drawdown24 drawdown36")
    for row in rows_5y:
        values = (row.year, row.units, round(row.reference_units), row.score,
                  row.return_24m, row.return_36m, row.drawdown_24m, row.drawdown_36m)
        print(" ".join(
            "-" if value is None else f"{value:.1f}" if isinstance(value, float) else str(value)
            for value in values
        ))
    for baseline, minimum in ((5, 3), (10, 5)):
        rows = build_rows(
            supply.pre_sale, prices, baseline_years=baseline, minimum_history=minimum
        )
        print(f"\n{baseline}y baseline, endpoint decline <= -5%")
        for horizon in (24, 36):
            outcomes = [
                (row.score, value)
                for row in rows
                if (value := getattr(row, f"return_{horizon}m")) is not None
            ]
            correlation = pearson(outcomes)
            correlation_text = "-" if correlation is None else f"{correlation:.3f}"
            print(f"{horizon}m score/return Pearson r={correlation_text}")
            for threshold in (60, 70, 80):
                result = evaluate(rows, horizon, threshold)
                precision = "-" if result.precision is None else f"{result.precision:.1%}"
                recall = "-" if result.recall is None else f"{result.recall:.1%}"
                print(f"  score>={threshold}: n={result.samples} alerts={result.alerts} "
                      f"declines={result.declines} tp={result.true_positives} "
                      f"precision={precision} recall={recall}")
    count, correlation = move_in_price_correlation(supply.move_in, prices)
    value = "-" if correlation is None else f"{correlation:.3f}"
    print(f"\nmove-in vs same-year price return: n={count}, Pearson r={value}")


if __name__ == "__main__":
    main()
