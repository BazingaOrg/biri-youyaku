import XCTest
@testable import Biri

@MainActor
final class CreateJobViewModelTests: XCTestCase {
    func testNewSourceCreatesWithCanonicalURLAndEmailThenNavigatesToJob() async throws {
        let service = CreateJobMockService()
        service.resolution = makeResolution(canonicalURL: "https://canonical.example/video")
        service.creation = try makeCreation(id: "job-new")
        let viewModel = CreateJobViewModel()
        viewModel.url = "  https://example.com/video  "
        viewModel.emailEnabled = true

        await viewModel.resolve(using: service)
        await viewModel.create(using: service)

        XCTAssertEqual(service.resolvedURLs, ["https://example.com/video"])
        XCTAssertEqual(service.createCalls.count, 1)
        XCTAssertEqual(service.createCalls.first?.url, "https://canonical.example/video")
        XCTAssertEqual(service.createCalls.first?.dedupe, true)
        XCTAssertEqual(service.createCalls.first?.emailEnabled, true)
        XCTAssertEqual(viewModel.destination, .job("job-new"))
    }

    func testExistingSourceOpensDocumentAndExplicitRegenerationDisablesDedupe() async throws {
        let service = CreateJobMockService()
        service.resolution = makeResolution(existing: .init(documentId: "doc-1", title: "已有笔记", savedAt: 1000))
        service.creation = try makeCreation(id: "job-regenerated")
        let viewModel = CreateJobViewModel()
        viewModel.url = "https://example.com/video"
        await viewModel.resolve(using: service)

        viewModel.openExisting()
        XCTAssertEqual(
            viewModel.destination,
            .reader(ReaderDestination(id: "doc-1", title: "已有笔记", kind: .document))
        )

        viewModel.clearDestination()
        await viewModel.create(using: service, dedupe: false)
        XCTAssertEqual(service.createCalls.first?.dedupe, false)
        XCTAssertEqual(viewModel.destination, .job("job-regenerated"))
    }

    func testActiveSourceNavigatesToExistingJobWithoutCreatingDuplicate() async {
        let service = CreateJobMockService()
        service.resolution = makeResolution(activeJobId: "job-active")
        let viewModel = CreateJobViewModel()
        viewModel.url = "https://example.com/video"
        await viewModel.resolve(using: service)

        viewModel.openActiveJob()

        XCTAssertEqual(viewModel.destination, .job("job-active"))
        XCTAssertTrue(service.createCalls.isEmpty)
    }

    func testExistingSourceWithActiveJobCannotCreateDuplicateRegeneration() async throws {
        let service = CreateJobMockService()
        service.resolution = makeResolution(
            existing: .init(documentId: "doc-1", title: "已有笔记", savedAt: 1000),
            activeJobId: "job-active"
        )
        service.creation = try makeCreation(id: "job-duplicate")
        let viewModel = CreateJobViewModel()
        viewModel.url = "https://example.com/video"
        await viewModel.resolve(using: service)

        viewModel.openExisting()
        XCTAssertEqual(viewModel.destination, .reader(ReaderDestination(id: "doc-1", title: "已有笔记", kind: .document)))
        viewModel.clearDestination()
        viewModel.openActiveJob()
        XCTAssertEqual(viewModel.destination, .job("job-active"))
        viewModel.clearDestination()
        await viewModel.create(using: service, dedupe: false)

        XCTAssertTrue(service.createCalls.isEmpty)
        XCTAssertNil(viewModel.destination)
    }

    func testTrashedSourceRestoresThroughLifecycleAPIAndOpensDocument() async {
        let service = CreateJobMockService()
        service.resolution = makeResolution(trashed: .init(documentId: "doc-trash", title: "回收站笔记", daysLeft: 4))
        service.restoredDocument = LifecycleDocument(
            id: "doc-trash", title: "回收站笔记", author: nil, bvid: nil, cid: nil,
            deletedAt: nil, deleteReason: nil
        )
        let viewModel = CreateJobViewModel()
        viewModel.url = "https://example.com/video"
        await viewModel.resolve(using: service)

        await viewModel.restoreTrashed(using: service)

        XCTAssertEqual(service.restoredIDs, ["doc-trash"])
        XCTAssertEqual(
            viewModel.destination,
            .reader(ReaderDestination(id: "doc-trash", title: "回收站笔记", kind: .document))
        )
    }

    func testLateResolutionCannotAppearAfterURLChanges() async {
        let service = CreateJobMockService()
        service.suspendResolve = true
        service.resolution = makeResolution(activeJobId: "stale-job")
        let viewModel = CreateJobViewModel()
        viewModel.url = "https://example.com/old"

        let resolving = Task { await viewModel.resolve(using: service) }
        guard await waitUntil({ service.resolveContinuation != nil }) else {
            XCTFail("Resolve did not reach controlled suspension")
            return
        }
        viewModel.updateURL("https://example.com/new")
        service.resolveContinuation?.resume(returning: service.resolution)
        await resolving.value

        XCTAssertNil(viewModel.resolution)
        XCTAssertNil(viewModel.destination)
        XCTAssertFalse(viewModel.isResolving)
    }

    private func makeResolution(
        canonicalURL: String = "https://example.com/video",
        existing: SourceResolution.ExistingDocument? = nil,
        trashed: SourceResolution.TrashedDocument? = nil,
        activeJobId: String? = nil
    ) -> SourceResolution {
        SourceResolution(
            provider: "bilibili", sourceId: "BV1", sourcePart: "", canonicalUrl: canonicalURL,
            existing: existing, trashed: trashed, activeJobId: activeJobId
        )
    }

    private func makeCreation(id: String) throws -> JobCreation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(JobCreation.self, from: Data("{\"ok\":true,\"job_id\":\"\(id)\"}".utf8))
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }
}

private final class CreateJobMockService: SourceServicing, LibraryLifecycleServicing {
    struct CreateCall {
        let url: String
        let dedupe: Bool
        let emailEnabled: Bool?
    }

    var resolution: SourceResolution!
    var creation: JobCreation!
    var restoredDocument: LifecycleDocument!
    var suspendResolve = false
    var resolveContinuation: CheckedContinuation<SourceResolution, Never>?
    private(set) var resolvedURLs: [String] = []
    private(set) var createCalls: [CreateCall] = []
    private(set) var restoredIDs: [String] = []

    func sourceCapabilities() async throws -> SourceCapabilities { throw APIError.invalidResponse }

    func resolveSource(url: String) async throws -> SourceResolution {
        resolvedURLs.append(url)
        if suspendResolve {
            suspendResolve = false
            return await withCheckedContinuation { resolveContinuation = $0 }
        }
        return resolution
    }

    func createJob(url: String, dedupe: Bool, emailEnabled: Bool?) async throws -> JobCreation {
        createCalls.append(CreateCall(url: url, dedupe: dedupe, emailEnabled: emailEnabled))
        return creation
    }

    func restoreDocument(id: String) async throws -> LifecycleDocument {
        restoredIDs.append(id)
        return restoredDocument
    }

    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }

    func trash() async throws -> TrashPage { TrashPage(ok: true, items: []) }

    func softDeleteDocument(id: String, reason: String?) async throws -> LifecycleDocument {
        throw APIError.invalidResponse
    }

    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult {
        throw APIError.invalidResponse
    }
}
