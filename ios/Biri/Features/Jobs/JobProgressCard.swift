import SwiftUI

struct JobProgressCard: View {
    let viewModel: JobDetailViewModel
    let job: Job

    var body: some View {
        VStack(spacing: 18) {
            stageRow(.source)
            stageRow(.transcript)
            stageRow(.summary)
            stageRow(.email)
        }
        .padding(16)
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
    }

    private func stageRow(_ stage: ProgressStage) -> some View {
        JobStageRow(
            title: stage.title,
            detail: detail(for: stage),
            state: state(for: stage),
            fraction: fraction(for: stage),
            valueLabel: valueLabel(for: stage)
        )
    }

    private func state(for stage: ProgressStage) -> JobStageState {
        if stage == .email, viewModel.emailError?.isEmpty == false { return .failed }
        if job.status == .canceled { return .waiting }

        if job.status == .failed {
            let failedRank = rank(forErrorStage: job.errorStage)
            if stage.rank < failedRank { return .done }
            if stage.rank == failedRank { return .failed }
            return .waiting
        }

        let currentRank = rank(for: job.status)
        if stage.rank < currentRank { return .done }
        if stage.rank == currentRank { return .current }
        return .waiting
    }

    private func detail(for stage: ProgressStage) -> String {
        if job.status == .canceled { return "任务已取消" }
        if job.status == .failed {
            let failedRank = rank(forErrorStage: job.errorStage)
            if stage.rank == failedRank { return "这一阶段未能完成" }
            if stage.rank > failedRank { return "等待前序阶段恢复" }
        }

        switch stage {
        case .source:
            switch job.status {
            case .pending: return "等待服务器开始处理"
            case .fetchingMeta: return "正在获取标题、作者与视频信息"
            case .downloadingAudio:
                if let downloaded = viewModel.downloadProgress?.downloadedBytes,
                   let total = viewModel.downloadProgress?.totalBytes,
                   total > 0 {
                    return "已下载 \(byteCount(downloaded)) / \(byteCount(total))"
                }
                return "正在下载音频"
            default: return "已获取来源信息"
            }
        case .transcript:
            switch job.status {
            case .transcribing:
                if let count = viewModel.transcribeProgress?.itemsCount {
                    return "已生成 \(count) 条字幕"
                }
                return "正在生成字幕"
            case .pending, .fetchingMeta, .downloadingAudio: return "等待音频下载完成"
            default: return "字幕已就绪"
            }
        case .summary:
            switch job.status {
            case .transcriptReady: return "字幕已就绪，可以继续生成"
            case .summarizing:
                if let progress = viewModel.summaryProgress {
                    return "已总结 \(progress.done) / \(progress.total) 段"
                }
                return "正在根据字幕生成笔记"
            case .pending, .fetchingMeta, .downloadingAudio, .transcribing: return "等待字幕完成"
            default: return "笔记已生成"
            }
        case .email:
            if viewModel.emailError?.isEmpty == false { return "邮件未送达，可以重发" }
            switch job.status {
            case .emailing: return "正在按任务设置发送邮件"
            case .completed: return "已按任务设置处理"
            default: return "笔记完成后按任务设置处理"
            }
        }
    }

    private func fraction(for stage: ProgressStage) -> Double? {
        guard state(for: stage) == .current else { return nil }
        switch stage {
        case .source:
            return percentFraction(viewModel.downloadProgress?.percent)
        case .transcript:
            return percentFraction(viewModel.transcribeProgress?.percent)
        case .summary:
            guard let progress = viewModel.summaryProgress, progress.total > 0 else { return nil }
            return min(max(Double(progress.done) / Double(progress.total), 0), 1)
        case .email:
            return nil
        }
    }

    private func valueLabel(for stage: ProgressStage) -> String? {
        switch stage {
        case .source:
            guard job.status == .downloadingAudio else { return nil }
            return percentLabel(viewModel.downloadProgress?.percent)
        case .transcript:
            guard job.status == .transcribing else { return nil }
            return percentLabel(viewModel.transcribeProgress?.percent)
        case .summary:
            guard job.status == .summarizing, let progress = viewModel.summaryProgress else { return nil }
            return "\(progress.done)/\(progress.total)"
        case .email:
            return nil
        }
    }

    private func percentFraction(_ percent: Double?) -> Double? {
        guard let percent, percent.isFinite else { return nil }
        return min(max(percent / 100, 0), 1)
    }

    private func percentLabel(_ percent: Double?) -> String? {
        guard let percent, percent.isFinite else { return nil }
        return "\(Int(min(max(percent, 0), 100).rounded()))%"
    }

    private func byteCount(_ value: Double) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(max(value, 0)), countStyle: .file)
    }

    private func rank(for status: JobStatus) -> Int {
        switch status {
        case .pending, .fetchingMeta, .downloadingAudio: 0
        case .transcribing: 1
        case .transcriptReady, .summarizing: 2
        case .emailing: 3
        case .completed: 4
        case .failed, .canceled: 0
        }
    }

    private func rank(forErrorStage stage: String?) -> Int {
        switch stage?.uppercased() {
        case "TRANSCRIBING": 1
        case "TRANSCRIPT_READY", "SUMMARIZING": 2
        case "EMAILING": 3
        default: 0
        }
    }
}

private enum ProgressStage {
    case source
    case transcript
    case summary
    case email

    var rank: Int {
        switch self {
        case .source: 0
        case .transcript: 1
        case .summary: 2
        case .email: 3
        }
    }

    var title: String {
        switch self {
        case .source: "获取来源"
        case .transcript: "生成字幕"
        case .summary: "总结笔记"
        case .email: "发送邮件"
        }
    }
}

private enum JobStageState: Equatable {
    case waiting
    case current
    case done
    case failed
}

private struct JobStageRow: View {
    let title: String
    let detail: String
    let state: JobStageState
    let fraction: Double?
    let valueLabel: String?

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            Image(systemName: iconName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(iconColor)
                .frame(width: 24, height: 24)
                .background(iconColor.opacity(0.12), in: Circle())

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let fraction {
                    ProgressView(value: fraction)
                        .tint(state == .failed ? .red : .accentColor)
                        .padding(.top, 3)
                }
            }

            Spacer(minLength: 4)
            if let valueLabel {
                Text(valueLabel)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var iconName: String {
        switch state {
        case .waiting: "circle"
        case .current: "clock.fill"
        case .done: "checkmark.circle.fill"
        case .failed: "exclamationmark.circle.fill"
        }
    }

    private var iconColor: Color {
        switch state {
        case .waiting: .secondary
        case .current: .accentColor
        case .done: .green
        case .failed: .red
        }
    }
}
