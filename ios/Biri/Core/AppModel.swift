import Foundation
import Observation
import SwiftUI

enum AppearancePreference: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }
    var label: String {
        switch self {
        case .system: "自动"
        case .light: "浅色"
        case .dark: "深色"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }
}

enum ReaderTextSize: String, CaseIterable, Identifiable {
    case small
    case standard
    case large

    var id: String { rawValue }
    var label: String {
        switch self {
        case .small: "小"
        case .standard: "标准"
        case .large: "大"
        }
    }

    var scale: Double {
        switch self {
        case .small: 0.92
        case .standard: 1
        case .large: 1.14
        }
    }
}

@MainActor
@Observable
final class AppModel {
    typealias ConnectionValidator = @MainActor (URL, String?) async throws -> RuntimeConfiguration

    private static let serverURLKey = "server-url"

    private(set) var serverURL: URL?
    private(set) var connectionInfo: RuntimeConfiguration?
    private(set) var connectionRevision = 0

    private let defaults: UserDefaults
    private let keychain: any CredentialStoring
    private let validateConnection: ConnectionValidator
    private var connectionGeneration = 0

    init(
        defaults: UserDefaults = .standard,
        keychain: any CredentialStoring = KeychainStore(),
        validateConnection: ConnectionValidator? = nil
    ) {
        self.defaults = defaults
        self.keychain = keychain
        self.validateConnection = validateConnection ?? { url, token in
            try await APIClient(baseURL: url, token: token).validateConnection()
        }
        if let value = defaults.string(forKey: Self.serverURLKey) {
            serverURL = try? ServerEndpoint.parse(value)
        }
    }

    var isConfigured: Bool { serverURL != nil }
    var hasSavedToken: Bool { keychain.readToken() != nil }

    func makeService() throws -> any BiriServicing {
        guard let serverURL else { throw APIError.notConfigured }
        return APIClient(baseURL: serverURL, token: keychain.readToken())
    }

    func connect(address: String, enteredToken: String) async throws {
        let url = try ServerEndpoint.parse(address)
        connectionGeneration += 1
        let currentGeneration = connectionGeneration
        let previousURL = serverURL
        let newToken = enteredToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let candidateToken = Self.credentialToken(
            currentURL: previousURL,
            newURL: url,
            enteredToken: newToken,
            savedToken: keychain.readToken()
        )
        let info = try await validateConnection(url, candidateToken)
        guard currentGeneration == connectionGeneration else { throw CancellationError() }

        if !newToken.isEmpty {
            try keychain.saveToken(newToken)
        } else if Self.shouldDiscardSavedToken(currentURL: previousURL, newURL: url, enteredToken: newToken) {
            try keychain.deleteToken()
        }
        defaults.set(url.absoluteString, forKey: Self.serverURLKey)
        serverURL = url
        connectionInfo = info
        connectionRevision += 1
    }

    static func credentialToken(currentURL: URL?, newURL: URL, enteredToken: String, savedToken: String?) -> String? {
        if !enteredToken.isEmpty { return enteredToken }
        return currentURL == newURL ? savedToken : nil
    }

    static func shouldDiscardSavedToken(currentURL: URL?, newURL: URL, enteredToken: String) -> Bool {
        currentURL != newURL && enteredToken.isEmpty
    }

    func clearSavedToken() throws {
        try keychain.deleteToken()
        connectionInfo = nil
        connectionRevision += 1
    }
}
