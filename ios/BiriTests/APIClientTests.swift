import XCTest
@testable import Biri

final class APIClientTests: XCTestCase {
    func testLibraryRequestAddsBearerCursorAndLimit() async throws {
        let client = makeClient { request in
            XCTAssertEqual(request.url?.path(), "/v1/library")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
            let query = request.url?.query() ?? ""
            XCTAssertTrue(query.contains("limit=30"))
            XCTAssertTrue(query.contains("cursor=next-page"))
            return self.response(url: request.url!, status: 200, json: #"{"items":[],"next_cursor":null,"total":0}"#)
        }

        let page = try await client.library(cursor: CursorValue("next-page"), limit: 30)
        XCTAssertEqual(page.total, 0)
    }

    func testSearchRequestEncodesQueryAndDecodesResults() async throws {
        let client = makeClient { request in
            XCTAssertEqual(request.url?.path(), "/v1/library/search")
            let components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
            XCTAssertEqual(components?.queryItems?.first { $0.name == "q" }?.value, "注意力")
            XCTAssertEqual(components?.queryItems?.first { $0.name == "scope" }?.value, "all")
            XCTAssertEqual(components?.queryItems?.first { $0.name == "limit" }?.value, "20")
            return self.response(
                url: request.url!, status: 200,
                json: #"{"groups":[{"document_id":"doc-1","job_id":null,"title":"注意力","author":"作者","provider":"bilibili","source_url":null,"saved_at":1000,"tldr":null,"duration":10,"legacy":false,"hits":[{"kind":"notes","chunk_ord":1,"snippet":"匹配内容","start_sec":null}]}],"next_cursor":null,"partial":[]}"#
            )
        }

        let page = try await client.search(query: "注意力", scope: .all, cursor: nil)

        XCTAssertEqual(page.groups.first?.displayTitle, "注意力")
        XCTAssertEqual(page.groups.first?.hits.first?.snippet, "匹配内容")
    }

    func testUnauthorizedResponseUsesReadableMessage() async {
        let client = makeClient { request in
            self.response(url: request.url!, status: 401, json: #"{"detail":"Invalid API token"}"#)
        }

        do {
            _ = try await client.runtimeConfiguration()
            XCTFail("Expected an unauthorized error")
        } catch let APIError.http(status, message) {
            XCTAssertEqual(status, 401)
            XCTAssertEqual(message, "Invalid API token")
            XCTAssertEqual(APIError.http(status: status, message: message).localizedDescription, "访问令牌不正确，请检查后重试")
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testServerAddressValidationAcceptsAndNormalizes() throws {
        XCTAssertEqual(try ServerEndpoint.parse("192.168.1.10:8000/").absoluteString, "http://192.168.1.10:8000")
        XCTAssertEqual(try ServerEndpoint.parse("https://example.com///").absoluteString, "https://example.com")
    }

    func testServerAddressValidationRejectsUnsupportedInput() {
        XCTAssertThrowsError(try ServerEndpoint.parse("ftp://example.com"))
        XCTAssertThrowsError(try ServerEndpoint.parse("https://example.com?token=value"))
        XCTAssertThrowsError(try ServerEndpoint.parse("https://user:pass@example.com"))
        XCTAssertThrowsError(try ServerEndpoint.parse(""))
    }

    private func makeClient(handler: @escaping (URLRequest) -> (HTTPURLResponse, Data)) -> APIClient {
        StubURLProtocol.handler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return APIClient(baseURL: URL(string: "https://example.com")!, token: "test-token", session: session)
    }

    private func response(url: URL, status: Int, json: String) -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!,
            Data(json.utf8)
        )
    }
}

private final class StubURLProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
