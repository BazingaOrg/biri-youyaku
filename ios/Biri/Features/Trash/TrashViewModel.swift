import Foundation
import Observation

@MainActor
@Observable
final class TrashViewModel {
    private(set) var items: [TrashItem] = []
    private(set) var purgeCandidate: TrashItem?
    private(set) var mutatingIDs: Set<String> = []
    var purgeConfirmation = ""
    var isLoading = false
    var errorMessage: String?
    var feedbackMessage: String?

    private var generation = 0
    private var mutationRevision = 0
    private var operationGenerations: [String: Int] = [:]

    var canConfirmPurge: Bool {
        guard let item = purgeCandidate, !item.title.isEmpty, !isPurging else { return false }
        return purgeConfirmation == item.title
    }

    var isPurging: Bool {
        guard let id = purgeCandidate?.id else { return false }
        return mutatingIDs.contains(id)
    }

    func load(using service: any LibraryLifecycleServicing) async {
        generation += 1
        let currentGeneration = generation
        let currentMutationRevision = mutationRevision
        isLoading = true
        errorMessage = nil
        defer { if currentGeneration == generation { isLoading = false } }
        do {
            let page = try await service.trash()
            guard currentGeneration == generation, currentMutationRevision == mutationRevision else { return }
            items = page.items
        } catch {
            guard currentGeneration == generation,
                  currentMutationRevision == mutationRevision,
                  !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func restore(_ item: TrashItem, using service: any LibraryLifecycleServicing) async {
        guard beginMutation(for: item.id) else { return }
        let operation = operationGenerations[item.id]!
        errorMessage = nil
        feedbackMessage = nil
        defer { finishMutation(for: item.id, operation: operation) }
        do {
            _ = try await service.restoreDocument(id: item.id)
            guard isCurrentMutation(item.id, operation: operation) else { return }
            items.removeAll { $0.id == item.id }
            feedbackMessage = "已恢复《\(item.displayTitle)》，可在资料库中阅读。"
        } catch {
            guard isCurrentMutation(item.id, operation: operation), !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func beginPurge(_ item: TrashItem) {
        guard !mutatingIDs.contains(item.id) else { return }
        purgeCandidate = item
        purgeConfirmation = ""
        errorMessage = nil
        feedbackMessage = nil
    }

    func cancelPurge() {
        guard !isPurging else { return }
        purgeCandidate = nil
        purgeConfirmation = ""
    }

    func confirmPurge(using service: any LibraryLifecycleServicing) async {
        guard canConfirmPurge, let item = purgeCandidate else { return }
        guard beginMutation(for: item.id) else { return }
        let operation = operationGenerations[item.id]!
        errorMessage = nil
        feedbackMessage = nil
        defer { finishMutation(for: item.id, operation: operation) }
        do {
            let result = try await service.purgeDocument(id: item.id, confirmedTitle: purgeConfirmation)
            guard isCurrentMutation(item.id, operation: operation) else { return }
            if result.purged {
                items.removeAll { $0.id == item.id }
                feedbackMessage = "《\(item.displayTitle)》已彻底删除。"
            } else {
                errorMessage = "服务器尚未彻底删除这篇笔记，请稍后重试。"
            }
            purgeCandidate = nil
            purgeConfirmation = ""
        } catch {
            guard isCurrentMutation(item.id, operation: operation), !error.isRequestCancellation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func isMutating(_ item: TrashItem) -> Bool {
        mutatingIDs.contains(item.id)
    }

    private func beginMutation(for id: String) -> Bool {
        guard !mutatingIDs.contains(id) else { return false }
        mutationRevision += 1
        let operation = (operationGenerations[id] ?? 0) + 1
        operationGenerations[id] = operation
        mutatingIDs.insert(id)
        return true
    }

    private func finishMutation(for id: String, operation: Int) {
        guard isCurrentMutation(id, operation: operation) else { return }
        mutatingIDs.remove(id)
    }

    private func isCurrentMutation(_ id: String, operation: Int) -> Bool {
        operationGenerations[id] == operation
    }
}
