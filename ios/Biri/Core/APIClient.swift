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
    func runtimeConfiguration() async throws -> RuntimeConfiguration
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

struct APIClient: BiriServicing {
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
        case .completed, .failed:
            query.append(URLQueryItem(name: "terminal_only", value: "true"))
        case .all:
            break
        }
        query.appendCursor(cursor)
        return try await get(path: "/v1/jobs", query: query)
    }

    func job(id: String) async throws -> Job {
        let response: JobResponse = try await get(path: "/v1/jobs/\(id.escapingPathComponent)")
        return response.job
    }

    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        try await get(path: "/v1/config/runtime")
    }

    private func get<Response: Decodable>(path: String, query: [URLQueryItem] = []) async throws -> Response {
        let endpoint = baseURL.appendingPathComponent(path)
        guard var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidServerAddress
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.invalidServerAddress }

        var request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 30)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
            guard (200..<300).contains(response.statusCode) else {
                throw APIError.http(status: response.statusCode, message: Self.errorMessage(from: data))
            }
            do {
                return try Self.decoder.decode(Response.self, from: data)
            } catch {
                throw APIError.decoding
            }
        } catch let error as APIError {
            throw error
        } catch let error as URLError {
            throw APIError.network(error)
        } catch {
            throw error
        }
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
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
