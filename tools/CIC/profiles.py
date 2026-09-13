from __future__ import annotations

from typing import Any


class CICProfileError(ValueError):
    pass


_PROFILES: dict[str, dict[str, Any]] = {
    "aigmos": {
        "event_rules": [
            {
                "rule_id": "AIGMOS_COMMANDDEF_HANDLER",
                "language_id": "python",
                "evidence_kind": "registration_handler",
                "evidence_value": "CommandDef",
                "event_type_ref": "command",
                "identity_keyword": "command",
            }
        ],
        "module_discovery_rules": [
            {
                "rule_id": "AIGMOS_INPUT_MODULE_DISCOVERY",
                "language_id": "python",
                "registry_path": "system/inputs/registry.py",
                "role": "input",
                "package_binding_names": ["_CORE_PACKAGE", "_EXT_PACKAGE"],
                "skip_binding_name": "_SKIP_MODULES",
            },
            {
                "rule_id": "AIGMOS_ADAPTER_MODULE_DISCOVERY",
                "language_id": "python",
                "registry_path": "system/adapters/registry.py",
                "role": "adapter",
                "package_binding_names": ["_CORE_PACKAGE", "_EXT_PACKAGE"],
                "skip_binding_name": "_SKIP_MODULES",
            },
        ],
        "state_contract_rules": [
            {
                "rule_id": "AIGMOS_RUNNER_DEFINITION_STATE",
                "source_path": "system/runtime/runner_store.py",
                "symbol_binding": "RUNNER_DEFS_SYMBOL",
                "read_targets": ["_state_get_value"],
                "write_targets": ["_state_set_value"],
            },
            {
                "rule_id": "AIGMOS_TRIGGER_DEFINITION_STATE",
                "source_path": "system/lib/trigger/store.py",
                "symbol_binding": "TRIGGER_DEFS_ROOT",
                "read_targets": ["read_value"],
                "write_targets": ["write_value", "delete_value"],
            },
            {
                "rule_id": "AIGMOS_EVENT_DEFINITION_STATE",
                "source_path": "system/lib/trigger/store.py",
                "symbol_binding": "EVENT_DEFS_ROOT",
                "read_targets": ["read_value"],
                "write_targets": ["write_value", "delete_value"],
            },
            {
                "rule_id": "AIGMOS_TRIGGER_RUNTIME_STATE",
                "source_path": "system/lib/trigger/store.py",
                "symbol_binding": "TRIGGER_STATE_ROOT",
                "read_targets": ["read_value"],
                "write_targets": ["write_value", "delete_value"],
            }
        ],
        "semantic_gap_rules": [
            {
                "id": "AIGMOS_RUNNER_CONCURRENT_SCHEDULING",
                "classification": "cw_semantic_gap",
                "source_path": "system/runtime/runner.py",
                "evidence_kind": "call_target",
                "targets": ["ThreadPoolExecutor", "threading.Thread", "submit"],
                "observed_semantics": "The live runner creates a background worker thread and submits runner steps to a ThreadPoolExecutor while preserving inflight job identity.",
                "missing_cw_semantics": "CW has no explicit asynchronous/background scheduling or concurrent job lifecycle semantic.",
                "why_existing_constructs_are_insufficient": "Event causality describes dispatch order but does not define concurrent execution, worker ownership, inflight jobs or executor scheduling. while/loop describe synchronous control and are not equivalent.",
                "candidate_extension": "Add a minimal runtime scheduling semantic, preferably as DR-level Effect/Event execution semantics rather than a new canonical atom.",
                "ccf_change_required": False,
                "blocking": True,
            },
            {
                "id": "AIGMOS_RUNNER_CANCELLATION",
                "classification": "cw_semantic_gap",
                "source_path": "system/runtime/runner.py",
                "evidence_kind": "call_target",
                "targets": ["cancel", "cancel_event.set"],
                "observed_semantics": "Runner kill/shutdown paths can request cancellation of an inflight execution and cancel a Future.",
                "missing_cw_semantics": "CW has no cancellation/termination request semantic for an already-dispatched execution.",
                "why_existing_constructs_are_insufficient": "fail terminates the current Function path; it does not address another inflight execution and therefore cannot represent cancellation.",
                "candidate_extension": "Add explicit execution-cancel semantics at DR level, scoped to a concrete execution/job identity.",
                "ccf_change_required": False,
                "blocking": True,
            },
            {
                "id": "AIGMOS_RUNNER_DYNAMIC_COMMAND_DISPATCH",
                "classification": "cw_semantic_gap",
                "source_path": "system/runtime/runner.py",
                "evidence_kind": "call_target",
                "targets": ["_call_step_executor"],
                "observed_semantics": "A runner step is stored as raw command text and is dispatched through a runtime-provided step executor; the concrete command Event is selected from the text only at execution time.",
                "missing_cw_semantics": "Current canonical Event causality requires explicit Event identity/refs and has no dynamic dispatch-by-runtime-text semantic.",
                "why_existing_constructs_are_insufficient": "A static event_cause cannot truthfully name a future command Event when the target command is data selected at runtime. function_call is forbidden and dependency is structural only.",
                "candidate_extension": "Add an explicit dynamic Event dispatch semantic whose target identity is resolved from validated runtime Data under a declared contract.",
                "ccf_change_required": False,
                "blocking": True,
            },
            {
                "id": "AIGMOS_RUNNER_DURABLE_DEFINITION_STATE",
                "classification": "cic_mapping_gap",
                "source_path": "system/runtime/runner_store.py",
                "evidence_kind": "literal_binding",
                "binding": "RUNNER_DEFS_SYMBOL",
                "value": "#SYSTEM:runtime:runners",
                "observed_semantics": "Durable runner definitions are read from and written to #SYSTEM:runtime:runners with fields name/source/mode/lines/autostart.",
                "missing_cw_semantics": "No new CW primitive is proven missing; CIC has source-backed state-contract evidence but does not yet materialize it as Data plus Schema/CTRCT.",
                "why_existing_constructs_are_insufficient": "Existing CW Data and Schema semantics appear sufficient, but automatic contract materialization still requires exact field type and constraint evidence.",
                "candidate_extension": "Continue CIC mapping from the state_contract_candidate into a CTRCT-owned Schema and canonical Data slot after field contracts are proven.",
                "ccf_change_required": False,
                "blocking": False,
            },
        ],
    }
}


def list_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))


def profile_options(name: str | None) -> dict[str, Any]:
    if name is None:
        return {}
    clean = str(name).strip().lower()
    if not clean:
        return {}
    profile = _PROFILES.get(clean)
    if profile is None:
        raise CICProfileError(f"unknown CIC profile: {name!r}; available: {', '.join(list_profiles())}")
    return {
        "event_rules": [dict(item) for item in profile.get("event_rules", [])],
        "module_discovery_rules": [dict(item) for item in profile.get("module_discovery_rules", [])],
        "state_contract_rules": [dict(item) for item in profile.get("state_contract_rules", [])],
        "semantic_gap_rules": [dict(item) for item in profile.get("semantic_gap_rules", [])],
    }
