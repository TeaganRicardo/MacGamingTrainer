import Foundation

/// Hades-owned presentation vocabulary. Native game terminology must continue to
/// resolve through the terminology registry; this type only owns trainer UI
/// product labels and composition keys.
enum Hades2PresentationText {
    enum Product {
        static let zhCN: [String: String] = [
            "moduleTitle": "Hades II 修改器",
            "disableAll": "全部关闭",
            "refreshStatus": "刷新状态",
            "shortcutSettings": "快捷键设置",
            "viewLog": "查看日志"
        ]

        static let en: [String: String] = [
            "moduleTitle": "Hades II Modifier",
            "disableAll": "Disable All",
            "refreshStatus": "Refresh Status",
            "shortcutSettings": "Shortcut Settings",
            "viewLog": "View Log"
        ]
    }

    static func product(_ key: String, language: TrainerLanguage) -> String {
        switch language {
        case .zhCN:
            return Product.zhCN[key] ?? key
        case .english:
            return Product.en[key] ?? key
        }
    }
}
