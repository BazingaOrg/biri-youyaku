import XCTest
@testable import Biri

@MainActor
final class ReaderExpansionTests: XCTestCase {
    func testInitialNoteChunkMapsOnlyToRenderedTextAndSelectsMatch() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(
            markdown: "# 标题\n\n第一段包含关键词，后面还有关键词。",
            cues: [TranscriptCue(start: 60, end: 62, text: "字幕关键词")],
            noteChunks: [NoteChunk(chunkOrd: 7, headingPath: "标题", startSec: nil, text: "第一段包含关键词，后面还有关键词。")]
        )
        let destination = ReaderDestination(
            id: "doc-1", title: "标题", kind: .document,
            initialChunkOrd: 7, searchQuery: "关键词"
        )
        let viewModel = ReaderViewModel(destination: destination)

        await viewModel.load(using: service)

        XCTAssertEqual(viewModel.initialNoteBlockID, viewModel.blocks.last?.id)
        XCTAssertEqual(viewModel.visibleMatches.count, 2)
        XCTAssertEqual(viewModel.currentMatch?.blockID, viewModel.initialNoteBlockID)
        viewModel.moveMatch(by: 1)
        XCTAssertEqual(viewModel.currentMatchPosition, 2)

        viewModel.selectedTab = .subtitles
        viewModel.resetMatchNavigation()
        XCTAssertEqual(viewModel.visibleMatches.count, 1)
        XCTAssertEqual(viewModel.currentMatch?.cueID, "60.0-字幕关键词")
    }

    func testUnmappedChunkDoesNotClaimPositionButKeepsSearchMatches() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(
            markdown: "实际正文中的关键词",
            noteChunks: [NoteChunk(chunkOrd: 9, headingPath: "不同章节", startSec: nil, text: "无法对应的原始块")]
        )
        let viewModel = ReaderViewModel(destination: ReaderDestination(
            id: "doc-1", title: "标题", kind: .document, initialChunkOrd: 9, searchQuery: "关键词"
        ))

        await viewModel.load(using: service)

        XCTAssertNil(viewModel.initialNoteBlockID)
        XCTAssertEqual(viewModel.visibleMatches.count, 1)
    }

    func testInitialCueChoosesNearestAvailableCue() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(
            markdown: "正文",
            cues: [
                TranscriptCue(start: 10, end: 12, text: "前面"),
                TranscriptCue(start: 30, end: 32, text: "目标字幕")
            ]
        )
        let viewModel = ReaderViewModel(destination: ReaderDestination(
            id: "doc-1", title: "标题", kind: .document,
            initialTab: .subtitles, initialCueStart: 29, searchQuery: "字幕"
        ))

        await viewModel.load(using: service)

        XCTAssertEqual(viewModel.initialCueID, "30.0-目标字幕")
        XCTAssertEqual(viewModel.currentMatch?.cueID, viewModel.initialCueID)
    }

    func testAmbiguousChunkDoesNotClaimExactPosition() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(
            markdown: "重复段落\n\n重复段落",
            noteChunks: [NoteChunk(chunkOrd: 4, headingPath: "", startSec: nil, text: "重复段落")]
        )
        let viewModel = ReaderViewModel(destination: ReaderDestination(
            id: "doc-1", title: "标题", kind: .document, initialChunkOrd: 4
        ))

        await viewModel.load(using: service)

        XCTAssertNil(viewModel.initialNoteBlockID)
    }

    func testAmbiguousFallbackChunkDoesNotClaimExactPosition() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(
            markdown: "重复段落内容需要足够长度\n\n重复段落内容需要足够长度",
            noteChunks: [NoteChunk(
                chunkOrd: 5,
                headingPath: "",
                startSec: nil,
                text: "开头 重复段落内容需要足够长度 重复段落内容需要足够长度 结尾"
            )]
        )
        let viewModel = ReaderViewModel(destination: ReaderDestination(
            id: "doc-1", title: "标题", kind: .document, initialChunkOrd: 5
        ))

        await viewModel.load(using: service)

        XCTAssertNil(viewModel.initialNoteBlockID)
    }

    func testRegenerationCreatesNewJobAndPreservesCurrentContent() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(markdown: "# 当前笔记")
        let viewModel = ReaderViewModel(destination: ReaderDestination(id: "doc-1", title: "标题", kind: .document))
        await viewModel.load(using: service)

        await viewModel.regenerate(using: service)

        XCTAssertEqual(service.resummarizedIDs, ["job-old"])
        XCTAssertEqual(viewModel.regeneratedJobID, "job-new")
        XCTAssertEqual(viewModel.content?.markdown, "# 当前笔记")
        XCTAssertFalse(viewModel.didMoveToTrash)
        XCTAssertNotNil(viewModel.feedbackMessage)
    }

    func testSoftDeleteProvidesRecoverableState() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(markdown: "正文")
        let viewModel = ReaderViewModel(destination: ReaderDestination(id: "doc-1", title: "标题", kind: .document))
        await viewModel.load(using: service)

        await viewModel.softDelete(using: service)

        XCTAssertEqual(service.softDeletedIDs, ["doc-1"])
        XCTAssertTrue(viewModel.didMoveToTrash)
        XCTAssertEqual(viewModel.content?.markdown, "正文")
        XCTAssertFalse(viewModel.canRegenerate)
    }

    func testLateSoftDeleteCannotMarkNewlyLoadedContentAsTrashed() async {
        let service = ReaderMutationService()
        service.documentResult = makeContent(markdown: "旧正文")
        let viewModel = ReaderViewModel(destination: ReaderDestination(id: "doc-1", title: "标题", kind: .document))
        await viewModel.load(using: service)
        service.documentResult = makeContent(markdown: "新正文")
        service.suspendSoftDelete = true

        let deletion = Task { await viewModel.softDelete(using: service) }
        guard await waitUntil({ service.softDeleteContinuation != nil }) else {
            await deletion.value
            return XCTFail("The deletion did not suspend")
        }
        await viewModel.load(using: service)
        service.softDeleteContinuation?.resume(returning: LifecycleDocument(
            id: "doc-1", title: "标题", author: nil, bvid: nil, cid: nil, deletedAt: 1000, deleteReason: nil
        ))
        await deletion.value

        XCTAssertEqual(viewModel.content?.markdown, "新正文")
        XCTAssertFalse(viewModel.didMoveToTrash)
        XCTAssertFalse(viewModel.isDeleting)
    }

    func testHighlightCountIsCaseInsensitiveAndIncludesRepeatedMatches() {
        XCTAssertEqual(SearchHighlight.matchCount(in: "Swift 与 swift 再次出现 SWIFT", query: "swift"), 3)
        XCTAssertEqual(SearchHighlight.matchCount(in: "正文", query: "  "), 0)
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func makeContent(
        markdown: String,
        cues: [TranscriptCue] = [],
        noteChunks: [NoteChunk]? = nil
    ) -> DocumentContent {
        let job = Job(
            id: "job-old", url: "https://example.com/video", title: "标题", author: "作者", duration: 60,
            status: .completed, errorStage: nil, errorMessage: nil, createdAt: 1000, updatedAt: 1000,
            completedAt: 1000, summaryAvailable: true, documentId: "doc-1", summary: markdown, transcript: cues
        )
        var content = DocumentContent(job: job)
        content.noteChunks = noteChunks
        return content
    }
}

@MainActor
private final class ReaderMutationService: BiriServicing, JobMutationServicing, LibraryLifecycleServicing {
    var documentResult: DocumentContent!
    var suspendSoftDelete = false
    var softDeleteContinuation: CheckedContinuation<LifecycleDocument, Never>?
    private(set) var resummarizedIDs: [String] = []
    private(set) var softDeletedIDs: [String] = []

    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }
    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }
    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        SearchPage(groups: [], nextCursor: nil, partial: [])
    }
    func document(id: String) async throws -> DocumentContent { documentResult }
    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        JobPage(jobs: [], nextCursor: nil)
    }
    func job(id: String) async throws -> Job { throw APIError.http(status: 404, message: nil) }
    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        RuntimeConfiguration(authMode: "none", knowledgeSearchEnabled: true)
    }

    func cancelJob(id: String) async throws -> OperationResponse { OperationResponse(ok: true) }
    func retryJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse { OperationResponse(ok: true) }
    func resumeJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse { OperationResponse(ok: true) }
    func resummarizeJob(id: String, emailEnabled: Bool?) async throws -> JobCreation {
        resummarizedIDs.append(id)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(JobCreation.self, from: Data(#"{"ok":true,"job_id":"job-new"}"#.utf8))
    }
    func deleteJob(id: String) async throws -> OperationResponse { OperationResponse(ok: true) }
    func deleteJobs(ids: [String]) async throws {}
    func previewBulkDelete(filter: BulkDeleteFilter) async throws -> BulkDeletePreview {
        BulkDeletePreview(
            ok: true, matchedCount: 0, byStatus: [:], sample: [], sampleTruncatedCount: 0,
            expiresAt: 2000, previewToken: "unused"
        )
    }
    func executeBulkDelete(previewToken: String) async throws -> BulkDeleteResult {
        BulkDeleteResult(ok: true, deletedCount: 0, cleanupPendingCount: 0, cleanupFailures: [], cleanupRetry: nil)
    }
    func resendEmail(jobID: String) async throws -> OperationResponse { OperationResponse(ok: true) }

    func trash() async throws -> TrashPage { TrashPage(ok: true, items: []) }
    func softDeleteDocument(id: String, reason: String?) async throws -> LifecycleDocument {
        softDeletedIDs.append(id)
        if suspendSoftDelete {
            suspendSoftDelete = false
            return await withCheckedContinuation { softDeleteContinuation = $0 }
        }
        return LifecycleDocument(id: id, title: "标题", author: nil, bvid: nil, cid: nil, deletedAt: 1000, deleteReason: reason)
    }
    func restoreDocument(id: String) async throws -> LifecycleDocument {
        LifecycleDocument(id: id, title: nil, author: nil, bvid: nil, cid: nil, deletedAt: nil, deleteReason: nil)
    }
    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult {
        DocumentPurgeResult(ok: true, id: id, purged: true, title: confirmedTitle, bvid: nil)
    }
}
