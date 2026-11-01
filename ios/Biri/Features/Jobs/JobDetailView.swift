import SwiftUI

struct JobDetailView: View {
    let jobID: String

    @Environment(AppModel.self) private var appModel
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) private var openURL
    @State private var viewModel: JobDetailViewModel

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
                ErrorStateView(message: message) { Task { await load() } }
            } else if let job = viewModel.job {
                detail(job)
            }
        }
        .navigationTitle("任务详情")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .task(id: viewModel.job?.status.isActive == true) {
            guard viewModel.job?.status.isActive == true else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled, scenePhase == .active else { continue }
                await load(quietly: true)
            }
        }
        .navigationDestination(for: ReaderDestination.self) { destination in
            ReaderView(destination: destination)
        }
    }

    private func detail(_ job: Job) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 12) {
                    Text(job.displayTitle)
                        .font(.title2.weight(.semibold))
                        .multilineTextAlignment(.center)
                    Label(job.status.label, systemImage: job.status.systemImage)
                        .font(.headline)
                        .foregroundStyle(job.status.color)
                    if job.status.isActive {
                        ProgressView()
                            .controlSize(.small)
                        Text("服务器正在处理，进度会自动更新")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 20)

                if let message = job.errorMessage, !message.isEmpty {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                }

                if let destination = job.destination {
                    NavigationLink(value: destination) {
                        Label("阅读笔记", systemImage: "book.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }

                VStack(spacing: 0) {
                    DetailRow(title: "作者", value: job.author?.isEmpty == false ? job.author! : "未知")
                    Divider().padding(.leading, 16)
                    DetailRow(title: "创建时间", value: Formatting.date(job.createdAt))
                    Divider().padding(.leading, 16)
                    DetailRow(title: "更新时间", value: Formatting.date(job.updatedAt))
                    if let stage = job.errorStage, !stage.isEmpty {
                        Divider().padding(.leading, 16)
                        DetailRow(title: "失败阶段", value: stage)
                    }
                }
                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))

                if let url = URL(string: job.url), ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                    Button {
                        openURL(url)
                    } label: {
                        Label("打开来源页面", systemImage: "safari")
                    }
                }

                Text("创建、取消、重试和重新生成请在网页版操作。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .padding(20)
            .frame(maxWidth: 700)
            .frame(maxWidth: .infinity)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .refreshable { await load(quietly: true) }
    }

    private func load(quietly: Bool = false) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service, quietly: quietly)
    }
}

private struct DetailRow: View {
    let title: String
    let value: String

    var body: some View {
        HStack(alignment: .top) {
            Text(title).foregroundStyle(.secondary)
            Spacer(minLength: 20)
            Text(value).multilineTextAlignment(.trailing)
        }
        .padding(16)
    }
}
