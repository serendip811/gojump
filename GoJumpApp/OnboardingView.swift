import SwiftUI

struct OnboardingView: View {
    let finish: () -> Void

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                Spacer()
                Text("아파트고점지수")
                    .font(.caption.weight(.bold))
                    .tracking(2.4)
                    .foregroundStyle(AppTheme.accent)
                Text("비싼 시장과\n꺾이는 시장은 다릅니다.")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(AppTheme.ink)
                    .padding(.top, 12)
                Text("가격 부담도와 고점 전환 신호를 나눠\n지금 시장의 상태를 확인하세요.")
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
                Text("두 점수는 미래 가격이나 정확한 매수 시점을 예측하지 않습니다.")
                    .font(.caption)
                    .foregroundStyle(AppTheme.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 16)
            }
            .padding(24)
        }
    }
}
