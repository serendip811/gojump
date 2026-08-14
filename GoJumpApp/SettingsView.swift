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
                LabeledContent("버전", value: appVersion)
                Button("온보딩 다시 보기") { didFinishOnboarding = false }
            }
            Section("지원 및 정책") {
                Link(destination: URL(string: "https://serendip811.github.io/gojump/sources/")!) {
                    Label("데이터 출처", systemImage: "building.columns")
                }
                Link(destination: URL(string: "https://serendip811.github.io/gojump/privacy/")!) {
                    Label("개인정보처리방침", systemImage: "hand.raised")
                }
                Link(destination: URL(string: "https://serendip811.github.io/gojump/support/")!) {
                    Label("문의 및 지원", systemImage: "questionmark.circle")
                }
            }
            Section {
                Text("아파트고점지수는 교육 및 정보 제공 목적이며 부동산·금융·투자 자문이 아닙니다.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(AppTheme.background)
        .navigationTitle("설정")
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0.0"
    }
}
