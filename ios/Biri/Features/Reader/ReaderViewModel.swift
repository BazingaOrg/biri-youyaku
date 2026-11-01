import Foundation
import Observation

@MainActor
@Observable
final class ReaderViewModel {
    let destination: ReaderDestination
    private(set) var content: DocumentContent?
    private(set) var blocks: [MarkdownBlock] = []
    var selectedTab: ReaderTab
    var transcriptQuery = ""
    var isLoading = false
    var errorMessage: String?

    private var generation = 0

    init(destination: ReaderDestination) {
        self.destination = destination
        selectedTab = destination.initialTab
    }

    var headings: [MarkdownHeading] { blocks.compactMap(\.heading) }
    var filteredCues: [TranscriptCue] {
        guard let content else { return [] }
        let query = transcriptQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return content.cues }
        return content.cues.filter { $0.text.localizedCaseInsensitiveContains(query) }
    }

    var copyText: String {
        guard let content else { return "" }
        if selectedTab == .notes { return content.markdown }
        return content.cues.map { "\($0.timeLabel)  \($0.text)" }.joined(separator: "\n")
    }

    func load(using service: any BiriServicing) async {
        generation += 1
        let currentGeneration = generation
        isLoading = true
        errorMessage = nil
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
        } catch {
            guard currentGeneration == generation, !(error is CancellationError) else { return }
            if case .network(let urlError) = error as? APIError, urlError.code == .cancelled { return }
            errorMessage = error.localizedDescription
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
}
