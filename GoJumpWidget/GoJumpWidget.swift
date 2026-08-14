import SwiftUI
@preconcurrency import WidgetKit

struct GoJumpEntry: TimelineEntry {
    let date: Date
    let snapshot: MarketSnapshot
}

struct GoJumpProvider: TimelineProvider {
    private final class CompletionBox: @unchecked Sendable {
        let call: (Timeline<GoJumpEntry>) -> Void

        init(_ call: @escaping (Timeline<GoJumpEntry>) -> Void) {
            self.call = call
        }
    }

    private let client = MarketAPIClient()

    func placeholder(in context: Context) -> GoJumpEntry { .init(date: .now, snapshot: .sample) }
    func getSnapshot(in context: Context, completion: @escaping (GoJumpEntry) -> Void) {
        completion(.init(date: .now, snapshot: SnapshotCache.load() ?? .sample))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<GoJumpEntry>) -> Void) {
        let completionBox = CompletionBox(completion)
        Task {
            let snapshot: MarketSnapshot
            do {
                let fresh = try await client.fetchSnapshot()
                try SnapshotCache.save(fresh)
                snapshot = fresh
            } catch {
                snapshot = SnapshotCache.load() ?? .sample
            }
            let entry = GoJumpEntry(date: .now, snapshot: snapshot)
            completionBox.call(
                Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(6 * 60 * 60)))
            )
        }
    }
}

struct GoJumpWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: GoJumpEntry

    var body: some View {
        switch family {
        case .systemSmall: small
        case .systemMedium: medium
        case .accessoryCircular: accessoryCircular
        case .accessoryRectangular: accessoryRectangular
        case .accessoryInline: accessoryInline
        default: small
        }
    }

    private var small: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("아파트고점지수").font(.caption2.bold())
                Spacer()
                Text(entry.snapshot.market).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            Text(entry.snapshot.effectiveVerdict.title)
                .font(.subheadline.bold())
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            HStack(spacing: 14) {
                widgetScore("부담", entry.snapshot.effectivePriceBurdenScore)
                widgetScore("전환", entry.snapshot.effectiveTransitionScore)
            }
            HStack {
                Text(widgetUpdateLabel)
                Spacer()
                if isSample { Text("샘플") }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
    }

    private var medium: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("서울 · 현재 판단").font(.caption.bold())
                Text(entry.snapshot.effectiveVerdict.title)
                    .font(.headline)
                    .lineLimit(2)
                HStack(spacing: 12) {
                    widgetScore("부담", entry.snapshot.effectivePriceBurdenScore)
                    widgetScore("전환", entry.snapshot.effectiveTransitionScore)
                }
                Spacer()
                Text("\(widgetUpdateLabel)\(isSample ? " · 샘플" : "")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 92, alignment: .leading)
            Divider()
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 9) {
                ForEach(entry.snapshot.indicators.prefix(6)) { indicator in
                    HStack {
                        Text(indicator.shortTitle)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text(indicator.id == "unpopular" ? indicator.value : "\(indicator.score)")
                            .font(.caption.bold())
                    }
                }
            }
        }
    }

    private var accessoryCircular: some View {
        Gauge(value: Double(entry.snapshot.effectiveTransitionScore), in: 0...100) {
            Text("전환")
        } currentValueLabel: {
            Text("\(entry.snapshot.effectiveTransitionScore)").font(.headline)
        }
        .gaugeStyle(.accessoryCircularCapacity)
        .widgetAccentable()
    }

    private var accessoryRectangular: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("서울 · \(entry.snapshot.effectiveVerdict.title)").font(.headline)
            Text("가격 부담 \(entry.snapshot.effectivePriceBurdenScore) · 고점 전환 \(entry.snapshot.effectiveTransitionScore)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var accessoryInline: some View {
        Text("서울 부담 \(entry.snapshot.effectivePriceBurdenScore) · 전환 \(entry.snapshot.effectiveTransitionScore)")
    }

    private func widgetScore(_ title: String, _ score: Int) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(.caption2).foregroundStyle(.secondary)
            Text("\(score)").font(.title2.bold()).monospacedDigit()
        }
    }

    private var isSample: Bool {
        entry.snapshot.dataMode == "sample" || entry.snapshot.dataMode == "fixture"
    }

    private var widgetUpdateLabel: String {
        if let generated = entry.snapshot.generatedAtLabel {
            if entry.snapshot.isStale() { return "지연 · \(generated)" }
            if entry.snapshot.usesPreviousIndicatorValues { return "이전값 포함 · \(generated)" }
            return generated
        }
        return "\(entry.snapshot.asOf) 기준"
    }

}

struct GoJumpMarketWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "GoJumpMarket", provider: GoJumpProvider()) { entry in
            GoJumpWidgetView(entry: entry)
                .containerBackground(Color(red: 0.965, green: 0.957, blue: 0.937), for: .widget)
                .widgetURL(URL(string: "gojump://market"))
        }
        .configurationDisplayName("아파트고점지수")
        .description("서울의 가격 부담도와 고점 전환 신호를 확인하세요.")
        .supportedFamilies([
            .systemSmall, .systemMedium,
            .accessoryCircular, .accessoryRectangular, .accessoryInline,
        ])
    }
}

@main
struct GoJumpWidgetBundle: WidgetBundle {
    var body: some Widget {
        GoJumpMarketWidget()
    }
}
