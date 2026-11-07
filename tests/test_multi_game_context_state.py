"""Two real Host contexts and workers retain request/document ownership without activation."""
from multi_game_context_harness import run_context_journey

run_context_journey(state_only=True)
