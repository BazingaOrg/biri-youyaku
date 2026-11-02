import Foundation
import Observation

enum CreateJobDestination: Hashable {
    case job(String)
    case reader(ReaderDestination)
}

@MainActor
@Observable
final class CreateJobViewModel {
    var url = ""
    var emailEnabled = false
    private(set) var resolution: SourceResolution?
    private(set) var destination: CreateJobDestination?
    var isResolving = false
    var isSubmitting = false
    var errorMessage: String?

    private var generation = 0
    private var resolvedURL: String?

    var trimmedURL: String { url.trimmingCharacters(in: .whitespacesAndNewlines) }
    var canResolve: Bool { !trimmedURL.isEmpty && !isResolving && !isSubmitting }

    func updateURL(_ newValue: String) {
        guard url != newValue else { return }
        urlDidChange()
        url = newValue
    }

    func urlDidChange() {
        generation += 1
        resolution = nil
        resolvedURL = nil
        destination = nil
        errorMessage = nil
        isResolving = false
    }

    func resolve(using service: any SourceServicing) async {
        let candidate = trimmedURL
        guard !candidate.isEmpty else {
            errorMessage = "请输入 Bilibili 或 YouTube 视频链接"
            return
        }
        guard !isSubmitting else { return }

        generation += 1
        let currentGeneration = generation
        isResolving = true
        errorMessage = nil
        destination = nil
        resolution = nil
        resolvedURL = nil
        defer {
            if currentGeneration == generation { isResolving = false }
        }

        do {
            let loaded = try await service.resolveSource(url: candidate)
            guard currentGeneration == generation, trimmedURL == candidate else { return }
            resolution = loaded
            resolvedURL = candidate
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func openExisting() {
        guard let existing = resolution?.existing else { return }
        destination = .reader(
            ReaderDestination(id: existing.documentId, title: existing.title, kind: .document)
        )
    }

    func openActiveJob() {
        guard let jobID = resolution?.activeJobId else { return }
        destination = .job(jobID)
    }

    func restoreTrashed(using service: any LibraryLifecycleServicing) async {
        guard let trashed = resolution?.trashed, !isSubmitting else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        do {
            let restored = try await service.restoreDocument(id: trashed.documentId)
            destination = .reader(
                ReaderDestination(
                    id: restored.id,
                    title: restored.title?.isEmpty == false ? restored.title! : trashed.title,
                    kind: .document
                )
            )
        } catch {
            guard !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func create(using service: any SourceServicing, dedupe: Bool = true) async {
        guard let resolution, resolvedURL == trimmedURL, resolution.activeJobId == nil, !isSubmitting else { return }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        do {
            let created = try await service.createJob(
                url: resolution.canonicalUrl,
                dedupe: dedupe,
                emailEnabled: emailEnabled
            )
            destination = .job(created.jobId)
        } catch {
            guard !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func clearDestination() {
        destination = nil
    }
}
