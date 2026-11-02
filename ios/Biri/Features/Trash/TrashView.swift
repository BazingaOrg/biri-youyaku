import SwiftUI

struct TrashView: View {
    @Environment(AppModel.self) private var appModel
    @State private var viewModel = TrashViewModel()

    var body: some View {
        List {
            Section {
                ForEach(viewModel.items) { item in
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(item.displayTitle)
                                .font(.headline)
                                .lineLimit(2)
                            HStack(spacing: 8) {
                                if let author = item.author, !author.isEmpty { Text(author) }
                                Text(item.provider.replacingOccurrences(of: "_", with: " ").capitalized)
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        }
                        Spacer()
                        if viewModel.isMutating(item) {
                            ProgressView().controlSize(.small)
                        } else {
                            Text(item.daysLeft <= 0 ? "今天到期" : "剩 \(item.daysLeft) 天")
                                .font(.caption)
                                .foregroundStyle(item.daysLeft <= 3 ? Color.red : Color.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                    .swipeActions(edge: .leading, allowsFullSwipe: true) {
                        Button {
                            Task { await restore(item) }
                        } label: {
                            Label("恢复", systemImage: "arrow.uturn.backward")
                        }
                        .tint(.green)
                        .disabled(viewModel.isMutating(item))
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            viewModel.beginPurge(item)
                        } label: {
                            Label("彻底删除", systemImage: "trash")
                        }
                        .disabled(viewModel.isMutating(item))
                    }
                    .contextMenu {
                        Button("恢复", systemImage: "arrow.uturn.backward") {
                            Task { await restore(item) }
                        }
                        Button("彻底删除", systemImage: "trash", role: .destructive) {
                            viewModel.beginPurge(item)
                        }
                    }
                }
            } header: {
                if !viewModel.items.isEmpty { Text("\(viewModel.items.count) 篇笔记") }
            } footer: {
                Text("笔记保留 30 天。恢复后会回到资料库；彻底删除无法撤销。左滑可管理单篇笔记。")
            }

            if let message = viewModel.errorMessage, !viewModel.items.isEmpty {
                Section {
                    Label(message, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("回收站")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
        .overlay { stateOverlay }
        .overlay(alignment: .bottom) {
            if let message = viewModel.feedbackMessage {
                Text(message)
                    .font(.callout)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(.regularMaterial, in: Capsule())
                    .padding(.bottom, 20)
            }
        }
        .sheet(isPresented: purgeSheetPresented) {
            purgeSheet
                .interactiveDismissDisabled(viewModel.isPurging)
        }
    }

    @ViewBuilder
    private var stateOverlay: some View {
        if let message = viewModel.errorMessage, viewModel.items.isEmpty {
            ErrorStateView(message: message) { Task { await load() } }
        } else if viewModel.isLoading && viewModel.items.isEmpty {
            ProgressView("正在读取回收站…")
        } else if viewModel.items.isEmpty {
            ContentUnavailableView {
                Label("回收站是空的", systemImage: "trash")
            } description: {
                Text("移到回收站的笔记会在这里保留 30 天。")
            }
        }
    }

    @ViewBuilder
    private var purgeSheet: some View {
        if let item = viewModel.purgeCandidate {
            NavigationStack {
                Form {
                    Section {
                        Text("将永久删除《\(item.displayTitle)》的笔记、字幕、历史版本和导入原件。此操作无法撤销。")
                            .foregroundStyle(.red)
                    }
                    Section {
                        Text("请输入完整笔记标题以确认：")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        Text(item.title)
                            .textSelection(.enabled)
                        TextField("笔记标题", text: $viewModel.purgeConfirmation)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .disabled(viewModel.isPurging)
                    }
                    if let message = viewModel.errorMessage {
                        Section {
                            Label(message, systemImage: "exclamationmark.triangle")
                                .font(.footnote)
                                .foregroundStyle(.red)
                        }
                    }
                    Section {
                        Button(role: .destructive) {
                            Task { await confirmPurge() }
                        } label: {
                            HStack {
                                Spacer()
                                if viewModel.isPurging { ProgressView().controlSize(.small).padding(.trailing, 8) }
                                Text(viewModel.isPurging ? "正在彻底删除…" : "彻底删除")
                                Spacer()
                            }
                        }
                        .disabled(!viewModel.canConfirmPurge)
                    }
                }
                .navigationTitle("彻底删除这篇笔记？")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("取消") { viewModel.cancelPurge() }
                            .disabled(viewModel.isPurging)
                    }
                }
            }
            .presentationDetents([.medium, .large])
        }
    }

    private var purgeSheetPresented: Binding<Bool> {
        Binding(
            get: { viewModel.purgeCandidate != nil },
            set: { presented in
                if !presented { viewModel.cancelPurge() }
            }
        )
    }

    private func load() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service)
    }

    private func restore(_ item: TrashItem) async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.restore(item, using: service)
    }

    private func confirmPurge() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.confirmPurge(using: service)
    }
}
