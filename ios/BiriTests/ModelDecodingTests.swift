import XCTest
@testable import Biri

final class ModelDecodingTests: XCTestCase {
    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    func testLibraryItemAndCursorDecode() throws {
        let data = Data(#"""
        {
          "items": [{
            "kind": "document", "id": "doc-1", "document_id": "doc-1", "job_id": "job-1",
            "title": "标题", "author": "作者", "provider": "bilibili", "duration": 61,
            "tags": ["学习"], "tldr": "摘要", "saved_at": 1000,
            "source_url": "https://example.com/video", "legacy": false
          }],
          "next_cursor": "cursor-value", "total": 1
        }
        """#.utf8)

        let page = try decoder.decode(LibraryPage.self, from: data)

        XCTAssertEqual(page.items.first?.destination.id, "doc-1")
        XCTAssertEqual(page.items.first?.destination.kind, .document)
        XCTAssertEqual(page.nextCursor?.raw, "cursor-value")
    }

    func testJobListAcceptsIntegerCursorAndMissingDetailFields() throws {
        let data = Data(#"""
        {
          "jobs": [{
            "id": "job-1", "url": "https://example.com", "title": null, "author": null,
            "duration": null, "status": "SUMMARIZING", "error_stage": null,
            "error_message": null, "created_at": 1000, "updated_at": 2000,
            "completed_at": null, "summary_available": false
          }],
          "next_cursor": 2000
        }
        """#.utf8)

        let page = try decoder.decode(JobPage.self, from: data)

        XCTAssertEqual(page.jobs.first?.status, .summarizing)
        XCTAssertTrue(page.jobs.first?.status.isActive == true)
        XCTAssertEqual(page.nextCursor?.raw, "2000")
    }

    func testDocumentContentDecodesTranscript() throws {
        let data = Data(#"""
        {
          "document": {
            "document_id": "doc-1", "job_id": "job-1", "title": "标题", "author": "作者",
            "provider": "bilibili", "source_url": "https://example.com", "duration": 65,
            "tldr": null, "updated_at": 2000
          },
          "markdown": "## 小节",
          "cues": [{"start": 2.5, "end": 4.0, "text": "字幕"}]
        }
        """#.utf8)

        let content = try decoder.decode(DocumentContent.self, from: data)

        XCTAssertEqual(content.document.documentId, "doc-1")
        XCTAssertEqual(content.cues.first?.timeLabel, "00:03")
    }
}
