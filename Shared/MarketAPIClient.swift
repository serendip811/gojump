import Foundation

struct MarketAPIClient: Sendable {
    static let productionSnapshotURL = URL(
        string: "https://serendip811.github.io/gojump/api/v1/markets/seoul/snapshot.json"
    )!

    let snapshotURL: URL

    init(snapshotURL: URL? = nil) {
        if let snapshotURL {
            self.snapshotURL = snapshotURL
        } else if let configured = Bundle.main.object(
            forInfoDictionaryKey: "GOJUMP_SNAPSHOT_URL"
        ) as? String, let url = URL(string: configured) {
            self.snapshotURL = url
        } else {
            self.snapshotURL = Self.productionSnapshotURL
        }
    }

    func fetchSnapshot() async throws -> MarketSnapshot {
        var request = URLRequest(url: snapshotURL)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadRevalidatingCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(MarketSnapshot.self, from: data)
    }
}
