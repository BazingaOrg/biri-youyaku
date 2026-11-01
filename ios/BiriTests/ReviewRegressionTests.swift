import XCTest
@testable import Biri

@MainActor
final class ReviewRegressionTests: XCTestCase {
    func testCredentialsAreOnlyReusedForSameServer() {
        let serverA = URL(string: "https://a.example.com")!
        let serverB = URL(string: "https://b.example.com")!

        XCTAssertEqual(
            AppModel.credentialToken(currentURL: serverA, newURL: serverA, enteredToken: "", savedToken: "stored"),
            "stored"
        )
        XCTAssertNil(AppModel.credentialToken(currentURL: serverA, newURL: serverB, enteredToken: "", savedToken: "stored"))
        XCTAssertTrue(AppModel.shouldDiscardSavedToken(currentURL: serverA, newURL: serverB, enteredToken: ""))
        XCTAssertEqual(
            AppModel.credentialToken(currentURL: serverA, newURL: serverB, enteredToken: "new-token", savedToken: "stored"),
            "new-token"
        )
        XCTAssertFalse(AppModel.shouldDiscardSavedToken(currentURL: serverA, newURL: serverB, enteredToken: "new-token"))
    }

    func testRemovingTokenClearsCredentialAndConnectionStatus() async throws {
        let suiteName = "ReviewRegressionTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let credentials = MemoryCredentialStore(token: nil)
        let model = AppModel(
            defaults: defaults,
            keychain: credentials,
            validateConnection: { _, _ in RuntimeConfiguration(authMode: "api_token", knowledgeSearchEnabled: true) }
        )
        try await model.connect(address: "https://a.example.com", enteredToken: "credential")
        XCTAssertNotNil(model.connectionInfo)

        try model.clearSavedToken()

        XCTAssertNil(credentials.token)
        XCTAssertNil(model.connectionInfo)
    }

    func testOnlyLatestConnectionCanCommitServerAndCredentials() async throws {
        let serverA = URL(string: "https://a.example.com")!
        let serverB = URL(string: "https://b.example.com")!
        let suiteName = "ReviewRegressionTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        defaults.set(serverA.absoluteString, forKey: "server-url")
        let credentials = MemoryCredentialStore(token: "first-credential")
        let control = ConnectionControl()
        let model = AppModel(
            defaults: defaults,
            keychain: credentials,
            validateConnection: { url, token in try await control.validate(url: url, token: token) }
        )

        let oldConnection = Task { try await model.connect(address: serverB.absoluteString, enteredToken: "second-credential") }
        guard await waitUntil({ control.continuations[serverB.host!] != nil }) else {
            control.shouldSuspend = false
            control.resumeAll()
            try? await oldConnection.value
            XCTFail("The first connection did not reach its controlled validation")
            return
        }
        let newConnection = Task { try await model.connect(address: serverA.absoluteString, enteredToken: "") }
        guard await waitUntil({ control.continuations[serverA.host!] != nil }) else {
            control.shouldSuspend = false
            control.resumeAll()
            try? await oldConnection.value
            try? await newConnection.value
            XCTFail("The second connection did not reach its controlled validation")
            return
        }

        XCTAssertEqual(control.calls.first { $0.url == serverB }?.token, "second-credential")
        XCTAssertEqual(control.calls.first { $0.url == serverA }?.token, "first-credential")
        control.resume(serverB)
        do {
            try await oldConnection.value
            XCTFail("A superseded connection must not commit")
        } catch is CancellationError {
        } catch {
            XCTFail("Unexpected connection error: \(error)")
        }
        control.resume(serverA)
        try await newConnection.value

        XCTAssertEqual(model.serverURL, serverA)
        XCTAssertEqual(credentials.token, "first-credential")
        XCTAssertEqual(model.connectionRevision, 1)
    }

    func testAudioOnlyCompletedJobDoesNotOfferReading() {
        XCTAssertNil(makeJob(id: "audio", status: .completed).destination)
        XCTAssertNil(makeJob(id: "empty", status: .completed, summary: "").destination)
        XCTAssertNotNil(makeJob(id: "note", status: .completed, summaryAvailable: true).destination)
        XCTAssertNotNil(makeJob(id: "document", status: .completed, documentId: "doc-1").destination)
    }

    func testSearchPaginationUsesSubmittedQueryAndScope() async {
        let service = ControlledService()
        service.firstSearchPages = [
            SearchPage(groups: [makeGroup(id: "first", title: "First")], nextCursor: CursorValue("next"), partial: [])
        ]
        service.nextSearchPage = SearchPage(groups: [makeGroup(id: "second", title: "Second")], nextCursor: nil, partial: [])
        let viewModel = SearchViewModel()
        viewModel.query = "first"
        await viewModel.search(using: service)

        viewModel.query = "edited"
        viewModel.scope = .subs
        await viewModel.loadMore(using: service)

        XCTAssertEqual(service.searchRequests.map(\.query), ["first", "first"])
        XCTAssertEqual(service.searchRequests.last?.scope.rawValue, SearchScope.all.rawValue)
        XCTAssertEqual(viewModel.groups.map(\.id).count, 2)
    }

    func testScopeChangeSupersedesInflightSearchAndPagination() async {
        let service = ControlledService()
        let oldGroup = makeGroup(id: "old", title: "Old scope")
        let newGroup = makeGroup(id: "new", title: "New scope")
        service.firstSearchPages = [
            SearchPage(groups: [newGroup], nextCursor: CursorValue("new-next"), partial: [])
        ]
        service.nextSearchPage = SearchPage(groups: [], nextCursor: nil, partial: [])
        service.suspendFirstSearch = true
        let viewModel = SearchViewModel()
        viewModel.query = "keyword"
        viewModel.scope = .all

        let oldSearch = Task { await viewModel.search(using: service) }
        guard await waitUntil({ service.firstSearchContinuation != nil }) else {
            service.suspendFirstSearch = false
            await oldSearch.value
            XCTFail("The initial search was not suspended")
            return
        }
        XCTAssertEqual(viewModel.submittedQuery, "keyword")

        viewModel.scope = .notes
        await viewModel.search(using: service)
        service.firstSearchContinuation?.resume(
            returning: SearchPage(groups: [oldGroup], nextCursor: CursorValue("old-next"), partial: [])
        )
        await oldSearch.value
        await viewModel.loadMore(using: service)

        XCTAssertEqual(viewModel.groups.map(\.id), [newGroup.id])
        XCTAssertEqual(service.searchRequests.map(\.scope), [.all, .notes, .notes])
        XCTAssertEqual(service.searchRequests.last?.cursor, CursorValue("new-next"))
    }

    func testBlankSearchClearsSubmittedQueryWithoutRequesting() async {
        let service = ControlledService()
        service.firstSearchPages = [
            SearchPage(groups: [makeGroup(id: "first", title: "First")], nextCursor: CursorValue("next"), partial: [])
        ]
        let viewModel = SearchViewModel()
        viewModel.query = "first"
        await viewModel.search(using: service)

        viewModel.query = "   "
        await viewModel.search(using: service)

        XCTAssertTrue(viewModel.submittedQuery.isEmpty)
        XCTAssertTrue(viewModel.groups.isEmpty)
        XCTAssertNil(viewModel.nextCursor)
        XCTAssertEqual(service.searchRequests.count, 1)
    }

    func testLateSearchPageCannotContaminateNewQuery() async {
        let service = ControlledService()
        let oldGroup = makeGroup(id: "old", title: "Alpha")
        let newGroup = makeGroup(id: "new", title: "Beta")
        service.firstSearchPages = [
            SearchPage(groups: [oldGroup], nextCursor: CursorValue("old-cursor"), partial: []),
            SearchPage(groups: [newGroup], nextCursor: nil, partial: [])
        ]
        service.nextSearchPage = SearchPage(groups: [makeGroup(id: "stale", title: "Stale")], nextCursor: CursorValue("stale-cursor"), partial: [])
        let viewModel = SearchViewModel()
        viewModel.query = "alpha"
        await viewModel.search(using: service)

        service.suspendNextSearch = true
        let oldPage = Task { await viewModel.loadMore(using: service) }
        guard await waitUntil({ service.searchContinuation != nil }) else {
            service.suspendNextSearch = false
            service.searchContinuation?.resume(returning: service.nextSearchPage!)
            await oldPage.value
            XCTFail("The old search page was not suspended")
            return
        }
        viewModel.query = "beta"
        await viewModel.search(using: service)
        service.searchContinuation?.resume(returning: service.nextSearchPage!)
        await oldPage.value

        XCTAssertEqual(viewModel.groups.map(\.id), [newGroup.id])
        XCTAssertNil(viewModel.nextCursor)
    }

    func testLibraryRendersBeforeActiveJobRequestCompletes() async {
        let service = ControlledService()
        let item = makeLibraryItem(id: "note")
        let activeJob = makeJob(id: "active", status: .summarizing)
        service.firstLibraryPages = [LibraryPage(items: [item], nextCursor: nil, total: 1)]
        service.firstJobPages = [JobPage(jobs: [activeJob], nextCursor: nil)]
        service.suspendFirstJobs = true
        let viewModel = LibraryViewModel()

        let load = Task { await viewModel.load(using: service) }
        guard await waitUntil({ !viewModel.items.isEmpty }) else {
            service.suspendFirstJobs = false
            service.firstJobsContinuation?.resume(returning: JobPage(jobs: [activeJob], nextCursor: nil))
            await load.value
            XCTFail("Library items waited for the active-job request")
            return
        }
        XCTAssertFalse(viewModel.isLoading)
        service.firstJobsContinuation?.resume(returning: JobPage(jobs: [activeJob], nextCursor: nil))
        await load.value

        XCTAssertEqual(viewModel.items.map(\.id), [item.id])
        XCTAssertEqual(viewModel.activeJob?.id, activeJob.id)
    }

    func testLateLibraryPageCannotContaminateReload() async {
        let service = ControlledService()
        let oldItem = makeLibraryItem(id: "old")
        let newItem = makeLibraryItem(id: "new")
        service.firstLibraryPages = [
            LibraryPage(items: [oldItem], nextCursor: CursorValue("old-cursor"), total: 2),
            LibraryPage(items: [newItem], nextCursor: nil, total: 1)
        ]
        service.nextLibraryPage = LibraryPage(items: [makeLibraryItem(id: "stale")], nextCursor: CursorValue("stale-cursor"), total: 2)
        service.firstJobPages = [JobPage(jobs: [], nextCursor: nil), JobPage(jobs: [], nextCursor: nil)]
        let viewModel = LibraryViewModel()
        await viewModel.load(using: service)

        service.suspendNextLibrary = true
        let oldPage = Task { await viewModel.loadMore(using: service) }
        guard await waitUntil({ service.libraryContinuation != nil }) else {
            service.suspendNextLibrary = false
            service.libraryContinuation?.resume(returning: service.nextLibraryPage!)
            await oldPage.value
            XCTFail("The old library page was not suspended")
            return
        }
        await viewModel.load(using: service)
        service.libraryContinuation?.resume(returning: service.nextLibraryPage!)
        await oldPage.value

        XCTAssertEqual(viewModel.items.map(\.id), [newItem.id])
        XCTAssertNil(viewModel.nextCursor)
    }

    func testLateJobPageCannotContaminateNewFilter() async {
        let service = ControlledService()
        service.firstJobPages = [
            JobPage(jobs: [makeJob(id: "running", status: .summarizing)], nextCursor: CursorValue("old-cursor")),
            JobPage(jobs: [makeJob(id: "done", status: .completed)], nextCursor: nil)
        ]
        service.nextJobPage = JobPage(jobs: [makeJob(id: "stale", status: .failed)], nextCursor: CursorValue("stale-cursor"))
        let viewModel = JobsViewModel()
        await viewModel.load(using: service)

        service.suspendNextJobs = true
        let oldPage = Task { await viewModel.loadMore(using: service) }
        guard await waitUntil({ service.jobsContinuation != nil }) else {
            service.suspendNextJobs = false
            service.jobsContinuation?.resume(returning: service.nextJobPage!)
            await oldPage.value
            XCTFail("The old job page was not suspended")
            return
        }
        viewModel.filter = .completed
        await viewModel.load(using: service)
        service.jobsContinuation?.resume(returning: service.nextJobPage!)
        await oldPage.value

        XCTAssertEqual(viewModel.jobs.map(\.id), ["done"])
        XCTAssertNil(viewModel.nextCursor)
    }

    func testFailedFilterLoadsUntilFirstMatchingPage() async {
        let service = ControlledService()
        service.firstJobPages = [
            JobPage(jobs: [makeJob(id: "done", status: .completed)], nextCursor: CursorValue("next"))
        ]
        service.nextJobPage = JobPage(jobs: [makeJob(id: "failed", status: .failed)], nextCursor: CursorValue("more"))
        let viewModel = JobsViewModel()
        viewModel.filter = .failed

        await viewModel.load(using: service)

        XCTAssertEqual(viewModel.visibleJobs.map(\.id), ["failed"])
        XCTAssertEqual(viewModel.nextCursor, CursorValue("more"))
    }

    func testFailedFilterExhaustsPagesBeforeShowingEmptyState() async {
        let service = ControlledService()
        service.firstJobPages = [
            JobPage(jobs: [makeJob(id: "done", status: .completed)], nextCursor: CursorValue("next"))
        ]
        service.nextJobPage = JobPage(jobs: [makeJob(id: "canceled", status: .canceled)], nextCursor: nil)
        let viewModel = JobsViewModel()
        viewModel.filter = .failed

        await viewModel.load(using: service)

        XCTAssertTrue(viewModel.visibleJobs.isEmpty)
        XCTAssertNil(viewModel.nextCursor)
    }

    func testQuietPollingPreservesLoadedHistoryAndCursor() async {
        let service = ControlledService()
        service.firstJobPages = [
            JobPage(
                jobs: [makeJob(id: "active", status: .summarizing), makeJob(id: "leaving", status: .summarizing)],
                nextCursor: CursorValue("page-two")
            ),
            JobPage(jobs: [makeJob(id: "active", status: .completed)], nextCursor: CursorValue("new-first-cursor"))
        ]
        service.nextJobPage = JobPage(jobs: [makeJob(id: "history", status: .completed)], nextCursor: CursorValue("page-three"))
        let viewModel = JobsViewModel()
        await viewModel.load(using: service)
        await viewModel.loadMore(using: service)

        await viewModel.load(using: service, quietly: true)

        XCTAssertEqual(viewModel.jobs.map(\.id), ["active", "history"])
        XCTAssertEqual(viewModel.jobs.first?.status, .completed)
        XCTAssertEqual(viewModel.nextCursor, CursorValue("page-three"))
    }

    func testQuietPollingDeduplicatesHistoryPromotedToFirstPage() async {
        let service = ControlledService()
        service.firstJobPages = [
            JobPage(
                jobs: [makeJob(id: "active", status: .summarizing), makeJob(id: "leaving", status: .summarizing)],
                nextCursor: CursorValue("page-two")
            ),
            JobPage(jobs: [makeJob(id: "history", status: .completed)], nextCursor: CursorValue("new-first-cursor"))
        ]
        service.nextJobPage = JobPage(jobs: [makeJob(id: "history", status: .summarizing)], nextCursor: CursorValue("page-three"))
        let viewModel = JobsViewModel()
        await viewModel.load(using: service)
        await viewModel.loadMore(using: service)

        await viewModel.load(using: service, quietly: true)

        XCTAssertEqual(viewModel.jobs.map(\.id), ["history"])
        XCTAssertEqual(viewModel.jobs.first?.status, .completed)
        XCTAssertEqual(viewModel.nextCursor, CursorValue("new-first-cursor"))
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func makeLibraryItem(id: String) -> Biri.LibraryItem {
        Biri.LibraryItem(
            id: id, documentId: id, jobId: nil, title: id, author: "作者", provider: "bilibili",
            duration: 10, tags: [], tldr: nil, savedAt: 1000, sourceUrl: nil, legacy: false
        )
    }

    private func makeJob(
        id: String,
        status: JobStatus,
        summaryAvailable: Bool = false,
        documentId: String? = nil,
        summary: String? = nil
    ) -> Job {
        Job(
            id: id, url: "https://example.com", title: id, author: "作者", duration: 10,
            status: status, errorStage: nil, errorMessage: nil, createdAt: 1000, updatedAt: 2000,
            completedAt: status == .completed ? 2000 : nil, summaryAvailable: summaryAvailable,
            documentId: documentId, summary: summary, transcript: nil
        )
    }

    private func makeGroup(id: String, title: String) -> SearchGroup {
        SearchGroup(
            documentId: id, jobId: nil, title: title, author: "作者", provider: "bilibili",
            sourceUrl: nil, savedAt: 1000, tldr: nil, duration: nil, legacy: false, hits: []
        )
    }
}

private final class MemoryCredentialStore: CredentialStoring {
    var token: String?
    init(token: String?) { self.token = token }
    func readToken() -> String? { token }
    func saveToken(_ token: String) throws { self.token = token }
    func deleteToken() throws { token = nil }
}

@MainActor
private final class ConnectionControl {
    struct Call {
        let url: URL
        let token: String?
    }

    private(set) var calls: [Call] = []
    var continuations: [String: CheckedContinuation<RuntimeConfiguration, Never>] = [:]
    var shouldSuspend = true

    func validate(url: URL, token: String?) async throws -> RuntimeConfiguration {
        calls.append(Call(url: url, token: token))
        if shouldSuspend {
            return await withCheckedContinuation { continuations[url.host!] = $0 }
        }
        return RuntimeConfiguration(authMode: "api_token", knowledgeSearchEnabled: true)
    }

    func resume(_ url: URL) {
        continuations.removeValue(forKey: url.host!)?.resume(
            returning: RuntimeConfiguration(authMode: "api_token", knowledgeSearchEnabled: true)
        )
    }

    func resumeAll() {
        let pending = continuations
        continuations.removeAll()
        for continuation in pending.values {
            continuation.resume(returning: RuntimeConfiguration(authMode: "api_token", knowledgeSearchEnabled: true))
        }
    }
}

private final class ControlledService: BiriServicing {
    var firstLibraryPages: [LibraryPage] = []
    var nextLibraryPage: LibraryPage?
    var suspendNextLibrary = false
    var libraryContinuation: CheckedContinuation<LibraryPage, Never>?

    private(set) var searchRequests: [(query: String, scope: SearchScope, cursor: CursorValue?)] = []
    var firstSearchPages: [SearchPage] = []
    var nextSearchPage: SearchPage?
    var suspendFirstSearch = false
    var firstSearchContinuation: CheckedContinuation<SearchPage, Never>?
    var suspendNextSearch = false
    var searchContinuation: CheckedContinuation<SearchPage, Never>?

    var firstJobPages: [JobPage] = []
    var nextJobPage: JobPage?
    var suspendFirstJobs = false
    var firstJobsContinuation: CheckedContinuation<JobPage, Never>?
    var suspendNextJobs = false
    var jobsContinuation: CheckedContinuation<JobPage, Never>?

    func library(cursor: CursorValue?, limit: Int) async throws -> LibraryPage {
        if cursor != nil {
            if suspendNextLibrary {
                return await withCheckedContinuation { libraryContinuation = $0 }
            }
            return nextLibraryPage!
        }
        return firstLibraryPages.removeFirst()
    }

    func search(query: String, scope: SearchScope, cursor: CursorValue?) async throws -> SearchPage {
        searchRequests.append((query, scope, cursor))
        if cursor == nil && suspendFirstSearch {
            suspendFirstSearch = false
            return await withCheckedContinuation { firstSearchContinuation = $0 }
        }
        if cursor != nil {
            if suspendNextSearch {
                return await withCheckedContinuation { searchContinuation = $0 }
            }
            return nextSearchPage!
        }
        return firstSearchPages.removeFirst()
    }

    func jobs(filter: JobFilter, cursor: CursorValue?, limit: Int) async throws -> JobPage {
        if cursor == nil && suspendFirstJobs {
            return await withCheckedContinuation { firstJobsContinuation = $0 }
        }
        if cursor != nil {
            if suspendNextJobs {
                return await withCheckedContinuation { jobsContinuation = $0 }
            }
            return nextJobPage!
        }
        return firstJobPages.removeFirst()
    }

    func document(id: String) async throws -> DocumentContent { throw APIError.http(status: 404, message: nil) }
    func job(id: String) async throws -> Job { throw APIError.http(status: 404, message: nil) }
    func runtimeConfiguration() async throws -> RuntimeConfiguration {
        RuntimeConfiguration(authMode: "none", knowledgeSearchEnabled: true)
    }
}
