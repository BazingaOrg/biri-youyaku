import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            NavigationStack {
                LibraryView()
            }
            .tabItem { Label("笔记", systemImage: "books.vertical") }

            NavigationStack {
                JobsView()
            }
            .tabItem { Label("任务", systemImage: "checklist") }

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label("设置", systemImage: "gearshape") }
        }
    }
}
