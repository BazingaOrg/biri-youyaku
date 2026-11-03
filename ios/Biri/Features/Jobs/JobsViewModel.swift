import Foundation
import Observation

@MainActor
@Observable
final class JobsViewModel {
    var filter: JobFilter = .all {
        didSet {
            if oldValue != filter { exitSelection() }
        }
    }
    private(set) var jobs: [Job] = []
    private(set) var nextCursor: CursorValue?
    private(set) var selectedIDs: Set<String> = []
    var isSelecting = false
    var isLoading = false
    var isLoadingMore = false
    var isDeleting = false
    var errorMessage: String?

    private var generation = 0
    private var isLoadInFlight = false
    private var pendingNonQuietLoad = false
    private var firstPageIDs: Set<String> = []
    var visibleJobs: [Job] { jobs.filter(filter.matches) }
    var hasActiveJobs: Bool { visibleJobs.contains { $0.status.isActive } }
    var pollKey: String { "\(filter.rawValue)-\(hasActiveJobs)" }
    var selectedCount: Int { deletableSelectedJobs.count }
    var canDeleteSelection: Bool { selectedCount > 0 && !isDeleting }

    private var deletableSelectedJobs: [Job] {
        visibleJobs.filter { selectedIDs.contains($0.id) && !$0.status.isActive }
    }

    func toggleSelection() {
        isSelecting.toggle()
        if !isSelecting { selectedIDs.removeAll() }
    }

    func exitSelection() {
        isSelecting = false
        selectedIDs.removeAll()
    }

    func toggleSelection(for job: Job) {
        guard isSelecting, !job.status.isActive, !isDeleting else { return }
        if selectedIDs.contains(job.id) {
            selectedIDs.remove(job.id)
        } else {
            selectedIDs.insert(job.id)
        }
    }

    func deleteSelected(using service: any JobMutationServicing) async {
        let ids = deletableSelectedJobs.map(\.id)
        await delete(ids: ids, using: service, exitSelectionAfterward: true)
    }

    func delete(job: Job, using service: any JobMutationServicing) async {
        guard !job.status.isActive else { return }
        await delete(ids: [job.id], using: service, exitSelectionAfterward: false)
    }

    private func delete(
        ids: [String],
        using service: any JobMutationServicing,
        exitSelectionAfterward: Bool
    ) async {
        guard !ids.isEmpty, !isDeleting else { return }
        isDeleting = true
        errorMessage = nil
        defer { isDeleting = false }

        do {
            try await service.deleteJobs(ids: ids)
            removeDeletedJobs(ids: ids)
            if exitSelectionAfterward { exitSelection() }
        } catch {
            if let batchError = error as? JobBatchDeleteError {
                removeDeletedJobs(ids: batchError.successfulIDs)
            }
            guard !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func removeDeletedJobs(ids: [String]) {
        let deletedIDs = Set(ids)
        jobs.removeAll { deletedIDs.contains($0.id) }
        firstPageIDs.subtract(deletedIDs)
        selectedIDs.subtract(deletedIDs)
    }

    func load(using service: any BiriServicing, quietly: Bool = false) async {
        guard !isLoadInFlight else {
            // Timer/foreground refreshes can share the current snapshot. A
            // filter-driven full load must run afterward with the latest state.
            if !quietly { pendingNonQuietLoad = true }
            return
        }
        isLoadInFlight = true
        var nextQuietly = quietly
        defer {
            isLoadInFlight = false
            pendingNonQuietLoad = false
        }
        while true {
            pendingNonQuietLoad = false
            await performLoad(using: service, quietly: nextQuietly)
            guard pendingNonQuietLoad else { break }
            nextQuietly = false
        }
    }

    private func performLoad(using service: any BiriServicing, quietly: Bool) async {
        generation += 1
        let currentGeneration = generation
        if !quietly { isLoading = true }
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            let preserveHistory = quietly && !visibleJobs.isEmpty
            var page = try await service.jobs(filter: filter, cursor: nil, limit: 50)
            let firstPageJobs = page.jobs
            guard currentGeneration == generation else { return }

            var seenCursors: Set<CursorValue> = []
            while !preserveHistory,
                  !page.jobs.contains(where: filter.matches),
                  let cursor = page.nextCursor,
                  !seenCursors.contains(cursor) {
                guard currentGeneration == generation else { return }
                seenCursors.insert(cursor)
                let nextPage = try await service.jobs(filter: filter, cursor: cursor, limit: 50)
                guard currentGeneration == generation else { return }
                let existingIDs = Set(page.jobs.map(\.id))
                page = JobPage(
                    jobs: page.jobs + nextPage.jobs.filter { !existingIDs.contains($0.id) },
                    nextCursor: nextPage.nextCursor
                )
            }

            if preserveHistory {
                let refreshedIDs = Set(page.jobs.map(\.id))
                let historicalJobs = jobs.filter { !firstPageIDs.contains($0.id) && !refreshedIDs.contains($0.id) }
                jobs = page.jobs + historicalJobs
                if historicalJobs.isEmpty { nextCursor = page.nextCursor }
            } else {
                jobs = page.jobs
                nextCursor = page.nextCursor
            }
            firstPageIDs = Set(firstPageJobs.map(\.id))
            let nonActiveIDs = Set(jobs.filter { !$0.status.isActive }.map(\.id))
            selectedIDs.formIntersection(nonActiveIDs)
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
            let page = try await service.jobs(filter: filter, cursor: nextCursor, limit: 50)
            guard currentGeneration == generation, self.nextCursor == nextCursor else { return }
            let existingIDs = Set(jobs.map(\.id))
            jobs.append(contentsOf: page.jobs.filter { !existingIDs.contains($0.id) })
            self.nextCursor = page.nextCursor
        } catch {
            if currentGeneration == generation, !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }
}
