"""M19A2-ATOMIC1 — deterministic execution-CANDIDATE registry (NOT an execution scheduler).

Mission-scope boundary (asserted in every emitted candidate):
  * candidate-only: every candidate is ``PROVISIONAL_NOT_EXECUTABLE`` and
    ``executable=false`` forever in this artifact; nothing here authorizes physical
    execution or experimental reuse of behavioral outcomes.
  * ``REAL_TASK_BEHAVIORAL_OUTCOMES = 0``: this registry is built purely from frozen
    construction-plan identities; NO pytest/behavioral run backs any record.
  * ENVIRONMENT_ID is the frozen *proposal* value (``OPWS_ENVIRONMENT_ID_PROPOSAL.json``,
    status PROPOSED_PENDING_OWNER_CONFIRMATION); runtime verification is PENDING.
  * F2P node identities are NOT frozen in-repo for all 219 tasks (only 29/219 committed
    in ``research/wp2/harness_v3_2026-09-26/phase5_c4v3_*.json``); node sets are resolved
    at evaluation by the frozen resolver (owner decision B3) and fail-closed on missing
    nodes. True frozen zero-F2P tasks (``f2p.total == 0``, 136) are recorded separately
    from ``NODE_IDS_PENDING_EXACT_VERIFICATION`` (83). No missing node ID is invented.
  * STAGE_5/6/7 eligibility and missing test-import strata evidence remain unresolved;
    this registry does not resolve them and never claims it does.

Frozen identity semantics (reused verbatim, never redefined):
  Five-field physical-execution identity ``OPWS_EXECUTION_REUSE_DEDUP_R1``:
  ``(TASK_ID, SCOPE_HASH, REFERENCE_PATCH_HASH, TEST_CONTRACT_HASH, ENVIRONMENT_ID)``.
  Two logical records may share one physical execution ONLY when all five fields are
  equal. All five fields are taken from the frozen authorities (the approved plan and
  the frozen binding artifacts); hashes are NOT recomputed here.

  Frozen functions/constants imported from ``opws_phase3b_patch_materialize``:
  ``PHYSICAL_IDENTITY_FIELDS``, ``plan_physical_dedup``, ``physical_execution_identity``,
  ``sha256_bytes``, ``_canonical_json`` — used verbatim (import-only, no behavior
  change, no frozen-contract edit).

Exact byte serialization and hash recipes (deterministic; documented):
  S1 identity-key bytes:
    ``json.dumps([identity[f] for f in PHYSICAL_IDENTITY_FIELDS], sort_keys=False,
    ensure_ascii=False, separators=(",",":"))`` — the frozen R1 serializer (same string
    the frozen ``plan_physical_dedup`` builds). Serializer identity is unambiguous: the
    frozen field order is fixed and ``sort_keys=False`` keeps it.
  H1 physical_execution_id (per candidate, frozen recipe):
    ``sha256(S1 bytes)`` via frozen ``physical_execution_identity``.
  H2 candidate_sha256 (content hash of one emitted candidate record):
    ``sha256(utf8(json.dumps(record_without_self_hash, sort_keys=True, ensure_ascii=False,
    separators=(",",":"))))`` — unit-level hash over the deterministic emitted record.
  H3 task_group_sha256:
    ``sha256(utf8(json.dumps(sorted(candidate_sha256s_of_task), sort_keys=True,
    ensure_ascii=False, separators=(",",":"))))`` — task-level hash.
  H4 aggregate_sha256:
    ``sha256(utf8(json.dumps([task_group_sha256 in canonical task-major order],
    sort_keys=False, ensure_ascii=False, separators=(",",":"))))`` — registry-level hash.
  H4 is a registry fingerprint ONLY; it is NEVER a TEST_CONTRACT_HASH and the
  reconciliation asserts it is distinct from every frozen ``TEST_CONTRACT_HASH``.

Ordering: task-major (``OPWS_ORDERED_TASK_IDS.json`` order); within a task, frozen arm
order (the 13 COMPLETE arms; RANDOM_SIZE_MATCHED_RM_CSS is DEFERRED and emits no
records). No ordering input ever derives from a behavioral outcome (there are none).
Effective tree OID is informational provenance only and is never an execution key;
equal source trees are not equated with equal contracts.

Fail-closed rules: missing/empty identity fields, missing ENVIRONMENT_ID, unknown task
id, non-OK ``status`` (WARN/ERROR/PARTIAL are rejected, never counted as OK), a failing
tree-receipt gate, or any measure-goal mismatch => reconciliation fails, a failure
receipt (carrying every individual failure) is the only artifact written, and no
``PHYSICAL_EXECUTION_PLAN_2554.json`` is produced.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make the repo's ``scripts`` package importable both as ``python scripts/....py`` and
# as a test-imported module (the run-time directory of a direct script launch is
# ``scripts/``, not the repo root).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# -------------------------------------------------------------------------------- frozen reuse
from scripts import opws_phase3b_patch_materialize as _mat  # noqa: E402 (sys.path bootstrap above)

sha256_bytes = _mat.sha256_bytes
_canonical_json = _mat._canonical_json
PHYSICAL_IDENTITY_FIELDS = _mat.PHYSICAL_IDENTITY_FIELDS
plan_physical_dedup = _mat.plan_physical_dedup
physical_execution_identity = _mat.physical_execution_identity

# ------------------------------------------------------------------------ pinned authorities

PLAN_SHA256_PIN = "62ef73588d302553596b9eb6161f03df5a4fe0df4c131390a9b61138754ac401"

# SHA-256 pins independently verified in the M19A2-ATOMIC0 discovery report (§3.2 / §2.1);
# all match the frozen authority table.
INPUT_SHA256_PINS: dict[str, str] = {
    "plan": PLAN_SHA256_PIN,
    "ordered_task_ids": "9cb18a3eceb849cef7edda42655a910c4bfe00c727767f77773c49fa4bfe3b8f",
    "environment_id_proposal": "94859d48e7040547d1cc92fc6868056246b4082d302cc47052059dfd58bac2cc",
    "contract_manifest": "5bd64af020caae5cca495aad31221411f87f347841a728452a0a2d3ee63cd064",
    "tree_receipt": "2b433b3d86f9e9d96d21db56949baf498ab8f26482293c8132194138533f729b",
}

# Frozen canonical COMPLETE-arm order (discovery §5.3); RANDOM_SIZE_MATCHED_RM_CSS is
# DEFERRED by design (no stored per-task artifact; must never be generated in Phase 2).
COMPLETE_ARM_ORDER_219: tuple[str, ...] = (
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
    "GOLD",
    "NEG",
    "FULL_REFERENCE",
)

# Approved / known measure goals for the real 219×13 input: 219 tasks, 13 complete
# arms, 2847 logical records, 2554 unique five-field identities (candidates),
# 136 true-zero-F2P tasks, 83 node-pending tasks, 131 distinct ENVIRONMENT_IDs,
# zero missing logical mappings, zero duplicate candidate ids.
MEASURE_GOALS: dict[str, int] = {
    "n_tasks": 219,
    "n_complete_arms": 13,
    "n_logical_records": 2847,
    "n_candidates": 2554,
    "n_true_zero_node_tasks": 136,
    "n_node_pending_tasks": 83,
    "n_distinct_environment_ids": 131,
    "n_missing_logical_mappings": 0,
    "n_duplicate_candidate_ids": 0,
}

UNRESOLVED_SCIENCE_GATES: tuple[str, ...] = (
    "funnel STAGE_5 behavior-executable preflight: 219/219 UNRESOLVED",
    "STAGE_6 n_opws_eligible: 83 unresolved / 136 false; STAGE_7 n_primary_paired: 83 unresolved / 136 false",
    "ENVIRONMENT_ID: proposal only (PROPOSED_PENDING_OWNER_CONFIRMATION), runtime verification pending",
    "F2P node identities: not frozen in-repo for all 219 tasks (29/219 committed); node sets resolved "
    "at evaluation per owner decision B3 with fail-closed count binding",
    "missing test-import strata evidence: no frozen static-import analysis source exists",
)

SCHEMA = "opws-m19a2-candidate-registry/1.0"
ARTIFACT = "PHYSICAL_EXECUTION_PLAN_2554"
PLAN_FILENAME = "PHYSICAL_EXECUTION_PLAN_2554.json"
RECEIPT_FILENAME = "M19A2_EXTRACTOR_RECEIPT.json"
REPORT_FILENAME = "M19A2_ATOMIC1_IMPLEMENTATION_REPORT.md"
FAILURE_RECEIPT_FILENAME = "M19A2_EXTRACTOR_FAILURE_RECEIPT.json"

IDENTITY_KEY_RECIPE = (
    "identity_key = json.dumps([identity[f] for f in PHYSICAL_IDENTITY_FIELDS], "
    "sort_keys=False, ensure_ascii=False, separators=(',', ':'))"
)
PHYSICAL_EXECUTION_ID_RECIPE = "physical_execution_id = sha256(utf8(identity_key))"
CANDIDATE_SHA_RECIPE = (
    "candidate_sha256 = sha256(utf8(json.dumps(record_without_self_hash, "
    "sort_keys=True, ensure_ascii=False, separators=(',', ':'))))"
)
TASK_GROUP_SHA_RECIPE = (
    "task_group_sha256 = sha256(utf8(json.dumps(sorted(candidate_sha256s_of_task), "
    "sort_keys=True, ensure_ascii=False, separators=(',', ':'))))"
)
AGGREGATE_SHA_RECIPE = (
    "aggregate_sha256 = sha256(utf8(json.dumps([task_group_sha256 in canonical task-major "
    "order], sort_keys=False, ensure_ascii=False, separators=(',', ':'))))"
)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_str(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def load_json_file(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        data: Any = json.load(fh)
        if not isinstance(data, dict):
            raise ExtractError(f"{path}: expected a JSON object")
        return data


# ------------------------------------------------------------------ read-only repo metadata

def _git_lines(cwd: Path, *args: str) -> tuple[list[str], bool]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            return [], False
        return [ln for ln in proc.stdout.splitlines() if ln != ""], True
    except (OSError, subprocess.SubprocessError):
        return [], False


def repo_metadata(repo_root: Path | None) -> dict[str, Any]:
    if repo_root is None or not Path(repo_root).is_dir():
        return {"repo_root": None, "repo_head": None, "changed_files": [], "git_ok": False}
    lines, ok = _git_lines(Path(repo_root), "rev-parse", "HEAD")
    head = lines[0] if ok and lines else None
    changed: list[str] = []
    st_lines, sok = _git_lines(Path(repo_root), "status", "--porcelain", "--untracked-files=normal")
    if sok:
        changed = st_lines
    return {
        "repo_root": str(repo_root),
        "repo_head": head,
        "head_resolved": ok,
        "changed_files": changed,
        "git_ok": ok or sok,
    }


# ------------------------------------------------------------------- input verification

class ExtractError(Exception):
    """Structural input error; the CLI renders a failure receipt (fail-closed)."""


class ReconciliationError(ExtractError):
    """Reconciliation failed; carries every individual failure for the receipt."""

    def __init__(self, message: str, failures: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.failures = list(failures)


def verify_input_hashes(paths: dict[str, Path]) -> dict[str, Any]:
    """Byte-verify the pinned frozen authorities (fail-closed on any mismatch)."""
    verified: dict[str, Any] = {}
    for name, path in paths.items():
        pin = INPUT_SHA256_PINS.get(name)
        if path is None or not Path(path).is_file():
            raise ExtractError(f"{name}: input path missing")
        actual = sha256_file(Path(path))
        match = pin is not None and actual == pin
        verified[name] = {
            "path": str(path),
            "sha256": actual,
            "pinned_sha256": pin,
            "match": match,
        }
        if not match:
            raise ExtractError(
                f"{name} hash mismatch: expected={pin} actual={actual} path={path}"
            )
    return verified


# --------------------------------------------------------------------- pure registry builder

def _recon(failures: list[dict[str, str]], code: str, detail: str) -> None:
    failures.append({"code": code, "detail": detail})


def _arm_index(arm_id: str, arm_sequence: tuple[str, ...]) -> int:
    return arm_sequence.index(arm_id)


def _f2p_status(manifest_task: dict[str, Any]) -> dict[str, Any]:
    f2p: dict[str, Any] = manifest_task.get("f2p") or {}
    try:
        behavioral = int(f2p.get("behavioral") or 0)
        symbol_absence = int(f2p.get("symbol_absence") or 0)
    except (TypeError, ValueError):
        behavioral = symbol_absence = -1
    total = behavioral + symbol_absence
    if total < 0:
        raise ExtractError(
            f"task {manifest_task['task_id']}: invalid frozen f2p counts "
            f"(behavioral={f2p.get('behavioral')!r} symbol_absence={f2p.get('symbol_absence')!r})"
        )
    if total == 0:
        status = "TRUE_ZERO_NODE"
        detail = (
            "frozen oracle counts give f2p.total == 0 (legitimate zero-F2P case, kept "
            "separate from unresolved identity); no node identity is needed"
        )
    else:
        status = "NODE_IDS_PENDING_EXACT_VERIFICATION"
        detail = (
            "frozen f2p.total > 0 but the per-node identity list is NOT frozen in-repo for "
            "all 219 tasks (29/219 committed); node sets are resolved at evaluation by the "
            "frozen resolver (owner decision B3) and fail-closed when len(node_set) < "
            "frozen_count. Exact node identity verification PENDING."
        )
    return {
        "status": status,
        "detail": detail,
        "f2p_behavioral_frozen_count": behavioral,
        "f2p_symbol_absence_frozen_count": symbol_absence,
        "f2p_total_frozen_count": total,
        "binding_mode": str(f2p.get("node_identity_binding_mode") or "UNKNOWN"),
        "node_identity_rule": str(f2p.get("node_identity_rule") or "UNKNOWN"),
        "node_ids_frozen_in_repo_for_all_tasks": False,
    }


def build_registry_spec(
    *,
    plan: dict[str, Any],
    ordered_task_ids: list[str],
    env_by_task: dict[str, str],
    manifest_by_task: dict[str, dict[str, Any]],
    tree_receipt: dict[str, Any],
    created_at: str,
    input_hashes: dict[str, dict[str, Any]],
    measure_goals: dict[str, int] | None = None,
    arm_sequence: list[str] | None = None,
    require_random_deferred: bool = True,
) -> dict[str, Any]:
    """Build the full candidate-registry specification (pure, no file writes).

    Deterministic and fail-closed: every validated input contributes exactly one
    canonical output; any structural inconsistency raises ``ReconciliationError``
    carrying every individual failure, and the CLI renders a failure receipt instead
    of the plan. ``arm_sequence`` defaults to the frozen 13-arm canonical order and is
    overridable only for synthetic tests (fixtures must not model the real 219 arms).
    """
    goals = dict(MEASURE_GOALS if measure_goals is None else measure_goals)
    arms = tuple(COMPLETE_ARM_ORDER_219) if arm_sequence is None else tuple(arm_sequence)
    failures: list[dict[str, str]] = []

    if int(plan.get("REAL_TASK_BEHAVIORAL_OUTCOMES") or 0) != 0:
        _recon(failures, "BEHAVIORAL_OUTCOMES_PRESENT", "plan declares REAL_TASK_BEHAVIORAL_OUTCOMES != 0")

    # --- task universe ---------------------------------------------------------------
    task_ids = list(ordered_task_ids)
    if len(task_ids) != len(set(task_ids)):
        _recon(failures, "DUPLICATE_TASK_IDS", "ordered_task_ids contains duplicates")
        task_ids = list(dict.fromkeys(task_ids))  # keep first occurrence for membership checks
    task_set = set(task_ids)
    plan_task_ids = {str(r["task_id"]) for r in plan.get("per_task_records") or []}
    for tid in sorted(plan_task_ids - task_set):
        _recon(failures, "UNKNOWN_TASK_ID", f"plan record references task not in ordered set: {tid}")
    for tid in sorted(task_set - plan_task_ids):
        _recon(failures, "TASK_WITHOUT_RECORDS", f"ordered task has no plan records: {tid}")

    # --- arms ------------------------------------------------------------------------
    arm_status = plan.get("arm_status") or []
    arm_by_id = {a.get("arm_id"): a for a in arm_status}
    complete_arms = [
        arm_by_id[a]["arm_id"]
        for a in arms
        if arm_by_id.get(a) and arm_by_id[a].get("coverage_status") == "COMPLETE"
    ]
    if complete_arms != list(arms):
        _recon(
            failures,
            "ARM_ORDER_CHANGED",
            f"complete-arm order differs from configured canonical order: {complete_arms}",
        )
    if require_random_deferred:
        rand = arm_by_id.get("RANDOM_SIZE_MATCHED_RM_CSS")
        if not (rand and rand.get("coverage_status") == "DEFERRED"):
            _recon(
                failures,
                "RANDOM_DEFERRAL_CHANGED",
                "RANDOM_SIZE_MATCHED_RM_CSS not DEFERRED as frozen",
            )

    # --- records (reject WARN/ERROR/PARTIAL; require exactly 1 per task x arm) ---------
    records = plan.get("per_task_records") or []
    seen: set[tuple[str, str]] = set()
    for rec in records:
        pair = (str(rec.get("task_id", "")), str(rec.get("arm_id", "")))
        if rec.get("status") != "OK":
            _recon(failures, "NON_OK_RECORD", f"record {pair} status={rec.get('status')!r} (only OK may count)")
        if rec.get("error_type") or rec.get("invalid_prediction_paths") or rec.get("unresolved_contracts"):
            _recon(failures, "RECORD_HAS_ANOMALY", f"record {pair} carries anomaly fields")
        if pair in seen:
            _recon(failures, "DUPLICATE_RECORD", f"duplicate (task, arm) record {pair}")
        seen.add(pair)
        for field in ("scope_hash", "reference_patch_sha256", "test_contract_hash", "effective_tree_oid"):
            if not rec.get(field):
                _recon(failures, "EMPTY_FIELD", f"record {pair} empty field {field}")
    expected_pairs = {(t, a) for t in task_set for a in arms}
    for pair in sorted(expected_pairs - seen):
        _recon(failures, "MISSING_RECORD", f"missing plan record for {pair}")
    for pair in sorted(seen - expected_pairs):
        _recon(failures, "UNEXPECTED_RECORD", f"unexpected plan record for {pair}")

    # --- environment + contract cross-checks ---------------------------------------------
    for tid in sorted(task_set):
        if not env_by_task.get(tid):
            _recon(failures, "ENV_UNRESOLVED", f"task {tid} has empty/missing ENVIRONMENT_ID")
    for tid in sorted(set(env_by_task) - task_set):
        _recon(failures, "ENV_UNKNOWN_TASK", f"env entry for unknown task {tid}")

    contract_by_task: dict[str, str] = {}
    for rec in records:
        tid = str(rec["task_id"])
        if tid in contract_by_task and contract_by_task[tid] != str(rec["test_contract_hash"]):
            _recon(failures, "CONTRACT_NONUNIFORM", f"task {tid} spans differing test_contract_hash values")
        contract_by_task.setdefault(tid, str(rec["test_contract_hash"]))
    contract_mismatch: list[str] = []
    for tid in sorted(task_set):
        man_task = manifest_by_task.get(tid)
        if man_task is None:
            _recon(failures, "MANIFEST_TASK_MISSING", f"task {tid} absent from contract manifest")
            continue
        man_contract = man_task.get("contract_sha256")
        if not man_contract:
            _recon(failures, "CONTRACT_UNRESOLVED", f"task {tid} contract unresolved in manifest")
        elif contract_by_task.get(tid) != man_contract:
            contract_mismatch.append(tid)
    if contract_mismatch:
        _recon(
            failures,
            "CONTRACT_CROSSCHECK_MISMATCH",
            "plan test_contract_hash != frozen manifest contract_sha256 for: " + ",".join(contract_mismatch[:5]),
        )

    # --- tree-receipt gate (FULL_REFERENCE requires RECONSTRUCTED parity) ------------------
    if tree_receipt is not None:
        exit_gate = tree_receipt.get("exit_gate") or {}
        statuses = {str(r.get("task_id")): r.get("status") for r in (tree_receipt.get("per_task") or [])}
        bad = [tid for tid in task_ids if statuses.get(tid) != "RECONSTRUCTED"]
        if bad:
            _recon(failures, "TREE_RECEIPT_NOT_RECONSTRUCTED", f"tasks not RECONSTRUCTED: {bad[:5]}")
        if not exit_gate.get("pass"):
            _recon(failures, "TREE_RECEIPT_GATE_FAIL", "tree receipt exit gate not passing")
        parity = plan.get("full_reference_target_tree_parity") or {}
        not_true = [tid for tid in task_ids if parity.get(tid) is not True]
        if not_true:
            _recon(failures, "TREE_PARITY_NOT_TRUE", f"full-reference parity not True: {not_true[:5]}")

    # --- fail-closed before any further processing -------------------------------------------
    if failures:
        raise ReconciliationError("input validation failed (fail-closed)", failures)

    # --- canonical task-major record stream --------------------------------------------------
    rec_by_pair: dict[tuple[str, str], dict[str, Any]] = {
        (str(r["task_id"]), str(r["arm_id"])): r for r in records
    }
    identities: list[dict[str, Any]] = []
    for tid in task_ids:
        for arm in arms:
            rec = rec_by_pair.get((str(tid), arm))
            if rec is None:
                continue  # already flagged as MISSING_RECORD
            identities.append(
                {
                    "TASK_ID": str(tid),
                    "SCOPE_HASH": str(rec["scope_hash"]),
                    "REFERENCE_PATCH_HASH": str(rec["reference_patch_sha256"]),
                    "TEST_CONTRACT_HASH": str(rec["test_contract_hash"]),
                    "ENVIRONMENT_ID": env_by_task[str(tid)],
                    "arm_id": arm,
                    "record_id": f"{arm}:{tid}",
                    "_effective_tree_oid": str(rec["effective_tree_oid"]),
                    "_reference_patch_bytes": int(rec.get("reference_patch_bytes") or 0),
                }
            )

    # --- frozen dedup (verbatim) -----------------------------------------------------------------
    dedup = plan_physical_dedup(identities)

    # --- per-candidate enrichment ------------------------------------------------------------------
    candidates: list[dict[str, Any]] = []
    record_to_candidate: dict[str, str] = {}
    for ordinal, ex in enumerate(dedup["physical_executions"], start=1):
        cid = str(ex["physical_execution_id"])
        if cid in record_to_candidate.values():
            _recon(failures, "DUPLICATE_CANDIDATE_ID", f"duplicate candidate id {cid}")
        identity_fields: dict[str, str] = {str(k): str(v) for k, v in ex["identity_fields"].items()}
        logical_ids = [str(r) for r in ex.get("logical_record_ids") or []]
        logical_arms = [str(r) for r in ex.get("logical_arm_ids") or []]
        if not logical_ids:
            _recon(failures, "EMPTY_CANDIDATE", f"candidate {cid} has zero logical origins")
        for rid in logical_ids:
            record_to_candidate[rid] = cid
        origin_recs = [
            rec_by_pair[(rid.split(":", 1)[1], rid.split(":", 1)[0])]
            for rid in logical_ids
            if len(rid.split(":", 1)) == 2 and (rid.split(":", 1)[1], rid.split(":", 1)[0]) in rec_by_pair
        ]
        oids = {str(r["effective_tree_oid"]) for r in origin_recs}
        if len(oids) != 1:
            _recon(failures, "NONUNIFORM_TREE_OID", f"candidate {cid} spans differing effective tree OIDs")
        pb = {int(r.get("reference_patch_bytes") or 0) for r in origin_recs}
        if len(pb) != 1:
            _recon(failures, "NONUNIFORM_PATCH_BYTES", f"candidate {cid} spans differing reference_patch_bytes")
        min_arm_idx = min(_arm_index(a, arms) for a in logical_arms)
        tid = str(identity_fields["TASK_ID"])
        node_status = _f2p_status(manifest_by_task[tid]) if tid in manifest_by_task else {
            "status": "NODE_IDS_PENDING_EXACT_VERIFICATION",
            "detail": "manifest task absent",
            "f2p_behavioral_frozen_count": 0,
            "f2p_symbol_absence_frozen_count": 0,
            "f2p_total_frozen_count": 0,
            "binding_mode": "UNKNOWN",
            "node_identity_rule": "UNKNOWN",
            "node_ids_frozen_in_repo_for_all_tasks": False,
        }
        candidates.append(
            {
                "ordinal": ordinal,
                "candidate_id": cid,
                "physical_execution_id": cid,
                "synthetic": False,
                "identity_fields": identity_fields,
                "provenance": {
                    "n_logical_origins": len(logical_ids),
                    "logical_record_ids": logical_ids,
                    "logical_arm_ids": logical_arms,
                    "min_arm_index": min_arm_idx,
                },
                "effective_tree_oid": sorted(oids)[0] if oids else None,
                "reference_patch_bytes": sorted(pb)[0] if pb else None,
                "node_identity_status": node_status,
                "execution_status": {
                    "status_code": "PROVISIONAL_NOT_EXECUTABLE",
                    "candidate_only": True,
                    "executable": False,
                    "environment_binding": "PENDING_VALIDATION",
                    "node_identity_verification": node_status["status"],
                    "real_behavioral_test_outcomes": 0,
                    "experimental_reuse_permitted": False,
                    "note": (
                        "candidate registry only, NOT a behavioral execution scheduler; "
                        "no physical execution, no environment binding, no reuse of outcomes"
                    ),
                },
            }
        )

    for (tid, arm) in seen:
        if f"{arm}:{tid}" not in record_to_candidate:
            _recon(failures, "UNMAPPED_RECORD", f"logical record ({tid}, {arm}) maps to no candidate")
    for rid in record_to_candidate:
        parts = rid.split(":", 1)
        if len(parts) != 2 or (parts[1], parts[0]) not in seen:
            _recon(failures, "GHOST_MAPPING", f"candidate mapping points at unknown record {rid}")

    # --- candidate content hashes (H2) ---------------------------------------------------------------
    for candidate in candidates:
        body = {k: v for k, v in candidate.items() if k != "candidate_sha256"}
        candidate["candidate_sha256"] = sha256_str(_canonical_json(body))

    # --- canonical ordering reconciliation -------------------------------------------------------------
    task_position = {tid: i for i, tid in enumerate(task_ids)}
    last_pos = -1
    prev_min_arm = -1
    for candidate in candidates:
        pos = task_position[str(candidate["identity_fields"]["TASK_ID"])]
        if pos < last_pos:
            _recon(failures, "CANDIDATE_TASK_ORDER", "candidate task order is not canonical")
            break
        if pos == last_pos:
            if candidate["provenance"]["min_arm_index"] < prev_min_arm:
                _recon(failures, "WITHIN_TASK_ORDER", "within-task candidate order violates frozen arm order")
                break
        else:
            prev_min_arm = -1
        last_pos = pos
        prev_min_arm = candidate["provenance"]["min_arm_index"]
    if last_pos != len(task_ids) - 1 and candidates:
        _recon(failures, "CANDIDATE_TASK_COVERAGE", "candidates do not cover all canonical tasks")

    # --- task groups + aggregate hashes (H3/H4) -----------------------------------------------------------
    by_task_candidates: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_task_candidates.setdefault(str(candidate["identity_fields"]["TASK_ID"]), []).append(candidate)
    task_groups: list[dict[str, Any]] = []
    for tid in task_ids:
        tcs = by_task_candidates.get(tid, [])
        task_groups.append(
            {
                "task_id": tid,
                "n_candidates": len(tcs),
                "n_logical_origins": sum(int(c["provenance"]["n_logical_origins"]) for c in tcs),
                "candidate_sha256s": [c["candidate_sha256"] for c in tcs],
                "task_group_sha256": sha256_str(_canonical_json(sorted(c["candidate_sha256"] for c in tcs))),
            }
        )
    aggregate_sha = sha256_str(
        json.dumps(
            [g["task_group_sha256"] for g in task_groups],
            sort_keys=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    # --- measure-goal reconciliation --------------------------------------------------------------------
    n_cases: dict[str, int] = {
        "n_tasks": len(task_ids),
        "n_complete_arms": len(complete_arms),
        "n_logical_records": len(records),
        "n_candidates": len(candidates),
        "n_true_zero_node_tasks": sum(
            1 for tid in task_ids if (manifest_by_task.get(tid, {}).get("f2p", {}) or {}).get("total", -1) == 0
        ),
        "n_node_pending_tasks": sum(
            1 for tid in task_ids if ((manifest_by_task.get(tid, {}).get("f2p", {}) or {}).get("total", -1) or 0) > 0
        ),
        "n_distinct_environment_ids": len({str(env_by_task[tid]) for tid in task_ids if tid in env_by_task}),
        "n_missing_logical_mappings": len(seen) - len(record_to_candidate),
        "n_duplicate_candidate_ids": len(candidates) - len({c["candidate_id"] for c in candidates}),
    }
    goal_checks: dict[str, bool] = {
        key: n_cases[key] == goal for key, goal in goals.items() if key in n_cases
    }
    for key, passed in sorted(goal_checks.items()):
        if not passed:
            _recon(
                failures,
                "MEASURE_GOAL_MISMATCH",
                f"goal {key}: expected {goals.get(key)}, observed {n_cases[key]}",
            )
    origin_total = sum(int(c["provenance"]["n_logical_origins"]) for c in candidates)
    goal_checks["n_logical_origins_total"] = origin_total == len(records)
    if origin_total != len(records):
        _recon(failures, "ORIGINS_TOTAL_MISMATCH", f"logical origins total {origin_total} != records {len(records)}")
    goal_checks["n_candidates_with_origin"] = all(int(c["provenance"]["n_logical_origins"]) >= 1 for c in candidates)
    if not goal_checks["n_candidates_with_origin"]:
        _recon(failures, "CANDIDATE_WITHOUT_ORIGIN", "a candidate has zero logical origins")

    # --- registry fingerprint is NOT a frozen TEST_CONTRACT_HASH ---------------------------------------------
    contract_hashes = {str(c["identity_fields"]["TEST_CONTRACT_HASH"]) for c in candidates}
    fingerprint_collides = aggregate_sha in contract_hashes
    goal_checks["aggregate_not_a_contract_hash"] = not fingerprint_collides
    if fingerprint_collides:
        _recon(failures, "AGGREGATE_IS_CONTRACT_HASH", "aggregate hash collides with a frozen TEST_CONTRACT_HASH")

    reconciled = not failures
    return {
        "schema": SCHEMA,
        "artifact": ARTIFACT,
        "status": "PROVISIONAL_NOT_EXECUTABLE" if reconciled else "FAILED_RECONCILIATION",
        "created_at": created_at,
        "canonical_order": {
            "record_sequence": "task-major (OPWS_ORDERED_TASK_IDS); within task frozen COMPLETE arm order",
            "task_order_source": "OPWS_ORDERED_TASK_IDS.json",
            "complete_arms": list(arms),
            "deferred": {
                "arm_id": "RANDOM_SIZE_MATCHED_RM_CSS",
                "coverage_status": "DEFERRED",
                "reason": "no stored per-task artifact; must never be generated in Phase 2",
            },
            "identity_key_recipe": IDENTITY_KEY_RECIPE,
        },
        "inputs": input_hashes,
        "counts": dict(sorted(n_cases.items())),
        "goal_checks": goal_checks,
        "reconciliation": {
            "reconciled": reconciled,
            "failures": failures,
            "n_failures": len(failures),
            "measures": n_cases,
            "goals": goals,
        },
        "task_groups": task_groups,
        "candidates": candidates,
        "hashes": {
            "identity_key_recipe": IDENTITY_KEY_RECIPE,
            "physical_execution_id_recipe": PHYSICAL_EXECUTION_ID_RECIPE,
            "candidate_sha256_recipe": CANDIDATE_SHA_RECIPE,
            "task_group_sha256_recipe": TASK_GROUP_SHA_RECIPE,
            "aggregate_sha256_recipe": AGGREGATE_SHA_RECIPE,
            "aggregate_sha256": aggregate_sha,
            "n_distinct_test_contract_hashes": len(contract_hashes),
            "aggregate_not_a_contract_hash": not fingerprint_collides,
        },
        "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
        "unresolved_science_gates": list(UNRESOLVED_SCIENCE_GATES),
        "execution_authorization": {
            "physical_execution": "NOT_AUTHORIZED",
            "experimental_reuse": "NOT_PERMITTED",
            "environment_binding": "PENDING_VALIDATION",
            "node_identity": "PENDING_VERIFICATION_OR_TRUE_ZERO",
        },
    }


# --------------------------------------------------------------------------- output rendering

def render_outputs(
    *,
    spec: dict[str, Any],
    out_dir: Path,
    repo_meta: dict[str, Any],
    start_wall_s: float,
    elapsed_wall_s_override: float | None = None,
) -> dict[str, Any]:
    if not spec.get("reconciliation", {}).get("reconciled", False):
        raise ExtractError("refusing to render outputs for a non-reconciled spec; write the failure receipt instead")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_text = _canonical_json(spec) + "\n"
    plan_path = out_dir / PLAN_FILENAME
    plan_path.write_bytes(plan_text.encode("utf-8"))
    plan_sha = sha256_str(plan_text)

    receipt = _build_receipt(spec, repo_meta, start_wall_s, plan_sha, elapsed_wall_s_override)
    receipt_text = _canonical_json(receipt) + "\n"
    receipt_path = out_dir / RECEIPT_FILENAME
    receipt_path.write_bytes(receipt_text.encode("utf-8"))
    receipt_sha = sha256_str(receipt_text)

    report_path = out_dir / REPORT_FILENAME
    report_text = _build_report_markdown(spec, receipt, plan_sha, receipt_sha)
    report_path.write_bytes(report_text.encode("utf-8"))
    report_sha = sha256_str(report_text)

    return {
        "plan": {"path": str(plan_path), "sha256": plan_sha},
        "receipt": {"path": str(receipt_path), "sha256": receipt_sha},
        "report": {"path": str(report_path), "sha256": report_sha},
    }


def render_failure_receipt(
    *,
    error: str,
    out_dir: Path,
    repo_meta: dict[str, Any],
    inputs: dict[str, dict[str, Any]] | None = None,
    created_at: str,
    failures: list[dict[str, str]] | None = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "artifact": "M19A2_EXTRACTOR_FAILURE_RECEIPT",
        "status": "FAILED_RECONCILIATION",
        "created_at": created_at,
        "error": error,
        "failures": failures or [],
        "input_hashes": inputs,
        "repo": repo_meta,
        "outputs": {"plan_written": False, "receipt_type": "failure"},
        "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
        "recommendation": "STOP",
    }
    path = out_dir / FAILURE_RECEIPT_FILENAME
    path.write_bytes((_canonical_json(payload) + "\n").encode("utf-8"))
    return path


def _build_receipt(
    spec: dict[str, Any],
    repo_meta: dict[str, Any],
    start_wall_s: float,
    plan_sha: str,
    elapsed_wall_s_override: float | None = None,
) -> dict[str, Any]:
    if elapsed_wall_s_override is not None:
        elapsed = float(elapsed_wall_s_override)
    else:
        elapsed = max(0.0, time.monotonic() - start_wall_s)
    counts = spec["counts"]
    return {
        "schema": "opws-m19a2-extractor-receipt/1.0",
        "artifact": "M19A2_EXTRACTOR_RECEIPT",
        "status": spec["status"],
        "created_at": spec["created_at"],
        "inputs": spec["inputs"],
        "input_pins": {
            name: {
                "path": info.get("path"),
                "pinned_sha256": INPUT_SHA256_PINS.get(name),
                "pin_match": info.get("match"),
            }
            for name, info in spec["inputs"].items()
        },
        "outputs": {
            "physical_execution_plan": {
                "file": PLAN_FILENAME,
                "sha256": plan_sha,
            },
        },
        "counts": counts,
        "n_candidates": counts.get("n_candidates"),
        "n_logical_mapping": counts.get("n_logical_records"),
        "n_missing_logical_mappings": counts.get("n_missing_logical_mappings"),
        "n_duplicate_candidate_ids": counts.get("n_duplicate_candidate_ids"),
        "error_count": spec["reconciliation"]["n_failures"],
        "warning_count": 0,
        "reconciliation": spec["reconciliation"],
        "hashes": spec["hashes"],
        "unresolved_science_gates": spec["unresolved_science_gates"],
        "repo": repo_meta,
        "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
        "go_recommendation": "GO" if spec["reconciliation"]["reconciled"] else "STOP",
        "recommendation_note": (
            "GO for M19A2-ATOMIC2 ONLY as a read-only registry/verification follow-up; never for "
            "behavioral execution. Physical execution, environment binding and experimental reuse "
            "remain NOT AUTHORIZED until STAGE_5/6/7, environment runtime verification and frozen "
            "node identity resolution."
        ),
        "elapsed_wall_s": round(elapsed, 3),
    }


def _build_report_markdown(
    spec: dict[str, Any],
    receipt: dict[str, Any],
    plan_sha: str,
    receipt_sha: str,
) -> str:
    lines: list[str] = []
    add = lines.append
    add("# M19A2-ATOMIC1 — Implementation Report (execution-candidate registry)\n")
    add(f"- **Artifact:** `{ARTIFACT}` — schema `{spec['schema']}`")
    add(f"- **Status:** `{spec['status']}` (reconciled={spec['reconciliation']['reconciled']})")
    add(f"- **Created at:** `{spec['created_at']}` (UTC)")
    add(f"- **REAL_TASK_BEHAVIORAL_OUTCOMES:** {spec['REAL_TASK_BEHAVIORAL_OUTCOMES']}\n")
    add("## 1 Scope discipline\n")
    add(
        "- This registry is a deterministic execution-CANDIDATE registry, not a behavioral execution scheduler.\n"
        "- Every candidate carries `execution_status.executable=false` and "
        "`status_code=PROVISIONAL_NOT_EXECUTABLE`; no physical execution is authorized.\n"
        "- `execution_authorization`: physical execution NOT_AUTHORIZED, experimental reuse NOT_PERMITTED, "
        "environment binding PENDING_VALIDATION.\n"
        "- Environment IDs are the frozen proposal values (`OPWS_ENVIRONMENT_ID_PROPOSAL.json`, "
        "PROPOSED_PENDING_OWNER_CONFIRMATION); runtime verification is not performed here.\n"
        "- F2P node identity: true zero-F2P (`f2p.total==0`) recorded as `TRUE_ZERO_NODE` separately from "
        "`NODE_IDS_PENDING_EXACT_VERIFICATION` (count > 0, per-node IDs not frozen in-repo for all 219 tasks). "
        "No node ID is invented.\n"
    )
    add("## 2 Implemented change\n")
    add(
        "- Added `scripts/opws_m19a2_candidate_registry.py` (deterministic extractor; reuses frozen "
        "`plan_physical_dedup` / `physical_execution_identity` / `PHYSICAL_IDENTITY_FIELDS` from "
        "`scripts/opws_phase3b_patch_materialize.py` verbatim — import-only, no frozen-contract edit).\n"
        "- Added `tests/test_opws_m19a2_candidate_registry.py` (synthetic tests only).\n"
    )
    add("## 3 Canonical ordering\n")
    add(
        f"- Record sequence: task-major (`OPWS_ORDERED_TASK_IDS.json`), within task the frozen COMPLETE arm "
        f"order; deferred arm emits no records.\n"
        f"- Complete arms ({len(spec['canonical_order']['complete_arms'])}): "
        + "`, `".join(spec["canonical_order"]["complete_arms"])
        + ".\n"
        f"- Deferred: `{spec['canonical_order']['deferred']['arm_id']}` — "
        f"{spec['canonical_order']['deferred']['coverage_status']}.\n"
        f"- Identity key recipe: `{spec['canonical_order']['identity_key_recipe']}`\n"
    )
    add("## 4 Hash recipes\n")
    for key in (
        "identity_key_recipe",
        "physical_execution_id_recipe",
        "candidate_sha256_recipe",
        "task_group_sha256_recipe",
        "aggregate_sha256_recipe",
    ):
        add(f"- {key}: `{spec['hashes'][key]}`")
    add(
        f"- aggregate_sha256 (registry fingerprint, NEVER a frozen TEST_CONTRACT_HASH; collision check: "
        f"`{spec['hashes']['aggregate_not_a_contract_hash']}`): `{spec['hashes']['aggregate_sha256']}`\n"
    )
    add("## 5 Reconciliation\n")
    add("| Claim | Goal | Observed | PASS |")
    add("|---|---|---|---|")
    for key, goal in sorted(spec["reconciliation"]["goals"].items()):
        observed = spec["counts"].get(key, "-")
        add(f"| {key} | {goal} | {observed} | {'PASS' if spec['goal_checks'].get(key, False) else 'FAIL'} |")
    add(
        f"| n_logical_origins_total | == n_logical_records | {spec['counts'].get('n_logical_records')} | "
        f"{'PASS' if spec['goal_checks'].get('n_logical_origins_total', False) else 'FAIL'} |"
    )
    add(
        f"| each candidate >= 1 logical origin | True | "
        f"{'PASS' if spec['goal_checks'].get('n_candidates_with_origin', False) else 'FAIL'} |"
    )
    add(
        f"| aggregate_not_a_contract_hash | True | "
        f"{'PASS' if spec['goal_checks'].get('aggregate_not_a_contract_hash', False) else 'FAIL'} |"
    )
    add(
        f"\n- Failures: {spec['reconciliation']['n_failures']} — "
        + ("none" if not spec["reconciliation"]["failures"] else str(spec["reconciliation"]["failures"]))
        + "\n"
    )
    add("## 6 Counts and provenance\n")
    for key in sorted(spec["counts"]):
        add(f"- **{key}:** {spec['counts'][key]}")
    add(
        f"\n- Each of the {spec['counts'].get('n_logical_records')} logical records maps to exactly one of "
        f"the {spec['counts'].get('n_candidates')} candidates (`record_to_candidate` bijection verified).\n"
    )
    add("## 7 Unresolved science gates\n")
    for gate in spec["unresolved_science_gates"]:
        add(f"- {gate}")
    add("\n## 8 Output artifacts\n")
    add(f"- `{PLAN_FILENAME}` — SHA-256 `{plan_sha}`")
    add(f"- `{RECEIPT_FILENAME}` — SHA-256 `{receipt_sha}` (see its `outputs`, `repo`, `hashes`)")
    add(f"- `{REPORT_FILENAME}` — this report")
    add(
        f"\n## 9 Recommendation\n"
        f"- **{receipt['go_recommendation']}** — {receipt['recommendation_note']}\n"
        f"- Elapsed wall time (extractor run): {receipt['elapsed_wall_s']} s\n"
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------- CLI

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="opws_m19a2_candidate_registry",
        description="M19A2-ATOMIC1 deterministic execution-candidate registry (candidate-only).",
    )
    parser.add_argument("--plan", required=True, help="EFFECTIVE_PATCH_PLAN_219.json (approved, SHA-pinned)")
    parser.add_argument("--ordered-task-ids", required=True, help="OPWS_ORDERED_TASK_IDS.json")
    parser.add_argument("--env-proposal", required=True, help="OPWS_ENVIRONMENT_ID_PROPOSAL.json")
    parser.add_argument("--contract-manifest", required=True, help="OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json")
    parser.add_argument("--tree-receipt", required=True, help="FULL_REFERENCE_TREE_RECEIPT_219.json")
    parser.add_argument("--out-dir", required=True, help="external output directory")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]),
                        help="project root for read-only git metadata (default: repo root of this script)")
    parser.add_argument("--created-at", default=None, help="fixed ISO UTC timestamp (determinism/testing)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    start_wall = time.monotonic()
    created_at = args.created_at or now_iso()
    out_dir = Path(args.out_dir)
    repo_meta = repo_metadata(Path(args.repo_root))

    input_paths = {
        "plan": Path(args.plan),
        "ordered_task_ids": Path(args.ordered_task_ids),
        "environment_id_proposal": Path(args.env_proposal),
        "contract_manifest": Path(args.contract_manifest),
        "tree_receipt": Path(args.tree_receipt),
    }
    try:
        input_hashes = verify_input_hashes(input_paths)
    except ExtractError as exc:
        render_failure_receipt(error=str(exc), out_dir=out_dir, repo_meta=repo_meta, created_at=created_at)
        print(f"STOP: {exc}", file=sys.stderr)
        return 2

    try:
        plan = load_json_file(input_paths["plan"])
        ordered_ids = [str(t) for t in load_json_file(input_paths["ordered_task_ids"])["ordered_task_ids"]]
        env_doc = load_json_file(input_paths["environment_id_proposal"])
        env_by_task = {str(e["task_id"]): str(e["environment_id"]) for e in env_doc["per_task"]}
        man_doc = load_json_file(input_paths["contract_manifest"])
        manifest_by_task = {str(t["task_id"]): t for t in man_doc["per_task"]}
        tree_receipt = load_json_file(input_paths["tree_receipt"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        render_failure_receipt(error=f"input load failed: {exc}", out_dir=out_dir, repo_meta=repo_meta,
                               inputs=input_hashes, created_at=created_at)
        print(f"STOP: input load failed: {exc}", file=sys.stderr)
        return 2

    try:
        spec = build_registry_spec(
            plan=plan,
            ordered_task_ids=ordered_ids,
            env_by_task=env_by_task,
            manifest_by_task=manifest_by_task,
            tree_receipt=tree_receipt,
            created_at=created_at,
            input_hashes=input_hashes,
        )
    except ReconciliationError as exc:
        render_failure_receipt(error=str(exc), out_dir=out_dir, repo_meta=repo_meta,
                               inputs=input_hashes, created_at=created_at, failures=exc.failures)
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    except ExtractError as exc:
        render_failure_receipt(error=str(exc), out_dir=out_dir, repo_meta=repo_meta,
                               inputs=input_hashes, created_at=created_at)
        print(f"STOP: {exc}", file=sys.stderr)
        return 3
    if not spec["reconciliation"]["reconciled"]:
        render_failure_receipt(error="reconciliation failed (measure-goal or integrity check)", out_dir=out_dir,
                               repo_meta=repo_meta, inputs=input_hashes, created_at=created_at,
                               failures=spec["reconciliation"]["failures"])
        print(f"STOP: reconciliation failed: {spec['reconciliation']['failures']}", file=sys.stderr)
        return 3

    outputs = render_outputs(spec=spec, out_dir=out_dir, repo_meta=repo_meta, start_wall_s=start_wall)
    print(f"RECONCILED={spec['reconciliation']['reconciled']}")
    print(f"CANDIDATES={spec['counts']['n_candidates']}")
    print(f"LOGICAL_MAPPINGS={spec['counts']['n_logical_records']}")
    print(f"AGGREGATE_SHA256={spec['hashes']['aggregate_sha256']}")
    for key, info in outputs.items():
        print(f"WROTE_{key.upper()}={info['path']}")
        print(f"SHA256_{key.upper()}={info['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
