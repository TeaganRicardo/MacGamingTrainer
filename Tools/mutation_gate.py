#!/usr/bin/env python3
"""Prove that declared invariants actually fail when the code they guard breaks.

A test suite that is green tells you nothing on its own: this repository
shipped three reviews' worth of real defects (unreachable error keys, a
`HeroHasTrait` call whose extra argument Lua silently ignored, a failed trait
removal reported as success) while every test passed. Most of those defects
were unguarded fixes.

This harness closes that loop. Each entry in the manifest states one
behavioural invariant, the exact production edit that breaks it, and the test
that must catch the break. A mutation that leaves the suite green is a hole
in the guard; the run fails.

Two rules keep this honest:

1. The manifest is data, not prose. It is reviewable, and the gate is
   self-maintaining: adding an invariant here makes it enforced.
2. A mutation is only a hole if behaviour actually changed. Mutants that are
   behaviourally equivalent to the original are recorded as equivalent, with
   the evidence, instead of failing the gate.

Usage:
    python3 Tools/mutation_gate.py                  # run every declared mutation
    python3 Tools/mutation_gate.py --list           # show the manifest
    python3 Tools/mutation_gate.py --only c2-arity  # run one invariant
    python3 Tools/mutation_gate.py --keep-failing   # leave a failing mutant in place
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Mutation:
    """One production edit that must break one named test."""

    ident: str
    invariant: str
    path: Path
    old: str
    new: str
    test: str
    note: str = ""
    equivalent_reason: Optional[str] = None
    def label(self) -> str:
        return f"{self.path.relative_to(ROOT)}: {self.invariant}"


@dataclass
class Result:
    mutation: Mutation
    outcome: str  # "caught" | "survived" | "equivalent" | "skipped" | "error"
    detail: str = ""
    stderr_tail: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Manifest
#
# Every entry is a real defect that shipped, or a fix that shipped without a
# guard. `old` must be unique in its file; the harness verifies that before
# mutating so a stale anchor is reported instead of silently doing nothing.
# --------------------------------------------------------------------------

# Why each invariant exists. Every entry traces to a defect that actually
# shipped, or to a review that demanded the check. An invariant with no
# incident behind it is a rule added to make a number look better, so the gate
# refuses to run without one.
PROVENANCE = {
    "d01-unconditional-grant": "#193 shipped it; review caught an unconditional capability grant",
    "d01-escape-hatch": "#193: the forbidden generic RemoveTraitData teardown must stay unreachable",
    "d01-instance-identity": "D01: removal input is a name, never a run-local instance id",
    "d01-hero-has-trait-arity": "#193 CRITICAL: Lua ignored the extra argument, so the guard passed instead of refusing",
    "d01-drop-rarity-recheck": "#193 MAJOR: D00 section 6 requires shop ownership AND a non-nil Rarity",
    "d01-drop-request-id": "D01: a non-idempotent action must ride the request-id path",
    "d01-durable-identity-claim": "D01: trait identity is current-run only and must never be persisted",
    "d01-catalog-at-callsite": "D01: the inventory is projected from runtime state, not the catalog",
    "d01-permissive-decoder": "an unrecognised capability must default to no removal",
    "d01-model-guard": "the model must require the proven capability and scope",
    "d01-hide-unremovable-rows": "D01: unproven families stay visible but disabled",
    "err-remove-trait-unreachable": "#193 CRITICAL: all six remove_trait refusals fell to the generic key",
    "receipt-drop-remove-trait": "#193 CRITICAL: default: return dropped the failed receipt entirely",
    "receipt-failed-as-success": "#193 CRITICAL: a failed removal presented a green success",
    "seam-empty-prefix": "#202: an empty module prefix claimed every Host-owned key",
    "seam-literal-feature-title": "#202 CRITICAL: the zh-CN fix never reached the combat screen",
    "seam-hardcoded-label": "#202: a Trainer Product Term had no registry entry",
    "protocol-error-arguments": "#202: Core added error.arguments but AdapterError could not set it",
    "protocol-read-arguments": "#202: the protocol funnel did not forward the module's arguments",
    "fixture-key-outside-namespace": "#202: the fixture emitted a key in a namespace it does not own",
    "fixture-key-unresolvable": "#202: the fixture emitted a key that resolved nowhere",
    "core-time-warp-presentation": "#196: Core Time Warp presentation must stay on the Host-owned key seam",
    "host-registry-forbidden-term": "#197: shared Host resources must reject registry-owned Hades vocabulary",
    "diagnostics-toggle-source": "#198: diagnostics feature inventory must follow schema.TOGGLES automatically",
    "diagnostics-host-protocol-symbol": "#198: diagnostics protocol identity must come from HOST_PROTOCOL_VERSION",
    "error-registry-producer": "#204: registered runtime refusals must name a live producer",
    "package-product-version-owner": "#179/#199: Info.plist is the sole product-version owner",
    "package-module-identity": "#179/#199: publish must not replace another module's app output",
    "terminology-metadata-provenance": "#180: governed native terminology metadata must remain complete",
    "hades-internal-term-leak": "#180: internal-domain vocabulary is forbidden in canonical Hades UI",
    "hades-compatibility-alias-leak": "#180: compatibility aliases are forbidden in canonical Hades UI",
    "runtime-error-code-identity": "#180: localized runtime copy must not replace the stable machine error code",
    "core-registry-vocabulary-leak": "#180: generic Core must reject Hades vocabulary from the production registry",
}


# Where a recorded equivalent-mutant justification must live. A file that
# exists and holds the pasted before/after output is checkable; a paragraph in
# the manifest is not.
EVIDENCE_DIR = ROOT / "docs/audits/mutation-evidence"


def _is_falsifiable(ident: str, reason: str) -> bool:
    """An excuse must be backed by a recorded artifact, not by prose.

    A surviving mutation is only a hole if behaviour actually changed, so
    recording one as equivalent is legitimate. Two rounds of review killed both
    weaker versions of this rule:

    * a length check, defeated by a long paragraph;
    * a keyword check for "python3" and "output", defeated by adding those two
      words to the same paragraph -- demonstrated end to end, flipping a real
      catch to `equivalent` and the gate to `mutation_gate_ok`.

    The only thing that cannot be written convincingly is an artifact somebody
    else can read. So the excuse must name a file under EVIDENCE_DIR, that file
    must exist, and it must hold more than a bare claim. The manifest keeps the
    one-line summary; the directory keeps the proof.
    """
    text = reason.strip()
    if len(text) < 40:
        return False
    if not text.startswith(f"{ident}:"):
        return False
    # It must point at a real file, named so the mapping is unambiguous.
    names = re.findall(r"mutation-evidence/([A-Za-z0-9._-]+)", text)
    if not names:
        return False
    for name in names:
        candidate = EVIDENCE_DIR / name
        # Containment first. `is_file()` follows symlinks, so a symlink planted
        # inside EVIDENCE_DIR can point anywhere on disk -- including a scratch
        # file outside the repository -- and the rule would accept a citation to
        # evidence nobody can review with the commit. The artifact has to be a
        # real file that lives under the repository.
        if not candidate.is_file() or candidate.is_symlink():
            return False
        try:
            resolved = candidate.resolve()
        except OSError:
            return False
        if not resolved.is_relative_to(ROOT):
            return False
        # A file that merely restates the claim is not evidence either.
        if len(candidate.read_text(encoding="utf-8", errors="ignore").strip()) < 200:
            return False
    return True




def _hades_lua() -> Path:
    return ROOT / "Backend/games/hades2/runtime/hades.lua"


def manifest() -> list[Mutation]:
    lua = _hades_lua()
    return [
        # --- D01 removal safety -------------------------------------------
        Mutation(
            ident="d01-unconditional-grant",
            invariant="removal capability is granted only on the proven native predicate",
            path=lua,
            old='if eligible then scope = "nameLevelAllMatching" end',
            new='scope = "nameLevelAllMatching"',
            test="tests/test_hades2_current_run_traits.py",
            note="shipped in #193, caught by review",
        ),
        Mutation(
            ident="d01-escape-hatch",
            invariant="no generic RemoveTraitData escape hatch is reachable",
            path=lua,
            old="RemoveWeaponTrait(traitName, { Silent = true })",
            new="RemoveTraitData(CurrentRun.Hero, { Name = traitName })",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-instance-identity",
            invariant="removal input is a name, never an instance identity",
            path=lua,
            old="local traitName = params.trait",
            new=("local traitName = params.trait\n"
                 "      local peek = CurrentRun.Hero.Traits[1] and CurrentRun.Hero.Traits[1].Id"),
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-hero-has-trait-arity",
            invariant="the presence check passes a trait name, so it can actually refuse",
            path=lua,
            old="if not HeroHasTrait(traitName) then",
            new="if not HeroHasTrait(CurrentRun.Hero, traitName) then",
            test="tests/test_hades2_current_run_traits.py",
            note=("Lua ignores extra arguments, so this made the guard a no-op that "
                  "passes; found in #193 review as a CRITICAL"),
        ),
        Mutation(
            ident="d01-drop-rarity-recheck",
            invariant="the live gate re-checks both halves of the D00 sell predicate",
            path=lua,
            old=('            if trait.Rarity == nil then\n'
                 '              error("Trait is not sell-eligible, so no safe removal exists: " .. traitName)\n'
                 '            end\n'),
            new="",
            test="tests/test_hades2_current_run_traits.py",
            note="#193 review MAJOR: capability model and executable gate disagreed",
        ),
        Mutation(
            ident="d01-drop-request-id",
            invariant="removal is treated as a non-idempotent action requiring a request id",
            path=ROOT / "Backend/games/hades2/command_router.py",
            old="'open_special_choice','lock_resource','lock_rerolls','remove_trait',",
            new="'open_special_choice','lock_resource','lock_rerolls',",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-durable-identity-claim",
            invariant="trait identity is presented as current-run only",
            path=lua,
            old="currentRunTraitIdentityPersistent = false",
            new="currentRunTraitIdentityPersistent = true",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-catalog-at-callsite",
            invariant="state() projects the inventory from the runtime, not the catalog",
            path=lua,
            old="local traitList, traitListReason = currentRunTraits()",
            new="local traitList, traitListReason = boons() and {list = boons()} or {list = {}}",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-permissive-decoder",
            invariant="an unrecognised capability defaults to no removal",
            path=ROOT / "Sources/Hades2/Hades2BackendState.swift",
            old="?? .none",
            new="?? .nameLevelAllMatching",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-model-guard",
            invariant="the model requires the proven capability and scope before removing",
            path=ROOT / "Sources/Hades2/Hades2Model.swift",
            old="guard trait.canRemove, trait.removalScopeAllMatching else { return }",
            new="guard false else { return }",
            test="tests/test_hades2_current_run_traits.py",
        ),
        Mutation(
            ident="d01-hide-unremovable-rows",
            invariant="the remove control is shown only for a removable row",
            path=ROOT / "Sources/Hades2/Hades2View.swift",
            old=("            if trait.canRemove {\n"
                 "                Button {\n"
                 "                    model.removeTrait(trait)"),
            new=("            if true {\n"
                 "                Button {\n"
                 "                    model.removeTrait(trait)"),
            test="tests/test_hades2_current_run_traits.py",
        ),
        # --- unreachable error copy (#193 review CRITICAL) -------------------
        Mutation(
            ident="err-remove-trait-unreachable",
            invariant="every remove_trait refusal resolves to its own stable key",
            path=ROOT / "Backend/games/hades2/error_presentation.py",
            old=("  'message': 'Trait removal requires an active run room',\n"
                 "  'key': 'hades2.error.traitRemovalNeedsRun',\n"
                 "  'runtime': {'commands': ['remove_trait'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},"),
            new=("  'message': 'Trait removal requires an active run room',\n"
                 "  'key': 'hades2.error.traitRemovalNeedsRun',\n"
                 "  'runtime': {'commands': ['remove_trait_DISABLED'], 'producer': {'kind': 'command', 'name': 'remove_trait'}}},"),
            test="tests/test_hades2_current_run_traits.py",
            note=("shipped in #193: all six refusals fell to the generic fallback key, "
                  "so the player was never told why"),
        ),
        # --- failed removal reported as success ----------------------------
        Mutation(
            ident="receipt-drop-remove-trait",
            invariant="a failed removal presents an error, not silence",
            path=ROOT / "Sources/Hades2/Hades2Model.swift",
            old='        case .removeTrait: title = presentation("hades2.receipt.traitRemoved")\n',
            new="",
            test="tests/test_hades2_backend_state_cleanup.py",
            note="#193 review CRITICAL: default: return dropped the failed receipt entirely",
        ),
        Mutation(
            ident="receipt-failed-as-success",
            invariant="a failed outcome never presents a success notice",
            path=ROOT / "Sources/Hades2/Hades2Model.swift",
            old=('        case .failed:\n'
                 '            noticeToken = nil\n'
                 '            errorToken = presentation("hades2.receipt.failed", arguments: [title.key])'),
            new=('        case .failed:\n'
                 '            noticeToken = presentation("hades2.receipt.traitRemovalCompleted", arguments: [title.key])\n'
                 '            errorToken = nil'),
            test="tests/test_hades2_backend_state_cleanup.py",
        ),
        # --- presentation seam --------------------------------------------
        Mutation(
            ident="seam-empty-prefix",
            invariant="a module with no namespace cannot claim Host-owned keys",
            path=ROOT / "Sources/Core/Host/TrainerLocalization.swift",
            old="        guard !prefix.isEmpty else { return }\n",
            new="",
            test="tests/test_host_localization_behavior.py",
            note="#202: presentationKeyPrefix defaults to \"\", and \"\" prefixes every key",
        ),
        Mutation(
            ident="seam-literal-feature-title",
            invariant="a feature row never carries a literal title",
            path=ROOT / "Sources/Hades2/Hades2View.swift",
            old='featureRow(text("hades2.feature.invincibility")',
            new='featureRow("Invincibility"',
            test="tests/test_hades2_presentation_contract.py",
            note="#202 review CRITICAL: the only row out of 24 that bypassed the seam",
        ),
        Mutation(
            ident="seam-hardcoded-label",
            invariant="a Trainer Product Term is referenced through the registry",
            path=ROOT / "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json",
            old='"hades2.feature.invincibility": "{term:productTerms.invincibility}"',
            new='"hades2.feature.invincibility": "无敌模式"',
            test="tests/test_hades2_presentation_contract.py",
        ),
        # --- final post-#177 hardening seams ------------------------------
        Mutation(
            ident="core-time-warp-presentation",
            invariant="Core presentation errors reject literal player-facing copy",
            path=ROOT / "Backend/core/adapter.py",
            old=("        if not isinstance(presentation, str) or "
                 "not presentation.startswith(self.PRESENTATION_PREFIX):"),
            new="        if not isinstance(presentation, str):",
            test="tests/test_process_time_warp_controller.py",
            note="#196 alias-agnostic Host presentation seam",
        ),
        Mutation(
            ident="host-registry-forbidden-term",
            invariant="shared Host localization contains no Hades registry vocabulary",
            path=ROOT / "Resources/Localization/zh-CN.lproj/Host.strings",
            old='"host.gameLibrary" = "游戏库";',
            new='"host.gameLibrary" = "重骰";',
            test="tests/test_host_shared_localization_coverage.py",
            note="#197 registry-derived compatibility-alias guard",
        ),
        Mutation(
            ident="diagnostics-toggle-source",
            invariant="diagnostics feature inventory derives from schema.TOGGLES",
            path=ROOT / "Backend/games/hades2/diagnostics.py",
            old="    diagnostic_features=list(schema.TOGGLES)",
            new="    diagnostic_features=list(schema.TOGGLES[:-1])",
            test="tests/test_diagnostics_live_status.py",
            note="#198 schema single-source cleanup",
        ),
        Mutation(
            ident="diagnostics-host-protocol-symbol",
            invariant="diagnostic bundles report the Host protocol from its canonical owner",
            path=ROOT / "Backend/games/hades2/diagnostics.py",
            old=("        'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),"
                 "'protocolVersion':HOST_PROTOCOL_VERSION,"),
            new=("        'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),"
                 "'protocolVersion':APP_BACKEND_VERSION,"),
            test="tests/test_hades2_diagnostics_log_scope.py",
            note="#198 protocol single-source cleanup",
        ),
        Mutation(
            ident="error-registry-producer",
            invariant="a registered runtime refusal must point at a live producer",
            path=ROOT / "Backend/games/hades2/error_presentation.py",
            old=("  'message': 'Trait removal requires an active run room',\n"
                 "  'key': 'hades2.error.traitRemovalNeedsRun',\n"
                 "  'runtime': {'commands': ['remove_trait'], 'producer': "
                 "{'kind': 'command', 'name': 'remove_trait'}}},"),
            new=("  'message': 'Trait removal requires an active run room',\n"
                 "  'key': 'hades2.error.traitRemovalNeedsRun',\n"
                 "  'runtime': {'commands': ['remove_trait'], 'producer': "
                 "{'kind': 'command', 'name': 'remove_trait_missing'}}},"),
            test="tests/test_hades2_error_registry_single_source.py",
            note="#204 dead-entry reverse coverage",
        ),
        Mutation(
            ident="package-product-version-owner",
            invariant="artifact identity cannot override Info.plist product SemVer",
            path=ROOT / "Tools/write_build_provenance.py",
            old='    if plist.get("CFBundleShortVersionString") != product_version:',
            new='    if False and plist.get("CFBundleShortVersionString") != product_version:',
            test="tests/test_build_artifact_provenance.py",
            note="#179/#199 root-only product identity",
        ),
        Mutation(
            ident="package-module-identity",
            invariant="publishing cannot replace an app owned by another module",
            path=ROOT / "Tools/publish_module_build.py",
            old="                if previous_game != selected_game:",
            new="                if False and previous_game != selected_game:",
            test="tests/test_module_publish_safety.py",
            note="#179/#199 selected-module output identity",
        ),
        # --- C05 terminology / presentation drift --------------------------
        Mutation(
            ident="terminology-metadata-provenance",
            invariant="governed native terminology keeps its localization identity metadata",
            path=ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json",
            old='"id": "GodBoon",',
            new='"id": "",',
            test="tests/test_hades2_official_terminology.py",
            note="#180 metadata drift must fail from the production registry",
        ),
        Mutation(
            ident="hades-internal-term-leak",
            invariant="internal-domain terms cannot appear in canonical Hades presentation",
            path=ROOT / "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json",
            old='"hades2.feature.invincibility": "{term:productTerms.invincibility}"',
            new='"hades2.feature.invincibility": "TalentDrop"',
            test="tests/test_hades2_presentation_contract.py",
            note="#180 registry-derived forbidden-surface enforcement",
        ),
        Mutation(
            ident="hades-compatibility-alias-leak",
            invariant="compatibility aliases cannot appear in canonical Hades presentation",
            path=ROOT / "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json",
            old='"hades2.feature.invincibility": "{term:productTerms.invincibility}"',
            new='"hades2.feature.invincibility": "重骰"',
            test="tests/test_hades2_presentation_contract.py",
            note="#180 registry-derived canonical-surface enforcement",
        ),
        Mutation(
            ident="runtime-error-code-identity",
            invariant="runtime localization preserves the stable machine error code",
            path=ROOT / "Backend/games/hades2/runtime_error_presentation.py",
            old="    return Hades2PresentationError(error.code, key, arguments, diagnostic=diagnostic)",
            new="    return Hades2PresentationError(raw, key, arguments, diagnostic=diagnostic)",
            test="tests/test_hades2_error_registry_single_source.py",
            note="#180 code/presentation identity separation",
        ),
        Mutation(
            ident="core-registry-vocabulary-leak",
            invariant="generic Core contains no Hades vocabulary owned by the production registry",
            path=ROOT / "Backend/core/adapter.py",
            old='            raise ValueError("Core presentation errors must use a host.* key.")',
            new='            raise ValueError("Core presentation errors must use a host.* key; 卡俄斯祝福 is module-owned.")',
            test="tests/test_host_shared_localization_coverage.py",
            note="#180 replaces a hand-maintained Core vocabulary sample with registry-derived coverage",
        ),
        # --- protocol envelope ---------------------------------------------
        Mutation(
            ident="protocol-error-arguments",
            invariant="error arguments travel the wire and reach the Host",
            path=ROOT / "Backend/core/adapter.py",
            old="        self.arguments = list(arguments)",
            new="        self.arguments = []",
            test="tests/test_protocol_fixtures_v0180.py",
        ),
        Mutation(
            ident="protocol-read-arguments",
            invariant="the protocol funnel forwards the module's arguments",
            path=ROOT / "Backend/core/protocol.py",
            old="                arguments = error.arguments",
            new="                arguments = None",
            test="tests/test_protocol_fixtures_v0180.py",
        ),
        Mutation(
            ident="fixture-key-outside-namespace",
            invariant="a module's emitted key lives in that module's own namespace",
            path=ROOT / "ContractFixtures/reference_module/backend/adapter.py",
            old="referenceFixture.error.failed",
            new="fixture.error.failed",
            test="tests/test_reference_fixture_session_integration.py",
            note="#202 review: a key that resolves nowhere is a fiction in a new place",
        ),
        Mutation(
            ident="fixture-key-unresolvable",
            invariant="a module's presentation table actually contains the key it emits",
            path=ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift",
            old='            "referenceFixture.error.failed": [.zhCN: "夹具请求失败（{0}，{1}）。", .en: "Fixture request failed ({0}, {1})."],\n',
            new="",
            test="tests/test_reference_fixture_session_integration.py",
        ),
    ]


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

# Each owning test declares completion with one literal *_ok marker, either in
# Python or in an embedded compiled harness. Discover it from that test instead
# of mirroring test->token ownership here.
def success_token_for(test: str) -> str:
    path = ROOT / test
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as error:
        raise ValueError(f"cannot inspect owning test {test}: {error}") from error
    python_tokens = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "print" or not node.args:
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.endswith("_ok"):
            python_tokens.add(value.value)
    if len(python_tokens) == 1:
        return next(iter(python_tokens))
    if len(python_tokens) > 1:
        raise ValueError(
            f"owning test {test} prints multiple *_ok completion markers: "
            f"{sorted(python_tokens)}"
        )

    # Some macOS behavior tests are Python wrappers around a compiled Swift
    # harness. Their completion marker is emitted by the embedded program, so
    # there is no Python print() call to discover. In that case only, inspect
    # string literals and require a single marker there.
    embedded_tokens = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        embedded_tokens.update(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*_ok\b", node.value))
    if len(embedded_tokens) != 1:
        raise ValueError(
            f"owning test {test} must declare exactly one literal *_ok completion marker; "
            f"found {sorted(embedded_tokens)}"
        )
    return next(iter(embedded_tokens))

def _run(test: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, test],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout,
    )


def _tail(text: str, n: int = 3) -> list[str]:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return [l[-160:] for l in lines[-n:]]


# Signals that the run failed to *execute* rather than to *disprove* an
# invariant. A mutation that only makes the harness crash is not evidence the
# invariant is policed -- the test never got a chance to judge anything.
#
# Each declared test prints a unique success token as its last line, so a
# genuine catch is one that fails WITHOUT that token. A missing token therefore
# means the run died, not that the assertion fired.
# `CalledProcessError` is deliberately NOT here: the Swift harnesses raise it
# with `check=True` and capture_output=True, so it wraps BOTH a genuine
# precondition failure and a compile crash, and the inner message is discarded
# either way. Treating it as a crash flag would mark every real Swift catch as
# an error; treating it as a catch would let a compile-only mutation pass. So
# the discriminator is the compiler's own diagnostics instead.
# Diagnostic formats the toolchains in this repo produce. These patterns are
# NO LONGER the decision -- `_is_verdict` is. They are kept so a run reported as
# an error can be read and classified by eye.
#
# Two rounds of review killed the pattern-list approach in both directions. A
# bare "error: " substring matched Swift's "Fatal error:" and missed a
# linker-only failure, so linking mutations read as verdicts. Adding trap
# patterns then broke the other way, because on macOS a real Swift `assert` is
# raised as SIGTRAP and the harness reports only the signal. Since the wrapper
# discards the text that would tell a crash and a verdict apart, no list of
# substrings can decide it. Two positive escapes can.
_CRASH_SIGNALS = (
    r"\bSyntaxError\b",
    r"\bIndentationError\b",
    r"\bModuleNotFoundError\b",
    r"\bImportError\b",
    r"\.swift:\d+:\d+: error:",   # swiftc, anchored to its diagnostic format
    r"(?:^|\n)\s*ld: (?:library not loaded|symbol\(s\) not found|framework not found)",
    r"(?:^|\n)\s*clang: error:",
)


def _is_verdict(text: str) -> bool:
    """True when the output shows a reached assertion, in any harness.

    Python and Swift report the same event differently and both are real
    catches. Python raises `AssertionError`. Swift raises `fatalError` /
    `assert` / `precondition`, which macOS delivers as SIGTRAP, and each prints
    its own wording to stderr.

    The signal itself is never accepted as evidence, because it says nothing
    about *why* the process stopped: a reached assertion and a force-unwrap nil
    both produce SIGTRAP and nothing else to tell them apart. So the message is
    required, which only works if the harness passes the child's output along
    rather than swallowing it into a CalledProcessError. One of them used to do
    exactly that -- see tests/test_host_localization_behavior.py.

    These are escapes, each a specific positive statement that an assertion was
    reached -- never a list of things that merely look wrong. Anything matching
    none of them is an error.
    """
    return (
        # Python's bare assert raises AssertionError.
        "AssertionError" in text
        # Swift's assert() and precondition() both trap, and both print their
        # own wording rather than "AssertionError". Measured on arm64 macOS:
        #   assert(ok, "...")        -> "T.swift:3: Assertion failed: ..."
        #   precondition(cond, "...") -> "T.swift:6: Precondition failed: ..."
        # Both are reached assertions. Without these two strings the only thing
        # recognising a Swift catch is the signal the wrapper reports after
        # discarding the message -- so the classifier was leaning entirely on
        # SIGTRAP, which a genuine crash also produces. Measured: a plain
        # Int8 overflow traps with rc=-5 and prints NOTHING, so it correctly
        # reads as an error. That distinction only holds while the message
        # forms are matched here rather than inferred from the signal.
        or "Assertion failed:" in text
        or "Precondition failed:" in text
        # `Fatal error:` is deliberately NOT a verdict, even though
        # `fatalError("msg")` is the dominant assertion form in this repository's
        # Swift harnesses. The runtime prints the same marker for crashes the
        # caller never chose, and the two cannot be told apart by message text --
        # the wording varies by version and language ("Index out of range",
        # "Unexpectedly found nil while unwrapping an Optional value", "Range out
        # of bounds"), so a blocklist goes stale on every toolchain upgrade and
        # becomes a silent-pass channel nobody is looking at.
        #
        # The path is not a reliable discriminator either: a reached assertion
        # prints `hades2runlogwatcher/hades2runlogwatcher.swift:2: Fatal error:`
        # and so does a stdlib force-unwrap, `unwrap/unwrap.swift:3: Fatal
        # error:`. Both are relative paths rooted at the binary name. That
        # heuristic was implemented and measured, and rejected.
        #
        # So the marker is dropped outright, and the cost was measured rather
        # than assumed: with this escape removed the gate still reports
        # `caught 21 | survived 0 | equivalent 0 | skipped 0 | error 0`. Not one
        # of the 21 declared invariants was resting on it -- every one is caught
        # by `Assertion failed:`, `Precondition failed:`, `XCTAssert`, an XCTest
        # summary line, or a `FAIL:` line, all of which name the failure rather
        # than the signal. A marker nothing needs is a marker that can only
        # mislead.
        or "XCTAssert" in text
        # XCTest reports a failed assertion as a per-test summary line --
        # "Suite.testCase : failed - reason". It carries neither the macro name
        # nor a signal, and it is a real catch. The line number that swiftc puts
        # in a diagnostic is absent here, so the pattern must not require one.
        or re.search(r"^\S.*\s:\s+failed\b", text, re.M) is not None
        # A trap signal is NOT a verdict and is deliberately not matched here.
        # It was, and that made a force-unwrap nil score as a catch: the
        # message an assertion prints and the message a crash prints are the only
        # things that differ, and the signal erases that difference. The one
        # harness that used to rely on this escape now asserts on the child's
        # captured output instead (tests/test_host_localization_behavior.py), so
        # the reason reaches the gate rather than being discarded by a
        # CalledProcessError wrapper. A crash still reads as an error, which is
        # the safe direction: it fails the build instead of inflating the count.
        # Python's unittest reports a failed test as a bare `FAIL: <docstring>`
        # line and a summary `FAILED (failures=N)`. Neither mentions an
        # assertion, and several suites in this repo use unittest rather than
        # bare asserts, so without these a real catch reads as an error.
        # Measured: no crash output matches either pattern.
        or re.search(r"^FAIL(?:ED)?: \S", text, re.M) is not None
        or re.search(r"^FAILED \((?:failures|errors)=\d+", text, re.M) is not None
    )


def _only_crashed(result: subprocess.CompletedProcess, success_token: str = "") -> bool:
    """True when a non-zero exit came from the harness dying, not an assertion.

    The question is always the same: did the test reach its assertions and judge
    the invariant, or did it stop before that and prove nothing?

    Two escapes establish a real verdict -- the success token, printed only by a
    run that completed, and a positive assertion marker. Everything else is an
    error.

    The default matters more than it looks. Reporting a crash as a catch inflates
    the headline number with guards that were never exercised, which is the exact
    defect round 1 found and the reason "21/21 caught" once meant nothing.
    Reporting a real catch as an error is visible, fails the build, and is cheap
    to fix. The reverse is silent.
    """
    text = (result.stderr or "") + (result.stdout or "")
    if success_token and success_token in text:
        return False  # it ran to completion, so any failure is a real verdict
    if _is_verdict(text):
        return False  # the test reached its assertions and judged
    return True


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _anchor_count(text: str, needle: str) -> int:
    """A stale anchor must be loud: it means the manifest needs updating."""
    return text.count(needle)


def check_manifest(mutations: list[Mutation]) -> list[str]:
    """Validate every anchor before running anything. Stale anchors are holes."""
    problems = []
    seen_ids = set()
    for m in mutations:
        if m.ident in seen_ids:
            problems.append(f"{m.ident}: duplicate ident")
        seen_ids.add(m.ident)
        if not m.test.startswith("tests/"):
            problems.append(f"{m.ident}: test must be a tests/ path, got {m.test}")
        if not (ROOT / m.test).is_file():
            problems.append(f"{m.ident}: test does not exist: {m.test}")
        else:
            try:
                success_token_for(m.test)
            except ValueError as error:
                problems.append(f"{m.ident}: {error}")
        if not PROVENANCE.get(m.ident):
            problems.append(
                f"{m.ident}: no provenance recorded. Every declared invariant must name "
                "the shipped defect or the review that demanded it, so it is traceable "
                "rather than decorative")
        if m.equivalent_reason is not None and not _is_falsifiable(m.ident, m.equivalent_reason):
            problems.append(
                f"{m.ident}: the equivalent-mutant excuse is not backed by a recorded "
                "artifact. It must read '{ident}: ...' and cite an existing file under "
                f"{EVIDENCE_DIR.relative_to(ROOT)} holding the before/after output")
        if not m.path.is_file():
            problems.append(f"{m.ident}: production file missing: {m.path}")
            continue
        count = _anchor_count(_read(m.path), m.old)
        if count == 0:
            problems.append(f"{m.ident}: anchor not found in {m.path.relative_to(ROOT)} — manifest is stale")
        elif count > 1:
            problems.append(
                f"{m.ident}: anchor appears {count}x in {m.path.relative_to(ROOT)} — must be unique")
    return problems


def run_mutation(m: Mutation) -> Result:
    """Break one invariant and require the owning test to notice.

    Two properties make the result mean anything, and both were missing in the
    first version of this harness:

    * The owning test must be GREEN before the mutation. Otherwise a test that
      is already red -- a missing locale, a rotted fixture, an unrelated flake
      -- makes every mutation look "caught" while proving nothing. With 12 of
      21 invariants owned by one file, one broken file blessed all of them.
    * The failure must be caused by the mutation. A mutation that merely makes
      the harness crash (a Swift type error, a syntax error) is not evidence
      that the invariant is policed; it is evidence that the test cannot run.

    So: run clean, run mutated, and require the mutant run to fail *for a
    different reason* than a crash. A mutation that only crashes is reported
    as an error, never as a catch.
    """
    original = _read(m.path)
    if m.old not in original:
        return Result(m, "skipped", "anchor disappeared between check and run")

    try:
        token = success_token_for(m.test)
    except ValueError as error:
        return Result(m, "error", str(error))
    clean = _run(m.test)
    if clean.returncode != 0:
        return Result(
            m, "error",
            "the owning test is RED before mutation, so this invariant cannot "
            "be proven; fix the test first",
            _tail(clean.stderr))
    if token and token not in (clean.stdout or ""):
        return Result(
            m, "error",
            f"the owning test did not print its success token {token!r}, so a "
            "crashed run cannot be told apart from a real catch",
            _tail(clean.stdout))

    try:
        m.path.write_text(original.replace(m.old, m.new, 1), encoding="utf-8")
        mutated = _run(m.test)
    except subprocess.TimeoutExpired:
        return Result(m, "error", "test timed out under mutation")
    finally:
        m.path.write_text(original, encoding="utf-8")

    if mutated.returncode == 0:
        if m.equivalent_reason:
            return Result(m, "equivalent", m.equivalent_reason)
        return Result(m, "survived", "test stayed green with the invariant broken",
                      _tail(mutated.stdout))

    if _only_crashed(mutated, token):
        return Result(
            m, "error",
            "the mutated run failed as a harness/compile error rather than an "
            "assertion, so the invariant was not actually policed",
            _tail(mutated.stderr))
    return Result(m, "caught", stderr_tail=_tail(mutated.stderr))


def verify_clean_tree() -> Optional[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        return f"git status failed (exit {result.returncode}): {diagnostic}"
    if result.stdout.strip():
        return result.stdout
    return None


def exit_code_for(results: list[Result]) -> int:
    """Return the gate verdict for completed mutation results."""
    return 1 if any(
        result.outcome in {"survived", "skipped", "error"}
        for result in results
    ) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the manifest and exit")
    parser.add_argument("--only", action="append", default=[], help="run one invariant by ident")
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--keep-failing", action="store_true",
                        help="leave a surviving mutant in place for inspection")
    args = parser.parse_args()

    mutations = manifest()
    if args.only:
        wanted = set(args.only)
        unknown = wanted - {m.ident for m in mutations}
        if unknown:
            print(f"unknown idents: {sorted(unknown)}", file=sys.stderr)
            return 2
        mutations = [m for m in mutations if m.ident in wanted]

    if args.list:
        for m in mutations:
            print(f"{m.ident:34} {m.path.relative_to(ROOT)}")
            print(f"{'':34}   invariant: {m.invariant}")
            print(f"{'':34}   test:      {m.test}")
        print(f"\n{len(mutations)} declared invariants")
        return 0

    # Order matters: refuse a dirty tree before asking for a toolchain, and
    # validate the manifest before touching production code. A machine without
    # swiftc must still be able to see that its tree is dirty, otherwise the
    # contract test cannot assert this without becoming macOS-only.
    dirty = verify_clean_tree()
    if dirty:
        print("working tree must be clean before running the gate:", file=sys.stderr)
        print(dirty, file=sys.stderr)
        return 1

    problems = check_manifest(mutations)
    if problems:
        print("manifest is invalid:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    if not shutil.which("swiftc"):
        print("swiftc is required: the declared invariants include compiled Swift",
              file=sys.stderr)
        return 2

    results = [run_mutation(m) for m in mutations]

    survivors = [r for r in results if r.outcome == "survived"]
    skipped = [r for r in results if r.outcome == "skipped"]
    errored = [r for r in results if r.outcome == "error"]
    caught = [r for r in results if r.outcome == "caught"]
    equivalent = [r for r in results if r.outcome == "equivalent"]

    if args.keep_failing and survivors:
        m = survivors[0].mutation
        _read  # no-op, keeps intent obvious
        original = _read(m.path)
        m.path.write_text(original.replace(m.old, m.new, 1), encoding="utf-8")
        print(f"left the first surviving mutant in place: {m.label()}", file=sys.stderr)

    payload = {
        "caught": [r.mutation.ident for r in caught],
        "survived": [r.mutation.ident for r in survivors],
        "equivalent": [r.mutation.ident for r in equivalent],
        "skipped": [r.mutation.ident for r in skipped],
        "error": [r.mutation.ident for r in errored],
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        width = max((len(r.mutation.ident) for r in results), default=0)
        for r in results:
            mark = {"caught": "caught ", "survived": "SURVIVED", "equivalent": "equivalent",
                    "skipped": "SKIPPED ", "error": "ERROR   "}[r.outcome]
            print(f"  {mark}  {r.mutation.ident:<{width}}  {r.mutation.test}")
            if r.outcome == "survived" and r.stderr_tail:
                print(f"           {r.mutation.invariant}")
        print()
        print(f"caught {len(caught)}  |  survived {len(survivors)}  |  "
              f"equivalent {len(equivalent)}  |  skipped {len(skipped)}  |  error {len(errored)}")

    after = verify_clean_tree()
    if after and not args.keep_failing:
        print("the gate restored files incorrectly; this is a bug in the harness", file=sys.stderr)
        print(after, file=sys.stderr)
        return 1

    verdict = exit_code_for(results)
    if survivors:
        print(
            f"\n{survivors[0].mutation.ident} stayed green with its invariant broken. "
            "Either the guard is missing or the mutation is behaviourally equivalent — "
            "prove which, then record an equivalent_reason or fix the guard.",
            file=sys.stderr)
    if verdict:
        return verdict
    print("mutation_gate_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
