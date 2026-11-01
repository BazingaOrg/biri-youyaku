import SwiftUI

struct JobsView: View {
    @Environment(AppModel.self) private var appModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var viewModel = JobsViewModel()

    var body: some View {
        List {
            Section {
                Picker("任务状态", selection: $viewModel.filter) {
                    ForEach(JobFilter.allCases) { filter in
                        Text(filter.label).tag(filter)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
            }

            ForEach(viewModel.visibleJobs) { job in
                NavigationLink(value: job.id) {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(job.displayTitle)
                            .font(.headline)
                            .lineLimit(2)
                        HStack(spacing: 8) {
                            if let author = job.author, !author.isEmpty {
                                Text(author).lineLimit(1)
                                Text("·")
                            }
                            RelativeDateText(milliseconds: job.updatedAt).fixedSize()
                            Spacer(minLength: 8)
                            JobStatusBadge(status: job.status)
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 3)
                }
            }

            if viewModel.nextCursor != nil && !viewModel.visibleJobs.isEmpty {
                LoadMoreRow(isLoading: viewModel.isLoadingMore) {
                    Task { await loadMore() }
                }
            }
            if let message = viewModel.errorMessage, !viewModel.visibleJobs.isEmpty {
                Label(message, systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("任务")
        .task(id: viewModel.filter) { await load() }
        .task(id: viewModel.pollKey) {
            guard viewModel.hasActiveJobs else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(8))
                guard !Task.isCancelled, scenePhase == .active else { continue }
                await load(quietly: true)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await load(quietly: true) } }
        }
        .refreshable { await load(quietly: true) }
        .navigationDestination(for: String.self) { jobID in
            JobDetailView(jobID: jobID)
        }
        .navigationDestination(for: ReaderDestination.self) { destination in
            ReaderView(destination: destination)
        }
        .overlay { stateOverlay }
    }

    @ViewBuilder
    private var stateOverlay: some View {
        if let message = viewModel.errorMessage, viewModel.visibleJobs.isEmpty {
            ErrorStateView(message: message) { Task { await load() } }
        } else if viewModel.isLoading && viewModel.visibleJobs.isEmpty {
            ProgressView("正在读取任务…")
        } else if viewModel.visibleJobs.isEmpty {
            ContentUnavailableView(emptyTitle, systemImage: "checklist")
        }
    }

    private var emptyTitle: String {
        switch viewModel.filter {
        case .all: "还没有任务"
        case .running: "没有进行中的任务"
        case .completed: "没有已完成任务"
        case .failed: "没有失败任务"
        }
    }

    private func load(quietly: Bool = false) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service, quietly: quietly)
    }

    private func loadMore() async {
        guard let service = try? appModel.makeService() else { return }
        await viewModel.loadMore(using: service)
    }
}

struct JobStatusBadge: View {
    let status: JobStatus

    var body: some View {
        Label(status.label, systemImage: status.systemImage)
            .font(.footnote.weight(.medium))
            .foregroundStyle(status.color)
            .labelStyle(.titleAndIcon)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(status.color.opacity(0.12), in: Capsule())
            .fixedSize()
    }
}

extension JobStatus {
    var color: Color {
        switch self {
        case .completed: .green
        case .failed: .red
        case .canceled: .secondary
        default: .accentColor
        }
    }
}
