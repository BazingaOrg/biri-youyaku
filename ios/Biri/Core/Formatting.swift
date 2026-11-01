import Foundation

struct Formatting {
    static func duration(_ seconds: Double?) -> String {
        guard let seconds, seconds.isFinite, seconds >= 0 else { return "时长未知" }
        let total = Int(seconds.rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let remainderSeconds = total % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, remainderSeconds)
        }
        return String(format: "%02d:%02d", minutes, remainderSeconds)
    }

    static func date(_ milliseconds: Int?) -> String {
        guard let milliseconds else { return "时间未知" }
        let date = Date(timeIntervalSince1970: TimeInterval(milliseconds) / 1000)
        return date.formatted(date: .abbreviated, time: .shortened)
    }
}
