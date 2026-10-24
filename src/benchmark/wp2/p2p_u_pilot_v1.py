"""WP-2 P2P-U MAIN PILOT adapter V1 (M19B-R4) - ZERO API.

Additive, clearly-versioned adapter that applies the FROZEN V2 P2P-U rule
(``p2p_u_v2.py``, artifact ``p2p-u-v2-2026-09-25``) to a PROSPECTIVE MAIN
candidate pool discovered under M19B-R4 for the golden pilot task
``saleor-rc-7e42fc67ce72``.

WHY AN ADAPTER (never a modification):
- The frozen V2 rule text pins its candidate pool to "the FINAL corrected
  Mission-08 frozen DEV unchanged-test discovered nodes; no rediscovery".
  Applying V2 ordering/salt/caps to a NEWLY discovered MAIN pool is a
  prospective, outcome-blind EXTENSION of the rule's scope, so it is bound
  through this versioned adapter with explicit provenance pins. The frozen
  V2 module is NEVER modified.
- No outcome, pass/fail, model, arm or generated-patch information is used:
  selection is a pure function of candidate node ids + touched production
  paths + the frozen salt (same property as frozen V2).

Pins (frozen BEFORE any behavioral outcome of the pilot):
- task/commits: parent 798632158394c9f2911e6d36e8e424fd55007dc4,
  target 7e42fc67ce72770720440781fc83685a48bd91b8
- reused V2 identity: salt ``wp2-p2p-u-v2-2026-09-25``, caps 200 / 400,
  PROXIMAL>=2 / DISTAL<=1, file-hash + node-hash ordering, one-node-per-file
  round-robin, P,P,P,D interleave, first_200 subset first_400.

Evaluator-only: the candidate membership, node ids and all pins must stay
invisible to every generation/repair arm (same firewall as frozen V2).
"""

from __future__ import annotations

import hashlib
import json

from benchmark.wp2.p2p_inventory_v1 import associate_unchanged_test_files
from benchmark.wp2.p2p_u_v2 import (
    P2P_U_PRIMARY_CAP,
    P2P_U_SENSITIVITY_CAP,
    P2P_U_V2_SAMPLE_SALT,
    P2P_U_V2_VERSION,
    build_task_selection,
    canonical_sha256,
    changed_test_contamination,
    verify_task_selection,
)

P2P_U_PILOT_VERSION = "p2p-u-pilot-v1-2026-10-24"
PILOT_TASK_ID = "saleor-rc-7e42fc67ce72"
PILOT_PARENT_COMMIT = "798632158394c9f2911e6d36e8e424fd55007dc4"
PILOT_TARGET_COMMIT = "7e42fc67ce72770720440781fc83685a48bd91b8"

# Frozen V2 pins are REUSED unchanged.
REUSED_SALT = P2P_U_V2_SAMPLE_SALT
REUSED_PRIMARY_CAP = P2P_U_PRIMARY_CAP
REUSED_SENSITIVITY_CAP = P2P_U_SENSITIVITY_CAP

# B3 exclusions: these file kinds are never eligible candidate test files.
EXCLUDED_SUFFIXES = ("__init__.py", "conftest.py")
NON_TEST_FILE_MARKERS = ("cassettes/", "fixtures/", "/fixtures", "[", "]")


def sha256_text(text: str) -> str:
    """Canonical sha256 of a UTF-8 text blob (node lists etc.)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def membership_sha256(node_ids: list[str]) -> str:
    """Canonical sha256 over the SORTED node-id membership list."""
    return sha256_text(json.dumps(sorted(node_ids), ensure_ascii=False))


def collect_files_from_associated(associated_files: list[str]) -> list[str]:
    """Candidate .py test files from a V1-associated list (B3/B4 rule).

    Mirrors the frozen DEV47 collect-arg rule plus the mission B3 exclusions:
    - .py only (cassette YAML etc. are test-support, not candidates);
    - no ``[]`` parametrization markers (pytest cannot collect such paths);
    - exclude ``__init__.py`` and ``conftest.py``;
    - no fixture/cassette directories (test-support modules, not test files).
    """
    out: list[str] = []
    for f in sorted(associated_files):
        low = f.lower()
        if not f.endswith(".py"):
            continue
        if f.endswith(EXCLUDED_SUFFIXES):
            continue
        if any(m in low for m in NON_TEST_FILE_MARKERS):
            continue
        out.append(f)
    return out


def derive_candidate_files(
    *,
    touched_production_files: list[str],
    all_test_files: list[str],
    target_diff_paths: set[str],
) -> list[str]:
    """B3 candidate test file eligibility (outcome-blind, deterministic).

    - files unchanged by the target commit (not in ``target_diff_paths``);
    - same top-level Saleor app as a touched production file (frozen V1
      association rule, ``p2p_inventory_v1.associate_unchanged_test_files``);
    - conftest.py / __init__.py / cassettes / fixtures excluded.
    """
    associated = associate_unchanged_test_files(
        touched_production_files=touched_production_files,
        all_test_files=all_test_files,
        target_diff_paths=target_diff_paths,
    )
    return collect_files_from_associated(associated)


def build_pilot_selection(
    *,
    task_id: str = PILOT_TASK_ID,
    candidate_node_ids: list[str],
    touched_production_files: list[str],
    salt: str = REUSED_SALT,
    primary_cap: int = REUSED_PRIMARY_CAP,
    sensitivity_cap: int = REUSED_SENSITIVITY_CAP,
) -> dict[str, object]:
    """Apply the frozen V2 selection algorithm (UNCHANGED) to the MAIN pilot
    candidate pool and return a provenance-pinned selection record.

    ``salt`` and caps MUST stay on the frozen V2 values; passing different
    values is only for synthetic tests of the pin guard. The candidate pool is
    treated as a SET: ids are canonicalized (sorted, dedup-verified) at the
    adapter boundary so the selection record is a pure function of membership.
    """
    if sorted(candidate_node_ids) != sorted(set(candidate_node_ids)):
        raise ValueError("duplicate candidate node ids")
    selection = build_task_selection(
        task_id=task_id,
        candidate_node_ids=sorted(candidate_node_ids),
        touched_production_files=touched_production_files,
        salt=salt,
        primary_cap=primary_cap,
        sensitivity_cap=sensitivity_cap,
    )
    verify = verify_task_selection(selection)
    ordered = selection["ordered_node_ids"]
    dedup_ok = len(ordered) == len(set(ordered))
    return {
        "task_id": task_id,
        "adapter_version": P2P_U_PILOT_VERSION,
        "reused_v2_version": P2P_U_V2_VERSION,
        "salt": salt,
        "primary_cap": primary_cap,
        "sensitivity_cap": sensitivity_cap,
        "all_checks_pass": bool(verify["all_pass"] and dedup_ok),
        "verify_checks": verify,
        "selection": selection,
    }


def apply_pilot_freeze(
    *,
    candidate_node_ids: list[str],
    touched_production_files: list[str],
    parent_node_ids: list[str] | None = None,
    changed_test_files: list[str] | None = None,
) -> dict[str, object]:
    """Freeze the M19B-R4 pilot candidate artifact (B6/B7/B8).

    Fail-closed: raises ValueError on any structural violation (parent side
    mismatch, duplicates, changed-test contamination, changed salt/caps).
    """
    if sorted(candidate_node_ids) != sorted(set(candidate_node_ids)):
        raise ValueError("duplicate candidate node ids")
    if parent_node_ids is not None and sorted(parent_node_ids) != sorted(set(parent_node_ids)):
        raise ValueError("duplicate parent node ids")
    if parent_node_ids is not None and sorted(candidate_node_ids) != sorted(parent_node_ids):
        raise ValueError("parent/target node-set mismatch")
    contamination = changed_test_contamination(candidate_node_ids, changed_test_files or [])
    if contamination:
        raise ValueError(f"changed-test contamination: {contamination}")
    record = build_pilot_selection(
        candidate_node_ids=candidate_node_ids,
        touched_production_files=touched_production_files,
    )
    if not record["all_checks_pass"]:
        raise ValueError("frozen V2 verification failed for pilot selection")
    membership = {
        "artifact": "OPWS_P2P_U_CANDIDATES_PILOT",
        "artifact_version": P2P_U_PILOT_VERSION,
        "task_id": PILOT_TASK_ID,
        "parent_commit": PILOT_PARENT_COMMIT,
        "target_commit": PILOT_TARGET_COMMIT,
        "salt": REUSED_SALT,
        "primary_cap": REUSED_PRIMARY_CAP,
        "sensitivity_cap": REUSED_SENSITIVITY_CAP,
        "rule": (
            "unchanged-test P2P-U preservation oracle candidates for the MAIN "
            "pilot task; frozen V2 ordering/salt/caps applied prospectively "
            "by the additive pilot adapter; PASS requires 3/3 stable on "
            "parent AND on FULL_REFERENCE target (unchanged rule, frozen "
            "before any outcome)"
        ),
        "evaluator_only": True,
        "invisible_to_generation": True,
        "collected": record,
    }
    membership["membership_sha256"] = membership_sha256(candidate_node_ids)
    membership["payload_sha256"] = canonical_sha256(membership)
    return membership


__all__ = [
    "P2P_U_PILOT_VERSION",
    "PILOT_TASK_ID",
    "PILOT_PARENT_COMMIT",
    "PILOT_TARGET_COMMIT",
    "REUSED_SALT",
    "REUSED_PRIMARY_CAP",
    "REUSED_SENSITIVITY_CAP",
    "apply_pilot_freeze",
    "build_pilot_selection",
    "collect_files_from_associated",
    "derive_candidate_files",
    "membership_sha256",
    "sha256_text",
]
