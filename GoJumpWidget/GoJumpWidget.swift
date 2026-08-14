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
            HStack(alignment: .lastTextBaseline, spacing: 5) {
                Text("\(entry.snapshot.score)")
                    .font(.system(size: 48, weight: .bold, design: .rounded))
                Text(entry.snapshot.level.title)
                    .font(.subheadline.bold())
                    .foregroundStyle(levelColor)
            }
            if let strongest = entry.snapshot.strongestIndicator {
                Label("\(strongest.shortTitle) \(strongest.score)", systemImage: strongest.symbol)
                    .font(.caption2.weight(.semibold))
                    .lineLimit(1)
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
                Text("서울 · 고점 신호").font(.caption.bold())
                Text("\(entry.snapshot.score)").font(.system(size: 50, weight: .bold, design: .rounded))
                Text(entry.snapshot.level.title)
                    .font(.headline)
                    .foregroundStyle(levelColor)
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
        Gauge(value: Double(entry.snapshot.score), in: 0...100) {
            Text("서울")
        } currentValueLabel: {
            Text("\(entry.snapshot.score)").font(.headline)
        }
        .gaugeStyle(.accessoryCircularCapacity)
        .widgetAccentable()
    }

    private var accessoryRectangular: some View {
        HStack(spacing: 8) {
            Text("\(entry.snapshot.score)")
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .widgetAccentable()
            VStack(alignment: .leading, spacing: 2) {
                Text("서울 · \(entry.snapshot.level.title)").font(.headline)
                if let strongest = entry.snapshot.strongestIndicator {
                    Text("\(strongest.shortTitle) \(strongest.score)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var accessoryInline: some View {
        Text("서울 \(entry.snapshot.score) · \(entry.snapshot.level.title)")
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

    private var levelColor: Color {
        switch entry.snapshot.level {
        case .stable: Color(red: 0.18, green: 0.49, blue: 0.42)
        case .watch: Color(red: 0.55, green: 0.50, blue: 0.28)
        case .caution: Color(red: 0.79, green: 0.54, blue: 0.14)
        case .alert: Color(red: 0.78, green: 0.27, blue: 0.08)
        case .highRisk: Color(red: 0.64, green: 0.12, blue: 0.10)
        }
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
        .description("서울 주택 시장의 여섯 가지 신호를 확인하세요.")
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
