import Foundation
import Security

/// Kleine Hülle um die Schlüsselbund-Ablage für Geheimnisse dieser Installation (nur auf diesem Gerät,
/// nicht in Backups/iCloud).
enum Keychain {
    private static let service = "de.nikgro.sleepsonar"

    enum Lookup: Equatable {
        case found(String)
        /// gibt es nicht
        case missing
        /// gerade nicht lesbar (z. B. vor dem ersten Entsperren nach dem Neustart) – nicht neu anlegen!
        case unavailable(OSStatus)
    }

    static func read(_ key: String) -> Lookup {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: key, kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &out)
        switch status {
        case errSecSuccess:
            guard let data = out as? Data, let text = String(data: data, encoding: .utf8) else { return .unavailable(status) }
            return .found(text)
        case errSecItemNotFound:
            return .missing
        default:
            Log.keychain.error("Schlüsselbund lesen \(key, privacy: .public): \(status)")
            return .unavailable(status)
        }
    }

    /// Wert, falls vorhanden und lesbar
    static func get(_ key: String) -> String? {
        if case .found(let v) = read(key) { return v }
        return nil
    }

    /// Überschreibt einen vorhandenen Eintrag (SecItemUpdate) oder legt ihn an – nie erst löschen, damit bei
    /// einem Fehler dazwischen nichts verloren geht
    @discardableResult
    static func set(_ key: String, _ value: String) -> Bool {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                   kSecAttrAccount as String: key]
        let data = Data(value.utf8)
        var status = SecItemUpdate(base as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = base
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(add as CFDictionary, nil)
        }
        if status != errSecSuccess { Log.keychain.fault("Schlüsselbund schreiben \(key, privacy: .public): \(status)") }
        return status == errSecSuccess
    }

    static func delete(_ key: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: key]
        SecItemDelete(q as CFDictionary)
    }
}
