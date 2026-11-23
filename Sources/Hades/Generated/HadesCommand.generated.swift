// Generated from games.hades.command_contract. Do not edit.
import Foundation

enum HadesCommand: String {
    case status = "status"
    case connect = "connect"
    case disconnect = "disconnect"
    case launch = "launch"
    case catalog = "catalog"
    case diagnostics = "diagnostics"
    case listProfiles = "list_profiles"
    case saveProfile = "save_profile"
    case loadProfile = "load_profile"
    case deleteProfile = "delete_profile"
    case setFeature = "set_feature"
    case setBoonRarity = "set_boon_rarity"
    case disableAll = "disable_all"
    case lockVital = "lock_vital"
    case lockResource = "lock_resource"
    case lockRerolls = "lock_rerolls"
    case setValue = "set_value"
    case setResource = "set_resource"
    case gainResource = "gain_resource"
    case spawnReward = "spawn_reward"
    case generateFishing = "generate_fishing"
    case generateChaosGate = "generate_chaos_gate"
    case generateChamberObject = "generate_chamber_object"
    case applyWorldExit = "apply_world_exit"
    case cancelWorldExit = "cancel_world_exit"
    case applyWorldOccurrence = "apply_world_occurrence"
    case cancelWorldOccurrence = "cancel_world_occurrence"
    case addTrait = "add_trait"
    case updateTrait = "update_trait"
    case removeTrait = "remove_trait"
    case setTraitUses = "set_trait_uses"
    case expireTrait = "expire_trait"
    case refreshTrait = "refresh_trait"
    case addChaosPair = "add_chaos_pair"
    case saveEditorInventory = "save_editor_inventory"
    case saveEditorOpen = "save_editor_open"
    case saveEditorTarget = "save_editor_target"
    case saveEditorQuery = "save_editor_query"
    case saveEditorDetail = "save_editor_detail"
    case saveEditorStage = "save_editor_stage"
    case saveEditorUnstage = "save_editor_unstage"
    case saveEditorReview = "save_editor_review"
    case saveEditorCancel = "save_editor_cancel"
    case saveEditorApply = "save_editor_apply"
    case saveEditorClose = "save_editor_close"

    var timeout: TimeInterval {
        switch self {
        case .connect: return 190.0
        case .launch: return 35.0
        case .loadProfile: return 120.0
        case .setFeature: return 55.0
        case .disableAll: return 55.0
        case .lockVital: return 55.0
        case .lockResource: return 55.0
        case .lockRerolls: return 55.0
        case .setValue: return 55.0
        case .addTrait: return 60.0
        case .updateTrait: return 60.0
        case .removeTrait: return 60.0
        case .setTraitUses: return 60.0
        case .expireTrait: return 60.0
        case .refreshTrait: return 60.0
        case .addChaosPair: return 60.0
        default: return 30.0
        }
    }

    var supportsOfflineIntent: Bool {
        switch self {
        case .loadProfile, .setFeature, .setBoonRarity, .disableAll: return true
        default: return false
        }
    }

    private var baseRequiresTrustedTarget: Bool {
        switch self {
        case .launch, .catalog, .listProfiles, .saveProfile, .deleteProfile, .saveEditorInventory, .saveEditorOpen, .saveEditorTarget, .saveEditorQuery, .saveEditorDetail, .saveEditorStage, .saveEditorUnstage, .saveEditorReview, .saveEditorCancel, .saveEditorApply, .saveEditorClose: return false
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
