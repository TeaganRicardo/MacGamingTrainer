import Foundation
import SwiftUI
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var application: TrainerApplicationCoordinator?
    private var terminationInFlight = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let application else { return .terminateNow }
        guard !terminationInFlight else { return .terminateLater }
        terminationInFlight = true
        application.prepareForTermination { [weak self] in
            DispatchQueue.main.async {
                self?.terminationInFlight = false
                NSApp.reply(toApplicationShouldTerminate: true)
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
    let application: TrainerApplicationCoordinator
    let title: String

    final class HookView: NSView {
        weak var closeDelegate: AppDelegate?
        var title = ""
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            configureWindow()
        }

        func configureWindow() {
            window?.delegate = closeDelegate
            window?.title = title
            window?.titlebarAppearsTransparent = true
            window?.backgroundColor = .clear
        }
    }

    func makeNSView(context: Context) -> HookView {
        delegate.application = application
        let view = HookView()
        view.closeDelegate = delegate
        view.title = title
        return view
    }

    func updateNSView(_ view: HookView, context: Context) {
        delegate.application = application
        view.closeDelegate = delegate
        view.title = title
        view.configureWindow()
    }
}

@main struct TrainerApplication: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var application: TrainerApplicationCoordinator
    @StateObject private var localization = TrainerLocalizationStore()

    init() {
        _application = StateObject(wrappedValue: TrainerApplicationCoordinator(
            contexts: TrainerGameCatalog.makeContexts()
        ))
    }

    var body: some Scene {
        Window("Mac Gaming Trainer", id: "main") {
            TrainerGamePages(application: application)
                .trainerTheme(.standard)
                .tint(TrainerTheme.standard.accent)
                .preferredColorScheme(.dark)
                .environmentObject(localization)
                .background(WindowCloseBridge(
                    delegate: delegate, application: application,
                    title: "\(application.context(id: application.selectedGameID)?.descriptor.displayName ?? "") · Mac Gaming Trainer"
                ).frame(width: 0, height: 0))
                .onAppear { delegate.application = application }
        }
        .defaultSize(width: 1160, height: 860)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) { }
            TrainerLanguageCommands(localization: localization)
            TrainerGameCatalogCommands(application: application, localization: localization)
        }
    }
}
