import SwiftUI

enum SearchHighlight {
    static func attributed(_ text: String, query: String?, markdown: Bool = false) -> AttributedString {
        var result = markdown ? InlineMarkdown.attributed(text) : AttributedString(text)
        let trimmed = query?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty else { return result }

        let plain = String(result.characters)
        var searchRange = plain.startIndex..<plain.endIndex
        while let range = plain.range(
            of: trimmed,
            options: [.caseInsensitive, .diacriticInsensitive],
            range: searchRange
        ) {
            guard let lower = AttributedString.Index(range.lowerBound, within: result),
                  let upper = AttributedString.Index(range.upperBound, within: result) else { break }
            result[lower..<upper].backgroundColor = Color.yellow.opacity(0.35)
            searchRange = range.upperBound..<plain.endIndex
        }
        return result
    }

    static func matchCount(in text: String, query: String) -> Int {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !text.isEmpty else { return 0 }
        var count = 0
        var searchRange = text.startIndex..<text.endIndex
        while let range = text.range(
            of: trimmed,
            options: [.caseInsensitive, .diacriticInsensitive],
            range: searchRange
        ) {
            count += 1
            searchRange = range.upperBound..<text.endIndex
        }
        return count
    }
}
