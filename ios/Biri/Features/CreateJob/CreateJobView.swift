import SwiftUI

struct CreateJobView: View {
    @Environment(AppModel.self) private var appModel
    @Environment(\.dismiss) private var dismiss
    @State private var viewModel = CreateJobViewModel()

    let onNavigate: (CreateJobDestination) -> Void

    init(onNavigate: @escaping (CreateJobDestination) -> Void) {
        self.onNavigate = onNavigate
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("支持 Bilibili 和 YouTube，也可以直接粘贴完整分享文案。")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 12) {
                    Text("视频链接")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        Image(systemName: "link")
                            .foregroundStyle(Color.accentColor)
                        TextField(
                            "粘贴视频链接或分享文案",
                            text: Binding(
                                get: { viewModel.url },
                                set: { viewModel.updateURL($0) }
                            )
                        )
                            .textFieldStyle(.plain)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .submitLabel(.go)
                            .onSubmit { resolve() }
                            .disabled(viewModel.isSubmitting)
                        if viewModel.isResolving && viewModel.resolution != nil {
                            ProgressView().controlSize(.small)
                        }
                        PasteButton(payloadType: String.self) { values in
                            guard let value = values.first else { return }
                            viewModel.updateURL(value)
                            resolve()
                        }
                        .labelStyle(.iconOnly)
                        .buttonStyle(.borderless)
                        .frame(width: 36, height: 36)
                        .accessibilityLabel("粘贴链接")
                    }
                    .padding(.horizontal, 13)
                    .frame(minHeight: 52)
                    .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))

                    Button(action: resolve) {
                        HStack(spacing: 8) {
                            if viewModel.isResolving {
                                ProgressView().controlSize(.small)
                            } else {
                                Image(systemName: "magnifyingglass")
                            }
                            Text(viewModel.isResolving ? "正在识别…" : "识别链接")
                        }
                        .frame(maxWidth: .infinity, minHeight: 24)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!viewModel.canResolve)
                }

                if let message = viewModel.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                }

                if let resolution = viewModel.resolution {
                    sourceCard(resolution)
                    resolutionActions(resolution)
                }
            }
            .padding(20)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("生成笔记")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("关闭") { dismiss() }
                    .disabled(viewModel.isSubmitting)
            }
        }
        .onChange(of: viewModel.destination) { _, destination in
            guard let destination else { return }
            viewModel.clearDestination()
            dismiss()
            onNavigate(destination)
        }
        .interactiveDismissDisabled(viewModel.isSubmitting)
    }

    @ViewBuilder
    private func sourceCard(_ resolution: SourceResolution) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: resolution.existing != nil ? "book.fill" : "play.rectangle.fill")
                .font(.title3)
                .foregroundStyle(Color.accentColor)
                .frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 5) {
                if let existing = resolution.existing {
                    Text(existing.title)
                        .font(.headline)
                    Text("已有笔记，可直接阅读")
                        .font(.caption)
                        .foregroundStyle(.green)
                    if resolution.activeJobId != nil {
                        Text("这个链接还有进行中的任务，无需重复创建")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else if let trashed = resolution.trashed {
                    Text(trashed.title)
                        .font(.headline)
                    if let daysLeft = trashed.daysLeft {
                        Text("笔记在回收站中，还可恢复 \(daysLeft) 天")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    } else {
                        Text("笔记在回收站中，可以恢复")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                } else if resolution.activeJobId != nil {
                    Text("这个链接已有进行中的任务")
                        .font(.headline)
                    Text("无需重复创建，可直接查看实时进度")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("已识别 \(providerLabel(resolution.provider)) 视频")
                        .font(.headline)
                    Text("没有找到已有笔记或进行中的任务")
                        .font(.caption)
                        .foregroundStyle(.green)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private func resolutionActions(_ resolution: SourceResolution) -> some View {
        if resolution.existing == nil, resolution.trashed == nil, resolution.activeJobId == nil {
            emailToggle
            actionButton("生成笔记", systemImage: "sparkles", prominent: true) {
                await create(dedupe: true)
            }
        } else if resolution.existing != nil {
            actionButton("阅读已有笔记", systemImage: "book.fill", prominent: true) {
                viewModel.openExisting()
            }
            if resolution.activeJobId != nil {
                actionButton("查看进行中的任务", systemImage: "clock.fill", prominent: false) {
                    viewModel.openActiveJob()
                }
            } else {
                emailToggle
                actionButton("仍要重新生成", systemImage: "arrow.clockwise", prominent: false) {
                    await create(dedupe: false)
                }
            }
        } else if resolution.trashed != nil {
            actionButton("恢复并阅读", systemImage: "arrow.uturn.backward", prominent: true) {
                await restore()
            }
            if resolution.activeJobId != nil {
                actionButton("查看进行中的任务", systemImage: "clock.fill", prominent: false) {
                    viewModel.openActiveJob()
                }
            }
        } else {
            actionButton("查看进行中的任务", systemImage: "clock.fill", prominent: true) {
                viewModel.openActiveJob()
            }
        }
    }

    private var emailToggle: some View {
        Toggle(isOn: $viewModel.emailEnabled) {
            VStack(alignment: .leading, spacing: 3) {
                Text("完成后发送邮件")
                Text("收件人使用服务器配置")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .disabled(viewModel.isSubmitting)
    }

    @ViewBuilder
    private func actionButton(
        _ title: String,
        systemImage: String,
        prominent: Bool,
        action: @escaping () async -> Void
    ) -> some View {
        let button = Button {
            Task { await action() }
        } label: {
            HStack(spacing: 8) {
                if viewModel.isSubmitting {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: systemImage)
                }
                Text(title)
            }
            .frame(maxWidth: .infinity, minHeight: 24)
        }
        .controlSize(.large)
        .disabled(viewModel.isSubmitting || viewModel.isResolving)

        if prominent {
            button.buttonStyle(.borderedProminent)
        } else {
            button.buttonStyle(.bordered)
        }
    }

    private func providerLabel(_ provider: String) -> String {
        switch provider.lowercased() {
        case "bilibili": "Bilibili"
        case "youtube": "YouTube"
        default: provider
        }
    }

    private func resolve() {
        guard viewModel.canResolve else { return }
        Task {
            guard let service = try? appModel.makeService() else {
                viewModel.errorMessage = APIError.notConfigured.localizedDescription
                return
            }
            await viewModel.resolve(using: service)
        }
    }

    private func create(dedupe: Bool) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.create(using: service, dedupe: dedupe)
    }

    private func restore() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.restoreTrashed(using: service)
    }
}
