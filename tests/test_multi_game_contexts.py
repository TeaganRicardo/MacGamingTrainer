"""Foreground activation, navigation and native retained tools across two modules."""
from multi_game_context_harness import ROOT, run_context_journey
from real_module_navigation_harness import run_real_module_navigation

run_context_journey()
run_real_module_navigation(ROOT)
