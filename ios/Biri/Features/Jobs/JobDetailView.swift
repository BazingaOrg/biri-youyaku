import SwiftUI
import UIKit

struct JobDetailView: View {
    let jobID: String

    @Environment(AppModel.self) private var appModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) private var openURL
    @State private var viewModel: JobDetailViewModel
    @State private var confirmation: JobDetailConfirmation?

    init(jobID: String) {
        self.jobID = jobID
        _viewModel = State(initialValue: JobDetailViewModel(jobID: jobID))
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.job == nil {
                ProgressView("正在加载任务…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let message = viewModel.errorMessage, viewModel.job == nil {
                ErrorStateView(message: message) { Task { await reconnect() } }
            } else if let job = viewModel.job {
                detail(job)
            }
        }
        .navigationTitle("任务详情")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await load()
            startStream()
        }
        .task(id: viewModel.pollKey) {
            guard viewModel.shouldPoll else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled, scenePhase == .active else { continue }
                await load(quietly: true)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                Task { await reconnect() }
            case .background:
                viewModel.stop()
            default:
                break
            }
        }
        .onDisappear { viewModel.stop() }
        .onChange(of: viewModel.didDelete) { _, deleted in
            if deleted { dismiss() }
        }
        .navigationDestination(item: $viewModel.navigation) { destination in
            JobDetailView(jobID: destination.id)
        }
        .navigationDestination(for: ReaderDestination.self) { destination in
            ReaderView(destination: destination)
        }
        .confirmationDialog(confirmation?.title ?? "确认操作", item: $confirmation) { item in
            switch item {
            case .cancel:
                Button("取消任务", role: .destructive) {
                    Task { await mutate(.cancel) }
                }
            case .resummarize:
                Button("重新生成") {
                    Task { await mutate(.resummarize) }
                }
            case .delete:
                Button("删除任务记录", role: .destructive) {
                    Task { await mutate(.delete) }
                }
            }
        } message: { item in
            Text(item.message)
        }
    }

    private func detail(_ job: Job) -> some View {
        ScrollView {
            VStack(spacing: 20) {
                VStack(alignment: .leading, spacing: 10) {
                    if let url = sourceURL(for: job) {
                        Button {
                            openURL(url)
                        } label: {
                            Text(job.displayTitle)
                                .font(.title3.weight(.semibold))
                                .foregroundStyle(Color.accentColor)
                                .underline()
                                .multilineTextAlignment(.leading)
                                .lineLimit(4)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .textSelection(.enabled)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("打开来源页面")
                        .disabled(viewModel.isMutating)
                    } else {
                        Text(job.displayTitle)
                            .font(.title3.weight(.semibold))
                            .multilineTextAlignment(.leading)
                            .lineLimit(4)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }
                    HStack(spacing: 8) {
                        if let author = job.author, !author.isEmpty {
                            Text(author)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        JobStatusBadge(status: job.status)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 12)

                if job.status.isActive {
                    actions(for: job)
                    connectionStatus
                    JobProgressCard(viewModel: viewModel, job: job)
                    livePreview(for: job)
                }

                if let message = viewModel.noticeMessage {
                    Label(message, systemImage: "checkmark.circle.fill")
                        .font(.footnote)
                        .foregroundStyle(.green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if let message = viewModel.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                }

                if job.status == .failed, let message = job.errorMessage, !message.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        Label("生成失败", systemImage: "exclamationmark.triangle.fill")
                            .font(.headline)
                        Text(message)
                            .font(.callout)
                        if let stage = job.errorStage, !stage.isEmpty {
                            Text("失败阶段：\(stage)")
                                .font(.caption)
                                .textSelection(.enabled)
                        }
                    }
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                }

                if let emailError = viewModel.emailError, !emailError.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("笔记已完成，但邮件未送达", systemImage: "envelope.badge.shield.half.filled")
                            .font(.headline)
                        Text(emailError)
                            .font(.footnote)
                        Button("重发邮件") { Task { await mutate(.resendEmail) } }
                            .buttonStyle(.bordered)
                            .disabled(viewModel.isMutating)
                    }
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(Color.orange.opacity(0.09), in: RoundedRectangle(cornerRadius: 12))
                }

                if !job.status.isActive {
                    actions(for: job)
                }

                VStack(spacing: 0) {
                    DetailRow(title: "创建时间", value: Formatting.date(job.createdAt))
                    Divider().padding(.leading, 16)
                    DetailRow(title: "更新时间", value: Formatting.date(job.updatedAt))
                    Divider().padding(.leading, 16)
                    DetailRow(title: "任务 ID", value: job.id, singleLine: true) {
                        UIPasteboard.general.string = job.id
                        viewModel.noticeMessage = "任务 ID 已复制"
                    }
                }
                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
            }
            .padding(20)
            .frame(maxWidth: 700)
            .frame(maxWidth: .infinity)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .toolbar { taskToolbar(for: job) }
        .refreshable { await reconnect() }
    }

    @ViewBuilder
    private var connectionStatus: some View {
        switch viewModel.connectionState {
        case .connecting:
            Label("正在连接实时进度…", systemImage: "antenna.radiowaves.left.and.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        case .connected:
            Label("实时进度已连接", systemImage: "dot.radiowaves.left.and.right")
                .font(.caption)
                .foregroundStyle(.green)
        case .reconnecting:
            Label("正在刷新快照并重新连接，已启用自动刷新", systemImage: "arrow.triangle.2.circlepath")
                .font(.caption)
                .foregroundStyle(.orange)
                .multilineTextAlignment(.center)
        case .stopped, .finished:
            EmptyView()
        }
    }

    @ViewBuilder
    private func livePreview(for job: Job) -> some View {
        if job.status == .summarizing, let summary = viewModel.liveSummary, !summary.isEmpty {
            VStack(alignment: .leading, spacing: 9) {
                Label("笔记实时预览（尚未完成）", systemImage: "text.document")
                    .font(.headline)
                Text(summary)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(15)
            .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        } else if job.status == .transcribing {
            let preview = viewModel.transcribePreview ?? viewModel.transcriptPreview.suffix(3).map(\.text).joined(separator: "\n")
            if !preview.isEmpty {
                VStack(alignment: .leading, spacing: 9) {
                    Label("字幕实时预览", systemImage: "captions.bubble")
                        .font(.headline)
                    Text(preview)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(15)
                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    @ToolbarContentBuilder
    private func taskToolbar(for job: Job) -> some ToolbarContent {
        if viewModel.canResummarize || (!job.status.isActive && job.status != .canceled) {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    if viewModel.canResummarize {
                        Button {
                            confirmation = .resummarize
                        } label: {
                            Label("重新生成", systemImage: "sparkles")
                        }
                        .disabled(viewModel.isMutating)
                    }

                    if !job.status.isActive && job.status != .canceled {
                        Button(role: .destructive) {
                            confirmation = .delete(job)
                        } label: {
                            Label("删除任务", systemImage: "trash")
                        }
                        .disabled(viewModel.isMutating)
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .accessibilityLabel("任务操作")
            }
        }
    }

    @ViewBuilder
    private func actions(for job: Job) -> some View {
        VStack(spacing: 12) {
            if let destination = job.destination {
                NavigationLink(value: destination) {
                    Label("阅读笔记", systemImage: "book.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(viewModel.isMutating)
            }

            if job.status == .failed {
                Button {
                    Task { await mutate(.retry) }
                } label: {
                    mutationLabel("重试任务", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(viewModel.isMutating)
            }

            if job.status == .transcriptReady {
                HStack(spacing: 12) {
                    Button {
                        Task { await mutate(.resume) }
                    } label: {
                        mutationLabel("继续生成", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(viewModel.isMutating)

                    cancelTaskButton
                }
            } else if job.status.isActive {
                cancelTaskButton
            } else if job.status == .canceled {
                Button(role: .destructive) {
                    confirmation = .delete(job)
                } label: {
                    Label("删除任务", systemImage: "trash")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(viewModel.isMutating)
            }
        }
    }

    private var cancelTaskButton: some View {
        Button("取消任务", role: .destructive) {
            confirmation = .cancel
        }
        .frame(maxWidth: .infinity)
        .buttonStyle(.bordered)
        .controlSize(.large)
        .disabled(viewModel.isMutating)
    }

    private func mutationLabel(_ title: String, systemImage: String) -> some View {
        HStack(spacing: 8) {
            if viewModel.isMutating {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: systemImage)
            }
            Text(title)
        }
        .frame(maxWidth: .infinity)
    }

    private func sourceURL(for job: Job) -> URL? {
        guard let url = URL(string: job.url),
              ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return nil }
        return url
    }

    private func load(quietly: Bool = false) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service, quietly: quietly)
    }

    private func startStream() {
        guard viewModel.job != nil, let service = try? appModel.makeService() else { return }
        viewModel.start(using: service)
    }

    private func reconnect() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.reconnect(using: service)
    }

    private func mutate(_ action: JobDetailMutation) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        switch action {
        case .cancel: await viewModel.cancel(using: service)
        case .retry: await viewModel.retry(using: service)
        case .resume: await viewModel.resume(using: service)
        case .resummarize: await viewModel.resummarize(using: service)
        case .delete: await viewModel.delete(using: service)
        case .resendEmail: await viewModel.resendEmail(using: service)
        }
    }
}

private enum JobDetailMutation {
    case cancel
    case retry
    case resume
    case resummarize
    case delete
    case resendEmail
}

private enum JobDetailConfirmation: Identifiable {
    case cancel
    case resummarize
    case delete(Job)

    var id: String {
        switch self {
        case .cancel: "cancel"
        case .resummarize: "resummarize"
        case .delete: "delete"
        }
    }

    var title: String {
        switch self {
        case .cancel: "取消这个任务？"
        case .resummarize: "重新生成笔记？"
        case .delete: "删除任务记录？"
        }
    }

    var message: String {
        switch self {
        case .cancel:
            return "服务器会停止后续处理，已生成的中间结果按现有规则保留。"
        case .resummarize:
            return "将使用已有字幕创建一个新任务，当前笔记和任务记录会保留。"
        case let .delete(job):
            if job.documentId == nil, job.summaryAvailable == true || job.summary?.isEmpty == false {
                return "这条旧任务的笔记仅保存在任务中。删除任务也会永久删除笔记，无法撤销。"
            }
            return "任务记录将被删除，已同步到资料库的笔记会保留。此操作无法撤销。"
        }
    }
}

private struct DetailRow: View {
    let title: String
    let value: String
    var singleLine = false
    var onCopy: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.footnote)
                .foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Text(value)
                    .lineLimit(singleLine ? 1 : nil)
                    .truncationMode(.middle)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let onCopy {
                    Button(action: onCopy) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("复制任务 ID")
                }
            }
        }
        .padding(16)
    }
}
