import SwiftUI

struct OnboardingView: View {
    let finish: () -> Void

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                Spacer()
                Text("GO—JUMP")
                    .font(.caption.weight(.bold))
                    .tracking(2.4)
                    .foregroundStyle(AppTheme.accent)
                Text("집값의 미래보다\n지금의 신호를 봅니다.")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
                    .padding(.top, 12)
                Text("흩어진 여섯 가지 시장 지표를 한곳에서\n쉽고 차분하게 확인하세요.")
                    .font(.title3)
                    .foregroundStyle(AppTheme.secondary)
                    .lineSpacing(6)
                    .padding(.top, 20)
                Spacer()
                HStack(spacing: 10) {
                    ForEach(["house.fill", "chart.bar.fill", "percent"], id: \.self) { icon in
                        Image(systemName: icon)
                            .font(.title3)
                            .frame(width: 54, height: 54)
                            .background(AppTheme.card, in: RoundedRectangle(cornerRadius: 18))
                    }
                    Text("+ 3개 지표")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppTheme.secondary)
                }
                Button(action: finish) {
                    HStack {
                        Text("서울 시장 살펴보기")
                        Spacer()
                        Image(systemName: "arrow.right")
                    }
                    .font(.headline)
                    .foregroundStyle(.white)
                    .padding(20)
                    .background(AppTheme.ink, in: RoundedRectangle(cornerRadius: 20))
                }
                .padding(.top, 32)
                Text("정보 제공 목적이며 부동산 투자 자문이 아닙니다.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 16)
            }
            .padding(24)
        }
    }
}
