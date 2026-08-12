import SwiftUI

struct MethodologyView: View {
    let snapshot: MarketSnapshot

    var body: some View {
        List {
            Section {
                Text("각 지표를 0~100점으로 바꾸고 데이터 품질과 초기 가중치를 반영합니다. 점수가 높을수록 여러 고점 신호가 강하게 겹친 상태예요.")
                    .foregroundStyle(AppTheme.secondary)
            }
            Section {
                ForEach(snapshot.indicators) { indicator in
                    HStack {
                        Label(indicator.title, systemImage: indicator.symbol)
                        Spacer()
                        Text(weight(for: indicator.id))
                            .foregroundStyle(AppTheme.secondary)
                    }
                }
            } header: {
                Text("현재 계산 비중")
            } footer: {
                Text("비인기 거래 확산도 Beta는 고정 비중 없이 최대 2.5점의 보조 신호로만 반영합니다.")
            }
            Section("점수 단계") {
                ForEach(MarketLevel.allCases, id: \.self) { level in
                    HStack {
                        Circle().fill(level.color).frame(width: 10, height: 10)
                        Text(level.title)
                        Spacer()
                        Text(range(for: level)).foregroundStyle(AppTheme.secondary)
                    }
                }
            }
            Section("원칙") {
                Label("누락된 데이터는 0점으로 계산하지 않아요.", systemImage: "checkmark.shield")
                Label("출처와 데이터 기준일을 항상 표시해요.", systemImage: "calendar.badge.checkmark")
                Label("가격의 미래를 예측하지 않아요.", systemImage: "eye")
            }
        }
        .scrollContentBackground(.hidden)
        .background(AppTheme.background)
        .navigationTitle("어떻게 계산하나요?")
    }

    private func weight(for id: String) -> String {
        guard let weight = ScoreCalculator.weights[id] else {
            return id == "unpopular" ? "보조 신호" : "제외"
        }
        let total = ScoreCalculator.weights.values.reduce(0, +)
        return (weight / total * 100).formatted(.number.precision(.fractionLength(1))) + "%"
    }

    private func range(for level: MarketLevel) -> String {
        switch level {
        case .stable: "0–24"
        case .watch: "25–44"
        case .caution: "45–64"
        case .alert: "65–79"
        case .highRisk: "80–100"
        }
    }
}
