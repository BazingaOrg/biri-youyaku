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

    var id: String { "\(kind)-\(chunkOrd)" }
    var isSubtitle: Bool { kind == "subs" }
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

    var id: String { "\(documentId ?? jobId ?? title ?? "item")-\(savedAt ?? 0)" }
    var displayTitle: String { title?.isEmpty == false ? title! : "未命名笔记" }

    func destination(for hit: SearchHit? = nil) -> ReaderDestination {
        ReaderDestination(
            id: documentId ?? jobId ?? id,
            title: displayTitle,
            kind: documentId == nil ? .job : .document,
            initialTab: hit?.isSubtitle == true ? .subtitles : .notes
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

    init(id: String, title: String, kind: Kind, initialTab: ReaderTab = .notes) {
        self.id = id
        self.title = title
        self.kind = kind
        self.initialTab = initialTab
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

    var displayTitle: String { title?.isEmpty == false ? title! : "未命名笔记" }
}

struct TranscriptCue: Decodable, Identifiable, Hashable {
    let start: Double
    let end: Double
    let text: String

    var id: String { "\(start)-\(text)" }
    var timeLabel: String { Formatting.duration(start) }
}

struct DocumentContent: Decodable {
    let document: DocumentMetadata
    let markdown: String
    let cues: [TranscriptCue]

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
