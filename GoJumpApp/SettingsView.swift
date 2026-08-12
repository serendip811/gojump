import SwiftUI

struct SettingsView: View {
    @AppStorage("didFinishOnboarding") private var didFinishOnboarding = true

    var body: some View {
        Form {
            Section("위젯") {
                Label("홈 화면이나 잠금 화면을 길게 눌러 위젯을 추가하세요.", systemImage: "rectangle.3.group")
                    .foregroundStyle(AppTheme.secondary)
            }
            Section("정보") {
                LabeledContent("데이터 지역", value: "서울")
                LabeledContent("프로토타입", value: "0.1.0")
                Button("온보딩 다시 보기") { didFinishOnboarding = false }
            }
            Section {
                Text("GoJump은 교육 및 정보 제공 목적이며 부동산·금융·투자 자문이 아닙니다.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(AppTheme.background)
        .navigationTitle("설정")
    }
}
