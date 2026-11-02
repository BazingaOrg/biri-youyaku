import Foundation
import Observation

struct UPDestination: Hashable, Identifiable {
    let mid: Int
    let author: String

    var id: Int { mid }
}

enum UPCatalogFilter: String, CaseIterable, Identifiable {
    case all
    case unsummarized
    case summarized

    var id: String { rawValue }
    var label: String {
        switch self {
        case .all: "全部"
        case .unsummarized: "未生成"
        case .summarized: "已生成"
        }
    }

    func matches(_ video: UPVideo) -> Bool {
        switch self {
        case .all: true
        case .unsummarized: video.status != .completed && video.status?.isActive != true
        case .summarized: video.status == .completed
        }
    }
}

extension UPVideo {
    var readerDestination: ReaderDestination? {
        guard status == .completed, let id = documentId ?? jobId else { return nil }
        return ReaderDestination(
            id: id,
            title: title,
            kind: documentId == nil ? .job : .document
        )
    }

    var activeJobID: String? {
        status?.isActive == true ? jobId : nil
    }

    func updating(status: JobStatus, jobID: String) -> UPVideo {
        UPVideo(
            bvid: bvid,
            title: title,
            cover: cover,
            pubdate: pubdate,
            duration: duration,
            url: url,
            status: status,
            jobId: jobID,
            documentId: documentId
        )
    }
}

@MainActor
@Observable
final class UPCatalogViewModel {
    let mid: Int
    private(set) var author: String
    private(set) var videos: [UPVideo] = []
    private(set) var total = 0
    private(set) var page = 0
    private(set) var hasMore = false
    private(set) var submittedKeyword = ""
    private(set) var mutatingVideoIDs: Set<String> = []

    var query = ""
    var order: UPCatalogOrder = .pubdate
    var filter: UPCatalogFilter = .all
    var isLoading = false
    var isLoadingMore = false
    var errorMessage: String?

    private var generation = 0
    private var loadedOrder: UPCatalogOrder = .pubdate

    init(mid: Int, author: String) {
        self.mid = mid
        self.author = author
    }

    var visibleVideos: [UPVideo] { videos.filter(filter.matches) }
    var loadedSummarizedCount: Int { videos.count { $0.status == .completed } }

    func load(
        using service: any UPServicing & SourceServicing & JobMutationServicing,
        quietly: Bool = false
    ) async {
        generation += 1
        let currentGeneration = generation
        let keyword = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let requestedOrder = order
        let changesLoadedQuery = submittedKeyword != keyword || loadedOrder != requestedOrder
        submittedKeyword = keyword
        if changesLoadedQuery {
            videos = []
            total = 0
            page = 0
            hasMore = false
        }
        isLoadingMore = false
        if !quietly { isLoading = true }
        errorMessage = nil
        defer {
            if currentGeneration == generation { isLoading = false }
        }

        do {
            let loaded = try await service.upVideos(
                mid: mid,
                page: 1,
                keyword: keyword,
                order: requestedOrder
            )
            guard currentGeneration == generation,
                  submittedKeyword == keyword,
                  order == requestedOrder,
                  loaded.mid == mid else { return }
            if !loaded.author.isEmpty { author = loaded.author }
            videos = loaded.videos
            total = loaded.total
            page = loaded.page
            hasMore = loaded.hasMore
            loadedOrder = requestedOrder
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func loadMore(using service: any UPServicing & SourceServicing & JobMutationServicing) async {
        guard hasMore, !isLoading, !isLoadingMore else { return }
        let currentGeneration = generation
        let requestedPage = page + 1
        let keyword = submittedKeyword
        let requestedOrder = loadedOrder
        isLoadingMore = true
        errorMessage = nil
        defer {
            if currentGeneration == generation { isLoadingMore = false }
        }

        do {
            let loaded = try await service.upVideos(
                mid: mid,
                page: requestedPage,
                keyword: keyword,
                order: requestedOrder
            )
            guard currentGeneration == generation,
                  submittedKeyword == keyword,
                  loadedOrder == requestedOrder,
                  page + 1 == requestedPage,
                  loaded.mid == mid else { return }
            let existingIDs = Set(videos.map(\.id))
            videos.append(contentsOf: loaded.videos.filter { !existingIDs.contains($0.id) })
            total = loaded.total
            page = loaded.page
            hasMore = loaded.hasMore
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func generateOrRetry(
        _ video: UPVideo,
        using service: any UPServicing & SourceServicing & JobMutationServicing
    ) async -> String? {
        guard !mutatingVideoIDs.contains(video.bvid),
              video.readerDestination == nil,
              video.activeJobID == nil else { return nil }
        mutatingVideoIDs.insert(video.bvid)
        errorMessage = nil
        defer { mutatingVideoIDs.remove(video.bvid) }

        do {
            let jobID: String
            if video.status == .failed, let existingJobID = video.jobId {
                _ = try await service.retryJob(id: existingJobID, emailEnabled: nil)
                jobID = existingJobID
            } else {
                let creation = try await service.createJob(url: video.url, dedupe: true, emailEnabled: nil)
                jobID = creation.jobId
            }
            replace(video, with: video.updating(status: .pending, jobID: jobID))
            return jobID
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
            return nil
        }
    }

    private func replace(_ video: UPVideo, with updated: UPVideo) {
        guard let index = videos.firstIndex(where: { $0.id == video.id }) else { return }
        videos[index] = updated
    }
}
