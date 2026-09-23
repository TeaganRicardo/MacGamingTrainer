import Foundation
import SwiftUI
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var model: (any TrainerHostModel)?
    private var terminationInFlight = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            for window in NSApp.windows where window.canBecomeMain {
                window.title = "\(ActiveGameModule.descriptor.displayName) · Mac Gaming Trainer"
                window.delegate = self
                window.titlebarAppearsTransparent = true
                window.backgroundColor = .clear
            }
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let model else { return .terminateNow }
        guard !terminationInFlight else { return .terminateLater }
        terminationInFlight = true
        model.prepareForTermination { [weak self] allow in
            DispatchQueue.main.async {
                self?.terminationInFlight = false
                NSApp.reply(toApplicationShouldTerminate: allow)
            }
        }
        return .terminateLater
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        NSApp.terminate(nil)
        return false
    }
}

private struct WindowCloseBridge: NSViewRepresentable {
    let delegate: AppDelegate
    let model: any TrainerHostModel

    final class HookView: NSView {
        weak var closeDelegate: AppDelegate?
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            window?.delegate = closeDelegate
        }
    }

    func makeNSView(context: Context) -> HookView {
        delegate.model = model
        let view = HookView()
        view.closeDelegate = delegate
        return view
    }

    func updateNSView(_ view: HookView, context: Context) {
        delegate.model = model
        view.closeDelegate = delegate
        view.window?.delegate = delegate
    }
}

@main struct TrainerApplication: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    private let backendSession: TrainerBackendSession
    @StateObject private var model: ActiveGameModule.Model

    init() {
        let backendSession = TrainerBackendSession()
        self.backendSession = backendSession
        _model = StateObject(wrappedValue: ActiveGameModule.makeModel(session: backendSession))
    }

    var body: some Scene {
        Window("Mac Gaming Trainer", id: "main") {
            TrainerHostView<ActiveGameModule>(model: model, session: backendSession)
                .trainerTheme(.standard)
                .tint(TrainerTheme.standard.accent)
                .preferredColorScheme(.dark)
                .background(WindowCloseBridge(delegate: delegate, model: model).frame(width: 0, height: 0))
                .onAppear { delegate.model = model }
        }
        .defaultSize(width: 1160, height: 860)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) { }
            ActiveGameModule.makeManagementCommands(model: model)
        }
    }
}
