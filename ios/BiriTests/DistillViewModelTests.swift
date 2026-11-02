import XCTest
@testable import Biri

@MainActor
final class DistillViewModelTests: XCTestCase {
    func testStatusDeltaMergesCountersAndRejectsStaleEvents() async {
        let service = ControlledDistillService()
        let original = run(id: "run-1", status: .preparingTranscripts, updatedAt: 2_000)
        service.latestRun = original
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        defer { viewModel.stopObserving() }

        viewModel.apply(
            .status(
                DistillStatusUpdate(
                    status: .extracting,
                    videosTotal: 20,
                    videosTranscribed: 18,
                    videosExtracted: 7,
                    error: nil
                )
            ),
            for: "run-1"
        )

        XCTAssertEqual(viewModel.run?.status, .extracting)
        XCTAssertEqual(viewModel.run?.counters.videosTotal, 20)
        XCTAssertEqual(viewModel.run?.counters.videosTranscribed, 18)
        XCTAssertEqual(viewModel.run?.counters.videosExtracted, 7)

        viewModel.apply(
            .snapshot(run(id: "run-other", status: .completed, updatedAt: 9_000)),
            for: "run-1"
        )
        viewModel.apply(
            .snapshot(run(id: "run-1", status: .pending, updatedAt: 1_000)),
            for: "run-1"
        )
        XCTAssertEqual(viewModel.run?.id, "run-1")
        XCTAssertEqual(viewModel.run?.status, .extracting)
        XCTAssertEqual(viewModel.run?.updatedAt, 2_000)

        viewModel.apply(
            .status(
                DistillStatusUpdate(
                    status: .completed,
                    videosTotal: nil,
                    videosTranscribed: nil,
                    videosExtracted: 20,
                    error: nil
                )
            ),
            for: "run-1"
        )
        viewModel.apply(
            .status(
                DistillStatusUpdate(
                    status: .extracting,
                    videosTotal: nil,
                    videosTranscribed: nil,
                    videosExtracted: 1,
                    error: nil
                )
            ),
            for: "run-1"
        )
        XCTAssertEqual(viewModel.run?.status, .completed)
        XCTAssertEqual(viewModel.run?.counters.videosExtracted, 20)
    }

    func testFailedRunStartsANewRunWithSelectedLimit() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-failed", status: .failed)
        service.startRun = run(id: "run-new", status: .pending, videoLimit: 75)
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        viewModel.videoLimit = 75

        await viewModel.start(using: service)
        defer { viewModel.stopObserving() }

        XCTAssertEqual(service.startLimits, [75])
        XCTAssertEqual(viewModel.run?.id, "run-new")
        XCTAssertNotEqual(viewModel.run?.id, "run-failed")
        XCTAssertNil(service.retryRunID)
    }

    func testCancelUsesRunIDAndRefreshesSnapshot() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .extracting, updatedAt: 1_000)
        service.statusRun = run(id: "run-1", status: .cancelled, updatedAt: 2_000)
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        defer { viewModel.stopObserving() }

        await viewModel.cancel(using: service)

        XCTAssertEqual(service.cancelledIDs, ["run-1"])
        XCTAssertEqual(viewModel.run?.status, .cancelled)
        XCTAssertEqual(viewModel.connectionState, .idle)
    }

    func testStreamFailureRecoversFromSnapshot() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .extracting, updatedAt: 1_000)
        service.statusRun = run(id: "run-1", status: .completed, updatedAt: 2_000)
        service.streamError = URLError(.networkConnectionLost)
        let viewModel = DistillViewModel(mid: 42, author: "作者", reconnectDelay: .zero)

        await viewModel.load(using: service)
        let recovered = await waitUntil { viewModel.run?.status == .completed }
        defer { viewModel.stopObserving() }

        XCTAssertTrue(recovered)
        XCTAssertGreaterThanOrEqual(service.statusRequests, 1)
        XCTAssertEqual(viewModel.run?.counters.videosExtracted, 3)
        XCTAssertEqual(viewModel.connectionState, .idle)
    }

    func testTerminalDeltaRefreshesFailureCountersFromFinalSnapshot() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .extracting, updatedAt: 1_000)
        service.statusRun = run(
            id: "run-1", status: .completed, updatedAt: 2_000,
            videosFailed: 2, failedBvids: ["BV1", "BV2"]
        )
        service.statusErrors = [URLError(.networkConnectionLost)]
        service.streamedEvents = [
            .status(DistillStatusUpdate(
                status: .completed,
                videosTotal: 3,
                videosTranscribed: 3,
                videosExtracted: 3,
                error: nil
            ))
        ]
        let viewModel = DistillViewModel(mid: 42, author: "作者", reconnectDelay: .zero)

        await viewModel.load(using: service)
        let refreshed = await waitUntil {
            viewModel.run?.status == .completed && viewModel.run?.counters.videosFailed == 2
        }
        defer { viewModel.stopObserving() }

        XCTAssertTrue(refreshed)
        XCTAssertEqual(viewModel.run?.counters.failedBvids, ["BV1", "BV2"])
        XCTAssertEqual(service.statusRequests, 2)
    }

    func testTerminalSnapshotFailureIsBoundedAndVisible() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .extracting, updatedAt: 1_000)
        service.statusRun = run(id: "run-1", status: .completed, updatedAt: 2_000, videosFailed: 2)
        service.statusErrors = [
            URLError(.networkConnectionLost),
            URLError(.networkConnectionLost),
            URLError(.networkConnectionLost)
        ]
        service.streamedEvents = [
            .status(DistillStatusUpdate(
                status: .completed, videosTotal: 3, videosTranscribed: 3, videosExtracted: 3, error: nil
            ))
        ]
        let viewModel = DistillViewModel(mid: 42, author: "作者", reconnectDelay: .zero)

        await viewModel.load(using: service)
        let finished = await waitUntil { viewModel.errorMessage != nil }
        defer { viewModel.stopObserving() }

        XCTAssertTrue(finished)
        XCTAssertEqual(service.statusRequests, 3)
        XCTAssertEqual(viewModel.run?.status, .completed)
        XCTAssertEqual(viewModel.run?.counters.videosFailed, 0)
        XCTAssertTrue(viewModel.errorMessage?.contains("最终统计暂未更新") == true)
    }

    func testCompletedCorpusLoadsOnceAndRejectsMismatchedRun() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .completed)
        service.corpus = DistillCorpus(ok: true, runId: "run-1", corpus: "# 主题\n观点")
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)

        await viewModel.loadCorpus(using: service)
        await viewModel.loadCorpus(using: service)

        XCTAssertEqual(service.corpusRequests, 1)
        XCTAssertEqual(viewModel.corpus, "# 主题\n观点")
        XCTAssertEqual(viewModel.corpusRunID, "run-1")
    }

    func testDeleteIsRejectedWhileStartIsPending() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-old", status: .failed)
        service.startRun = run(id: "run-new", status: .pending)
        service.suspendsStart = true
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        let startTask = Task { await viewModel.start(using: service) }
        guard await waitUntil({ service.startContinuation != nil }) else {
            await startTask.value
            XCTFail("Start request did not suspend")
            return
        }

        await viewModel.delete(using: service)
        service.resumeStart()
        await startTask.value

        XCTAssertTrue(service.deletedMIDs.isEmpty)
        XCTAssertEqual(viewModel.run?.id, "run-new")
        XCTAssertNil(viewModel.corpus)
        viewModel.stopObserving()
    }

    func testStartIsRejectedWhileDeleteIsPending() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-old", status: .completed)
        service.startRun = run(id: "run-new", status: .pending)
        service.suspendsDelete = true
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        let deleteTask = Task { await viewModel.delete(using: service) }
        guard await waitUntil({ service.deleteContinuation != nil }) else {
            XCTFail("Delete request did not suspend")
            return
        }

        await viewModel.start(using: service)
        XCTAssertTrue(service.startLimits.isEmpty)
        service.resumeDelete()
        await deleteTask.value

        XCTAssertEqual(service.deletedMIDs, [42])
        XCTAssertNil(viewModel.run)
    }

    func testDeleteClearsOnlyDistillState() async {
        let service = ControlledDistillService()
        service.latestRun = run(id: "run-1", status: .completed)
        service.corpus = DistillCorpus(ok: true, runId: "run-1", corpus: "语料")
        let viewModel = DistillViewModel(mid: 42, author: "作者")
        await viewModel.load(using: service)
        await viewModel.loadCorpus(using: service)

        await viewModel.delete(using: service)

        XCTAssertEqual(service.deletedMIDs, [42])
        XCTAssertNil(viewModel.run)
        XCTAssertNil(viewModel.corpus)
        XCTAssertNil(viewModel.corpusRunID)
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func run(
        id: String,
        status: DistillRunStatus,
        videoLimit: Int = 50,
        updatedAt: Int = 1_000,
        videosFailed: Int = 0,
        failedBvids: [String] = []
    ) -> DistillRun {
        DistillRun(
            id: id,
            mid: 42,
            upName: "作者",
            status: status,
            videoLimit: videoLimit,
            counters: DistillCounters(
                videosTotal: 3,
                videosTranscribed: status == .pending ? 0 : 3,
                videosExtracted: status == .completed ? 3 : 0,
                videosFailed: videosFailed,
                failedBvids: failedBvids
            ),
            error: status == .failed ? "失败原因" : nil,
            dirPath: "/data/distill/42",
            createdAt: 1_000,
            updatedAt: updatedAt
        )
    }
}

private final class ControlledDistillService: DistillServicing {
    var latestRun: DistillRun?
    var startRun: DistillRun?
    var statusRun: DistillRun?
    var statusErrors: [Error] = []
    var corpus: DistillCorpus?
    var streamError: Error?
    var streamedEvents: [DistillEvent] = []
    var suspendsStart = false
    var startContinuation: CheckedContinuation<DistillRun, Never>?
    var suspendsDelete = false
    var deleteContinuation: CheckedContinuation<OperationResponse, Never>?
    private(set) var startLimits: [Int] = []
    private(set) var cancelledIDs: [String] = []
    private(set) var deletedMIDs: [Int] = []
    private(set) var statusRequests = 0
    private(set) var corpusRequests = 0
    let retryRunID: String? = nil

    func startDistill(mid: Int, videoLimit: Int) async throws -> DistillRun {
        startLimits.append(videoLimit)
        if suspendsStart {
            return await withCheckedContinuation { continuation in
                startContinuation = continuation
            }
        }
        return startRun!
    }

    func resumeStart() {
        startContinuation?.resume(returning: startRun!)
        startContinuation = nil
    }

    func distillStatus(id: String) async throws -> DistillRun {
        statusRequests += 1
        if !statusErrors.isEmpty { throw statusErrors.removeFirst() }
        return statusRun ?? latestRun!
    }

    func latestDistill(mid: Int) async throws -> DistillRun? { latestRun }

    func cancelDistill(id: String) async throws -> OperationResponse {
        cancelledIDs.append(id)
        return OperationResponse(ok: true)
    }

    func distillCorpus(id: String) async throws -> DistillCorpus {
        corpusRequests += 1
        return corpus!
    }

    func deleteDistill(mid: Int) async throws -> OperationResponse {
        deletedMIDs.append(mid)
        if suspendsDelete {
            return await withCheckedContinuation { continuation in
                deleteContinuation = continuation
            }
        }
        return OperationResponse(ok: true)
    }

    func resumeDelete() {
        deleteContinuation?.resume(returning: OperationResponse(ok: true))
        deleteContinuation = nil
    }

    func distillEvents(id: String) -> AsyncThrowingStream<DistillEvent, Error> {
        let streamError = streamError
        return AsyncThrowingStream { continuation in
            for event in streamedEvents { continuation.yield(event) }
            if let streamError {
                continuation.finish(throwing: streamError)
            } else {
                continuation.onTermination = { _ in continuation.finish() }
            }
        }
    }
}
