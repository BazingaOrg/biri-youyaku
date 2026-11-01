import Foundation
import Observation

@MainActor
@Observable
final class LibraryViewModel {
    private(set) var items: [LibraryItem] = []
    private(set) var activeJob: Job?
    private(set) var total = 0
    private(set) var nextCursor: CursorValue?
    var isLoading = false
    var isLoadingMore = false
    var errorMessage: String?

    private var generation = 0

    func load(using service: any BiriServicing) async {
        generation += 1
        let currentGeneration = generation
        isLoading = true
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            async let pageRequest = service.library(cursor: nil, limit: 30)
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
        isLoadingMore = true
        defer { isLoadingMore = false }
        do {
            let page = try await service.library(cursor: nextCursor, limit: 30)
            guard currentGeneration == generation, self.nextCursor == nextCursor else { return }
            let existingIDs = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !existingIDs.contains($0.id) })
            self.nextCursor = page.nextCursor
        } catch {
            if currentGeneration == generation, !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
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
        isLoadingMore = true
        defer { isLoadingMore = false }
        do {
            let page = try await service.search(query: submittedQuery, scope: submittedScope, cursor: nextCursor)
            guard currentGeneration == generation, self.nextCursor == nextCursor else { return }
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
        if case .network(let error) = self as? APIError { return error.code == .cancelled }
        return false
    }
}
