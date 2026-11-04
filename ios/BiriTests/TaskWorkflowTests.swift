import XCTest
@testable import Biri

@MainActor
final class TaskWorkflowTests: XCTestCase {
    func testOverlappingQuietLoadsCoalesceAndAllowLaterRefresh() async {
        let service = TaskWorkflowMockService()
        service.shouldPauseJobRequests = true
        let viewModel = JobsViewModel()
        let firstLoad = Task { await viewModel.load(using: service, quietly: true) }
        guard await waitUntil({ service.jobPageRequestCount == 1 }) else {
            service.resumeJobRequests()
            XCTFail("Initial jobs request did not start")
            return
        }

        await viewModel.load(using: service, quietly: true)
        XCTAssertEqual(service.jobPageRequestCount, 1)
        service.resumeJobRequests()
        await firstLoad.value
        XCTAssertEqual(service.jobPageRequestCount, 1)

        await viewModel.load(using: service)
        XCTAssertEqual(service.jobPageRequestCount, 2)
        XCTAssertFalse(viewModel.isLoading)
    }

    func testNonQuietLoadRunsAfterInFlightRefresh() async {
        let service = TaskWorkflowMockService()
        service.shouldPauseJobRequests = true
        let viewModel = JobsViewModel()
        let refresh = Task { await viewModel.load(using: service, quietly: true) }
        guard await waitUntil({ service.jobPageRequestCount == 1 }) else {
            service.resumeJobRequests()
            XCTFail("Initial jobs request did not start")
            return
        }

        await viewModel.load(using: service)
        XCTAssertEqual(service.jobPageRequestCount, 1)
        service.resumeJobRequests()
        await refresh.value

        XCTAssertEqual(service.jobPageRequestCount, 2)
        XCTAssertFalse(viewModel.isLoading)
    }

    func testSelectionDeletesOnlySelectedTerminalJobs() async {
        let service = TaskWorkflowMockService()
        service.jobPage = JobPage(jobs: [
            makeTaskJob(id: "active", status: .summarizing),
            makeTaskJob(id: "done", status: .completed),
            makeTaskJob(id: "failed", status: .failed)
        ], nextCursor: nil)
        let viewModel = JobsViewModel()
        await viewModel.load(using: service)
        viewModel.toggleSelection()

        viewModel.toggleSelection(for: viewModel.jobs[0])
        viewModel.toggleSelection(for: viewModel.jobs[1])
        viewModel.toggleSelection(for: viewModel.jobs[2])
        XCTAssertEqual(viewModel.selectedIDs, ["done", "failed"])

        await viewModel.deleteSelected(using: service)

        XCTAssertEqual(service.deletedIDGroups, [["done", "failed"]])
        XCTAssertEqual(viewModel.jobs.map(\.id), ["active"])
        XCTAssertTrue(viewModel.selectedIDs.isEmpty)
        XCTAssertFalse(viewModel.isSelecting)
    }

    func testPartialBatchDeleteRemovesSuccessesAndRetainsRemainingSelection() async {
        let service = TaskWorkflowMockService()
        service.jobPage = JobPage(jobs: [
            makeTaskJob(id: "first", status: .completed),
            makeTaskJob(id: "fails", status: .failed),
            makeTaskJob(id: "last", status: .canceled)
        ], nextCursor: nil)
        service.failingDeletionID = "fails"
        let viewModel = JobsViewModel()
        await viewModel.load(using: service)
        viewModel.toggleSelection()
        for job in viewModel.jobs { viewModel.toggleSelection(for: job) }

        await viewModel.deleteSelected(using: service)

        XCTAssertEqual(viewModel.jobs.map(\.id), ["fails", "last"])
        XCTAssertEqual(viewModel.selectedIDs, ["fails", "last"])
        XCTAssertTrue(viewModel.isSelecting)
        XCTAssertTrue(viewModel.errorMessage?.contains("已删除 1 条") == true)
        XCTAssertFalse(viewModel.isDeleting)
    }

    func testActiveJobCannotBeDeletedAndMutationStateDoesNotStick() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "active", status: .summarizing)
        let viewModel = JobDetailViewModel(jobID: "active")
        await viewModel.load(using: service)

        await viewModel.delete(using: service)

        XCTAssertTrue(service.deletedIDGroups.isEmpty)
        XCTAssertFalse(viewModel.isMutating)
        XCTAssertFalse(viewModel.didDelete)
        viewModel.stop()
    }

    func testResummarizeNavigatesToReturnedNewJobID() async throws {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(
            id: "job-original", status: .completed,
            transcript: [TranscriptCue(start: 0, end: 1, text: "字幕")]
        )
        service.creation = try makeTaskCreation(id: "job-new")
        let viewModel = JobDetailViewModel(jobID: "job-original")
        await viewModel.load(using: service)

        await viewModel.resummarize(using: service)

        XCTAssertEqual(service.resummarizedIDs, ["job-original"])
        XCTAssertEqual(viewModel.navigation, JobNavigation(id: "job-new"))
        XCTAssertNotEqual(viewModel.navigation?.id, viewModel.jobID)
    }

    func testLiteTranscriptAvailabilityKeepsResummarizeAction() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(
            id: "job-lite", status: .completed, summaryAvailable: true, transcriptAvailable: true
        )
        let viewModel = JobDetailViewModel(jobID: "job-lite")

        await viewModel.load(using: service)

        XCTAssertTrue(viewModel.canResummarize)
    }

    func testRetryKeepsCurrentJobAndRestartsLiveUpdates() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-failed", status: .failed)
        let viewModel = JobDetailViewModel(jobID: "job-failed")
        await viewModel.load(using: service)
        service.jobResult = makeTaskJob(id: "job-failed", status: .pending)

        await viewModel.retry(using: service)

        XCTAssertEqual(service.retriedIDs, ["job-failed"])
        XCTAssertEqual(viewModel.job?.id, "job-failed")
        XCTAssertEqual(viewModel.job?.status, .pending)
        XCTAssertNil(viewModel.navigation)
        XCTAssertEqual(viewModel.connectionState, .connecting)
        viewModel.stop()
    }

    func testTypedEventsExposeRealStageProgressAndCumulativeSummary() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-live", status: .downloadingAudio)
        let viewModel = JobDetailViewModel(jobID: "job-live")
        await viewModel.load(using: service)
        viewModel.start(using: service)
        let generation = viewModel.streamGeneration

        viewModel.process(.downloadProgress(makeDownloadProgress(percent: 42.5)), generation: generation)
        viewModel.process(.transcribeProgress(makeTranscribeProgress(percent: 65, preview: "实时字幕")), generation: generation)
        viewModel.process(.cumulativeSummary("截至目前总结的完整内容"), generation: generation)
        viewModel.process(.summaryProgress(SummarySegmentProgress(done: 2, total: 5)), generation: generation)
        viewModel.process(.status(makeStatusEvent(status: .summarizing)), generation: generation)

        XCTAssertEqual(viewModel.downloadProgress?.percent, 42.5)
        XCTAssertEqual(viewModel.transcribeProgress?.percent, 65)
        XCTAssertEqual(viewModel.transcribePreview, "实时字幕")
        XCTAssertEqual(viewModel.liveSummary, "截至目前总结的完整内容")
        XCTAssertEqual(viewModel.summaryProgress, SummarySegmentProgress(done: 2, total: 5))
        XCTAssertEqual(viewModel.job?.status, .summarizing)
        viewModel.stop()
    }

    func testTerminalEventFinishesStreamAndRefreshesReaderSnapshot() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-terminal", status: .summarizing)
        service.finishStreamImmediately = true
        service.streamedEvents = [.status(makeStatusEvent(status: .completed, summary: "# 完成"))]
        let viewModel = JobDetailViewModel(jobID: "job-terminal")
        await viewModel.load(using: service)
        service.jobResult = makeTaskJob(
            id: "job-terminal", status: .completed,
            summaryAvailable: true, documentId: "doc-done", summary: "# 完成"
        )

        viewModel.start(using: service)
        guard await waitUntil({ viewModel.connectionState == .finished && viewModel.job?.documentId == "doc-done" }) else {
            viewModel.stop()
            XCTFail("Terminal event did not finish live updates")
            return
        }

        XCTAssertEqual(viewModel.job?.status, .completed)
        XCTAssertEqual(viewModel.job?.documentId, "doc-done")
        XCTAssertNotNil(viewModel.job?.destination)
        viewModel.stop()
    }

    func testTerminalJobDoesNotOpenEventStream() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-done", status: .completed, summaryAvailable: true)
        let viewModel = JobDetailViewModel(jobID: "job-done")
        await viewModel.load(using: service)

        viewModel.start(using: service)

        XCTAssertEqual(viewModel.connectionState, .finished)
        XCTAssertTrue(service.jobStreamRequestIDs.isEmpty)
    }

    func testReconnectRefreshesSnapshotBeforeOpeningAnotherStream() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-reconnect", status: .summarizing)
        service.finishStreamImmediately = true
        let viewModel = JobDetailViewModel(jobID: "job-reconnect")
        await viewModel.load(using: service)
        let initialRequestCount = service.jobRequestIDs.count

        viewModel.start(using: service)
        guard await waitUntil({ service.jobRequestIDs.count > initialRequestCount }) else {
            viewModel.stop()
            XCTFail("Reconnect did not refresh the job snapshot")
            return
        }

        XCTAssertEqual(service.jobRequestIDs.count, initialRequestCount + 1)
        XCTAssertTrue(viewModel.usesPollingFallback)
        viewModel.stop()
    }

    func testStoppedStreamCannotApplyStaleEvents() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-stale", status: .downloadingAudio)
        let viewModel = JobDetailViewModel(jobID: "job-stale")
        await viewModel.load(using: service)
        viewModel.start(using: service)
        let staleGeneration = viewModel.streamGeneration
        viewModel.stop()

        viewModel.process(.downloadProgress(makeDownloadProgress(percent: 99)), generation: staleGeneration)
        viewModel.process(.status(makeStatusEvent(status: .completed, summary: "过期总结")), generation: staleGeneration)

        XCTAssertNil(viewModel.downloadProgress)
        XCTAssertNil(viewModel.liveSummary)
        XCTAssertEqual(viewModel.job?.status, .downloadingAudio)
    }

    func testCompletedEmailErrorLoadsFromJobSnapshot() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(
            id: "job-email-persisted", status: .completed,
            summary: "笔记", emailError: "上次发送失败"
        )
        let viewModel = JobDetailViewModel(jobID: "job-email-persisted")

        await viewModel.load(using: service)

        XCTAssertEqual(viewModel.emailError, "上次发送失败")
        XCTAssertEqual(viewModel.job?.emailError, "上次发送失败")
    }

    func testCompletedEmailErrorCanBeResent() async {
        let service = TaskWorkflowMockService()
        service.jobResult = makeTaskJob(id: "job-email", status: .completed, summary: "笔记")
        let viewModel = JobDetailViewModel(jobID: "job-email")
        await viewModel.load(using: service)
        viewModel.start(using: service)
        viewModel.process(
            .status(makeStatusEvent(status: .completed, emailError: "发送失败")),
            generation: viewModel.streamGeneration
        )
        XCTAssertEqual(viewModel.emailError, "发送失败")

        await viewModel.resendEmail(using: service)

        XCTAssertEqual(service.resentEmailJobIDs, ["job-email"])
        XCTAssertNil(viewModel.emailError)
        XCTAssertEqual(viewModel.noticeMessage, "邮件已重新发送")
        viewModel.stop()
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<5_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }
}

private func makeTaskJob(
    id: String,
    status: JobStatus,
    summaryAvailable: Bool = false,
    documentId: String? = nil,
    summary: String? = nil,
    transcript: [TranscriptCue]? = nil,
    transcriptAvailable: Bool? = nil,
    emailError: String? = nil
) -> Job {
    Job(
        id: id, url: "https://example.com/video", title: "任务 \(id)", author: "作者", duration: 10,
        status: status, errorStage: nil, errorMessage: nil, createdAt: 1000, updatedAt: 2000,
        completedAt: status == .completed ? 2000 : nil, summaryAvailable: summaryAvailable,
        documentId: documentId, summary: summary, transcript: transcript,
        transcriptAvailable: transcriptAvailable, emailError: emailError
    )
}

private func makeTaskCreation(id: String) throws -> JobCreation {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(JobCreation.self, from: Data("{\"ok\":true,\"job_id\":\"\(id)\"}".utf8))
}

private func makeStatusEvent(
    status: JobStatus,
    summary: String? = nil,
    emailError: String? = nil
) -> JobStatusEvent {
    JobStatusEvent(
        status: status, summary: summary, stage: nil, message: nil, errorCode: nil,
        emailError: emailError, transcriptPreview: nil, subtitleSource: nil, queued: nil, tags: nil
    )
}

private func makeDownloadProgress(percent: Double) -> DownloadProgress {
    DownloadProgress(
        status: "downloading", downloadedBytes: 50, totalBytes: 100,
        percent: percent, speed: nil, eta: nil
    )
}

private func makeTranscribeProgress(percent: Double, preview: String) -> TranscribeProgress {
    TranscribeProgress(percent: percent, itemsCount: 3, preview: preview)
}

private final class TaskWorkflowMockService: JobDetailServicing {
    var jobPage = JobPage(jobs: [], nextCursor: nil)
    private(set) var jobPageRequestCount = 0
    var shouldPauseJobRequests = false
    private var jobRequestContinuations: [CheckedContinuation<Void, Never>] = []
    var jobResult: Job!
    var creation: JobCreation!
    var streamedEvents: [JobEvent] = []
    var finishStreamImmediately = false
    var failingDeletionID: String?
    private(set) var deletedIDGroups: [[String]] = []
    private(set) var resummarizedIDs: [String] = []
    private(set) var retriedIDs: [String] = []
    private(set) var resentEmailJobIDs: [String] = []
    private(set) var jobRequestIDs: [String] = []
    private(set) var jobStreamRequestIDs: [String] = []

    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        jobPageRequestCount += 1
        if shouldPauseJobRequests {
            await withCheckedContinuation { continuation in
                jobRequestContinuations.append(continuation)
            }
        }
        return jobPage
    }

    func resumeJobRequests() {
        shouldPauseJobRequests = false
        let continuations = jobRequestContinuations
        jobRequestContinuations.removeAll()
        for continuation in continuations { continuation.resume() }
    }

    func job(id: String) async throws -> Job {
        jobRequestIDs.append(id)
        return jobResult
    }

    func jobEvents(id: String) -> AsyncThrowingStream<JobEvent, Error> {
        jobStreamRequestIDs.append(id)
        return AsyncThrowingStream { continuation in
            for event in streamedEvents { continuation.yield(event) }
            if finishStreamImmediately {
                continuation.finish()
            } else {
                continuation.onTermination = { _ in }
            }
        }
    }

    func deleteJobs(ids: [String]) async throws {
        deletedIDGroups.append(ids)
        var successfulIDs: [String] = []
        for id in ids {
            if id == failingDeletionID {
                throw JobBatchDeleteError(
                    successfulIDs: successfulIDs,
                    underlying: APIError.http(status: 500, message: "删除失败")
                )
            }
            successfulIDs.append(id)
        }
    }

    func deleteJob(id: String) async throws -> OperationResponse {
        deletedIDGroups.append([id])
        return OperationResponse(ok: true)
    }

    func resummarizeJob(id: String, emailEnabled: Bool?) async throws -> JobCreation {
        resummarizedIDs.append(id)
        return creation
    }

    func retryJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse {
        retriedIDs.append(id)
        return OperationResponse(ok: true)
    }

    func resendEmail(jobID: String) async throws -> OperationResponse {
        resentEmailJobIDs.append(jobID)
        return OperationResponse(ok: true)
    }

    func cancelJob(id: String) async throws -> OperationResponse { OperationResponse(ok: true) }
    func resumeJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse { OperationResponse(ok: true) }

    func previewBulkDelete(filter: BulkDeleteFilter) async throws -> BulkDeletePreview {
        throw APIError.invalidResponse
    }

    func executeBulkDelete(previewToken: String) async throws -> BulkDeleteResult {
        throw APIError.invalidResponse
    }

    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }

    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        SearchPage(groups: [], nextCursor: nil, partial: [])
    }

    func document(id: String) async throws -> DocumentContent { throw APIError.invalidResponse }

    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        RuntimeConfiguration(authMode: "none", knowledgeSearchEnabled: true)
    }
}
