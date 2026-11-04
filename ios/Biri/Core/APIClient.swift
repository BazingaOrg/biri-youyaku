import Foundation
#if canImport(UIKit)
import UIKit
#endif

protocol BiriServicing {
    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage
    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage
    func document(id: String) async throws -> DocumentContent
    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage
    func job(id: String) async throws -> Job
    func job(id: String, lite: Bool) async throws -> Job
    func runtimeConfiguration() async throws -> RuntimeConfiguration
}

extension BiriServicing {
    func job(id: String, lite: Bool) async throws -> Job {
        try await job(id: id)
    }
}

protocol SourceServicing {
    func sourceCapabilities() async throws -> SourceCapabilities
    func resolveSource(url: String) async throws -> SourceResolution
    func createJob(url: String, dedupe: Bool, emailEnabled: Bool?) async throws -> JobCreation
}

protocol JobMutationServicing {
    func cancelJob(id: String) async throws -> OperationResponse
    func retryJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse
    func resumeJob(id: String, emailEnabled: Bool?) async throws -> OperationResponse
    func resummarizeJob(id: String, emailEnabled: Bool?) async throws -> JobCreation
    func deleteJob(id: String) async throws -> OperationResponse
    func deleteJobs(ids: [String]) async throws
    func previewBulkDelete(filter: BulkDeleteFilter) async throws -> BulkDeletePreview
    func executeBulkDelete(previewToken: String) async throws -> BulkDeleteResult
    func resendEmail(jobID: String) async throws -> OperationResponse
}

protocol LibraryLifecycleServicing {
    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage
    func trash() async throws -> TrashPage
    func softDeleteDocument(id: String, reason: String?) async throws -> LifecycleDocument
    func restoreDocument(id: String) async throws -> LifecycleDocument
    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult
}

protocol UPServicing {
    func resolveUP(input: String) async throws -> UPResolution
    func upVideos(mid: Int, page: Int, keyword: String, order: UPCatalogOrder) async throws -> UPCatalogPage
}

protocol DistillServicing {
    func startDistill(mid: Int, videoLimit: Int) async throws -> DistillRun
    func distillStatus(id: String) async throws -> DistillRun
    func latestDistill(mid: Int) async throws -> DistillRun?
    func cancelDistill(id: String) async throws -> OperationResponse
    func distillCorpus(id: String) async throws -> DistillCorpus
    func deleteDistill(mid: Int) async throws -> OperationResponse
    func distillEvents(id: String) -> AsyncThrowingStream<DistillEvent, Error>
}

protocol JobEventServicing {
    func jobEvents(id: String) -> AsyncThrowingStream<JobEvent, Error>
}

struct JobBatchDeleteError: LocalizedError {
    let successfulIDs: [String]
    let underlying: Error

    var errorDescription: String? {
        let reason = underlying.localizedDescription
        guard !successfulIDs.isEmpty else { return reason }
        return "已删除 \(successfulIDs.count) 条任务记录，其余未能删除。\(reason)"
    }
}

enum APIError: LocalizedError {
    case notConfigured
    case invalidServerAddress
    case invalidResponse
    case http(status: Int, message: String?)
    case network(URLError)
    case decoding

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "请先连接服务器"
        case .invalidServerAddress:
            return "服务器地址无效，请输入正确地址，例如 https://api.example.com"
        case .invalidResponse:
            return "无法识别服务器返回的内容，请检查服务器地址"
        case let .http(status, message):
            switch status {
            case 401: return "访问令牌不正确，请检查后重试"
            case 403: return "服务器拒绝了访问，请检查访问验证设置"
            case 404:
                if let message, !message.isEmpty { return message }
                return "内容不存在或已被删除"
            default:
                if let message, !message.isEmpty { return message }
                return "服务器请求失败（\(status)）"
            }
        case let .network(error):
            switch error.code {
            case .notConnectedToInternet: return "网络不可用，请检查当前连接"
            case .timedOut: return "连接服务器超时，请稍后重试"
            case .cannotFindHost, .cannotConnectToHost: return "连不上服务器，请检查地址和网络"
            case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted:
                return "安全连接失败，请使用有效的 HTTPS 证书"
            default: return error.localizedDescription
            }
        case .decoding:
            return "无法读取服务器返回的数据。请确认地址正确，或更新 App 和服务器。"
        }
    }
}

struct APIClient: BiriServicing, SourceServicing, JobMutationServicing, LibraryLifecycleServicing,
    UPServicing, DistillServicing, JobEventServicing {
    let baseURL: URL
    let token: String?
    let session: URLSession

    init(baseURL: URL, token: String?, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
    }

    func validateConnection() async throws -> RuntimeConfiguration {
        let configuration = try await runtimeConfiguration()
        _ = try await library(cursor: nil, limit: 1)
        return configuration
    }

    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        query.appendCursor(cursor)
        return try await get(path: "/v1/library", query: query)
    }

    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        if let up { query.append(URLQueryItem(name: "up", value: up)) }
        if let tag { query.append(URLQueryItem(name: "tag", value: tag)) }
        query.appendCursor(cursor)
        return try await get(path: "/v1/library", query: query)
    }

    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        var queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "scope", value: scope.rawValue),
            URLQueryItem(name: "limit", value: "20")
        ]
        queryItems.appendCursor(cursor)
        return try await get(path: "/v1/library/search", query: queryItems)
    }

    func document(id: String) async throws -> DocumentContent {
        try await get(path: "/v1/library/documents/\(id.escapingPathComponent)/content")
    }

    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        switch filter {
        case .running:
            query.append(URLQueryItem(name: "active_only", value: "true"))
        case .completed:
            query.append(URLQueryItem(name: "status", value: JobStatus.completed.rawValue))
        case .failed:
            query.append(URLQueryItem(name: "status", value: JobStatus.failed.rawValue))
        case .all:
            break
        }
        query.appendCursor(cursor)
        return try await get(path: "/v1/jobs", query: query)
    }

    func job(id: String) async throws -> Job {
        try await job(id: id, lite: false)
    }

    func job(id: String, lite: Bool) async throws -> Job {
        let response: JobResponse = try await get(
            path: "/v1/jobs/\(id.escapingPathComponent)",
            query: lite ? [URLQueryItem(name: "lite", value: "true")] : []
        )
        return response.job
    }

    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        try await get(path: "/v1/config/runtime")
    }

    func sourceCapabilities() async throws -> SourceCapabilities {
        try await get(path: "/v1/sources/capabilities")
    }

    func resolveSource(url: String) async throws -> SourceResolution {
        try await get(path: "/v1/sources/resolve", query: [URLQueryItem(name: "url", value: url)])
    }

    func createJob(url: String, dedupe: Bool = true, emailEnabled: Bool? = nil) async throws -> JobCreation {
        try await request(
            path: "/v1/jobs",
            method: "POST",
            body: CreateJobRequest(url: url, options: JobOptionsRequest(emailEnabled: emailEnabled), dedupe: dedupe)
        )
    }

    @discardableResult
    func cancelJob(id: String) async throws -> OperationResponse {
        try await request(path: "/v1/jobs/\(id.escapingPathComponent)/cancel", method: "POST")
    }

    @discardableResult
    func retryJob(id: String, emailEnabled: Bool? = nil) async throws -> OperationResponse {
        try await request(
            path: "/v1/jobs/\(id.escapingPathComponent)/retry",
            method: "POST",
            body: JobOptionsEnvelope(options: JobOptionsRequest(emailEnabled: emailEnabled))
        )
    }

    @discardableResult
    func resumeJob(id: String, emailEnabled: Bool? = nil) async throws -> OperationResponse {
        try await request(
            path: "/v1/jobs/\(id.escapingPathComponent)/resume",
            method: "POST",
            body: JobOptionsEnvelope(options: JobOptionsRequest(emailEnabled: emailEnabled))
        )
    }

    func resummarizeJob(id: String, emailEnabled: Bool? = nil) async throws -> JobCreation {
        try await request(
            path: "/v1/jobs/\(id.escapingPathComponent)/resummarize",
            method: "POST",
            body: JobOptionsEnvelope(options: JobOptionsRequest(emailEnabled: emailEnabled))
        )
    }

    @discardableResult
    func deleteJob(id: String) async throws -> OperationResponse {
        try await request(path: "/v1/jobs/\(id.escapingPathComponent)", method: "DELETE")
    }

    func deleteJobs(ids: [String]) async throws {
        var successfulIDs: [String] = []
        do {
            for id in ids {
                try await deleteJob(id: id)
                successfulIDs.append(id)
            }
        } catch {
            throw JobBatchDeleteError(successfulIDs: successfulIDs, underlying: error)
        }
    }

    func previewBulkDelete(filter: BulkDeleteFilter) async throws -> BulkDeletePreview {
        try await request(path: "/v1/jobs/bulk-delete/preview", method: "POST", body: filter)
    }

    func executeBulkDelete(previewToken: String) async throws -> BulkDeleteResult {
        try await request(
            path: "/v1/jobs/bulk-delete/execute",
            method: "POST",
            body: BulkDeleteExecuteRequest(previewToken: previewToken)
        )
    }

    @discardableResult
    func resendEmail(jobID: String) async throws -> OperationResponse {
        try await request(path: "/v1/jobs/\(jobID.escapingPathComponent)/email", method: "POST")
    }

    func trash() async throws -> TrashPage {
        try await get(path: "/v1/library/trash")
    }

    func softDeleteDocument(id: String, reason: String? = nil) async throws -> LifecycleDocument {
        let response: LifecycleDocumentResponse = try await request(
            path: "/v1/knowledge/documents/\(id.escapingPathComponent)/soft-delete",
            method: "POST",
            body: SoftDeleteDocumentRequest(reason: reason)
        )
        return response.document
    }

    func restoreDocument(id: String) async throws -> LifecycleDocument {
        let response: LifecycleDocumentResponse = try await request(
            path: "/v1/knowledge/documents/\(id.escapingPathComponent)/restore",
            method: "POST"
        )
        return response.document
    }

    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult {
        try await request(
            path: "/v1/knowledge/documents/\(id.escapingPathComponent)/purge",
            method: "POST",
            body: PurgeDocumentRequest(confirm: true, confirmTitle: confirmedTitle)
        )
    }

    func resolveUP(input: String) async throws -> UPResolution {
        try await get(path: "/v1/up/resolve", query: [URLQueryItem(name: "input", value: input)])
    }

    func upVideos(
        mid: Int,
        page: Int = 1,
        keyword: String = "",
        order: UPCatalogOrder = .pubdate
    ) async throws -> UPCatalogPage {
        var query = [URLQueryItem(name: "page", value: String(page))]
        if !keyword.isEmpty { query.append(URLQueryItem(name: "keyword", value: keyword)) }
        query.append(URLQueryItem(name: "order", value: order.rawValue))
        return try await get(path: "/v1/up/\(mid)/videos", query: query)
    }

    func startDistill(mid: Int, videoLimit: Int = 50) async throws -> DistillRun {
        let response: DistillRunResponse = try await request(
            path: "/v1/up/\(mid)/distill",
            method: "POST",
            body: StartDistillRequest(videoLimit: videoLimit)
        )
        return response.run
    }

    func distillStatus(id: String) async throws -> DistillRun {
        let response: DistillRunResponse = try await get(path: "/v1/distill/\(id.escapingPathComponent)")
        return response.run
    }

    func latestDistill(mid: Int) async throws -> DistillRun? {
        let response: LatestDistillResponse = try await get(path: "/v1/up/\(mid)/distill/latest")
        return response.run
    }

    @discardableResult
    func cancelDistill(id: String) async throws -> OperationResponse {
        try await request(path: "/v1/distill/\(id.escapingPathComponent)/cancel", method: "POST")
    }

    func distillCorpus(id: String) async throws -> DistillCorpus {
        try await get(path: "/v1/distill/\(id.escapingPathComponent)/corpus")
    }

    @discardableResult
    func deleteDistill(mid: Int) async throws -> OperationResponse {
        try await request(path: "/v1/up/\(mid)/distill", method: "DELETE")
    }

    /// The server sends a current status snapshot when a connection opens, but does not replay
    /// missed events. After reconnecting, fetch `job(id:)` to restore a complete current snapshot.
    func jobEvents(id: String) -> AsyncThrowingStream<JobEvent, Error> {
        mapServerSentEvents(path: "/v1/jobs/\(id.escapingPathComponent)/stream", transform: Self.jobEvent)
    }

    /// The first event is a full run snapshot; later status events are deltas. There is no event
    /// replay, so callers must fetch `distillStatus(id:)` after reconnecting to fill any gaps.
    func distillEvents(id: String) -> AsyncThrowingStream<DistillEvent, Error> {
        mapServerSentEvents(path: "/v1/distill/\(id.escapingPathComponent)/events", transform: Self.distillEvent)
    }

    private func get<Response: Decodable>(path: String, query: [URLQueryItem] = []) async throws -> Response {
        try await request(path: path, query: query)
    }

    private func request<Response: Decodable>(
        path: String,
        method: String = "GET",
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil
    ) async throws -> Response {
        var request = try makeRequest(path: path, method: method, query: query)
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try Self.encoder.encode(body)
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
            guard (200..<300).contains(response.statusCode) else {
                throw APIError.http(status: response.statusCode, message: Self.errorMessage(from: data))
            }
            return try Self.decode(Response.self, from: data)
        } catch let error as APIError {
            throw error
        } catch let error as URLError {
            throw APIError.network(error)
        } catch {
            throw error
        }
    }

    private func makeRequest(
        path: String,
        method: String,
        query: [URLQueryItem] = [],
        accept: String = "application/json",
        timeout: TimeInterval = 30
    ) throws -> URLRequest {
        let endpoint = baseURL.appendingPathComponent(path)
        guard var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidServerAddress
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.invalidServerAddress }

        var request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue(accept, forHTTPHeaderField: "Accept")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func serverSentEvents(path: String) -> AsyncThrowingStream<ServerSentEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let request = try makeRequest(
                        path: path,
                        method: "GET",
                        accept: "text/event-stream",
                        timeout: 60
                    )
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
                    if !(200..<300).contains(response.statusCode) {
                        var data = Data()
                        for try await byte in bytes { data.append(byte) }
                        throw APIError.http(status: response.statusCode, message: Self.errorMessage(from: data))
                    }

                    var eventName = "message"
                    var dataLines: [String] = []
                    func flushEvent() {
                        if let event = ServerSentEvent(name: eventName, dataLines: dataLines) {
                            continuation.yield(event)
                        }
                        eventName = "message"
                        dataLines.removeAll()
                    }
                    func processLine(_ rawLine: String) {
                        var line = rawLine
                        if line.last == "\r" { line.removeLast() }
                        if line.isEmpty {
                            flushEvent()
                        } else if line.hasPrefix(":") {
                            return
                        } else if let value = Self.sseValue(for: "event", in: line) {
                            eventName = value
                        } else if let value = Self.sseValue(for: "data", in: line) {
                            dataLines.append(value)
                        }
                    }

                    var lineBytes = Data()
                    for try await byte in bytes {
                        if Task.isCancelled { break }
                        if byte == 0x0A {
                            processLine(String(decoding: lineBytes, as: UTF8.self))
                            lineBytes.removeAll(keepingCapacity: true)
                        } else {
                            lineBytes.append(byte)
                        }
                    }
                    if !lineBytes.isEmpty {
                        processLine(String(decoding: lineBytes, as: UTF8.self))
                    }
                    flushEvent()
                    continuation.finish()
                } catch {
                    if Task.isCancelled {
                        continuation.finish()
                    } else if let error = error as? URLError {
                        continuation.finish(throwing: APIError.network(error))
                    } else {
                        continuation.finish(throwing: error)
                    }
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func mapServerSentEvents<Event>(
        path: String,
        transform: @escaping (ServerSentEvent) throws -> Event
    ) -> AsyncThrowingStream<Event, Error> {
        let source = serverSentEvents(path: path)
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await event in source {
                        continuation.yield(try transform(event))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func jobEvent(from event: ServerSentEvent) throws -> JobEvent {
        switch event.name {
        case "status": return .status(try decode(JobStatusEvent.self, from: event.data))
        case "meta": return .meta(try decode(JobMetaEvent.self, from: event.data))
        case "download_progress": return .downloadProgress(try decode(DownloadProgress.self, from: event.data))
        case "transcribe_progress": return .transcribeProgress(try decode(TranscribeProgress.self, from: event.data))
        case "summary_chunk": return .cumulativeSummary(try decode(SummaryChunk.self, from: event.data).text)
        case "summary_segment": return .summaryProgress(try decode(SummarySegmentProgress.self, from: event.data))
        case "error": return .error(try decode(JobErrorEvent.self, from: event.data))
        default: throw APIError.decoding
        }
    }

    private static func distillEvent(from event: ServerSentEvent) throws -> DistillEvent {
        guard event.name == "status" else { throw APIError.decoding }
        let probe = try decode(DistillSnapshotProbe.self, from: event.data)
        if probe.id != nil {
            return .snapshot(try decode(DistillRun.self, from: event.data))
        }
        return .status(try decode(DistillStatusUpdate.self, from: event.data))
    }

    private static func sseValue(for field: String, in line: String) -> String? {
        let prefix = "\(field):"
        guard line.hasPrefix(prefix) else { return nil }
        let value = line.dropFirst(prefix.count)
        return value.hasPrefix(" ") ? String(value.dropFirst()) : String(value)
    }

    private static func decode<Response: Decodable>(_ type: Response.Type, from data: Data) throws -> Response {
        do {
            return try decoder.decode(type, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    private static func errorMessage(from data: Data) -> String? {
        if let envelope = try? decoder.decode(ErrorEnvelope.self, from: data) {
            return envelope.detail
        }
        if let envelope = try? decoder.decode(ValidationErrorEnvelope.self, from: data) {
            return envelope.detail.first?.msg
        }
        return nil
    }
}

private struct JobResponse: Decodable {
    let job: Job
}

private struct CreateJobRequest: Encodable {
    let url: String
    let options: JobOptionsRequest
    let dedupe: Bool
}

private struct JobOptionsEnvelope: Encodable {
    let options: JobOptionsRequest
}

private struct JobOptionsRequest: Encodable {
    let emailEnabled: Bool?
}

private struct BulkDeleteExecuteRequest: Encodable {
    let previewToken: String
}

private struct SoftDeleteDocumentRequest: Encodable {
    let reason: String?
}

private struct PurgeDocumentRequest: Encodable {
    let confirm: Bool
    let confirmTitle: String
}

private struct LifecycleDocumentResponse: Decodable {
    let document: LifecycleDocument
}

private struct StartDistillRequest: Encodable {
    let videoLimit: Int
}

private struct DistillRunResponse: Decodable {
    let run: DistillRun
}

private struct LatestDistillResponse: Decodable {
    let run: DistillRun?
}

private struct SummaryChunk: Decodable {
    let text: String
}

private struct DistillSnapshotProbe: Decodable {
    let id: String?
}

private struct ServerSentEvent {
    let name: String
    let data: Data

    init?(name: String, dataLines: [String]) {
        guard !dataLines.isEmpty else { return nil }
        self.name = name
        data = Data(dataLines.joined(separator: "\n").utf8)
    }
}

private struct ErrorEnvelope: Decodable {
    let detail: String
}

private struct ValidationErrorEnvelope: Decodable {
    struct Item: Decodable { let msg: String }
    let detail: [Item]
}

private extension Array where Element == URLQueryItem {
    mutating func appendCursor(_ cursor: CursorValue?) {
        if let cursor { append(URLQueryItem(name: "cursor", value: cursor.raw)) }
    }
}

private extension String {
    var escapingPathComponent: String {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/")
        return addingPercentEncoding(withAllowedCharacters: allowed) ?? self
    }
}

enum ServerEndpoint {
    static func parse(_ rawValue: String) throws -> URL {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw APIError.invalidServerAddress }
        let candidate = trimmed.contains("://") ? trimmed : "http://\(trimmed)"
        guard var components = URLComponents(string: candidate),
              let scheme = components.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              components.host?.isEmpty == false,
              components.user == nil,
              components.query == nil,
              components.fragment == nil else {
            throw APIError.invalidServerAddress
        }
        components.scheme = scheme
        while !components.path.isEmpty && components.path.hasSuffix("/") {
            components.path.removeLast()
        }
        guard let url = components.url else { throw APIError.invalidServerAddress }
        return url
    }
}
