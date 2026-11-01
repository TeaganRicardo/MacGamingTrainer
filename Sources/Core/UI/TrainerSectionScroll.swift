import AppKit
import SwiftUI

/// Own the native viewport motion, including its last frame and cancellation.
/// A SwiftUI transaction completion does not track ScrollViewProxy's AppKit
/// scroll, so it cannot retire a jump that may still be moving when a page hides.
@MainActor
final class TrainerSectionScroll: ObservableObject {
    private struct Target {
        weak var view: NSView?
    }
    private struct Pending {
        let request: TrainerSectionNavigation.Request
        let navigation: TrainerSectionNavigation
    }
    @MainActor
    private final class Jump {
        let request: TrainerSectionNavigation.Request
        weak var navigation: TrainerSectionNavigation?
        weak var target: NSView?
        weak var scroll: NSScrollView?
        let origin: NSPoint
        let animation: ProgressAnimation

        init(_ pending: Pending, target: NSView, scroll: NSScrollView, duration: TimeInterval) {
            request = pending.request
            navigation = pending.navigation
            self.target = target
            self.scroll = scroll
            origin = scroll.contentView.bounds.origin
            animation = ProgressAnimation(duration: duration, animationCurve: .easeInOut)
            animation.animationBlockingMode = .nonblocking
        }
    }
    private final class ProgressAnimation: NSAnimation {
        var update: ((CGFloat) -> Void)?
        override var currentProgress: NSAnimation.Progress {
            get { super.currentProgress }
            set {
                super.currentProgress = newValue
                update?(CGFloat(currentValue))
            }
        }
    }

    private var targets: [String: Target] = [:]
    private var pending: Pending?
    private var active: Jump?
    private var reduceMotion = false
    private var layoutCheckScheduled = false
    private var inputMonitor: Any?
    private weak var viewportProbe: NSView?
    private weak var monitoredScroll: NSScrollView?

    deinit {
        if let inputMonitor { NSEvent.removeMonitor(inputMonitor) }
    }

    func register(_ view: NSView, id: String) {
        targets[id] = Target(view: view)
        targetDidLayout(id)
    }

    func attachViewport(_ probe: NSView) {
        viewportProbe = probe
        updateInputMonitoring()
    }

    func detachViewport(_ probe: NSView) {
        guard viewportProbe === probe else { return }
        viewportProbe = nil
        let cancelled = pending
        pending = nil
        cancelActive()
        updateInputMonitoring()
        // Native dismantling can run within a SwiftUI update. The owner stops
        // immediately; retire only the matching published request afterwards.
        if let cancelled {
            DispatchQueue.main.async { cancelled.navigation.cancelRequest(cancelled.request) }
        }
    }

    func unregister(_ view: NSView, id: String) {
        guard targets[id]?.view === view else { return }
        targets.removeValue(forKey: id)
        if active?.target === view { cancelActive() }
    }

    func targetDidLayout(_ id: String) {
        guard pending?.request.destination == id, !layoutCheckScheduled else { return }
        layoutCheckScheduled = true
        // Native layout callbacks can run within a SwiftUI update. Consume the
        // latest request afterwards, once its newly revealed target has a frame.
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.layoutCheckScheduled = false
            self.startIfReady()
        }
    }

    func scroll(_ request: TrainerSectionNavigation.Request, navigation: TrainerSectionNavigation) {
        cancelActive()
        pending = Pending(request: request, navigation: navigation)
        updateInputMonitoring()
        startIfReady()
    }

    func setReduceMotion(_ enabled: Bool) {
        reduceMotion = enabled
        if enabled, let active { finish(active.request) }
    }

    func cancel() {
        let cancelled = pending
        pending = nil
        if let cancelled { cancelled.navigation.cancelRequest(cancelled.request) }
        cancelActive()
        updateInputMonitoring()
    }

    private func startIfReady() {
        guard let pending else { return }
        guard pending.navigation.isVisible, pending.navigation.request == pending.request else {
            self.pending = nil
            updateInputMonitoring()
            return
        }
        guard let target = targets[pending.request.destination]?.view,
              target.window != nil, target.bounds.height > 0,
              let scroll = target.enclosingScrollView, scroll.contentView.bounds.height > 0,
              let destination = destination(of: target, in: scroll) else { return }
        let request = pending.request
        guard pending.navigation.consume(request, finishScroll: { [weak self] in
            self?.finish(request)
        }) else { return }
        self.pending = nil
        let duration = TrainerMotion.duration(.selection, reduceMotion: reduceMotion)
        if duration == 0 || scroll.contentView.bounds.origin == destination {
            setOffset(destination, in: scroll)
            pending.navigation.didFinishScroll(request)
            updateInputMonitoring()
            return
        }
        let jump = Jump(pending, target: target, scroll: scroll, duration: duration)
        active = jump
        updateInputMonitoring()
        jump.animation.update = { [weak self] progress in self?.advance(request, progress: progress) }
        jump.animation.start()
    }

    private func destination(of target: NSView, in scroll: NSScrollView) -> NSPoint? {
        guard target.window != nil, target.enclosingScrollView === scroll,
              let document = scroll.documentView else { return nil }
        let frame = target.convert(target.bounds, to: document)
        var proposed = scroll.contentView.bounds
        proposed.origin.y = document.isFlipped ? frame.minY : frame.maxY - proposed.height
        return scroll.contentView.constrainBoundsRect(proposed).origin
    }

    private func advance(_ request: TrainerSectionNavigation.Request, progress: CGFloat) {
        guard let jump = active, jump.request == request else { return }
        guard let scroll = jump.scroll, let target = jump.target,
              let destination = destination(of: target, in: scroll) else {
            cancelActive()
            return
        }
        // Resolve against the current document geometry every frame, so a
        // resized or asynchronously updated section still ends at its top.
        let progress = min(1, max(0, progress))
        let point = NSPoint(x: jump.origin.x + (destination.x - jump.origin.x) * progress,
                            y: jump.origin.y + (destination.y - jump.origin.y) * progress)
        setOffset(point, in: scroll)
        if progress == 1 { retire(jump) }
    }

    private func finish(_ request: TrainerSectionNavigation.Request) {
        guard let jump = active, jump.request == request else { return }
        jump.animation.update = nil
        jump.animation.stop()
        if let scroll = jump.scroll, let target = jump.target,
           let destination = destination(of: target, in: scroll) {
            setOffset(destination, in: scroll)
        }
        retire(jump)
    }

    private func setOffset(_ point: NSPoint, in scroll: NSScrollView) {
        let clip = scroll.contentView
        let constrained = clip.constrainBoundsRect(NSRect(origin: point, size: clip.bounds.size)).origin
        clip.scroll(to: constrained)
        scroll.reflectScrolledClipView(clip)
    }

    private func cancelActive() {
        guard let jump = active else { return }
        jump.animation.update = nil
        jump.animation.stop()
        retire(jump)
    }

    private func retire(_ jump: Jump) {
        guard active === jump else { return }
        active = nil
        jump.animation.update = nil
        updateInputMonitoring()
        jump.navigation?.didFinishScroll(jump.request)
    }

    private func updateInputMonitoring() {
        let scroll = viewportProbe?.enclosingScrollView ?? active?.scroll ?? monitoredScroll
        guard pending != nil || active != nil, let scroll else {
            if let inputMonitor { NSEvent.removeMonitor(inputMonitor) }
            inputMonitor = nil
            monitoredScroll = nil
            return
        }
        guard inputMonitor == nil || monitoredScroll !== scroll else { return }
        if let inputMonitor { NSEvent.removeMonitor(inputMonitor) }
        monitoredScroll = scroll
        inputMonitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .leftMouseDown, .keyDown]) {
            [weak self, weak scroll] event in
            guard let scroll, event.window === scroll.window else { return event }
            let ownsInput: Bool
            if event.type == .keyDown {
                let responder = scroll.window?.firstResponder as? NSView
                let field = (responder as? NSTextView)?.delegate as? NSTextField
                ownsInput = responder?.isDescendant(of: scroll) == true || field?.enclosingScrollView === scroll
            } else {
                ownsInput = scroll.bounds.contains(scroll.convert(event.locationInWindow, from: nil))
            }
            if ownsInput { self?.cancel() }
            return event
        }
    }
}

/// Unlike a section target, this probe is present while a requested section is
/// still being revealed. User input in that viewport can cancel the wait too.
struct TrainerSectionViewportProbe: NSViewRepresentable {
    @Environment(\.trainerSectionScroll) private var owner

    final class Probe: NSView {
        weak var owner: TrainerSectionScroll?
        override func layout() { super.layout(); owner?.attachViewport(self) }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); owner?.attachViewport(self) }
    }

    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ view: Probe, context: Context) {
        if view.owner !== owner { view.owner?.detachViewport(view) }
        view.owner = owner
        owner?.attachViewport(view)
    }
    static func dismantleNSView(_ view: Probe, coordinator: ()) { view.owner?.detachViewport(view) }
}

private struct TrainerSectionScrollKey: EnvironmentKey {
    static let defaultValue: TrainerSectionScroll? = nil
}

extension EnvironmentValues {
    var trainerSectionScroll: TrainerSectionScroll? {
        get { self[TrainerSectionScrollKey.self] }
        set { self[TrainerSectionScrollKey.self] = newValue }
    }
}

private struct TrainerSectionTarget: NSViewRepresentable {
    @Environment(\.trainerSectionScroll) private var owner
    let id: String

    final class TargetView: NSView {
        weak var owner: TrainerSectionScroll?
        var id = ""
        override func setFrameSize(_ newSize: NSSize) { super.setFrameSize(newSize); owner?.targetDidLayout(id) }
        override func layout() { super.layout(); owner?.targetDidLayout(id) }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); owner?.targetDidLayout(id) }
    }

    func makeNSView(context: Context) -> TargetView { TargetView() }
    func updateNSView(_ view: TargetView, context: Context) {
        if view.owner !== owner || view.id != id { view.owner?.unregister(view, id: view.id) }
        view.owner = owner
        view.id = id
        owner?.register(view, id: id)
    }
    static func dismantleNSView(_ view: TargetView, coordinator: ()) {
        view.owner?.unregister(view, id: view.id)
    }
}

extension View {
    func trainerSectionTarget(_ id: String) -> some View {
        self.id(id).background(TrainerSectionTarget(id: id).allowsHitTesting(false).accessibilityHidden(true))
    }
}
