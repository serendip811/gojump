import SwiftUI

enum AppTheme {
    static let background = Color(red: 0.965, green: 0.957, blue: 0.937)
    static let card = Color.white.opacity(0.82)
    static let ink = Color(red: 0.11, green: 0.105, blue: 0.095)
    static let secondary = Color(red: 0.42, green: 0.40, blue: 0.36)
    static let accent = Color(red: 0.76, green: 0.27, blue: 0.10)
    static let rateBenchmark = Color(red: 0.12, green: 0.38, blue: 0.62)
    static let paleAccent = Color(red: 0.95, green: 0.87, blue: 0.81)
    static let line = Color.black.opacity(0.08)
}

extension MarketLevel {
    var color: Color {
        switch self {
        case .stable: Color(red: 0.20, green: 0.48, blue: 0.42)
        case .watch: Color(red: 0.48, green: 0.53, blue: 0.33)
        case .caution: Color(red: 0.75, green: 0.52, blue: 0.16)
        case .alert: AppTheme.accent
        case .highRisk: Color(red: 0.58, green: 0.12, blue: 0.10)
        }
    }
}
