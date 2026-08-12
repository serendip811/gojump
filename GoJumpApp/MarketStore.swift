import Combine
import Foundation
import WidgetKit

enum MarketLoadState: Equatable {
    case idle, loading, loaded, failed(String)
}

struct MarketAPIClient: Sendable {
    let snapshotURL: URL

    init(snapshotURL: URL? = nil) {
        if let snapshotURL {
            self.snapshotURL = snapshotURL
        } else if let configured = Bundle.main.object(forInfoDictionaryKey: "GOJUMP_SNAPSHOT_URL") as? String,
                  let url = URL(string: configured) {
            self.snapshotURL = url
        } else {
            self.snapshotURL = URL(string: "http://127.0.0.1:8080/v1/markets/seoul/snapshot")!
        }
    }

    func fetchSnapshot() async throws -> MarketSnapshot {
        var request = URLRequest(url: snapshotURL)
        request.timeoutInterval = 12
        request.cachePolicy = .reloadRevalidatingCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(MarketSnapshot.self, from: data)
    }
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
