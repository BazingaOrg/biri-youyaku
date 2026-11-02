import SwiftUI
import UIKit

struct DistillView: View {
    @Environment(AppModel.self) private var appModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var viewModel: DistillViewModel
    @State private var showingCancelConfirmation = false
    @State private var showingDeleteConfirmation = false
    @State private var showCopied = false

    init(mid: Int, author: String) {
        _viewModel = State(initialValue: DistillViewModel(mid: mid, author: author))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                startSection
                if let run = viewModel.run {
                    runSection(run)
                }
                if let message = viewModel.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                }
                Text("蒸馏只整理该 UP 主的语料；删除蒸馏结果不会删除已生成的单篇笔记。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .padding(20)
            .frame(maxWidth: 700)
            .frame(maxWidth: .infinity)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("蒸馏语料")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .task(id: corpusTaskKey) {
            guard viewModel.run?.status == .completed, viewModel.corpus == nil else { return }
            await loadCorpus()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await load() } }
        }
        .onDisappear { viewModel.stopObserving() }
        .confirmationDialog(
            "取消这次蒸馏？",
            isPresented: $showingCancelConfirmation,
            titleVisibility: .visible
        ) {
            Button("取消蒸馏", role: .destructive) {
                Task { await cancel() }
            }
            Button("继续处理", role: .cancel) {}
        } message: {
            Text("服务器会停止后续处理，已生成的中间结果按现有规则保留。")
        }
        .confirmationDialog(
            "删除蒸馏语料？",
            isPresented: $showingDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("删除语料", role: .destructive) {
                Task { await delete() }
            }
            Button("保留", role: .cancel) {}
        } message: {
            Text("将删除该 UP 主的蒸馏语料和运行记录，无法撤销。单篇笔记不受影响。")
        }
        .overlay(alignment: .bottom) {
            if showCopied {
                Text("已复制 Markdown 语料")
                    .font(.callout)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(.regularMaterial, in: Capsule())
                    .padding(.bottom, 20)
            }
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            Image(systemName: "square.stack.3d.up.fill")
                .font(.title)
                .foregroundStyle(Color.accentColor)
            Text(viewModel.author)
                .font(.title2.weight(.semibold))
                .multilineTextAlignment(.center)
            Text("实验功能 · 从最近的视频提炼主题与观点")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }

    private var startSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("处理最近 \(viewModel.videoLimit) 个视频")
                        .font(.headline)
                    Text("可选择 1 到 200 个，仅处理当前 UP 主")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Stepper(
                    "视频数量",
                    value: $viewModel.videoLimit,
                    in: 1...200
                )
                .labelsHidden()
                .disabled(viewModel.run?.status.isActive == true || viewModel.isStarting)
            }

            if viewModel.run?.status.isActive != true {
                Button {
                    Task { await start() }
                } label: {
                    HStack {
                        if viewModel.isStarting { ProgressView().controlSize(.small) }
                        Text(startButtonTitle)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(viewModel.isStarting || viewModel.isDeleting || viewModel.isLoading)
            }
        }
        .padding()
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
    }

    private var startButtonTitle: String {
        if viewModel.isStarting { return "正在创建…" }
        switch viewModel.run?.status {
        case .failed, .cancelled: return "重新开始（创建新任务）"
        case .completed: return "创建新的蒸馏任务"
        default: return "开始蒸馏"
        }
    }

    private func runSection(_ run: DistillRun) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label(run.status.label, systemImage: run.status.systemImage)
                    .font(.headline)
                    .foregroundStyle(run.status.color)
                Spacer()
                Text("上限 \(run.videoLimit) 个")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if run.status.isActive {
                if !viewModel.connectionState.label.isEmpty {
                    Label(viewModel.connectionState.label, systemImage: "antenna.radiowaves.left.and.right")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if viewModel.connectionState == .connecting || viewModel.connectionState == .reconnecting {
                    ProgressView().controlSize(.small)
                }
            }

            if let progress = run.realProgress {
                VStack(alignment: .leading, spacing: 8) {
                    Text(progress.label)
                        .font(.subheadline)
                    ProgressView(value: Double(progress.completed), total: Double(progress.total))
                    Text("共 \(run.counters.videosTotal) 个视频 · 已转写 \(run.counters.videosTranscribed) · 已提炼 \(run.counters.videosExtracted) · 失败 \(run.counters.videosFailed)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("共 \(run.counters.videosTotal) 个视频 · 已转写 \(run.counters.videosTranscribed) · 已提炼 \(run.counters.videosExtracted) · 失败 \(run.counters.videosFailed)")
                    .font(.subheadline)
            }

            if let error = run.error, !error.isEmpty {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(.red)
            }

            if run.status.isActive {
                Button(viewModel.isCancelling ? "正在提交取消…" : "取消蒸馏") {
                    showingCancelConfirmation = true
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isCancelling)
            } else {
                Button(viewModel.isDeleting ? "正在删除…" : "删除蒸馏语料", role: .destructive) {
                    showingDeleteConfirmation = true
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isDeleting || viewModel.isStarting)
            }

            if run.status == .completed {
                corpusSection
            }
        }
        .padding()
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
    }

    private var corpusSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()
            HStack {
                Text("Markdown 语料")
                    .font(.headline)
                Spacer()
                Button {
                    guard let corpus = viewModel.corpus else { return }
                    UIPasteboard.general.string = corpus
                    showCopied = true
                    Task {
                        try? await Task.sleep(for: .seconds(2))
                        showCopied = false
                    }
                } label: {
                    Label("复制", systemImage: "doc.on.doc")
                }
                .disabled(viewModel.corpus == nil)
            }

            if viewModel.isLoadingCorpus {
                ProgressView("正在读取语料…")
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if let corpus = viewModel.corpus {
                ScrollView {
                    Text(corpus)
                        .font(.system(.footnote, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                }
                .frame(maxHeight: 420)
                .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 10))
            } else {
                Button("加载语料预览") { Task { await loadCorpus() } }
            }
        }
    }

    private var corpusTaskKey: String {
        guard let run = viewModel.run else { return "none" }
        return "\(run.id)-\(run.status.rawValue)-\(viewModel.corpusRunID ?? "none")"
    }

    private func service() -> (any DistillServicing)? {
        try? appModel.makeService()
    }

    private func load() async {
        guard let service = service() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service)
    }

    private func start() async {
        guard let service = service() else { return }
        await viewModel.start(using: service)
    }

    private func cancel() async {
        guard let service = service() else { return }
        await viewModel.cancel(using: service)
    }

    private func delete() async {
        guard let service = service() else { return }
        await viewModel.delete(using: service)
    }

    private func loadCorpus() async {
        guard let service = service() else { return }
        await viewModel.loadCorpus(using: service)
    }
}

private extension DistillRunStatus {
    var label: String {
        switch self {
        case .pending: "等待处理"
        case .fetchingDynamics: "准备中"
        case .preparingTranscripts: "准备转写"
        case .extracting: "提取观点"
        case .assembling: "组装语料"
        case .completed: "已完成"
        case .failed: "蒸馏失败"
        case .cancelled: "已取消"
        }
    }

    var systemImage: String {
        switch self {
        case .completed: "checkmark.circle.fill"
        case .failed: "exclamationmark.circle.fill"
        case .cancelled: "stop.circle.fill"
        default: "clock.fill"
        }
    }

    var color: Color {
        switch self {
        case .completed: .green
        case .failed: .red
        case .cancelled: .secondary
        default: .accentColor
        }
    }
}

private extension DistillRun {
    var realProgress: (completed: Int, total: Int, label: String)? {
        guard counters.videosTotal > 0 else { return nil }
        switch status {
        case .preparingTranscripts:
            return (
                counters.videosTranscribed,
                counters.videosTotal,
                "转写进度 \(counters.videosTranscribed) / \(counters.videosTotal)"
            )
        case .extracting:
            return (
                counters.videosExtracted,
                counters.videosTotal,
                "观点提取 \(counters.videosExtracted) / \(counters.videosTotal)"
            )
        case .completed:
            return (
                counters.videosExtracted,
                counters.videosTotal,
                "已提炼 \(counters.videosExtracted) / \(counters.videosTotal)"
            )
        default:
            return nil
        }
    }
}
