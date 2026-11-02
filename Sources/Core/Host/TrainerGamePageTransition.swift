import AppKit
import QuartzCore
import SwiftUI

/// One per Trainer window. Captures only the currently displayed workbench,
/// never a game process, and animates the outgoing pixels on a Core Animation
/// layer after SwiftUI has laid out the destination's retained live controls.
///
/// The snapshot is presentation-only: the actual selection, AX tree, hotkeys,
/// game contexts and input ownership all change synchronously at the Host.
@MainActor
final class TrainerGamePageTransition {
    private weak var surface: TrainerGamePageTransitionView?
    private var generation = 0
    private var pendingDestination: String?

    func attach(_ view: TrainerGamePageTransitionView) {
        surface = view
    }

    func detach(_ view: TrainerGamePageTransitionView) {
        guard surface === view else { return }
        cancel()
        surface = nil
    }

    func prepare(destination: String, reduceMotion: Bool) {
        generation &+= 1
        pendingDestination = nil
        if reduceMotion {
            surface?.clear()
            return
        }
        guard let surface, let image = surface.captureVisibleWorkbench() else {
            surface?.clear()
            return
        }
        surface.install(image)
        pendingDestination = destination
    }

    /// Called from the Host's authoritative selection change. Give the new
    /// SwiftUI hierarchy its native layout first; then the compositor owns
    /// every intermediate opacity frame, even if subsequent work stalls main.
    func finish(destination: String) {
        guard pendingDestination == destination else { return }
        pendingDestination = nil
        let token = generation
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generation == token, let surface = self.surface else { return }
            surface.window?.contentView?.layoutSubtreeIfNeeded()
            guard self.generation == token else { return }
            let duration = TrainerMotion.duration(.selection, reduceMotion: false)
            surface.fadeSnapshot(duration: duration)
            DispatchQueue.main.asyncAfter(deadline: .now() + duration + 0.04) { [weak self, weak surface] in
                guard let self, self.generation == token else { return }
                surface?.clear()
            }
        }
    }

    func cancel() {
        generation &+= 1
        pendingDestination = nil
        surface?.clear()
    }
}

/// A noninteractive NSView in the workbench overlay, not a second hosting tree.
/// The NSImageView rasterizes once; its backing layer's opacity animates in the
/// window compositor without repeatedly laying out SwiftUI's full game pages.
@MainActor
final class TrainerGamePageTransitionView: NSView {
    private let imageView = NSImageView(frame: .zero)
    private static let fadeKey = "trainer.game.page.crossfade"

    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        imageView.wantsLayer = true
        imageView.imageScaling = .scaleAxesIndependently
        imageView.layer?.opacity = 0
        addSubview(imageView)
    }

    required init?(coder: NSCoder) {
        fatalError("TrainerGamePageTransitionView is created by SwiftUI")
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func layout() {
        super.layout()
        if imageView.frame.width > 0,
           (abs(imageView.frame.width - bounds.width) > 1 ||
            abs(imageView.frame.height - bounds.height) > 1) {
            // Never stretch an outdated page snapshot when the user resizes.
            clear()
        }
        imageView.frame = bounds
    }

    func captureVisibleWorkbench() -> NSImage? {
        guard let window, let root = window.contentView else { return nil }
        let rect = convert(bounds, to: root).integral
        guard rect.width >= 2, rect.height >= 2,
              root.bounds.insetBy(dx: -1, dy: -1).contains(rect),
              let bitmap = root.bitmapImageRepForCachingDisplay(in: rect) else { return nil }
        root.cacheDisplay(in: rect, to: bitmap)
        guard let image = bitmap.cgImage else { return nil }
        return NSImage(cgImage: image, size: rect.size)
    }

    func install(_ image: NSImage) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        imageView.layer?.removeAnimation(forKey: Self.fadeKey)
        imageView.image = image
        imageView.layer?.opacity = 1
        CATransaction.commit()
        // Submit the outgoing image before the new retained page invalidates
        // its SwiftUI subtree. Subsequent fades can run in the compositor.
        CATransaction.flush()
    }

    func fadeSnapshot(duration: TimeInterval) {
        guard imageView.image != nil, let layer = imageView.layer else { return }
        let fade = CABasicAnimation(keyPath: "opacity")
        fade.fromValue = layer.presentation()?.opacity ?? 1
        fade.toValue = 0
        fade.duration = duration
        fade.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.opacity = 0
        layer.add(fade, forKey: Self.fadeKey)
        CATransaction.commit()
        CATransaction.flush()
    }

    func clear() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        imageView.layer?.removeAnimation(forKey: Self.fadeKey)
        imageView.layer?.opacity = 0
        imageView.image = nil
        CATransaction.commit()
    }
}

struct TrainerGamePageTransitionSurface: NSViewRepresentable {
    let transition: TrainerGamePageTransition

    func makeNSView(context: Context) -> TrainerGamePageTransitionView {
        let view = TrainerGamePageTransitionView(frame: .zero)
        transition.attach(view)
        return view
    }

    func updateNSView(_ view: TrainerGamePageTransitionView, context: Context) {
        transition.attach(view)
    }

    static func dismantleNSView(_ view: TrainerGamePageTransitionView, coordinator: ()) {
        // Parent state may survive a SwiftUI host rebuild. Do not retain a
        // detached compositor layer or let its old completion clear a new one.
        view.clear()
    }
}
