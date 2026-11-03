import SwiftUI

struct BrandIconView: View {
    var body: some View {
        Image("BrandIcon")
            .resizable()
            .scaledToFit()
            .frame(width: 88, height: 88)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .accessibilityHidden(true)
    }
}

struct LoadMoreRow: View {
    var isLoading: Bool
    var title = "加载更多"
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if isLoading {
                    ProgressView().controlSize(.small)
                }
                Text(isLoading ? "正在加载…" : title)
            }
            .font(.callout.weight(.medium))
            .foregroundStyle(isLoading ? Color.secondary : Color.accentColor)
            .frame(maxWidth: .infinity, minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 16))
        .listRowSeparator(.hidden)
    }
}

struct ErrorStateView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("暂时无法加载", systemImage: "wifi.exclamationmark")
        } description: {
            Text(message)
        } actions: {
            Button("重试", action: retry)
                .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}
