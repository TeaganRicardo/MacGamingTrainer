// Generated from Backend/games/hades2/command_contract.py. Do not edit.
import Foundation

enum Hades2Command: String {
    case scan = "scan"
    case status = "status"
    case connect = "connect"
    case disconnect = "disconnect"
    case launch = "launch"
    case disableAll = "disable_all"
    case runtimeReset = "runtime_reset"
    case resetDesired = "reset_desired"
    case setDesired = "set_desired"
    case setVital = "set_vital"
    case setCounter = "set_counter"
    case lockVital = "lock_vital"
    case setResource = "set_resource"
    case lockResource = "lock_resource"
    case setRerolls = "set_rerolls"
    case lockRerolls = "lock_rerolls"
    case setGatheringDesired = "set_gathering_desired"
    case setChaosGateDesired = "set_chaos_gate_desired"
    case generateGathering = "generate_gathering"
    case setStat = "set_stat"
    case setElement = "set_element"
    case lockElement = "lock_element"
    case setBoonRarityDesired = "set_boon_rarity_desired"
    case setNextRoomRewardDesired = "set_next_room_reward_desired"
    case spawnReward = "spawn_reward"
    case acquireChaosPair = "acquire_chaos_pair"
    case openSellTraits = "open_sell_traits"
    case setTraitLevel = "set_trait_level"
    case setTraitRarity = "set_trait_rarity"
    case setTraitRemainingUses = "set_trait_remaining_uses"
    case expireTrait = "expire_trait"
    case removeTrait = "remove_trait"
    case advanceTraitLifecycle = "advance_trait_lifecycle"
    case openSpecialChoice = "open_special_choice"
    case saveEditorOpen = "save_editor_open"
    case saveEditorQuery = "save_editor_query"
    case saveEditorStage = "save_editor_stage"
    case saveEditorReview = "save_editor_review"
    case saveEditorCancel = "save_editor_cancel"
    case saveEditorApply = "save_editor_apply"
    case listProfiles = "list_profiles"
    case saveProfile = "save_profile"
    case loadProfile = "load_profile"
    case deleteProfile = "delete_profile"
    case diagnostics = "diagnostics"
    case exportDiagnostics = "export_diagnostics"
    case prepare = "prepare"
    case restore = "restore"

    var timeout: TimeInterval {
        switch self {
        case .scan: return 15.0
        case .status: return 15.0
        case .connect: return 90.0
        case .disconnect: return 12.0
        case .launch: return 10.0
        case .saveEditorApply: return 30.0
        case .diagnostics: return 70.0
        case .exportDiagnostics: return 85.0
        case .prepare: return 560.0
        case .restore: return 240.0
        default: return 6.0
        }
    }
}
