import Foundation

struct MarkdownHeading: Identifiable, Hashable {
    let id: Int
    let level: Int
    let text: String
}

enum MarkdownBlock: Identifiable, Hashable {
    case heading(id: Int, level: Int, text: String)
    case paragraph(id: Int, text: String)
    case quote(id: Int, text: String)
    case listItem(id: Int, number: Int?, text: String)
    case code(id: Int, language: String, text: String)
    case divider(id: Int)

    var id: Int {
        switch self {
        case let .heading(id, _, _), let .paragraph(id, _), let .quote(id, _),
             let .listItem(id, _, _), let .code(id, _, _), let .divider(id):
            id
        }
    }

    var heading: MarkdownHeading? {
        if case let .heading(id, level, text) = self {
            return MarkdownHeading(id: id, level: level, text: text)
        }
        return nil
    }
}

struct MarkdownParser {
    static func parse(_ markdown: String) -> [MarkdownBlock] {
        let normalized = markdown.replacingOccurrences(of: "\r\n", with: "\n")
        let lines = normalized.components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var code: [String] = []
        var codeLanguage = ""
        var insideCode = false
        var nextID = 0

        func id() -> Int {
            defer { nextID += 1 }
            return nextID
        }

        func flushParagraph() {
            guard !paragraph.isEmpty else { return }
            let text = paragraph.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty { blocks.append(.paragraph(id: id(), text: text)) }
            paragraph.removeAll()
        }

        func flushCode() {
            blocks.append(.code(id: id(), language: codeLanguage, text: code.joined(separator: "\n")))
            code.removeAll()
            codeLanguage = ""
        }

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") {
                if insideCode {
                    flushCode()
                    insideCode = false
                } else {
                    flushParagraph()
                    codeLanguage = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                    insideCode = true
                }
                continue
            }
            if insideCode {
                code.append(line)
                continue
            }
            if trimmed.isEmpty {
                flushParagraph()
                continue
            }

            let hashes = trimmed.prefix(while: { $0 == "#" })
            if (1...6).contains(hashes.count) {
                let index = trimmed.index(trimmed.startIndex, offsetBy: hashes.count)
                if trimmed[index...].hasPrefix(" ") {
                    flushParagraph()
                    let text = trimmed[index...].drop(while: { $0 == " " })
                    blocks.append(.heading(id: id(), level: hashes.count, text: String(text)))
                    continue
                }
            }

            if ["---", "***", "___"].contains(trimmed) {
                flushParagraph()
                blocks.append(.divider(id: id()))
                continue
            }
            if trimmed.hasPrefix(">") {
                flushParagraph()
                let text = trimmed.dropFirst().drop(while: { $0 == " " })
                blocks.append(.quote(id: id(), text: String(text)))
                continue
            }
            if ["- ", "* ", "+ "].contains(where: trimmed.hasPrefix) {
                flushParagraph()
                blocks.append(.listItem(id: id(), number: nil, text: String(trimmed.dropFirst(2))))
                continue
            }
            let components = trimmed.split(separator: " ", maxSplits: 1).map(String.init)
            if components.count == 2,
               components[0].hasSuffix("."),
               let number = Int(components[0].dropLast()) {
                flushParagraph()
                blocks.append(.listItem(id: id(), number: number, text: components[1]))
                continue
            }
            paragraph.append(line)
        }
        flushParagraph()
        if insideCode { flushCode() }
        return blocks
    }
}

enum InlineMarkdown {
    static func attributed(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }
}
