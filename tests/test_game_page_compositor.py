"""Keep module-switch motion compositor-owned without forcing a page raster pass.

Native two-game navigation and focus fixtures exercise the real SwiftUI host.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pages = (ROOT / "Sources/Core/Host/TrainerGamePages.swift").read_text()
compositor = (ROOT / "Sources/Core/Host/TrainerGamePageTransition.swift").read_text()
sidebar = (ROOT / "Sources/Core/UI/TrainerSidebar.swift").read_text()

# The originating action starts a native transition before the synchronous
# authoritative selection. A later observer only resolves native ownership.
assert "transition.prepare(destination: context.id, reduceMotion: reduceMotion)" in pages
assert pages.index("transition.prepare(destination: context.id, reduceMotion: reduceMotion)") < pages.index("application.selectedGameID = context.id")
assert "transition.finish(destination: newValue)" in pages
assert "TrainerGamePageTransitionSurface(transition: transition)" in pages
assert ".allowsHitTesting(false)" in pages
assert ".accessibilityHidden(true)" in pages

# Core Animation owns the fade of existing window content. CPU screenshots
# would add a full synchronous SwiftUI render to every module switch.
assert "CATransition()" in compositor and "fade.type = .fade" in compositor
assert "CAMediaTimingFunction(name: .easeInEaseOut)" in compositor
assert "layer.add(fade, forKey: Self.animationKey)" in compositor
assert "layer?.removeAnimation(forKey: Self.animationKey)" in compositor
assert "pendingDestination" in compositor
assert "guard !reduceMotion" in compositor
assert "override func hitTest(" in compositor
for expensive in ("bitmapImageRepForCachingDisplay", "cacheDisplay(in:", "NSImageView", "DispatchQueue.main.asyncAfter"):
    assert expensive not in compositor, expensive
assert "NSHostingView(" not in compositor

# Keep all section/native motion; no full-action-stack height interpolation.
card = sidebar.split("struct TrainerSidebarCard", 1)[1].split("struct TrainerSidebar<", 1)[0]
assert card.count(".animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)") == 1
assert "Avoid interpolating the action stack's height" in card
print("game_page_compositor_contract_ok")
