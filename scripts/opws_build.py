"""OPWS R1 Phase 0/1 — additive immutable-input builders (read-only over frozen evidence).

This module NEVER executes OPWS, never calls a model API, never mutates a frozen
artifact, and never writes outside ``research/opws/binding``. It only reads frozen
Full-D7 / M17 / OPWS-R1 evidence and materializes deterministic, self-hashed
binding artifacts.

Design rules enforced here
--------------------------
* Every input is read from disk (or from the frozen protocol git objects); every
  input SHA-256 is recorded in the build status artifact.
* No value is guessed: a field that cannot be derived from frozen evidence is
  emitted as an ``UNRESOLVED_*`` token, never as ``true`` / ``0`` / a placeholder
  that could be mistaken for a real decision.
* ``ordered_task_ids_sha256`` is a NEW task-level hash. It is asserted to differ
  from the frozen 144-unit ``ordered membership`` hash ``8eb4a724...``.
* F2P node identities are *resolvable at evaluation time* (frozen evaluator node
  records bounded by the frozen per-task count). They are not fabricated at
  binding time; the rule mirrors ``scripts/wp2_m17_contract.py``.

Usage
-----
    python scripts/opws_build.py --check
    python scripts/opws_build.py --created-at 2026-10-20T00:00:00Z
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
BUILD_DIR = PROJECT / "research" / "opws" / "binding"

READINESS_MANIFEST = PROJECT / "research/env-canon-r4/R4_FULL144_READINESS_MANIFEST.json"
CENSUS = PROJECT / "research/env-canon-r4/R4_I6_CORRECTED_ZERO_CONTAINER_CENSUS_144.json"
RUNTIME_BINDING = PROJECT / "research/env-canon-r4/R4_EXECUTION_IMAGE_BINDING_RUNTIME_CLEAN.json"
FULLD7_RESULT = PROJECT / "research/env-canon-r4/R4_SCIENTIFIC_FULL144_SUCCESSOR_RESULT_2026-10-17.json"
PER_TASK_V2 = PROJECT / "research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl"
MAIN297_CENSUS = PROJECT / "research/wp2/wp2_saleor_main297_census_2026-09-22.json"
ADAPTER_REPORT = PROJECT / "research/wp2/m17_v1/adapter/adapter_report.json"
MAIN297_MANIFEST = PROJECT / "research/wp1b/wp1b_main_297_manifest.json"
E1_EVALUATOR = PROJECT / "scripts/wp2_m14a_evalcore_e1.py"

EXPECTED_N_UNITS = 144
EXPECTED_N_TASKS = 219
EXPECTED_POPULATION_IDENTITY = "ce51d2ec0eb28f6b720fbab13a852618e2de0f0a1111a3cc19dc64b1d19defac"
EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH = "8eb4a7242e12bb03715adac5fffdea2e4340585843fc137ececd38952ad6a19e"
EXPECTED_RUNTIME_BINDING_HASH = "5169c69d45f0761c85792ec182c9e949f58d8c9f5a29355d5a371944293d2ef2"

FULL_D7_TAG = "m17-d7-r4-scientific-full144-successor-pass-2026-10-17"
FULL_D7_EVIDENCE_COMMIT = "0fea61c799b3b3ded9d0c74a0a20ea3535d103c1"
PROTOCOL_TAG = "m17-opws-protocol-r1-frozen-2026-10-12"
PROTOCOL_TAG_OBJECT = "63ff392b92cacf5d274cfe1823275ff3bba90af7"
PROTOCOL_COMMIT = "9038df3ea80d7d478c2f949b2d3fae75754bb6e1"
PROTOCOL_DIR = "research/opws-protocol-r1"
EXPECTED_N_PROTOCOL_FILES = 16

BINDING_FIELDS = (
    "full_d7_evidence_commit",
    "full_d7_tag",
    "full_d7_ready_population_file",
    "full_d7_ready_population_sha256",
    "n_env_ready",
    "behavior_contract_manifest",
    "behavior_contract_manifest_sha256",
    "n_opws_eligible",
    "n_primary_paired",
    "ordered_task_ids",
    "ordered_task_ids_sha256",
    "binding_created_at",
    "protocol_sha256",
)

F2P_CLASSES = ("BEHAVIORAL_F2P", "SYMBOL_ABSENCE_F2P")

UNRESOLVED_STAGE5 = "UNRESOLVED_PENDING_STAGE5_PREFLIGHT"
UNRESOLVED_STAGE7 = "UNRESOLVED_PENDING_STAGE7_ARM_ARTIFACTS"


class BuildError(RuntimeError):
    """A frozen-evidence invariant failed; the build must not proceed."""


# ---------------------------------------------------------------- primitives
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha_obj(obj: Any) -> str:
    return sha256_bytes(canon(obj).encode("utf-8"))


def ordered_task_ids_sha256(task_ids: list[str]) -> str:
    """Explicit canonical recipe for the task-level order hash.

    ``json.dumps(list, separators=(",", ":"))`` -> UTF-8 -> SHA-256.
    This is intentionally the same byte convention as
    ``src/benchmark/wp2/full144/population.py::ordered_membership_hash`` but over
    the 219 task IDs, not the 144 unit IDs.
    """
    payload = json.dumps(task_ids, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def environment_id(immutable_image_id: str, runtime_binding_hash: str, fingerprint: str) -> str:
    """Proposed deterministic ENVIRONMENT_ID (sha256 over the three components)."""
    payload = json.dumps(
        [immutable_image_id, runtime_binding_hash, fingerprint],
        separators=(",", ":"),
    )
    return sha256_bytes(payload.encode("utf-8"))


def git_bytes(*args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(PROJECT), *args],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


# ---------------------------------------------------------------- inputs
def load_population() -> dict[str, Any]:
    census = read_json(CENSUS)
    readiness = read_json(READINESS_MANIFEST)

    require(
        census.get("population_identity_sha256") == EXPECTED_POPULATION_IDENTITY,
        "census population identity mismatch",
    )
    require(readiness.get("n_units") == EXPECTED_N_UNITS, "readiness manifest n_units != 144")
    require(readiness.get("aggregate", {}).get("READY") == EXPECTED_N_UNITS, "readiness aggregate READY != 144")

    census_units = census.get("units")
    require(isinstance(census_units, list) and len(census_units) == EXPECTED_N_UNITS, "census units != 144")

    readiness_units = {u["validation_unit_id"]: u for u in readiness["units"]}
    require(len(readiness_units) == EXPECTED_N_UNITS, "readiness unit ids not unique")

    units: list[dict[str, Any]] = []
    for cu in census_units:
        uid = str(cu["validation_unit_id"])
        ru = readiness_units[uid]
        require(ru.get("readiness_verdict") == "READY", f"{uid}: readiness_verdict != READY")
        require(
            list(ru.get("member_task_ids") or []) == list(cu.get("member_tasks") or []),
            f"{uid}: census member_tasks != readiness member_task_ids (order-sensitive)",
        )
        require(bool(ru.get("immutable_image_id")), f"{uid}: missing immutable_image_id")
        units.append(
            {
                "validation_unit_id": uid,
                "immutable_image_id": ru["immutable_image_id"],
                "docker_profile_id": ru.get("docker_profile_id"),
                "native_profile_id": ru.get("native_profile_id"),
                "python_version": ru.get("python_version"),
                "wheelhouse_era": ru.get("wheelhouse_era"),
                "install_route": ru.get("install_route"),
                "lock_type": ru.get("lock_type"),
                "member_task_ids": list(ru["member_task_ids"]),
            }
        )

    task_ids = [t for u in units for t in u["member_task_ids"]]
    require(len(task_ids) == EXPECTED_N_TASKS, f"expanded task count {len(task_ids)} != {EXPECTED_N_TASKS}")
    require(len(set(task_ids)) == EXPECTED_N_TASKS, "expanded task ids not unique")

    readiness_counts = census.get("per_member_task_readiness") or {}
    require(readiness_counts.get("commit_missing") == [], "census reports commit_missing tasks")
    require(readiness_counts.get("commit_ready") == EXPECTED_N_TASKS, "census commit_ready != 219")

    membership_hash = ordered_task_ids_sha256([u["validation_unit_id"] for u in units])
    require(
        membership_hash == EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH,
        "unit order does not reproduce the frozen ordered-membership hash",
    )

    order_hash = ordered_task_ids_sha256(task_ids)
    require(order_hash != EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH, "refusing to reuse the unit-level 8eb4a724 hash")

    return {
        "units": units,
        "task_ids": task_ids,
        "unit_order_membership_hash": membership_hash,
        "ordered_task_ids_sha256": order_hash,
    }


def load_runtime_binding(units: list[dict[str, Any]]) -> dict[str, Any]:
    binding = read_json(RUNTIME_BINDING)
    require(
        binding.get("deterministic_binding_hash") == EXPECTED_RUNTIME_BINDING_HASH,
        "runtime binding hash mismatch",
    )
    require(binding.get("population_identity") == EXPECTED_POPULATION_IDENTITY, "runtime binding population mismatch")

    image_by_unit: dict[str, str] = {}
    for pair in binding.get("pairs", []):
        image = str(pair["immutable_image_id"])
        for uid in pair.get("member_validation_unit_ids", []):
            image_by_unit[str(uid)] = image
    require(len(image_by_unit) == EXPECTED_N_UNITS, "runtime binding unit coverage != 144")

    for unit in units:
        require(
            image_by_unit[unit["validation_unit_id"]] == unit["immutable_image_id"],
            f"{unit['validation_unit_id']}: readiness image != runtime binding image",
        )

    return {
        "deterministic_binding_hash": binding["deterministic_binding_hash"],
        "unique_pair_count": binding.get("unique_pair_count"),
        "pairs": binding.get("pairs", []),
    }


def load_task_inputs(task_ids: list[str]) -> dict[str, Any]:
    per_task_rows = read_jsonl(PER_TASK_V2)
    per_task = {str(r["task_id"]): r for r in per_task_rows}
    require(len(per_task) == len(per_task_rows), "per_task_v2 has duplicate task ids")

    main_rows = read_json(MAIN297_CENSUS)["tasks"]
    main297 = {str(r["task_id"]): r for r in main_rows}
    main297_manifest = read_json(MAIN297_MANIFEST)
    manifest_ids = [str(t) for t in main297_manifest["task_ids"]]

    adapter = read_json(ADAPTER_REPORT)
    unresolved = {str(t) for t in (adapter.get("main_unresolved_detail") or {})}
    require(adapter.get("main_resolved") == EXPECTED_N_TASKS, "adapter main_resolved != 219")
    require(adapter.get("main_unresolved") == len(unresolved) == 1, "adapter main_unresolved bookkeeping mismatch")

    missing_per_task = [t for t in task_ids if t not in per_task]
    missing_main = [t for t in task_ids if t not in main297]
    not_in_manifest = [t for t in task_ids if t not in set(manifest_ids)]
    require(not missing_per_task, f"tasks missing from per_task_v2: {missing_per_task[:5]}")
    require(not missing_main, f"tasks missing from MAIN_297 census: {missing_main[:5]}")
    require(not not_in_manifest, f"tasks missing from MAIN_297 manifest: {not_in_manifest[:5]}")

    for task_id in task_ids:
        fp = (per_task[task_id].get("provenance") or {}).get("environment_fingerprint")
        require(bool(fp), f"{task_id}: missing provenance.environment_fingerprint")
        require(bool(main297[task_id].get("test_command")), f"{task_id}: missing deterministic test_command")

    return {
        "per_task": per_task,
        "n_per_task_extra": len(per_task) - len(task_ids),
        "per_task_extra_ids": sorted(set(per_task) - set(task_ids)),
        "main297": main297,
        "manifest_ids": manifest_ids,
        "adapter_unresolved": sorted(unresolved),
        "adapter_verdict": adapter.get("verdict"),
        "adapter_artifact_sha256": adapter.get("artifact_sha256"),
    }


def load_protocol_bundle() -> dict[str, Any]:
    tag_object = git_bytes("rev-parse", PROTOCOL_TAG).decode().strip()
    peel = git_bytes("rev-list", "-n", "1", PROTOCOL_TAG).decode().strip()
    require(tag_object == PROTOCOL_TAG_OBJECT, "protocol tag object mismatch")
    require(peel == PROTOCOL_COMMIT, "protocol tag peel mismatch")

    full_d7_peel = git_bytes("rev-list", "-n", "1", FULL_D7_TAG).decode().strip()
    require(full_d7_peel == FULL_D7_EVIDENCE_COMMIT, "Full-D7 tag peel mismatch")

    listing = git_bytes("ls-tree", "-r", "--name-only", PROTOCOL_COMMIT, "--", PROTOCOL_DIR).decode()
    paths = sorted(p for p in listing.splitlines() if p.endswith((".json", ".md")))
    require(len(paths) == EXPECTED_N_PROTOCOL_FILES, f"protocol file count {len(paths)} != 16")

    entries: list[list[str]] = []
    for rel in paths:
        blob = git_bytes("cat-file", "blob", f"{PROTOCOL_COMMIT}:{rel}")
        entries.append([rel, sha256_bytes(blob)])

    bundle_sha = sha_obj(entries)
    return {
        "protocol_tag": PROTOCOL_TAG,
        "protocol_tag_object": tag_object,
        "protocol_commit": peel,
        "protocol_sha256": bundle_sha,
        "protocol_sha256_recipe": (
            "sha256(compact_json(sorted [[relpath, sha256(blob_bytes)]]) at protocol_commit)"
        ),
        "n_protocol_files": len(paths),
        "protocol_files": entries,
        "full_d7_tag": FULL_D7_TAG,
        "full_d7_evidence_commit": full_d7_peel,
    }


# ---------------------------------------------------------------- artifacts
def build_artifact_ready_population(
    units: list[dict[str, Any]], task_ids: list[str], inputs: dict[str, Any]
) -> dict[str, Any]:
    unit_of = {t: u["validation_unit_id"] for u in units for t in u["member_task_ids"]}
    image_of = {t: u["immutable_image_id"] for u in units for t in u["member_task_ids"]}
    per_task = inputs["per_task"]
    records = []
    for task_id in task_ids:
        row = per_task[task_id]
        counts = row.get("counts") or {}
        records.append(
            {
                "task_id": task_id,
                "validation_unit_id": unit_of[task_id],
                "immutable_image_id": image_of[task_id],
                "era_key": row.get("era_key"),
                "target_commit": row.get("provenance", {}).get("target_commit")
                or inputs["main297"][task_id].get("target_commit"),
                "f2p_total": int(counts.get("BEHAVIORAL_F2P", 0)) + int(counts.get("SYMBOL_ABSENCE_F2P", 0)),
                "behavioral_f2p": int(counts.get("BEHAVIORAL_F2P", 0)),
                "symbol_absence_f2p": int(counts.get("SYMBOL_ABSENCE_F2P", 0)),
                "primary_behavioral_f2p_eligible": bool(
                    (row.get("eligibility") or {}).get("PRIMARY_BEHAVIORAL_F2P_ELIGIBLE")
                ),
                "environment_fingerprint": row["provenance"]["environment_fingerprint"],
            }
        )

    return {
        "artifact": "opws_ready_population_tasks_219",
        "schema_version": "opws-ready-population/1.0-additive",
        "n_units": len(units),
        "n_tasks": len(task_ids),
        "population_identity_sha256": EXPECTED_POPULATION_IDENTITY,
        "unit_order_membership_hash": EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH,
        "aggregation_rule": (
            "unit-major expansion: census/readiness unit order (144), member_task_ids order within unit"
        ),
        "units": units,
        "per_task": records,
        "n_f2p_positive": sum(1 for r in records if r["f2p_total"] > 0),
        "n_primary_behavioral_f2p_eligible": sum(1 for r in records if r["primary_behavioral_f2p_eligible"]),
        "per_task_extra_ids_outside_population": inputs["per_task_extra_ids"],
    }


def build_artifact_ordered_task_ids(population: dict[str, Any]) -> dict[str, Any]:
    task_ids = [str(r["task_id"]) for r in population["per_task"]]
    return {
        "artifact": "opws_ordered_task_ids",
        "schema_version": "opws-ordered-task-ids/1.0-additive",
        "canonical_recipe": (
            'sha256(utf8(json.dumps(task_ids, separators=(",", ":")))) '
            "over the unit-major expansion of the frozen 144-unit READY census"
        ),
        "n_tasks": len(task_ids),
        "ordered_task_ids_sha256": ordered_task_ids_sha256(task_ids),
        "order_authority": (
            "R4_I6_CORRECTED_ZERO_CONTAINER_CENSUS_144.json unit order; "
            "R4_FULL144_READINESS_MANIFEST.json member_task_ids order (verified identical)"
        ),
        "not_equal_to": {
            "ordered_membership_hash_144_units": EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH,
            "reason": "unit-level hash is not a task-level hash and must never be reused for this field",
        },
        "ordered_task_ids": task_ids,
    }


def build_artifact_environment_id(
    population: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    runtime_hash = runtime["deterministic_binding_hash"]
    proposals = []
    for rec in population["per_task"]:
        components = [rec["immutable_image_id"], runtime_hash, rec["environment_fingerprint"]]
        proposals.append(
            {
                "task_id": rec["task_id"],
                "validation_unit_id": rec["validation_unit_id"],
                "components": {
                    "immutable_image_id": components[0],
                    "deterministic_binding_hash": components[1],
                    "environment_fingerprint": components[2],
                },
                "environment_id": environment_id(*components),
            }
        )
    ids = [p["environment_id"] for p in proposals]
    shared: dict[str, list[str]] = {}
    for p in proposals:
        shared.setdefault(p["environment_id"], []).append(p["task_id"])
    return {
        "artifact": "opws_environment_id_proposal",
        "schema_version": "opws-environment-id-proposal/1.0-additive",
        "status": "PROPOSED_PENDING_OWNER_CONFIRMATION",
        "proposal": (
            "ENVIRONMENT_ID = sha256(utf8(compact_json([immutable_image_id, "
            "deterministic_binding_hash, environment_fingerprint])))"
        ),
        "components": {
            "immutable_image_id": "per-pair pinned image digest from the frozen Full-D7 readiness/runtime binding",
            "deterministic_binding_hash": runtime_hash,
            "environment_fingerprint": "per-task provenance.environment_fingerprint from per_task_v2.jsonl",
        },
        "open_owner_decision": (
            "The frozen protocol names ENVIRONMENT_ID as a physical-identity field but does not define its "
            "serialization. This proposal fixes the composition and byte recipe; owner confirmation is required "
            "before the value may be treated as frozen binding semantics."
        ),
        "n_tasks": len(proposals),
        "n_distinct_environment_ids": len(set(ids)),
        "shared_environment_groups": {k: v for k, v in shared.items() if len(v) > 1},
        "per_task": proposals,
    }


def build_artifact_behavior_contract(
    population: dict[str, Any], inputs: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    e1_sha = file_sha256(E1_EVALUATOR)
    unresolved = set(inputs["adapter_unresolved"])
    per_task = inputs["per_task"]
    contracts = []
    for rec in population["per_task"]:
        task_id = rec["task_id"]
        row = per_task[task_id]
        counts = row.get("counts") or {}
        main = inputs["main297"][task_id]
        adapter_resolved = task_id not in unresolved
        test_command = main.get("test_command")
        contract = {
            "task_id": task_id,
            "validation_unit_id": rec["validation_unit_id"],
            "target_commit": main.get("target_commit") or rec.get("target_commit"),
            "parent_commit": main.get("parent_commit"),
            "adapter_resolved": adapter_resolved,
            "adapter_source": "research/wp2/m17_v1/adapter/adapter_report.json",
            "test_command": test_command,
            "test_command_source": "research/wp2/wp2_saleor_main297_census_2026-09-22.json",
            "evaluator_boundary": {
                "kind": "E1",
                "entrypoint": "scripts/wp2_m14a_evalcore_e1.py:evaluate_state_e1",
                "sha256": e1_sha,
            },
            "f2p": {
                "behavioral": int(counts.get("BEHAVIORAL_F2P", 0)),
                "symbol_absence": int(counts.get("SYMBOL_ABSENCE_F2P", 0)),
                "total": int(counts.get("BEHAVIORAL_F2P", 0)) + int(counts.get("SYMBOL_ABSENCE_F2P", 0)),
                "classes": list(F2P_CLASSES),
                "selector_blind": True,
                "node_identity_binding_mode": "AT_EVALUATION_BOUNDED_BY_FROZEN_COUNT",
                "node_identity_rule": (
                    "frozen evaluator node records with v3_class in F2P classes; "
                    "len(node_set) < frozen count => MISSING_F2P_NODES (fail-closed)"
                ),
                "source": "scripts/wp2_m17_contract.py::f2p_node_set_from_frozen",
            },
            "preservation": {
                "p2p_s": "frozen SWE-bench-aligned changed-test PASS_TO_PASS identities",
                "p2p_u": "frozen unchanged-test STABLE_P2P identities (cap-200, STABLE over 3 reps)",
                "defined_if": "p2p_s_defined OR p2p_u_cap200_defined",
                "no_silent_reclassify": True,
                "source": "scripts/wp2_p2p_s_freeze_v1.py / scripts/wp2_p2p_u_v2_exec.py",
            },
            "behavior_contract_resolved": bool(adapter_resolved and test_command),
        }
        contract["contract_sha256"] = sha_obj(contract)
        contracts.append(contract)

    body = {
        "artifact": "opws_behavior_contract_manifest",
        "schema_version": "opws-behavior-contract-manifest/1.0-additive",
        "scoring_semantics": (
            "behavior_sufficient = 1 iff every required frozen F2P node is present and passes (strict, fail-closed)"
        ),
        "population_identity_sha256": EXPECTED_POPULATION_IDENTITY,
        "protocol_sha256": protocol["protocol_sha256"],
        "n_tasks": len(contracts),
        "n_contract_resolved": sum(1 for c in contracts if c["behavior_contract_resolved"]),
        "n_f2p_positive": sum(1 for c in contracts if c["f2p"]["total"] > 0),
        "per_task": contracts,
    }
    body["manifest_sha256"] = sha_obj(body)
    return body


def build_artifact_funnel(
    population: dict[str, Any], contracts: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    contract_by_task = {c["task_id"]: c for c in contracts["per_task"]}
    manifest_ids = set(inputs["manifest_ids"])
    rows = []
    for rec in population["per_task"]:
        task_id = rec["task_id"]
        contract = contract_by_task[task_id]
        in_universe = task_id in manifest_ids
        test_evidence = contract["f2p"]["total"] > 0
        behavior_contract = bool(contract["behavior_contract_resolved"])
        env_ready = True  # every task comes from a unit whose frozen verdict is READY

        if not in_universe:
            stage6: Any = False
        elif not test_evidence or not behavior_contract or not env_ready:
            stage6 = False
        else:
            stage6 = UNRESOLVED_STAGE5

        reasons = []
        if not in_universe:
            reasons.append("NOT_IN_UNIVERSE")
        if not test_evidence:
            reasons.append("TEST_EVIDENCE_MISSING")
        if not behavior_contract:
            reasons.append("BEHAVIOR_CONTRACT_MISSING")
        if not env_ready:
            reasons.append("ENV_NOT_READY")
        if stage6 == UNRESOLVED_STAGE5:
            reasons.append(UNRESOLVED_STAGE5)

        rows.append(
            {
                "task_id": task_id,
                "stage1_in_universe": in_universe,
                "stage2_test_evidence": test_evidence,
                "stage3_behavior_contract": behavior_contract,
                "stage4_env_ready": env_ready,
                "stage5_behavior_executable": UNRESOLVED_STAGE5,
                "stage6_opws_eligible": stage6,
                "stage7_primary_paired_eligible": UNRESOLVED_STAGE7
                if stage6 == UNRESOLVED_STAGE5
                else False,
                "frozen_f2p_total": contract["f2p"]["total"],
                "reason_codes": reasons,
            }
        )

    def counts(key: str) -> dict[str, int]:
        return {
            "true": sum(1 for r in rows if r[key] is True),
            "false": sum(1 for r in rows if r[key] is False),
            "unresolved": sum(1 for r in rows if isinstance(r[key], str)),
        }

    body = {
        "artifact": "opws_eligibility_funnel_manifest",
        "schema_version": "opws-eligibility-funnel/1.0-additive",
        "scope": "219-task frozen Full-D7 READY population",
        "tri_state_rule": (
            "true = gate passes from frozen evidence; false = gate fails from frozen evidence; "
            "UNRESOLVED_* = gate has not been evaluated and must never be reported as pass or fail"
        ),
        "stage_counts": {
            "stage1_in_universe": counts("stage1_in_universe"),
            "stage2_test_evidence": counts("stage2_test_evidence"),
            "stage3_behavior_contract": counts("stage3_behavior_contract"),
            "stage4_env_ready": counts("stage4_env_ready"),
            "stage5_behavior_executable": counts("stage5_behavior_executable"),
            "stage6_opws_eligible": counts("stage6_opws_eligible"),
            "stage7_primary_paired_eligible": counts("stage7_primary_paired_eligible"),
        },
        "distinct_markers": {
            "ENV_READY": counts("stage4_env_ready")["true"],
            "OPWS_ELIGIBLE": "UNRESOLVED (stage 5 preflight not executed in Phase 0/1)",
            "PRIMARY_PAIRED_ELIGIBLE": "UNRESOLVED (stage 7 arm artifacts not validated in Phase 0/1)",
        },
        "per_task": rows,
    }
    body["manifest_sha256"] = sha_obj(body)
    return body


def build_artifact_binding(
    *,
    population: dict[str, Any],
    ordered: dict[str, Any],
    contracts: dict[str, Any],
    protocol: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    binding = {
        "full_d7_evidence_commit": protocol["full_d7_evidence_commit"],
        "full_d7_tag": protocol["full_d7_tag"],
        "full_d7_ready_population_file": "research/env-canon-r4/R4_FULL144_READINESS_MANIFEST.json",
        "full_d7_ready_population_sha256": file_sha256(READINESS_MANIFEST),
        "n_env_ready": population["n_tasks"],
        "behavior_contract_manifest": "research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json",
        "behavior_contract_manifest_sha256": contracts["manifest_sha256"],
        "n_opws_eligible": UNRESOLVED_STAGE5,
        "n_primary_paired": UNRESOLVED_STAGE7,
        "ordered_task_ids": ordered["ordered_task_ids"],
        "ordered_task_ids_sha256": ordered["ordered_task_ids_sha256"],
        "binding_created_at": created_at,
        "protocol_sha256": protocol["protocol_sha256"],
    }
    require(tuple(binding) == BINDING_FIELDS, "binding field set/order drifted from the frozen 13-field schema")
    return binding


def build_artifact_status(
    *,
    binding: dict[str, Any],
    funnel: dict[str, Any],
    population: dict[str, Any],
    ordered: dict[str, Any],
    env_proposal: dict[str, Any],
    contracts: dict[str, Any],
    protocol: dict[str, Any],
    inputs: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    inputs_table = [
        (READINESS_MANIFEST, "full_d7_ready_population"),
        (CENSUS, "frozen_census_and_unit_order"),
        (RUNTIME_BINDING, "runtime_image_binding"),
        (FULLD7_RESULT, "scientific_full144_result"),
        (PER_TASK_V2, "per_task_f2p_counts_and_environment_fingerprint"),
        (MAIN297_CENSUS, "test_command_and_parent_target_commits"),
        (ADAPTER_REPORT, "adapter_resolution"),
        (MAIN297_MANIFEST, "stage1_frozen_task_universe"),
        (E1_EVALUATOR, "e1_evaluator_boundary"),
    ]
    return {
        "artifact": "opws_population_binding_status",
        "schema_version": "opws-population-binding-status/1.0-additive",
        "binding_status": "DRAFT_PARTIAL_PHASE1_HOLD",
        "binding_self_sha256": sha_obj(binding),
        "binding_self_sha256_recipe": "sha256(compact_json(binding_13_fields, sorted keys))",
        "created_at": created_at,
        "unresolved_binding_fields": ["n_opws_eligible", "n_primary_paired"],
        "unresolved_binding_reasons": {
            "n_opws_eligible": "STAGE_5 behavior-contract-executable preflight requires OPWS worktree execution",
            "n_primary_paired": "STAGE_7 requires RM_CSS/AGENT scope artifacts + GOLD validity control",
        },
        "population": {
            "n_units": population["n_units"],
            "n_tasks": population["n_tasks"],
            "n_f2p_positive": population["n_f2p_positive"],
            "n_primary_behavioral_f2p_eligible": population["n_primary_behavioral_f2p_eligible"],
            "ordered_task_ids_sha256": ordered["ordered_task_ids_sha256"],
            "not_equal_to_unit_hash": EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH,
        },
        "environment_id_proposal": {
            "status": env_proposal["status"],
            "n_tasks": env_proposal["n_tasks"],
            "n_distinct_environment_ids": env_proposal["n_distinct_environment_ids"],
        },
        "behavior_contract": {
            "manifest_sha256": contracts["manifest_sha256"],
            "n_contract_resolved": contracts["n_contract_resolved"],
            "n_f2p_positive": contracts["n_f2p_positive"],
        },
        "funnel_stage_counts": funnel["stage_counts"],
        "protocol": {
            "protocol_tag": protocol["protocol_tag"],
            "protocol_tag_object": protocol["protocol_tag_object"],
            "protocol_commit": protocol["protocol_commit"],
            "protocol_sha256": protocol["protocol_sha256"],
            "n_protocol_files": protocol["n_protocol_files"],
        },
        "input_files": [
            {
                "path": path.relative_to(PROJECT).as_posix(),
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path, role in inputs_table
        ],
        "input_invariants": {
            "population_identity": EXPECTED_POPULATION_IDENTITY,
            "unit_order_membership_hash_reproduced": population["unit_order_membership_hash"]
            == EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH,
            "runtime_binding_hash": EXPECTED_RUNTIME_BINDING_HASH,
            "adapter_main_resolved": 219,
            "per_task_v2_records": len(inputs["per_task"]),
            "per_task_v2_extra_ids": inputs["per_task_extra_ids"],
        },
        "blockers": [
            {
                "id": "P1_STAGE5_PREFLIGHT_NOT_EXECUTED",
                "class": "MISSING_EXECUTION",
                "detail": "STAGE_5 requires an OPWS worktree dry preflight; Phase 0/1 is record-only.",
            },
            {
                "id": "P2_ENVIRONMENT_ID_SERIALIZATION_UNCONFIRMED",
                "class": "OWNER_DECISION",
                "detail": env_proposal["open_owner_decision"],
            },
            {
                "id": "P3_F2P_NODE_IDENTITY_BINDING_MODE",
                "class": "OWNER_CONFIRMATION",
                "detail": (
                    "Node identities are bound as an evaluation-time rule (frozen evaluator, bounded by frozen "
                    "count), not as stored binding-time node IDs. The quantitative claim '9/219 tasks have stored "
                    "node_records; 78 F2P-positive tasks lack them' is UNVERIFIED_SOURCE_COUNT: per_task_v2.jsonl "
                    "has no top-level node_records; harness_v3 covers a disjoint task set. The evaluation-time rule "
                    "mirrors scripts/wp2_m17_contract.py::f2p_node_set_from_frozen (fail-closed on missing nodes)."
                ),
            },
        ],
        "prohibitions_respected": {
            "no_opws_execution": True,
            "no_model_api_calls": True,
            "no_frozen_artifact_mutation": True,
            "no_selector_outcome_or_gold_analysis": True,
            "no_retraining_or_rethresholding": True,
            "no_commit_push_tag": True,
        },
    }


def build_all(*, created_at: str) -> dict[str, dict[str, Any]]:
    population_in = load_population()
    runtime = load_runtime_binding(population_in["units"])
    inputs = load_task_inputs(population_in["task_ids"])
    protocol = load_protocol_bundle()

    population = build_artifact_ready_population(population_in["units"], population_in["task_ids"], inputs)
    ordered = build_artifact_ordered_task_ids(population)
    env_proposal = build_artifact_environment_id(population, runtime)
    contracts = build_artifact_behavior_contract(population, inputs, protocol)
    funnel = build_artifact_funnel(population, contracts, inputs)
    binding = build_artifact_binding(
        population=population,
        ordered=ordered,
        contracts=contracts,
        protocol=protocol,
        created_at=created_at,
    )
    status = build_artifact_status(
        binding=binding,
        funnel=funnel,
        population={**population, **population_in},
        ordered=ordered,
        env_proposal=env_proposal,
        contracts=contracts,
        protocol=protocol,
        inputs=inputs,
        created_at=created_at,
    )
    return {
        "OPWS_READY_POPULATION_219.json": population,
        "OPWS_ORDERED_TASK_IDS.json": ordered,
        "OPWS_ENVIRONMENT_ID_PROPOSAL.json": env_proposal,
        "OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json": contracts,
        "OPWS_ELIGIBILITY_FUNNEL_219.json": funnel,
        "OPWS_POPULATION_BINDING_R1.json": binding,
        "OPWS_POPULATION_BINDING_STATUS.json": status,
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
        "artifact": "opws_build_determinism",
        "schema_version": "opws-build-determinism/1.0-additive",
        "n_artifacts": len(entries),
        "all_identical": all(e["identical"] for e in entries),
        "artifacts": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build OPWS R1 Phase 0/1 immutable-input artifacts (read-only).")
    parser.add_argument("--out-dir", default=str(BUILD_DIR), help="output directory (default: research/opws/binding)")
    parser.add_argument(
        "--created-at",
        default=os.environ.get("OPWS_BINDING_CREATED_AT") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="UTC ISO timestamp recorded in the binding; pass a fixed value for byte-deterministic rebuilds",
    )
    parser.add_argument("--check", action="store_true", help="build twice and verify byte-determinism; write nothing")
    args = parser.parse_args(argv)

    first_payloads = build_all(created_at=args.created_at)
    first = {name: render(payload) for name, payload in first_payloads.items()}
    second_payloads = build_all(created_at=args.created_at)
    second = {name: render(payload) for name, payload in second_payloads.items()}
    determinism = determinism_report(first, second)
    first["OPWS_BUILD_DETERMINISM.json"] = render(determinism)

    if args.check:
        print(json.dumps({"all_identical": determinism["all_identical"], "artifacts": determinism["n_artifacts"]}))
        return 0 if determinism["all_identical"] else 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in first.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")

    status = first_payloads["OPWS_POPULATION_BINDING_STATUS.json"]
    print(
        json.dumps(
            {
                "binding_status": status["binding_status"],
                "binding_self_sha256": status["binding_self_sha256"],
                "ordered_task_ids_sha256": status["population"]["ordered_task_ids_sha256"],
                "n_env_ready": status["population"]["n_tasks"],
                "n_f2p_positive": status["population"]["n_f2p_positive"],
                "n_contract_resolved": status["behavior_contract"]["n_contract_resolved"],
                "funnel_stage_counts": status["funnel_stage_counts"],
                "all_identical": determinism["all_identical"],
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0 if determinism["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
