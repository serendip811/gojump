import Foundation

enum MarketLevel: String, Codable, CaseIterable, Sendable {
    case stable, watch, caution, alert, highRisk

    var title: String {
        switch self {
        case .stable: "안정"
        case .watch: "관찰"
        case .caution: "주의"
        case .alert: "경계"
        case .highRisk: "고점 위험"
        }
    }

    static func from(score: Int) -> Self {
        switch score {
        case ..<25: .stable
        case 25..<45: .watch
        case 45..<65: .caution
        case 65..<80: .alert
        default: .highRisk
        }
    }
}

enum IndicatorTrend: String, Codable, Sendable {
    case up, down, flat

    var symbol: String {
        switch self {
        case .up: "arrow.up.right"
        case .down: "arrow.down.right"
        case .flat: "arrow.right"
        }
    }
}

struct MarketIndicator: Identifiable, Codable, Hashable, Sendable {
    let id: String
    let title: String
    let shortTitle: String
    let score: Int
    let trend: IndicatorTrend
    let value: String
    let change: String
    let symbol: String
    let explanation: String
    let insight: String
    let source: String
    let observedAt: String
    let history: [Int]
    var rawHistory: [Double]? = nil
    var historyLabels: [String]? = nil
    var historyUnit: String? = nil
    var historyReferenceValue: Double? = nil
    var historyReferenceLabel: String? = nil
    var historyForecastStartLabel: String? = nil
    var secondaryTitle: String? = nil
    var secondaryValue: String? = nil
    var secondaryChange: String? = nil
    var secondaryInsight: String? = nil
    var secondaryRawHistory: [Double]? = nil
    var secondaryHistoryLabels: [String]? = nil
    var secondaryHistoryUnit: String? = nil
    var secondarySource: String? = nil
    var secondaryObservedAt: String? = nil

    var level: MarketLevel { .from(score: score) }
}

struct MarketSnapshot: Codable, Sendable {
    let market: String
    let score: Int
    let delta7d: Int
    let deltaLabel: String?
    let confidence: Double
    let asOf: String
    var generatedAt: String? = nil
    let summary: String
    let history: [Int]
    var historyLabels: [String]? = nil
    var priceHistory: [Double]? = nil
    var priceHistoryLabels: [String]? = nil
    var priceHistoryUnit: String? = nil
    let dataMode: String?
    let liveIndicatorCount: Int?
    var freshIndicatorCount: Int? = nil
    var freshIndicatorIds: [String]? = nil
    var dataWarnings: [String]? = nil
    let indicators: [MarketIndicator]

    var level: MarketLevel { .from(score: score) }
    var strongestIndicator: MarketIndicator? { indicators.max { $0.score < $1.score } }

    var usesPreviousIndicatorValues: Bool {
        guard dataMode == "live" || dataMode == "partialLive",
              let freshIndicatorCount else { return false }
        return freshIndicatorCount < indicators.count
    }

    var previousValueIndicatorTitles: [String] {
        guard usesPreviousIndicatorValues, let freshIndicatorIds else { return [] }
        let fresh = Set(freshIndicatorIds)
        return indicators
            .filter { !fresh.contains($0.id) }
            .map(\.shortTitle)
    }

    var generatedDate: Date? {
        guard let generatedAt else { return nil }
        let fractionalFormatter = ISO8601DateFormatter()
        fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractionalFormatter.date(from: generatedAt)
            ?? ISO8601DateFormatter().date(from: generatedAt)
    }

    func isStale(now: Date = .now, threshold: TimeInterval = 36 * 60 * 60) -> Bool {
        guard let generatedDate else { return dataMode == "live" || dataMode == "partialLive" }
        return now.timeIntervalSince(generatedDate) > threshold
    }

    var generatedAtLabel: String? {
        guard let generatedDate else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ko_KR")
        formatter.timeZone = TimeZone(identifier: "Asia/Seoul")
        formatter.dateFormat = "M월 d일 HH:mm"
        return formatter.string(from: generatedDate)
    }
}

extension MarketSnapshot {
    private static let sampleCompositeHistory: [Int] = [
        57, 52, 53, 55, 56, 56, 60, 71, 72, 70, 72, 79,
        85, 89, 90, 91, 88, 84, 86, 82, 87, 88, 88, 88,
        86, 79, 64, 59, 58, 56, 52, 44, 45, 44, 44, 47,
        49, 45, 45, 35, 40, 34, 36, 41, 40, 42, 47, 52,
        52, 54, 50, 47, 48, 50, 49, 56, 56, 58, 50, 50,
        49, 54, 56, 62, 56, 57, 67, 64,
    ]
    private static let sampleCompositeLabels: [String] = sampleCompositeHistory.indices.map { index in
        let absoluteMonth = 2020 * 12 + 11 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }
    private static let samplePriceHistory: [Double] = [
        81.857, 83.169, 84.499, 85.625, 86.44, 87.311, 88.76, 89.898,
        91.33, 92.876, 93.848, 94.842, 95.279, 95.501, 95.589, 95.641,
        95.746, 95.949, 96.077, 96.111, 95.971, 95.785, 95.145, 93.798,
        92.454, 90.52, 89.436, 88.389, 87.532, 86.767, 86.52, 86.323,
        86.274, 86.503, 86.703, 86.736, 86.644, 86.477, 86.373, 86.245,
        86.102, 86.075, 86.182, 86.664, 87.436, 88.199, 88.64, 88.893,
        89.107, 89.164, 89.22, 89.797, 90.681, 91.236, 92.539, 93.727,
        94.285, 95.055, 96.441, 98.096, 99.138, 100, 101.336, 102.784,
        103.817, 104.68, 105.798, 106.913,
    ]
    private static let sampleKHAIValues: [Double] = [
        116.3, 120.5, 108.5, 108.7, 106.6, 113.6, 111.5, 116.7,
        115.1, 126.9, 127.2, 145.9, 148.8, 154.9, 151.9, 160.6,
        151.4, 164.8, 162.0, 157.8, 141.0, 144.3, 149.8, 150.8,
        139.2, 134.7, 131.0, 131.0, 127.0, 123.0, 117.8, 119.4,
        110.8, 114.1, 104.8, 104.3, 94.8, 94.6, 90.4, 90.1,
        86.8, 89.9, 88.5, 91.9, 83.7, 91.5, 90.4, 93.7,
        95.2, 94.1, 96.8, 102.4, 103.6, 107.2, 110.3, 116.7,
        118.8, 122.7, 130.3, 133.3, 129.9, 124.6, 123.6, 126.6,
        132.2, 142.8, 144.5, 153.4, 166.2, 172.9, 182.0, 199.2,
        203.7, 204.0, 214.6, 198.6, 175.5, 165.2, 161.4, 156.0,
        151.0, 147.9, 150.9, 157.9, 155.7, 153.4, 155.2, 165.1,
        179.3,
    ]

    private static let sampleKHAILabels: [String] = sampleKHAIValues.indices.map { index in
        let year = 2004 + index / 4
        let quarter = index % 4 + 1
        return "\(year) \(quarter)Q"
    }

    private static let sampleVolumeValues: [Double] = [
        4_060, 2_690, 2_196, 1_360, 1_130, 1_100,
        816, 1_482, 1_734, 1_722, 1_064, 646,
        755, 607, 558, 733, 830, 1_411,
        2_462, 2_991, 3_202, 3_354, 3_853, 3_595,
        3_869, 3_371, 2_307, 1_832, 1_790, 2_583,
        2_604, 4_273, 4_464, 5_112, 7_626, 8_901,
        6_309, 3_071, 3_722, 3_359, 3_150, 3_345,
        6_363, 9_794, 5_227, 7_577, 11_270, 4_149,
        4_277, 8_665, 8_532, 3_390, 4_774, 5_373,
        5_796, 5_516, 8_646, 8_942, 5_254, 4_720,
    ]

    private static let sampleVolumeLabels: [String] = sampleVolumeValues.indices.map { index in
        let absoluteMonth = 2021 * 12 + 7 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }

    private static let sampleUnsoldValues: [Double] = [
        372, 327, 283, 268, 274, 205, 187, 200, 157, 119, 64, 41,
        39, 75, 56, 68, 45, 45, 48, 48, 47, 47, 47, 42,
        39, 29, 28, 28, 27, 27, 50, 770, 292, 178, 123, 190,
        205, 207, 191, 176, 151, 131, 112, 91, 78, 70, 61, 58,
        56, 54, 52, 52, 49, 49, 88, 82, 76, 71, 65, 59,
        55, 55, 55, 54, 54, 47, 47, 180, 360, 688, 719, 592,
        610, 719, 866, 865, 953, 996, 2_099, 1_084, 1_058, 1_144,
        1_181, 1_081, 976, 914, 908, 877, 958, 997, 1_018, 968,
        936, 974, 959, 953, 946, 969, 917, 931, 957, 1_352,
        1_002, 942, 943, 989, 1_021, 1_033, 1_106, 1_088, 1_056, 1_037,
        939, 914, 1_132, 1_028, 995, 985, 1_013,
    ]

    private static let sampleUnsoldLabels: [String] = sampleUnsoldValues.indices.map { index in
        let absoluteMonth = 2016 * 12 + 7 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }

    private static let sampleSubscriptionValues: [Double] = [
        146.8, 142.2, 110.8, 68.6, 64.4, 51.9, 64.9, 64.0, 120.1, 195.8,
        245.8, 248.4, 205.7, 163.5, 150.7, 44.2, 87.5, 74.7, 98.9, 231.3,
        313.9, 319.9, 192.5, 59.3, 43.4, 31.8, 29.4, 19.4, 25.2, 15.1,
        5.1, 3.4, 3.4, 5.6, 6.7, 6.7, 54.4, 55.8, 48.4, 51.1,
        80.1, 99.4, 74.7, 69.1, 42.9, 46.9, 42.8, 90.3, 83.8, 154.2,
        60.1, 190.6, 165.9, 177.3, 125.8, 156.7, 167.8, 106.8, 62.6, 48.8,
        56.1, 151.6, 21.3, 49.8, 87.0, 90.0, 352.2, 232.8, 255.8, 192.8,
        288.3, 144.0, 126.4, 128.8, 111.9, 91.0, 25.2,
    ]

    private static let sampleSubscriptionLabels: [String] = sampleSubscriptionValues.indices.map { index in
        let absoluteMonth = 2020 * 12 + 1 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }

    private static let sampleMortgageRateValues: [Double] = [
        2.70, 2.80, 2.89, 3.04, 3.13, 3.16, 3.19, 3.21, 3.21, 3.26, 3.22, 3.28,
        3.28, 3.24, 3.33, 3.39, 3.42, 3.47, 3.46, 3.45, 3.47, 3.49, 3.46, 3.44,
        3.36, 3.29, 3.31, 3.28, 3.19, 3.12, 3.08, 3.04, 2.98, 2.93, 2.74, 2.64,
        2.47, 2.51, 2.50, 2.45, 2.45, 2.51, 2.52, 2.48, 2.58, 2.52, 2.49, 2.45,
        2.39, 2.44, 2.47, 2.56, 2.59, 2.63, 2.66, 2.73, 2.73, 2.69, 2.74, 2.81,
        2.88, 3.01, 3.26, 3.51, 3.63, 3.85, 3.88, 3.84, 3.90, 3.90, 4.04, 4.16,
        4.35, 4.79, 4.82, 4.74, 4.63, 4.58, 4.56, 4.40, 4.24, 4.21, 4.26, 4.28,
        4.31, 4.35, 4.56, 4.48, 4.16, 3.99, 3.96, 3.94, 3.93, 3.91, 3.71, 3.50,
        3.51, 3.74, 4.05, 4.30, 4.25, 4.27, 4.23, 4.17, 3.98, 3.87, 3.93, 3.96,
        3.96, 3.96, 3.98, 4.17, 4.23, 4.29, 4.32, 4.34, 4.31, 4.32, 4.36,
    ]

    private static let sampleBaseRateValues: [Double] = [
        1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25, 1.25,
        1.25, 1.25, 1.25, 1.50, 1.50, 1.50, 1.50, 1.50, 1.50, 1.50, 1.50, 1.50,
        1.50, 1.50, 1.50, 1.75, 1.75, 1.75, 1.75, 1.75, 1.75, 1.75, 1.75, 1.50,
        1.50, 1.50, 1.25, 1.25, 1.25, 1.25, 1.25, 0.75, 0.75, 0.50, 0.50, 0.50,
        0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50,
        0.75, 0.75, 0.75, 1.00, 1.00, 1.25, 1.25, 1.25, 1.50, 1.75, 1.75, 2.25,
        2.50, 2.50, 3.00, 3.25, 3.25, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50,
        3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50, 3.50,
        3.50, 3.50, 3.50, 3.25, 3.00, 3.00, 3.00, 2.75, 2.75, 2.75, 2.50, 2.50,
        2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50, 2.50,
    ]

    private static let sampleRateLabels: [String] = sampleMortgageRateValues.indices.map { index in
        let absoluteMonth = 2016 * 12 + 7 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }

    private static let sampleLiquidityValues: [Double] = [
        61, 61, 59, 58, 58, 59, 59, 58, 59, 57, 57, 56,
        55, 55, 54, 55, 57, 57, 56, 53, 47, 47, 43, 37,
        42, 36, 34, 31, 36, 39, 43, 45, 47, 52, 52, 50,
        47, 47, 46, 50, 54, 57, 58, 62, 63, 61, 59, 56,
        55, 53, 51, 57, 58, 58, 56, 58, 57, 55, 56, 57,
        56, 56, 57, 58, 59, 58, 58, 57,
    ]
    private static let sampleLiquidityLabels: [String] = sampleLiquidityValues.indices.map { index in
        let absoluteMonth = 2020 * 12 + 11 + index
        return "\(absoluteMonth / 12) \(absoluteMonth % 12 + 1)월"
    }

    static let sample = MarketSnapshot(
        market: "서울",
        score: 64,
        delta7d: -2,
        deltaLabel: "장기 공급 반영",
        confidence: 0.86,
        asOf: "2026.08.10",
        summary: "거래량 감소와 금리 부담이\n경고 신호를 높이고 있어요.",
        history: sampleCompositeHistory,
        historyLabels: sampleCompositeLabels,
        priceHistory: samplePriceHistory,
        priceHistoryLabels: sampleCompositeLabels,
        priceHistoryUnit: "2026.01=100",
        dataMode: "sample",
        liveIndicatorCount: 0,
        indicators: [
            .init(id: "pir", title: "서울 주택구입부담", shortTitle: "구입부담", score: 89, trend: .up, value: "179.3", change: "1년 +23.6p", symbol: "house.fill", explanation: "K-HAI는 중위소득 가구가 표준대출로 중위가격 주택을 살 때의 원리금 상환 부담을 보여줘요. 100을 넘으면 부담이 큰 구간이에요.", insight: "서울 주택구입부담지수는 179.3이며 1년 전보다 +23.6p 변했어요.", source: "한국주택금융공사 HOUSTAT · 분기", observedAt: "2026년 1분기", history: [74, 75, 79, 78, 77, 78, 83, 89], rawHistory: sampleKHAIValues, historyLabels: sampleKHAILabels, historyUnit: "K-HAI", historyReferenceValue: 100, historyReferenceLabel: "부담 기준 100"),
            .init(id: "volume", title: "아파트 거래량", shortTitle: "거래량", score: 55, trend: .up, value: "4,720건", change: "전월 -10.2%", symbol: "chart.bar.fill", explanation: "최근 3개월 거래량을 직전 3개월, 전년 같은 기간, 과거 5년 같은 계절과 비교해 시장 유동성이 식는 정도를 봐요.", insight: "최근 3개월 거래량은 직전 3개월보다 -5.2%, 전년 같은 기간보다 -17.7% 변했어요. 과거 같은 계절과 비교하면 +16.6%예요.", source: "국토교통부 실거래가 · 잠정치", observedAt: "2026년 7월", history: [50, 47, 55, 62, 58, 63, 55, 55], rawHistory: sampleVolumeValues, historyLabels: sampleVolumeLabels, historyUnit: "건"),
            .init(id: "unpopular", title: "비인기 거래 확산도 Beta", shortTitle: "확산도 Beta", score: 57, trend: .flat, value: "57", change: "확산 중", symbol: "building.2.crop.circle", explanation: "거래가 드물던 단지·면적군까지 매수세가 넓어지는지 보는 실험 지표예요.", insight: "현재 단계는 ‘확산 중’이에요. 종합점수에는 최대 2.5점의 보조 신호로만 반영해요.", source: "국토교통부 실거래가 · 자체 분석 Beta", observedAt: "2026년 7월", history: sampleLiquidityValues.map(Int.init), rawHistory: sampleLiquidityValues, historyLabels: sampleLiquidityLabels, historyUnit: "확산지수"),
            .init(
                id: "subscription", title: "서울 청약 수요", shortTitle: "청약 수요",
                score: 76, trend: .up, value: "25.2 : 1", change: "전년 대비 -71.0%",
                symbol: "person.2.fill",
                explanation: "최근 3개월 일반공급 접수건수를 공급세대수로 나눈 값이에요. 경쟁률이 빠르게 낮아지면 새 아파트에 대한 미래 수요가 식는 신호일 수 있어요.",
                insight: "최근 3개월 공급 1,256세대의 가중 경쟁률은 25.2대 1이며 전년보다 71.0% 낮아졌어요.",
                source: "한국부동산원 청약홈 · 일반공급", observedAt: "2026년 6월",
                history: [40, 51, 25, 42, 76], rawHistory: sampleSubscriptionValues,
                historyLabels: sampleSubscriptionLabels, historyUnit: ": 1",
                secondaryTitle: "서울 미분양 주택", secondaryValue: "1,013호",
                secondaryChange: "3개월 -1.5%",
                secondaryInsight: "수요 냉각 이후 실제로 남은 주택은 1,013호예요. 미분양은 고점을 예측하기보다 시장 약화를 확인하는 보조 신호로 봐요.",
                secondaryRawHistory: sampleUnsoldValues, secondaryHistoryLabels: sampleUnsoldLabels,
                secondaryHistoryUnit: "호", secondarySource: "한국은행 ECOS · 국토교통부",
                secondaryObservedAt: "2026년 6월"
            ),
            .init(
                id: "rate", title: "주택 금융 금리", shortTitle: "금리", score: 81,
                trend: .up, value: "4.36%", change: "3개월 +0.02%p", symbol: "percent",
                explanation: "금리가 오르면 대출 원리금 부담이 늘고 주택 구매에 사용할 수 있는 자금이 줄어들어요.",
                insight: "2026년 6월 주택담보대출 금리는 4.36%, 당시 기준금리는 2.50%예요. 현재 기준금리는 2.75%예요.",
                source: "한국은행 ECOS · 신규취급액", observedAt: "2026년 6월",
                history: [72, 75, 78, 80, 77, 78, 79, 81],
                rawHistory: sampleMortgageRateValues, historyLabels: sampleRateLabels,
                historyUnit: "%", secondaryTitle: "한국은행 기준금리",
                secondaryRawHistory: sampleBaseRateValues,
                secondaryHistoryLabels: sampleRateLabels, secondaryHistoryUnit: "%"
            ),
            .init(id: "supply", title: "향후 입주 물량", shortTitle: "공급", score: 0, trend: .down, value: "3.6만호", change: "10년 평균 -52.6%", symbol: "building.2.fill", explanation: "서울 아파트의 과거 입주 실적과 향후 입주 예정물량을 같은 기준으로 비교해요.", insight: "향후 2년 합계 35,952호, 연평균 17,976호로 직전 10년 평균 37,925호보다 52.6% 적어요. 서울시 공식 2년 전망은 44,355호로 집계 범위에 따라 차이가 있어요.", source: "KB부동산 데이터허브·프롭티어 · 입주물량", observedAt: "2026~2027년", history: [41, 68, 90, 46, 30, 40, 20, 45], rawHistory: [18_395, 23_411, 41_502, 44_835, 33_368, 34_735, 38_648, 50_802, 54_495, 72_545, 67_830, 55_745, 58_019, 84_378, 70_358, 56_973, 47_742, 33_874, 55_416, 33_555, 34_552, 39_282, 27_215, 32_307, 45_966, 28_276, 32_848, 35_032, 43_216, 51_581, 53_263, 36_472, 30_187, 34_283, 26_476, 35_891, 18_273, 17_679, 9_523], historyLabels: (1990...2028).map(String.init), historyUnit: "호", historyReferenceValue: 37_924.9, historyReferenceLabel: "직전 10년 평균 3.8만호", historyForecastStartLabel: "2026")
        ]
    )
}
