from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from backend.collector import MolitTradeClient, SEOUL_DISTRICTS, previous_month
from backend.config import load_env
from backend.ecos import EcosClient
from backend.houstat import HoustatClient
from backend.liquidity import analyze_liquidity
from backend.macro_store import MacroStore
from backend.seoul_supply import SeoulSupplyClient
from backend.kb_supply import KBSupplyClient
from backend.snapshot import (
    load_fixture, merge_composite_history, with_price_history, with_live_affordability, with_live_kb_supply, with_live_liquidity, with_live_rate, with_live_supply,
    with_live_subscription, with_live_unsold, with_live_volume,
)
from backend.subscription import SubscriptionClient, build_subscription_snapshot
from backend.trade_store import TradeStore


def build_snapshot(year_month: str | None = None) -> dict:
    snapshot = load_fixture()
    fresh_indicator_ids: set[str] = set()
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        snapshot["dataMode"] = "fixture"
        return snapshot

    if year_month is None:
        from datetime import date, timedelta
        last_month = date.today().replace(day=1) - timedelta(days=1)
        year_month = last_month.strftime("%Y%m")

    client = MolitTradeClient(key)
    previous_year_month = previous_month(year_month)
    store = TradeStore()
    trade_warnings: list[str] = []
    try:
        current_trades = client.fetch_seoul_month(year_month)
        for district_code in SEOUL_DISTRICTS:
            store.replace_district_month(
                district_code, year_month,
                [trade for trade in current_trades if trade.district_code == district_code],
            )
        current_count = len(current_trades)
        fresh_indicator_ids.add("volume")
    except Exception as error:
        if not store.is_seoul_month_complete(year_month):
            store.close()
            raise
        current_count = store.month_count(year_month)
        trade_warnings.append(
            f"MOLIT refresh unavailable; complete cached month used: {type(error).__name__}"
        )
    if store.is_seoul_month_complete(previous_year_month):
        previous_count = store.month_count(previous_year_month)
    else:
        previous_trades = client.fetch_seoul_month(previous_year_month)
        previous_count = len(previous_trades)
        for district_code in SEOUL_DISTRICTS:
            store.replace_district_month(
                district_code, previous_year_month,
                [trade for trade in previous_trades if trade.district_code == district_code],
            )
    snapshot = with_live_volume(
        snapshot, current_count, previous_count,
        f"{year_month[:4]}년 {int(year_month[4:])}월",
        store.monthly_counts(240),
    )
    if trade_warnings:
        snapshot.setdefault("dataWarnings", []).extend(trade_warnings)
    ecos = EcosClient(os.getenv("ECOS_API_KEY", "sample"))
    rates = ecos.fetch_rates()
    macro_store = MacroStore()
    try:
        macro_store.upsert_rates(rates.mortgage_observations, rates.base_observations)
    finally:
        macro_store.close()
    snapshot = with_live_rate(snapshot, rates)
    fresh_indicator_ids.add("rate")
    unsold = ecos.fetch_seoul_unsold()
    macro_store = MacroStore()
    try:
        macro_store.upsert_unsold(unsold.observations)
    finally:
        macro_store.close()
    try:
        subscription_rows = SubscriptionClient().fetch_seoul_history()
        macro_store = MacroStore()
        try:
            macro_store.upsert_subscription(subscription_rows)
        finally:
            macro_store.close()
        snapshot = with_live_subscription(
            snapshot, build_subscription_snapshot(subscription_rows), unsold
        )
        fresh_indicator_ids.add("subscription")
    except Exception as error:
        snapshot = with_live_unsold(snapshot, unsold)
        warnings = snapshot.setdefault("dataWarnings", [])
        warnings.append(f"Subscription unavailable: {type(error).__name__}")
    houstat = HoustatClient(os.getenv("HOUSTAT_API_KEY", "sample"))
    try:
        affordability = houstat.fetch_affordability()
        macro_store = MacroStore()
        try:
            macro_store.upsert_khai(affordability.observations)
        finally:
            macro_store.close()
        snapshot = with_live_affordability(snapshot, affordability)
        fresh_indicator_ids.add("pir")
    except Exception as error:
        snapshot["dataWarnings"] = [f"HOUSTAT unavailable: {type(error).__name__}"]
    try:
        seoul_supply = SeoulSupplyClient().fetch()
        kb_supply = KBSupplyClient().fetch()
        macro_store = MacroStore()
        try:
            macro_store.upsert_kb_supply(kb_supply.move_in, kb_supply.pre_sale)
        finally:
            macro_store.close()
        snapshot = with_live_kb_supply(snapshot, kb_supply, seoul_supply)
        fresh_indicator_ids.add("supply")
    except Exception as error:
        warnings = snapshot.setdefault("dataWarnings", [])
        warnings.append(f"KB supply unavailable: {type(error).__name__}")
        try:
            snapshot = with_live_supply(snapshot, SeoulSupplyClient().fetch())
            fresh_indicator_ids.add("supply")
        except Exception as fallback_error:
            warnings.append(f"Seoul supply unavailable: {type(fallback_error).__name__}")
    try:
        snapshot = with_live_liquidity(snapshot, analyze_liquidity(store, year_month))
        if "volume" in fresh_indicator_ids:
            fresh_indicator_ids.add("unpopular")
    except Exception as error:
        warnings = snapshot.setdefault("dataWarnings", [])
        warnings.append(f"Liquidity unavailable: {type(error).__name__}")
    finally:
        store.close()
    macro_store = MacroStore()
    try:
        macro_store.upsert_composite_scores([(year_month, snapshot["score"])])
        try:
            prices = ecos.fetch_kb_seoul_apartment_price_index(end=year_month)
            macro_store.upsert_seoul_apartment_prices(prices)
        except Exception as error:
            warnings = snapshot.setdefault("dataWarnings", [])
            warnings.append(f"Seoul price index unavailable: {type(error).__name__}")
        snapshot = merge_composite_history(snapshot, macro_store.composite_scores(240))
        price_history = macro_store.seoul_apartment_prices(240)
        if price_history:
            snapshot = with_price_history(snapshot, price_history)
    finally:
        macro_store.close()
    snapshot["freshIndicatorIds"] = sorted(fresh_indicator_ids)
    snapshot["freshIndicatorCount"] = len(fresh_indicator_ids)
    return snapshot


class Handler(BaseHTTPRequestHandler):
    snapshot: dict = {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json({"status": "ok", "dataMode": self.snapshot.get("dataMode")})
        elif path == "/v1/markets/seoul/snapshot":
            self._json(self.snapshot)
        else:
            self._json({"error": "not_found"}, status=404)

    def _json(self, value: dict, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[gojump] {format % args}")


def main() -> None:
    loaded_keys = load_env()
    parser = argparse.ArgumentParser(description="GoJump snapshot API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--month", help="MOLIT query month, YYYYMM")
    args = parser.parse_args()
    Handler.snapshot = build_snapshot(args.month)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    env_source = ".env loaded" if "DATA_GO_KR_SERVICE_KEY" in loaded_keys else "process env or fixture"
    print(f"GoJump API http://{args.host}:{args.port} ({Handler.snapshot['dataMode']}, {env_source})")
    server.serve_forever()


if __name__ == "__main__":
    main()
