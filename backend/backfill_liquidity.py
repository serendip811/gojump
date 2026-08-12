from backend.collector import shift_month
from backend.liquidity import analyze_liquidity
from backend.trade_store import TradeStore


def main() -> None:
    store = TradeStore()
    try:
        month = "202012"
        while month <= "202607":
            analyze_liquidity(store, month)
            month = shift_month(month, 1)
        print(f"Stored {len(store.liquidity_scores('202607'))} monthly liquidity scores")
    finally:
        store.close()


if __name__ == "__main__":
    main()
