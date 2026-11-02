import Foundation
import Observation

@MainActor
@Observable
final class LibraryViewModel {
    private(set) var items: [LibraryItem] = []
    private(set) var activeJob: Job?
    private(set) var total = 0
    private(set) var nextCursor: CursorValue?
    private(set) var selectedUP: String?
    private(set) var selectedUPName: String?
    private(set) var selectedTag: String?
    var isLoading = false
    var isLoadingMore = false
    var errorMessage: String?

    private var generation = 0

    var hasFilters: Bool { selectedUP != nil || selectedTag != nil }

    func load(using service: any BiriServicing) async {
        generation += 1
        let currentGeneration = generation
        let up = selectedUP
        let tag = selectedTag
        isLoading = true
        isLoadingMore = false
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            async let pageRequest = page(using: service, cursor: nil, up: up, tag: tag)
            async let activeRequest = service.jobs(filter: .running, cursor: nil, limit: 1)
            let page = try await pageRequest
            guard currentGeneration == generation else { return }
            items = page.items
            total = page.total
            nextCursor = page.nextCursor
            isLoading = false

            let activePage = try? await activeRequest
            guard currentGeneration == generation else { return }
            activeJob = activePage?.jobs.first
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func loadMore(using service: any BiriServicing) async {
        guard let nextCursor, !isLoading, !isLoadingMore else { return }
        let currentGeneration = generation
        let requestedCursor = nextCursor
        let up = selectedUP
        let tag = selectedTag
        isLoadingMore = true
        defer { if currentGeneration == generation { isLoadingMore = false } }
        do {
            let page = try await page(using: service, cursor: requestedCursor, up: up, tag: tag)
            guard currentGeneration == generation,
                  self.nextCursor == requestedCursor,
                  self.selectedUP == up,
                  self.selectedTag == tag else { return }
            let existingIDs = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !existingIDs.contains($0.id) })
            self.nextCursor = page.nextCursor
            total = page.total
        } catch {
            if currentGeneration == generation, !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }

    func filterByUP(mid: Int, name: String?, using service: any BiriServicing) async {
        selectedUP = String(mid)
        selectedUPName = name?.isEmpty == false ? name : nil
        clearResults()
        await load(using: service)
    }

    func filterByTag(_ tag: String, using service: any BiriServicing) async {
        let trimmed = tag.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        selectedTag = trimmed
        clearResults()
        await load(using: service)
    }

    func removeUPFilter(using service: any BiriServicing) async {
        guard selectedUP != nil else { return }
        selectedUP = nil
        selectedUPName = nil
        clearResults()
        await load(using: service)
    }

    func removeTagFilter(using service: any BiriServicing) async {
        guard selectedTag != nil else { return }
        selectedTag = nil
        clearResults()
        await load(using: service)
    }

    private func clearResults() {
        items = []
        total = 0
        nextCursor = nil
    }

    private func page(
        using service: any BiriServicing,
        cursor: CursorValue?,
        up: String?,
        tag: String?
    ) async throws -> LibraryPage {
        if let lifecycle = service as? any LibraryLifecycleServicing {
            return try await lifecycle.library(cursor: cursor, limit: 30, up: up, tag: tag)
        }
        guard up == nil, tag == nil else {
            throw APIError.http(status: 400, message: "当前连接不支持笔记筛选")
        }
        return try await service.library(cursor: cursor, limit: 30)
    }
}

@MainActor
@Observable
final class SearchViewModel {
    var query = ""
    var scope: SearchScope = .all
    private(set) var groups: [SearchGroup] = []
    private(set) var nextCursor: CursorValue?
    private(set) var partial: [String] = []
    private(set) var submittedQuery = ""
    private var submittedScope: SearchScope = .all
    var isLoading = false
    var isLoadingMore = false
    var errorMessage: String?

    private var generation = 0

    func clear() {
        generation += 1
        query = ""
        groups = []
        nextCursor = nil
        partial = []
        submittedQuery = ""
        submittedScope = .all
        errorMessage = nil
        isLoading = false
        isLoadingMore = false
    }

    func search(using service: any BiriServicing) async {
        generation += 1
        let currentGeneration = generation
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedScope = scope
        guard !trimmed.isEmpty else {
            groups = []
            nextCursor = nil
            partial = []
            submittedQuery = ""
            submittedScope = .all
            errorMessage = nil
            isLoading = false
            return
        }
        isLoading = true
        isLoadingMore = false
        nextCursor = nil
        partial = []
        submittedQuery = trimmed
        submittedScope = requestedScope
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            let page = try await service.search(query: trimmed, scope: requestedScope, cursor: nil)
            guard currentGeneration == generation else { return }
            groups = page.groups
            nextCursor = page.nextCursor
            partial = page.partial
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func loadMore(using service: any BiriServicing) async {
        guard let nextCursor, !isLoading, !isLoadingMore else { return }
        let currentGeneration = generation
        let requestedCursor = nextCursor
        let query = submittedQuery
        let scope = submittedScope
        isLoadingMore = true
        defer { if currentGeneration == generation { isLoadingMore = false } }
        do {
            let page = try await service.search(query: query, scope: scope, cursor: requestedCursor)
            guard currentGeneration == generation, self.nextCursor == requestedCursor else { return }
            let existingIDs = Set(groups.map(\.id))
            groups.append(contentsOf: page.groups.filter { !existingIDs.contains($0.id) })
            self.nextCursor = page.nextCursor
            partial = page.partial
        } catch {
            if currentGeneration == generation, !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }
}

extension Error {
    var isRequestCancellation: Bool {
        if self is CancellationError { return true }
        if let error = self as? JobBatchDeleteError { return error.underlying.isRequestCancellation }
        if case .network(let error) = self as? APIError { return error.code == .cancelled }
        return false
    }
}
