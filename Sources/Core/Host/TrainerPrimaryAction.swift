@MainActor
enum TrainerPrimaryActionRouter {
    static func perform(
        refreshTarget: () -> Bool,
        connect: () -> Void,
        launch: () -> Void
    ) {
        if refreshTarget() {
            connect()
        } else {
            launch()
        }
    }
}
