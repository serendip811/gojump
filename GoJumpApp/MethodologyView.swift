import SwiftUI

struct MethodologyView: View {
    let snapshot: MarketSnapshot

    var body: some View {
        List {
            Section {
                Text("한 점수로 고점을 단정하지 않아요. 가격이 소득·금리에 비해 얼마나 부담스러운지와 거래·청약이 실제로 식는지를 분리해 봅니다.")
                    .foregroundStyle(AppTheme.secondary)
            }
            Section("두 점수") {
                methodologyRow("가격 부담도", detail: "구입부담 75% · 금리 25%", color: AppTheme.accent)
                methodologyRow("고점 전환 신호", detail: "거래량 냉각 55% · 청약 냉각 45%", color: AppTheme.rateBenchmark)
            }
            Section("현재 판단") {
                Text(snapshot.effectiveVerdict.title).font(.headline)
                Text(snapshot.effectiveVerdict.summary).foregroundStyle(AppTheme.secondary)
                Text("두 점수 중 65점 이상을 ‘높음’으로 보고 네 가지 시장 상태를 구분합니다.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
            }
            Section {
                ForEach(snapshot.indicators) { indicator in
                    HStack {
                        Label(indicator.title, systemImage: indicator.symbol)
                        Spacer()
                        Text(role(for: indicator.id))
                            .foregroundStyle(AppTheme.secondary)
                    }
                }
            } header: {
                Text("지표 역할")
            } footer: {
                Text("공급과 비인기 거래 확산도 Beta는 두 핵심 점수에 넣지 않고 해석을 돕는 보조 정보로 제공합니다.")
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
                Label("가격보다 먼저 움직인다는 보장을 하지 않아요.", systemImage: "eye")
            }
        }
        .scrollContentBackground(.hidden)
        .background(AppTheme.background)
        .navigationTitle("어떻게 계산하나요?")
    }

    private func methodologyRow(_ title: String, detail: String, color: Color) -> some View {
        HStack {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(title)
            Spacer()
            Text(detail).font(.caption).foregroundStyle(AppTheme.secondary)
        }
    }

    private func role(for id: String) -> String {
        switch id {
        case "pir": "부담도 75%"
        case "rate": "부담도 25%"
        case "volume": "전환 55%"
        case "subscription": "전환 45%"
        case "supply": "공급 여건"
        case "unpopular": "실험 지표"
        default: "보조 정보"
        }
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
