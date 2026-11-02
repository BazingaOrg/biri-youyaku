import Foundation
import Observation

enum DistillConnectionState: Equatable {
    case idle
    case connecting
    case connected
    case reconnecting
    case polling

    var label: String {
        switch self {
        case .idle: ""
        case .connecting: "正在连接实时进度"
        case .connected: "实时更新中"
        case .reconnecting: "正在重新连接"
        case .polling: "实时连接受阻，正在用状态快照更新"
        }
    }
}

@MainActor
@Observable
final class DistillViewModel {
    let mid: Int
    private(set) var author: String
    private(set) var run: DistillRun?
    private(set) var corpus: String?
    private(set) var corpusRunID: String?
    private(set) var connectionState: DistillConnectionState = .idle

    var videoLimit = 50
    var isLoading = false
    var isStarting = false
    var isCancelling = false
    var isDeleting = false
    var isLoadingCorpus = false
    var errorMessage: String?

    private var requestGeneration = 0
    private var observationGeneration = 0
    private var observationTask: Task<Void, Never>?
    private let reconnectDelay: Duration

    init(mid: Int, author: String, reconnectDelay: Duration = .seconds(5)) {
        self.mid = mid
        self.author = author
        self.reconnectDelay = reconnectDelay
    }

    func load(using service: any DistillServicing) async {
        requestGeneration += 1
        let currentGeneration = requestGeneration
        if run == nil { isLoading = true }
        errorMessage = nil
        defer {
            if currentGeneration == requestGeneration { isLoading = false }
        }

        do {
            let latest = try await service.latestDistill(mid: mid)
            guard currentGeneration == requestGeneration else { return }
            adopt(latest, using: service)
        } catch {
            guard currentGeneration == requestGeneration, !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func start(using service: any DistillServicing) async {
        guard !isStarting, !isDeleting, run?.status.isActive != true else { return }
        guard (1...200).contains(videoLimit) else {
            errorMessage = "视频数量需在 1 到 200 之间"
            return
        }

        requestGeneration += 1
        isStarting = true
        errorMessage = nil
        defer { isStarting = false }

        do {
            let started = try await service.startDistill(mid: mid, videoLimit: videoLimit)
            requestGeneration += 1
            adopt(started, using: service)
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }

    func cancel(using service: any DistillServicing) async {
        guard let currentRun = run, currentRun.status.isActive, !isCancelling else { return }
        isCancelling = true
        errorMessage = nil
        defer { isCancelling = false }

        do {
            _ = try await service.cancelDistill(id: currentRun.id)
            let snapshot = try await service.distillStatus(id: currentRun.id)
            apply(.snapshot(snapshot), for: currentRun.id)
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }

    func delete(using service: any DistillServicing) async {
        guard run != nil, run?.status.isActive != true, !isDeleting, !isStarting else { return }
        requestGeneration += 1
        isDeleting = true
        errorMessage = nil
        stopObserving()
        defer { isDeleting = false }

        do {
            _ = try await service.deleteDistill(mid: mid)
            requestGeneration += 1
            run = nil
            corpus = nil
            corpusRunID = nil
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
            if let run, run.status.isActive { startObserving(using: service, runID: run.id) }
        }
    }

    func loadCorpus(using service: any DistillServicing) async {
        guard let currentRun = run,
              currentRun.status == .completed,
              corpusRunID != currentRun.id,
              !isLoadingCorpus else { return }
        isLoadingCorpus = true
        errorMessage = nil
        defer { isLoadingCorpus = false }

        do {
            let loaded = try await service.distillCorpus(id: currentRun.id)
            guard run?.id == currentRun.id, loaded.runId == currentRun.id else { return }
            corpus = loaded.corpus
            corpusRunID = currentRun.id
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }

    func apply(_ event: DistillEvent, for runID: String) {
        guard let currentRun = run, currentRun.id == runID else { return }
        switch event {
        case let .snapshot(snapshot):
            guard snapshot.id == runID, snapshot.mid == mid,
                  snapshot.updatedAt >= currentRun.updatedAt else { return }
            run = snapshot
            if !snapshot.upName.isNilOrEmpty { author = snapshot.upName! }
            if !snapshot.status.isActive { connectionState = .idle }
        case let .status(update):
            guard currentRun.status.isActive || !update.status.isActive else { return }
            let counters = DistillCounters(
                videosTotal: update.videosTotal ?? currentRun.counters.videosTotal,
                videosTranscribed: update.videosTranscribed ?? currentRun.counters.videosTranscribed,
                videosExtracted: update.videosExtracted ?? currentRun.counters.videosExtracted,
                videosFailed: currentRun.counters.videosFailed,
                failedBvids: currentRun.counters.failedBvids
            )
            run = DistillRun(
                id: currentRun.id,
                mid: currentRun.mid,
                upName: currentRun.upName,
                status: update.status,
                videoLimit: currentRun.videoLimit,
                counters: counters,
                error: update.error ?? currentRun.error,
                dirPath: currentRun.dirPath,
                createdAt: currentRun.createdAt,
                updatedAt: currentRun.updatedAt
            )
            if !update.status.isActive { connectionState = .idle }
        }
    }

    func stopObserving() {
        observationGeneration += 1
        observationTask?.cancel()
        observationTask = nil
        connectionState = .idle
    }

    private func adopt(_ newRun: DistillRun?, using service: any DistillServicing) {
        let previousID = run?.id
        stopObserving()
        run = newRun
        if previousID != newRun?.id {
            corpus = nil
            corpusRunID = nil
        }
        if let newRun {
            videoLimit = newRun.videoLimit
            if !newRun.upName.isNilOrEmpty { author = newRun.upName! }
            if newRun.status.isActive { startObserving(using: service, runID: newRun.id) }
        }
    }

    private func startObserving(using service: any DistillServicing, runID: String) {
        observationGeneration += 1
        let currentGeneration = observationGeneration
        observationTask?.cancel()
        connectionState = .connecting
        observationTask = Task { [weak self] in
            guard let self else { return }
            await self.observe(
                using: service,
                runID: runID,
                generation: currentGeneration
            )
        }
    }

    private func observe(
        using service: any DistillServicing,
        runID: String,
        generation currentGeneration: Int
    ) async {
        while isObservationCurrent(runID: runID, generation: currentGeneration) {
            do {
                for try await event in service.distillEvents(id: runID) {
                    guard isObservationCurrent(runID: runID, generation: currentGeneration) else { return }
                    connectionState = .connected
                    apply(event, for: runID)
                    guard run?.status.isActive == true else {
                        guard currentGeneration == observationGeneration, run?.id == runID else { return }
                        var snapshot: DistillRun?
                        for attempt in 0..<3 {
                            snapshot = try? await service.distillStatus(id: runID)
                            if snapshot != nil { break }
                            guard currentGeneration == observationGeneration, run?.id == runID else { return }
                            connectionState = .polling
                            if attempt < 2 {
                                do {
                                    try await Task.sleep(for: reconnectDelay)
                                } catch {
                                    return
                                }
                            }
                        }
                        guard currentGeneration == observationGeneration, run?.id == runID else { return }
                        if let snapshot {
                            apply(.snapshot(snapshot), for: runID)
                        } else {
                            errorMessage = "任务已结束，但最终统计暂未更新。请重新打开此页刷新。"
                        }
                        connectionState = .idle
                        return
                    }
                }
            } catch {
                if Task.isCancelled || error.isRequestCancellation { return }
            }

            guard isObservationCurrent(runID: runID, generation: currentGeneration) else { return }
            connectionState = .polling
            do {
                let snapshot = try await service.distillStatus(id: runID)
                guard isObservationCurrent(runID: runID, generation: currentGeneration) else { return }
                apply(.snapshot(snapshot), for: runID)
            } catch {
                if Task.isCancelled || error.isRequestCancellation { return }
            }

            guard isObservationCurrent(runID: runID, generation: currentGeneration),
                  run?.status.isActive == true else {
                connectionState = .idle
                return
            }
            connectionState = .reconnecting
            do {
                try await Task.sleep(for: reconnectDelay)
            } catch {
                return
            }
        }
    }

    private func isObservationCurrent(runID: String, generation: Int) -> Bool {
        generation == observationGeneration && run?.id == runID && run?.status.isActive == true
    }
}

private extension Optional where Wrapped == String {
    var isNilOrEmpty: Bool {
        switch self {
        case nil: true
        case let .some(value): value.isEmpty
        }
    }
}
