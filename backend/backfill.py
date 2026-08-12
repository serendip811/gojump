from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.collector import MolitTradeClient, SEOUL_DISTRICTS, shift_month
from backend.config import load_env
from backend.trade_store import TradeStore


def fetch_with_delay(
    client: MolitTradeClient, district: str, month: str, delay: float,
):
    try:
        return client.fetch_month(district, month)
    finally:
        if delay > 0:
            time.sleep(delay)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Backfill Seoul apartment trades")
    parser.add_argument("--end", required=True, help="Last month, YYYYMM")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--delay", type=float, default=.5, help="Delay after each request")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")

    store = TradeStore()
    months = [shift_month(args.end, offset) for offset in range(-(args.months - 1), 1)]
    jobs = [
        (district, month) for month in months for district in SEOUL_DISTRICTS
        if args.refresh or not store.is_collected(district, month)
    ]
    client = MolitTradeClient(key)
    print(f"Backfill: {len(jobs)} district-month requests ({len(months)} months)")
    completed = 0
    failed: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(fetch_with_delay, client, district, month, args.delay): (district, month)
            for district, month in jobs
        }
        for future in as_completed(futures):
            district, month = futures[future]
            try:
                store.replace_district_month(district, month, future.result())
            except Exception as error:
                failed.append((district, month, type(error).__name__))
            completed += 1
            if completed % 25 == 0 or completed == len(jobs):
                print(f"  {completed}/{len(jobs)}")
    store.close()
    if failed:
        preview = ", ".join(f"{district}/{month}:{error}" for district, month, error in failed[:5])
        raise SystemExit(f"Backfill completed with {len(failed)} failed jobs: {preview}")


if __name__ == "__main__":
    main()
