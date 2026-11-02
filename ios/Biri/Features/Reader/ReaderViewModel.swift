import Foundation
import Observation

struct ReaderMatch: Identifiable, Hashable {
    let id: String
    let tab: ReaderTab
    let blockID: Int?
    let cueID: String?
}

@MainActor
@Observable
final class ReaderViewModel {
    let destination: ReaderDestination
    private(set) var content: DocumentContent?
    private(set) var blocks: [MarkdownBlock] = []
    private(set) var contentRevision = 0
    private(set) var initialNoteBlockID: Int?
    private(set) var initialCueID: String?
    private(set) var matches: [ReaderMatch] = []
    private(set) var currentMatchIndex = 0
    private(set) var regeneratedJobID: String?
    private(set) var didMoveToTrash = false
    var selectedTab: ReaderTab
    var transcriptQuery = ""
    var isLoading = false
    var isRegenerating = false
    var isDeleting = false
    var errorMessage: String?
    var actionErrorMessage: String?
    var feedbackMessage: String?

    private var generation = 0
    private var mutationGeneration = 0

    init(destination: ReaderDestination) {
        self.destination = destination
        selectedTab = destination.initialTab
    }

    var headings: [MarkdownHeading] { blocks.compactMap(\.heading) }
    var searchQuery: String {
        destination.searchQuery?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    var filteredCues: [TranscriptCue] {
        guard let content else { return [] }
        let query = transcriptQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return content.cues }
        return content.cues.filter { $0.text.localizedCaseInsensitiveContains(query) }
    }

    var visibleMatches: [ReaderMatch] {
        let tabMatches = matches.filter { $0.tab == selectedTab }
        guard selectedTab == .subtitles else { return tabMatches }
        let query = transcriptQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return tabMatches }
        let visibleIDs = Set(filteredCues.map(\.id))
        return tabMatches.filter { $0.cueID.map(visibleIDs.contains) == true }
    }

    var currentMatch: ReaderMatch? {
        guard !visibleMatches.isEmpty else { return nil }
        let index = min(max(currentMatchIndex, 0), visibleMatches.count - 1)
        return visibleMatches[index]
    }

    var currentMatchID: String? { currentMatch?.id }
    var currentMatchPosition: Int { currentMatch == nil ? 0 : min(currentMatchIndex + 1, visibleMatches.count) }

    var copyText: String {
        guard let content else { return "" }
        if selectedTab == .notes { return content.markdown }
        return content.cues.map { "\($0.timeLabel)  \($0.text)" }.joined(separator: "\n")
    }

    var canRegenerate: Bool {
        content != nil && regenerationJobID != nil && !isRegenerating && !isDeleting && !didMoveToTrash
    }

    var canSoftDelete: Bool {
        content != nil && documentID != nil && !isRegenerating && !isDeleting && !didMoveToTrash
    }

    func load(using service: any BiriServicing) async {
        generation += 1
        let currentGeneration = generation
        isLoading = true
        errorMessage = nil
        actionErrorMessage = nil
        defer {
            if currentGeneration == generation { isLoading = false }
        }
        do {
            let loaded: DocumentContent
            switch destination.kind {
            case .document:
                loaded = try await service.document(id: destination.id)
            case .job:
                let job = try await service.job(id: destination.id)
                if let documentId = job.documentId {
                    loaded = try await service.document(id: documentId)
                } else {
                    guard job.summary?.isEmpty == false else { throw APIError.http(status: 404, message: nil) }
                    loaded = DocumentContent(job: job)
                }
            }
            guard currentGeneration == generation else { return }
            content = loaded
            blocks = MarkdownParser.parse(loaded.markdown)
            didMoveToTrash = false
            initialNoteBlockID = Self.noteBlockID(
                for: destination.initialChunkOrd,
                content: loaded,
                blocks: blocks
            )
            initialCueID = Self.cueID(for: destination.initialCueStart, cues: loaded.cues)
            rebuildMatches()
            selectInitialMatch()
            contentRevision += 1
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func resetMatchNavigation() {
        currentMatchIndex = 0
    }

    func moveMatch(by offset: Int) {
        let count = visibleMatches.count
        guard count > 0 else {
            currentMatchIndex = 0
            return
        }
        currentMatchIndex = (currentMatchIndex + offset + count) % count
    }

    func regenerate(using service: any JobMutationServicing) async {
        guard let jobID = regenerationJobID, canRegenerate else { return }
        mutationGeneration += 1
        let currentMutation = mutationGeneration
        let currentGeneration = generation
        isRegenerating = true
        actionErrorMessage = nil
        feedbackMessage = nil
        defer {
            if currentMutation == mutationGeneration { isRegenerating = false }
        }
        do {
            let creation = try await service.resummarizeJob(id: jobID, emailEnabled: nil)
            guard currentMutation == mutationGeneration, currentGeneration == generation else { return }
            regeneratedJobID = creation.jobId
            feedbackMessage = "已创建重新生成任务，当前笔记会保留。"
        } catch {
            guard currentMutation == mutationGeneration,
                  currentGeneration == generation,
                  !error.isRequestCancellation else { return }
            actionErrorMessage = error.localizedDescription
        }
    }

    func softDelete(using service: any LibraryLifecycleServicing) async {
        guard let documentID, canSoftDelete else { return }
        mutationGeneration += 1
        let currentMutation = mutationGeneration
        let currentGeneration = generation
        isDeleting = true
        actionErrorMessage = nil
        feedbackMessage = nil
        defer {
            if currentMutation == mutationGeneration { isDeleting = false }
        }
        do {
            _ = try await service.softDeleteDocument(id: documentID, reason: "从 iOS 阅读页移到回收站")
            guard currentMutation == mutationGeneration, currentGeneration == generation else { return }
            didMoveToTrash = true
            feedbackMessage = "已移到回收站，可在“设置 › 内容管理 › 回收站”恢复。"
        } catch {
            guard currentMutation == mutationGeneration,
                  currentGeneration == generation,
                  !error.isRequestCancellation else { return }
            actionErrorMessage = error.localizedDescription
        }
    }

    func sourceURL(at seconds: Double? = nil) -> URL? {
        guard let value = content?.document.sourceUrl,
              var components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              ["http", "https"].contains(scheme) else { return nil }
        if let seconds {
            var items = components.queryItems?.filter { $0.name != "t" } ?? []
            items.append(URLQueryItem(name: "t", value: String(Int(seconds))))
            components.queryItems = items
        }
        return components.url
    }

    private var regenerationJobID: String? {
        content?.document.jobId ?? (destination.kind == .job ? destination.id : nil)
    }

    private var documentID: String? {
        content?.document.documentId ?? (destination.kind == .document ? destination.id : nil)
    }

    private func rebuildMatches() {
        guard !searchQuery.isEmpty else {
            matches = []
            currentMatchIndex = 0
            return
        }
        var result: [ReaderMatch] = []
        for block in blocks {
            guard let text = Self.plainText(for: block) else { continue }
            let count = SearchHighlight.matchCount(in: text, query: searchQuery)
            for occurrence in 0..<count {
                result.append(ReaderMatch(
                    id: "notes-\(block.id)-\(occurrence)",
                    tab: .notes,
                    blockID: block.id,
                    cueID: nil
                ))
            }
        }
        for cue in content?.cues ?? [] {
            let count = SearchHighlight.matchCount(in: cue.text, query: searchQuery)
            for occurrence in 0..<count {
                result.append(ReaderMatch(
                    id: "subs-\(cue.id)-\(occurrence)",
                    tab: .subtitles,
                    blockID: nil,
                    cueID: cue.id
                ))
            }
        }
        matches = result
    }

    private func selectInitialMatch() {
        let visible = visibleMatches
        if let initialNoteBlockID,
           let index = visible.firstIndex(where: { $0.blockID == initialNoteBlockID }) {
            currentMatchIndex = index
        } else if let initialCueID,
                  let index = visible.firstIndex(where: { $0.cueID == initialCueID }) {
            currentMatchIndex = index
        } else {
            currentMatchIndex = 0
        }
    }

    private static func noteBlockID(
        for chunkOrd: Int?,
        content: DocumentContent,
        blocks: [MarkdownBlock]
    ) -> Int? {
        guard let chunkOrd,
              let chunk = content.noteChunks?.first(where: { $0.chunkOrd == chunkOrd }) else { return nil }
        let chunkText = normalize(chunk.text)
        guard !chunkText.isEmpty else { return nil }

        let directMatches = blocks.compactMap { block -> Int? in
            guard let text = plainText(for: block).map(normalize), !text.isEmpty else { return nil }
            return text == chunkText || text.contains(chunkText) ? block.id : nil
        }
        guard directMatches.count < 2 else { return nil }
        if let blockID = directMatches.first { return blockID }

        let fallbackMatches = blocks.compactMap { block -> Int? in
            guard let text = plainText(for: block).map(normalize), text.count >= 12 else { return nil }
            return chunkText.contains(text) ? block.id : nil
        }
        return fallbackMatches.count == 1 ? fallbackMatches[0] : nil
    }

    private static func cueID(for start: Double?, cues: [TranscriptCue]) -> String? {
        guard let start, !cues.isEmpty else { return nil }
        return cues.min { abs($0.start - start) < abs($1.start - start) }?.id
    }

    private static func plainText(for block: MarkdownBlock) -> String? {
        switch block {
        case let .heading(_, _, text), let .paragraph(_, text), let .quote(_, text), let .listItem(_, _, text):
            return String(InlineMarkdown.attributed(text).characters)
        case let .code(_, _, text):
            return text
        case .divider:
            return nil
        }
    }

    private static func normalize(_ text: String) -> String {
        text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}
