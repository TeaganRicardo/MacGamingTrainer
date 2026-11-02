import AppKit
import QuartzCore
import SwiftUI

/// One per Trainer window. Core Animation composites the already-rendered
/// outgoing and incoming Host contents when the authoritative game changes.
/// No CPU bitmap capture, duplicate NSHostingView, or per-frame SwiftUI layout.
@MainActor
final class TrainerGamePageTransition {
    // CALayer normalizes CATransition to the standard "transition" key.
    private static let animationKey = "transition"
    private weak var surface: NSView?
    private weak var animatedRoot: NSView?
    private var pendingDestination: String?

    func attach(_ view: NSView) {
        surface = view
    }

    func detach(_ view: NSView) {
        guard surface === view else { return }
        cancel()
        surface = nil
    }

    func prepare(destination: String, reduceMotion: Bool) {
        cancel()
        guard !reduceMotion, let root = surface?.window?.contentView else { return }
        // SwiftUI's NSHostingView already maintains the layer hierarchy.
        // Work only at its existing compositor boundary; do not rasterize the
        // retained Hades I and II workbenches or interpolate native controls.
        if root.layer == nil { root.wantsLayer = true }
        guard let layer = root.layer else { return }
        let fade = CATransition()
        fade.type = .fade
        fade.duration = TrainerMotion.duration(.selection, reduceMotion: false)
        fade.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        layer.add(fade, forKey: Self.animationKey)
        animatedRoot = root
        pendingDestination = destination
    }

    func finish(destination: String) {
        // The Host selection is authoritative. An unrelated programmatic
        // selection must not leave an earlier game's transition running.
        guard let pendingDestination else { return }
        if pendingDestination == destination {
            self.pendingDestination = nil
        } else {
            cancel()
        }
    }

    func cancel() {
        pendingDestination = nil
        animatedRoot?.layer?.removeAnimation(forKey: Self.animationKey)
        animatedRoot = nil
    }
}

