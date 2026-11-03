import SwiftUI
import UIKit

struct JobsView: View {
    @Environment(AppModel.self) private var appModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var viewModel = JobsViewModel()
    @State private var deletionConfirmation: JobsDeletionConfirmation?

    var body: some View {
        List {
            ForEach(viewModel.visibleJobs) { job in
                row(for: job)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if !job.status.isActive, !viewModel.isSelecting {
                            Button("删除", systemImage: "trash", role: .destructive) {
                                deletionConfirmation = .job(job)
                            }
                        }
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
        .toolbar(.hidden, for: .navigationBar)
        .safeAreaInset(edge: .top, spacing: 0) {
            Picker("任务状态", selection: $viewModel.filter) {
                ForEach(JobFilter.allCases) { filter in
                    Text(filter.label).tag(filter)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.regularMaterial)
        }
        .background {
            ThreeFingerTapGesture {
                guard !viewModel.isDeleting else { return }
                viewModel.toggleSelection()
            }
        }
        .safeAreaInset(edge: .bottom) {
            if viewModel.isSelecting {
                HStack(spacing: 16) {
                    Text("已选择 \(viewModel.selectedCount) 项")
                        .font(.subheadline)
                    Spacer()
                    Button("完成") { viewModel.exitSelection() }
                        .disabled(viewModel.isDeleting)
                    Button("删除任务记录", role: .destructive) {
                        deletionConfirmation = .selected
                    }
                    .disabled(!viewModel.canDeleteSelection)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(.bar)
            }
        }
        .confirmationDialog(
            "删除任务记录？",
            item: $deletionConfirmation,
            titleVisibility: .visible
        ) { confirmation in
            switch confirmation {
            case .selected:
                Button("删除 \(viewModel.selectedCount) 条任务记录", role: .destructive) {
                    Task { await deleteSelected() }
                }
            case let .job(job):
                Button("删除任务记录", role: .destructive) {
                    Task { await delete(job) }
                }
            }
        } message: { confirmation in
            switch confirmation {
            case .selected:
                Text("将删除选中的任务记录。已同步到资料库的笔记会保留；仅存在于旧任务中的笔记也会一并删除。此操作无法撤销。")
            case let .job(job):
                Text("将删除“\(job.displayTitle)”的任务记录。已同步到资料库的笔记会保留；仅存在于旧任务中的笔记也会一并删除。此操作无法撤销。")
            }
        }
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
    private func row(for job: Job) -> some View {
        if viewModel.isSelecting {
            Button {
                viewModel.toggleSelection(for: job)
            } label: {
                JobRow(
                    job: job,
                    isSelected: viewModel.selectedIDs.contains(job.id),
                    showsSelection: true
                )
            }
            .buttonStyle(.plain)
            .disabled(viewModel.isDeleting)
            .accessibilityHint(job.status.isActive ? "进行中的任务需先取消，不能删除" : "切换任务选择")
        } else {
            NavigationLink(value: job.id) {
                JobRow(job: job, isSelected: false, showsSelection: false)
            }
            .accessibilityAction(named: "选择任务") {
                viewModel.toggleSelection()
                viewModel.toggleSelection(for: job)
            }
        }
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

    private func deleteSelected() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.deleteSelected(using: service)
    }

    private func delete(_ job: Job) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.delete(job: job, using: service)
    }
}

private enum JobsDeletionConfirmation: Identifiable {
    case selected
    case job(Job)

    var id: String {
        switch self {
        case .selected: "selected"
        case let .job(job): job.id
        }
    }
}

private struct JobRow: View {
    let job: Job
    let isSelected: Bool
    let showsSelection: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            if showsSelection {
                Image(systemName: selectionImage)
                    .font(.title3)
                    .foregroundStyle(job.status.isActive ? Color.secondary : Color.accentColor)
                    .frame(width: 24)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 9) {
                Text(job.displayTitle)
                    .font(.headline)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                HStack(spacing: 8) {
                    if let author = job.author, !author.isEmpty {
                        Text(author).lineLimit(1)
                        Text("·")
                    }
                    Text(Formatting.date(job.createdAt)).fixedSize()
                    Spacer(minLength: 8)
                    JobStatusBadge(status: job.status)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 3)
        .contentShape(Rectangle())
    }

    private var selectionImage: String {
        if job.status.isActive { return "circle.slash" }
        return isSelected ? "checkmark.circle.fill" : "circle"
    }
}

struct JobStatusBadge: View {
    let status: JobStatus

    var body: some View {
        Image(systemName: status.systemImage)
            .font(.title3)
            .foregroundStyle(status.color)
            .frame(width: 28, height: 28)
            .accessibilityLabel(status.label)
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

private struct ThreeFingerTapGesture: UIViewRepresentable {
    let action: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(action: action)
    }

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        context.coordinator.action = action
        guard let hostView = uiView.superview, context.coordinator.hostView !== hostView else { return }
        context.coordinator.detach()

        let recognizer = UITapGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handleTap)
        )
        recognizer.numberOfTouchesRequired = 3
        recognizer.numberOfTapsRequired = 1
        recognizer.cancelsTouchesInView = false
        recognizer.delegate = context.coordinator
        hostView.addGestureRecognizer(recognizer)
        context.coordinator.hostView = hostView
        context.coordinator.recognizer = recognizer
    }

    static func dismantleUIView(_ uiView: UIView, coordinator: Coordinator) {
        coordinator.detach()
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var action: () -> Void
        weak var hostView: UIView?
        var recognizer: UITapGestureRecognizer?

        init(action: @escaping () -> Void) {
            self.action = action
        }

        @objc func handleTap() {
            action()
        }

        func detach() {
            if let hostView, let recognizer {
                hostView.removeGestureRecognizer(recognizer)
            }
            hostView = nil
            recognizer = nil
        }

        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer
        ) -> Bool {
            true
        }
    }
}
