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
                if viewModel.content != nil {
                    Picker("阅读内容", selection: $viewModel.selectedTab) {
                        Text("笔记").tag(ReaderTab.notes)
                        Text("字幕").tag(ReaderTab.subtitles)
                    }
                    .pickerStyle(.segmented)
                    .padding(12)
                    .background(Color(uiColor: .systemBackground))
                }
            }
            .task { await load() }
            .sheet(isPresented: $showingDirectory) {
                directorySheet
            }
            .overlay(alignment: .bottom) {
                if showCopied {
                    Text("已复制")
                        .font(.callout)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 10)
                        .background(.regularMaterial, in: Capsule())
                        .padding(.bottom, 20)
                        .transition(.opacity)
                }
            }
    }

    @ViewBuilder
    private var contentView: some View {
        if viewModel.isLoading && viewModel.content == nil {
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
                                    Text(author)
                                }
                                Text(Formatting.duration(content.document.duration))
                            }
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        }

                        if viewModel.selectedTab == .notes {
                            if viewModel.blocks.isEmpty {
                                ContentUnavailableView("这篇笔记还没有正文", systemImage: "doc.plaintext")
                            } else {
                                MarkdownView(blocks: viewModel.blocks, fontScale: textSize.scale)
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
                .onChange(of: showingDirectory) { _, presented in
                    guard !presented, let id = selectedHeadingID else { return }
                    proxy.scrollTo(id, anchor: .top)
                    selectedHeadingID = nil
                }
            }
        }
    }

    @State private var selectedHeadingID: Int?

    private var transcriptView: some View {
        VStack(alignment: .leading, spacing: 12) {
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
                            Text(cue.text)
                                .font(.system(size: subtitleSize * textSize.scale))
                                .lineSpacing(5)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.vertical, 12)
                        Divider()
                    }
                }
            }
        }
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

                Picker("正文字号", selection: $textSize) {
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
                .disabled(viewModel.content == nil)

                if let url = viewModel.sourceURL() {
                    Button {
                        openURL(url)
                    } label: {
                        Label("打开来源页面", systemImage: "safari")
                    }
                }
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

    private func load() async {
        guard let service = try? appModel.makeService() else {
            viewModel.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await viewModel.load(using: service)
    }
}
