import XCTest
@testable import GoJump

final class ScoreCalculatorTests: XCTestCase {
    func testLevelBoundaries() {
        XCTAssertEqual(MarketLevel.from(score: 24), .stable)
        XCTAssertEqual(MarketLevel.from(score: 25), .watch)
        XCTAssertEqual(MarketLevel.from(score: 65), .alert)
        XCTAssertEqual(MarketLevel.from(score: 80), .highRisk)
    }

    func testWeightedSampleScore() {
        XCTAssertEqual(ScoreCalculator.score(for: MarketSnapshot.sample.indicators), MarketSnapshot.sample.score)
    }

    func testMissingIndicatorsRenormalizeWeights() {
        let pir = MarketSnapshot.sample.indicators.first { $0.id == "pir" }!
        XCTAssertEqual(ScoreCalculator.score(for: [pir]), pir.score)
    }

    func testSnapshotCachePayloadRoundTrip() throws {
        let encoded = try JSONEncoder().encode(MarketSnapshot.sample)
        let decoded = try JSONDecoder().decode(MarketSnapshot.self, from: encoded)
        XCTAssertEqual(decoded.score, 64)
        XCTAssertEqual(decoded.indicators.count, 6)
        XCTAssertEqual(decoded.dataMode, "sample")
        XCTAssertEqual(decoded.liveIndicatorCount, 0)
    }

    func testSnapshotGeneratedAtUsesSeoulDisplayTimeAndStaleness() throws {
        let liveJSON = try JSONEncoder().encode(MarketSnapshot.sample)
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: liveJSON) as? [String: Any])
        object["generatedAt"] = "2026-08-12T21:17:00.000000Z"
        object["dataMode"] = "live"
        let data = try JSONSerialization.data(withJSONObject: object)
        let snapshot = try JSONDecoder().decode(MarketSnapshot.self, from: data)

        XCTAssertEqual(snapshot.generatedAtLabel, "8월 13일 06:17")
        XCTAssertFalse(snapshot.isStale(now: try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-08-13T20:00:00Z"))))
        XCTAssertTrue(snapshot.isStale(now: try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-08-14T10:00:00Z"))))
    }

    func testProductionClientDefaultsToPagesSnapshot() {
        XCTAssertEqual(
            MarketAPIClient.productionSnapshotURL.absoluteString,
            "https://serendip811.github.io/gojump/api/v1/markets/seoul/snapshot.json"
        )
    }

    func testIndicatorDecodesRawHistory() throws {
        let json = #"{"id":"pir","title":"서울 주택구입부담","shortTitle":"구입부담","score":89,"trend":"up","value":"179.3","change":"1년 +23.6p","symbol":"house.fill","explanation":"설명","insight":"해석","source":"HOUSTAT","observedAt":"2026년 1분기","history":[78,83,90],"rawHistory":[155.2,165.1,179.3],"historyLabels":["2025 3Q","2025 4Q","2026 1Q"],"historyUnit":"K-HAI"}"#
        let indicator = try JSONDecoder().decode(MarketIndicator.self, from: Data(json.utf8))
        XCTAssertEqual(indicator.rawHistory, [155.2, 165.1, 179.3])
        XCTAssertEqual(indicator.historyLabels?.last, "2026 1Q")
        XCTAssertEqual(indicator.historyUnit, "K-HAI")
    }

    func testSampleContainsFiveYearsOfMonthlyVolume() {
        let volume = MarketSnapshot.sample.indicators.first { $0.id == "volume" }
        XCTAssertEqual(volume?.rawHistory?.count, 60)
        XCTAssertEqual(volume?.historyLabels?.first, "2021 8월")
        XCTAssertEqual(volume?.historyLabels?.last, "2026 7월")
        XCTAssertEqual(volume?.rawHistory?.max(), 11_270)
    }

    func testSampleSeparatesSubscriptionAndUnsoldHistory() {
        let subscription = MarketSnapshot.sample.indicators.first { $0.id == "subscription" }
        XCTAssertEqual(subscription?.rawHistory?.count, 77)
        XCTAssertEqual(subscription?.historyLabels?.first, "2020 2월")
        XCTAssertEqual(subscription?.historyLabels?.last, "2026 6월")
        XCTAssertEqual(subscription?.secondaryRawHistory?.count, 119)
        XCTAssertEqual(subscription?.secondaryHistoryLabels?.first, "2016 8월")
        XCTAssertEqual(subscription?.secondaryHistoryLabels?.last, "2026 6월")
        XCTAssertEqual(subscription?.secondaryRawHistory?.max(), 2_099)
    }

    func testSampleContainsTenYearsOfRateHistory() {
        let rate = MarketSnapshot.sample.indicators.first { $0.id == "rate" }
        XCTAssertEqual(rate?.rawHistory?.count, 119)
        XCTAssertEqual(rate?.secondaryRawHistory?.count, 119)
        XCTAssertEqual(rate?.historyLabels?.first, "2016 8월")
        XCTAssertEqual(rate?.historyLabels?.last, "2026 6월")
        XCTAssertEqual(rate?.rawHistory?.last, 4.36)
        XCTAssertEqual(rate?.secondaryRawHistory?.last, 2.50)
    }

    func testSampleContainsTwoYearSupplyForecast() {
        let supply = MarketSnapshot.sample.indicators.first { $0.id == "supply" }
        XCTAssertEqual(supply?.rawHistory?.count, 39)
        XCTAssertEqual(supply?.historyLabels?.first, "1990")
        XCTAssertEqual(supply?.historyLabels?.last, "2028")
        XCTAssertEqual(supply?.historyForecastStartLabel, "2026")
    }

    func testExpansionSignalIsSmallPositiveBonus() {
        let expansion = MarketSnapshot.sample.indicators.first { $0.id == "unpopular" }!
        let signal = ScoreCalculator.expansionSignal(for: expansion)
        XCTAssertEqual(signal.stage, "확산 중")
        XCTAssertEqual(signal.score, 65)
        XCTAssertEqual(signal.bonus, 0.75, accuracy: 0.001)
    }

    func testSampleUsesCalculatedCompositeHistory() {
        XCTAssertEqual(MarketSnapshot.sample.history.count, 68)
        XCTAssertEqual(Array(MarketSnapshot.sample.history.suffix(12)), [56, 58, 50, 50, 49, 54, 56, 62, 56, 57, 67, 64])
        XCTAssertEqual(MarketSnapshot.sample.historyLabels?.first, "2020 12월")
        XCTAssertEqual(MarketSnapshot.sample.historyLabels?.last, "2026 7월")
        XCTAssertEqual(MarketSnapshot.sample.priceHistory?.count, 68)
        XCTAssertEqual(MarketSnapshot.sample.priceHistory?.last, 106.913)
        XCTAssertEqual(MarketSnapshot.sample.priceHistoryLabels, MarketSnapshot.sample.historyLabels)
    }
}
