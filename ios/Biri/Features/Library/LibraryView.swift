import SwiftUI

struct LibraryView: View {
    @Environment(AppModel.self) private var appModel
    @State private var library = LibraryViewModel()
    @State private var search = SearchViewModel()
    @State private var isSearchPresented = false
    @State private var isCreatingJob = false
    @State private var createDestination: CreateJobDestination?
    @State private var upDestination: UPDestination?
    @FocusState private var isSearchFieldFocused: Bool

    var body: some View {
        List {
            if isSearchPresented {
                searchContent
            } else {
                libraryContent
            }
        }
        .listStyle(.plain)
        .toolbar(.hidden, for: .navigationBar)
        .sheet(isPresented: $isCreatingJob) {
            NavigationStack {
                CreateJobView { destination in
                    createDestination = destination
                }
            }
        }
        .navigationDestination(item: $createDestination) { destination in
            switch destination {
            case let .job(jobID):
                JobDetailView(jobID: jobID)
            case let .reader(readerDestination):
                ReaderView(destination: readerDestination)
            }
        }
        .navigationDestination(item: $upDestination) { destination in
            UPCatalogView(destination: destination)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            searchBar
        }
        .onChange(of: isSearchFieldFocused) { _, focused in
            if focused { isSearchPresented = true }
        }
        .onAppear {
            guard !isSearchPresented else { return }
            Task { await loadLibrary() }
        }
        .onChange(of: search.scope) { _, _ in
            guard isSearchPresented, !search.submittedQuery.isEmpty else { return }
            Task { await performSearch() }
        }
        .onChange(of: isSearchPresented) { _, searching in
            if !searching { search.clear() }
        }
        .refreshable {
            if isSearchPresented {
                await performSearch()
            } else {
                await loadLibrary()
            }
        }
        .navigationDestination(for: ReaderDestination.self) { destination in
            ReaderView(destination: destination)
        }
        .navigationDestination(for: String.self) { jobID in
            JobDetailView(jobID: jobID)
        }
        .overlay { stateOverlay }
    }

    private var searchBar: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("搜索标题、正文和字幕", text: $search.query)
                        .focused($isSearchFieldFocused)
                        .submitLabel(.search)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .onSubmit {
                            isSearchPresented = true
                            isSearchFieldFocused = false
                            Task { await performSearch() }
                        }
                    if !search.query.isEmpty {
                        Button {
                            search.clear()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("清空搜索内容")
                    }
                }
                .padding(.horizontal, 10)
                .frame(minHeight: 38)
                .background(
                    Color(uiColor: .secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 10)
                )

                if isSearchPresented {
                    Button("取消") {
                        isSearchFieldFocused = false
                        isSearchPresented = false
                    }
                    .buttonStyle(.borderless)
                } else {
                    Button {
                        isCreatingJob = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline)
                            .frame(width: 38, height: 38)
                            .background(Color.accentColor.opacity(0.12), in: Circle())
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("生成笔记")
                }
            }

            if isSearchPresented {
                Picker("搜索范围", selection: $search.scope) {
                    ForEach(SearchScope.allCases) { scope in
                        Text(scope.label).tag(scope)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            } else if library.total > 0 {
                HStack {
                    Text("全部笔记")
                    Spacer()
                    Text("\(library.total) 篇")
                        .foregroundStyle(.secondary)
                }
                .font(.subheadline.weight(.medium))
                .padding(.horizontal, 4)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
    }

    @ViewBuilder
    private var libraryContent: some View {
        if let job = library.activeJob {
            Section("正在生成") {
                NavigationLink(value: job.id) {
                    Label {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(job.displayTitle).lineLimit(2)
                            Text(job.status.label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "clock.fill").foregroundStyle(Color.accentColor)
                    }
                }
            }
        }

        if library.hasFilters {
            Section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        if library.selectedUP != nil {
                            filterChip(title: library.selectedUPName ?? "UP 主", systemImage: "person.crop.circle") {
                                Task { await removeUPFilter() }
                            }
                        }
                        if let tag = library.selectedTag {
                            filterChip(title: tag, systemImage: "tag") {
                                Task { await removeTagFilter() }
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
            } footer: {
                Text("点按条件旁的叉号移除筛选。")
            }
        }

        Section {
            ForEach(library.items) { item in
                NavigationLink(value: item.destination) {
                    LibraryRow(item: item, onUP: {
                        guard let mid = item.mid, let author = item.author, !author.isEmpty else { return }
                        upDestination = UPDestination(mid: mid, author: author)
                    }, onTag: { tag in
                        Task { await filterByTag(tag) }
                    })
                    .equatable()
                }
                .listRowSeparator(item.id == library.items.first?.id ? .hidden : .automatic, edges: .top)
                .contextMenu {
                    if let mid = item.mid {
                        Button {
                            Task { await filterByUP(mid: mid, name: item.author) }
                        } label: {
                            Label("只看这个 UP 主的笔记", systemImage: "line.3.horizontal.decrease.circle")
                        }
                    }
                }
                .onAppear {
                    if item.id == library.items.suffix(5).first?.id, library.nextCursor != nil {
                        Task { await loadMore() }
                    }
                }
            }
            if library.isLoading && !library.items.isEmpty {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity)
            }
            if library.nextCursor != nil {
                LoadMoreRow(isLoading: library.isLoadingMore) {
                    Task { await loadMore() }
                }
            }
            if let message = library.errorMessage, !library.items.isEmpty {
                Label(message, systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var searchContent: some View {
        ForEach(search.groups) { group in
            Section {
                NavigationLink(value: group.destination()) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(SearchHighlight.attributed(group.displayTitle, query: search.submittedQuery))
                            .font(.headline)
                            .lineLimit(2)
                        if let author = group.author, !author.isEmpty {
                            if let mid = group.mid {
                                Button {
                                    upDestination = UPDestination(mid: mid, author: author)
                                } label: {
                                    Text(SearchHighlight.attributed(author, query: search.submittedQuery))
                                        .font(.caption)
                                        .foregroundStyle(Color.accentColor)
                                }
                                .buttonStyle(.borderless)
                            } else {
                                Text(SearchHighlight.attributed(author, query: search.submittedQuery))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if !matchReasons(for: group).isEmpty {
                            Text("匹配：" + matchReasons(for: group).joined(separator: "、"))
                                .font(.caption)
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                }
                ForEach(group.hits) { hit in
                    NavigationLink(value: group.destination(for: hit, query: search.submittedQuery)) {
                        VStack(alignment: .leading, spacing: 6) {
                            Label(hitLabel(hit), systemImage: hit.isSubtitle ? "captions.bubble" : "doc.text")
                                .font(.caption)
                                .foregroundStyle(Color.accentColor)
                            Text(SearchHighlight.attributed(hit.snippet, query: search.submittedQuery))
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .lineLimit(3)
                        }
                    }
                }
            }
        }
        if search.nextCursor != nil {
            LoadMoreRow(isLoading: search.isLoadingMore, title: "加载更多结果") {
                Task {
                    guard let service = try? appModel.makeService() else { return }
                    await search.loadMore(using: service)
                }
            }
        }
        if search.partial.contains("subs") {
            Text("暂时无法搜索字幕，当前结果可能不完整。")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        if let message = search.errorMessage, !search.groups.isEmpty {
            Label(message, systemImage: "exclamationmark.triangle")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var stateOverlay: some View {
        if isSearchPresented {
            if search.isLoading && search.groups.isEmpty {
                ProgressView("正在搜索…")
            } else if let message = search.errorMessage, search.groups.isEmpty {
                ErrorStateView(message: message) {
                    Task { await performSearch() }
                }
            } else if !search.isLoading,
                      !search.submittedQuery.isEmpty,
                      search.groups.isEmpty {
                ContentUnavailableView.search(text: search.submittedQuery)
            }
        } else if let message = library.errorMessage, library.items.isEmpty {
            ErrorStateView(message: message) { Task { await loadLibrary() } }
        } else if library.isLoading && library.items.isEmpty {
            ProgressView("正在读取笔记…")
        } else if library.items.isEmpty {
            ContentUnavailableView {
                Label(library.hasFilters ? "没有符合筛选的笔记" : "还没有笔记", systemImage: "books.vertical")
            } description: {
                Text(library.hasFilters ? "移除 UP 主或标签条件后再看看。" : "点按搜索框右侧的“＋”，粘贴视频链接创建第一篇笔记。")
            }
        }
    }

    private func filterChip(title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .lineLimit(1)
            Image(systemName: "xmark.circle.fill")
                .accessibilityHidden(true)
        }
        .buttonStyle(.borderless)
        .font(.caption)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Color(uiColor: .secondarySystemBackground), in: Capsule())
        .accessibilityLabel("移除筛选：\(title)")
    }

    private func matchReasons(for group: SearchGroup) -> [String] {
        guard let match = group.match else { return [] }
        var reasons: [String] = []
        if match.title { reasons.append("标题") }
        if match.author { reasons.append("作者") }
        if match.bvid { reasons.append(group.bvid.map { "BV \($0)" } ?? "BV") }
        if !match.tags.isEmpty { reasons.append("标签：" + match.tags.joined(separator: "、")) }
        return reasons
    }

    private func hitLabel(_ hit: SearchHit) -> String {
        if hit.isSubtitle {
            return "字幕 · \(Formatting.duration(hit.startSec))"
        }
        if let heading = hit.headingPath?.split(separator: ">").last?.trimmingCharacters(in: .whitespaces),
           !heading.isEmpty {
            return "笔记 · \(heading)"
        }
        return "笔记"
    }

    private func performSearch() async {
        guard let service = try? appModel.makeService() else {
            search.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await search.search(using: service)
    }

    private func loadLibrary() async {
        guard let service = try? appModel.makeService() else {
            library.errorMessage = APIError.notConfigured.localizedDescription
            return
        }
        await library.load(using: service)
    }

    private func loadMore() async {
        guard let service = try? appModel.makeService() else { return }
        await library.loadMore(using: service)
    }

    private func filterByTag(_ tag: String) async {
        guard let service = try? appModel.makeService() else { return }
        await library.filterByTag(tag, using: service)
    }

    private func filterByUP(mid: Int, name: String?) async {
        guard let service = try? appModel.makeService() else { return }
        await library.filterByUP(mid: mid, name: name, using: service)
    }

    private func removeUPFilter() async {
        guard let service = try? appModel.makeService() else { return }
        await library.removeUPFilter(using: service)
    }

    private func removeTagFilter() async {
        guard let service = try? appModel.makeService() else { return }
        await library.removeTagFilter(using: service)
    }
}

private struct LibraryRow: View, Equatable {
    let item: LibraryItem
    let onUP: () -> Void
    let onTag: (String) -> Void

    static func == (lhs: LibraryRow, rhs: LibraryRow) -> Bool {
        lhs.item == rhs.item
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(item.displayTitle)
                .font(.headline)
                .lineLimit(2)
            if let tldr = item.tldr, !tldr.isEmpty {
                Text(tldr)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if !item.tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(item.tags, id: \.self) { tag in
                            Button(tag) { onTag(tag) }
                                .buttonStyle(.borderless)
                                .font(.caption)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Color(uiColor: .secondarySystemBackground), in: Capsule())
                        }
                    }
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                if let author = item.author, !author.isEmpty {
                    if item.mid != nil {
                        Button(author, action: onUP)
                            .buttonStyle(.borderless)
                            .foregroundStyle(Color.accentColor)
                            .lineLimit(1)
                    } else {
                        Text(author)
                            .lineLimit(1)
                    }
                }
                HStack(spacing: 10) {
                    Text(item.provider.replacingOccurrences(of: "_", with: " ").capitalized)
                    Text(Formatting.duration(item.duration))
                    Spacer(minLength: 8)
                    Text(Formatting.date(item.savedAt))
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 5)
    }
}
