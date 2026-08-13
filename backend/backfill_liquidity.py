import argparse

from backend.collector import shift_month
from backend.liquidity import analyze_liquidity
from backend.trade_store import TradeStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalculate liquidity score history")
    parser.add_argument("--start", required=True, help="First score month, YYYYMM")
    parser.add_argument("--end", required=True, help="Last score month, YYYYMM")
    args = parser.parse_args()
    store = TradeStore()
    try:
        month = args.start
        while month <= args.end:
            analyze_liquidity(store, month)
            month = shift_month(month, 1)
        print(f"Stored {len(store.liquidity_scores(args.end))} monthly liquidity scores")
    finally:
        store.close()


if __name__ == "__main__":
    main()
