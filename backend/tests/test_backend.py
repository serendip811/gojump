import unittest
import os
import tempfile
import json
from pathlib import Path

from backend.collector import MolitTradeClient, Trade, parse_trade_xml, previous_month
from backend.config import load_env
from backend.ecos import (
    EcosClient, EcosObservation, RateSnapshot, UnsoldHousingSnapshot,
    calculate_rate_score, calculate_unsold_score,
)
from backend.export_static_api import validate_snapshot
from backend.backtest_rate import align_base_rate, build_rows as build_rate_rows
from backend.backtest_supply import (
    build_rows as build_supply_rows,
    evaluate as evaluate_supply,
    move_in_price_correlation,
)
from backend.backtest_liquidity import (
    LiquidityBacktestRow,
    evaluate as evaluate_liquidity,
)
from backend.backtest_composite import (
    CompositeRow,
    khai_scores,
    peak_episodes as composite_peak_episodes,
    rate_scores as composite_rate_scores,
)
from backend.backtest_expansion_variants import (
    ExpansionPoint,
    combine_rows as combine_expansion_rows,
    expansion_points,
    phase_score,
)
from backend.houstat import (
    AffordabilitySnapshot, HoustatClient, HoustatObservation,
    calculate_affordability_score,
)
from backend.liquidity import LiquiditySnapshot, analyze_liquidity, calculate_liquidity_score
from backend.macro_store import MacroStore
from backend.seoul_supply import SeoulSupplyClient, SupplySnapshot, calculate_supply_score
from backend.kb_supply import KBSupplyClient, KBSupplySnapshot, SupplyObservation
from backend.snapshot import (
    WEIGHTS, calculate_score, expansion_signal, load_fixture, volume_score, volume_score_from_history,
    merge_composite_history, with_composite_history, with_price_history, with_live_affordability, with_live_liquidity, with_live_rate, with_live_supply,
    with_live_kb_supply, with_live_subscription, with_live_unsold, with_live_volume,
)
from backend.trade_store import TradeStore
from backend.subscription import (
    DETAIL_URL, SubscriptionClient, SubscriptionObservation,
    build_subscription_snapshot, calculate_subscription_score,
)


XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body>
<items>
  <item><dealAmount>120,000</dealAmount><dealYear>2026</dealYear><dealMonth>7</dealMonth><dealDay>2</dealDay><aptNm>Alpha</aptNm></item>
  <item><dealAmount>90,000</dealAmount><dealYear>2026</dealYear><dealMonth>7</dealMonth><dealDay>3</dealDay><aptNm>Beta</aptNm><cdealDay>26.07.10</cdealDay></item>
</items><numOfRows>1000</numOfRows><pageNo>1</pageNo><totalCount>2</totalCount>
</body></response>"""


class CollectorTests(unittest.TestCase):
    def test_parse_and_exclude_cancelled_trade(self):
        parsed, total = parse_trade_xml(XML, "11680")
        self.assertEqual(total, 2)
        self.assertEqual(parsed[0].amount_10k_krw, 120000)
        client = MolitTradeClient("key", transport=lambda _: XML)
        self.assertEqual(len(client.fetch_month("11680", "202607")), 1)

    def test_previous_month_crosses_year(self):
        self.assertEqual(previous_month("202601"), "202512")


class LiquidityTests(unittest.TestCase):
    @staticmethod
    def trade(year: int, month: int, day: int, apartment: str, amount: int) -> Trade:
        return Trade(
            district_code="11680", deal_year=year, deal_month=month, deal_day=day,
            amount_10k_krw=amount, apartment=apartment, legal_dong="테스트동",
            land_lot="1-1" if apartment == "Popular" else "2-2", area_sqm=84.9,
            floor=10, built_year=2010, apartment_sequence="", cancelled=False,
        )

    def test_store_replaces_month_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "test.sqlite3")
            rows = [self.trade(2026, 7, 1, "Popular", 100_000)]
            store.replace_district_month("11680", "202607", rows)
            store.replace_district_month("11680", "202607", rows)
            self.assertEqual(store.month_count("202607"), 1)
            self.assertEqual(store.monthly_counts(), [("202607", 1)])
            store.close()

    def test_analysis_detects_spread_into_low_liquidity_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "test.sqlite3")
            year, month = 2024, 8
            for index in range(24):
                absolute = year * 12 + month - 1 + index
                y, m = absolute // 12, absolute % 12 + 1
                period = f"{y:04d}{m:02d}"
                popular = [self.trade(y, m, day + 1, "Popular", 100_000 + index) for day in range(8)]
                low_count = 5 if index >= 21 else 1
                low = [self.trade(y, m, day + 15, "Low", 50_000 + index * 100 + day) for day in range(low_count)]
                store.replace_district_month("11680", period, popular + low)
            result = analyze_liquidity(store, "202607")
            self.assertGreater(result.recent_share_percent, result.baseline_share_percent)
            self.assertGreater(result.score, 50)
            store.close()

    def test_score_increases_with_share_record_and_spread(self):
        low = calculate_liquidity_score(5, 5, 10, 1)
        high = calculate_liquidity_score(20, 5, 80, 2)
        self.assertGreater(high, low)

    def test_backtest_excludes_unknown_future_and_measures_alerts(self):
        rows = [
            LiquidityBacktestRow("202001", 60, -6, -8, -9),
            LiquidityBacktestRow("202002", 50, 2, 3, -1),
            LiquidityBacktestRow("202003", 70, None, None, None),
        ]
        result = evaluate_liquidity(rows, 12, 55)
        self.assertEqual(result.samples, 2)
        self.assertEqual(result.alerts, 1)
        self.assertEqual(result.true_positives, 1)
        self.assertEqual(result.precision, 1)


class SnapshotTests(unittest.TestCase):
    def test_fixture_score_is_consistent(self):
        fixture = load_fixture()
        self.assertEqual(calculate_score(fixture["indicators"]), fixture["score"])

    def test_static_export_validation_rejects_fixture_in_production(self):
        with self.assertRaises(ValueError):
            validate_snapshot(load_fixture(), require_live=True)

    def test_static_export_accepts_sufficient_partial_live_snapshot(self):
        snapshot = load_fixture()
        snapshot["dataMode"] = "partialLive"
        snapshot["liveIndicatorCount"] = 5
        snapshot["freshIndicatorCount"] = 6
        snapshot["freshIndicatorIds"] = [
            "pir", "volume", "unpopular", "subscription", "rate", "supply"
        ]
        supply = next(row for row in snapshot["indicators"] if row["id"] == "supply")
        supply["rawHistory"] = list(range(10))
        supply["historyLabels"] = [str(year) for year in range(2017, 2027)]
        validate_snapshot(snapshot, require_live=True)

    def test_static_export_rejects_cached_or_fallback_indicator(self):
        snapshot = load_fixture()
        snapshot["dataMode"] = "live"
        snapshot["liveIndicatorCount"] = 6
        snapshot["freshIndicatorCount"] = 5
        snapshot["freshIndicatorIds"] = [
            "pir", "volume", "unpopular", "rate", "supply"
        ]
        with self.assertRaisesRegex(ValueError, "freshly collect all six"):
            validate_snapshot(snapshot, require_live=True)

    def test_static_export_rejects_short_production_history(self):
        snapshot = load_fixture()
        snapshot["dataMode"] = "live"
        snapshot["liveIndicatorCount"] = 6
        snapshot["freshIndicatorCount"] = 6
        snapshot["freshIndicatorIds"] = [
            "pir", "volume", "unpopular", "subscription", "rate", "supply"
        ]
        snapshot["history"] = [64]
        snapshot["historyLabels"] = ["2026 7월"]
        with self.assertRaisesRegex(ValueError, "at least 24 months"):
            validate_snapshot(snapshot, require_live=True)

    def test_static_export_rejects_short_expansion_history(self):
        snapshot = load_fixture()
        snapshot["dataMode"] = "live"
        snapshot["liveIndicatorCount"] = 6
        snapshot["freshIndicatorCount"] = 6
        snapshot["freshIndicatorIds"] = [
            "pir", "volume", "unpopular", "subscription", "rate", "supply"
        ]
        expansion = next(row for row in snapshot["indicators"] if row["id"] == "unpopular")
        expansion["rawHistory"] = [58]
        expansion["historyLabels"] = ["2026 7월"]
        with self.assertRaisesRegex(ValueError, "unpopular history"):
            validate_snapshot(snapshot, require_live=True)

    def test_expansion_signal_is_small_positive_bonus(self):
        fixture = load_fixture()
        indicator = next(row for row in fixture["indicators"] if row["id"] == "unpopular")
        score, bonus, stage = expansion_signal(indicator)
        self.assertEqual((score, stage), (65, "확산 중"))
        self.assertAlmostEqual(bonus, .75)

    def test_composite_history_keeps_full_actual_rows(self):
        history = [(f"2025{month:02d}", 40 + month) for month in range(1, 13)]
        history.append(("202601", 64))
        result = with_composite_history(load_fixture(), history)
        self.assertEqual(result["history"], list(range(41, 53)) + [64])
        self.assertEqual(result["historyLabels"][-1], "2026 1월")

    def test_composite_history_merges_fixture_and_latest_actual_month(self):
        fixture = load_fixture()
        result = merge_composite_history(fixture, [("202607", 64), ("202608", 66)])
        self.assertGreaterEqual(len(result["history"]), len(fixture["history"]))
        self.assertEqual(result["historyLabels"][-2:], ["2026 7월", "2026 8월"])
        self.assertEqual(result["history"][-2:], [64, 66])

    def test_price_history_keeps_values_and_month_labels(self):
        result = with_price_history(load_fixture(), [("202512", 99.1), ("202601", 100.0)])
        self.assertEqual(result["priceHistory"], [99.1, 100.0])
        self.assertEqual(result["priceHistoryLabels"], ["2025 12월", "2026 1월"])
        self.assertEqual(result["priceHistoryUnit"], "2026.01=100")

    def test_live_volume_updates_value_and_score(self):
        history = [("202606", 100), ("202607", 80)]
        result = with_live_volume(load_fixture(), 80, 100, "2026년 7월", history)
        volume = next(item for item in result["indicators"] if item["id"] == "volume")
        self.assertEqual(volume["value"], "80건")
        self.assertEqual(volume["score"], volume_score(80, 100))
        self.assertEqual(volume["rawHistory"], [100, 80])
        self.assertEqual(volume["historyLabels"], ["2026 6월", "2026 7월"])
        self.assertEqual(volume["historyUnit"], "건")
        self.assertEqual(result["dataMode"], "partialLive")
        self.assertEqual(result["deltaLabel"], "거래량 반영")

    def test_volume_history_score_uses_three_month_and_seasonal_comparisons(self):
        history = [
            ("202205", 1722), ("202206", 1063), ("202207", 645),
            ("202305", 3354), ("202306", 3852), ("202307", 3594),
            ("202405", 5112), ("202406", 7626), ("202407", 8901),
            ("202505", 7577), ("202506", 11270), ("202507", 4149),
            ("202602", 5796), ("202603", 5516), ("202604", 8646),
            ("202605", 8942), ("202606", 5254), ("202607", 4720),
        ]
        score, change_3m, change_1y, change_seasonal = volume_score_from_history(history)
        self.assertEqual(score, 55)
        self.assertAlmostEqual(change_3m, -5.22, places=2)
        self.assertAlmostEqual(change_1y, -17.74, places=2)
        self.assertAlmostEqual(change_seasonal, 16.63, places=2)

    def test_live_rate_updates_indicator_and_count(self):
        rates = RateSnapshot(
            base_rate=EcosObservation("20260720", 2.75, "한국은행 기준금리", "연%"),
            mortgage_rate=EcosObservation("202606", 4.36, "주택담보대출", "연리%"),
            mortgage_change_3m=.11,
            score=67,
            history_scores=[42, 45, 50, 54, 59, 62, 65, 67],
            mortgage_observations=[
                EcosObservation("202605", 4.20, "주택담보대출", "연리%"),
                EcosObservation("202606", 4.36, "주택담보대출", "연리%"),
            ],
            base_observations=[
                EcosObservation("20260528", 2.50, "한국은행 기준금리", "연%"),
                EcosObservation("20260618", 2.75, "한국은행 기준금리", "연%"),
            ],
        )
        result = with_live_rate(with_live_volume(load_fixture(), 80, 100, "2026년 7월"), rates)
        rate = next(item for item in result["indicators"] if item["id"] == "rate")
        self.assertEqual(rate["value"], "4.36%")
        self.assertEqual(rate["score"], 67)
        self.assertEqual(rate["rawHistory"], [4.20, 4.36])
        self.assertEqual(rate["secondaryRawHistory"], [2.50, 2.75])
        self.assertEqual(rate["historyLabels"], ["2026 5월", "2026 6월"])
        self.assertEqual(result["liveIndicatorCount"], 2)

    def test_live_unsold_updates_subscription_indicator(self):
        observations = [
            EcosObservation("202605", 985, "서울", "호"),
            EcosObservation("202606", 1013, "서울", "호"),
        ]
        unsold = UnsoldHousingSnapshot(
            latest=EcosObservation("202606", 1013, "서울", "호"),
            change_3m_percent=-1.46,
            score=38,
            history_scores=[22, 30, 42, 55, 63, 58, 54, 56],
            observations=observations,
        )
        result = with_live_unsold(load_fixture(), unsold)
        item = next(row for row in result["indicators"] if row["id"] == "subscription")
        self.assertEqual(item["shortTitle"], "미분양")
        self.assertEqual(item["value"], "1,013호")
        self.assertEqual(item["rawHistory"], [985, 1013])
        self.assertEqual(item["historyLabels"], ["2026 5월", "2026 6월"])
        self.assertEqual(result["liveIndicatorCount"], 3)

    def test_live_affordability_replaces_pir_indicator(self):
        periods = [
            "202401", "202402", "202403", "202404",
            "202501", "202502", "202503", "202504", "202601",
        ]
        observations = [
            HoustatObservation(period, 150.0 + index)
            for index, period in enumerate(periods)
        ]
        affordability = AffordabilitySnapshot(
            latest=HoustatObservation("202601", 179.3),
            change_1y=23.6,
            score=88,
            history_scores=[53, 60, 64, 68, 72, 77, 84, 100],
            observations=observations,
        )
        result = with_live_affordability(load_fixture(), affordability)
        item = next(row for row in result["indicators"] if row["id"] == "pir")
        self.assertEqual(item["shortTitle"], "구입부담")
        self.assertEqual(item["value"], "179.3")
        self.assertEqual(item["rawHistory"], [row.value for row in observations])
        self.assertEqual(len(item["historyLabels"]), 9)
        self.assertEqual(item["historyLabels"][0], "2024 1Q")
        self.assertEqual(item["historyLabels"][-1], "2026 1Q")
        self.assertEqual(result["liveIndicatorCount"], 4)

    def test_live_supply_updates_indicator_and_increments_count(self):
        supply = SupplySnapshot(2026, 27158, 2027, 17197, 44355, 13, [28, 13, 0])
        base = load_fixture()
        base["liveIndicatorCount"] = 4
        result = with_live_supply(base, supply)
        item = next(row for row in result["indicators"] if row["id"] == "supply")
        self.assertEqual(item["value"], "4.4만호")
        self.assertEqual(item["score"], 13)
        self.assertEqual(item["rawHistory"], [27158, 17197])
        self.assertEqual(item["historyLabels"], ["2026", "2027"])
        self.assertEqual(item["historyReferenceValue"], 35000)
        self.assertEqual(result["liveIndicatorCount"], 5)

    def test_live_liquidity_completes_six_live_indicators(self):
        liquidity = LiquiditySnapshot(3.61, 2.75, 67.64, 1.08, 57, [50, 51, 52], "2026년 7월")
        base = load_fixture()
        base["liveIndicatorCount"] = 5
        result = with_live_liquidity(base, liquidity)
        item = next(row for row in result["indicators"] if row["id"] == "unpopular")
        self.assertEqual(item["shortTitle"], "확산도 Beta")
        self.assertNotIn("unpopular", WEIGHTS)
        self.assertEqual(item["value"], "3.6%")
        self.assertEqual(result["liveIndicatorCount"], 6)
        self.assertEqual(result["dataMode"], "live")


class EcosTests(unittest.TestCase):
    def test_fetch_series_parses_official_shape(self):
        payload = json.dumps({
            "StatisticSearch": {
                "list_total_count": 1,
                "row": [{
                    "TIME": "202606", "DATA_VALUE": "4.36",
                    "ITEM_NAME1": "주택담보대출", "UNIT_NAME": "연리%",
                }],
            }
        }).encode()
        rows = EcosClient("sample", transport=lambda _: payload).fetch_series(
            "121Y006", "M", "202606", "202606", "BECBLA0302"
        )
        self.assertEqual(rows[0].value, 4.36)

    def test_rate_score_increases_with_high_rising_rate(self):
        low = calculate_rate_score([2.0, 2.1, 2.2, 2.1], 1.5)
        high = calculate_rate_score([2.0, 2.5, 3.2, 4.4], 3.0)
        self.assertGreater(high, low)

    def test_unsold_score_increases_with_high_rising_inventory(self):
        low = calculate_unsold_score([1200, 1100, 1000, 900])
        high = calculate_unsold_score([900, 1000, 1100, 1400])
        self.assertGreater(high, low)


class HoustatTests(unittest.TestCase):
    def test_fetch_seoul_parses_official_shape(self):
        payload = json.dumps({
            "SttsApiTblData": [
                {"head": [{"list_total_count": 18}, {"RESULT": {"CODE": "INFO-000"}}]},
                {"row": [
                    {"ITM_NM": "전국", "DTA_VAL": 61.5},
                    {"ITM_NM": "서울", "DTA_VAL": 179.3},
                ]},
            ]
        }).encode()
        row = HoustatClient(transport=lambda _: payload).fetch_seoul("202601")
        self.assertIsNotNone(row)
        self.assertEqual(row.value, 179.3)

    def test_missing_period_returns_none(self):
        payload = json.dumps({"RESULT": {"CODE": "INFO-200", "MESSAGE": "no data"}}).encode()
        self.assertIsNone(HoustatClient(transport=lambda _: payload).fetch_seoul("202602"))

    def test_authenticated_series_parses_all_seoul_rows(self):
        payload = json.dumps({
            "SttsApiTblData": [
                {"head": [{"list_total_count": 2}, {"RESULT": {"CODE": "INFO-000"}}]},
                {"row": [
                    {"WRTTIME_IDTFR_ID": "202504", "ITM_NM": "서울", "DTA_VAL": 165.1},
                    {"WRTTIME_IDTFR_ID": "202601", "ITM_NM": "서울", "DTA_VAL": 179.3},
                ]},
            ]
        }).encode()
        rows = HoustatClient("real-key", transport=lambda _: payload).fetch_seoul_series()
        self.assertEqual([row.value for row in rows], [165.1, 179.3])

    def test_affordability_score_increases_with_high_rising_burden(self):
        low = calculate_affordability_score([100, 98, 96, 94, 92])
        high = calculate_affordability_score([100, 110, 125, 145, 180])
        self.assertGreater(high, low)

    def test_macro_store_upserts_full_khai_series(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_khai([
                HoustatObservation("200401", 116.3),
                HoustatObservation("202601", 179.3),
            ])
            store.upsert_khai([HoustatObservation("202601", 180.0)])
            rows = store.khai_series()
            self.assertEqual([row.time for row in rows], ["200401", "202601"])
            self.assertEqual(rows[-1].value, 180.0)
            store.close()

    def test_macro_store_keeps_latest_composite_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_composite_scores([("202601", 60), ("202602", 62)])
            store.upsert_composite_scores([("202602", 64), ("202603", 63)])
            self.assertEqual(store.composite_scores(2), [("202602", 64), ("202603", 63)])
            store.close()

    def test_macro_store_upserts_seoul_apartment_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_seoul_apartment_prices([
                EcosObservation("202512", 99.1, "아파트(서울)", "2026.01=100"),
                EcosObservation("202601", 100.0, "아파트(서울)", "2026.01=100"),
            ])
            store.upsert_seoul_apartment_prices([
                EcosObservation("202512", 99.2, "아파트(서울)", "2026.01=100"),
            ])
            self.assertEqual(store.seoul_apartment_prices(), [("202512", 99.2), ("202601", 100.0)])
            store.close()

    def test_macro_store_upserts_unsold_series(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_unsold([
                EcosObservation("201608", 372, "서울", "호"),
                EcosObservation("202606", 1013, "서울", "호"),
            ])
            store.upsert_unsold([EcosObservation("202606", 1014, "서울", "호")])
            self.assertEqual(store.unsold_series(), [("201608", 372.0), ("202606", 1014.0)])
            store.close()

    def test_macro_store_upserts_subscription_series(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_subscription([
                SubscriptionObservation("202602", 29, 222, 32, 228),
                SubscriptionObservation("202603", 578, 90750, 539, 54885),
            ])
            store.upsert_subscription([
                SubscriptionObservation("202602", 30, 225, 32, 228),
            ])
            rows = store.subscription_series()
            self.assertEqual([row.time for row in rows], ["202602", "202603"])
            self.assertEqual(rows[0].general_supply, 30)
            store.close()

    def test_macro_store_upserts_rate_series(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MacroStore(Path(directory) / "test.sqlite3")
            store.upsert_rates(
                [EcosObservation("202605", 4.2, "주택담보대출", "%")],
                [EcosObservation("20260528", 2.5, "기준금리", "%")],
            )
            store.upsert_rates(
                [EcosObservation("202605", 4.3, "주택담보대출", "%")], []
            )
            self.assertEqual(
                store.rate_series("mortgage_rate_observations"), [("202605", 4.3)]
            )
            self.assertEqual(
                store.rate_series("base_rate_observations"), [("20260528", 2.5)]
            )
            store.close()


class SubscriptionTests(unittest.TestCase):
    def test_fetch_parses_seoul_rows(self):
        download_url = (
            "https://www.data.go.kr/cmm/cmm/fileDownload.do?"
            "atchFileId=FILE_TEST&amp;fileDetailSn=1"
        )
        html = f'<a href="{download_url}">download</a>'.encode()
        payload = (
            "연월,시도,특별공급 공급세대수,특별공급 접수건수,특별공급 경쟁률,"
            "일반공급 공급세대수,일반공급 접수건수,일반공급 경쟁률\n"
            "2026-06,서울,608,6338,10.42,601,10292,17.12\n"
            "2026-06,부산,100,100,1.00,100,100,1.00\n"
        ).encode("utf-8-sig")
        client = SubscriptionClient(
            transport=lambda url: html if url == DETAIL_URL else payload
        )
        rows = client.fetch_seoul_history()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].time, "202606")
        self.assertAlmostEqual(rows[0].general_rate or 0, 17.1248, places=3)

    def test_score_increases_when_competition_falls(self):
        strong = calculate_subscription_score(150, 500, 100)
        weak = calculate_subscription_score(10, 500, 100)
        self.assertGreater(weak, strong)

    def test_small_supply_reduces_extreme_score(self):
        low_confidence = calculate_subscription_score(1, 30, 100)
        high_confidence = calculate_subscription_score(1, 500, 100)
        self.assertLess(low_confidence, high_confidence)

    def test_snapshot_uses_weighted_three_month_rate(self):
        rows = [
            SubscriptionObservation("202501", 100, 10_000, 0, 0),
            SubscriptionObservation("202502", 200, 10_000, 0, 0),
            SubscriptionObservation("202503", 300, 6_000, 0, 0),
        ]
        result = build_subscription_snapshot(rows)
        self.assertAlmostEqual(result.latest_rate, 26_000 / 600)
        self.assertEqual(result.latest_supply_3m, 600)

    def test_live_subscription_keeps_unsold_as_secondary_signal(self):
        subscription = build_subscription_snapshot([
            SubscriptionObservation("202504", 400, 40_000, 0, 0),
            SubscriptionObservation("202505", 400, 20_000, 0, 0),
            SubscriptionObservation("202506", 400, 8_000, 0, 0),
        ])
        unsold = UnsoldHousingSnapshot(
            latest=EcosObservation("202506", 1013, "서울", "호"),
            change_3m_percent=-1.5,
            score=77,
            history_scores=[70, 77],
            observations=[EcosObservation("202505", 985, "서울", "호"),
                          EcosObservation("202506", 1013, "서울", "호")],
        )
        result = with_live_subscription(load_fixture(), subscription, unsold)
        item = next(row for row in result["indicators"] if row["id"] == "subscription")
        self.assertEqual(item["title"], "서울 청약 수요")
        self.assertEqual(item["secondaryValue"], "1,013호")
        self.assertEqual(item["rawHistory"][-1], subscription.latest_rate)


class SeoulSupplyTests(unittest.TestCase):
    def test_fetch_parses_official_totals(self):
        payload = json.dumps({
            "ocvoTotalDetail": {
                "yr2": "2026", "yr1": "2027",
                "sum06_sum": 27158, "sum05_sum": 17197, "sum03_sum": 44355,
            }
        }).encode()
        result = SeoulSupplyClient(transport=lambda _: payload).fetch()
        self.assertEqual(result.total_units, 44355)
        self.assertEqual(result.score, calculate_supply_score(44355 / 2))

    def test_supply_score_increases_above_reference(self):
        self.assertLess(calculate_supply_score(20_000), calculate_supply_score(50_000))


class KBSupplyTests(unittest.TestCase):
    @staticmethod
    def payload(rows):
        return json.dumps({"dataBody": {"data": {"차트데이터": [
            {"일정": str(year), "합계": {"세대수": units, "단지개수": 1}}
            for year, units in rows
        ]}}}).encode()

    def test_fetch_builds_ten_year_reference_without_future(self):
        move_rows = [(year, 35_000) for year in range(2016, 2026)] + [
            (2026, 20_000), (2027, 15_000), (2028, 5_000),
        ]
        payloads = iter([self.payload(move_rows), self.payload([(2025, 30_000)])])
        result = KBSupplyClient(transport=lambda _: next(payloads), current_year=2026).fetch()
        self.assertEqual(result.reference_annual_units, 35_000)
        self.assertEqual(result.forecast_average_units, 17_500)
        self.assertEqual(result.score, 0)

    def test_live_snapshot_exposes_long_history_and_forecast_start(self):
        move_in = [SupplyObservation(year, 30_000) for year in range(1990, 2029)]
        supply = KBSupplySnapshot(move_in, [], 2026, 35_000, 30_000, 36)
        base = load_fixture()
        base["dataMode"] = "partialLive"
        base["liveIndicatorCount"] = 4
        result = with_live_kb_supply(base, supply)
        item = next(row for row in result["indicators"] if row["id"] == "supply")
        self.assertEqual(len(item["rawHistory"]), 39)
        self.assertEqual(item["historyForecastStartLabel"], "2026")
        self.assertEqual(result["liveIndicatorCount"], 5)
        self.assertEqual(result["dataMode"], "partialLive")

    def test_kb_supply_and_liquidity_complete_six_live_indicators(self):
        move_in = [SupplyObservation(year, 30_000) for year in range(2016, 2028)]
        supply = KBSupplySnapshot(move_in, [], 2026, 35_000, 30_000, 36)
        liquidity = LiquiditySnapshot(
            3.61, 2.75, 67.64, 1.08, 57, [50, 51, 52], "2026년 7월"
        )
        base = load_fixture()
        base["dataMode"] = "partialLive"
        base["liveIndicatorCount"] = 4

        result = with_live_liquidity(with_live_kb_supply(base, supply), liquidity)

        self.assertEqual(result["liveIndicatorCount"], 6)
        self.assertEqual(result["dataMode"], "live")


class SupplyBacktestTests(unittest.TestCase):
    def test_uses_prior_supply_only_and_aligns_24_month_return(self):
        supply = [SupplyObservation(year, units) for year, units in (
            (2010, 100), (2011, 100), (2012, 100), (2013, 200),
        )]
        prices = [
            EcosObservation("201312", 100, "서울", "index"),
            EcosObservation("201512", 90, "서울", "index"),
        ]
        rows = build_supply_rows(supply, prices)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reference_units, 100)
        self.assertEqual(rows[0].score, 100)
        self.assertAlmostEqual(rows[0].return_24m, -10)

    def test_evaluation_excludes_rows_without_full_horizon(self):
        supply = [SupplyObservation(year, 100) for year in range(2010, 2015)]
        prices = [
            EcosObservation("201312", 100, "서울", "index"),
            EcosObservation("201512", 94, "서울", "index"),
            EcosObservation("201412", 100, "서울", "index"),
        ]
        result = evaluate_supply(build_supply_rows(supply, prices), 24, 50)
        self.assertEqual(result.samples, 1)
        self.assertEqual(result.true_positives, 1)

    def test_move_in_correlation_returns_sample_count(self):
        move_in = [SupplyObservation(2020, 100), SupplyObservation(2021, 200)]
        prices = [
            EcosObservation("202001", 100, "", ""),
            EcosObservation("202012", 110, "", ""),
            EcosObservation("202101", 100, "", ""),
            EcosObservation("202112", 80, "", ""),
        ]
        count, correlation = move_in_price_correlation(move_in, prices)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(correlation, -1)


class CompositeBacktestTests(unittest.TestCase):
    def test_khai_is_available_three_months_after_quarter_end(self):
        observations = [HoustatObservation("202101", 120)]
        scores = khai_scores(observations, ["202105", "202106"])
        self.assertNotIn("202105", scores)
        self.assertIn("202106", scores)

    def test_rate_uses_previous_month_observation(self):
        scores = composite_rate_scores(
            [("202101", 2.5), ("202102", 5.0)],
            [("20210101", 1.0), ("20210201", 3.0)],
            ["202102"],
        )
        self.assertEqual(scores["202102"], calculate_rate_score([2.5], 1.0))

    def test_peak_episode_reports_first_pre_peak_alert(self):
        rows = []
        for index, (month, price, score) in enumerate((
            ("202101", 100, 70), ("202102", 105, 82), ("202103", 110, 85),
            ("202104", 100, 70), ("202105", 90, 60),
        )):
            rows.append(CompositeRow(month, price, 0, 0, 0, 0, 0, score, score))
        episodes = composite_peak_episodes(rows, "score_5", horizon=2, decline_percent=10)
        self.assertEqual(episodes[0].peak_month, "202103")
        self.assertEqual(episodes[0].first_alert_month, "202102")
        self.assertEqual(episodes[0].alert_offset_months, -1)

    def test_expansion_components_use_trailing_history_only(self):
        before = expansion_points([("202101", 60), ("202102", 58)])
        after = expansion_points([("202101", 60), ("202102", 58), ("202103", 20)])
        self.assertEqual(before[-1], after[1])
        self.assertEqual(before[-1].rollover, 66)

    def test_five_percent_variant_has_bounded_influence(self):
        row = CompositeRow("202101", 100, 0, 0, 0, 0, 0, 80, 80)
        expansion = {"202101": ExpansionPoint("202101", 50, 50, 50)}
        combined = combine_expansion_rows([row], expansion, "level40_roll60", 5)
        self.assertEqual(combined[0].score_5, 78)

    def test_bonus_mode_never_reduces_base_score(self):
        row = CompositeRow("202101", 100, 0, 0, 0, 0, 0, 80, 80)
        expansion = {"202101": ExpansionPoint("202101", 40, 30, 40)}
        combined = combine_expansion_rows(
            [row], expansion, "level40_roll60", 5, mode="bonus"
        )
        self.assertEqual(combined[0].score_5, 80)

    def test_phase_mix_emphasizes_rollover(self):
        point = ExpansionPoint("202101", 60, 70, 90)
        self.assertEqual(phase_score(point, "level40_roll60"), 82)

class ConfigTests(unittest.TestCase):
    def test_load_env_supports_quotes_and_does_not_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("GOJUMP_TEST_KEY='from-file'\nEXISTING_KEY=file\n", encoding="utf-8")
            os.environ["EXISTING_KEY"] = "process"
            try:
                loaded = load_env(path)
                self.assertEqual(os.environ["GOJUMP_TEST_KEY"], "from-file")
                self.assertEqual(os.environ["EXISTING_KEY"], "process")
                self.assertEqual(loaded, {"GOJUMP_TEST_KEY"})
            finally:
                os.environ.pop("GOJUMP_TEST_KEY", None)
                os.environ.pop("EXISTING_KEY", None)


class RateBacktestTests(unittest.TestCase):
    def test_base_rate_is_aligned_at_month_end(self):
        base = [("20200116", 1.25), ("20200317", .75), ("20200528", .5)]
        self.assertEqual(align_base_rate("202003", base), .75)
        self.assertEqual(align_base_rate("202004", base), .75)

    def test_historical_score_does_not_see_future_mortgage_rates(self):
        mortgage = [("202001", 2.5), ("202002", 2.6), ("202003", 2.7)]
        base = [("20191231", 1.25)]
        prices = {"202001": 100, "202002": 101, "202003": 102}
        rows = build_rate_rows(mortgage, base, prices)
        first_expected = calculate_rate_score([2.5], 1.25)
        self.assertEqual(rows[0].score, first_expected)
        self.assertNotEqual(rows[0].score, calculate_rate_score([2.5, 2.6, 2.7], 1.25))


if __name__ == "__main__":
    unittest.main()
