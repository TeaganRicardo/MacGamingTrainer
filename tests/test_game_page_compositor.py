"""Composited game-page transitions remain independent of retained SwiftUI layout.

A lightweight source contract complements the native Hades I/Hades II navigation
journey, which verifies presentation layers, native focus and game ownership.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pages = (ROOT / "Sources/Core/Host/TrainerGamePages.swift").read_text()
compositor = (ROOT / "Sources/Core/Host/TrainerGamePageTransition.swift").read_text()
sidebar = (ROOT / "Sources/Core/UI/TrainerSidebar.swift").read_text()

# Capture the outgoing real workbench before switching the authoritative
# selection; native layer animation is committed only after the new layout.
assert "transition.prepare(destination: context.id, reduceMotion: reduceMotion)" in pages
assert pages.index("transition.prepare(destination: context.id, reduceMotion: reduceMotion)") < pages.index("application.selectedGameID = context.id")
assert "transition.finish(destination: newValue)" in pages
assert "TrainerGamePageTransitionSurface(transition: transition)" in pages
assert ".allowsHitTesting(false)" in pages
assert ".accessibilityHidden(true)" in pages

# Core Animation owns the visible page crossfade; SwiftUI does not animate all
# retained page layouts or use a delayed authoritative game selection.
assert "bitmapImageRepForCachingDisplay" in compositor
assert "cacheDisplay(in:" in compositor
assert "CABasicAnimation(keyPath: \"opacity\")" in compositor
assert "CATransaction.flush()" in compositor
assert "layoutSubtreeIfNeeded()" in compositor
assert "imageView.layer?.opacity" in compositor
assert "generation" in compositor and "pendingDestination" in compositor
assert "if reduceMotion" in compositor
assert "override func hitTest(" in compositor

# Animating the expanding sidebar action stack's height causes repeated SwiftUI
# layout work; preserve only the small icon's native selection motion.
card = sidebar.split("struct TrainerSidebarCard", 1)[1].split("struct TrainerSidebar<", 1)[0]
assert card.count(".animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)") == 1
assert ".animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)\n\n" not in card
print("game_page_compositor_contract_ok")
