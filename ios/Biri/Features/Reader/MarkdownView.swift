import SwiftUI

struct MarkdownView: View {
    let blocks: [MarkdownBlock]
    let fontScale: Double

    @ScaledMetric(relativeTo: .body) private var bodySize = 17

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(blocks) { block in
                blockView(block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case let .heading(id, level, text):
            Text(InlineMarkdown.attributed(text))
                .font(.system(size: bodySize * fontScale * headingFactor(level), weight: .semibold, design: .serif))
                .padding(.top, level <= 2 ? 12 : 4)
                .id(id)
        case let .paragraph(_, text):
            Text(InlineMarkdown.attributed(text))
                .font(bodyFont)
                .lineSpacing(7)
        case let .quote(_, text):
            HStack(alignment: .top, spacing: 12) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.accentColor)
                    .frame(width: 3)
                Text(InlineMarkdown.attributed(text))
                    .font(bodyFont)
                    .foregroundStyle(.secondary)
                    .lineSpacing(6)
            }
        case let .listItem(_, number, text):
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(number.map(String.init) ?? "•")
                    .font(bodyFont)
                    .foregroundStyle(Color.accentColor)
                    .frame(minWidth: 18, alignment: .trailing)
                Text(InlineMarkdown.attributed(text))
                    .font(bodyFont)
                    .lineSpacing(6)
            }
        case let .code(_, language, text):
            VStack(alignment: .leading, spacing: 8) {
                if !language.isEmpty {
                    Text(language)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ScrollView(.horizontal) {
                    Text(text)
                        .font(.system(size: bodySize * fontScale * 0.86, design: .monospaced))
                        .textSelection(.enabled)
                        .padding(12)
                }
            }
            .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
        case .divider:
            Divider()
        }
    }

    private var bodyFont: Font {
        .system(size: bodySize * fontScale, design: .serif)
    }

    private func headingFactor(_ level: Int) -> Double {
        switch level {
        case 1: 1.25
        case 2: 1.18
        case 3: 1.1
        default: 1.05
        }
    }
}
