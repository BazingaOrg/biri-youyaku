import XCTest
@testable import Biri

@MainActor
final class ReaderViewModelTests: XCTestCase {
    func testLegacyJobFallsBackToSummaryAndTranscript() async {
        let service = MockService()
        service.jobResult = makeJob(documentId: nil, summary: "# 旧笔记", transcript: [TranscriptCue(start: 0, end: 1, text: "字幕")])
        let viewModel = ReaderViewModel(destination: ReaderDestination(id: "job-1", title: "旧笔记", kind: .job))

        await viewModel.load(using: service)

        XCTAssertEqual(viewModel.content?.markdown, "# 旧笔记")
        XCTAssertEqual(viewModel.content?.cues.count, 1)
        XCTAssertEqual(viewModel.headings.first?.text, "旧笔记")
        XCTAssertTrue(service.documentIDs.isEmpty)
    }

    func testJobWithDocumentUsesCanonicalDocument() async {
        let service = MockService()
        service.jobResult = makeJob(documentId: "doc-1", summary: "旧副本")
        service.documentResult = DocumentContent(job: makeJob(documentId: "doc-1", summary: "# 正式笔记"))
        let viewModel = ReaderViewModel(destination: ReaderDestination(id: "job-1", title: "笔记", kind: .job))

        await viewModel.load(using: service)

        XCTAssertEqual(service.documentIDs, ["doc-1"])
        XCTAssertEqual(viewModel.content?.markdown, "# 正式笔记")
    }

    private func makeJob(documentId: String?, summary: String?, transcript: [TranscriptCue]? = nil) -> Job {
        Job(
            id: "job-1", url: "https://example.com", title: "标题", author: "作者", duration: 10,
            status: .completed, errorStage: nil, errorMessage: nil, createdAt: 1000, updatedAt: 2000,
            completedAt: 2000, summaryAvailable: true, documentId: documentId, summary: summary, transcript: transcript
        )
    }
}

private final class MockService: BiriServicing {
    var jobResult: Job!
    var documentResult: DocumentContent!
    var documentIDs: [String] = []

    func job(id: String) async throws -> Job { jobResult }
    func document(id: String) async throws -> DocumentContent {
        documentIDs.append(id)
        return documentResult
    }
    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }
    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        SearchPage(groups: [], nextCursor: nil, partial: [])
    }
    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        JobPage(jobs: [], nextCursor: nil)
    }
    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        RuntimeConfiguration(authMode: "none", knowledgeSearchEnabled: true)
    }
}
