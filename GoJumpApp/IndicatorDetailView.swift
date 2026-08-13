import Charts
import SwiftUI

struct IndicatorDetailView: View {
    let indicator: MarketIndicator
    @State private var historyRange: HistoryRange
    @State private var selectedHistoryIndex: Int?

    init(indicator: MarketIndicator) {
        self.indicator = indicator
        _historyRange = State(initialValue: indicator.id == "supply" ? .fiveYears : .twoYears)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .firstTextBaseline) {
                    Text("\(indicator.score)")
                        .font(.system(size: 64, weight: .bold, design: .rounded))
                    Text(indicator.id == "unpopular" ? "/ 100 · 확산도 Beta" : "/ 100 · \(indicator.level.title)")
                        .font(.headline)
                        .foregroundStyle(indicator.id == "unpopular" ? AppTheme.secondary : indicator.level.color)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(indicator.value).font(.title2.bold())
                    Text(indicator.change).font(.subheadline).foregroundStyle(AppTheme.secondary)
                }
                historyChart
                InfoSection(title: "현재 해석", text: indicator.insight, highlighted: true)
                InfoSection(title: "왜 이 지표를 보나요?", text: indicator.explanation)
                VStack(alignment: .leading, spacing: 8) {
                    Text("데이터").font(.headline)
                    Label(indicator.source, systemImage: "building.columns")
                    Label(indicator.observedAt, systemImage: "calendar")
                }
                .font(.subheadline)
                .foregroundStyle(AppTheme.secondary)
            }
            .padding(20)
        }
        .background(AppTheme.background)
        .navigationTitle(indicator.title)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private var historyChart: some View {
        if let rawHistory = indicator.rawHistory, !rawHistory.isEmpty {
            let points = historyPoints(values: rawHistory)
            let secondaryPoints = secondaryHistoryPoints()
            let selection = historySelection(points: points, secondaryPoints: secondaryPoints)
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(chartTitle)
                        .font(.subheadline.bold())
                    Spacer()
                    Text(points.first.map { "\($0.label)–\(points.last?.label ?? $0.label)" } ?? "")
                        .font(.caption)
                        .foregroundStyle(AppTheme.secondary)
                }
                if indicator.id == "rate" {
                    HStack(spacing: 18) {
                        chartLegend(title: "주택담보대출", color: indicator.level.color, dashed: false)
                        chartLegend(title: "기준금리", color: AppTheme.rateBenchmark, dashed: true)
                    }
                }
                if indicator.id == "supply" {
                    HStack(spacing: 18) {
                        chartLegend(title: "입주 실적", color: AppTheme.secondary.opacity(0.45), dashed: false)
                        chartLegend(title: "입주 예정", color: indicator.level.color, dashed: false)
                    }
                }
                Picker("조회 기간", selection: $historyRange) {
                    ForEach(availableRanges) { range in
                        Text(range.title).tag(range)
                    }
                }
                .pickerStyle(.segmented)
                .onChange(of: historyRange) { _, _ in selectedHistoryIndex = nil }
                Chart {
                    if let reference = indicator.historyReferenceValue {
                        RuleMark(y: .value("기준", reference))
                            .foregroundStyle(AppTheme.secondary.opacity(0.55))
                            .lineStyle(.init(lineWidth: 1, dash: [5, 4]))
                            .annotation(position: .top, alignment: .leading) {
                                Text(indicator.historyReferenceLabel ?? "기준 \(formatted(reference))")
                                    .font(.caption2)
                                    .foregroundStyle(AppTheme.secondary)
                            }
                    }
                    if indicator.id == "supply" {
                        ForEach(points) { point in
                            BarMark(
                                x: .value("연도", point.index),
                                y: .value("입주예정", point.value),
                                width: .fixed(supplyBarWidth(for: points.count))
                            )
                            .foregroundStyle(
                                isForecastSupply(point)
                                    ? AnyShapeStyle(indicator.level.color.gradient)
                                    : AnyShapeStyle(AppTheme.secondary.opacity(0.35))
                            )
                            .cornerRadius(6)
                            .annotation(position: .overlay, alignment: .top) {
                                if points.count <= 10 {
                                    Text("\(Int(point.value).formatted())")
                                        .font(.caption2.bold())
                                        .foregroundStyle(isForecastSupply(point) ? Color.white : AppTheme.ink)
                                        .padding(.top, 4)
                                }
                            }
                        }
                    } else {
                        ForEach(points) { point in
                            LineMark(
                                x: .value("기간", point.index),
                                y: .value(indicator.historyUnit ?? "값", point.value),
                                series: .value("계열", "주택담보대출")
                            )
                                .foregroundStyle(indicator.level.color)
                                .lineStyle(.init(lineWidth: points.count > 20 ? 2.5 : 3, lineCap: .round, lineJoin: .round))
                            if points.count <= 20 {
                                PointMark(x: .value("기간", point.index), y: .value(indicator.historyUnit ?? "값", point.value))
                                    .foregroundStyle(indicator.level.color)
                            }
                        }
                    }
                    if indicator.id == "rate" {
                        ForEach(secondaryPoints) { point in
                            LineMark(
                                x: .value("기간", point.index),
                                y: .value("기준금리", point.value),
                                series: .value("계열", "기준금리")
                            )
                            .foregroundStyle(AppTheme.rateBenchmark)
                            .lineStyle(.init(lineWidth: 2, lineCap: .round, dash: [6, 4]))
                        }
                    }
                    if points.count > 20,
                       !["rate", "supply"].contains(indicator.id),
                       let peak = points.max(by: { $0.value < $1.value }) {
                        PointMark(x: .value("기간", peak.index), y: .value(indicator.historyUnit ?? "값", peak.value))
                            .foregroundStyle(indicator.level.color)
                            .annotation(position: .top) {
                                Text("최고 \(formatted(peak.value))")
                                    .font(.caption2.bold())
                                    .foregroundStyle(indicator.level.color)
                            }
                    }
                    if indicator.id != "supply", let latest = points.last {
                        PointMark(x: .value("기간", latest.index), y: .value(indicator.historyUnit ?? "값", latest.value))
                            .foregroundStyle(indicator.level.color)
                            .annotation(position: .top, alignment: .trailing) {
                                Text(formatted(latest.value))
                                    .font(.caption.bold())
                                    .foregroundStyle(indicator.level.color)
                            }
                    }
                    InteractiveSelectionMarks(selection: selection)
                }
                .chartXAxis(.hidden)
                .id(historyRange)
                .chartXScale(range: .plotDimension(startPadding: 8, endPadding: 28))
                .chartYScale(domain: yDomain(for: points))
                .chartXSelection(value: $selectedHistoryIndex)
                .interactiveChartTooltip(selection)
                .chartYAxis {
                    AxisMarks(position: .trailing, values: .automatic(desiredCount: 4))
                }
                .frame(height: 190)
                HStack(alignment: .top, spacing: 0) {
                    let indexes = axisIndexes(for: points.count)
                    ForEach(Array(indexes.enumerated()), id: \.element) { position, index in
                        let parts = points[index].label.split(separator: " ")
                        Text(parts.joined(separator: "\n"))
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondary)
                            .multilineTextAlignment(.center)
                            .frame(width: 54)
                        if position < indexes.count - 1 {
                            Spacer(minLength: 0)
                        }
                    }
                }
                .padding(.horizontal, 4)
            }
        } else {
            let points = fallbackHistoryPoints
            let selection = fallbackHistorySelection(points: points)
            VStack(alignment: .leading, spacing: 10) {
                Text("위험점수 추이")
                    .font(.subheadline.bold())
                Chart {
                    ForEach(points) { point in
                        LineMark(x: .value("기간", point.index), y: .value("위험", point.value))
                            .foregroundStyle(indicator.level.color)
                            .lineStyle(.init(lineWidth: 3, lineCap: .round))
                        PointMark(x: .value("기간", point.index), y: .value("위험", point.value))
                            .foregroundStyle(indicator.level.color)
                    }
                    InteractiveSelectionMarks(selection: selection)
                }
                .chartYScale(domain: 0...100)
                .chartXSelection(value: $selectedHistoryIndex)
                .interactiveChartTooltip(selection)
                .chartXAxis(.hidden)
                .frame(height: 190)
            }
        }
    }

    private func historyPoints(values: [Double]) -> [HistoryPoint] {
        let labels = indicator.historyLabels ?? values.indices.map { "\($0 + 1)분기" }
        let count = min(values.count, labels.count)
        let start = max(0, count - historyRange.observationCount(for: indicator.id))
        return (start..<count).enumerated().map { localIndex, sourceIndex in
            HistoryPoint(index: localIndex, value: values[sourceIndex], label: labels[sourceIndex])
        }
    }

    private func secondaryHistoryPoints() -> [HistoryPoint] {
        guard let values = indicator.secondaryRawHistory else { return [] }
        let labels = indicator.secondaryHistoryLabels ?? values.indices.map { "\($0 + 1)월" }
        let count = min(values.count, labels.count)
        let start = max(0, count - historyRange.observationCount(for: indicator.id))
        return (start..<count).enumerated().map { localIndex, sourceIndex in
            HistoryPoint(index: localIndex, value: values[sourceIndex], label: labels[sourceIndex])
        }
    }

    private var fallbackHistoryPoints: [HistoryPoint] {
        let labels = indicator.historyLabels ?? indicator.history.indices.map { "\($0 + 1)" }
        let count = min(indicator.history.count, labels.count)
        return (0..<count).map {
            HistoryPoint(index: $0, value: Double(indicator.history[$0]), label: labels[$0])
        }
    }

    private func historySelection(
        points: [HistoryPoint], secondaryPoints: [HistoryPoint]
    ) -> InteractiveChartSelection? {
        guard let selectedHistoryIndex,
              let primary = points.first(where: { $0.index == selectedHistoryIndex }) else { return nil }
        var values = [InteractiveChartValue(
            title: primarySeriesTitle,
            displayValue: formatted(primary.value),
            plotValue: primary.value,
            color: indicator.id == "supply" && !isForecastSupply(primary)
                ? AppTheme.secondary : indicator.level.color
        )]
        if indicator.id == "rate",
           let secondary = secondaryPoints.first(where: { $0.index == selectedHistoryIndex }) {
            values.append(InteractiveChartValue(
                title: "기준금리", displayValue: formatted(secondary.value),
                plotValue: secondary.value, color: AppTheme.rateBenchmark
            ))
        }
        return InteractiveChartSelection(index: primary.index, label: primary.label, values: values)
    }

    private func fallbackHistorySelection(points: [HistoryPoint]) -> InteractiveChartSelection? {
        guard let selectedHistoryIndex,
              let point = points.first(where: { $0.index == selectedHistoryIndex }) else { return nil }
        return InteractiveChartSelection(
            index: point.index,
            label: point.label,
            values: [InteractiveChartValue(
                title: "점수", displayValue: "\(Int(point.value))",
                plotValue: point.value, color: indicator.level.color
            )]
        )
    }

    private var primarySeriesTitle: String {
        switch indicator.id {
        case "pir": "K-HAI"
        case "volume": "거래"
        case "unpopular": "확산"
        case "subscription": "경쟁률"
        case "rate": "주담대"
        case "supply": "입주"
        default: "값"
        }
    }

    private func axisIndexes(for count: Int) -> [Int] {
        guard count > 1 else { return [0] }
        if indicator.id == "supply", count <= 6 { return Array(0..<count) }
        let divisions = min(3, count - 1)
        return Array(Set((0...divisions).map {
            Int((Double($0) * Double(count - 1) / Double(divisions)).rounded())
        })).sorted()
    }

    private func isForecastSupply(_ point: HistoryPoint) -> Bool {
        guard let start = indicator.historyForecastStartLabel else { return false }
        return point.label >= start
    }

    private func supplyBarWidth(for count: Int) -> CGFloat {
        if count > 25 { return 7 }
        if count > 10 { return 11 }
        return 20
    }

    private func yDomain(for points: [HistoryPoint]) -> ClosedRange<Double> {
        if indicator.id == "pir" {
            let maximum = indicator.rawHistory?.max() ?? 0
            let ceiling = max(250, ceil(maximum / 50) * 50)
            return 0...ceiling
        }
        if indicator.id == "volume" {
            let maximum = indicator.rawHistory?.max() ?? 0
            let ceiling = max(15_000, ceil(maximum / 5_000) * 5_000)
            return 0...ceiling
        }
        if indicator.id == "subscription" {
            let maximum = points.map(\.value).max() ?? 0
            let step = maximum > 200 ? 100.0 : 50.0
            let ceiling = max(step, ceil(maximum / step) * step)
            return 0...ceiling
        }
        if indicator.id == "supply" {
            return 0...100_000
        }
        if indicator.id == "rate" {
            let maximum = max(
                indicator.rawHistory?.max() ?? 0,
                indicator.secondaryRawHistory?.max() ?? 0
            )
            return 0...max(8, ceil(maximum))
        }
        let values = points.map(\.value) + [indicator.historyReferenceValue].compactMap { $0 }
        let minimum = values.min() ?? 0
        let maximum = values.max() ?? 100
        let padding = max(8, (maximum - minimum) * 0.10)
        return max(0, minimum - padding)...(maximum + padding)
    }

    private var availableRanges: [HistoryRange] {
        switch indicator.id {
        case "volume": [.twoYears, .fiveYears]
        case "subscription": [.twoYears, .fiveYears, .all]
        case "rate": [.twoYears, .fiveYears, .tenYears]
        case "supply": [.fiveYears, .tenYears, .all]
        default: [.twoYears, .fiveYears, .all]
        }
    }

    private var chartTitle: String {
        switch indicator.id {
        case "volume": "월 거래량 추이"
        case "subscription": "3개월 가중 청약 경쟁률"
        case "rate": "주택담보대출 금리"
        case "supply": "연도별 입주예정물량"
        case "unpopular": "비인기 거래 확산지수"
        default: "\(indicator.historyUnit ?? "원지수") 추이"
        }
    }

    private func formatted(_ value: Double) -> String {
        if ["건", "호"].contains(indicator.historyUnit) {
            return Int(value.rounded()).formatted()
        }
        if indicator.historyUnit == "%" {
            return value.formatted(.number.precision(.fractionLength(2))) + "%"
        }
        return value.formatted(.number.precision(.fractionLength(1)))
    }

    private func chartLegend(title: String, color: Color, dashed: Bool) -> some View {
        HStack(spacing: 6) {
            if dashed {
                HStack(spacing: 3) {
                    ForEach(0..<3, id: \.self) { _ in
                        Capsule().fill(color).frame(width: 5, height: 2)
                    }
                }
                .frame(width: 21)
            } else {
                Capsule().fill(color).frame(width: 21, height: 3)
            }
            Text(title)
                .font(.caption)
                .foregroundStyle(AppTheme.secondary)
        }
    }

}

private enum HistoryRange: String, CaseIterable, Identifiable {
    case twoYears
    case fiveYears
    case tenYears
    case all

    var id: Self { self }

    var title: String {
        return switch self {
        case .twoYears: "2년"
        case .fiveYears: "5년"
        case .tenYears: "10년"
        case .all: "전체"
        }
    }

    func observationCount(for indicatorID: String) -> Int {
        if indicatorID == "supply" {
            switch self {
            case .twoYears: return 2
            case .fiveYears: return 5
            case .tenYears: return 10
            case .all: return .max
            }
        }
        return switch self {
        case .twoYears: indicatorID == "pir" ? 8 : 24
        case .fiveYears: indicatorID == "pir" ? 20 : 60
        case .tenYears: 120
        case .all: .max
        }
    }
}

private struct HistoryPoint: Identifiable {
    let index: Int
    let value: Double
    let label: String

    var id: Int { index }
}

private struct InfoSection: View {
    let title: String
    let text: String
    var highlighted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            Text(text).font(.body).foregroundStyle(AppTheme.secondary).lineSpacing(5)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(highlighted ? AppTheme.paleAccent.opacity(0.5) : AppTheme.card, in: RoundedRectangle(cornerRadius: 22))
    }
}
