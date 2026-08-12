import SwiftUI

struct RootView: View {
    @AppStorage("didFinishOnboarding") private var didFinishOnboarding = false

    var body: some View {
        if didFinishOnboarding {
            MainTabView()
        } else {
            OnboardingView {
                withAnimation { didFinishOnboarding = true }
            }
        }
    }
}

struct MainTabView: View {
    @StateObject private var marketStore = MarketStore()
    @State private var selectedTab = AppTab.market

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                HomeView(snapshot: marketStore.snapshot, loadState: marketStore.state)
                    .task { await marketStore.refresh() }
                    .refreshable { await marketStore.refresh() }
            }
                .tabItem { Label("시장", systemImage: "waveform.path.ecg") }
                .tag(AppTab.market)
            NavigationStack { MethodologyView(snapshot: marketStore.snapshot) }
                .tabItem { Label("계산법", systemImage: "function") }
                .tag(AppTab.methodology)
            NavigationStack { SettingsView() }
                .tabItem { Label("설정", systemImage: "gearshape") }
                .tag(AppTab.settings)
        }
        .tint(AppTheme.accent)
        .onOpenURL { url in
            if url.scheme == "gojump" { selectedTab = .market }
        }
    }
}

private enum AppTab: Hashable {
    case market, methodology, settings
}
