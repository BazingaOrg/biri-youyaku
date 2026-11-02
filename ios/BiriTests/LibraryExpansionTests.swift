import XCTest
@testable import Biri

@MainActor
final class LibraryExpansionTests: XCTestCase {
    func testFilteredPaginationKeepsUPAndTagOnEveryRequest() async {
        let service = LibraryControlledService()
        service.firstPages = [
            LibraryPage(items: [makeItem("one")], nextCursor: CursorValue("next"), total: 2),
            LibraryPage(items: [makeItem("two")], nextCursor: nil, total: 2)
        ]
        let viewModel = LibraryViewModel()

        await viewModel.filterByTag("机器学习", using: service)
        await viewModel.filterByUP(mid: 42, name: "作者", using: service)

        XCTAssertEqual(service.requests.map(\.up), [nil, "42"])
        XCTAssertEqual(service.requests.map(\.tag), ["机器学习", "机器学习"])
    }

    func testLoadMoreUsesSameFiltersAndCursor() async {
        let service = LibraryControlledService()
        service.firstPages = [
            LibraryPage(items: [], nextCursor: CursorValue("old"), total: 2),
            LibraryPage(items: [makeItem("one")], nextCursor: CursorValue("next"), total: 2)
        ]
        service.nextPage = LibraryPage(items: [makeItem("two")], nextCursor: nil, total: 2)
        let viewModel = LibraryViewModel()
        await viewModel.filterByUP(mid: 42, name: "作者", using: service)
        await viewModel.filterByTag("机器学习", using: service)

        await viewModel.loadMore(using: service)

        XCTAssertEqual(viewModel.items.map(\.id), ["one", "two"])
        XCTAssertEqual(service.requests.last?.cursor, CursorValue("next"))
        XCTAssertEqual(service.requests.last?.up, "42")
        XCTAssertEqual(service.requests.last?.tag, "机器学习")
        XCTAssertNil(viewModel.nextCursor)
    }

    func testRemovingTagReloadsWithoutTagButKeepsUP() async {
        let service = LibraryControlledService()
        service.firstPages = [
            LibraryPage(items: [], nextCursor: nil, total: 0),
            LibraryPage(items: [], nextCursor: nil, total: 0),
            LibraryPage(items: [makeItem("kept")], nextCursor: nil, total: 1)
        ]
        let viewModel = LibraryViewModel()
        await viewModel.filterByUP(mid: 42, name: "作者", using: service)
        await viewModel.filterByTag("机器学习", using: service)

        await viewModel.removeTagFilter(using: service)

        XCTAssertEqual(viewModel.selectedUP, "42")
        XCTAssertNil(viewModel.selectedTag)
        XCTAssertEqual(service.requests.last?.up, "42")
        XCTAssertNil(service.requests.last?.tag)
        XCTAssertEqual(viewModel.items.map(\.id), ["kept"])
    }

    func testLateFilteredResponseCannotReplaceNewFilter() async {
        let service = LibraryControlledService()
        let newItem = makeItem("new")
        service.firstPages = [LibraryPage(items: [newItem], nextCursor: nil, total: 1)]
        service.suspendFirstPage = true
        let viewModel = LibraryViewModel()

        let oldLoad = Task { await viewModel.filterByTag("旧标签", using: service) }
        guard await waitUntil({ service.firstContinuation != nil }) else {
            await oldLoad.value
            return XCTFail("The old filter did not suspend")
        }
        await viewModel.filterByUP(mid: 42, name: "新 UP", using: service)
        service.firstContinuation?.resume(
            returning: LibraryPage(items: [makeItem("stale")], nextCursor: CursorValue("stale"), total: 1)
        )
        await oldLoad.value

        XCTAssertEqual(viewModel.items.map(\.id), [newItem.id])
        XCTAssertEqual(viewModel.selectedUP, "42")
        XCTAssertEqual(viewModel.selectedTag, "旧标签")
        XCTAssertNil(viewModel.nextCursor)
    }

    func testSearchHitDestinationCarriesQueryAndPreciseLocation() {
        let noteHit = SearchHit(kind: "notes", chunkOrd: 7, snippet: "命中", startSec: nil, headingPath: "章节", endSec: nil)
        let group = SearchGroup(
            documentId: "doc-1", jobId: nil, title: "标题", author: "作者", provider: "bilibili",
            sourceUrl: nil, savedAt: 1000, tldr: nil, duration: 10, legacy: false, hits: [noteHit]
        )

        let destination = group.destination(for: noteHit, query: "关键词")

        XCTAssertEqual(destination.id, "doc-1")
        XCTAssertEqual(destination.initialTab, .notes)
        XCTAssertEqual(destination.initialChunkOrd, 7)
        XCTAssertNil(destination.initialCueStart)
        XCTAssertEqual(destination.searchQuery, "关键词")
    }

    func testSubtitleDestinationUsesCueStartAndSubtitleTab() {
        let hit = SearchHit(kind: "subs", chunkOrd: 3, snippet: "字幕", startSec: 61.2, headingPath: nil, endSec: 64)
        let group = SearchGroup(
            documentId: "doc-1", jobId: nil, title: "标题", author: nil, provider: "bilibili",
            sourceUrl: nil, savedAt: nil, tldr: nil, duration: nil, legacy: false, hits: [hit]
        )

        let destination = group.destination(for: hit, query: "字幕")

        XCTAssertEqual(destination.initialTab, .subtitles)
        XCTAssertNil(destination.initialChunkOrd)
        XCTAssertEqual(destination.initialCueStart, 61.2)
        XCTAssertEqual(destination.searchQuery, "字幕")
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func makeItem(_ id: String) -> Biri.LibraryItem {
        Biri.LibraryItem(
            id: id, documentId: id, jobId: nil, title: id, author: "作者", provider: "bilibili",
            duration: 10, tags: ["机器学习"], tldr: nil, savedAt: 1000, sourceUrl: nil, legacy: false,
            mid: 42, bvid: "BV1"
        )
    }
}

@MainActor
private final class LibraryControlledService: BiriServicing, LibraryLifecycleServicing {
    struct Request {
        let cursor: CursorValue?
        let up: String?
        let tag: String?
    }

    var firstPages: [LibraryPage] = []
    var nextPage: LibraryPage?
    var suspendFirstPage = false
    var firstContinuation: CheckedContinuation<LibraryPage, Never>?
    private(set) var requests: [Request] = []

    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        try await library(cursor: cursor, limit: limit, up: nil, tag: nil)
    }

    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage {
        requests.append(Request(cursor: cursor, up: up, tag: tag))
        if cursor != nil { return nextPage! }
        if suspendFirstPage {
            suspendFirstPage = false
            return await withCheckedContinuation { firstContinuation = $0 }
        }
        return firstPages.removeFirst()
    }

    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        SearchPage(groups: [], nextCursor: nil, partial: [])
    }

    func document(id: String) async throws -> DocumentContent { throw APIError.http(status: 404, message: nil) }
    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        JobPage(jobs: [], nextCursor: nil)
    }
    func job(id: String) async throws -> Job { throw APIError.http(status: 404, message: nil) }
    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        RuntimeConfiguration(authMode: "none", knowledgeSearchEnabled: true)
    }

    func trash() async throws -> TrashPage { TrashPage(ok: true, items: []) }
    func softDeleteDocument(id: String, reason: String?) async throws -> LifecycleDocument {
        throw APIError.http(status: 404, message: nil)
    }
    func restoreDocument(id: String) async throws -> LifecycleDocument {
        throw APIError.http(status: 404, message: nil)
    }
    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult {
        throw APIError.http(status: 404, message: nil)
    }
}
