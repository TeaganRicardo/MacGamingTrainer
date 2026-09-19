import Foundation

enum Hades2Command: String {
    case scan, status, connect, disconnect, launch
    case disableAll = "disable_all"
    case resetDesired = "reset_desired"
    case setDesired = "set_desired"
    case setVital = "set_vital"
    case setCounter = "set_counter"
    case lockVital = "lock_vital"
    case setResource = "set_resource"
    case lockResource = "lock_resource"
    case setRerolls = "set_rerolls"
    case lockRerolls = "lock_rerolls"
    case setStat = "set_stat"
    case setElement = "set_element"
    case lockElement = "lock_element"
    case setBoonRarityDesired = "set_boon_rarity_desired"
    case setNextRoomRewardDesired = "set_next_room_reward_desired"
    case spawnReward = "spawn_reward"
    case openSellTraits = "open_sell_traits"
    case openSpecialChoice = "open_special_choice"
    case listProfiles = "list_profiles"
    case saveProfile = "save_profile"
    case loadProfile = "load_profile"
    case deleteProfile = "delete_profile"
    case diagnostics
    case exportDiagnostics = "export_diagnostics"
    case backup
    case listBackups = "list_backups"
    case renameBackup = "rename_backup"
    case openBackupFolder = "open_backup_folder"
    case restoreBackup = "restore_backup"
    case deleteBackup = "delete_backup"
    case cancelStagedRestore = "cancel_staged_restore"
    case prepare
    case restore
}

/// Typed Hades module-protocol-v5 request boundary. Command spelling and JSON parameter
/// keys live here rather than being duplicated through the store and views.
enum Hades2Request {
    case scan, status, connect, disconnect, launch, disableAll, resetDesired
    case setDesired(feature: String, value: Any)
    case setVital(vital: String, field: String, value: Double)
    case setCounter(counter: String, value: Double)
    case lockVital(vital: String, locked: Bool)
    case setResource(resource: String, amount: Int)
    case lockResource(resource: String, locked: Bool)
    case setRerolls(amount: Int)
    case lockRerolls(locked: Bool)
    case setStat(stat: String, locked: Bool, value: Any?)
    case setElement(element: String, amount: Int)
    case lockElement(element: String, locked: Bool)
    case setBoonRarity(target: String, multiplier: Double, forceLegendary: Bool, forceDuo: Bool)
    case setNextRoomReward(String?)
    case spawnReward(String)
    case openSellTraits
    case openSpecialChoice(source: String)
    case listProfiles
    case saveProfile(name: String, shortcuts: [String: Any])
    case loadProfile(String)
    case deleteProfile(String)
    case diagnostics, exportDiagnostics
    case backup(runCount: Int?)
    case listBackups
    case renameBackup(id: String, name: String)
    case openBackupFolder(String?)
    case restoreBackup(String)
    case deleteBackup(String)
    case cancelStagedRestore
    case prepare, restore

    var command: Hades2Command {
        switch self {
        case .scan: return .scan
        case .status: return .status
        case .connect: return .connect
        case .disconnect: return .disconnect
        case .launch: return .launch
        case .disableAll: return .disableAll
        case .resetDesired: return .resetDesired
        case .setDesired: return .setDesired
        case .setVital: return .setVital
        case .setCounter: return .setCounter
        case .lockVital: return .lockVital
        case .setResource: return .setResource
        case .lockResource: return .lockResource
        case .setRerolls: return .setRerolls
        case .lockRerolls: return .lockRerolls
        case .setStat: return .setStat
        case .setElement: return .setElement
        case .lockElement: return .lockElement
        case .setBoonRarity: return .setBoonRarityDesired
        case .setNextRoomReward: return .setNextRoomRewardDesired
        case .spawnReward: return .spawnReward
        case .openSellTraits: return .openSellTraits
        case .openSpecialChoice: return .openSpecialChoice
        case .listProfiles: return .listProfiles
        case .saveProfile: return .saveProfile
        case .loadProfile: return .loadProfile
        case .deleteProfile: return .deleteProfile
        case .diagnostics: return .diagnostics
        case .exportDiagnostics: return .exportDiagnostics
        case .backup: return .backup
        case .listBackups: return .listBackups
        case .renameBackup: return .renameBackup
        case .openBackupFolder: return .openBackupFolder
        case .restoreBackup: return .restoreBackup
        case .deleteBackup: return .deleteBackup
        case .cancelStagedRestore: return .cancelStagedRestore
        case .prepare: return .prepare
        case .restore: return .restore
        }
    }


    var timeout: TimeInterval {
        switch self {
        case .scan:
            // pgrep is normally quick, but historical successful scans can exceed
            // four seconds while Steam/game process state is settling.
            return 15.0
        case .status:
            // A live status request can spend up to ~3 s waiting for the Lua
            // boundary, then still needs debugger stop/focus-restore/resume
            // cleanup. Keep the host watchdog outside those transport deadlines
            // so it never SIGTERMs the debugger owner mid-cleanup.
            return 15.0
        case .connect:
            // LLDB attach + symbol validation + first Lua bootstrap is the slow
            // path. Real successful Hades II connections have taken >50 s on
            // the target Mac; a 12 s watchdog incorrectly killed healthy attach.
            return 90.0
        case .disconnect:
            return 12.0
        case .launch:
            return 10.0
        case .prepare, .restore:
            return 30.0
        case .backup, .restoreBackup, .deleteBackup, .renameBackup, .openBackupFolder:
            return 15.0
        case .diagnostics, .exportDiagnostics:
            return 15.0
        default:
            return 6.0
        }
    }

    var params: [String: Any] {
        switch self {
        case .setDesired(let feature, let value):
            return ["feature": feature, "value": value]
        case .setVital(let vital, let field, let value):
            return ["vital": vital, "field": field, "value": value]
        case .setCounter(let counter, let value):
            return ["counter": counter, "value": value]
        case .lockVital(let vital, let locked):
            return ["vital": vital, "locked": locked]
        case .setResource(let resource, let amount):
            return ["resource": resource, "amount": amount]
        case .lockResource(let resource, let locked):
            return ["resource": resource, "locked": locked]
        case .setRerolls(let amount):
            return ["amount": amount]
        case .lockRerolls(let locked):
            return ["locked": locked]
        case .setStat(let stat, let locked, let value):
            var result: [String: Any] = ["stat": stat, "locked": locked]
            if let value { result["value"] = value }
            return result
        case .setElement(let element, let amount):
            return ["element": element, "amount": amount]
        case .lockElement(let element, let locked):
            return ["element": element, "locked": locked]
        case .setBoonRarity(let target, let multiplier, let forceLegendary, let forceDuo):
            return ["target": target, "multiplier": multiplier, "forceLegendary": forceLegendary, "forceDuo": forceDuo]
        case .setNextRoomReward(let reward):
            return ["reward": reward ?? NSNull()]
        case .spawnReward(let reward):
            return ["reward": reward]
        case .openSellTraits:
            return [:]
        case .openSpecialChoice(let source):
            return ["source": source]
        case .saveProfile(let name, let shortcuts):
            return ["name": name, "shortcuts": shortcuts]
        case .loadProfile(let name), .deleteProfile(let name):
            return ["name": name]
        case .backup(let runCount):
            return runCount.map { ["runCount": $0] } ?? [:]
        case .renameBackup(let id, let name):
            return ["backupId": id, "name": name]
        case .openBackupFolder(let id):
            return id.map { ["backupId": $0] } ?? [:]
        case .restoreBackup(let id), .deleteBackup(let id):
            return ["backupId": id]
        default:
            return [:]
        }
    }
}

final class Hades2API {
    private let session: TrainerBackendSession

    init(session: TrainerBackendSession) {
        self.session = session
    }

    func request(
        _ request: Hades2Request,
        operation: String,
        coalesceKey: String? = nil,
        announceSuccess: Bool = true,
        completion: ((Bool) -> Void)? = nil
    ) {
        session.send(
            request.command.rawValue,
            params: request.params,
            operation: operation,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            timeout: request.timeout,
            completion: completion
        )
    }
}
