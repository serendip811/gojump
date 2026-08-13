import Combine
import Foundation
import WidgetKit

enum MarketLoadState: Equatable {
    case idle, loading, loaded, failed(String)
}

@MainActor
final class MarketStore: ObservableObject {
    @Published private(set) var snapshot: MarketSnapshot
    @Published private(set) var state: MarketLoadState = .idle
    private let client: MarketAPIClient

    init(client: MarketAPIClient = MarketAPIClient()) {
        self.client = client
        self.snapshot = SnapshotCache.load() ?? .sample
        WidgetCenter.shared.reloadAllTimelines()
    }

    func refresh() async {
        guard state != .loading else { return }
        state = .loading
        do {
            let fresh = try await client.fetchSnapshot()
            snapshot = fresh
            try SnapshotCache.save(fresh)
            WidgetCenter.shared.reloadAllTimelines()
            state = .loaded
        } catch {
            state = .failed(error.localizedDescription)
            WidgetCenter.shared.reloadAllTimelines()
        }
    }
}
