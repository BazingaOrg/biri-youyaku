import SwiftUI

struct UPCatalogView: View {
    let destination: UPDestination

    @Environment(AppModel.self) private var appModel
    @State private var viewModel: UPCatalogViewModel
    @State private var selectedJobID: String?
    @State private var readerDestination: ReaderDestination?

    init(destination: UPDestination) {
        self.destination = destination
        _viewModel = State(initialValue: UPCatalogViewModel(mid: destination.mid, author: destination.author))
    }

    var body: some View {
        List {
            authorSection
            controlsSection
            videosSection
        }
        .listStyle(.plain)
        .navigationTitle(viewModel.author)
        .navigationBarTitleDisplayMode(.inline)
        .searchable(
            text: $viewModel.query,
            placement: .navigationBarDrawer(displayMode: .always),
            prompt: "搜索这个 UP 主的视频"
        )
        .onSubmit(of: .search) { Task { await load() } }
        .task { await load() }
        .onChange(of: viewModel.order) { _, _ in Task { await load() } }
        .refreshable { await load(quietly: true) }
        .navigationDestination(item: $selectedJobID) { jobID in
            JobDetailView(jobID: jobID)
        }
        .navigationDestination(item: $readerDestination) { destination in
            ReaderView(destination: destination)
        }
        .overlay { stateOverlay }
    }

    private var authorSection: some View {
        Section {
            authorHeader
            NavigationLink {
                DistillView(mid: viewModel.mid, author: viewModel.author)
            } label: {
                Label {
                    HStack {
                        Text("蒸馏语料")
                        Spacer()
                        Text("实验功能")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "square.stack.3d.up")
                }
            }
        }
        .listRowSeparator(.hidden)
    }

    private var controlsSection: some View {
        Section {
            Picker("排序方式", selection: $viewModel.order) {
                Text("按发布时间").tag(UPCatalogOrder.pubdate)
                Text("按播放量").tag(UPCatalogOrder.click)
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Picker("生成状态", selection: $viewModel.filter) {
                ForEach(UPCatalogFilter.allCases) { filter in
                    Text(filter.label).tag(filter)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            if viewModel.filter != .all {
                Text("状态筛选只作用于已加载的 \(viewModel.videos.count) 个视频。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .listRowSeparator(.hidden)
    }

    private var videosSection: some View {
        Section {
            ForEach(viewModel.visibleVideos) { video in
                UPVideoRow(
                    video: video,
                    isMutating: viewModel.mutatingVideoIDs.contains(video.id),
                    actionTitle: actionTitle(for: video),
                    action: { performAction(for: video) }
                )
                .onAppear {
                    guard video.id == viewModel.visibleVideos.suffix(5).first?.id else { return }
                    Task { await loadMore() }
                }
            }

            if viewModel.visibleVideos.isEmpty, !viewModel.videos.isEmpty, !viewModel.isLoading {
                ContentUnavailableView(
                    "已加载视频中没有符合条件的项目",
                    systemImage: "line.3.horizontal.decrease.circle"
                )
                .listRowSeparator(.hidden)
            }

            if viewModel.hasMore {
                LoadMoreRow(isLoading: viewModel.isLoadingMore) {
                    Task { await loadMore() }
                }
            }

            if let message = viewModel.errorMessage, !viewModel.videos.isEmpty {
                Label(message, systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        } header: {
            if !viewModel.submittedKeyword.isEmpty {
                Text("搜索“\(viewModel.submittedKeyword)” · \(viewModel.total) 个结果")
            } else {
                Text("投稿视频")
            }
        }
    }

    private var authorHeader: some View {
        HStack(spacing: 14) {
            Text(viewModel.author.prefix(1))
                .font(.title2.weight(.semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 52, height: 52)
                .background(Color.accentColor.opacity(0.12), in: Circle())
            VStack(alignment: .leading, spacing: 5) {
                Text(viewModel.author)
                    .font(.title3.weight(.semibold))
                    .lineLimit(2)
                Text("\(viewModel.total) 个视频 · 已加载 \(viewModel.videos.count) 个，其中 \(viewModel.loadedSummarizedCount) 篇已生成")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var stateOverlay: some View {
        if let message = viewModel.errorMessage, viewModel.videos.isEmpty {
            ErrorStateView(message: message) { Task { await load() } }
        } else if viewModel.isLoading, viewModel.videos.isEmpty {
            ProgressView("正在读取投稿…")
        } else if viewModel.videos.isEmpty, !viewModel.isLoading {
            ContentUnavailableView(
                viewModel.submittedKeyword.isEmpty ? "还没有投稿视频" : "没有找到匹配的视频",
                systemImage: "play.rectangle"
            )
        }
    }

    private func actionTitle(for video: UPVideo) -> String {
        if viewModel.mutatingVideoIDs.contains(video.id) { return "处理中" }
        if video.readerDestination != nil { return "阅读" }
        if video.activeJobID != nil { return "进度" }
        if video.status == .failed, video.jobId != nil { return "重试" }
        return "生成"
    }

    private func performAction(for video: UPVideo) {
        if let destination = video.readerDestination {
            readerDestination = destination
        } else if let jobID = video.activeJobID {
            selectedJobID = jobID
        } else {
            Task {
                guard let service = currentService(),
                      let jobID = await viewModel.generateOrRetry(video, using: service) else { return }
                selectedJobID = jobID
            }
        }
    }

    private func load(quietly: Bool = false) async {
        guard let service = currentService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service, quietly: quietly)
    }

    private func loadMore() async {
        guard let service = currentService() else { return }
        await viewModel.loadMore(using: service)
    }

    private func currentService() -> (any UPServicing & SourceServicing & JobMutationServicing)? {
        try? appModel.makeService()
    }
}

private struct UPVideoRow: View {
    let video: UPVideo
    let isMutating: Bool
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            thumbnail
                .frame(width: 92, height: 58)
                .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 6) {
                Text(video.title)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(3)
                HStack(spacing: 6) {
                    Text(Formatting.duration(Double(video.duration)))
                    Text("·")
                    Text(Date(timeIntervalSince1970: TimeInterval(video.pubdate)), style: .date)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                if let status = video.status {
                    Label(status.label, systemImage: status.systemImage)
                        .font(.caption)
                        .foregroundStyle(status.color)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button(action: action) {
                HStack(spacing: 5) {
                    if isMutating {
                        ProgressView().controlSize(.small)
                    }
                    Text(actionTitle)
                }
            }
                .font(.caption.weight(.semibold))
                .buttonStyle(.bordered)
                .disabled(isMutating)
                .frame(minWidth: 52)
        }
        .padding(.vertical, 5)
    }

    @ViewBuilder
    private var thumbnail: some View {
        if let url = URL(string: video.cover), !video.cover.isEmpty {
            AsyncImage(url: url) { phase in
                switch phase {
                case let .success(image):
                    image.resizable().scaledToFill()
                default:
                    placeholder
                }
            }
        } else {
            placeholder
        }
    }

    private var placeholder: some View {
        ZStack {
            Color(uiColor: .secondarySystemBackground)
            Image(systemName: "play.rectangle")
                .foregroundStyle(.secondary)
        }
    }
}
