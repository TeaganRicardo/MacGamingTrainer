"""Native sheet layout, focus and real module shortcut-presentation journeys."""

SHEET_JOURNEY = r'''
@MainActor
func sheetJourneyPump(_ duration: TimeInterval = 0.06) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) { NSApp.sendEvent(event) }
        NSApp.updateWindows()
    }
}

@MainActor
func sheetJourneyWait(_ host: NSView, _ expectation: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    repeat {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        sheetJourneyPump(0.02)
    } while Date() < deadline
    fatalError("native sheet timed out: " + expectation)
}

@MainActor
func sheetJourneyActivate(_ window: NSWindow) {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    sheetJourneyPump(0.2)
}

@MainActor
func exerciseSheetLayout(_ window: NSWindow, localization: TrainerLocalizationStore, draft: NSTextField? = nil) {
    let oldLanguage = localization.language
    let oldSize = window.contentView!.bounds.size
    let originalDraft = draft?.stringValue
    let originalField = draft
    if let draft { managementCheck(window.makeFirstResponder(draft), "sheet draft refused native focus") }
    let responder = window.firstResponder
    var translatedDoneLabels: [String] = []
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        let hostKeys = ["host.done", "host.shortcutSettings", "host.refresh"]
        managementCheck(hostKeys.allSatisfy { localization.localized($0) != $0 },
                        "sheet fixture did not load the shipped Host translations")
        let doneLabel = localization.localized("host.done")
        translatedDoneLabels.append(doneLabel)
        for width: CGFloat in [360, oldSize.width] {
            window.setContentSize(NSSize(width: width, height: oldSize.height))
            sheetJourneyPump()
            let host = window.contentView!
            host.layoutSubtreeIfNeeded()
            managementCheck(!nativeAccessibilityControls(host).contains { ($0.text ?? "").hasPrefix("host.") },
                            "native sheet exposed an untranslated Host key")
            managementCheck(namedNativeControl(host, role: "AXButton", name: doneLabel) != nil,
                            "native sheet did not update its visible Done label after language selection")
            let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
            var seen = Set<ObjectIdentifier>()
            func controls(_ object: Any, scrolling: Bool = false) -> [(NativeAccessibilityControl, Bool)] {
                guard let object = object as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return [] }
                let node = NativeAccessibilityControl(object: object)
                let childrenScroll = scrolling || node.role == "AXScrollArea"
                let own = ["AXButton", "AXTextField", "AXPopUpButton"].contains(node.role ?? "") && node.frame.width > 0
                    ? [(node, scrolling)] : []
                return own + node.children.flatMap { controls($0, scrolling: childrenScroll) }
            }
            let interactive = controls(host)
            // Scroll rows can extend vertically beyond the viewport. Their
            // controls still must fit its width, while header/footer controls
            // must remain fully inside the sheet.
            managementCheck(!interactive.isEmpty && interactive.allSatisfy { control, scrolling in
                let frame = control.frame
                return frame.minX >= bounds.minX && frame.maxX <= bounds.maxX
                    && (scrolling || bounds.contains(frame))
            },
                            "sheet controls overflowed a narrow bilingual native host")
            if let draft {
                managementCheck(draft === originalField && draft.stringValue == originalDraft && window.firstResponder === responder,
                                "sheet reflow or language change replaced its focused draft")
            }
        }
    }
    managementCheck(Set(translatedDoneLabels).count == 2, "sheet languages did not resolve to distinct visible labels")
    localization.language = oldLanguage
    window.setContentSize(oldSize)
    sheetJourneyPump()
}

@MainActor
func exerciseModuleShortcutSheet<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore,
    show: () -> Void, isPresented: () -> Bool, chord: () -> String,
    commands: () -> [[String: Any]]
) {
    let visibility = TrainerGamePageVisibility()
    let host = NSHostingView(rootView: ManagementPageFixture(content: content, visibility: visibility)
        .environmentObject(localization))
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 800),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = host
    sheetJourneyActivate(window)
    print("native_sheet_reduce_motion=\(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion)")
    let before = commands().count
    let original = chord()
    func sheet() -> NSWindow { window.attachedSheet! }
    func captureButton() -> NativeAccessibilityControl? {
        guard let root = window.attachedSheet?.contentView else { return nil }
        return nativeAccessibilityControls(root).first { $0.identifier == "trainer.shortcut.capture.invincibility" }
    }
    func key(_ code: UInt16, flags: NSEvent.ModifierFlags = [], characters: String = "") {
        let target = window.attachedSheet ?? window
        let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: flags,
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: target.windowNumber,
            context: nil, characters: characters, charactersIgnoringModifiers: characters,
            isARepeat: false, keyCode: code)!
        NSApp.postEvent(event, atStart: false)
        sheetJourneyPump()
    }
    show()
    sheetJourneyWait(host, "real module shortcut sheet") { window.attachedSheet != nil && captureButton() != nil }
    exerciseSheetLayout(sheet(), localization: localization)
    managementCheck(captureButton()!.press(), "shortcut capture refused native Press")
    sheetJourneyWait(host, "native shortcut monitor installed") { GlobalHotkeys.isShortcutCaptureActive }
    key(53, characters: "\u{1b}")
    sheetJourneyWait(host, "Escape cancels active shortcut capture") {
        !GlobalHotkeys.isShortcutCaptureActive
    }
    managementCheck(isPresented() && window.attachedSheet != nil && chord() == original,
                    "Escape assigned a shortcut or dismissed an active capture's sheet")

    let oldCaptureButton = captureButton()!
    managementCheck(oldCaptureButton.press(), "second capture refused native Press")
    sheetJourneyWait(host, "capture before page selection") { GlobalHotkeys.isShortcutCaptureActive }
    visibility.setVisible(false)
    sheetJourneyWait(host, "hidden game cancels native capture and sheet") {
        !isPresented() && window.attachedSheet == nil && !GlobalHotkeys.isShortcutCaptureActive
    }
    _ = oldCaptureButton.press()
    sheetJourneyPump()
    managementCheck(!GlobalHotkeys.isShortcutCaptureActive && chord() == original,
                    "a dismissed sheet's old capture button installed a monitor")
    visibility.setVisible(true)
    sheetJourneyPump()
    show()
    sheetJourneyWait(host, "reopened module shortcut sheet") { captureButton() != nil }
    managementCheck(captureButton()!.press(), "reopened capture refused native Press")
    sheetJourneyWait(host, "reopened shortcut monitor") { GlobalHotkeys.isShortcutCaptureActive }
    key(99, flags: [.control, .option, .command], characters: String(UnicodeScalar(NSF3FunctionKey)!))
    sheetJourneyWait(host, "module persists one captured native chord") {
        !GlobalHotkeys.isShortcutCaptureActive && chord() != original
    }
    managementPress(localization.localized("host.done"), in: sheet().contentView!)
    sheetJourneyWait(host, "native shortcut Done closes") { !isPresented() && window.attachedSheet == nil }
    for _ in 0..<3 {
        show()
        sheetJourneyWait(host, "rapid native sheet reopen") { window.attachedSheet != nil }
        key(53, characters: "\u{1b}")
        sheetJourneyWait(host, "idle Escape dismisses native sheet") { !isPresented() && window.attachedSheet == nil }
    }
    managementCheck(commands().count == before && !GlobalHotkeys.isShortcutCaptureActive,
                    "shortcut presentation generated backend traffic or retained a monitor")
    window.contentView = nil
    window.close()
    sheetJourneyPump()
    print("module_shortcut_sheet_continuity_ok")
}
'''
