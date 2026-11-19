"""Swift module identities of the product.

Core, each game frontend and the App compile as separate Swift modules of one
package (`Tools/product_support.py` owns their order and dependencies). Games
and the App import TrainerCore, the App also imports each selected game, and
nothing imports the App or another game. Core API that games use is `package`.

This file has no imports so Swift test harnesses can share the names without
loading the module manifest tooling.
"""
SWIFT_PACKAGE_NAME = 'MacGamingTrainer'
SWIFT_CORE_MODULE = 'TrainerCore'
SWIFT_APP_MODULE = 'TrainerApp'
