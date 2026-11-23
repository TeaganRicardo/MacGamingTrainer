// Generated from games.reference_fixture.command_contract. Do not edit.
import Foundation

enum ReferenceFixtureCommand: String {
    case status = "status"
    case connect = "connect"
    case disconnect = "disconnect"
    case setEnabled = "set_enabled"
    case disableAll = "disable_all"
    case listProfiles = "list_profiles"
    case saveProfile = "save_profile"
    case loadProfile = "load_profile"
    case deleteProfile = "delete_profile"
    case diagnostics = "diagnostics"
    case fail = "fail"

    var timeout: TimeInterval {
        switch self {
        default: return 6.0
        }
    }

    var supportsOfflineIntent: Bool {
        switch self {
        case .setEnabled, .disableAll, .loadProfile: return true
        default: return false
        }
    }

    private var baseRequiresTrustedTarget: Bool {
        switch self {
        case .listProfiles, .saveProfile, .deleteProfile, .diagnostics, .fail: return false
        default: return true
        }
    }

    func offlineIntent(connected: Bool) -> Bool {
        !connected && supportsOfflineIntent
    }

    func requiresTrustedTarget(connected: Bool) -> Bool {
        baseRequiresTrustedTarget && !offlineIntent(connected: connected)
    }
}
