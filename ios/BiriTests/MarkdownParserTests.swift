import XCTest
@testable import Biri

final class MarkdownParserTests: XCTestCase {
    func testCommonBlocksKeepTheirContent() {
        let markdown = """
        # 标题
        第一段 **重点**。

        > 引用
        - 无序项
        2. 有序项
        ```swift
        let value = 42
        ```
        ---
        """

        let blocks = MarkdownParser.parse(markdown)

        XCTAssertEqual(blocks.count, 7)
        XCTAssertEqual(blocks[0].heading?.text, "标题")
        XCTAssertEqual(blocks[1], .paragraph(id: 1, text: "第一段 **重点**。"))
        XCTAssertEqual(blocks[2], .quote(id: 2, text: "引用"))
        XCTAssertEqual(blocks[3], .listItem(id: 3, number: nil, text: "无序项"))
        XCTAssertEqual(blocks[4], .listItem(id: 4, number: 2, text: "有序项"))
        XCTAssertEqual(blocks[5], .code(id: 5, language: "swift", text: "let value = 42"))
        XCTAssertEqual(blocks[6], .divider(id: 6))
    }

    func testUnclosedCodeFenceDoesNotDropText() {
        let blocks = MarkdownParser.parse("```\n保留这行")
        XCTAssertEqual(blocks, [.code(id: 0, language: "", text: "保留这行")])
    }

    func testPlainTextIsNotMistakenForOrderedList() {
        let blocks = MarkdownParser.parse("版本 2. 仍在同一段落")
        XCTAssertEqual(blocks, [.paragraph(id: 0, text: "版本 2. 仍在同一段落")])
    }
}
