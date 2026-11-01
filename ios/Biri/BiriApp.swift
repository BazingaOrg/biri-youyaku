import SwiftUI

@main
struct BiriApp: App {
    @State private var appModel = AppModel()
    @AppStorage("appearance") private var appearance: AppearancePreference = .system

    var body: some Scene {
        WindowGroup {
            Group {
                if appModel.isConfigured {
                    MainTabView()
                        .id(appModel.connectionRevision)
                } else {
                    NavigationStack {
                        ServerSettingsView(isInitialSetup: true)
                    }
                }
            }
            .environment(appModel)
            .tint(Color.accentColor)
            .preferredColorScheme(appearance.colorScheme)
        }
    }
}
