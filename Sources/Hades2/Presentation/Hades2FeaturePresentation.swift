import SwiftUI

extension Hades2TrainerModel {
    /// Hades II observations for one feature intent, in the shared Core phase model.
    func featurePresentation(_ key: Hades2FeatureKey, enabled: Bool) -> TrainerFeaturePresentation {
        TrainerFeaturePresentation(
            enabled: enabled,
            supported: supportsFeature(key),
            connected: connected,
            active: activeFeatures[key.rawValue] ?? false,
            dormant: dormantFeatures[key.rawValue] ?? false,
            activationPending: isFeatureActivationPending(key),
            canActivate: canSetFeature,
            canEditDesired: canEditDesired
        )
    }
}
