import Foundation

enum SnapshotCache {
    private static let key = "latestMarketSnapshot"
    private static let suiteName = "group.kr.gojump.shared"

    private static var defaults: UserDefaults {
        UserDefaults(suiteName: suiteName) ?? .standard
    }

    static func load() -> MarketSnapshot? {
        guard let data = defaults.data(forKey: key) else { return nil }
        guard let snapshot = try? JSONDecoder().decode(MarketSnapshot.self, from: data) else {
            return nil
        }
        let affordability = snapshot.indicators.first { $0.id == "pir" }
        let volume = snapshot.indicators.first { $0.id == "volume" }
        let subscription = snapshot.indicators.first { $0.id == "subscription" }
        let rate = snapshot.indicators.first { $0.id == "rate" }
        let supply = snapshot.indicators.first { $0.id == "supply" }
        guard affordability?.rawHistory?.isEmpty == false,
              affordability?.historyLabels?.count == affordability?.rawHistory?.count,
              (volume?.rawHistory?.count ?? 0) >= 60,
              volume?.historyLabels?.count == volume?.rawHistory?.count,
              (subscription?.rawHistory?.count ?? 0) >= 70,
              subscription?.historyLabels?.count == subscription?.rawHistory?.count,
              (subscription?.secondaryRawHistory?.count ?? 0) >= 24,
              subscription?.secondaryHistoryLabels?.count == subscription?.secondaryRawHistory?.count,
              (rate?.rawHistory?.count ?? 0) >= 119,
              rate?.historyLabels?.count == rate?.rawHistory?.count,
              rate?.secondaryRawHistory?.count == rate?.rawHistory?.count,
              (supply?.rawHistory?.count ?? 0) >= 39,
              supply?.historyLabels?.count == supply?.rawHistory?.count else {
            return nil
        }
        return snapshot
    }

    static func save(_ snapshot: MarketSnapshot) throws {
        let data = try JSONEncoder().encode(snapshot)
        defaults.set(data, forKey: key)
    }
}
