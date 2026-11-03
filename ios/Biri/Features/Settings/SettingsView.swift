import SwiftUI

struct SettingsView: View {
    @AppStorage("appearance") private var appearance: AppearancePreference = .system
    @AppStorage("reader-text-size") private var readerTextSize: ReaderTextSize = .standard

    var body: some View {
        Form {
            Section("连接") {
                NavigationLink {
                    ServerSettingsView()
                } label: {
                    Label {
                        VStack(alignment: .leading) {
                            Text("服务器")
                            Text("查看或更改连接")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "server.rack")
                    }
                }
            }

            Section("内容管理") {
                NavigationLink {
                    TrashView()
                } label: {
                    Label {
                        VStack(alignment: .leading) {
                            Text("回收站")
                            Text("恢复或彻底删除已移除的笔记")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "trash")
                    }
                }
            }

            Section("外观") {
                Picker("外观", selection: $appearance) {
                    ForEach(AppearancePreference.allCases) { preference in
                        Text(preference.label).tag(preference)
                    }
                }
                .pickerStyle(.segmented)

                Picker("阅读字号", selection: $readerTextSize) {
                    ForEach(ReaderTextSize.allCases) { size in
                        Text(size.label).tag(size)
                    }
                }
                .pickerStyle(.segmented)
            }

            Section("关于") {
                LabeledContent("应用", value: "笔哩")
                LabeledContent("版本", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0")
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }
}

struct ServerSettingsView: View {
    var isInitialSetup = false

    @Environment(AppModel.self) private var appModel
    @Environment(\.dismiss) private var dismiss
    @State private var address = ""
    @State private var token = ""
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var confirmClearToken = false

    var body: some View {
        Form {
            if isInitialSetup {
                Section {
                    VStack(spacing: 16) {
                        BrandIconView()
                        Text("把视频链接整理成可阅读、可搜索的笔记。")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)
                    .listRowBackground(Color.clear)
                }
            }

            Section {
                TextField("服务器地址", text: $address, prompt: Text("https://api.example.com").foregroundStyle(.secondary))
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField(
                    "访问令牌（API Token）",
                    text: $token,
                    prompt: Text(appModel.hasSavedToken ? "输入新 Token 以更换" : "服务器未启用访问验证时可留空").foregroundStyle(.secondary)
                )
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if appModel.hasSavedToken && !isInitialSetup {
                    LabeledContent("已保存的 Token", value: "••••••••")
                    Button("移除 Token", role: .destructive) {
                        confirmClearToken = true
                    }
                }
            } footer: {
                Text("服务器开启访问验证时填写 API Token；Token 仅保存在本机钥匙串。")
            }

            if let info = appModel.connectionInfo {
                Section("当前连接") {
                    LabeledContent("状态", value: "已连接")
                    LabeledContent("访问验证", value: info.authMode == "api_token" ? "需要 Token" : "无需 Token")
                    LabeledContent("全文搜索", value: info.knowledgeSearchEnabled ? "已启用" : "未启用")
                    if !info.knowledgeSearchEnabled {
                        Text("仍可搜索标题、作者等基本信息。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .font(.callout)
                }
            }

            if isInitialSetup || hasChanges || appModel.connectionInfo == nil {
                Section {
                    Button {
                        Task { await connect() }
                    } label: {
                        HStack {
                            Spacer()
                            if isSaving { ProgressView().controlSize(.small).padding(.trailing, 8) }
                            Text(isSaving ? "正在连接…" : connectButtonTitle)
                            Spacer()
                        }
                    }
                    .disabled(isSaving || address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .navigationTitle(isInitialSetup ? "连接服务器" : "服务器")
        .navigationBarTitleDisplayMode(isInitialSetup ? .large : .inline)
        .onAppear {
            if address.isEmpty { address = appModel.serverURL?.absoluteString ?? "" }
        }
        .confirmationDialog("从这台 iPhone 移除已保存的 API Token？", isPresented: $confirmClearToken, titleVisibility: .visible) {
            Button("移除 Token", role: .destructive) {
                do {
                    try appModel.clearSavedToken()
                } catch {
                    errorMessage = error.localizedDescription
                }
            }
            Button("取消", role: .cancel) {}
        }
    }

    private var hasChanges: Bool {
        if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return true }
        let normalizedAddress = (try? ServerEndpoint.parse(address))?.absoluteString
        return normalizedAddress != appModel.serverURL?.absoluteString
    }

    private var connectButtonTitle: String {
        isInitialSetup || appModel.connectionInfo == nil ? "连接" : "保存并重新连接"
    }

    private func connect() async {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }
        do {
            try await appModel.connect(address: address, enteredToken: token)
            token = ""
            if !isInitialSetup { dismiss() }
        } catch {
            if !error.isRequestCancellation { errorMessage = error.localizedDescription }
        }
    }
}
