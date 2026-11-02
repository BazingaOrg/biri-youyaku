import XCTest
@testable import Biri

@MainActor
final class TrashViewModelExpansionTests: XCTestCase {
    func testPurgeRequiresExactTitleAndRemovesOnlyConfirmedItem() async {
        let service = TrashControlledService()
        let item = makeItem(id: "doc-1", title: "完整标题")
        service.pages = [TrashPage(ok: true, items: [item, makeItem(id: "doc-2", title: "另一篇")])]
        let viewModel = TrashViewModel()
        await viewModel.load(using: service)
        viewModel.beginPurge(item)

        viewModel.purgeConfirmation = "完整"
        await viewModel.confirmPurge(using: service)

        XCTAssertTrue(service.purgeRequests.isEmpty)
        XCTAssertEqual(viewModel.purgeCandidate, item)
        XCTAssertEqual(viewModel.items.count, 2)

        viewModel.purgeConfirmation = "完整标题"
        await viewModel.confirmPurge(using: service)

        XCTAssertEqual(service.purgeRequests.map(\.id), ["doc-1"])
        XCTAssertEqual(service.purgeRequests.map(\.title), ["完整标题"])
        XCTAssertEqual(viewModel.items.map(\.id), ["doc-2"])
        XCTAssertNil(viewModel.purgeCandidate)
        XCTAssertEqual(viewModel.purgeConfirmation, "")
        XCTAssertNotNil(viewModel.feedbackMessage)
    }

    func testRestoreRemovesItemAndReportsRecovery() async {
        let service = TrashControlledService()
        let item = makeItem(id: "doc-1", title: "可恢复")
        service.pages = [TrashPage(ok: true, items: [item])]
        let viewModel = TrashViewModel()
        await viewModel.load(using: service)

        await viewModel.restore(item, using: service)

        XCTAssertEqual(service.restoredIDs, ["doc-1"])
        XCTAssertTrue(viewModel.items.isEmpty)
        XCTAssertTrue(viewModel.feedbackMessage?.contains("已恢复") == true)
        XCTAssertTrue(viewModel.mutatingIDs.isEmpty)
    }

    func testTrashPageStartedBeforeRestoreCannotReinsertRestoredItem() async {
        let service = TrashControlledService()
        let item = makeItem(id: "doc-1", title: "可恢复")
        let stalePage = TrashPage(ok: true, items: [item])
        service.pages = [stalePage]
        let viewModel = TrashViewModel()
        await viewModel.load(using: service)
        service.suspendTrash = true

        let reload = Task { await viewModel.load(using: service) }
        guard await waitUntil({ service.trashContinuation != nil }) else {
            await reload.value
            return XCTFail("The reload did not suspend")
        }
        await viewModel.restore(item, using: service)
        service.trashContinuation?.resume(returning: stalePage)
        await reload.value

        XCTAssertTrue(viewModel.items.isEmpty)
        XCTAssertTrue(viewModel.feedbackMessage?.contains("已恢复") == true)
    }

    private func waitUntil(_ condition: @escaping @MainActor () -> Bool) async -> Bool {
        for _ in 0..<2_000 {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(1))
        }
        return condition()
    }

    private func makeItem(id: String, title: String) -> TrashItem {
        TrashItem(
            documentId: id, title: title, author: "作者", provider: "bilibili", sourceId: "BV1",
            sourcePart: nil, bvid: "BV1", deletedAt: 1000, expiresAt: 2000, daysLeft: 6
        )
    }
}

@MainActor
private final class TrashControlledService: LibraryLifecycleServicing {
    struct PurgeRequest {
        let id: String
        let title: String
    }

    var pages: [TrashPage] = []
    var suspendTrash = false
    var trashContinuation: CheckedContinuation<TrashPage, Never>?
    private(set) var restoredIDs: [String] = []
    private(set) var purgeRequests: [PurgeRequest] = []

    func library(cursor: CursorValue?, limit: Int, up: String?, tag: String?) async throws -> LibraryPage {
        LibraryPage(items: [], nextCursor: nil, total: 0)
    }

    func trash() async throws -> TrashPage {
        if suspendTrash {
            suspendTrash = false
            return await withCheckedContinuation { trashContinuation = $0 }
        }
        return pages.removeFirst()
    }

    func softDeleteDocument(id: String, reason: String?) async throws -> LifecycleDocument {
        LifecycleDocument(id: id, title: nil, author: nil, bvid: nil, cid: nil, deletedAt: 1000, deleteReason: reason)
    }

    func restoreDocument(id: String) async throws -> LifecycleDocument {
        restoredIDs.append(id)
        return LifecycleDocument(id: id, title: nil, author: nil, bvid: nil, cid: nil, deletedAt: nil, deleteReason: nil)
    }

    func purgeDocument(id: String, confirmedTitle: String) async throws -> DocumentPurgeResult {
        purgeRequests.append(PurgeRequest(id: id, title: confirmedTitle))
        return DocumentPurgeResult(ok: true, id: id, purged: true, title: confirmedTitle, bvid: nil)
    }
}
