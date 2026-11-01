import SwiftUI

struct LibraryView: View {
    @Environment(AppModel.self) private var appModel
    @State private var library = LibraryViewModel()
    @State private var search = SearchViewModel()
    @State private var isSearchPresented = false

    var body: some View {
        List {
            if isSearchPresented {
                searchContent
            } else {
                libraryContent
            }
        }
        .listStyle(.plain)
        .navigationTitle(isSearchPresented ? "搜索笔记" : (library.total > 0 ? "全部笔记（\(library.total)）" : "笔记"))
        .searchable(
            text: $search.query,
            isPresented: $isSearchPresented,
            placement: .navigationBarDrawer(displayMode: .always),
            prompt: "搜索标题、正文和字幕"
        )
        .searchScopes($search.scope) {
            ForEach(SearchScope.allCases) { scope in
                Text(scope.label).tag(scope)
            }
        }
        .onSubmit(of: .search) {
            isSearchPresented = true
            Task { await performSearch() }
        }
        .task { await loadLibrary() }
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

        Section {
            ForEach(library.items) { item in
                NavigationLink(value: item.destination) {
                    LibraryRow(item: item).equatable()
                }
                .onAppear {
                    if item.id == library.items.suffix(5).first?.id, library.nextCursor != nil {
                        Task { await loadMore() }
                    }
                }
            }
            if library.isLoading && !library.items.isEmpty {
                ProgressView().frame(maxWidth: .infinity)
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
        if search.isLoading && search.groups.isEmpty {
            HStack {
                ProgressView()
                Text("正在搜索…").foregroundStyle(.secondary)
            }
        }
        ForEach(search.groups) { group in
            Section {
                NavigationLink(value: group.destination()) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(group.displayTitle).font(.headline).lineLimit(2)
                        if let author = group.author, !author.isEmpty {
                            Text(author).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                ForEach(group.hits) { hit in
                    NavigationLink(value: group.destination(for: hit)) {
                        VStack(alignment: .leading, spacing: 6) {
                            Label(hit.isSubtitle ? "字幕" : "笔记", systemImage: hit.isSubtitle ? "captions.bubble" : "doc.text")
                                .font(.caption)
                                .foregroundStyle(Color.accentColor)
                            Text(hit.snippet)
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
            if let message = search.errorMessage, search.groups.isEmpty {
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
                Label("还没有笔记", systemImage: "books.vertical")
            } description: {
                Text("在网页版生成笔记后，会出现在这里。")
            }
        }
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
}

private struct LibraryRow: View, Equatable {
    let item: LibraryItem

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
            HStack(spacing: 10) {
                if let author = item.author, !author.isEmpty { Text(author) }
                Text(Formatting.duration(item.duration))
                RelativeDateText(milliseconds: item.savedAt)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
        }
        .padding(.vertical, 5)
    }
}
