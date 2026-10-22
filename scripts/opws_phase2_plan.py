"""OPWS R1 Phase 2 — zero-outcome scope validation + five-field physical-execution dedup plan.

Deterministic, read-only planning over frozen evidence. This module:

* Never executes OPWS, never calls a model API, never samples any arm scope, never
  materializes git diffs, and never writes outside ``research/opws/phase2``.
* Resolves the frozen 12-arm registry (``OPWS_ARM_REGISTRY_R1.json`` at the frozen
  protocol commit) and validates the frozen per-arm scope sources that ALREADY EXIST
  on disk (presence + SHA-256 + per-task coverage over the 219 READY tasks).
* Computes the canonical SCOPE_HASH per (arm, task) **only from pre-existing frozen
  artifacts** (MAIN_297 prediction files, gold proxies, per-task candidate universes).
  No selector output is ever generated; ``RANDOM_SIZE_MATCHED_RM_CSS`` has NO stored
  per-task artifact and its scope hashes are recorded as ``UNRESOLVED_PENDING_PHASE4``.
* Produces the five-field physical-execution identity
  ``(TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID)``,
  counts logical arm-records and provable unique physical executions (scope-level dedup),
  and records unresolved dependencies, resource estimates, and future gates.

Usage
-----
    python scripts/opws_phase2_plan.py --check --created-at 2026-10-20T10:00:00Z
    python scripts/opws_phase2_plan.py --created-at 2026-10-20T10:00:00Z
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_BOOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_BOOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_BOOT))

from scripts import opws_build as ob  # noqa: E402

PROJECT = ob.PROJECT
PHASE2_DIR = PROJECT / "research" / "opws" / "phase2"

# frozen arm order (source: OPWS_ARM_REGISTRY_R1.json -> arm_id_uniqueness.arm_order)
FROZEN_ARM_ORDER = [
    "RM_CSS",
    "AGENT",
    "AGENTLESS_STYLE_ADAPTATION",
    "SIP",
    "DENSE_K3",
    "DENSE_K10",
    "BM25_K3",
    "BM25_K10",
    "BM25_TO_CIA_1HOP",
    "SELECT_ALL",
    "RANDOM_SIZE_MATCHED_RM_CSS",
    "GOLD",
]
FROZEN_RANDOM_SEED = 20261012
FROZEN_REGISTRY_START_HASH = "83399ff875c7793286d66311afb6c62071ea04b3"
DEDUP_FIVE_FIELDS = (
    "TASK_ID",
    "SCOPE_HASH",
    "REFERENCE_PATCH_HASH",
    "TEST_CONTRACT_HASH",
    "ENVIRONMENT_ID",
)

UNRESOLVED_REF_PATCH = "UNRESOLVED_PENDING_PATCH_MATERIALIZATION"
UNRESOLVED_RANDOM_SCOPE = "UNRESOLVED_PENDING_PHASE4_RANDOM_SAMPLING"
UNRESOLVED_ELIGIBLE = ob.UNRESOLVED_STAGE5
UNRESOLVED_PAIRED = ob.UNRESOLVED_STAGE7

# frozen per-arm scope sources (path relative to PROJECT unless marked "D:", resolver key)
_R2 = "D:/wp2_comp_baselines/research/competitor-baselines-r2/per_task_predictions_r2.json"
ARM_SCOPE_SOURCES: dict[str, dict[str, Any]] = {
    "RM_CSS": {"path": "research/wp1a/sip_rmcss_per_task_predictions.json", "key": "rmcss_predicted_set"},
    "AGENT": {"path": "research/wp1b/main-297-2026-09-22/wp1b_agent_predictions.json", "key": "selected_paths"},
    "AGENTLESS_STYLE_ADAPTATION": {
        "path": "D:/wp2_agentless_main297/research/competitor-agentless-r1/agentless_r1_prediction_freeze.json",
        "key": "prediction_set",
    },
    "SIP": {"path": "research/wp1a/sip_rmcss_per_task_predictions.json", "key": "sip_predicted_set"},
    "DENSE_K3": {"path": _R2, "key": "DENSE@3_selected"},
    "DENSE_K10": {"path": _R2, "key": "DENSE@10_selected"},
    "BM25_K3": {"path": _R2, "key": "BM25@3_selected"},
    "BM25_K10": {"path": _R2, "key": "BM25@10_selected"},
    "BM25_TO_CIA_1HOP": {"path": _R2, "key": "BM25_TO_CIA_1HOP_selected"},
    "SELECT_ALL": {
        "path": "benchmark_data/real_commit_impact_saleor/scientific/<task_id>/public/candidate_universe.json",
        "key": "records.path",
    },
    "RANDOM_SIZE_MATCHED_RM_CSS": {"path": None, "key": None},  # derived at Phase 4; never generated here
    "GOLD": {"path": "research/saleor-reserve-300-rmcss/saleor_reserve_300_proxies.json", "key": "proxies"},
}
# frozen canonical scope-hash definition (OPWS_SCOPE_SEMANTICS_R1.json):
# repository-relative, forward slashes, exact strings as stored; NO absolute
# paths, NO drive prefixes, NO backslash escape ambiguities, NO empty strings,
# NO ``.`` / ``..`` traversal or redundant components, NO aliasing.
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:[\\/]?")
_FORBIDDEN_PATH_COMPONENTS = ("", ".", "..")


def normalize_scope_path(path: Any, *, context: str) -> str:
    """Enforce the frozen repository-relative forward-slash scope-path spelling.

    Raises ``BuildError`` (fail closed) for absolute paths, drive prefixes,
    backslash escape ambiguities, empty strings, and ``.``/``..`` traversal or
    redundant path components. Returns the single canonical repository-relative
    spelling, unchanged (no OS normalization, no case folding, no aliasing).
    """
    if not isinstance(path, str) or path == "":
        raise ob.BuildError(f"{context}: scope path must be a non-empty string, got {path!r}")
    if "\\" in path:
        raise ob.BuildError(
            f"{context}: backslash not allowed in repository-relative scope path: {path!r}"
        )
    if _DRIVE_PREFIX_RE.match(path):
        raise ob.BuildError(
            f"{context}: absolute drive prefix not allowed in repository-relative scope path: {path!r}"
        )
    if path.startswith("/"):
        raise ob.BuildError(
            f"{context}: absolute leading-slash path is not repository-relative: {path!r}"
        )
    for comp in path.split("/"):
        if comp in _FORBIDDEN_PATH_COMPONENTS:
            raise ob.BuildError(
                f"{context}: path component {comp!r} forbidden in repository-relative scope path: {path!r}"
            )
    return path


def normalize_scope_paths(paths: Any, *, context: str) -> tuple[list[str], int]:
    """Validate + dedupe a scope path list.

    Returns ``(sorted unique canonical repository-relative paths, duplicate_count)``.
    Fails closed (``BuildError``) on any invalid path (absolute, drive prefix,
    backslash, empty, ``.``/``..`` component). Exact duplicate spellings are
    removed and counted (frozen ``no_duplicates``); aliasing is never applied.
    """
    if not isinstance(paths, (list, tuple)):
        raise ob.BuildError(
            f"{context}: scope paths must be a list, got {type(paths).__name__}"
        )
    canonical = [normalize_scope_path(p, context=context) for p in paths]
    unique = sorted(set(canonical))
    duplicate_count = len(canonical) - len(unique)
    return unique, duplicate_count


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_canonical_scope_hash(paths: list[str]) -> str:
    """Frozen canonical scope hash (OPWS_SCOPE_SEMANTICS_R1.json).

    Normalize: repository-relative, forward slashes, exact strings as stored;
    fail closed on any invalid path; deduplicate; sort lexicographically (byte
    order). Canonical JSON = ``json.dumps(sorted_list, sort_keys=False)`` with
    ``separators=(",", ":")``; hash input = that canonical JSON encoded UTF-8.
    """
    normalized, _ = normalize_scope_paths(paths, context="scope")
    canonical = json.dumps(normalized, sort_keys=False, ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


# ---------------------------------------------------------------- scope readers
def _universe_file(task_id: str) -> Path:
    return (
        PROJECT
        / "benchmark_data"
        / "real_commit_impact_saleor"
        / "scientific"
        / task_id
        / "public"
        / "candidate_universe.json"
    )


def _to_task_map(records: Any, key_field: str = "task_id") -> dict[str, Any]:
    if isinstance(records, dict):
        return records
    if isinstance(records, list):
        return {str(r[key_field]): r for r in records if key_field in r}
    raise ob.BuildError(f"cannot index scope records of type {type(records).__name__}")


def _load_scope_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_arm_scope_lists(arm_id: str, task_ids: list[str], cache: dict[str, Any]) -> dict[str, list[str]]:
    """Return {task_id: [paths]} for one arm strictly from a pre-existing frozen artifact.

    Raises BuildError if the artifact is missing or a READY task lacks a record
    (fail-closed; empty list is a VALID zero-size scope and is kept as such).
    """
    if arm_id not in ARM_SCOPE_SOURCES:
        raise ob.BuildError(f"{arm_id}: unknown arm id; not in the frozen 12-arm registry")
    src = ARM_SCOPE_SOURCES[arm_id]
    if src["path"] is None:
        raise ob.BuildError(f"{arm_id}: no stored per-task artifact; must never be generated in Phase 2")

    if arm_id == "SELECT_ALL":
        universe_scope: dict[str, list[str]] = {}
        for tid in task_ids:
            ufile = _universe_file(tid)
            if not ufile.exists():
                raise ob.BuildError(f"SELECT_ALL: candidate universe missing for {tid}")
            u = json.loads(ufile.read_text(encoding="utf-8"))
            universe_scope[tid] = [r["path"] for r in u.get("records", []) if r.get("path")]
        return universe_scope

    path = Path(src["path"]) if not src["path"].startswith("D:/") else Path(src["path"])
    if cur := cache.get(str(path)):
        data = cur
    else:
        if not path.exists():
            raise ob.BuildError(f"{arm_id}: frozen scope source missing: {path}")
        data = _load_scope_file(path)
        cache[str(path)] = data

    per_task: dict[str, list[str]] = {}
    if arm_id == "GOLD":
        proxies = data.get("proxies") if isinstance(data, dict) else data
        for tid in task_ids:
            val = proxies.get(tid) if isinstance(proxies, dict) else None
            if val is None:
                raise ob.BuildError(f"GOLD: proxies missing task {tid}")
            per_task[tid] = list(val)
        return per_task

    # keyed prediction artifacts
    records = data.get("per_task", data.get("records", data))
    recs = _to_task_map(records)
    for tid in task_ids:
        rec = recs.get(tid)
        if rec is None:
            raise ob.BuildError(f"{arm_id}: frozen prediction record missing for {tid}")
        key = str(src["key"])
        val = rec.get(key)
        if val is None:
            raise ob.BuildError(f"{arm_id}: record for {tid} lacks '{key}'")
        per_task[tid] = [str(p) for p in val]
    return per_task


# ---------------------------------------------------------------- loaders
def load_arm_registry() -> dict[str, Any]:
    blob = ob.git_bytes("cat-file", "blob", f"{ob.PROTOCOL_COMMIT}:{ob.PROTOCOL_DIR}/OPWS_ARM_REGISTRY_R1.json")
    reg: dict[str, Any] = json.loads(blob.decode("utf-8"))
    order = reg.get("arm_id_uniqueness", {}).get("arm_order")
    if order != FROZEN_ARM_ORDER:
        raise ob.BuildError(
            f"ARM REGISTRY arm_order mismatch: frozen={FROZEN_ARM_ORDER} registry={order}"
        )
    arms = [a["arm_id"] for a in reg.get("arms", [])]
    if sorted(arms) != sorted(FROZEN_ARM_ORDER) or len(set(arms)) != 12:
        raise ob.BuildError(f"ARM REGISTRY must contain exactly the 12 frozen arms: {arms}")
    if reg.get("registry_start_hash") != FROZEN_REGISTRY_START_HASH:
        raise ob.BuildError("ARM REGISTRY registry_start_hash mismatch")
    if reg.get("constants", {}).get("RANDOM_SEED") != FROZEN_RANDOM_SEED:
        raise ob.BuildError("ARM REGISTRY RANDOM_SEED mismatch")
    return reg


def load_binding(binding_dir: Path) -> dict[str, Any]:
    """Read the frozen Phase-1 binding artifacts (never regenerated here)."""
    ordered = json.loads((binding_dir / "OPWS_ORDERED_TASK_IDS.json").read_text(encoding="utf-8"))
    env = json.loads((binding_dir / "OPWS_ENVIRONMENT_ID_PROPOSAL.json").read_text(encoding="utf-8"))
    manifest = json.loads((binding_dir / "OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json").read_text(encoding="utf-8"))
    task_ids = ordered["ordered_task_ids"] if isinstance(ordered, dict) and "ordered_task_ids" in ordered else ordered
    if not isinstance(task_ids, list) or len(task_ids) != ob.EXPECTED_N_TASKS:
        raise ob.BuildError("ordered task ids must be the frozen 219-task list")

    env_by_task = {r["task_id"]: r["environment_id"] for r in env["per_task"]}
    contract_by_task = {r["task_id"]: r["contract_sha256"] for r in manifest["per_task"]}
    f2p_positive: set[str] = set()
    for r in manifest["per_task"]:
        if (r.get("f2p") or {}).get("total", 0) > 0:
            f2p_positive.add(r["task_id"])

    for tid in task_ids:
        if tid not in env_by_task or tid not in contract_by_task:
            raise ob.BuildError(f"binding lookup missing for {tid}")
    return {
        "task_ids": task_ids,
        "env_by_task": env_by_task,
        "contract_by_task": contract_by_task,
        "f2p_positive": sorted(f2p_positive),
        "n_f2p_positive": len(f2p_positive),
    }


def load_wall_s() -> dict[str, float]:
    """Per-task frozen eval wall seconds (per_task_v2.jsonl) for resource estimates."""
    out: dict[str, float] = {}
    for line in ob.PER_TASK_V2.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "wall_s" in r:
            out[str(r["task_id"])] = float(r["wall_s"])
    return out


# ---------------------------------------------------------------- plan build
def build_validation(task_ids: list[str]) -> dict[str, Any]:
    scope_cache: dict[str, Any] = {}
    per_arm: list[dict[str, Any]] = []
    for arm_id in FROZEN_ARM_ORDER:
        src = ARM_SCOPE_SOURCES[arm_id]
        entry: dict[str, Any] = {"arm_id": arm_id, "scope_source": src["path"]}
        if src["path"] is None:
            # frozen rule: RANDOM_SIZE_MATCHED_RM_CSS is the founder arm that is explicitly
            # deferred (derived at Phase 4, seed 20261012; never generated in Phase 2).
            entry.update(
                {
                    "stored_artifact": False,
                    "resolve_mode": "DERIVED_PENDING_PHASE4",
                    "never_generated_in_phase2": True,
                    "coverage": {"n": 0, "of": len(task_ids), "missing": []},
                }
            )
            per_arm.append(entry)
            continue
        if arm_id == "SELECT_ALL":
            missing = [
                t
                for t in task_ids
                if not _universe_file(t).exists()
            ]
            if missing:
                # FAIL CLOSED: SELECT_ALL is derived from per-task candidate universes; a
                # missing universe for any READY task is a hard source failure.
                raise ob.BuildError(
                    f"SELECT_ALL: candidate universe missing for {len(missing)} task(s): {missing[:5]}"
                )
            entry.update(
                {
                    "stored_artifact": True,
                    "resolve_mode": "FROZEN_ARTIFACT",
                    "coverage": {"n": len(task_ids), "of": len(task_ids), "missing": []},
                    "source_sha256": "per-task candidate_universe files; hashed per task in plan",
                    "n_distinct_scope_hashes": None,
                }
            )
            per_arm.append(entry)
            continue
        path = Path(src["path"])
        if not path.exists():
            # FAIL CLOSED: a missing frozen scope source for a stored-artifact arm is a
            # hard failure; it must NOT be silently downgraded to a SOURCE_MISSING/
            # generic-UNRESOLVED group.
            raise ob.BuildError(f"{arm_id}: frozen scope source missing: {path}")
        # FAIL CLOSED: resolve_arm_scope_lists must complete for every READY task, and
        # every scope path must satisfy the frozen canonical repository-relative rule
        # (compute_canonical_scope_hash re-raises BuildError on any invalid path).
        lists = resolve_arm_scope_lists(arm_id, task_ids, scope_cache)
        source_sha = ob.file_sha256(path)
        # per-arm source sha256 (arm may share a file with another arm; record per arm)
        hashes = {tid: compute_canonical_scope_hash(v) for tid, v in lists.items()}
        scope_hash_set = set(hashes.values())
        per_arm.append(
            {
                "arm_id": arm_id,
                "scope_source": src["path"],
                "stored_artifact": True,
                "resolve_mode": "FROZEN_ARTIFACT",
                "source_sha256": source_sha,
                "coverage": {"n": len(lists), "of": len(task_ids), "missing": []},
                "n_distinct_scope_hashes": len(scope_hash_set),
                "n_empty_scopes": sum(1 for v in lists.values() if not v),
            }
        )
    return {
        "artifact": "opws_scope_validation_r1",
        "schema_version": "opws-scope-validation-r1/1.0-additive",
        "mission": "M17_OPWS_R1_PHASE2_SCOPE_DEDUP",
        "zero_outcome": {
            "no_arm_execution": True,
            "no_model_api": True,
            "no_selector_output_generated": True,
            "no_patch_materialization": True,
            "no_gold_inspection_beyond_frozen_path_lists": True,
        },
        "registry": {
            "protocol_commit": ob.PROTOCOL_COMMIT,
            "protocol_tag": ob.PROTOCOL_TAG,
            "registry_start_hash": FROZEN_REGISTRY_START_HASH,
            "random_seed": FROZEN_RANDOM_SEED,
            "n_arms": 12,
            "arm_order": FROZEN_ARM_ORDER,
            "dedup_five_fields": list(DEDUP_FIVE_FIELDS),
        },
        "population": {
            "n_tasks": len(task_ids),
            "ordered_task_ids_sha256": ob.ordered_task_ids_sha256(task_ids),
        },
        "per_arm": per_arm,
    }


def build_dedup_plan(validation: dict[str, Any], binding: dict[str, Any], created_at: str) -> dict[str, Any]:
    task_ids = binding["task_ids"]
    env_by_task = binding["env_by_task"]
    contract_by_task = binding["contract_by_task"]
    scope_cache: dict[str, Any] = {}

    # resolve per-task scope hashes for every arm with a stored artifact
    resolved: dict[str, dict[str, str]] = {}
    unresolved_arms: dict[str, list[str]] = {}  # arm_id -> task_ids that share the arm
    for arm_id in FROZEN_ARM_ORDER:
        if arm_id == "RANDOM_SIZE_MATCHED_RM_CSS":
            # frozen rule: this arm is derived at Phase 4 (seed 20261012); it has no
            # stored per-task artifact and must NEVER be generated in Phase 2. It is the
            # ONLY arm permitted to be explicitly deferred.
            unresolved_arms[arm_id] = list(task_ids)
            continue
        # FAIL CLOSED: every other frozen arm must resolve from its pre-existing scope
        # artifact. A missing/invalid source or per-task record (or a non-canonical
        # scope path rejected by compute_canonical_scope_hash) raises BuildError and
        # propagates; it is never silently downgraded to a generic UNRESOLVED group.
        lists = resolve_arm_scope_lists(arm_id, task_ids, scope_cache)
        for tid, paths in lists.items():
            resolved.setdefault(tid, {})[arm_id] = compute_canonical_scope_hash(paths)

    # five-field identity availability per task
    tasks: list[dict[str, Any]] = []
    for tid in task_ids:
        arms_hashes = resolved.get(tid, {})
        # physical groups: arms with identical known scope hash collapse (same task ->
        # identical scoped-gold patch, task-level test contract + environment constants)
        groups: dict[str, dict[str, Any]] = {}
        for arm_id, sh in arms_hashes.items():
            groups.setdefault(f"known:{sh}", {"scope_hash": sh, "arm_ids": [], "n_arm_records": 0})
            groups[f"known:{sh}"]["arm_ids"].append(arm_id)
            groups[f"known:{sh}"]["n_arm_records"] += 1
        for arm_id in unresolved_arms:
            groups.setdefault(f"unresolved:{arm_id}", {
                "scope_hash": UNRESOLVED_RANDOM_SCOPE, "arm_ids": [arm_id], "n_arm_records": 1,
            })
        tasks.append(
            {
                "task_id": tid,
                "n_known_arm_records": len(arms_hashes),
                "n_unresolved_arm_records": len(unresolved_arms),
                "n_logical_arm_records": len(arms_hashes) + len(unresolved_arms),
                "n_physical_groups": len(groups),
                "n_known_distinct_scope_hashes": len(set(arms_hashes.values())),
                "test_contract_hash": contract_by_task[tid],
                "environment_id": env_by_task[tid],
                "reference_patch_hash": UNRESOLVED_REF_PATCH,
            }
        )

    n_logical = sum(t["n_logical_arm_records"] for t in tasks)
    n_physical = sum(t["n_physical_groups"] for t in tasks)
    n_known_hash_records = sum(t["n_known_arm_records"] for t in tasks)
    n_unresolved = sum(t["n_unresolved_arm_records"] for t in tasks)

    # resource estimate from frozen wall_s over the F2P-positive candidate subset
    wall = load_wall_s()
    wall_candidates = [wall.get(t, 0.0) for t in binding["f2p_positive"]]
    sum_wall_f2p_h = sum(wall_candidates) / 3600.0

    # primary pair (RM_CSS, AGENT) counts
    pair = ("RM_CSS", "AGENT")
    pair_logical = 0
    pair_physical = 0
    for tid in task_ids:
        known = resolved.get(tid, {})
        pair_arms = [a for a in pair if a in known] + [a for a in pair if a in unresolved_arms]
        if not pair_arms:
            continue
        pair_logical += len(pair_arms)
        pair_physical += len({(known.get(a) if a in known else UNRESOLVED_RANDOM_SCOPE) for a in pair_arms})

    return {
        "artifact": "opws_physical_dedup_plan_r1",
        "schema_version": "opws-physical-dedup-plan-r1/1.0-additive",
        "mission": "M17_OPWS_R1_PHASE2_SCOPE_DEDUP",
        "created_at": created_at,
        "population": {
            "n_tasks": len(task_ids),
            "n_f2p_positive_candidate": binding["n_f2p_positive"],
            "n_opws_eligible": UNRESOLVED_ELIGIBLE,
            "n_primary_paired": UNRESOLVED_PAIRED,
        },
        "five_field_physical_identity": {
            "fields": list(DEDUP_FIVE_FIELDS),
            "note": (
                "All five fields must be equal before two logical arm records may share "
                "one physical OPWS execution (OPWS_EXECUTION_REUSE_DEDUP_R1.json)."
            ),
        },
        "field_availability": {
            "TASK_ID": "KNOWN_ALL",
            "SCOPE_HASH": (
                "KNOWN_FOR_STORED_ARTIFACT_ARMS; UNRESOLVED for "
                "RANDOM_SIZE_MATCHED_RM_CSS (never generated in Phase 2)"
            ),
            "REFERENCE_PATCH_HASH": UNRESOLVED_REF_PATCH,
            "TEST_CONTRACT_HASH": "KNOWN_ALL (frozen behavior contract manifest)",
            "ENVIRONMENT_ID": "KNOWN_ALL (frozen environment-id proposal)",
        },
        "execution_order": {
            "principle": "task-major",
            "within_task": "unique canonical scopes ordered deterministically by scope_hash; logical-arm mapping",
            "zero_ordering_inputs_from_outcomes": True,
        },
        "counts": {
            "n_logical_arm_records": n_logical,
            "n_known_scope_hash_records": n_known_hash_records,
            "n_unresolved_scope_records": n_unresolved,
            "n_unique_physical_executions": n_physical,
            "dedup_reduction_records": n_logical - n_physical,
            "primary_pair": {"arms": list(pair), "n_logical": pair_logical, "n_unique_physical": pair_physical},
            "per_arm_scope_sources_resolved": sum(1 for a in validation["per_arm"] if a.get("stored_artifact")),
            "per_arm_scope_sources_unresolved": sum(1 for a in validation["per_arm"] if not a.get("stored_artifact")),
        },
        "unresolved_dependencies": [
            {
                "field": "REFERENCE_PATCH_HASH",
                "status": UNRESOLVED_REF_PATCH,
                "required": (
                    "git-object scoped gold diff (parent->target restricted to scope) "
                    "materialization at Phase 3/4"
                ),
            },
            {
                "field": "SCOPE_HASH (RANDOM_SIZE_MATCHED_RM_CSS)",
                "status": UNRESOLVED_RANDOM_SCOPE,
                "required": "frozen deterministic sampling (seed 20261012) at Phase 4; never generated in Phase 2",
            },
            {
                "field": "n_opws_eligible",
                "status": UNRESOLVED_ELIGIBLE,
                "required": "STAGE_5 behavior-contract preflight (Phase 3)",
            },
            {
                "field": "n_primary_paired",
                "status": UNRESOLVED_PAIRED,
                "required": "STAGE_7 paired eligibility (Phase 5)",
            },
        ],
        "resource_estimates": {
            "raw_eval_hours_over_f2p_positive_candidates": round(sum_wall_f2p_h, 3),
            "frozen_source": "sum(wall_s) over the 83 F2P-positive candidate tasks (per_task_v2.jsonl)",
            "upper_bound_all_12_arms_no_dedup_hours": round(sum_wall_f2p_h * 12.0, 3),
            "overhead_factor": [1.25, 1.40],
            "scope_dedup_effective_hours_unknown_pending_eligibility": UNRESOLVED_ELIGIBLE,
            "disk_gate_gib_free": "UNKNOWN (B5: >=40 GiB or relocate Docker root; C: 30.9 GiB at Phase-1 record)",
        },
        "future_gates": [
            "G1 - STAGE_5 behavior-contract preflight (Phase 3) resolves n_opws_eligible",
            "G2 - REFERENCE_PATCH_HASH materialization (Phase 3/4) resolves the 5th field for final physical mapping",
            "G3 - RANDOM_SIZE_MATCHED_RM_CSS sampling (Phase 4, seed 20261012) resolves its scope hashes",
            "G4 - STAGE_7 paired eligibility (Phase 5) resolves n_primary_paired",
            "G5 - disk >=40 GiB (B5) before any arm run",
        ],
        "zero_outcome": {
            "no_arm_execution": True,
            "no_model_api": True,
            "no_selector_output_generated": True,
            "no_patch_materialization": True,
            "scope_hashes_only_from_pre_existing_frozen_artifacts": True,
        },
        "tasks": tasks,
    }


def build_all(*, created_at: str) -> dict[str, dict[str, Any]]:
    load_arm_registry()  # validates the frozen registry; raises BuildError on mismatch
    binding = load_binding(ob.BUILD_DIR)
    validation = build_validation(binding["task_ids"])
    plan = build_dedup_plan(validation, binding, created_at)
    return {
        "OPWS_SCOPE_VALIDATION_R1.json": validation,
        "OPWS_PHYSICAL_DEDUP_PLAN_R1.json": plan,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def determinism_report(first: dict[str, str], second: dict[str, str]) -> dict[str, Any]:
    entries = []
    for name in first:
        a = sha256_bytes(first[name].encode("utf-8"))
        b = sha256_bytes(second[name].encode("utf-8"))
        entries.append(
            {
                "artifact": name,
                "run1_sha256": a,
                "run2_sha256": b,
                "identical": a == b and first[name] == second[name],
            }
        )
    return {
        "artifact": "opws_phase2_determinism",
        "schema_version": "opws-phase2-determinism/1.0-additive",
        "n_artifacts": len(entries),
        "all_identical": all(e["identical"] for e in entries),
        "artifacts": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPWS R1 Phase 2 scope validation + physical dedup plan (read-only).")
    parser.add_argument("--out-dir", default=str(PHASE2_DIR), help="output directory (default: research/opws/phase2)")
    parser.add_argument(
        "--created-at",
        default=os.environ.get("OPWS_PHASE2_CREATED_AT") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="UTC ISO timestamp recorded in the plan; pass a fixed value for byte-deterministic rebuilds",
    )
    parser.add_argument("--check", action="store_true", help="build twice and verify byte-determinism; write nothing")
    args = parser.parse_args(argv)

    first_payloads = build_all(created_at=args.created_at)
    first = {name: render(payload) for name, payload in first_payloads.items()}
    second_payloads = build_all(created_at=args.created_at)
    second = {name: render(payload) for name, payload in second_payloads.items()}
    determinism = determinism_report(first, second)
    first["OPWS_PHASE2_DETERMINISM.json"] = render(determinism)

    if args.check:
        print(json.dumps({"all_identical": determinism["all_identical"], "artifacts": determinism["n_artifacts"]}))
        return 0 if determinism["all_identical"] else 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in first.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")

    plan = first_payloads["OPWS_PHYSICAL_DEDUP_PLAN_R1.json"]
    print(
        json.dumps(
            {
                "n_logical_arm_records": plan["counts"]["n_logical_arm_records"],
                "n_unique_physical_executions": plan["counts"]["n_unique_physical_executions"],
                "dedup_reduction_records": plan["counts"]["dedup_reduction_records"],
                "n_f2p_positive_candidate": plan["population"]["n_f2p_positive_candidate"],
                "n_opws_eligible": plan["population"]["n_opws_eligible"],
                "all_identical": determinism["all_identical"],
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0 if determinism["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
