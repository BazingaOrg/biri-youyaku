import XCTest
@testable import Biri

final class FeatureAPIContractTests: XCTestCase {
    func testSourceCapabilitiesAndResolutionDecodeBackendContracts() async throws {
        let client = makeClient { request in
            switch request.url!.path() {
            case "/v1/sources/capabilities":
                return self.response(request, json: #"{"providers":["bilibili","youtube","upload"],"upload":{"max_bytes":1048576,"extensions":[".srt",".wav"]},"ffmpeg":true,"ffprobe":true,"asr":{"installed":true,"model":"auto"},"youtube":false}"#)
            case "/v1/sources/resolve":
                XCTAssertEqual(self.queryItem("url", in: request), "https://example.com/video?p=2")
                return self.response(request, json: #"{"provider":"bilibili","source_id":"BV1","source_part":"2","canonical_url":"https://example.com/video?p=2","existing":{"document_id":"doc-1","title":"已有笔记","saved_at":1000},"trashed":null,"active_job_id":"job-active"}"#)
            default:
                XCTFail("Unexpected path: \(request.url!.path())")
                return self.response(request, status: 404, json: #"{"detail":"not found"}"#)
            }
        }

        let capabilities = try await client.sourceCapabilities()
        let resolution = try await client.resolveSource(url: "https://example.com/video?p=2")

        XCTAssertEqual(capabilities.upload.maxBytes, 1_048_576)
        XCTAssertTrue(capabilities.asr.installed)
        XCTAssertEqual(resolution.existing?.documentId, "doc-1")
        XCTAssertEqual(resolution.activeJobId, "job-active")
    }

    func testCreateJobAndResummarizeEncodeEmailOptionAndUseReturnedNewID() async throws {
        let client = makeClient { request in
            XCTAssertEqual(request.httpMethod, "POST")
            let body = try self.jsonBody(request)
            let options = try XCTUnwrap(body["options"] as? [String: Any])
            XCTAssertEqual(options["email_enabled"] as? Bool, false)
            switch request.url!.path() {
            case "/v1/jobs":
                XCTAssertEqual(body["url"] as? String, "https://example.com/video")
                XCTAssertEqual(body["dedupe"] as? Bool, true)
                return self.response(request, json: #"{"ok":true,"job_id":"job-original"}"#)
            case "/v1/jobs/job-original/resummarize":
                return self.response(request, json: #"{"ok":true,"job_id":"job-resummary"}"#)
            default:
                XCTFail("Unexpected path: \(request.url!.path())")
                return self.response(request, status: 404, json: #"{"detail":"not found"}"#)
            }
        }

        let original = try await client.createJob(url: "https://example.com/video", dedupe: true, emailEnabled: false)
        let resummary = try await client.resummarizeJob(id: original.jobId, emailEnabled: false)

        XCTAssertEqual(original.jobId, "job-original")
        XCTAssertFalse(original.deduped)
        XCTAssertEqual(resummary.jobId, "job-resummary")
        XCTAssertNotEqual(resummary.jobId, original.jobId)
    }

    func testJobSnapshotDecodesPersistedEmailError() async throws {
        let client = makeClient { request in
            XCTAssertEqual(request.url!.path(), "/v1/jobs/job-email")
            return self.response(request, json: #"{"job":{"id":"job-email","url":"https://example.com/video","title":"笔记","author":"作者","duration":10,"status":"COMPLETED","error_stage":null,"error_message":null,"created_at":1,"updated_at":2,"completed_at":2,"summary_available":true,"document_id":null,"summary":"正文","transcript":[],"email_error":"上次发送失败"}}"#)
        }

        let job = try await client.job(id: "job-email")

        XCTAssertEqual(job.emailError, "上次发送失败")
    }

    func testJobMutationsAndSelectedDeletionUseFocusedRoutes() async throws {
        var deletedIDs: [String] = []
        let client = makeClient { request in
            let path = request.url!.path()
            switch path {
            case "/v1/jobs/job-1/cancel", "/v1/jobs/job-1/retry", "/v1/jobs/job-1/resume", "/v1/jobs/job-1/email":
                XCTAssertEqual(request.httpMethod, "POST")
            case "/v1/jobs/job-1", "/v1/jobs/job-2":
                XCTAssertEqual(request.httpMethod, "DELETE")
                deletedIDs.append(request.url!.lastPathComponent)
            default:
                XCTFail("Unexpected path: \(path)")
            }
            return self.response(request, json: #"{"ok":true}"#)
        }

        try await client.cancelJob(id: "job-1")
        try await client.retryJob(id: "job-1", emailEnabled: true)
        try await client.resumeJob(id: "job-1", emailEnabled: nil)
        try await client.resendEmail(jobID: "job-1")
        try await client.deleteJobs(ids: ["job-1", "job-2"])

        XCTAssertEqual(deletedIDs, ["job-1", "job-2"])
    }

    func testBatchDeleteReportsSuccessfulIDsBeforeFailure() async throws {
        var requestedIDs: [String] = []
        let client = makeClient { request in
            let id = request.url!.lastPathComponent
            requestedIDs.append(id)
            if id == "job-2" {
                return self.response(request, status: 500, json: #"{"detail":"删除失败"}"#)
            }
            return self.response(request, json: #"{"ok":true}"#)
        }

        do {
            try await client.deleteJobs(ids: ["job-1", "job-2", "job-3"])
            XCTFail("Expected the middle deletion to fail")
        } catch let error as JobBatchDeleteError {
            XCTAssertEqual(error.successfulIDs, ["job-1"])
            XCTAssertEqual(requestedIDs, ["job-1", "job-2"])
        }
    }

    func testLibraryFiltersTrashAndTitleConfirmedPurgeMatchBackend() async throws {
        let client = makeClient { request in
            let path = request.url!.path()
            switch path {
            case "/v1/library":
                XCTAssertEqual(self.queryItem("up", in: request), "42")
                XCTAssertEqual(self.queryItem("tag", in: request), "机器学习")
                XCTAssertEqual(self.queryItem("cursor", in: request), "1000")
                return self.response(request, json: #"{"items":[],"next_cursor":null,"total":0}"#)
            case "/v1/library/trash":
                return self.response(request, json: #"{"ok":true,"items":[{"document_id":"doc-1","title":"旧笔记","author":"作者","provider":"bilibili","source_id":"BV1","source_part":"","bvid":"BV1","deleted_at":1000,"expires_at":2000,"days_left":6}]}"#)
            case "/v1/knowledge/documents/doc-1/soft-delete":
                let body = try self.jsonBody(request)
                XCTAssertEqual(body["reason"] as? String, "不再需要")
                return self.response(request, json: #"{"ok":true,"document":{"id":"doc-1","title":"旧笔记","author":"作者","bvid":"BV1","cid":2,"deleted_at":1000,"delete_reason":"不再需要"}}"#)
            case "/v1/knowledge/documents/doc-1/restore":
                return self.response(request, json: #"{"ok":true,"document":{"id":"doc-1","title":"旧笔记","author":"作者","bvid":"BV1","cid":2,"deleted_at":null}}"#)
            case "/v1/knowledge/documents/doc-1/purge":
                let body = try self.jsonBody(request)
                XCTAssertEqual(body["confirm"] as? Bool, true)
                XCTAssertEqual(body["confirm_title"] as? String, "旧笔记")
                return self.response(request, json: #"{"ok":true,"id":"doc-1","purged":true,"title":"旧笔记","bvid":"BV1"}"#)
            default:
                XCTFail("Unexpected path: \(path)")
                return self.response(request, status: 404, json: #"{"detail":"not found"}"#)
            }
        }

        _ = try await client.library(cursor: CursorValue("1000"), limit: 20, up: "42", tag: "机器学习")
        let trash = try await client.trash()
        let deleted = try await client.softDeleteDocument(id: "doc-1", reason: "不再需要")
        let restored = try await client.restoreDocument(id: "doc-1")
        let purged = try await client.purgeDocument(id: "doc-1", confirmedTitle: "旧笔记")

        XCTAssertEqual(trash.items.first?.daysLeft, 6)
        XCTAssertEqual(deleted.deleteReason, "不再需要")
        XCTAssertNil(restored.deletedAt)
        XCTAssertTrue(purged.purged)
    }

    func testBulkDeletePreviewTokenIsTheOnlyExecuteInput() async throws {
        let client = makeClient { request in
            switch request.url!.path() {
            case "/v1/jobs/bulk-delete/preview":
                let body = try self.jsonBody(request)
                XCTAssertEqual(body["query"] as? String, "旧任务")
                XCTAssertEqual(body["tag"] as? String, "历史")
                return self.response(request, json: #"{"ok":true,"matched_count":1,"by_status":{"COMPLETED":1,"FAILED":0,"CANCELED":0},"sample":[{"id":"job-1","title":"旧任务","author":null,"created_at":1000,"status":"COMPLETED"}],"sample_truncated_count":0,"expires_at":2000,"preview_token":"signed-preview"}"#)
            case "/v1/jobs/bulk-delete/execute":
                let body = try self.jsonBody(request)
                XCTAssertEqual(body.count, 1)
                XCTAssertEqual(body["preview_token"] as? String, "signed-preview")
                return self.response(request, json: #"{"ok":true,"deleted_count":1,"cleanup_pending_count":0,"cleanup_failures":[],"cleanup_retry":null}"#)
            default:
                XCTFail("Unexpected path: \(request.url!.path())")
                return self.response(request, status: 404, json: #"{"detail":"not found"}"#)
            }
        }

        let preview = try await client.previewBulkDelete(filter: BulkDeleteFilter(query: "旧任务", tag: "历史"))
        let result = try await client.executeBulkDelete(previewToken: preview.previewToken)

        XCTAssertEqual(preview.sample.first?.status, .completed)
        XCTAssertEqual(result.deletedCount, 1)
        XCTAssertEqual(result.cleanupPendingCount, 0)
    }

    func testUPAndDistillContractsUseCatalogAndRunIdentifiers() async throws {
        let runJSON = #"{"id":"run-1","mid":42,"up_name":"作者","status":"PENDING","video_limit":20,"counters":{"videos_total":0,"videos_transcribed":0,"videos_extracted":0,"videos_failed":0,"failed_bvids":[]},"error":null,"dir_path":"/data/distill/42","created_at":1000,"updated_at":1000}"#
        let client = makeClient { request in
            let path = request.url!.path()
            switch path {
            case "/v1/up/resolve":
                XCTAssertEqual(self.queryItem("input", in: request), "https://space.bilibili.com/42")
                return self.response(request, json: #"{"ok":true,"mid":42}"#)
            case "/v1/up/42/videos":
                XCTAssertEqual(self.queryItem("page", in: request), "2")
                XCTAssertEqual(self.queryItem("keyword", in: request), "Swift")
                XCTAssertEqual(self.queryItem("order", in: request), "click")
                return self.response(request, json: #"{"ok":true,"mid":42,"author":"作者","total":1,"page":2,"page_size":30,"has_more":false,"videos":[{"bvid":"BV1","title":"视频","cover":"https://example.com/cover.jpg","pubdate":1000,"duration":61,"url":"https://www.bilibili.com/video/BV1","status":"COMPLETED","job_id":"job-1","document_id":"doc-1"}]}"#)
            case "/v1/up/42/distill":
                if request.httpMethod == "DELETE" { return self.response(request, json: #"{"ok":true}"#) }
                let body = try self.jsonBody(request)
                XCTAssertEqual(body["video_limit"] as? Int, 20)
                return self.response(request, json: "{\"ok\":true,\"run\":\(runJSON)}")
            case "/v1/distill/run-1":
                return self.response(request, json: "{\"ok\":true,\"run\":\(runJSON)}")
            case "/v1/up/42/distill/latest":
                return self.response(request, json: #"{"ok":true,"run":null}"#)
            case "/v1/distill/run-1/cancel":
                return self.response(request, json: #"{"ok":true}"#)
            case "/v1/distill/run-1/corpus":
                return self.response(request, json: "{\"ok\":true,\"run_id\":\"run-1\",\"corpus\":\"# 语料\"}")
            default:
                XCTFail("Unexpected path: \(path)")
                return self.response(request, status: 404, json: #"{"detail":"not found"}"#)
            }
        }

        let resolution = try await client.resolveUP(input: "https://space.bilibili.com/42")
        let catalog = try await client.upVideos(mid: resolution.mid, page: 2, keyword: "Swift", order: .click)
        let run = try await client.startDistill(mid: 42, videoLimit: 20)
        let status = try await client.distillStatus(id: run.id)
        let latest = try await client.latestDistill(mid: 42)
        let corpus = try await client.distillCorpus(id: run.id)
        try await client.cancelDistill(id: run.id)
        try await client.deleteDistill(mid: 42)

        XCTAssertEqual(catalog.videos.first?.status, .completed)
        XCTAssertEqual(status.counters.videosTotal, 0)
        XCTAssertNil(latest)
        XCTAssertEqual(corpus.corpus, "# 语料")
    }

    func testJobSSEDecodesSnapshotProgressAndCumulativeSummary() async throws {
        let sse = """
        event: status
        data: {"status":"SUMMARIZING","summary":null,"queued":false}

        event: meta
        data: {"title":"标题","author":"作者","duration":61,"chapters":[{"start":0,"end":10,"title":"开头"}]}

        event: download_progress
        data: {"percent":50,"downloaded_bytes":10,"total_bytes":20}

        : keepalive
        event: transcribe_progress
        data: {"percent":75,"items_count":3,"preview":"字幕"}

        event: summary_chunk
        data: {"text":"截至目前的完整总结"}

        event: summary_segment
        data: {"done":1,"total":2}

        event: error
        data: {"stage":"SUMMARIZING","message":"失败原因"}

        """
        let client = makeClient { request in
            XCTAssertEqual(request.url!.path(), "/v1/jobs/job-1/stream")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            return self.response(request, body: sse, contentType: "text/event-stream")
        }

        var events: [JobEvent] = []
        for try await event in client.jobEvents(id: "job-1") {
            events.append(event)
        }

        XCTAssertEqual(events.count, 7)
        guard case let .status(snapshot) = events[0] else { return XCTFail("Expected status snapshot") }
        XCTAssertEqual(snapshot.status, .summarizing)
        guard case let .meta(meta) = events[1] else { return XCTFail("Expected metadata") }
        XCTAssertEqual(meta.chapters.first?.title, "开头")
        guard case let .downloadProgress(download) = events[2] else { return XCTFail("Expected download progress") }
        XCTAssertEqual(download.percent, 50)
        guard case let .transcribeProgress(transcribe) = events[3] else { return XCTFail("Expected transcribe progress") }
        XCTAssertEqual(transcribe.itemsCount, 3)
        guard case let .cumulativeSummary(summary) = events[4] else { return XCTFail("Expected cumulative summary") }
        XCTAssertEqual(summary, "截至目前的完整总结")
        guard case let .summaryProgress(segment) = events[5] else { return XCTFail("Expected summary progress") }
        XCTAssertEqual(segment.done, 1)
        guard case let .error(error) = events[6] else { return XCTFail("Expected error event") }
        XCTAssertEqual(error.message, "失败原因")
    }

    func testDistillSSESeparatesFullSnapshotFromStatusDelta() async throws {
        let sse = """
        event: status
        data: {"id":"run-1","mid":42,"up_name":"作者","status":"PREPARING_TRANSCRIPTS","video_limit":20,"counters":{"videos_total":3,"videos_transcribed":0,"videos_extracted":0,"videos_failed":0,"failed_bvids":[]},"error":null,"dir_path":"/data/distill/42","created_at":1000,"updated_at":1000}

        event: status
        data: {"status":"EXTRACTING","videos_total":3,"videos_transcribed":2,"videos_extracted":1}

        """
        let client = makeClient { request in
            XCTAssertEqual(request.url!.path(), "/v1/distill/run-1/events")
            return self.response(request, body: sse, contentType: "text/event-stream")
        }

        var events: [DistillEvent] = []
        for try await event in client.distillEvents(id: "run-1") {
            events.append(event)
        }

        XCTAssertEqual(events.count, 2)
        guard case let .snapshot(snapshot) = events[0] else { return XCTFail("Expected full snapshot") }
        XCTAssertEqual(snapshot.counters.videosTotal, 3)
        guard case let .status(update) = events[1] else { return XCTFail("Expected status delta") }
        XCTAssertEqual(update.status, .extracting)
        XCTAssertEqual(update.videosTranscribed, 2)
    }

    private func makeClient(handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) -> APIClient {
        FeatureStubURLProtocol.handler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FeatureStubURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "https://example.com")!,
            token: "test-token",
            session: URLSession(configuration: configuration)
        )
    }

    private func response(
        _ request: URLRequest,
        status: Int = 200,
        json: String
    ) -> (HTTPURLResponse, Data) {
        response(request, status: status, body: json, contentType: "application/json")
    }

    private func response(
        _ request: URLRequest,
        status: Int = 200,
        body: String,
        contentType: String
    ) -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": contentType]
            )!,
            Data(body.utf8)
        )
    }

    private func queryItem(_ name: String, in request: URLRequest) -> String? {
        URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
            .queryItems?.first { $0.name == name }?.value
    }

    private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
        let data: Data
        if let body = request.httpBody {
            data = body
        } else if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var body = Data()
            var buffer = [UInt8](repeating: 0, count: 1024)
            while true {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                body.append(buffer, count: count)
            }
            data = body
        } else {
            XCTFail("Expected a JSON request body")
            return [:]
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

private final class FeatureStubURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
