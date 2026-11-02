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
    private weak var surface: TrainerGamePageTransitionAnchor?
    private weak var animatedRoot: NSView?
    private var pendingDestination: String?

    func attach(_ view: TrainerGamePageTransitionAnchor) {
        surface = view
    }

    func detach(_ view: TrainerGamePageTransitionAnchor) {
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
        // No deferred visible selection or queued completion. The native
        // transition expires naturally after the new layout is committed.
        guard pendingDestination == destination else { return }
        pendingDestination = nil
    }

    func cancel() {
        pendingDestination = nil
        animatedRoot?.layer?.removeAnimation(forKey: Self.animationKey)
        animatedRoot = nil
    }
}

/// The anchor only finds the containing AppKit compositor. It never draws a
/// second game page and cannot intercept pointer, keyboard or AX interaction.
@MainActor
final class TrainerGamePageTransitionAnchor: NSView {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

struct TrainerGamePageTransitionSurface: NSViewRepresentable {
    let transition: TrainerGamePageTransition

    func makeNSView(context: Context) -> TrainerGamePageTransitionAnchor {
        let view = TrainerGamePageTransitionAnchor(frame: .zero)
        transition.attach(view)
        return view
    }

    func updateNSView(_ view: TrainerGamePageTransitionAnchor, context: Context) {
        transition.attach(view)
    }

    static func dismantleNSView(_ view: TrainerGamePageTransitionAnchor, coordinator: ()) {
        // Any in-flight CATransition has the native layer's own lifetime.
        // The anchor neither captures pixels nor retains an alternate tree.
    }
}
