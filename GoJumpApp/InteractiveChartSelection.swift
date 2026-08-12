import Charts
import SwiftUI

struct InteractiveChartValue: Identifiable {
    let title: String
    let displayValue: String
    let plotValue: Double
    let color: Color

    var id: String { title }
}

struct InteractiveChartSelection {
    let index: Int
    let label: String
    let values: [InteractiveChartValue]
}

struct InteractiveSelectionMarks: ChartContent {
    let selection: InteractiveChartSelection?

    var body: some ChartContent {
        if let selection {
            RuleMark(x: .value("선택 기간", selection.index))
                .foregroundStyle(AppTheme.secondary.opacity(0.55))
                .lineStyle(.init(lineWidth: 1, dash: [3, 3]))
            ForEach(selection.values) { value in
                PointMark(
                    x: .value("선택 기간", selection.index),
                    y: .value(value.title, value.plotValue)
                )
                .foregroundStyle(value.color)
                .symbolSize(55)
            }
        }
    }
}

extension View {
    func interactiveChartTooltip(_ selection: InteractiveChartSelection?) -> some View {
        chartOverlay { proxy in
            GeometryReader { geometry in
                if let selection,
                   let plotAnchor = proxy.plotFrame,
                   let xPosition = proxy.position(forX: selection.index) {
                    let plotFrame = geometry[plotAnchor]
                    InteractiveChartTooltip(selection: selection)
                        .frame(width: selection.values.count > 1 ? 154 : 126)
                        .position(
                            x: min(
                                max(plotFrame.minX + xPosition, plotFrame.minX + 77),
                                plotFrame.maxX - 77
                            ),
                            y: plotFrame.minY + 27
                        )
                        .allowsHitTesting(false)
                }
            }
        }
    }
}

private struct InteractiveChartTooltip: View {
    let selection: InteractiveChartSelection

    var body: some View {
        VStack(spacing: 4) {
            Text(selection.label)
                .foregroundStyle(.white.opacity(0.72))
            HStack(spacing: 9) {
                ForEach(selection.values) { value in
                    Text("\(value.title) \(value.displayValue)")
                        .foregroundStyle(value.color)
                }
            }
        }
        .font(.caption2.weight(.semibold))
        .lineLimit(1)
        .minimumScaleFactor(0.75)
        .monospacedDigit()
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(Color.black.opacity(0.88), in: RoundedRectangle(cornerRadius: 9))
    }
}
