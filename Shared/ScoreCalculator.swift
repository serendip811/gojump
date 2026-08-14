import Foundation

enum ScoreCalculator {
    static let priceBurdenWeights: [String: Double] = ["pir": 0.75, "rate": 0.25]
    static let transitionWeights: [String: Double] = ["volume": 0.55, "subscription": 0.45]

    static let weights: [String: Double] = [
        "pir": 0.25,
        "volume": 0.20,
        "subscription": 0.15,
        "rate": 0.15,
        "supply": 0.15
    ]

    static func score(for indicators: [MarketIndicator]) -> Int? {
        let valid = indicators.compactMap { indicator -> (Int, Double)? in
            guard let weight = weights[indicator.id] else { return nil }
            return (indicator.score, weight)
        }
        let totalWeight = valid.reduce(0) { $0 + $1.1 }
        guard totalWeight > 0 else { return nil }
        let weighted = valid.reduce(0) { $0 + Double($1.0) * $1.1 }
        let baseScore = Int((weighted / totalWeight).rounded())
        let bonus = indicators.first(where: { $0.id == "unpopular" }).map {
            expansionSignal(for: $0).bonus
        } ?? 0
        return min(100, Int((Double(baseScore) + bonus).rounded()))
    }

    static func weightedScore(for indicators: [MarketIndicator], weights: [String: Double]) -> Int? {
        let valid = indicators.compactMap { indicator -> (score: Int, weight: Double)? in
            guard let weight = weights[indicator.id] else { return nil }
            return (indicator.score, weight)
        }
        let totalWeight = valid.reduce(0) { $0 + $1.weight }
        guard totalWeight > 0 else { return nil }
        return Int((valid.reduce(0) { $0 + Double($1.score) * $1.weight } / totalWeight).rounded())
    }

    static func priceBurdenScore(for indicators: [MarketIndicator]) -> Int? {
        weightedScore(for: indicators, weights: priceBurdenWeights)
    }

    static func transitionScore(for indicators: [MarketIndicator]) -> Int? {
        weightedScore(for: indicators, weights: transitionWeights)
    }

    static func expansionSignal(for indicator: MarketIndicator) -> (score: Int, bonus: Double, stage: String) {
        let history = indicator.rawHistory ?? indicator.history.map(Double.init)
        guard let raw = history.last else { return (50, 0, "관찰 중") }
        let trailing = Array(history.suffix(6))
        let decline = (trailing.max() ?? raw) - raw
        let level = max(0, min(100, 50 + (raw - 50) * 2))
        let rollover = max(0, min(100, 50 + decline * 8))
        let phaseScore = Int((level * 0.60 + rollover * 0.40).rounded())
        let bonus = max(0, Double(phaseScore - 50)) * 0.05
        let stage: String
        if decline >= 3, (trailing.max() ?? raw) >= 55 {
            stage = "확산 둔화"
        } else if raw >= 60 {
            stage = "과열 확산"
        } else if raw >= 50 {
            stage = "확산 중"
        } else {
            stage = "제한적 확산"
        }
        return (phaseScore, bonus, stage)
    }
}
