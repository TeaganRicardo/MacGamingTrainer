"""Real-module numeric disclosure and conditional capability journeys."""

DISCLOSURE_SOURCE_REFRESH = r'''
@MainActor
func exerciseDisclosureSourceRefresh() {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.finishLaunching()
    app.activate(ignoringOtherApps: true)
    func fields(_ view: NSView) -> [NSTextField] {
        (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
    }
    func pump(_ duration: TimeInterval) {
        let deadline = Date().addingTimeInterval(duration)
        while Date() < deadline {
            if let event = app.nextEvent(matching: .any,
                until: min(deadline, Date().addingTimeInterval(0.01)), inMode: .default, dequeue: true) {
                app.sendEvent(event)
            }
            app.updateWindows()
        }
    }
    enum ResumedCompletion: CaseIterable { case retained, editedAgain, replacedObservation }
    for reopen in [false, true] {
        for action in ResumedCompletion.allCases {
            var source = "1"
            var completions: [TrainerTextField.Completion] = []
            var completionOwners: [String] = []
            var editing: [Bool] = []
            let binding = Binding<String>(get: { source }, set: { source = $0 })
            func root(_ title: String, expanded: Bool) -> AnyView {
                AnyView(TrainerTextField(title: title, text: binding,
                    onEditingChanged: { editing.append($0) },
                    onCommit: { completions.append($0); completionOwners.append(title); return $0.text })
                    .id("retained-field")
                    .environment(\.trainerDisclosureExpanded, expanded)
                    .disabled(!expanded)
                    .frame(width: 240, height: 24)
                    .frame(width: 280, height: 70))
            }
            let host = NSHostingView(rootView: root("initial", expanded: true))
            let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 280, height: 70),
                                  styleMask: [.titled], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            app.activate(ignoringOtherApps: true)
            let deadline = Date().addingTimeInterval(2)
            while !(app.isActive && window.isKeyWindow && !fields(host).isEmpty) && Date() < deadline {
                host.layoutSubtreeIfNeeded(); pump(0.01)
            }
            precondition(app.isActive && window.isKeyWindow)
            let field = fields(host).first!
            precondition(window.makeFirstResponder(field))
            pump(0.04)
            precondition(window.makeFirstResponder(field))
            let editor = field.currentEditor() as! NSTextView
            let owner = field.delegate as! TrainerTextField.Coordinator
            let beforeCompletions = completions.count
            let beforeBegins = editing.filter { $0 }.count
            let beforeEnds = editing.filter { !$0 }.count
            editor.selectAll(nil)
            editor.setMarkedText("2.75", selectedRange: NSRange(location: 4, length: 0),
                                 replacementRange: editor.selectedRange())
            precondition(editor.hasMarkedText() && source == "1")
            precondition(owner.suspendForDisclosure(field))
            precondition(owner.edit == nil && field.currentEditor() == nil
                         && editing.filter { $0 }.count == beforeBegins,
                         "native resignation reentered an edit that disclosure had retired")
            precondition(source == "1", "fixture drained the queued publication before its follow-up update")
            let refreshedTitle = reopen ? "reopened observation" : "collapsed observation"
            host.rootView = root(refreshedTitle, expanded: reopen)
            host.layoutSubtreeIfNeeded()
            precondition(fields(host).first === field && field.placeholderString == refreshedTitle,
                         "fixture did not perform a second update on the same native field")
            precondition(source == "1", "fixture drained publication during its forced follow-up update")
            precondition(field.stringValue == "2.75" && completions.count == beforeCompletions,
                         "a follow-up SwiftUI update replaced a suspended draft before its binding publication; reopened=\(reopen) field=\(field.stringValue)")

            if action == .replacedObservation {
                let published = Date().addingTimeInterval(2)
                while source != "2.75" && Date() < published { pump(0.01) }
                precondition(source == "2.75", "suspended draft publication did not finish")
                source = "4"
                host.rootView = root("replacement observation", expanded: true)
                host.layoutSubtreeIfNeeded()
                precondition(fields(host).first === field && field.stringValue == "4",
                             "unfocused source observation did not replace the suspended draft")
            }
            let resumedText = action == .replacedObservation ? "4" : "2.75"
            // A real refocus flushes the old end before capturing the next edit.
            // Explicit completion must submit the held draft even without another
            // keystroke, while an accepted observation and a later unchanged
            // completion must not inherit its uncommitted intent.
            host.rootView = root("explicit refocus", expanded: true)
            host.layoutSubtreeIfNeeded()
            precondition(window.makeFirstResponder(field))
            let resumed = field.currentEditor() as! NSTextView
            precondition(source == resumedText && resumed.string == resumedText
                         && editing.filter { !$0 }.count == beforeEnds + 1
                         && editing.filter { $0 }.count == beforeBegins + 1,
                         "refocus lost its held draft or reordered its previous edit owner")
            if action == .editedAgain {
                resumed.selectAll(nil)
                resumed.insertText("3.5", replacementRange: resumed.selectedRange())
            }
            let submitted = action == .editedAgain ? "3.5" : resumedText
            let changed = action != .replacedObservation
            resumed.doCommand(by: #selector(NSResponder.insertNewline(_:)))
            precondition(completions.count == beforeCompletions + 1
                         && completions.last?.text == submitted && completions.last?.changed == changed
                         && completionOwners.last == "explicit refocus",
                         "explicit Return lost the resumed draft or its current callback; action=\(action)")
            precondition(window.makeFirstResponder(field))
            let unchanged = field.currentEditor() as! NSTextView
            unchanged.doCommand(by: #selector(NSResponder.insertNewline(_:)))
            precondition(completions.count == beforeCompletions + 2
                         && completions.last?.text == submitted && completions.last?.changed == false
                         && completions.dropFirst(beforeCompletions).filter(\.changed).count == (changed ? 1 : 0),
                         "a later unchanged Return replayed the suspended draft's explicit completion")
            host.rootView = AnyView(EmptyView())
            host.layoutSubtreeIfNeeded()
            window.close()
        }
    }
    print("disclosure_source_refresh_ok")
}
'''

DISCLOSURE_EDIT_LIFETIME = r'''
@MainActor
private func disclosureLifetimePump(_ seconds: TimeInterval) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)), inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
func exerciseDisclosureEditLifetime() {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    NSApp.activate(ignoringOtherApps: true)
    let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 280, height: 70),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    var draft = "1"
    var events: [String] = []
    var commits = 0
    let binding = Binding<String>(get: { draft }, set: {
        draft = $0
    })
    func makeField(_ name: String) -> (TrainerTextField.Field, TrainerTextField.Coordinator) {
        let owner = TrainerTextField(title: name, text: binding,
            onEditingChanged: {
                events.append(name + ($0 ? ":true" : ":false"))
            },
            onCommit: { completion in
                commits += 1
                return completion.text
            })
        let coordinator = owner.makeCoordinator()
        let field = TrainerTextField.Field(frame: NSRect(x: 10, y: 20, width: 240, height: 24))
        field.stringValue = draft
        field.isEditable = true
        field.delegate = coordinator
        field.onFocus = { [weak coordinator] in coordinator?.begin() }
        return (field, coordinator)
    }
    let (retained, retainedOwner) = makeField("retained")
    window.contentView = retained
    window.makeKeyAndOrderFront(nil)
    let ready = Date().addingTimeInterval(2)
    while !(NSApp.isActive && window.isKeyWindow) && Date() < ready { disclosureLifetimePump(0.01) }
    precondition(NSApp.isActive && window.isKeyWindow && window.makeFirstResponder(retained),
                 "disclosure lifetime fixture could not focus an active native field")
    let retainedEditor = retained.currentEditor() as! NSTextView
    let retainedCommits = commits
    let retainedBegins = events.filter { $0 == "retained:true" }.count
    let retainedEnds = events.filter { $0 == "retained:false" }.count
    retainedEditor.selectAll(nil)
    retainedEditor.setMarkedText("2.75", selectedRange: NSRange(location: 4, length: 0),
                                replacementRange: retainedEditor.selectedRange())
    precondition(retainedOwner.suspendForDisclosure(retained))
    precondition(retainedOwner.edit == nil && retained.currentEditor() == nil
                 && events.filter { $0 == "retained:true" }.count == retainedBegins,
                 "native resignation revived the suspended edit")
    disclosureLifetimePump(0.02)
    RunLoop.current.run(until: Date().addingTimeInterval(0.02))
    precondition(draft == "2.75" && retained.stringValue == "2.75" && commits == retainedCommits
                 && events.filter { $0 == "retained:false" }.count == retainedEnds + 1,
                 "same-identity disclosure did not publish its retained native composition")
    TrainerTextField.dismantleNSView(retained, coordinator: retainedOwner)

    draft = "old-target"
    let (old, oldOwner) = makeField("old")
    window.contentView = old
    precondition(window.makeFirstResponder(old))
    let oldEditor = old.currentEditor() as! NSTextView
    let replacementCommits = commits
    oldEditor.selectAll(nil)
    oldEditor.setMarkedText("6.25", selectedRange: NSRange(location: 4, length: 0),
                           replacementRange: oldEditor.selectedRange())
    precondition(oldOwner.suspendForDisclosure(old))
    TrainerTextField.dismantleNSView(old, coordinator: oldOwner)
    // A module can reuse its local draft state while replacing the native
    // control by .id(target). No event turn occurs between retirement and reset.
    draft = "new-target"
    let (replacement, replacementOwner) = makeField("new")
    window.contentView = replacement
    precondition(window.makeFirstResponder(replacement))
    disclosureLifetimePump(0.02)
    RunLoop.current.run(until: Date().addingTimeInterval(0.02))
    precondition(draft == "new-target" && replacement.stringValue == "new-target" && commits == replacementCommits,
                 "retired disclosure published an old marked draft into a replacement target")
    precondition(Array(events.suffix(3)) == ["old:true", "old:false", "new:true"],
                 "retirement reordered editing ownership across the replacement native field")
    TrainerTextField.dismantleNSView(replacement, coordinator: replacementOwner)
    disclosureLifetimePump(0.02)
    window.close()
    print("disclosure_edit_lifetime_ok")
}
'''

DISCLOSURE_NATIVE_RETIREMENT = r'''
@MainActor
func exerciseDisclosureNativeRetirement() {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.finishLaunching()
    var source = "1"
    var completions: [TrainerTextField.Completion] = []
    var editing: [Bool] = []
    let binding = Binding<String>(get: { source }, set: { source = $0 })
    func root(expanded: Bool) -> AnyView {
        AnyView(TrainerDisclosure(isExpanded: expanded) {
            TrainerTextField(title: expanded ? "visible" : "retired", text: binding,
                onEditingChanged: { editing.append($0) },
                onCommit: { completions.append($0); return $0.text },
                style: .plain)
                .frame(width: 240, height: 24)
        }.frame(width: 280, height: 70))
    }
    func fields(_ view: NSView) -> [NSTextField] {
        (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
    }
    let host = NSHostingView(rootView: root(expanded: true))
    let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 280, height: 70),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    app.activate(ignoringOtherApps: true)
    let ready = Date().addingTimeInterval(2)
    while !(app.isActive && window.isKeyWindow && !fields(host).isEmpty) && Date() < ready {
        host.layoutSubtreeIfNeeded(); disclosureLifetimePump(0.01)
    }
    precondition(app.isActive && window.isKeyWindow)
    let field = fields(host).first!
    precondition(window.makeFirstResponder(field))
    disclosureLifetimePump(0.04)
    precondition(window.makeFirstResponder(field))
    let editor = field.currentEditor() as! NSTextView
    let owner = field.delegate as! TrainerTextField.Coordinator
    let beforeCompletions = completions.count
    let beforeBegins = editing.filter { $0 }.count
    let beforeEnds = editing.filter { !$0 }.count
    editor.selectAll(nil)
    editor.setMarkedText("2.75", selectedRange: NSRange(location: 4, length: 0),
                         replacementRange: editor.selectedRange())
    precondition(editor.hasMarkedText() && editor.string == "2.75"
                 && editor.delegate === field && field.currentEditor() === editor)
    // The native enabled state can arrive before NSViewRepresentable receives
    // the new disclosure environment. Exercise that ordering without a pump,
    // an explicit suspension call, or a synthetic completion notification.
    field.isEnabled = false
    host.rootView = root(expanded: false)
    host.layoutSubtreeIfNeeded()
    precondition(fields(host).first === field && field.placeholderString == "retired",
                 "fixture did not deliver disclosure retirement to the same native field")
    let retained = field.currentEditor() == nil && owner.edit == nil && field.stringValue == "2.75"
        && completions.count == beforeCompletions && editing.filter { $0 }.count == beforeBegins
    if !retained {
        let detail = "nativeText=" + (field.currentEditor()?.string ?? field.stringValue) + " source=" + source
            + " editor=" + (field.currentEditor()?.string ?? "<none>")
            + " completions=" + String(completions.count - beforeCompletions)
        fputs("disclosure_native_retirement_failure=" + detail + "\n", stderr)
    }
    precondition(retained,
                 "native disabling before the disclosure update lost or completed the marked draft")
    let published = Date().addingTimeInterval(2)
    while source != "2.75" && Date() < published { disclosureLifetimePump(0.01) }
    precondition(source == "2.75" && editing.filter { !$0 }.count == beforeEnds + 1,
                 "native retirement did not publish the held draft and retire its editing owner once")
    host.rootView = AnyView(EmptyView())
    host.layoutSubtreeIfNeeded()
    window.close()
    print("disclosure_native_retirement_ok")
}
'''

DISCLOSURE_NATIVE_RETIREMENT_BOUNDARIES = r'''
@MainActor
func exerciseDisclosureNativeRetirementBoundaries() {
    enum Boundary: CaseIterable {
        case ordinaryDisable, reenabled, reenabledEdited, replacedComposition, cancelledEdit, replacedTarget
    }
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.finishLaunching()
    func fields(_ view: NSView) -> [NSTextField] {
        (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
    }
    for boundary in Boundary.allCases {
        var source = "1"
        var completions: [TrainerTextField.Completion] = []
        var editing: [String] = []
        let binding = Binding<String>(get: { source }, set: { source = $0 })
        func root(expanded: Bool, enabled: Bool = true, title: String = "visible", target: String = "original") -> AnyView {
            AnyView(TrainerDisclosure(isExpanded: expanded) {
                TrainerTextField(title: title, text: binding,
                    onEditingChanged: { editing.append(target + ($0 ? ":true" : ":false")) },
                    onCommit: { completions.append($0); return $0.text }, style: .plain)
                    .id(target).disabled(!enabled).frame(width: 240, height: 24)
            }.frame(width: 280, height: 70))
        }
        let host = NSHostingView(rootView: root(expanded: true))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 280, height: 70),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        let ready = Date().addingTimeInterval(2)
        while !(app.isActive && window.isKeyWindow && !fields(host).isEmpty) && Date() < ready {
            host.layoutSubtreeIfNeeded(); disclosureLifetimePump(0.01)
        }
        precondition(app.isActive && window.isKeyWindow)
        let original = fields(host).first!
        precondition(window.makeFirstResponder(original))
        disclosureLifetimePump(0.04)
        precondition(window.makeFirstResponder(original))
        let editor = original.currentEditor() as! NSTextView
        let beforeCompletions = completions.count
        let beforeBegins = editing.filter { $0 == "original:true" }.count
        let beforeEnds = editing.filter { $0 == "original:false" }.count
        editor.selectAll(nil)
        editor.setMarkedText("2.75", selectedRange: NSRange(location: 4, length: 0),
                             replacementRange: editor.selectedRange())
        precondition(editor.hasMarkedText() && editor.string == "2.75"
                     && editor.delegate === original && original.currentEditor() === editor)
        var expected = "1"
        var current = original
        var target = "original"
        switch boundary {
        case .ordinaryDisable:
            original.isEnabled = false
            host.rootView = root(expanded: true, enabled: false, title: "busy")
            host.layoutSubtreeIfNeeded()
            precondition(fields(host).first === original && original.placeholderString == "busy"
                         && !original.isEnabled && original.currentEditor() == nil,
                         "fixture did not deliver the ordinary busy update to its original field")
            precondition(source == "1" && completions.count == beforeCompletions,
                         "ordinary disabling published or completed a disclosure-only snapshot")
        case .reenabled, .reenabledEdited:
            original.isEnabled = false
            original.isEnabled = true
            if boundary == .reenabledEdited {
                precondition(window.makeFirstResponder(original))
                let resumed = original.currentEditor() as! NSTextView
                resumed.selectAll(nil)
                resumed.insertText("3.5", replacementRange: resumed.selectedRange())
                expected = "3.5"
            }
        case .replacedComposition:
            editor.insertText("1", replacementRange: NSRange(location: 0, length: editor.string.utf16.count))
            precondition(!editor.hasMarkedText() && editor.string == "1",
                         "fixture did not replace its marked composition through native input")
        case .cancelledEdit:
            // Ending native composition is not cancellation. The following
            // real Escape cancels the whole edit through its existing owner;
            // OS input-method candidate cancellation is a separate acceptance.
            editor.unmarkText()
            precondition(!editor.hasMarkedText() && editor.string == "2.75",
                         "fixture did not end composition while retaining its uncommitted text")
            for type in [NSEvent.EventType.keyDown, .keyUp] {
                let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                    context: nil, characters: "\u{1b}", charactersIgnoringModifiers: "\u{1b}",
                    isARepeat: false, keyCode: 53)!
                app.sendEvent(event)
            }
            let cancelled = Date().addingTimeInterval(1)
            while original.currentEditor() != nil && Date() < cancelled { disclosureLifetimePump(0.01) }
            let editCancelled = original.currentEditor() == nil
                && (original.delegate as? TrainerTextField.Coordinator)?.edit == nil
                && original.stringValue == "1" && source == "1"
                && completions.count == beforeCompletions
                && editing.filter { $0 == "original:false" }.count == beforeEnds + 1
            if !editCancelled {
                let diagnostic: [String: Any] = [
                    "nativeText": original.currentEditor()?.string ?? original.stringValue,
                    "editor": original.currentEditor()?.string ?? "<none>", "marked": editor.hasMarkedText(),
                    "source": source, "active": app.isActive, "key": window.isKeyWindow,
                    "firstResponder": String(describing: window.firstResponder),
                    "completionDelta": completions.count - beforeCompletions, "editing": editing]
                let data = try! JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys])
                FileHandle.standardError.write(Data("disclosure_edit_cancel_failure=".utf8) + data + Data("\n".utf8))
            }
            precondition(editCancelled, "native Escape did not cancel the edit after composition ended")
        case .replacedTarget:
            original.isEnabled = false
            host.rootView = AnyView(EmptyView())
            host.layoutSubtreeIfNeeded()
            source = "replacement"
            target = "replacement"
            host.rootView = root(expanded: true, target: target)
            host.layoutSubtreeIfNeeded()
            current = fields(host).first!
            precondition(current !== original && window.makeFirstResponder(current))
            precondition(Array(editing.suffix(3)) == ["original:true", "original:false", "replacement:true"],
                         "replacement reordered the retired and new edit owners")
            let replacement = current.currentEditor() as! NSTextView
            replacement.selectAll(nil)
            replacement.insertText("4.5", replacementRange: replacement.selectedRange())
            expected = "4.5"
        }
        host.rootView = root(expanded: false, enabled: boundary != .ordinaryDisable, title: "retired", target: target)
        host.layoutSubtreeIfNeeded()
        precondition(fields(host).first === current && current.placeholderString == "retired")
        precondition(current.currentEditor() == nil && current.stringValue == expected
                     && completions.count == beforeCompletions,
                     "native retirement revived an obsolete draft or completed an edit; boundary=\(boundary)")
        disclosureLifetimePump(0.03)
        precondition(source == expected && completions.count == beforeCompletions
                     && editing.filter { $0 == "original:true" }.count == beforeBegins
                     && editing.filter { $0 == "original:false" }.count == beforeEnds + 1,
                     "native retirement published a stale target or repeated an editing callback; boundary=\(boundary)")
        host.rootView = AnyView(EmptyView())
        host.layoutSubtreeIfNeeded()
        window.close()
    }
    print("disclosure_native_retirement_boundaries_ok")
}
'''

DISCLOSURE_JOURNEY = DISCLOSURE_EDIT_LIFETIME + DISCLOSURE_SOURCE_REFRESH + DISCLOSURE_NATIVE_RETIREMENT + DISCLOSURE_NATIVE_RETIREMENT_BOUNDARIES + r'''
private func disclosureCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("module disclosure: " + message) }
}

private func disclosureFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(disclosureFields)
}

@MainActor
private func disclosurePump(_ duration: TimeInterval) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
private func disclosureWait(_ host: NSView, _ expectation: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    repeat {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        disclosurePump(0.02)
    } while Date() < deadline
    disclosureCheck(condition(), "timed out: " + expectation)
}

@MainActor
func exerciseModuleDisclosure<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore, gameID: String,
    expanded: Binding<Bool>, primaryLabel: (TrainerPresentationLanguage) -> String,
    expandedLabel: (TrainerPresentationLanguage) -> String,
    outsideLabel: (TrainerPresentationLanguage) -> String,
    conditionalRole: String, conditionalLabel: (TrainerPresentationLanguage) -> String,
    busy: () -> Bool, commands: () -> [[String: Any]], observeAvailability: (Int) throws -> Void
) rethrows {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    NSApp.activate(ignoringOtherApps: true)
    let reduced = TrainerMotion.transaction(.disclosure, reduceMotion: true)
    disclosureCheck(reduced.animation == nil && reduced.disablesAnimations,
                    "reduced disclosure inherited motion")
    disclosureCheck(TrainerMotion.transaction(.disclosure, reduceMotion: false).animation != nil,
                    "normal disclosure lost structural motion")
    print("disclosure_system_reduce_motion=\(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion)")
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for key in ["host.disclosure.expanded", "host.disclosure.collapsed"] {
            disclosureCheck(localization.localized(key) != key,
                            "missing shipped Host disclosure translation: " + key)
        }
        for width: CGFloat in [817, 1150] {
            expanded.wrappedValue = false
            try observeAvailability(3)
            let host = NSHostingView(rootView: TrainerShell { EmptyView() } content: {
                content.frame(minWidth: TrainerTheme.standard.contentMinWidth,
                              maxWidth: TrainerTheme.standard.pageMaxWidth, alignment: .topLeading)
            }.environmentObject(localization))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 740),
                styleMask: [.titled, .resizable], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            func field(_ title: String) -> NSTextField? {
                disclosureFields(host).first { $0.accessibilityLabel() == title }
            }
            func button() -> NativeAccessibilityControl? {
                nativeAccessibilityControls(host).first { $0.identifier == gameID + ".numericDisclosure" }
            }
            func conditional() -> NativeAccessibilityControl? {
                namedNativeControl(host, role: conditionalRole, name: conditionalLabel(language))
            }
            disclosureWait(host, "mounted real numeric fields and capability") {
                NSApp.isActive && window.isKeyWindow && !busy()
                    && button()?.enabled == true && field(primaryLabel(language)) != nil
                    && field(expandedLabel(language))?.isEnabled == false && conditional()?.enabled == true
            }
            let before = commands().count
            let primary = field(primaryLabel(language))!
            let detail = field(expandedLabel(language))!
            let primaryFrame = primary.convert(primary.bounds, to: nil)
            let headerButtonFrame = window.convertFromScreen(button()!.frame)
            disclosureCheck(headerButtonFrame.width > 0 && headerButtonFrame.height > 0,
                            "numeric disclosure header has no measurable native frame")
            func primaryGeometry(primaryFrame: NSRect, headerFrame: NSRect) -> [String: Any] {
                var geometry: [String: Any] = [
                    "primaryWindow": NSStringFromRect(primaryFrame),
                    "disclosureButtonWindow": NSStringFromRect(headerFrame),
                    "primaryFromDisclosureButtonY": primaryFrame.minY - headerFrame.minY,
                    "windowFrame": NSStringFromRect(window.frame),
                    "hostFrame": NSStringFromRect(host.frame), "hostBounds": NSStringFromRect(host.bounds)]
                if let scroll = primary.enclosingScrollView {
                    geometry["scrollFrame"] = NSStringFromRect(scroll.frame)
                    geometry["scrollBounds"] = NSStringFromRect(scroll.bounds)
                    geometry["clipBounds"] = NSStringFromRect(scroll.contentView.bounds)
                    if let document = scroll.documentView {
                        let frame = primary.convert(primary.bounds, to: document)
                        geometry["primaryDocument"] = NSStringFromRect(frame)
                        geometry["documentFrame"] = NSStringFromRect(document.frame)
                        geometry["documentBounds"] = NSStringFromRect(document.bounds)
                        geometry["documentFlipped"] = document.isFlipped
                        geometry["primaryFromDocumentTop"] = document.isFlipped
                            ? frame.minY - document.bounds.minY : document.bounds.maxY - frame.maxY
                    }
                }
                return geometry
            }
            let initialPrimaryGeometry = primaryGeometry(primaryFrame: primaryFrame, headerFrame: headerButtonFrame)
            disclosureCheck(!nativeAccessibilityControls(host).contains {
                $0.role == "AXTextField" && $0.label == expandedLabel(language)
            }, "collapsed numeric field remained exposed to accessibility")
            let focusSelector = NSSelectorFromString("setAccessibilityFocused:")
            let focusObject = button()!.object
            disclosureCheck(focusObject.responds(to: focusSelector), "disclosure has no native keyboard focus route")
            typealias FocusSetter = @convention(c) (AnyObject, Selector, Bool) -> Void
            unsafeBitCast(focusObject.method(for: focusSelector), to: FocusSetter.self)(focusObject, focusSelector, true)
            let focusedSelector = NSSelectorFromString("isAccessibilityFocused")
            disclosureCheck(focusObject.responds(to: focusedSelector), "disclosure has no native focus observation")
            typealias FocusGetter = @convention(c) (AnyObject, Selector) -> Bool
            let focused = unsafeBitCast(focusObject.method(for: focusedSelector), to: FocusGetter.self)
            disclosureWait(host, "actual keyboard focus on disclosure") {
                NSApp.isActive && window.isKeyWindow && focused(focusObject, focusedSelector)
            }
            for type in [NSEvent.EventType.keyDown, .keyUp] {
                let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                    context: nil, characters: " ", charactersIgnoringModifiers: " ", isARepeat: false, keyCode: 49)!
                NSApp.sendEvent(event)
                disclosurePump(0.02)
            }
            disclosureWait(host, "expanded native numeric field") { expanded.wrappedValue && detail.isEnabled }
            disclosureCheck(window.makeFirstResponder(detail), "expanded native field refused focus")
            guard let rejectedEditor = detail.currentEditor() as? NSTextView,
                  let nativeDetail = detail as? TrainerTextField.Field else { fatalError("missing numeric editor") }
            rejectedEditor.selectAll(nil)
            rejectedEditor.insertText("invalid", replacementRange: rejectedEditor.selectedRange())
            rejectedEditor.doCommand(by: #selector(NSResponder.insertNewline(_:)))
            disclosureWait(host, "real module exposes rejected input before disclosure") {
                nativeDetail.validationMessage != nil && commands().count == before
            }
            let rejection = nativeDetail.validationMessage
            disclosureCheck(window.makeFirstResponder(detail), "rejected field refused a correction draft")
            guard let editor = detail.currentEditor() as? NSTextView else { fatalError("missing correction editor") }
            editor.selectAll(nil)
            editor.setMarkedText("2.75", selectedRange: NSRange(location: 4, length: 0),
                                 replacementRange: editor.selectedRange())
            disclosureCheck(editor.hasMarkedText() && editor.string == "2.75"
                            && editor.delegate === detail && detail.currentEditor() === editor,
                            "fixture did not compose the intended text in the current numeric editor")
            disclosureCheck(button()!.press(), "numeric collapse refused AX action")
            disclosureWait(host, "immediate hidden input retirement") {
                !expanded.wrappedValue && !detail.isEnabled && detail.currentEditor() == nil
            }
            let retainedDraft = detail.stringValue == "2.75" && commands().count == before
            if !retainedDraft {
                let diagnostic: [String: Any] = [
                    "game": gameID, "language": language.rawValue, "width": width,
                    "field": detail.stringValue,
                    "editor": detail.currentEditor()?.string ?? "<none>",
                    "sameNativeField": field(expandedLabel(language)) === detail,
                    "enabled": detail.isEnabled, "expanded": expanded.wrappedValue, "busy": busy(),
                    "running": NSApp.isRunning, "active": NSApp.isActive, "key": window.isKeyWindow,
                    "validation": nativeDetail.validationMessage ?? "<none>",
                    "commandsBefore": before, "commandsAfter": commands().count,
                    "commandDelta": Array(commands().dropFirst(before))]
                let data = try! JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys])
                FileHandle.standardError.write(Data("disclosure_retirement_failure=".utf8) + data + Data("\n".utf8))
            }
            disclosureCheck(retainedDraft,
                            "layout retirement committed or discarded the native draft")
            disclosureCheck(nativeDetail.validationMessage == rejection,
                            "layout retirement treated an unvalidated correction as a successful edit")
            for _ in 0..<6 {
                disclosureCheck(button()!.press(), "rapid disclosure reversal refused input")
                disclosurePump(0.025)
            }
            disclosureCheck(button()!.press(), "reopening native disclosure refused input")
            disclosureWait(host, "retained editor after reversal") {
                expanded.wrappedValue && detail.isEnabled && detail.stringValue == "2.75"
            }
            disclosureCheck(field(expandedLabel(language)) === detail,
                            "disclosure rebuilt its native numeric editor")
            disclosureCheck(nativeDetail.validationMessage == rejection,
                            "reopening disclosure hid the existing correction cue")
            let currentPrimaryFrame = primary.convert(primary.bounds, to: nil)
            let currentHeaderButtonFrame = window.convertFromScreen(button()!.frame)
            disclosureCheck(currentHeaderButtonFrame.width > 0 && currentHeaderButtonFrame.height > 0,
                            "numeric disclosure header lost its native frame")
            // Rejected input can insert a game-owned error banner above this
            // section. Preserve the compact row's own geometry and header gap
            // while allowing that legitimate section/viewport translation.
            let compactRowsStable = field(primaryLabel(language)) === primary
                && abs(currentPrimaryFrame.minX - primaryFrame.minX) < 1
                && abs(currentPrimaryFrame.width - primaryFrame.width) < 1
                && abs(currentPrimaryFrame.height - primaryFrame.height) < 1
                && abs((currentPrimaryFrame.minY - currentHeaderButtonFrame.minY)
                       - (primaryFrame.minY - headerButtonFrame.minY)) < 1
            if !compactRowsStable {
                let diagnostic: [String: Any] = [
                    "game": gameID, "language": language.rawValue, "width": width,
                    "sameNativeField": field(primaryLabel(language)) === primary,
                    "expanded": expanded.wrappedValue, "active": NSApp.isActive, "key": window.isKeyWindow,
                    "initial": initialPrimaryGeometry,
                    "current": primaryGeometry(primaryFrame: currentPrimaryFrame, headerFrame: currentHeaderButtonFrame)]
                let data = try! JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys])
                FileHandle.standardError.write(Data("disclosure_geometry_failure=".utf8) + data + Data("\n".utf8))
            }
            disclosureCheck(compactRowsStable,
                "expanded rows moved or resized the accepted compact dashboard")

            // Keep a real editor below the grid visible through both directions
            // of reflow. AX activation does not simulate an incidental mouse blur.
            let outside = field(outsideLabel(language))!
            _ = outside.scrollToVisible(outside.bounds)
            disclosureCheck(window.makeFirstResponder(outside), "neighbor editor refused focus")
            let outsideEditor = outside.currentEditor() as! NSTextView
            outsideEditor.selectAll(nil)
            outsideEditor.insertText("1.3", replacementRange: outsideEditor.selectedRange())
            for expected in [false, true, false] {
                disclosureCheck(button()!.press(), "focused-neighbor disclosure refused AX action")
                disclosureWait(host, "focused editor remains visible through reflow") {
                    expanded.wrappedValue == expected && outside.currentEditor() === outsideEditor
                        && outside.visibleRect.contains(outside.bounds)
                }
            }
            disclosureCheck(commands().count == before, "reflow dispatched a runtime command")

            try observeAvailability(0)
            disclosureWait(host, "conditional capability retired") { !busy() && conditional() == nil }
            disclosureCheck(commands().count == before + 1, "conditional removal dispatched a mutation")
            try observeAvailability(1)
            disclosureWait(host, "conditional capability returned") { !busy() && conditional()?.enabled == true }
            disclosureCheck(commands().count == before + 2, "conditional return dispatched a mutation")
            disclosureCheck(field(expandedLabel(language)) === detail && detail.stringValue == "2.75",
                            "conditional reflow reset an unrelated numeric draft")
            window.contentView = nil
            window.close()
        }
    }
    exerciseDisclosureEditLifetime()
    exerciseDisclosureSourceRefresh()
    exerciseDisclosureNativeRetirement()
    exerciseDisclosureNativeRetirementBoundaries()
    print(gameID + "_disclosure_module_journey_ok")
}
'''
