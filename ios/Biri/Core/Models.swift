import Foundation

struct CursorValue: Hashable, Sendable, Decodable {
    let raw: String

    init(_ raw: String) {
        self.raw = raw
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) {
            raw = value
        } else if let value = try? container.decode(Int.self) {
            raw = String(value)
        } else {
            throw DecodingError.typeMismatch(
                String.self,
                .init(codingPath: decoder.codingPath, debugDescription: "Expected a string or integer cursor")
            )
        }
    }
}

struct LibraryItem: Decodable, Identifiable, Hashable {
    let id: String
    let documentId: String?
    let jobId: String?
    let title: String?
    let author: String?
    let provider: String
    let duration: Double?
    let tags: [String]
    let tldr: String?
    let savedAt: Int?
    let sourceUrl: String?
    let legacy: Bool
    var sourceId: String? = nil
    var sourcePart: String? = nil
    var mid: Int? = nil
    var bvid: String? = nil
    var cid: Int? = nil

    var displayTitle: String { title?.isEmpty == false ? title! : "未命名笔记" }
    var destination: ReaderDestination {
        ReaderDestination(
            id: documentId ?? jobId ?? id,
            title: displayTitle,
            kind: documentId == nil ? .job : .document
        )
    }
}

struct LibraryPage: Decodable {
    let items: [LibraryItem]
    let nextCursor: CursorValue?
    let total: Int
}

enum SearchScope: String, CaseIterable, Identifiable {
    case all
    case notes
    case subs

    var id: String { rawValue }
    var label: String {
        switch self {
        case .all: "全部"
        case .notes: "笔记"
        case .subs: "字幕"
        }
    }
}

struct SearchHit: Decodable, Identifiable, Hashable {
    let kind: String
    let chunkOrd: Int
    let snippet: String
    let startSec: Double?
    var headingPath: String? = nil
    var endSec: Double? = nil

    var id: String { "\(kind)-\(chunkOrd)" }
    var isSubtitle: Bool { kind == "subs" }
}

struct SearchMatch: Decodable, Hashable {
    let title: Bool
    let author: Bool
    let bvid: Bool
    let sourceId: Bool
    let tags: [String]
}

struct SearchHitCounts: Decodable, Hashable {
    let notes: Int
    let subs: Int
}

struct SearchGroup: Decodable, Identifiable, Hashable {
    let documentId: String?
    let jobId: String?
    let title: String?
    let author: String?
    let provider: String
    let sourceUrl: String?
    let savedAt: Int?
    let tldr: String?
    let duration: Double?
    let legacy: Bool
    let hits: [SearchHit]
    var sourceId: String? = nil
    var sourcePart: String? = nil
    var mid: Int? = nil
    var bvid: String? = nil
    var cid: Int? = nil
    var match: SearchMatch? = nil
    var hitCounts: SearchHitCounts? = nil

    var id: String { "\(documentId ?? jobId ?? title ?? "item")-\(savedAt ?? 0)" }
    var displayTitle: String { title?.isEmpty == false ? title! : "未命名笔记" }

    func destination(for hit: SearchHit? = nil, query: String? = nil) -> ReaderDestination {
        ReaderDestination(
            id: documentId ?? jobId ?? id,
            title: displayTitle,
            kind: documentId == nil ? .job : .document,
            initialTab: hit?.isSubtitle == true ? .subtitles : .notes,
            initialChunkOrd: hit?.isSubtitle == false ? hit?.chunkOrd : nil,
            initialCueStart: hit?.isSubtitle == true ? hit?.startSec : nil,
            searchQuery: hit == nil ? nil : query
        )
    }
}

struct SearchPage: Decodable {
    let groups: [SearchGroup]
    let nextCursor: CursorValue?
    let partial: [String]
}

enum ReaderTab: String, Hashable {
    case notes
    case subtitles

    var label: String { self == .notes ? "笔记" : "字幕" }
}

struct ReaderDestination: Hashable, Identifiable {
    enum Kind: Hashable {
        case document
        case job
    }

    let id: String
    let title: String
    let kind: Kind
    let initialTab: ReaderTab
    let initialChunkOrd: Int?
    let initialCueStart: Double?
    let searchQuery: String?

    init(
        id: String,
        title: String,
        kind: Kind,
        initialTab: ReaderTab = .notes,
        initialChunkOrd: Int? = nil,
        initialCueStart: Double? = nil,
        searchQuery: String? = nil
    ) {
        self.id = id
        self.title = title
        self.kind = kind
        self.initialTab = initialTab
        self.initialChunkOrd = initialChunkOrd
        self.initialCueStart = initialCueStart
        self.searchQuery = searchQuery
    }
}

struct DocumentMetadata: Decodable, Hashable {
    let documentId: String?
    let jobId: String?
    let title: String?
    let author: String?
    let provider: String
    let sourceUrl: String?
    let duration: Double?
    let tldr: String?
    let updatedAt: Int?
    var sourceId: String? = nil
    var sourcePart: String? = nil
    var subtitleSource: String? = nil
    var subtitleLanguage: String? = nil
    var mid: Int? = nil
    var bvid: String? = nil
    var cid: Int? = nil
    var tags: [String]? = nil
    var createdAt: Int? = nil
    var expiresAt: Int? = nil

    var displayTitle: String { title?.isEmpty == false ? title! : "未命名笔记" }
}

struct TranscriptCue: Decodable, Identifiable, Hashable {
    let start: Double
    let end: Double
    let text: String

    var id: String { "\(start)-\(text)" }
    var timeLabel: String { Formatting.duration(start) }
}

struct NoteChunk: Decodable, Identifiable, Hashable {
    let chunkOrd: Int
    let headingPath: String
    let startSec: Double?
    let text: String

    var id: Int { chunkOrd }
}

struct TranscriptChunk: Decodable, Identifiable, Hashable {
    let chunkOrd: Int
    let startSec: Double?
    let endSec: Double?
    let text: String

    var id: Int { chunkOrd }
}

struct DocumentContent: Decodable {
    let document: DocumentMetadata
    let markdown: String
    let cues: [TranscriptCue]
    var noteChunks: [NoteChunk]? = nil
    var transcriptChunks: [TranscriptChunk]? = nil
    var contentHash: String? = nil

    init(job: Job) {
        document = DocumentMetadata(
            documentId: job.documentId,
            jobId: job.id,
            title: job.title,
            author: job.author,
            provider: "legacy_job",
            sourceUrl: job.url,
            duration: job.duration,
            tldr: nil,
            updatedAt: job.updatedAt
        )
        markdown = job.summary ?? ""
        cues = job.transcript ?? []
    }
}

enum JobStatus: String, Decodable, Hashable {
    case pending = "PENDING"
    case fetchingMeta = "FETCHING_META"
    case downloadingAudio = "DOWNLOADING_AUDIO"
    case transcribing = "TRANSCRIBING"
    case transcriptReady = "TRANSCRIPT_READY"
    case summarizing = "SUMMARIZING"
    case emailing = "EMAILING"
    case completed = "COMPLETED"
    case failed = "FAILED"
    case canceled = "CANCELED"

    var isActive: Bool {
        switch self {
        case .completed, .failed, .canceled: false
        default: true
        }
    }

    var label: String {
        switch self {
        case .pending: "等待处理"
        case .fetchingMeta: "获取内容信息"
        case .downloadingAudio: "下载音频"
        case .transcribing: "正在生成字幕"
        case .transcriptReady: "字幕已生成"
        case .summarizing: "正在总结"
        case .emailing: "正在发送邮件"
        case .completed: "已完成"
        case .failed: "失败"
        case .canceled: "已取消"
        }
    }

    var systemImage: String {
        switch self {
        case .completed: "checkmark.circle.fill"
        case .failed: "exclamationmark.circle.fill"
        case .canceled: "stop.circle.fill"
        default: "clock.fill"
        }
    }
}

struct Job: Decodable, Identifiable, Hashable {
    let id: String
    let url: String
    let title: String?
    let author: String?
    let duration: Double?
    let status: JobStatus
    let errorStage: String?
    let errorMessage: String?
    let createdAt: Int
    let updatedAt: Int
    let completedAt: Int?
    let summaryAvailable: Bool?
    let documentId: String?
    let summary: String?
    let transcript: [TranscriptCue]?
    var emailError: String? = nil

    var displayTitle: String { title?.isEmpty == false ? title! : id }

    var destination: ReaderDestination? {
        guard documentId != nil || summaryAvailable == true || summary?.isEmpty == false else { return nil }
        return ReaderDestination(
            id: documentId ?? id,
            title: displayTitle,
            kind: documentId == nil ? .job : .document
        )
    }
}

struct JobPage: Decodable {
    let jobs: [Job]
    let nextCursor: CursorValue?
}

enum JobFilter: String, CaseIterable, Identifiable {
    case all
    case running
    case completed
    case failed

    var id: String { rawValue }
    var label: String {
        switch self {
        case .all: "全部"
        case .running: "进行中"
        case .completed: "已完成"
        case .failed: "失败"
        }
    }

    func matches(_ job: Job) -> Bool {
        switch self {
        case .all: true
        case .running: job.status.isActive
        case .completed: job.status == .completed
        case .failed: job.status == .failed
        }
    }
}

struct RuntimeConfiguration: Decodable {
    let authMode: String
    let knowledgeSearchEnabled: Bool
}

struct SourceCapabilities: Decodable {
    struct Upload: Decodable {
        let maxBytes: Int
        let extensions: [String]
    }

    struct ASR: Decodable {
        let installed: Bool
        let model: String
    }

    let providers: [String]
    let upload: Upload
    let ffmpeg: Bool
    let ffprobe: Bool
    let asr: ASR
    let youtube: Bool
}

struct SourceResolution: Decodable {
    struct ExistingDocument: Decodable, Hashable {
        let documentId: String
        let title: String
        let savedAt: Int?
    }

    struct TrashedDocument: Decodable, Hashable {
        let documentId: String
        let title: String
        let daysLeft: Int?
    }

    let provider: String
    let sourceId: String
    let sourcePart: String
    let canonicalUrl: String
    let existing: ExistingDocument?
    let trashed: TrashedDocument?
    let activeJobId: String?
}

struct JobCreation: Decodable {
    let ok: Bool
    let jobId: String
    let deduped: Bool

    private enum CodingKeys: String, CodingKey {
        case ok
        case jobId
        case deduped
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ok = try container.decode(Bool.self, forKey: .ok)
        jobId = try container.decode(String.self, forKey: .jobId)
        deduped = try container.decodeIfPresent(Bool.self, forKey: .deduped) ?? false
    }
}

struct OperationResponse: Decodable {
    let ok: Bool
}

struct BulkDeleteFilter: Encodable, Hashable {
    var query: String?
    var author: String?
    var tag: String?

    init(query: String? = nil, author: String? = nil, tag: String? = nil) {
        self.query = query
        self.author = author
        self.tag = tag
    }
}

struct BulkDeletePreview: Decodable {
    struct Sample: Decodable, Identifiable, Hashable {
        let id: String
        let title: String
        let author: String?
        let createdAt: Int
        let status: JobStatus
    }

    let ok: Bool
    let matchedCount: Int
    let byStatus: [String: Int]
    let sample: [Sample]
    let sampleTruncatedCount: Int
    let expiresAt: Int
    let previewToken: String
}

struct BulkDeleteResult: Decodable {
    struct CleanupFailure: Decodable, Hashable {
        let jobId: String
        let fileType: String
    }

    let ok: Bool
    let deletedCount: Int
    let cleanupPendingCount: Int
    let cleanupFailures: [CleanupFailure]
    let cleanupRetry: String?
}

struct TrashItem: Decodable, Identifiable, Hashable {
    let documentId: String
    let title: String
    let author: String?
    let provider: String
    let sourceId: String?
    let sourcePart: String?
    let bvid: String?
    let deletedAt: Int
    let expiresAt: Int
    let daysLeft: Int

    var id: String { documentId }
    var displayTitle: String { title.isEmpty ? "未命名笔记" : title }
}

struct TrashPage: Decodable {
    let ok: Bool
    let items: [TrashItem]
}

struct LifecycleDocument: Decodable, Hashable {
    let id: String
    let title: String?
    let author: String?
    let bvid: String?
    let cid: Int?
    let deletedAt: Int?
    let deleteReason: String?
}

struct DocumentPurgeResult: Decodable {
    let ok: Bool
    let id: String
    let purged: Bool
    let title: String?
    let bvid: String?
}

struct UPResolution: Decodable {
    let ok: Bool
    let mid: Int
}

enum UPCatalogOrder: String {
    case pubdate
    case click
}

struct UPVideo: Decodable, Identifiable, Hashable {
    let bvid: String
    let title: String
    let cover: String
    let pubdate: Int
    let duration: Int
    let url: String
    let status: JobStatus?
    let jobId: String?
    let documentId: String?

    var id: String { bvid }
}

struct UPCatalogPage: Decodable {
    let ok: Bool
    let mid: Int
    let author: String
    let total: Int
    let page: Int
    let pageSize: Int
    let hasMore: Bool
    let videos: [UPVideo]
}

enum DistillRunStatus: String, Decodable, Hashable {
    case pending = "PENDING"
    case fetchingDynamics = "FETCHING_DYNAMICS"
    case preparingTranscripts = "PREPARING_TRANSCRIPTS"
    case extracting = "EXTRACTING"
    case assembling = "ASSEMBLING"
    case completed = "COMPLETED"
    case failed = "FAILED"
    case cancelled = "CANCELLED"

    var isActive: Bool {
        switch self {
        case .completed, .failed, .cancelled: false
        default: true
        }
    }
}

struct DistillCounters: Decodable, Hashable {
    let videosTotal: Int
    let videosTranscribed: Int
    let videosExtracted: Int
    let videosFailed: Int
    let failedBvids: [String]
}

struct DistillRun: Decodable, Identifiable, Hashable {
    let id: String
    let mid: Int
    let upName: String?
    let status: DistillRunStatus
    let videoLimit: Int
    let counters: DistillCounters
    let error: String?
    let dirPath: String
    let createdAt: Int
    let updatedAt: Int
}

struct DistillCorpus: Decodable {
    let ok: Bool
    let runId: String
    let corpus: String
}

struct DistillStatusUpdate: Decodable, Hashable {
    let status: DistillRunStatus
    let videosTotal: Int?
    let videosTranscribed: Int?
    let videosExtracted: Int?
    let error: String?
}

enum DistillEvent: Hashable {
    case snapshot(DistillRun)
    case status(DistillStatusUpdate)
}

struct JobChapter: Decodable, Hashable {
    let start: Double
    let end: Double?
    let title: String
}

struct JobStatusEvent: Decodable, Hashable {
    let status: JobStatus
    let summary: String?
    let stage: String?
    let message: String?
    let errorCode: String?
    let emailError: String?
    let transcriptPreview: [TranscriptCue]?
    let subtitleSource: String?
    let queued: Bool?
    let tags: [String]?
}

struct JobMetaEvent: Decodable, Hashable {
    let title: String
    let author: String
    let duration: Double
    let chapters: [JobChapter]
}

struct DownloadProgress: Decodable, Hashable {
    let status: String?
    let downloadedBytes: Double?
    let totalBytes: Double?
    let percent: Double?
    let speed: Double?
    let eta: Double?
}

struct TranscribeProgress: Decodable, Hashable {
    let percent: Double?
    let itemsCount: Int?
    let preview: String?
}

struct SummarySegmentProgress: Decodable, Hashable {
    let done: Int
    let total: Int
}

struct JobErrorEvent: Decodable, Hashable {
    let stage: String?
    let message: String?
}

enum JobEvent: Hashable {
    case status(JobStatusEvent)
    case meta(JobMetaEvent)
    case downloadProgress(DownloadProgress)
    case transcribeProgress(TranscribeProgress)
    case cumulativeSummary(String)
    case summaryProgress(SummarySegmentProgress)
    case error(JobErrorEvent)
}
