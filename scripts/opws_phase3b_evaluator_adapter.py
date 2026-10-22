"""OPWS R1 Phase 3B — test-contract / environment-identity evaluator adapter skeleton.

ENGINEERING ONLY. This adapter's inputs are immutable contract hashes, run identifiers,
node lists and parent-commit identifiers. In M18 there is **no live Docker/WSL execution
on real tasks**: the behavioral evaluation entry point always closes with
``BehavioralEvaluationNotAuthorizedError`` and scientific PASS/FAIL states remain
**UNOBSERVED**. The adapter's only jobs in this mission are:

1. Distinguish a failure to *instantiate* a contract (``TEST_CONTRACT_INVALID``) from a
   *behavioral* failure (which cannot exist in M18).
2. Provide the R1.1 **PROPOSED** control-record interface (NEG, FULL_REFERENCE,
   ORIGINAL_R1_GOLD/GOLD_PROXY, SELECT_ALL) **without changing any frozen arm ID, frozen
   source or denominator**.
3. Map engineering failures onto the frozen outcome taxonomy's invalid/contract classes
   (``OPWS_OUTCOME_TAXONOMY_R1.json``), and assert that scientific classes are never
   emitted by engineering code.
4. Apply the common behavior contract **exactly once** in the synthetic fixture model
   (deduplicated on the frozen ``TEST_CONTRACT_HASH``).
5. Reuse the frozen five-component physical-execution identity tuple from the
   materializer (equal patch hashes alone are never permission to deduplicate different
   scopes; logical records are reported separately from physical execution opportunities).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_BOOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_BOOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_BOOT))

from scripts import opws_phase3b_patch_materialize as mat  # noqa: E402

ADAPTER_SCHEMA = "opws-phase3b-evaluator-adapter/1.0-engineering"

# Frozen scientific classes (OPWS_OUTCOME_TAXONOMY_R1.json) — engineering code must
# never produce one in M18.
SCIENTIFIC_CLASSES = frozenset(
    {"OPWS_PASS", "BEHAVIOR_FAIL", "PRESERVATION_FAIL", "BEHAVIOR_AND_PRESERVATION_FAIL"}
)

# Frozen invalid/contract classes this adapter may legitimately classify engineering
# failures into.
ENGINEERING_CLASSES = frozenset(
    {
        "PATCH_APPLICATION_INVALID",
        "TEST_CONTRACT_INVALID",
        "ENVIRONMENT_INVALID",
        "INFRASTRUCTURE_TRANSIENT",
        "INFRASTRUCTURE_FATAL",
        "ARM_PREDICTION_INVALID",
        "OPWS_INVALID_CONTROL_FAILURE",
        "UNKNOWN_FAIL_CLOSED",
    }
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------ errors
class AdapterError(RuntimeError):
    """Base class for adapter engineering failures (never a scientific outcome)."""


class ContractNotInstantiatedError(AdapterError):
    """The frozen behavior/preservation contract cannot be instantiated.

    Maps to frozen ``TEST_CONTRACT_INVALID`` (INVALID_CONTRACT). This is distinct from
    any behavioral failure — behavioral failures are UNOBSERVED in M18.
    """


class BehavioralEvaluationNotAuthorizedError(AdapterError):
    """No behavioral/preservation evaluation may run in M18 (fail closed)."""


class EnvironmentNotMaterializedError(AdapterError):
    """The frozen environment cannot be materialized idempotently (ENVIRONMENT_INVALID)."""


class BadEnvironmentIdentityError(AdapterError):
    """ENVIRONMENT_ID does not match the frozen identity contract (malformed)."""


class InconsistentTestPatchIdentityError(AdapterError):
    """A control record's TEST_CONTRACT_HASH disagrees with its test-patch hash."""

    # Maps to TEST_CONTRACT_INVALID (or HARNESS_CONSISTENCY category for GOLD vs
    # SELECT_ALL disagreement) — never a selector failure.


class UnsupportedFileStatusError(AdapterError):
    """A changed-file classification uses a status outside the frozen R1 set."""


class UnknownFailClosedError(AdapterError):
    """Unclassifiable engineering failure; owner review required (UNKNOWN_FAIL_CLOSED)."""


# ------------------------------------------------------------------ identity format guards
def require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _HEX64.match(value):
        raise ContractNotInstantiatedError(f"{label}: not a 64-hex sha256: {value!r}")
    return value


def require_environment_id(value: str, label: str = "ENVIRONMENT_ID") -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BadEnvironmentIdentityError(f"{label}: malformed environment identity {value!r}")
    return value


# ------------------------------------------------------------------ contract instantiation
@dataclass(frozen=True)
class ContractInstance:
    """A resolved, instantiable test contract (M18: no behavior runs on it)."""

    test_contract_hash: str
    node_ids: tuple[str, ...]
    instantiation_id: str
    contract_kind: str  # e.g. "F2P_BEHAVIOR", "P2P_PRESERVATION", "COMMON_TEST"
    status: str = "INSTANTIATED"

    def as_dict(self) -> dict[str, str]:
        return {
            "test_contract_hash": self.test_contract_hash,
            "node_ids": json.dumps(list(self.node_ids), separators=(",", ":")),
            "instantiation_id": self.instantiation_id,
            "contract_kind": self.contract_kind,
            "status": self.status,
        }


def instantiate_contract(
    *,
    contract_hash: str,
    node_ids: list[str],
    contract_kind: str = "COMMON_TEST",
    environment_id: str | None = None,
) -> ContractInstance:
    """Instantiation boundary: immutable contract hash + node list -> instance.

    Fails closed with ``ContractNotInstantiatedError`` (TEST_CONTRACT_INVALID) for a
    malformed hash, an empty/malformed node list, or a bad environment id. A resolved
    instance still carries **no behavioral result** — evaluating it is unauthorized in
    M18 (see :func:`evaluate_behavior`).
    """
    require_sha256(contract_hash, "contract_hash")
    if not isinstance(node_ids, list) or len(node_ids) == 0 or any(
        not isinstance(n, str) or not n for n in node_ids
    ):
        raise ContractNotInstantiatedError(
            f"node list must be a non-empty list of non-empty strings, got {node_ids!r}"
        )
    if environment_id is not None:
        require_environment_id(environment_id)
    ident = mat.physical_execution_identity(
        task_id="__contract_only__",
        scope_hash="",
        reference_patch_hash="",
        test_contract_hash=contract_hash,
        environment_id=environment_id or "ENV_UNBOUND",
    )["physical_execution_id"]
    return ContractInstance(
        test_contract_hash=contract_hash,
        node_ids=tuple(node_ids),
        instantiation_id=ident,
        contract_kind=contract_kind,
    )


def evaluate_behavior(instance: ContractInstance, worktree: Path) -> dict[str, Any]:
    """No-op boundary that MUST fail closed in M18.

    Even a validly instantiated contract can not be behaviorally evaluated in this
    mission: scientific PASS/FAIL must remain UNOBSERVED. Real evaluation is a future
    owner-authorized mission (STAGE_5 inside Linux). This function always raises
    :class:`BehavioralEvaluationNotAuthorizedError`.
    """
    # The parameters exist for interface continuity; no real evaluation is possible.
    del instance, worktree
    raise BehavioralEvaluationNotAuthorizedError(
        "behavioral evaluation is NOT AUTHORIZED in M18; scientific outcomes stay UNOBSERVED"
    )


# ------------------------------------------------------------------ common tests exactly once
def apply_common_tests_once(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Synthetic-fixture model: apply a common test contract exactly once per task.

    Deduplicates on the frozen TEST_CONTRACT_HASH: identical contracts share one
    physical instantiation; an arm-record list is returned per hash. Records with
    different hashes are never merged even if node lists look similar (frozen identity
    over downloaded hashes, not content recall).
    """
    by_hash: dict[str, list[dict[str, Any]]] = {}
    hash_ok = 0
    hash_bad: list[dict[str, Any]] = []
    for rec in records:
        h = rec.get("test_contract_hash")
        try:
            require_sha256(str(h), "test_contract_hash")
        except (ContractNotInstantiatedError, ValueError):
            hash_bad.append({"record_id": rec.get("record_id"), "reason": "INVALID_TEST_CONTRACT_HASH"})
            continue
        hash_ok += 1
        by_hash.setdefault(str(h), []).append(rec)
    instantiations: list[dict[str, Any]] = []
    for h in sorted(by_hash):
        inst = instantiate_contract(
            contract_hash=h,
            node_ids=by_hash[h][0].get("node_ids") or ["node_placeholder"],
        )
        instantiations.append(
            {
                "test_contract_hash": h,
                "instantiation_id": inst.instantiation_id,
                "n_logical_records": len(by_hash[h]),
                "logical_record_ids": [r.get("record_id") for r in by_hash[h]],
                "applied_once": len(by_hash[h]) > 0,
            }
        )
    return {
        "n_records": len(records),
        "n_valid_hashes": hash_ok,
        "n_instantiations": len(instantiations),
        "invalid_records": hash_bad,
        "instantiations": instantiations,
    }


# ------------------------------------------------------------------ R1.1 PROPOSED control records
@dataclass(frozen=True)
class ControlRecord:
    """A R1.1 PROPOSED control record. Never changes frozen arm IDs or sources."""

    control_id: str
    arm_id: str  # frozen arm id, unchanged (GOLD / SELECT_ALL), or PROPOSED label
    role: str
    description: str
    source: str
    status: str = "PROPOSED_R11"
    scientific_allowed: bool = False

    def as_dict(self) -> dict[str, str]:
        return {
            "control_id": self.control_id,
            "arm_id": self.arm_id,
            "role": self.role,
            "description": self.description,
            "source": self.source,
            "status": self.status,
            "scientific_allowed": str(self.scientific_allowed),
        }

def r11_proposed_control_records() -> list[ControlRecord]:
    """The PROPOSED R1.1 control-record interface (M18 item C.9).

    * NEG — parent state + the common test contract (no reference patch at all).
    * FULL_REFERENCE — complete historical non-test patch + the same common tests
      (PROPOSED R1.1 diagnostic; NOT the old GOLD arm).
    * ORIGINAL_R1_GOLD / GOLD_PROXY — unchanged frozen proxy scope source (GOLD).
    * SELECT_ALL — unchanged frozen selectable universe (ceiling control).

    All records are PROPOSED_R11; none of them changes the frozen arm IDs, frozen scope
    sources, or scientific denominators.
    """
    return [
        ControlRecord(
            control_id="CTRL-NEG",
            arm_id="NEG",
            role="NEGATIVE_CONTROL",
            description=(
                "parent state materialized with the common test contract and NO reference "
                "patch; any change from parent is an instrument artifact"
            ),
            source="PROPOSED_R11_PARENT_OBJECTS",
        ),
        ControlRecord(
            control_id="CTRL-FULL_REFERENCE",
            arm_id="FULL_REFERENCE",
            role="PROPOSED_R11_DIAGNOSTIC",
            description=(
                "complete historical non-test reference patch (derived from parent/target "
                "git name-status minus test files) + the same common tests; proposed "
                "owner-approved replacement diagnostic, never silently GOLD"
            ),
            source="PROPOSED_R11_GIT_OBJECTS_DERIVED",
        ),
        ControlRecord(
            control_id="CTRL-GOLD",
            arm_id="GOLD",
            role="DIAGNOSTIC_ONLY",
            description="frozen historical gold proxy scope source (evaluation-only), unchanged",
            source="research/saleor-reserve-300-rmcss/saleor_reserve_300_proxies.json",
        ),
        ControlRecord(
            control_id="CTRL-GOLD_PROXY",
            arm_id="GOLD_PROXY",
            role="ALIAS_OF_FROZEN_GOLD",
            description="explicit alias label for the same frozen proxy source as GOLD",
            source="research/saleor-reserve-300-rmcss/saleor_reserve_300_proxies.json",
        ),
        ControlRecord(
            control_id="CTRL-SELECT_ALL",
            arm_id="SELECT_ALL",
            role="CEILING_CONTROL",
            description="frozen selectable repository-file universe, unchanged",
            source="benchmark_data/real_commit_impact_saleor/scientific/<task>/public/candidate_universe.json",
        ),
    ]


# ------------------------------------------------------------------ engineering failure taxonomy
def classify_engineering_failure(exc: BaseException) -> dict[str, str]:
    """Map an engineering failure onto the R1.1 fail-closed engineering taxonomy.

    Scientific codes (OPWS_PASS, BEHAVIOR_FAIL, PRESERVATION_FAIL,
    BEHAVIOR_AND_PRESERVATION_FAIL) are never produced here.
    """
    if isinstance(exc, ContractNotInstantiatedError):
        return {"engineering_code": "ERROR_TEST_CONTRACT", "taxonomy_class": "TEST_CONTRACT_INVALID"}
    if isinstance(exc, InconsistentTestPatchIdentityError):
        return {"engineering_code": "ERROR_INCONSISTENT_TEST_PATCH_ID", "taxonomy_class": "TEST_CONTRACT_INVALID"}
    if isinstance(exc, UnsupportedFileStatusError):
        return {"engineering_code": "ERROR_UNSUPPORTED_FILE_STATUS", "taxonomy_class": "ARM_PREDICTION_INVALID"}
    if isinstance(exc, mat.ScopePathInvalidError):
        return {"engineering_code": "ERROR_INVALID_PREDICTION_PATH", "taxonomy_class": "ARM_PREDICTION_INVALID"}
    if isinstance(exc, mat.UnsupportedStatusError):
        return {"engineering_code": "ERROR_UNSUPPORTED_FILE_STATUS", "taxonomy_class": "ARM_PREDICTION_INVALID"}
    if isinstance(exc, (EnvironmentNotMaterializedError, BadEnvironmentIdentityError)):
        return {"engineering_code": "ERROR_BAD_ENVIRONMENT", "taxonomy_class": "ENVIRONMENT_INVALID"}
    if isinstance(exc, mat.GitObjectIdentityError):
        return {"engineering_code": "ERROR_OBJECT_IDENTITY", "taxonomy_class": "INFRASTRUCTURE_FATAL"}
    if isinstance(exc, mat.SymlinkPathError):
        return {"engineering_code": "ERROR_SYMLINK_PATH", "taxonomy_class": "PATCH_APPLICATION_INVALID"}
    if isinstance(exc, mat.OutputTooLargeError):
        return {"engineering_code": "ERROR_UNEXPECTED_OUTPUT", "taxonomy_class": "INFRASTRUCTURE_FATAL"}
    if isinstance(exc, mat.GitCommandError):
        return {"engineering_code": "ERROR_GIT_COMMAND", "taxonomy_class": "INFRASTRUCTURE_FATAL"}
    return {"engineering_code": "ERROR_UNKNOWN", "taxonomy_class": "UNKNOWN_FAIL_CLOSED"}


def classify_apply_check(ok: bool, stderr: str) -> dict[str, str]:
    """Classify a fixture-only ``git apply --check`` result.

    A failed apply is ``PATCH_APPLICATION_INVALID`` (frozen taxonomy: patch rejects/
    conflicts on the frozen parent state); it is **never** a behavioral signal.
    """
    if ok:
        return {"engineering_code": "APPLY_OK", "taxonomy_class": "NOT_APPLIED_INVALID_UNOBSERVED"}
    return {
        "engineering_code": "ERROR_PATCH_CONFLICT",
        "taxonomy_class": "PATCH_APPLICATION_INVALID",
        "stderr_tail": stderr[-400:],
    }


def guard_non_scientific(records: list[dict[str, str]]) -> dict[str, Any]:
    """Assert engineering records never carry a scientific class in M18 (fail closed)."""
    violations = [r for r in records if r.get("outcome_class") in SCIENTIFIC_CLASSES]
    return {
        "records_checked": len(records),
        "scientific_violations": len(violations),
        "scientific_classes_must_be_unobserved": True,
    }


# ------------------------------------------------------------------ CLI (engineering demo only)
def _cli() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="opws_phase3b_evaluator_adapter",
        description="Engineering-only evaluator-adapter skeleton (M18: no behavior runs).",
    )
    ap.add_argument("--contract-hash", required=True, help="frozen test-contract sha256")
    ap.add_argument("--node-ids", required=True, help="comma-separated frozen F2P node ids")
    ap.add_argument("--env-id", help="ENVIRONMENT_ID (validated, optional)")
    ap.add_argument("--dry-run", action="store_true", help="instantiate + classify only, no evaluation")
    args = ap.parse_args()
    inst = instantiate_contract(
        contract_hash=args.contract_hash,
        node_ids=[n for n in args.node_ids.split(",") if n],
        environment_id=args.env_id,
    )
    print(json.dumps(inst.as_dict(), sort_keys=True, separators=(",", ":")))
    if args.dry_run:
        return 0
    try:
        evaluate_behavior(inst, Path("."))
    except BehavioralEvaluationNotAuthorizedError as exc:
        print(f"UNOBSERVED={str(exc)}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
