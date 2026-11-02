import SwiftUI
import UIKit

struct ReaderView: View {
    let destination: ReaderDestination

    @Environment(AppModel.self) private var appModel
    @Environment(\.openURL) private var openURL
    @AppStorage("reader-text-size") private var textSize: ReaderTextSize = .standard
    @State private var viewModel: ReaderViewModel
    @State private var showingDirectory = false
    @State private var showCopied = false
    @State private var confirmRegenerate = false
    @State private var confirmTrash = false
    @State private var selectedHeadingID: Int?
    @State private var upDestination: UPDestination?
    @State private var regeneratedJobID: String?
    @ScaledMetric(relativeTo: .body) private var subtitleSize = 15

    init(destination: ReaderDestination) {
        self.destination = destination
        _viewModel = State(initialValue: ReaderViewModel(destination: destination))
    }

    var body: some View {
        contentView
            .background(Color(uiColor: .systemBackground))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbarContent }
            .safeAreaInset(edge: .top) {
                if viewModel.content != nil && !viewModel.didMoveToTrash {
                    Picker("阅读内容", selection: $viewModel.selectedTab) {
                        Text("笔记").tag(ReaderTab.notes)
                        Text("字幕").tag(ReaderTab.subtitles)
                    }
                    .pickerStyle(.segmented)
                    .padding(12)
                    .background(Color(uiColor: .systemBackground))
                }
            }
            .safeAreaInset(edge: .bottom) {
                if !viewModel.searchQuery.isEmpty, viewModel.content != nil, !viewModel.didMoveToTrash {
                    matchBar
                }
            }
            .task { await load() }
            .navigationDestination(item: $upDestination) { destination in
                UPCatalogView(destination: destination)
            }
            .navigationDestination(item: $regeneratedJobID) { jobID in
                JobDetailView(jobID: jobID)
            }
            .onChange(of: viewModel.regeneratedJobID) { _, jobID in
                regeneratedJobID = jobID
            }
            .sheet(isPresented: $showingDirectory) {
                directorySheet
            }
            .confirmationDialog("重新生成笔记？", isPresented: $confirmRegenerate, titleVisibility: .visible) {
                Button("重新生成") { Task { await regenerate() } }
                Button("取消", role: .cancel) {}
            } message: {
                Text("会使用已有字幕创建一个新任务，当前笔记和任务记录都会保留。")
            }
            .confirmationDialog("移到回收站？", isPresented: $confirmTrash, titleVisibility: .visible) {
                Button("移到回收站", role: .destructive) { Task { await softDelete() } }
                Button("取消", role: .cancel) {}
            } message: {
                Text("笔记会从资料库移除，之后可在回收站恢复。")
            }
            .overlay(alignment: .bottom) {
                if let toastText {
                    Text(toastText)
                        .font(.callout)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 10)
                        .background(.regularMaterial, in: Capsule())
                        .padding(.bottom, viewModel.searchQuery.isEmpty ? 20 : 76)
                        .transition(.opacity)
                }
            }
    }

    @ViewBuilder
    private var contentView: some View {
        if viewModel.didMoveToTrash {
            ContentUnavailableView {
                Label("已移到回收站", systemImage: "trash")
            } description: {
                Text("可在“设置 › 内容管理 › 回收站”恢复这篇笔记。")
            }
        } else if viewModel.isLoading && viewModel.content == nil {
            ProgressView("正在加载笔记…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let message = viewModel.errorMessage, viewModel.content == nil {
            ErrorStateView(message: message) { Task { await load() } }
        } else if let content = viewModel.content {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(content.document.displayTitle)
                                .font(.system(.title2, design: .serif, weight: .bold))
                            HStack(spacing: 12) {
                                if let author = content.document.author, !author.isEmpty {
                                    if let mid = content.document.mid {
                                        Button(author) {
                                            upDestination = UPDestination(mid: mid, author: author)
                                        }
                                        .buttonStyle(.borderless)
                                        .foregroundStyle(Color.accentColor)
                                    } else {
                                        Text(author)
                                    }
                                }
                                Text(Formatting.duration(content.document.duration))
                                Text(content.document.provider.replacingOccurrences(of: "_", with: " ").capitalized)
                            }
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)

                            if let tags = content.document.tags, !tags.isEmpty {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 6) {
                                        ForEach(tags, id: \.self) { tag in
                                            Text(tag)
                                                .font(.caption)
                                                .padding(.horizontal, 8)
                                                .padding(.vertical, 4)
                                                .background(Color(uiColor: .secondarySystemBackground), in: Capsule())
                                        }
                                    }
                                }
                            }

                            if let sourceDetail = sourceDetail(for: content.document) {
                                Text(sourceDetail)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if let message = viewModel.actionErrorMessage {
                            Label(message, systemImage: "exclamationmark.triangle")
                                .font(.footnote)
                                .foregroundStyle(.red)
                        }

                        if viewModel.selectedTab == .notes {
                            if viewModel.blocks.isEmpty {
                                ContentUnavailableView("这篇笔记还没有正文", systemImage: "doc.plaintext")
                            } else {
                                MarkdownView(
                                    blocks: viewModel.blocks,
                                    fontScale: textSize.scale,
                                    highlightQuery: viewModel.searchQuery
                                )
                            }
                        } else {
                            transcriptView
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 16)
                    .frame(maxWidth: 760)
                    .frame(maxWidth: .infinity)
                }
                .onAppear {
                    DispatchQueue.main.async { scrollToInitialPosition(proxy: proxy) }
                }
                .onChange(of: showingDirectory) { _, presented in
                    guard !presented, let id = selectedHeadingID else { return }
                    proxy.scrollTo(id, anchor: .top)
                    selectedHeadingID = nil
                }
                .onChange(of: viewModel.currentMatchID) { _, _ in
                    withAnimation { scrollToCurrentMatch(proxy: proxy) }
                }
                .onChange(of: viewModel.selectedTab) { _, _ in
                    viewModel.resetMatchNavigation()
                    DispatchQueue.main.async { scrollToCurrentMatch(proxy: proxy) }
                }
                .onChange(of: viewModel.transcriptQuery) { _, _ in
                    viewModel.resetMatchNavigation()
                }
            }
        }
    }

    private var transcriptView: some View {
        VStack(alignment: .leading, spacing: 12) {
            if viewModel.content?.cues.isEmpty == false {
                Label {
                    TextField("在字幕里搜索", text: $viewModel.transcriptQuery)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } icon: {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
            }

            if viewModel.filteredCues.isEmpty {
                ContentUnavailableView(
                    viewModel.content?.cues.isEmpty == true ? "这篇笔记没有字幕" : "没有匹配的字幕",
                    systemImage: "captions.bubble"
                )
            } else {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(viewModel.filteredCues) { cue in
                        HStack(alignment: .firstTextBaseline, spacing: 14) {
                            if let url = viewModel.sourceURL(at: cue.start) {
                                Button(cue.timeLabel) { openURL(url) }
                                    .font(.caption.monospacedDigit())
                                    .frame(minWidth: 52, minHeight: 44, alignment: .leading)
                            } else {
                                Text(cue.timeLabel)
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                                    .frame(minWidth: 52, minHeight: 44, alignment: .leading)
                            }
                            Text(SearchHighlight.attributed(cue.text, query: viewModel.searchQuery))
                                .font(.system(size: subtitleSize * textSize.scale))
                                .lineSpacing(5)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.vertical, 12)
                        .id(cue.id)
                        Divider()
                    }
                }
            }
        }
    }

    private var matchBar: some View {
        HStack(spacing: 12) {
            if viewModel.visibleMatches.isEmpty {
                Text("“\(viewModel.searchQuery)” 没有可见匹配")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                Text("“\(viewModel.searchQuery)” 第 \(viewModel.currentMatchPosition) / \(viewModel.visibleMatches.count) 处")
                    .font(.footnote.weight(.medium))
                    .lineLimit(1)
            }
            Spacer()
            Button {
                viewModel.moveMatch(by: -1)
            } label: {
                Image(systemName: "chevron.up")
                    .frame(width: 36, height: 32)
            }
            .accessibilityLabel("上一处匹配")
            Button {
                viewModel.moveMatch(by: 1)
            } label: {
                Image(systemName: "chevron.down")
                    .frame(width: 36, height: 32)
            }
            .accessibilityLabel("下一处匹配")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .disabled(viewModel.visibleMatches.isEmpty)
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                Button {
                    showingDirectory = true
                } label: {
                    Label("目录", systemImage: "list.bullet")
                }
                .disabled(viewModel.headings.isEmpty || viewModel.selectedTab != .notes)

                Picker("阅读字号", selection: $textSize) {
                    ForEach(ReaderTextSize.allCases) { size in
                        Text(size.label).tag(size)
                    }
                }

                Button {
                    UIPasteboard.general.string = viewModel.copyText
                    withAnimation { showCopied = true }
                    Task {
                        try? await Task.sleep(for: .seconds(2))
                        withAnimation { showCopied = false }
                    }
                } label: {
                    Label("复制当前内容", systemImage: "doc.on.doc")
                }
                .disabled(viewModel.content == nil || viewModel.didMoveToTrash)

                if let url = viewModel.sourceURL() {
                    Button {
                        openURL(url)
                    } label: {
                        Label("打开来源页面", systemImage: "safari")
                    }
                }

                Button {
                    confirmRegenerate = true
                } label: {
                    Label("重新生成笔记", systemImage: "arrow.clockwise")
                }
                .disabled(!viewModel.canRegenerate)

                Button(role: .destructive) {
                    confirmTrash = true
                } label: {
                    Label("移到回收站", systemImage: "trash")
                }
                .disabled(!viewModel.canSoftDelete)
            } label: {
                Image(systemName: "ellipsis.circle")
            }
            .accessibilityLabel("阅读操作")
        }
    }

    private var directorySheet: some View {
        NavigationStack {
            List(viewModel.headings) { heading in
                Button {
                    selectedHeadingID = heading.id
                    showingDirectory = false
                } label: {
                    Text(heading.text)
                        .padding(.leading, CGFloat(max(0, heading.level - 1)) * 12)
                }
            }
            .navigationTitle("本篇目录")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("完成") { showingDirectory = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private var toastText: String? {
        if showCopied { return "已复制" }
        return viewModel.feedbackMessage
    }

    private func sourceDetail(for document: DocumentMetadata) -> String? {
        var details: [String] = []
        if let bvid = document.bvid, !bvid.isEmpty { details.append("BV \(bvid)") }
        if let language = document.subtitleLanguage, !language.isEmpty {
            var subtitle = "字幕：\(language)"
            if let source = document.subtitleSource, !source.isEmpty { subtitle += " · \(source)" }
            details.append(subtitle)
        } else if let source = document.subtitleSource, !source.isEmpty {
            details.append("字幕：\(source)")
        }
        return details.isEmpty ? nil : details.joined(separator: " · ")
    }

    private func scrollToInitialPosition(proxy: ScrollViewProxy) {
        if viewModel.selectedTab == .notes, let id = viewModel.initialNoteBlockID {
            proxy.scrollTo(id, anchor: .top)
        } else if viewModel.selectedTab == .subtitles, let id = viewModel.initialCueID {
            proxy.scrollTo(id, anchor: .center)
        } else {
            scrollToCurrentMatch(proxy: proxy)
        }
    }

    private func scrollToCurrentMatch(proxy: ScrollViewProxy) {
        guard let match = viewModel.currentMatch else { return }
        if let id = match.blockID {
            proxy.scrollTo(id, anchor: .top)
        } else if let id = match.cueID {
            proxy.scrollTo(id, anchor: .center)
        }
    }

    private func load() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service)
    }

    private func regenerate() async {
        guard let service = try? appModel.makeService() else {
            viewModel.actionErrorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.regenerate(using: service)
    }

    private func softDelete() async {
        guard let service = try? appModel.makeService() else {
            viewModel.actionErrorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.softDelete(using: service)
    }
}
