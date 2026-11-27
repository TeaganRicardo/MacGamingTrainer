import ast
import inspect
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades import (
    operation_budgets as hades_budgets,
    simulation_time_warp as hades_time_warp,
)
from games.hades.command_contract import (
    command_budget_audit as hades_budget_audit,
    command_metadata as hades_command_metadata,
)
from games.hades2 import operation_budgets as budgets, preparation
from games.hades2.command_contract import (
    command_budget_audit as hades2_budget_audit,
    command_metadata,
)
from games.hades2.transport_client import Hades2LuaTransport


def _maximum_subprocess_calls(function):
    """Count bounded commands, including calls hidden in preparation helpers."""
    tree = ast.parse((ROOT / "Backend/games/hades2/preparation.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

    @lru_cache(None)
    def function_cost(name):
        return sequence_cost(functions[name].body)

    def expression_cost(node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "_command":
                return 1
            if node.func.id in functions:
                return function_cost(node.func.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "run" and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                return 1
        return sum(expression_cost(child) for child in ast.iter_child_nodes(node))

    def statement_cost(statement):
        if isinstance(statement, ast.If):
            return expression_cost(statement.test) + max(sequence_cost(statement.body), sequence_cost(statement.orelse))
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            return expression_cost(
                statement.iter if isinstance(statement, (ast.For, ast.AsyncFor)) else statement.test
            ) + max(sequence_cost(statement.body), sequence_cost(statement.orelse))
        if isinstance(statement, ast.Try):
            branches = [sequence_cost(statement.body) + sequence_cost(statement.orelse)]
            branches.extend(sequence_cost(handler.body) for handler in statement.handlers)
            return max(branches) + sequence_cost(statement.finalbody)
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            return sum(expression_cost(item.context_expr) for item in statement.items) + sequence_cost(statement.body)
        return expression_cost(statement)

    def sequence_cost(statements):
        return sum(statement_cost(statement) for statement in statements)

    if function == "prepare":
        # The matching-backup loop returns; the fresh-backup path runs only
        # when no record matched. Summing both paths invents 9 extra commands.
        body = functions[function].body
        loop_index = next(i for i, statement in enumerate(body) if isinstance(statement, ast.For))
        prefix = sequence_cost(body[:loop_index])
        return prefix + max(statement_cost(body[loop_index]), sequence_cost(body[loop_index + 1 :]))
    return function_cost(function)


# The conservative counts include helper bodies and bound the longest branch.
assert preparation.TIMEOUT == budgets.SUBPROCESS_TIMEOUT_SECONDS
assert budgets.PREPARATION_MAX_SUBPROCESS_CALLS == 16
assert budgets.RESTORE_MAX_SUBPROCESS_CALLS == 6
assert _maximum_subprocess_calls("prepare") <= budgets.PREPARATION_MAX_SUBPROCESS_CALLS
assert _maximum_subprocess_calls("restore") <= budgets.RESTORE_MAX_SUBPROCESS_CALLS


def request_timeout(command):
    timeouts = {row["name"]: float(row["timeoutSeconds"]) for row in command_metadata()}
    assert command in timeouts, f"Hades Host command contract missing {command}"
    return timeouts[command]


# Keep worst-case aggregate budgets explicit and compare the Swift request
# watchdog with backend Python's bounded command/transport deadlines.
assert budgets.PREPARATION_OPERATION_BUDGET_SECONDS == (
    budgets.PREPARATION_MAX_SUBPROCESS_CALLS * budgets.SUBPROCESS_TIMEOUT_SECONDS
    + budgets.POST_PREPARATION_SCAN_BUDGET_SECONDS
)
assert budgets.PREPARATION_MAX_SUBPROCESS_CALLS == 16
assert budgets.RESTORE_OPERATION_BUDGET_SECONDS == (
    budgets.RESTORE_MAX_SUBPROCESS_CALLS * budgets.SUBPROCESS_TIMEOUT_SECONDS
    + budgets.SUBPROCESS_TIMEOUT_SECONDS
    + budgets.PROCESS_QUERY_TIMEOUT_SECONDS
)
assert budgets.RESTORE_MAX_SUBPROCESS_CALLS == 6
assert request_timeout("prepare") > budgets.PREPARATION_OPERATION_BUDGET_SECONDS
assert request_timeout("restore") > budgets.RESTORE_OPERATION_BUDGET_SECONDS
assert budgets.PREPARATION_OPERATION_BUDGET_SECONDS == 515
assert budgets.RESTORE_OPERATION_BUDGET_SECONDS == 215

assert budgets.STATUS_CHECK_BUDGET_SECONDS == 2 * (
    budgets.LUA_BOUNDARY_TIMEOUT_SECONDS
    + budgets.LUA_EXPRESSION_TIMEOUT_SECONDS
    + 2 * budgets.LUA_CLEANUP_TIMEOUT_SECONDS
)
assert budgets.DIAGNOSTICS_OPERATION_BUDGET_SECONDS == sum(
    (
        budgets.SUBPROCESS_TIMEOUT_SECONDS,
        budgets.STATUS_CHECK_BUDGET_SECONDS,
        budgets.LLDB_DISCOVERY_TIMEOUT_SECONDS,
        budgets.LLDB_PYTHON_TIMEOUT_SECONDS,
    )
)
assert request_timeout("diagnostics") > budgets.DIAGNOSTICS_OPERATION_BUDGET_SECONDS
assert budgets.DIAGNOSTICS_OPERATION_BUDGET_SECONDS == 65

assert budgets.SAVE_EDITOR_OPEN_BUDGET_SECONDS == (
    budgets.PROCESS_QUERY_TIMEOUT_SECONDS + budgets.SAVE_EDITOR_OPERATION_BUDGET_SECONDS
)
assert budgets.LOAD_PROFILE_OPERATION_BUDGET_SECONDS == (
    budgets.STATUS_CHECK_BUDGET_SECONDS + budgets.STATUS_COMMAND_BUDGET_SECONDS
)
assert request_timeout("save_editor_inventory") > budgets.SAVE_EDITOR_OPERATION_BUDGET_SECONDS
assert request_timeout("save_editor_open") > budgets.SAVE_EDITOR_OPEN_BUDGET_SECONDS
assert request_timeout("load_profile") > budgets.LOAD_PROFILE_OPERATION_BUDGET_SECONDS
assert (
    inspect.signature(Hades2LuaTransport.execute).parameters["expression_timeout_seconds"].default
    == budgets.LUA_EXPRESSION_TIMEOUT_SECONDS
)

hades_timeouts = {row["name"]: float(row["timeoutSeconds"]) for row in hades_command_metadata()}
assert hades_budgets.PROCESS_CONTROL_TIMEOUT_SECONDS == 3.0
assert hades_budgets.EXPRESSION_TIMEOUT_MICROSECONDS == 8_000_000
assert hades_time_warp.HadesSimulationTimeWarp.BOUNDED_TIMEOUT_SECONDS == hades_budgets.PROCESS_CONTROL_TIMEOUT_SECONDS
assert hades_budgets.CONNECT_OPERATION_BUDGET_SECONDS == (
    hades_budgets.PROCESS_QUERY_TIMEOUT_SECONDS
    + hades_budgets.PROCESS_IDENTITY_TIMEOUT_SECONDS
    + hades_budgets.SIDECAR_CONNECT_TIMEOUT_SECONDS
    + 4 * hades_budgets.SIDECAR_DEFAULT_TIMEOUT_SECONDS
)
assert hades_budgets.LOAD_PROFILE_OPERATION_BUDGET_SECONDS == (5 * hades_budgets.SIDECAR_DEFAULT_TIMEOUT_SECONDS)
assert hades_budgets.MUTATION_WITH_ROLLBACK_BUDGET_SECONDS == (2 * hades_budgets.SIDECAR_DEFAULT_TIMEOUT_SECONDS)
assert hades_timeouts["connect"] > hades_budgets.CONNECT_OPERATION_BUDGET_SECONDS
assert hades_timeouts["load_profile"] > hades_budgets.LOAD_PROFILE_OPERATION_BUDGET_SECONDS
assert hades_timeouts["set_feature"] > hades_budgets.MUTATION_WITH_ROLLBACK_BUDGET_SECONDS

# Every declared command for both real modules must have outer timeout > worst-case inner budget.
for game_id, audit in (("hades", hades_budget_audit()), ("hades2", hades2_budget_audit())):
    assert audit, game_id
    for row in audit:
        assert float(row["timeoutSeconds"]) > float(row["worstCaseInnerSeconds"]), (game_id, row)

print("host_watchdog_aggregate_budgets_ok")
