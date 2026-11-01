"""Drive the real AppKit/SwiftUI popup through public accessibility and input APIs."""

NATIVE_PICKER = r'''
enum NativePickerOpening { case pointer, keyboard, accessibility }

@MainActor
private final class NativePickerSelectionState {
    var trackingMenu: NSMenu?
    var opened = false
    var destinationTitle: String?
    var previousHighlightTitle: String?
    var awaitingArrow = false
    var returnQueued = false
    var failure: String?
    var reportedFailure = false
    var accessibilityAction: [String: Any] = [:]
}

@MainActor
func nativePickerPump(_ duration: TimeInterval = 0.04) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) { NSApp.sendEvent(event) }
        NSApp.updateWindows()
    }
}

@MainActor
func nativePickerWait(_ message: String, onFailure: () -> Void = {}, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(3)
    repeat {
        if condition() { return }
        nativePickerPump(0.02)
    } while Date() < deadline
    onFailure()
    fatalError("native picker timed out: " + message)
}

@MainActor
func activateNativePickerWindow(_ window: NSWindow) {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    nativePickerWait("active key window before native input") { NSApp.isActive && window.isKeyWindow }
    window.contentView?.layoutSubtreeIfNeeded()
}

@MainActor
func nativePickerHasName(_ picker: NativeAccessibilityControl, _ name: String) -> Bool {
    if picker.label == name { return true }
    // A visible native label can name its popup through AXTitleUIElement
    // instead of duplicating that text in the popup's AXLabel.
    let selector = NSSelectorFromString("accessibilityTitleUIElement")
    guard picker.object.responds(to: selector),
          let title = picker.object.perform(selector)?.takeUnretainedValue() as? NSObject else { return false }
    return NativeAccessibilityControl(object: title).text == name
}

@MainActor
func selectNativePicker(_ picker: NativeAccessibilityControl, in window: NSWindow,
                        moving steps: Int, opening: NativePickerOpening) {
    precondition(picker.role == "AXPopUpButton" && picker.enabled && !picker.frame.isEmpty,
                 "selection must address an enabled real native popup")
    activateNativePickerWindow(window)
    let before = Set(NSApp.windows.filter(\.isVisible).map(ObjectIdentifier.init))
    let state = NativePickerSelectionState()
    let began = NotificationCenter.default.addObserver(forName: NSMenu.didBeginTrackingNotification,
        object: nil, queue: .main) { notification in
        MainActor.assumeIsolated { state.trackingMenu = notification.object as? NSMenu }
    }
    let ended = NotificationCenter.default.addObserver(forName: NSMenu.didEndTrackingNotification,
        object: nil, queue: .main) { notification in
        MainActor.assumeIsolated {
            if notification.object as? NSMenu === state.trackingMenu { state.trackingMenu = nil }
        }
    }
    @MainActor
    func visibleMenu() -> NSWindow? {
        NSApp.windows.first { $0.isVisible && !before.contains(ObjectIdentifier($0)) }
    }
    @MainActor
    func reportFailure(_ stage: String) {
        guard !state.reportedFailure else { return }
        state.reportedFailure = true
        // Only failed boundaries call this. Freeze menu state before reading
        // any diagnostic AX values; never add reads to the normal input path.
        let opened = state.opened, awaitingArrow = state.awaitingArrow, returnQueued = state.returnQueued
        let trackingMenu = state.trackingMenu
        let failure = state.failure, destination = state.destinationTitle, previousHighlight = state.previousHighlightTitle
        let accessibilityAction = state.accessibilityAction
        let currentHighlight = trackingMenu?.highlightedItem?.title
        let active = NSApp.isActive, key = window.isKeyWindow, running = NSApp.isRunning
        let extraWindows = NSApp.windows.filter { $0.isVisible && !before.contains(ObjectIdentifier($0)) }
        let titleSelector = NSSelectorFromString("accessibilityTitleUIElement")
        let title = picker.object.responds(to: titleSelector)
            ? picker.object.perform(titleSelector)?.takeUnretainedValue() as? NSObject : nil
        let context: [String: Any] = [
            "stage": stage, "opening": String(describing: opening),
            "pickerLabel": picker.label ?? "nil", "pickerTitle": title.flatMap { NativeAccessibilityControl(object: $0).text } ?? "nil",
            "pickerValue": picker.valueText ?? "nil", "pickerFrame": NSStringFromRect(picker.frame),
            "active": active, "key": key, "running": running,
            "opened": opened, "awaitingArrow": awaitingArrow, "returnQueued": returnQueued,
            "failure": failure ?? "nil", "destination": destination ?? "nil",
            "accessibilityAction": accessibilityAction,
            "previousHighlight": previousHighlight ?? "nil",
            "currentHighlight": currentHighlight ?? "nil",
            "trackingMenu": trackingMenu.map { String(describing: ObjectIdentifier($0)) } ?? "nil",
            "completionObservedAfterFailure": failure == nil && opened && returnQueued && trackingMenu == nil && extraWindows.isEmpty,
            "extraVisibleWindows": extraWindows.map {
                ["number": $0.windowNumber, "key": $0.isKeyWindow, "frame": NSStringFromRect($0.frame)] as [String: Any]
            }]
        let payload = (try? JSONSerialization.data(withJSONObject: context, options: [.sortedKeys]))
            ?? Data(String(describing: context).utf8)
        FileHandle.standardError.write(Data("NATIVE_PICKER_FAILURE ".utf8) + payload + Data("\n".utf8))
    }
    @MainActor
    func openAccessibilityMenu() -> Bool {
        let object = picker.object
        let names = NSSelectorFromString("accessibilityActionNames")
        let rawActions = object.responds(to: names)
            ? object.perform(names)?.takeUnretainedValue() as? [Any] ?? [] : []
        let advertised = rawActions.compactMap { item -> String? in
            (item as? String) ?? (item as? NSAccessibility.Action)?.rawValue
        }
        func allowed(_ action: Selector) -> Bool? {
            let selector = NSSelectorFromString("isAccessibilitySelectorAllowed:")
            guard object.responds(to: selector) else { return nil }
            typealias Getter = @convention(c) (AnyObject, Selector, Selector) -> Bool
            return unsafeBitCast(object.method(for: selector), to: Getter.self)(object, selector, action)
        }
        let legacy = NSSelectorFromString("accessibilityPerformAction:")
        let legacyResponds = object.responds(to: legacy), legacyAllowed = allowed(legacy)
        let actions = [("AXPress", "accessibilityPerformPress"), ("AXShowMenu", "accessibilityPerformShowMenu")]
            .map { name, method in
                let selector = NSSelectorFromString(method)
                return (name: name, method: method, selector: selector,
                        responds: object.responds(to: selector), allowed: allowed(selector))
            }
        state.accessibilityAction = [
            "advertised": advertised, "legacyResponds": legacyResponds,
            "legacyAllowed": legacyAllowed.map { String($0) } ?? "unavailable",
            "modern": actions.map {
                ["name": $0.name, "method": $0.method, "responds": $0.responds,
                 "allowed": $0.allowed.map { String($0) } ?? "unavailable"] as [String: Any]
            }]
        // Default modern implementations can respond without supporting an
        // action. Prefer the element's advertised action contract; never send
        // an unadvertised legacy action or a disallowed modern selector.
        let routes = actions.filter { advertised.contains($0.name) }
            + actions.filter { !advertised.contains($0.name) }
        for action in routes {
            if advertised.contains(action.name), legacyResponds, legacyAllowed != false {
                state.accessibilityAction["route"] = "accessibilityPerformAction:" + action.name
                state.accessibilityAction["return"] = "void; real menu completion remains required"
                typealias Action = @convention(c) (AnyObject, Selector, NSString) -> Void
                unsafeBitCast(object.method(for: legacy), to: Action.self)(object, legacy, action.name as NSString)
                return true
            }
            if action.responds, action.allowed == true {
                state.accessibilityAction["route"] = action.method
                state.accessibilityAction["return"] = "pending"
                typealias Action = @convention(c) (AnyObject, Selector) -> Bool
                let triggered = unsafeBitCast(object.method(for: action.selector), to: Action.self)(object, action.selector)
                state.accessibilityAction["return"] = triggered
                return triggered
            }
        }
        state.accessibilityAction["route"] = "no supported public menu action"
        return false
    }
    @MainActor
    func postKey(_ characters: String, code: UInt16) {
        for kind in [NSEvent.EventType.keyDown, .keyUp] {
            let event = NSEvent.keyEvent(with: kind, location: .zero, modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: (NSApp.keyWindow ?? window).windowNumber, context: nil,
                characters: characters, charactersIgnoringModifiers: characters,
                isARepeat: false, keyCode: code)!
            NSApp.postEvent(event, atStart: false)
        }
    }
    // SwiftUI can replace native NSMenuItem objects while a menu tracks.
    // These fixtures use unique visible choice titles: preserve the initially
    // checked selection's requested neighbor, then resolve it in each current
    // menu snapshot. Object replacement alone is not keyboard movement.
    let inputDeadline = Date().addingTimeInterval(3)
    let timer = Timer(timeInterval: 0.02, repeats: true) { timer in
        MainActor.assumeIsolated {
            if Date() >= inputDeadline {
                state.failure = "destination=\(state.destinationTitle ?? "nil"), highlight=\(state.trackingMenu?.highlightedItem?.title ?? "nil")"
                reportFailure("input deadline")
                state.trackingMenu?.cancelTrackingWithoutAnimation()
                timer.invalidate()
                return
            }
            guard !state.returnQueued, let menu = state.trackingMenu else { return }
            state.opened = true
            let choices = menu.items.filter { item in
                if #available(macOS 14.0, *), item.isSectionHeader { return false }
                return item.isEnabled && !item.isHidden && !item.isSeparatorItem && !item.hasSubmenu
            }
            let titles = choices.map(\.title)
            guard Set(titles).count == titles.count else {
                state.failure = "native popup choices have ambiguous visible titles"
                reportFailure("ambiguous choices")
                menu.cancelTrackingWithoutAnimation()
                timer.invalidate()
                return
            }
            if state.destinationTitle == nil {
                guard choices.filter({ $0.state == .on }).count == 1,
                      let selected = choices.firstIndex(where: { $0.state == .on }),
                      choices.indices.contains(selected + steps) else {
                    state.failure = "native popup has no unique checked selection or requested neighbor"
                    reportFailure("initial checked neighbor")
                    menu.cancelTrackingWithoutAnimation()
                    timer.invalidate()
                    return
                }
                state.destinationTitle = choices[selected + steps].title
                print("native_picker_input=\(opening) checked=\(choices[selected].title) destination=\(state.destinationTitle!)")
            }
            guard let destinationIndex = titles.firstIndex(of: state.destinationTitle!) else {
                state.failure = "native popup lost its original semantic destination: \(state.destinationTitle!)"
                reportFailure("missing destination")
                menu.cancelTrackingWithoutAnimation()
                timer.invalidate()
                return
            }
            let highlightedTitle = menu.highlightedItem?.title
            let highlightedIndex = highlightedTitle.flatMap { titles.firstIndex(of: $0) }
            guard highlightedTitle == nil || highlightedIndex != nil else {
                state.failure = "native popup highlight is not a unique current choice: \(highlightedTitle!)"
                reportFailure("invalid highlight")
                menu.cancelTrackingWithoutAnimation()
                timer.invalidate()
                return
            }
            if state.awaitingArrow {
                // A transient nil highlight during menu rebuilding also does
                // not acknowledge the queued Arrow. Wait for an actual choice.
                guard let highlightedTitle, highlightedTitle != state.previousHighlightTitle else { return }
                state.awaitingArrow = false
            }
            if highlightedIndex == destinationIndex {
                state.returnQueued = true
                postKey("\r", code: 36)
            } else {
                state.previousHighlightTitle = highlightedTitle
                state.awaitingArrow = true
                let down = (highlightedIndex ?? -1) < destinationIndex
                postKey(down ? "\u{F701}" : "\u{F700}", code: down ? 125 : 126)
            }
        }
    }
    RunLoop.main.add(timer, forMode: .common)
    RunLoop.main.add(timer, forMode: .eventTracking)
    defer {
        timer.invalidate()
        NotificationCenter.default.removeObserver(began)
        NotificationCenter.default.removeObserver(ended)
    }
    switch opening {
    case .pointer:
        let point = window.convertPoint(fromScreen: NSPoint(x: picker.frame.midX, y: picker.frame.midY))
        for kind in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
            let event = NSEvent.mouseEvent(with: kind, location: point, modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                context: nil, eventNumber: 1, clickCount: 1, pressure: kind == .leftMouseDown ? 1 : 0)!
            NSApp.postEvent(event, atStart: false)
        }
    case .keyboard:
        let focus = NSSelectorFromString("setAccessibilityFocused:")
        precondition(picker.object.responds(to: focus), "native popup lacks its public accessibility focus setter")
        typealias Setter = @convention(c) (AnyObject, Selector, Bool) -> Void
        unsafeBitCast(picker.object.method(for: focus), to: Setter.self)(picker.object, focus, true)
        nativePickerPump()
        postKey(" ", code: 49)
    case .accessibility:
        let dispatched = openAccessibilityMenu()
        if !dispatched {
            state.failure = "native popup has no triggered public accessibility menu action"
            reportFailure("accessibility menu opening")
        }
        precondition(dispatched, "native popup refused its supported accessibility menu action")
    }
    nativePickerWait("real menu opened, accepted Arrow/Return and dismissed",
                     onFailure: { reportFailure("menu completion wait deadline") }) {
        state.failure != nil || (state.opened && state.returnQueued && state.trackingMenu == nil && visibleMenu() == nil)
    }
    if state.failure != nil { reportFailure("menu selection rejected") }
    precondition(state.failure == nil, "native picker selection failed: " + (state.failure ?? ""))
    nativePickerPump()
}
'''
