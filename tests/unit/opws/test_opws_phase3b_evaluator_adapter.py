"""OPWS R1 Phase 3B — evaluator-adapter skeleton unit tests (synthetic fixtures).

Engineering only. None of these tests runs a behavior/preservation evaluator, WSL,
Docker, an API, or any real task; scientific PASS/FAIL classes are never produced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_phase3b_evaluator_adapter as ada  # noqa: E402
from scripts import opws_phase3b_patch_materialize as m  # noqa: E402

H64 = "c" * 64


# ---------------------------------------------------------------- instantiation
def test_instantiate_valid_contract() -> None:
    inst = ada.instantiate_contract(contract_hash=H64, node_ids=["n1", "n2"], environment_id="env-linux-1")
    assert inst.status == "INSTANTIATED"
    assert inst.test_contract_hash == H64
    assert inst.node_ids == ("n1", "n2")
    assert len(inst.instantiation_id) == 64


@pytest.mark.parametrize(
    "kwargs",
    [
        {"contract_hash": "not-a-hash", "node_ids": ["n1"]},
        {"contract_hash": "", "node_ids": ["n1"]},
        {"contract_hash": "G" * 64, "node_ids": ["n1"]},
        {"contract_hash": H64, "node_ids": []},
        {"contract_hash": H64, "node_ids": ["n1", ""]},
    ],
)
def test_bad_contract_hash_or_node_list_is_test_contract_invalid(kwargs: dict) -> None:
    with pytest.raises(ada.ContractNotInstantiatedError):
        ada.instantiate_contract(**kwargs)


def test_bad_environment_id_rejected() -> None:
    with pytest.raises(ada.BadEnvironmentIdentityError):
        ada.instantiate_contract(contract_hash=H64, node_ids=["n1"], environment_id="bad\x00env")


# ---------------------------------------------------------------- no behavior in M18
def test_evaluate_behavior_never_runs_in_m18() -> None:
    inst = ada.instantiate_contract(contract_hash=H64, node_ids=["n1"])
    with pytest.raises(ada.BehavioralEvaluationNotAuthorizedError):
        ada.evaluate_behavior(inst, Path("/unused"))
    # the adapter's own records must carry no scientific class in M18
    summary = ada.guard_non_scientific(
        [{"record_id": "r1", "outcome_class": "NOT_APPLIED_INVALID_UNOBSERVED"}]
    )
    assert summary["scientific_violations"] == 0


# ---------------------------------------------------------------- common tests once
def test_common_tests_applied_exactly_once_by_contract_hash() -> None:
    records = [
        {"record_id": "a1", "test_contract_hash": H64, "node_ids": ["n1"]},
        {"record_id": "a2", "test_contract_hash": H64, "node_ids": ["n1"]},  # same contract
        {"record_id": "b1", "test_contract_hash": "d" * 64, "node_ids": ["n9"]},
        {"record_id": "c1", "test_contract_hash": "not-a-hash", "node_ids": ["n1"]},
    ]
    plan = ada.apply_common_tests_once(records)
    assert plan["n_records"] == 4
    assert plan["n_valid_hashes"] == 3
    assert plan["n_instantiations"] == 2  # two distinct contracts, applied once each
    assert [r["test_contract_hash"] for r in plan["instantiations"]] == sorted([H64, "d" * 64])
    assert plan["instantiations"][0]["n_logical_records"] == 2  # deduped onto one instantiation
    assert len(plan["invalid_records"]) == 1
    assert plan["invalid_records"][0]["record_id"] == "c1"


# ---------------------------------------------------------------- R1.1 PROPOSED control records
def test_control_records_are_proposed_and_arm_ids_unchanged() -> None:
    records = ada.r11_proposed_control_records()
    ids = [r.arm_id for r in records]
    assert ids == ["NEG", "FULL_REFERENCE", "GOLD", "GOLD_PROXY", "SELECT_ALL"]
    assert all(r.status == "PROPOSED_R11" for r in records)
    # frozen GOLD / SELECT_ALL sources are preserved verbatim in the proposal
    gold = next(r for r in records if r.arm_id == "GOLD")
    assert gold.source == "research/saleor-reserve-300-rmcss/saleor_reserve_300_proxies.json"
    sa = next(r for r in records if r.arm_id == "SELECT_ALL")
    assert "candidate_universe.json" in sa.source
    # each control may be serialized
    as_dict = gold.as_dict()
    assert as_dict["arm_id"] == "GOLD" and as_dict["status"] == "PROPOSED_R11"


# ---------------------------------------------------------------- engineering taxonomy
def test_classification_never_emits_scientific_classes() -> None:
    errors = [
        ada.ContractNotInstantiatedError("x"),
        ada.InconsistentTestPatchIdentityError("x"),
        ada.UnsupportedFileStatusError("x"),
        ada.EnvironmentNotMaterializedError("x"),
        ada.BadEnvironmentIdentityError("x"),
        m.ScopePathInvalidError("x"),
        m.UnsupportedStatusError("x"),
        m.GitObjectIdentityError("x"),
        m.SymlinkPathError("x"),
        m.OutputTooLargeError("x"),
        m.GitCommandError("x"),
        RuntimeError("unexpected"),
    ]
    for exc in errors:
        cls = ada.classify_engineering_failure(exc)["taxonomy_class"]
        assert cls not in ada.SCIENTIFIC_CLASSES, f"{type(exc).__name__} -> {cls}"
        assert cls in ada.ENGINEERING_CLASSES, f"{type(exc).__name__} -> {cls}"


def test_apply_check_classification_is_patch_conflict_never_behavioral() -> None:
    bad = ada.classify_apply_check(ok=False, stderr="error: patch does not apply")
    assert bad["taxonomy_class"] == "PATCH_APPLICATION_INVALID"
    good = ada.classify_apply_check(ok=True, stderr="")
    assert good["taxonomy_class"] == "NOT_APPLIED_INVALID_UNOBSERVED"


# ---------------------------------------------------------------- physical identity
def test_physical_identity_requires_all_five_fields() -> None:
    a = m.physical_execution_identity(
        task_id="t1", scope_hash="a" * 64, reference_patch_hash="b" * 64,
        test_contract_hash="c" * 64, environment_id="env1",
    )
    b = m.physical_execution_identity(
        task_id="t1", scope_hash="a" * 64, reference_patch_hash="b" * 64,
        test_contract_hash="c" * 64, environment_id="env1",
    )
    c = m.physical_execution_identity(
        task_id="t1", scope_hash="a" * 64, reference_patch_hash="b" * 64,
        test_contract_hash="c" * 64, environment_id="env2",
    )
    assert a == b
    assert a["physical_execution_id"] == b["physical_execution_id"]
    assert a["physical_execution_id"] != c["physical_execution_id"]  # ENVIRONMENT_ID differs


def test_equal_patch_hash_different_scope_is_two_physical_executions() -> None:
    plan = m.plan_physical_dedup(
        [
            {"record_id": "r1", "arm_id": "GOLD", **m.physical_execution_identity(
                task_id="t1", scope_hash="s1", reference_patch_hash="p1",
                test_contract_hash=H64, environment_id="e1")},
            {"record_id": "r2", "arm_id": "SELECT_ALL", **m.physical_execution_identity(
                task_id="t1", scope_hash="s2",  # different scope, same patch hash p1
                reference_patch_hash="p1", test_contract_hash=H64, environment_id="e1")},
        ]
    )
    assert plan["n_physical_executions"] == 2


def test_identical_five_tuple_shares_one_physical_execution() -> None:
    plan = m.plan_physical_dedup(
        [
            {"record_id": "r1", "arm_id": "A", **m.physical_execution_identity(
                task_id="t1", scope_hash="s1", reference_patch_hash="p1",
                test_contract_hash=H64, environment_id="e1")},
            {"record_id": "r2", "arm_id": "B", **m.physical_execution_identity(
                task_id="t1", scope_hash="s1", reference_patch_hash="p1",
                test_contract_hash=H64, environment_id="e1")},
        ]
    )
    assert plan["n_logical_records"] == 2
    assert plan["n_physical_executions"] == 1
    assert plan["physical_executions"][0]["dedup_reason"] == "FIVE_FIELDS_EQUAL"
    assert plan["physical_executions"][0]["logical_arm_ids"] == ["A", "B"]
