import Foundation
import Observation

@MainActor
@Observable
final class JobsViewModel {
    var filter: JobFilter = .all
    private(set) var jobs: [Job] = []
    private(set) var nextCursor: CursorValue?
    var isLoading = false
    var isLoadingMore = false
    var errorMessage: String?

    private var generation = 0
    private var firstPageIDs: Set<String> = []
    var visibleJobs: [Job] { jobs.filter(filter.matches) }
    var hasActiveJobs: Bool { visibleJobs.contains { $0.status.isActive } }
    var pollKey: String { "\(filter.rawValue)-\(hasActiveJobs)" }

    func load(using service: any BiriServicing, quietly: Bool = false) async {
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

@MainActor
@Observable
final class JobDetailViewModel {
    let jobID: String
    private(set) var job: Job?
    var isLoading = false
    var errorMessage: String?

    private var generation = 0
    init(jobID: String) { self.jobID = jobID }

    func load(using service: any BiriServicing, quietly: Bool = false) async {
        generation += 1
        let currentGeneration = generation
        if !quietly { isLoading = true }
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            let loaded = try await service.job(id: jobID)
            guard currentGeneration == generation else { return }
            job = loaded
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }
}
