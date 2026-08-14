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
                Text("아파트고점지수")
                    .font(.caption.weight(.bold))
                    .tracking(2.2)
                    .foregroundStyle(AppTheme.accent)
                Text("서울")
                    .font(.system(size: 42, weight: .bold, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
            }
            Spacer(minLength: 12)
            VStack(alignment: .trailing, spacing: 7) {
                if let dataStatus {
                    Label(dataStatus.title, systemImage: dataStatus.symbol)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(dataStatus.color)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(dataStatus.color.opacity(0.10), in: Capsule())
                }
                Text(updateTimeLabel)
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
            }
            .padding(.bottom, 6)
        }
        .padding(.top, 20)
    }

    private var updateTimeLabel: String {
        guard let generated = snapshot.generatedAtLabel else {
            return "\(snapshot.asOf) 기준"
        }
        return snapshot.isStale() ? "업데이트 지연 · \(generated)" : "업데이트 \(generated)"
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("현재 판단")
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

            Text(snapshot.effectiveVerdict.title)
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .foregroundStyle(AppTheme.ink)

            Text(snapshot.effectiveVerdict.summary)
                .font(.title3.weight(.medium))
                .lineSpacing(5)
                .foregroundStyle(AppTheme.secondary)

            HStack(spacing: 0) {
                scoreColumn(
                    title: "가격 부담도", score: snapshot.effectivePriceBurdenScore,
                    detail: "소득·금리 대비", color: AppTheme.accent
                )
                Divider().overlay(AppTheme.line).padding(.horizontal, 18)
                scoreColumn(
                    title: "고점 전환 신호", score: snapshot.effectiveTransitionScore,
                    detail: "거래·청약 냉각", color: AppTheme.rateBenchmark
                )
            }
            .padding(18)
            .background(AppTheme.card, in: RoundedRectangle(cornerRadius: 18))

            Divider().overlay(AppTheme.line)
        }
    }

    private func scoreColumn(title: String, score: Int, detail: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(AppTheme.secondary)
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text("\(score)")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(color)
                Text("/100").font(.caption).foregroundStyle(AppTheme.secondary)
            }
            Text(detail).font(.caption2).foregroundStyle(AppTheme.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
                        Text("주요 근거")
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
        let burdenPoints = priceBurdenHistoryPoints
        let transitionPoints = transitionHistoryPoints
        return VStack(alignment: .leading, spacing: 16) {
            Text("시장 신호 추이").font(.title2.bold())
            HStack(spacing: 18) {
                chartLegend(title: "가격 부담도", color: AppTheme.accent)
                chartLegend(title: "고점 전환", color: AppTheme.rateBenchmark)
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
                ForEach(burdenPoints) { point in
                    LineMark(x: .value("월", point.index), y: .value("점수", point.score), series: .value("계열", "burden"))
                        .foregroundStyle(AppTheme.accent)
                        .lineStyle(.init(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    if point.index == burdenPoints.last?.index {
                        PointMark(x: .value("월", point.index), y: .value("점수", point.score))
                            .foregroundStyle(AppTheme.accent)
                    }
                }
                ForEach(transitionPoints) { point in
                    LineMark(x: .value("월", point.index), y: .value("점수", point.score), series: .value("계열", "transition"))
                        .foregroundStyle(AppTheme.rateBenchmark)
                        .lineStyle(.init(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                    if point.index == transitionPoints.last?.index {
                        PointMark(x: .value("월", point.index), y: .value("점수", point.score))
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
            }
            .frame(height: 170)
            HStack(alignment: .top, spacing: 0) {
                let indexes = compositeAxisIndexes(count: burdenPoints.count)
                ForEach(Array(indexes.enumerated()), id: \.element) { position, index in
                    let parts = burdenPoints[index].label.split(separator: " ")
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

    private var dataStatus: (title: String, symbol: String, color: Color)? {
        switch loadState {
        case .loading:
            return ("업데이트 중", "arrow.triangle.2.circlepath", AppTheme.secondary)
        case .failed:
            if snapshot.dataMode == "sample" || snapshot.dataMode == "fixture" {
                return ("내장 샘플", "hammer.fill", AppTheme.accent)
            }
            return ("저장 데이터", "internaldrive.fill", AppTheme.secondary)
        default:
            if snapshot.usesPreviousIndicatorValues {
                return ("일부 이전값", "clock.arrow.circlepath", AppTheme.accent)
            }
            switch snapshot.dataMode {
            case "live": return nil
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

    private var priceBurdenHistoryPoints: [CompositeHistoryPoint] {
        let values = snapshot.effectivePriceBurdenHistory
        let labels = snapshot.effectivePriceBurdenHistoryLabels ?? values.indices.map { "\($0 + 1)월" }
        let count = min(values.count, labels.count)
        let start = max(0, count - compositeRange.monthCount)
        return (start..<count).enumerated().map { localIndex, sourceIndex in
            CompositeHistoryPoint(
                index: localIndex,
                score: values[sourceIndex],
                label: labels[sourceIndex]
            )
        }
    }

    private var transitionHistoryPoints: [CompositeHistoryPoint] {
        let labels = snapshot.effectiveTransitionHistoryLabels ?? []
        let values = snapshot.effectiveTransitionHistory
        let count = min(labels.count, values.count)
        let valueByLabel = Dictionary(uniqueKeysWithValues: (0..<count).map { (labels[$0], values[$0]) })
        return priceBurdenHistoryPoints.compactMap { scorePoint in
            guard let value = valueByLabel[scorePoint.label] else { return nil }
            return CompositeHistoryPoint(index: scorePoint.index, score: value, label: scorePoint.label)
        }
    }

    private var selectedCompositePoint: (burden: CompositeHistoryPoint, transition: CompositeHistoryPoint?)? {
        guard let selectedCompositeIndex,
              let burden = priceBurdenHistoryPoints.first(where: { $0.index == selectedCompositeIndex }) else {
            return nil
        }
        return (burden, transitionHistoryPoints.first(where: { $0.index == selectedCompositeIndex }))
    }

    private var compositeChartSelection: InteractiveChartSelection? {
        guard let selected = selectedCompositePoint else { return nil }
        var values = [
            InteractiveChartValue(
                title: "부담", displayValue: "\(selected.burden.score)",
                plotValue: Double(selected.burden.score), color: AppTheme.accent
            )
        ]
        if let transition = selected.transition {
            values.append(InteractiveChartValue(
                title: "전환", displayValue: "\(transition.score)",
                plotValue: Double(transition.score),
                color: AppTheme.rateBenchmark
            ))
        }
        return InteractiveChartSelection(index: selected.burden.index, label: selected.burden.label, values: values)
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
            } else if snapshot.usesPreviousIndicatorValues {
                let titles = snapshot.previousValueIndicatorTitles
                let subject = titles.isEmpty ? "일부 지표" : titles.joined(separator: "·")
                Label("\(subject)은 이전 발표값을 사용 중이에요.", systemImage: "clock.arrow.circlepath")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.accent)
            } else if snapshot.dataMode == "fixture" || snapshot.dataMode == "sample" {
                Label("현재 화면은 개발용 샘플 데이터를 표시합니다.", systemImage: "hammer.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.accent)
            }
            Text("가격 부담도는 현재의 비싼 정도, 고점 전환 신호는 거래·청약의 냉각 정도를 보여줍니다. 두 점수 모두 미래 가격이나 정확한 매수 시점을 예측하지 않습니다.")
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
