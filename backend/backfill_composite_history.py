from backend.backtest_composite import load_rows
from backend.backtest_expansion_variants import combine_rows, load_expansion
from backend.macro_store import MacroStore


def build_composite_history() -> list[tuple[str, int]]:
    expansion = load_expansion()
    rows = [row for row in load_rows() if row.month in expansion]
    combined = combine_rows(rows, expansion, "level60_roll40", 5, mode="bonus")
    return [(row.month, row.score_5) for row in combined]


def main() -> None:
    history = build_composite_history()
    store = MacroStore()
    try:
        store.upsert_composite_scores(history)
    finally:
        store.close()
    print(f"Stored {len(history)} monthly composite scores: {history[0][0]}..{history[-1][0]}")


if __name__ == "__main__":
    main()
