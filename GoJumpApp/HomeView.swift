import Charts
import SwiftUI

struct HomeView: View {
    let snapshot: MarketSnapshot
    var loadState: MarketLoadState = .loaded
    @State private var compositeRange: CompositeHistoryRange = .oneYear
    @State private var selectedCompositeIndex: Int?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 0), count: 3)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header
                hero
                    .padding(.top, 38)
                strongestSignal
                    .padding(.top, 28)
                indicatorMatrix
                    .padding(.top, 34)
                historySection
                    .padding(.top, 36)
                disclaimer
                    .padding(.top, 24)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 36)
        }
        .background(AppTheme.background)
        .toolbar(.hidden, for: .navigationBar)
        .navigationDestination(for: MarketIndicator.self) {
            IndicatorDetailView(indicator: $0)
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 9) {
                Text("GO—JUMP")
                    .font(.caption.weight(.bold))
                    .tracking(2.2)
                    .foregroundStyle(AppTheme.accent)
                Text("서울")
                    .font(.system(size: 42, weight: .bold, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
            }
            Spacer(minLength: 12)
            VStack(alignment: .trailing, spacing: 7) {
                Label(dataStatus.title, systemImage: dataStatus.symbol)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(dataStatus.color)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 5)
                    .background(dataStatus.color.opacity(0.10), in: Capsule())
                Text("\(snapshot.asOf) 기준")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
            }
            .padding(.bottom, 6)
        }
        .padding(.top, 20)
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("고점 신호")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.secondary)
                Spacer()
                if case .loading = loadState {
                    ProgressView().controlSize(.small)
                }
                Label("신뢰도 \(Int(snapshot.confidence * 100))%", systemImage: "checkmark.seal.fill")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(AppTheme.secondary)
            }

            HStack(alignment: .bottom, spacing: 12) {
                HStack(alignment: .lastTextBaseline, spacing: 8) {
                    Text("\(snapshot.score)")
                        .font(.system(size: 88, weight: .bold, design: .rounded))
                        .tracking(-3)
                    Text("/ 100")
                        .font(.title3.weight(.medium))
                        .foregroundStyle(AppTheme.secondary)
                        .padding(.bottom, 11)
                }
                Spacer(minLength: 12)
                VStack(alignment: .trailing, spacing: 12) {
                    Text(snapshot.level.title)
                        .font(.headline)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 10)
                        .background(snapshot.level.color, in: RoundedRectangle(cornerRadius: 8))
                    Label(
                        snapshot.deltaLabel ?? "7일간 \(snapshot.delta7d >= 0 ? "+" : "")\(snapshot.delta7d)",
                        systemImage: snapshot.deltaLabel?.contains("반영") == true
                            ? "arrow.triangle.2.circlepath"
                            : snapshot.delta7d >= 0 ? "arrow.up.right" : "arrow.down.right"
                    )
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                }
                .padding(.bottom, 9)
            }

            Divider().overlay(AppTheme.line)

            Text(snapshot.summary.replacingOccurrences(of: "\n", with: " "))
                .font(.title3.weight(.medium))
                .lineSpacing(5)
                .foregroundStyle(AppTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private var strongestSignal: some View {
        if let item = snapshot.strongestIndicator {
            NavigationLink(value: item) {
                HStack(spacing: 16) {
                    Image(systemName: item.symbol)
                        .font(.title3)
                        .foregroundStyle(AppTheme.accent)
                        .frame(width: 44, height: 44)
                        .background(AppTheme.paleAccent, in: Circle())
                    VStack(alignment: .leading, spacing: 4) {
                        Text("가장 강한 신호")
                            .font(.caption)
                            .foregroundStyle(AppTheme.secondary)
                        Text("\(item.title)  \(item.score)")
                            .font(.headline)
                            .foregroundStyle(AppTheme.ink)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppTheme.secondary)
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 16)
                .background(Color.white.opacity(0.5))
            }
            .buttonStyle(.plain)
        }
    }

    private var indicatorMatrix: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("6대 지표")
                .font(.title2.bold())
            Divider().overlay(AppTheme.line)
            LazyVGrid(columns: columns, spacing: 0) {
                ForEach(Array(snapshot.indicators.enumerated()), id: \.element.id) { index, item in
                    NavigationLink(value: item) {
                        IndicatorCell(indicator: item)
                            .overlay(alignment: .trailing) {
                                if index % 3 != 2 {
                                    Rectangle().fill(AppTheme.line).frame(width: 1)
                                }
                            }
                            .overlay(alignment: .bottom) {
                                if index < 3 {
                                    Rectangle().fill(AppTheme.line).frame(height: 1)
                                }
                            }
                    }
                    .buttonStyle(.plain)

                }
            }
        }
    }

    private var historySection: some View {
        let points = compositeHistoryPoints
        let pricePoints = compositePricePoints
        let priceDomain = compositePriceDomain
        return VStack(alignment: .leading, spacing: 16) {
            Text("종합점수 추이").font(.title2.bold())
            HStack(spacing: 18) {
                chartLegend(title: "종합점수", color: AppTheme.accent)
                chartLegend(title: "서울 아파트 가격지수", color: AppTheme.rateBenchmark)
                Spacer()
            }
            Picker("조회 기간", selection: $compositeRange) {
                ForEach(CompositeHistoryRange.allCases) { range in
                    Text(range.title).tag(range)
                }
            }
            .pickerStyle(.segmented)
            .onChange(of: compositeRange) { _, _ in selectedCompositeIndex = nil }
            Chart {
                InteractiveSelectionMarks(selection: compositeChartSelection)
                ForEach(points) { point in
                    LineMark(x: .value("월", point.index), y: .value("점수", point.score), series: .value("계열", "score"))
                        .foregroundStyle(AppTheme.accent)
                        .lineStyle(.init(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    if point.index == points.last?.index {
                        PointMark(x: .value("월", point.index), y: .value("점수", point.score))
                            .foregroundStyle(AppTheme.accent)
                    }
                }
                ForEach(pricePoints) { point in
                    LineMark(x: .value("월", point.index), y: .value("가격 환산", point.normalizedValue), series: .value("계열", "price"))
                        .foregroundStyle(AppTheme.rateBenchmark)
                        .lineStyle(.init(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                    if point.index == pricePoints.last?.index {
                        PointMark(x: .value("월", point.index), y: .value("가격 환산", point.normalizedValue))
                            .foregroundStyle(AppTheme.rateBenchmark)
                    }
                }
            }
            .chartYScale(domain: 0...100)
            .chartXSelection(value: $selectedCompositeIndex)
            .interactiveChartTooltip(compositeChartSelection)
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .leading, values: [0, 25, 50, 75, 100]) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let score = value.as(Int.self) {
                            Text("\(score)").foregroundStyle(AppTheme.accent)
                        }
                    }
                }
                AxisMarks(position: .trailing, values: [0, 25, 50, 75, 100]) { value in
                    AxisValueLabel {
                        if let normalized = value.as(Double.self) {
                            Text(priceAxisLabel(normalized, domain: priceDomain))
                                .foregroundStyle(AppTheme.rateBenchmark)
                        }
                    }
                }
            }
            .frame(height: 170)
            HStack(alignment: .top, spacing: 0) {
                let indexes = compositeAxisIndexes(count: points.count)
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
            .padding(.leading, 28)
            .padding(.trailing, 4)
        }
    }

    private var dataStatus: (title: String, symbol: String, color: Color) {
        switch loadState {
        case .loading:
            return ("업데이트 중", "arrow.triangle.2.circlepath", AppTheme.secondary)
        case .failed:
            if snapshot.dataMode == "sample" || snapshot.dataMode == "fixture" {
                return ("내장 샘플", "hammer.fill", AppTheme.accent)
            }
            return ("저장 데이터", "internaldrive.fill", AppTheme.secondary)
        default:
            switch snapshot.dataMode {
            case "live": return ("실데이터", "checkmark.circle.fill", .green)
            case "partialLive": return ("일부 실데이터", "exclamationmark.circle.fill", AppTheme.accent)
            default: return ("샘플", "hammer.fill", AppTheme.accent)
            }
        }
    }

    private func chartLegend(title: String, color: Color) -> some View {
        HStack(spacing: 7) {
            Capsule().fill(color).frame(width: 20, height: 3)
            Text(title).font(.caption).foregroundStyle(AppTheme.secondary)
        }
    }

    private var compositeHistoryPoints: [CompositeHistoryPoint] {
        let labels = snapshot.historyLabels ?? snapshot.history.indices.map { "\($0 + 1)월" }
        let count = min(snapshot.history.count, labels.count)
        let start = max(0, count - compositeRange.monthCount)
        return (start..<count).enumerated().map { localIndex, sourceIndex in
            CompositeHistoryPoint(
                index: localIndex,
                score: snapshot.history[sourceIndex],
                label: labels[sourceIndex]
            )
        }
    }

    private var compositePricePoints: [CompositePricePoint] {
        let labels = snapshot.priceHistoryLabels ?? []
        let values = snapshot.priceHistory ?? []
        let count = min(labels.count, values.count)
        let valueByLabel = Dictionary(uniqueKeysWithValues: (0..<count).map { (labels[$0], values[$0]) })
        let domain = compositePriceDomain
        return compositeHistoryPoints.compactMap { scorePoint in
            guard let value = valueByLabel[scorePoint.label] else { return nil }
            let normalized = (value - domain.lowerBound) / (domain.upperBound - domain.lowerBound) * 100
            return CompositePricePoint(index: scorePoint.index, value: value, normalizedValue: normalized)
        }
    }

    private var selectedCompositePoint: (score: CompositeHistoryPoint, price: CompositePricePoint?)? {
        guard let selectedCompositeIndex,
              let score = compositeHistoryPoints.first(where: { $0.index == selectedCompositeIndex }) else {
            return nil
        }
        return (score, compositePricePoints.first(where: { $0.index == selectedCompositeIndex }))
    }

    private var compositeChartSelection: InteractiveChartSelection? {
        guard let selected = selectedCompositePoint else { return nil }
        var values = [
            InteractiveChartValue(
                title: "점수", displayValue: "\(selected.score.score)",
                plotValue: Double(selected.score.score), color: AppTheme.accent
            )
        ]
        if let price = selected.price {
            values.append(InteractiveChartValue(
                title: "가격",
                displayValue: price.value.formatted(.number.precision(.fractionLength(1))),
                plotValue: price.normalizedValue,
                color: AppTheme.rateBenchmark
            ))
        }
        return InteractiveChartSelection(index: selected.score.index, label: selected.score.label, values: values)
    }

    private var compositePriceDomain: ClosedRange<Double> {
        let values = snapshot.priceHistory ?? []
        guard let minimum = values.min(), let maximum = values.max() else { return 80...110 }
        let lower = floor(minimum / 10) * 10
        let upper = ceil(maximum / 10) * 10
        return lower...(upper > lower ? upper : lower + 10)
    }

    private func priceAxisLabel(_ normalized: Double, domain: ClosedRange<Double>) -> String {
        let value = domain.lowerBound + normalized / 100 * (domain.upperBound - domain.lowerBound)
        return value.formatted(.number.precision(.fractionLength(0)))
    }

    private func compositeAxisIndexes(count: Int) -> [Int] {
        guard count > 1 else { return [0] }
        let divisions = min(3, count - 1)
        return Array(Set((0...divisions).map {
            Int((Double($0) * Double(count - 1) / Double(divisions)).rounded())
        })).sorted()
    }

    private var disclaimer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if case .failed = loadState {
                if snapshot.dataMode == "fixture" || snapshot.dataMode == "sample" {
                    Label("서버에 연결하지 못해 앱에 내장된 샘플 데이터를 표시합니다.", systemImage: "wifi.slash")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.accent)
                } else {
                    Label("서버에 연결하지 못해 마지막 저장 데이터를 표시합니다.", systemImage: "wifi.slash")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.secondary)
                }
            } else if snapshot.dataMode == "partialLive" {
                let liveCount = snapshot.liveIndicatorCount ?? 1
                Label("현재 \(liveCount)개 지표가 실데이터이며 나머지 \(6 - liveCount)개는 샘플입니다.", systemImage: "exclamationmark.circle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.accent)
            } else if snapshot.dataMode == "fixture" || snapshot.dataMode == "sample" {
                Label("현재 화면은 개발용 샘플 데이터를 표시합니다.", systemImage: "hammer.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.accent)
            }
            Text("이 점수는 시장 관찰을 돕는 참고 정보이며 미래 가격이나 매수 시점을 예측하지 않습니다.")
                .font(.caption)
                .foregroundStyle(AppTheme.secondary)
                .lineSpacing(4)
        }
    }
}

private enum CompositeHistoryRange: String, CaseIterable, Identifiable {
    case oneYear, threeYears, fiveYears, all

    var id: String { rawValue }
    var title: String {
        switch self {
        case .oneYear: "1년"
        case .threeYears: "3년"
        case .fiveYears: "5년"
        case .all: "전체"
        }
    }
    var monthCount: Int {
        switch self {
        case .oneYear: 12
        case .threeYears: 36
        case .fiveYears: 60
        case .all: .max
        }
    }
}

private struct CompositeHistoryPoint: Identifiable {
    let index: Int
    let score: Int
    let label: String
    var id: Int { index }
}

private struct CompositePricePoint: Identifiable {
    let index: Int
    let value: Double
    let normalizedValue: Double
    var id: Int { index }
}

private struct IndicatorCell: View {
    let indicator: MarketIndicator

    var body: some View {
        VStack(spacing: 7) {
            Text(indicator.shortTitle)
                .font(.caption)
                .foregroundStyle(AppTheme.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text(indicator.id == "unpopular" ? indicator.value : "\(indicator.score)")
                .font(.system(size: 32, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(AppTheme.ink)
            Text(indicator.id == "unpopular" ? indicator.change : indicator.level.title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(indicator.id == "unpopular" ? AppTheme.secondary : indicator.level.color)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 18)
        .contentShape(Rectangle())
    }
}
