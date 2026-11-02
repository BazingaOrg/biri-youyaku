import Foundation
import Observation

typealias JobDetailServicing = BiriServicing & JobMutationServicing & JobEventServicing

enum JobConnectionState: Equatable {
    case stopped
    case connecting
    case connected
    case reconnecting
    case finished
}

struct JobNavigation: Identifiable, Hashable {
    let id: String
}

@MainActor
@Observable
final class JobDetailViewModel {
    let jobID: String
    private(set) var job: Job?
    private(set) var emailError: String?
    private(set) var downloadProgress: DownloadProgress?
    private(set) var transcribeProgress: TranscribeProgress?
    private(set) var summaryProgress: SummarySegmentProgress?
    private(set) var liveSummary: String?
    private(set) var transcriptPreview: [TranscriptCue] = []
    private(set) var transcribePreview: String?
    private(set) var connectionState: JobConnectionState = .stopped
    private(set) var usesPollingFallback = false
    private(set) var streamGeneration = 0
    var navigation: JobNavigation?
    var didDelete = false
    var isLoading = false
    var isMutating = false
    var errorMessage: String?
    var noticeMessage: String?

    private var generation = 0
    private var eventRevision = 0
    @ObservationIgnored private var streamTask: Task<Void, Never>?

    init(jobID: String) {
        self.jobID = jobID
    }

    var shouldPoll: Bool {
        job?.status.isActive == true && usesPollingFallback
    }

    var pollKey: String { "\(jobID)-\(shouldPoll)" }

    var canResummarize: Bool {
        job?.transcript?.isEmpty == false
    }

    func load(using service: any BiriServicing, quietly: Bool = false) async {
        generation += 1
        let currentGeneration = generation
        let startingEventRevision = eventRevision
        if !quietly { isLoading = true }
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            let loaded = try await service.job(id: jobID)
            guard currentGeneration == generation, startingEventRevision == eventRevision else { return }
            job = loaded
            emailError = loaded.emailError
            liveSummary = loaded.summary ?? liveSummary
            if let transcript = loaded.transcript, !transcript.isEmpty {
                transcriptPreview = transcript
            }
        } catch {
            guard currentGeneration == generation, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func start(using service: any JobDetailServicing) {
        stop()
        streamGeneration += 1
        let currentGeneration = streamGeneration
        connectionState = .connecting
        streamTask = Task { [weak self] in
            await self?.runEventLoop(using: service, generation: currentGeneration)
        }
    }

    func stop() {
        streamGeneration += 1
        streamTask?.cancel()
        streamTask = nil
        connectionState = .stopped
        usesPollingFallback = false
    }

    func reconnect(using service: any JobDetailServicing) async {
        stop()
        await load(using: service, quietly: true)
        guard job != nil else { return }
        start(using: service)
    }

    private func runEventLoop(using service: any JobDetailServicing, generation: Int) async {
        var failedAttempts = 0
        var shouldRefreshSnapshot = false

        while !Task.isCancelled, generation == streamGeneration {
            if shouldRefreshSnapshot {
                connectionState = .reconnecting
                await load(using: service, quietly: true)
                guard !Task.isCancelled, generation == streamGeneration else { return }
            }

            do {
                for try await event in service.jobEvents(id: jobID) {
                    guard !Task.isCancelled, generation == streamGeneration else { return }
                    process(event, generation: generation)
                    if job?.status.isActive == false { break }
                }
                guard !Task.isCancelled, generation == streamGeneration else { return }

                if job?.status.isActive == false {
                    connectionState = .finished
                    usesPollingFallback = false
                    await load(using: service, quietly: true)
                    return
                }
                failedAttempts += 1
            } catch {
                guard !Task.isCancelled, generation == streamGeneration else { return }
                failedAttempts += 1
            }

            usesPollingFallback = true
            connectionState = .reconnecting
            shouldRefreshSnapshot = true
            let delay = min(2 * failedAttempts, 10)
            do {
                try await Task.sleep(for: .seconds(delay))
            } catch {
                return
            }
        }
    }

    func process(_ event: JobEvent, generation: Int) {
        guard generation == streamGeneration, generation > 0 else { return }
        eventRevision += 1
        connectionState = .connected
        usesPollingFallback = false

        switch event {
        case let .status(update):
            apply(update)
        case let .meta(meta):
            guard let current = job else { return }
            job = copyJob(current, title: meta.title, author: meta.author, duration: meta.duration)
        case let .downloadProgress(progress):
            downloadProgress = progress
        case let .transcribeProgress(progress):
            transcribeProgress = progress
            if let preview = progress.preview, !preview.isEmpty {
                transcribePreview = preview
            }
        case let .cumulativeSummary(summary):
            liveSummary = summary
        case let .summaryProgress(progress):
            summaryProgress = progress
        case let .error(error):
            guard let current = job else { return }
            job = copyJob(
                current,
                errorStage: .some(error.stage ?? current.errorStage),
                errorMessage: .some(error.message ?? current.errorMessage)
            )
        }
    }

    private func apply(_ update: JobStatusEvent) {
        emailError = update.emailError
        if let summary = update.summary { liveSummary = summary }
        if let preview = update.transcriptPreview { transcriptPreview = preview }
        guard let current = job else { return }

        let failed = update.status == .failed
        job = copyJob(
            current,
            status: update.status,
            errorStage: .some(failed ? (update.stage ?? current.errorStage) : update.stage),
            errorMessage: .some(failed ? (update.message ?? current.errorMessage) : update.message),
            summary: .some(update.summary ?? current.summary),
            summaryAvailable: update.summary == nil ? nil : .some(true),
            transcript: .some(update.transcriptPreview ?? current.transcript),
            emailError: .some(emailError)
        )
    }

    func cancel(using service: any JobDetailServicing) async {
        guard beginMutation() else { return }
        defer { isMutating = false }
        do {
            _ = try await service.cancelJob(id: jobID)
            stop()
            await load(using: service, quietly: true)
            start(using: service)
            noticeMessage = "已请求取消任务"
        } catch {
            mutationFailed(error)
        }
    }

    func retry(using service: any JobDetailServicing) async {
        guard beginMutation() else { return }
        defer { isMutating = false }
        do {
            _ = try await service.retryJob(id: jobID, emailEnabled: nil)
            stop()
            await load(using: service, quietly: true)
            start(using: service)
            noticeMessage = "已重新开始当前任务"
        } catch {
            mutationFailed(error)
        }
    }

    func resume(using service: any JobDetailServicing) async {
        guard beginMutation() else { return }
        defer { isMutating = false }
        do {
            _ = try await service.resumeJob(id: jobID, emailEnabled: nil)
            stop()
            await load(using: service, quietly: true)
            start(using: service)
            noticeMessage = "已继续生成笔记"
        } catch {
            mutationFailed(error)
        }
    }

    func resummarize(using service: any JobDetailServicing) async {
        guard beginMutation() else { return }
        defer { isMutating = false }
        do {
            let created = try await service.resummarizeJob(id: jobID, emailEnabled: nil)
            stop()
            navigation = JobNavigation(id: created.jobId)
        } catch {
            mutationFailed(error)
        }
    }

    func delete(using service: any JobDetailServicing) async {
        guard job?.status.isActive == false, beginMutation() else { return }
        defer { isMutating = false }
        do {
            _ = try await service.deleteJob(id: jobID)
            stop()
            didDelete = true
        } catch {
            mutationFailed(error)
        }
    }

    func resendEmail(using service: any JobDetailServicing) async {
        guard job?.status == .completed, beginMutation() else { return }
        defer { isMutating = false }
        do {
            _ = try await service.resendEmail(jobID: jobID)
            emailError = nil
            noticeMessage = "邮件已重新发送"
        } catch {
            mutationFailed(error)
        }
    }

    private func beginMutation() -> Bool {
        guard !isMutating else { return false }
        isMutating = true
        errorMessage = nil
        noticeMessage = nil
        return true
    }

    private func mutationFailed(_ error: Error) {
        guard !error.isRequestCancellation else { return }
        errorMessage = error.localizedDescription
    }

    private func copyJob(
        _ current: Job,
        status: JobStatus? = nil,
        title: String? = nil,
        author: String? = nil,
        duration: Double? = nil,
        errorStage: String?? = nil,
        errorMessage: String?? = nil,
        summary: String?? = nil,
        summaryAvailable: Bool?? = nil,
        transcript: [TranscriptCue]?? = nil,
        emailError: String?? = nil
    ) -> Job {
        Job(
            id: current.id,
            url: current.url,
            title: title ?? current.title,
            author: author ?? current.author,
            duration: duration ?? current.duration,
            status: status ?? current.status,
            errorStage: errorStage ?? current.errorStage,
            errorMessage: errorMessage ?? current.errorMessage,
            createdAt: current.createdAt,
            updatedAt: current.updatedAt,
            completedAt: current.completedAt,
            summaryAvailable: summaryAvailable ?? current.summaryAvailable,
            documentId: current.documentId,
            summary: summary ?? current.summary,
            transcript: transcript ?? current.transcript,
            emailError: emailError ?? current.emailError
        )
    }
}
