from __future__ import annotations

import dataclasses
import os

from backend.collector import shift_month
from backend.config import load_env
from backend.ecos import EcosClient
from backend.liquidity import analyze_liquidity
from backend.trade_store import TradeStore


KB_PRICE_STAT = "901Y062"
SEOUL_APARTMENT_ITEM = "P63ACA"


@dataclasses.dataclass(frozen=True)
class LiquidityBacktestRow:
    month: str
    score: int
    return_6m: float | None
    return_12m: float | None
    drawdown_12m: float | None


@dataclasses.dataclass(frozen=True)
class BacktestResult:
    horizon_months: int
    score_threshold: int
    samples: int
    alerts: int
    declines: int
    true_positives: int
    precision: float | None
    recall: float | None


def build_rows(
    store: TradeStore,
    prices: dict[str, float],
    start_month: str,
    end_month: str,
) -> list[LiquidityBacktestRow]:
    rows: list[LiquidityBacktestRow] = []
    month = start_month
    while month <= end_month:
        snapshot = analyze_liquidity(store, month)
        start = prices.get(month)

        def change(horizon: int) -> float | None:
            target = prices.get(shift_month(month, horizon))
            return None if start is None or target is None else (target / start - 1) * 100

        future = [prices.get(shift_month(month, offset)) for offset in range(1, 13)]
        drawdown = None
        if start is not None and all(value is not None for value in future):
            drawdown = (min(value for value in future if value is not None) / start - 1) * 100
        rows.append(LiquidityBacktestRow(
            month, snapshot.score, change(6), change(12), drawdown
        ))
        month = shift_month(month, 1)
    return rows


def evaluate(
    rows: list[LiquidityBacktestRow],
    horizon_months: int,
    score_threshold: int,
    decline_threshold: float = -5,
) -> BacktestResult:
    attribute = f"return_{horizon_months}m"
    eligible = [(row, getattr(row, attribute)) for row in rows]
    eligible = [(row, outcome) for row, outcome in eligible if outcome is not None]
    alerts = [(row, outcome) for row, outcome in eligible if row.score >= score_threshold]
    declines = [(row, outcome) for row, outcome in eligible if outcome <= decline_threshold]
    true_positives = sum(outcome <= decline_threshold for _, outcome in alerts)
    return BacktestResult(
        horizon_months, score_threshold, len(eligible), len(alerts), len(declines),
        true_positives,
        true_positives / len(alerts) if alerts else None,
        true_positives / len(declines) if declines else None,
    )


def main() -> None:
    load_env()
    key = os.environ.get("ECOS_API_KEY")
    if not key:
        raise SystemExit("ECOS_API_KEY is required")
    prices = {
        row.time: row.value
        for row in EcosClient(key).fetch_series(
            KB_PRICE_STAT, "M", "201901", "202607", SEOUL_APARTMENT_ITEM
        )
    }
    store = TradeStore()
    try:
        rows = build_rows(store, prices, "202012", "202601")
    finally:
        store.close()
    for horizon in (6, 12):
        for threshold in (55, 60, 65):
            result = evaluate(rows, horizon, threshold)
            precision = "-" if result.precision is None else f"{result.precision:.1%}"
            recall = "-" if result.recall is None else f"{result.recall:.1%}"
            print(f"{horizon}m score>={threshold}: n={result.samples} alerts={result.alerts} "
                  f"declines={result.declines} tp={result.true_positives} "
                  f"precision={precision} recall={recall}")


if __name__ == "__main__":
    main()
