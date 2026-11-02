import XCTest
@testable import Biri

@MainActor
final class UPCatalogViewModelTests: XCTestCase {
    func testPaginationDeduplicatesAndFiltersOnlyLoadedRows() async {
        let service = ControlledUPService()
        service.firstPages = [
            catalogPage(
                page: 1,
                hasMore: true,
                videos: [
                    video("BV1", status: .completed, jobID: "job-1", documentID: "doc-1"),
                    video("BV2", status: .transcribing, jobID: "job-2")
                ]
            )
        ]
        service.nextPage = catalogPage(
            page: 2,
            hasMore: false,
            videos: [
                video("BV3", status: .failed, jobID: "job-3"),
                video("BV1", status: .completed, jobID: "job-1", documentID: "doc-1")
            ]
        )
        let viewModel = UPCatalogViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        await viewModel.loadMore(using: service)

        XCTAssertEqual(viewModel.videos.map(\.id), ["BV1", "BV2", "BV3"])
        XCTAssertEqual(service.requests.map(\.page), [1, 2])
        XCTAssertEqual(viewModel.loadedSummarizedCount, 1)

        viewModel.filter = .summarized
        XCTAssertEqual(viewModel.visibleVideos.map(\.id), ["BV1"])
        viewModel.filter = .unsummarized
        XCTAssertEqual(viewModel.visibleVideos.map(\.id), ["BV3"])
        viewModel.filter = .all
        XCTAssertEqual(viewModel.visibleVideos.count, 3)
    }

    func testLatePageCannotContaminateSubmittedSearchAndOrdering() async {
        let service = ControlledUPService()
        service.firstPages = [
            catalogPage(page: 1, hasMore: true, videos: [video("OLD")]),
            catalogPage(page: 1, hasMore: false, videos: [video("NEW")])
        ]
        service.nextPage = catalogPage(page: 2, hasMore: true, videos: [video("STALE")])
        let viewModel = UPCatalogViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)

        service.suspendNextPage = true
        let oldPage = Task { await viewModel.loadMore(using: service) }
        guard await waitUntil({ service.nextPageContinuation != nil }) else {
            service.nextPageContinuation?.resume(returning: service.nextPage!)
            await oldPage.value
            return XCTFail("The old catalog page was not suspended")
        }

        viewModel.query = "  Swift  "
        viewModel.order = .click
        await viewModel.load(using: service)
        service.nextPageContinuation?.resume(returning: service.nextPage!)
        await oldPage.value

        XCTAssertEqual(viewModel.videos.map(\.id), ["NEW"])
        XCTAssertFalse(viewModel.hasMore)
        XCTAssertEqual(viewModel.submittedKeyword, "Swift")
        XCTAssertEqual(service.requests.last?.keyword, "Swift")
        XCTAssertEqual(service.requests.last?.order, .click)
    }

    func testFailedQueryTransitionCannotAppendToPreviousResults() async {
        let service = ControlledUPService()
        service.firstPages = [catalogPage(page: 1, hasMore: true, videos: [video("OLD")])]
        let viewModel = UPCatalogViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        service.firstPageError = APIError.http(status: 500, message: "加载失败")
        viewModel.query = "NEW"
        viewModel.order = .click

        await viewModel.load(using: service)
        let requestCount = service.requests.count
        await viewModel.loadMore(using: service)

        XCTAssertTrue(viewModel.videos.isEmpty)
        XCTAssertFalse(viewModel.hasMore)
        XCTAssertEqual(service.requests.count, requestCount)
        XCTAssertEqual(viewModel.errorMessage, "加载失败")
    }

    func testFailedVideoUsesRetryAndNewVideoUsesCreate() async {
        let service = ControlledUPService()
        service.firstPages = [
            catalogPage(
                page: 1,
                hasMore: false,
                videos: [
                    video("FAILED", status: .failed, jobID: "job-old"),
                    video("NEW", status: nil)
                ]
            )
        ]
        let viewModel = UPCatalogViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)

        let retriedID = await viewModel.generateOrRetry(viewModel.videos[0], using: service)
        let createdID = await viewModel.generateOrRetry(viewModel.videos[1], using: service)

        XCTAssertEqual(retriedID, "job-old")
        XCTAssertEqual(createdID, "job-created")
        XCTAssertEqual(service.retryIDs, ["job-old"])
        XCTAssertEqual(service.createdURLs, ["https://www.bilibili.com/video/NEW"])
        XCTAssertEqual(viewModel.videos.map(\.status), [.pending, .pending])
        XCTAssertEqual(viewModel.videos.map(\.jobId), ["job-old", "job-created"])
    }

    func testCompletedDocumentAndActiveJobExposeNativeDestinations() {
        let completed = video("DONE", status: .completed, jobID: "job-done", documentID: "doc-done")
        let active = video("ACTIVE", status: .summarizing, jobID: "job-active")

        XCTAssertEqual(completed.readerDestination?.kind, .document)
        XCTAssertEqual(completed.readerDestination?.id, "doc-done")
        XCTAssertNil(completed.activeJobID)
        XCTAssertEqual(active.activeJobID, "job-active")
        XCTAssertNil(active.readerDestination)
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func video(
        _ id: String,
        status: JobStatus? = nil,
        jobID: String? = nil,
        documentID: String? = nil
    ) -> UPVideo {
        UPVideo(
            bvid: id,
            title: "视频 \(id)",
            cover: "",
            pubdate: 1_700_000_000,
            duration: 61,
            url: "https://www.bilibili.com/video/\(id)",
            status: status,
            jobId: jobID,
            documentId: documentID
        )
    }

    private func catalogPage(page: Int, hasMore: Bool, videos: [UPVideo]) -> UPCatalogPage {
        UPCatalogPage(
            ok: true,
            mid: 42,
            author: "作者",
            total: videos.count,
            page: page,
            pageSize: 30,
            hasMore: hasMore,
            videos: videos
        )
    }
}

private final class ControlledUPService: UPServicing, SourceServicing, JobMutationServicing {
    struct Request {
        let mid: Int
        let page: Int
        let keyword: String
        let order: UPCatalogOrder
    }

    private(set) var requests: [Request] = []
    var firstPages: [UPCatalogPage] = []
    var firstPageError: Error?
    var nextPage: UPCatalogPage?
    var suspendNextPage = false
    var nextPageContinuation: CheckedContinuation<UPCatalogPage, Never>?
    private(set) var retryIDs: [String] = []
    private(set) var createdURLs: [String] = []

    func resolveUP(input: String) async throws -> UPResolution {
        UPResolution(ok: true, mid: 42)
    }

    func upVideos(mid: Int, page: Int, keyword: String, order: UPCatalogOrder) async throws -> UPCatalogPage {
        requests.append(Request(mid: mid, page: page, keyword: keyword, order: order))
        if page > 1 {
            if suspendNextPage {
                suspendNextPage = false
                return await withCheckedContinuation { nextPageContinuation = $0 }
            }
            return nextPage!
        }
        if let firstPageError { throw firstPageError }
        return firstPages.removeFirst()
    }

    func sourceCapabilities() async throws -> SourceCapabilities {
        throw APIError.http(status: 404, message: nil)
    }

    func resolveSource(url: String) async throws -> SourceResolution {
        throw APIError.http(status: 404, message: nil)
    }

    func createJob(url: String, dedupe: Bool, emailEnabled: Bool?) async throws -> JobCreation {
        createdURLs.append(url)
        let data = Data(#"{"ok":true,"job_id":"job-created","deduped":false}"#.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(JobCreation.self, from: data)
    }

    func cancelJob(id: String) async throws -> OperationResponse { OperationResponse(ok: true) }

    func retryJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse {
        retryIDs.append(id)
        return OperationResponse(ok: true)
    }

    func resumeJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse {
        OperationResponse(ok: true)
    }

    func resummarizeJob(id: String, emailEnabled: Bool?) async throws -> JobCreation {
        throw APIError.http(status: 404, message: nil)
    }

    func deleteJob(id: String) async throws -> OperationResponse { OperationResponse(ok: true) }
    func deleteJobs(ids: [String]) async throws {}

    func previewBulkDelete(filter: BulkDeleteFilter) async throws -> BulkDeletePreview {
        throw APIError.http(status: 404, message: nil)
    }

    func executeBulkDelete(previewToken: String) async throws -> BulkDeleteResult {
        throw APIError.http(status: 404, message: nil)
    }

    func resendEmail(jobID: String) async throws -> OperationResponse { OperationResponse(ok: true) }
}
