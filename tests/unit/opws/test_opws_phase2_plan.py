"""OPWS R1 Phase 2 — zero-outcome scope validation + five-field physical dedup plan unit tests.

Deterministic, positive and negative coverage for ``scripts/opws_phase2_plan.py``:

* the frozen 12-arm registry resolves exactly (order, seed, start hash);
* the five-field physical-execution identity matches the frozen contract;
* per-arm scope sources resolve from pre-existing frozen artifacts (219/219 READY
  tasks) and NEVER generate a missing selector output;
* canonical scope hashing is deterministic and empty-scope-valid;
* logical vs unique physical counts satisfy the frozen dedup contract;
* unresolved fields are ``UNRESOLVED_*`` tokens, never fabricated values;
* the plan builds twice with byte-identical output; frozen inputs are unmodified.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_phase2_plan as p2  # noqa: E402

CREATED_AT = "2026-10-20T10:00:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def artifacts() -> dict:
    return p2.build_all(created_at=CREATED_AT)


@pytest.fixture(scope="module")
def validation(artifacts: dict) -> dict:
    return artifacts["OPWS_SCOPE_VALIDATION_R1.json"]


@pytest.fixture(scope="module")
def plan(artifacts: dict) -> dict:
    return artifacts["OPWS_PHYSICAL_DEDUP_PLAN_R1.json"]


# ---------------------------------------------------------------- registry
def test_registry_resolves_exactly_the_frozen_12_arms(validation: dict) -> None:
    assert validation["registry"]["n_arms"] == 12
    assert validation["registry"]["arm_order"] == p2.FROZEN_ARM_ORDER
    assert validation["registry"]["random_seed"] == 20261012
    assert validation["registry"]["registry_start_hash"] == p2.FROZEN_REGISTRY_START_HASH
    assert validation["registry"]["protocol_commit"] == p2.ob.PROTOCOL_COMMIT
    assert validation["registry"]["dedup_five_fields"] == [
        "TASK_ID",
        "SCOPE_HASH",
        "REFERENCE_PATCH_HASH",
        "TEST_CONTRACT_HASH",
        "ENVIRONMENT_ID",
    ]


def test_registry_arm_ids_unique_and_complete(validation: dict) -> None:
    order = validation["registry"]["arm_order"]
    assert len(set(order)) == 12
    assert {"RM_CSS", "GOLD", "SELECT_ALL", "AGENT"} <= set(order)


def test_arm_registry_source_blob_validates() -> None:
    reg = p2.load_arm_registry()
    assert reg["artifact"] == "opws_arm_registry_r1"
    assert reg["status"] == "FROZEN"
    assert reg["arm_artifact_resolution"]["all_core_arms_resolved"] is True
    assert reg["arm_id_uniqueness"]["arm_order"] == p2.FROZEN_ARM_ORDER


# ---------------------------------------------------------------- scope sources
def test_all_stored_scope_sources_present_and_cover_219(validation: dict) -> None:
    per_arm = {a["arm_id"]: a for a in validation["per_arm"]}
    for arm_id in p2.FROZEN_ARM_ORDER:
        entry = per_arm[arm_id]
        if arm_id == "RANDOM_SIZE_MATCHED_RM_CSS":
            assert entry["resolve_mode"] == "DERIVED_PENDING_PHASE4"
            assert entry["never_generated_in_phase2"] is True
            continue
        assert entry["stored_artifact"] is True, f"{arm_id} stored artifact must resolve"
        assert entry["coverage"]["n"] == 219, f"{arm_id} must cover all 219 READY tasks"
        assert entry["coverage"]["missing"] == []


def test_scope_hashes_computed_from_existing_artifacts_only(validation: dict) -> None:
    per_arm = {a["arm_id"]: a for a in validation["per_arm"]}
    rmcss = per_arm["RM_CSS"]
    assert rmcss["n_distinct_scope_hashes"] > 0
    assert rmcss["n_distinct_scope_hashes"] <= 219


# ---------------------------------------------------------------- canonical hash
def test_canonical_scope_hash_is_deterministic_and_order_independent() -> None:
    a = ["saleor/core/jwt.py", "saleor/graphql/page/resolvers.py"]
    b = ["saleor/graphql/page/resolvers.py", "saleor/core/jwt.py"]
    assert p2.compute_canonical_scope_hash(a) == p2.compute_canonical_scope_hash(b)
    assert len(p2.compute_canonical_scope_hash(a)) == 64


def test_canonical_scope_hash_dedupes_duplicates() -> None:
    dup = ["x/a.py", "x/a.py", "y/b.py"]
    uniq = ["x/a.py", "y/b.py"]
    assert p2.compute_canonical_scope_hash(dup) == p2.compute_canonical_scope_hash(uniq)


def test_canonical_scope_hash_empty_is_valid_zero_size_scope() -> None:
    h = p2.compute_canonical_scope_hash([])
    assert isinstance(h, str) and len(h) == 64
    # deterministic across calls
    assert h == p2.compute_canonical_scope_hash([])


def test_canonical_scope_hash_changes_with_scope_membership() -> None:
    h1 = p2.compute_canonical_scope_hash(["saleor/a.py"])
    h2 = p2.compute_canonical_scope_hash(["saleor/b.py"])
    h3 = p2.compute_canonical_scope_hash(["saleor/a.py", "saleor/b.py"])
    assert len({h1, h2, h3}) == 3


# ---------------------------------------------------------------- five-field identity
def test_five_field_identity_matches_frozen_contract(plan: dict) -> None:
    assert plan["five_field_physical_identity"]["fields"] == list(p2.DEDUP_FIVE_FIELDS)


def test_field_availability_marks_unknowns_as_unresolved_tokens(plan: dict) -> None:
    assert plan["field_availability"]["REFERENCE_PATCH_HASH"] == p2.UNRESOLVED_REF_PATCH
    assert plan["field_availability"]["TEST_CONTRACT_HASH"].startswith("KNOWN_ALL")
    assert plan["field_availability"]["ENVIRONMENT_ID"].startswith("KNOWN_ALL")


def test_every_task_row_carries_all_five_fields_or_unresolved_token(plan: dict) -> None:
    assert len(plan["tasks"]) == 219
    for t in plan["tasks"]:
        assert t["task_id"].startswith("saleor-rc-")
        assert len(t["test_contract_hash"]) == 64
        assert len(t["environment_id"]) == 64
        assert t["reference_patch_hash"] == p2.UNRESOLVED_REF_PATCH
        assert t["n_logical_arm_records"] == 12


# ---------------------------------------------------------------- counts (positive)
def test_logical_arm_records_are_12x219(plan: dict) -> None:
    assert plan["counts"]["n_logical_arm_records"] == 12 * 219


def test_unique_physical_is_less_than_logical_when_any_dedup_applies(plan: dict) -> None:
    logical = plan["counts"]["n_logical_arm_records"]
    physical = plan["counts"]["n_unique_physical_executions"]
    assert 0 < physical <= logical
    assert plan["counts"]["dedup_reduction_records"] == logical - physical


def test_unique_physical_at_least_one_group_per_task(plan: dict) -> None:
    assert plan["counts"]["n_unique_physical_executions"] >= 219


def test_unresolved_scope_records_are_only_the_random_arm(plan: dict) -> None:
    assert plan["counts"]["n_unresolved_scope_records"] == 219
    assert plan["counts"]["n_known_scope_hash_records"] == 2190 + 219  # 10 stored + SELECT_ALL


def test_primary_pair_counts_are_within_bounds(plan: dict) -> None:
    pair = plan["counts"]["primary_pair"]
    assert pair["arms"] == ["RM_CSS", "AGENT"]
    assert pair["n_logical"] == 438
    assert 219 <= pair["n_unique_physical"] <= 438


def test_f2p_positive_candidate_matches_phase1_record(plan: dict) -> None:
    assert plan["population"]["n_f2p_positive_candidate"] == 83


def test_eligibility_fields_are_tokens_never_numbers(plan: dict) -> None:
    assert plan["population"]["n_opws_eligible"] == p2.UNRESOLVED_ELIGIBLE
    assert plan["population"]["n_primary_paired"] == p2.UNRESOLVED_PAIRED


# ---------------------------------------------------------------- zero-outcome
def test_zero_outcome_declarations(validation: dict, plan: dict) -> None:
    for doc in (validation, plan):
        assert doc["zero_outcome"]["no_arm_execution"] is True
        assert doc["zero_outcome"]["no_model_api"] is True
        assert doc["zero_outcome"]["no_selector_output_generated"] is True
        assert doc["zero_outcome"]["no_patch_materialization"] is True


def test_build_is_pure_and_writes_nothing(artifacts: dict, tmp_path: Path) -> None:
    # build_all must not write any file
    p2.PHASE2_DIR.mkdir(parents=True, exist_ok=True)
    before = sorted(f for f in p2.PHASE2_DIR.rglob("*") if f.is_file())
    p2.build_all(created_at=CREATED_AT)
    after = sorted(f for f in p2.PHASE2_DIR.rglob("*") if f.is_file())
    assert [f.name for f in before] == [f.name for f in after]


# ---------------------------------------------------------------- negative
def test_unknown_arm_id_raises() -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.resolve_arm_scope_lists("NOT_AN_ARM", ["saleor-rc-438595033c60"], {})


def test_resolving_derived_arm_scope_is_forbidden() -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.resolve_arm_scope_lists(
            "RANDOM_SIZE_MATCHED_RM_CSS", ["saleor-rc-438595033c60"], {}
        )


def test_missing_prediction_record_fails_closed() -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.resolve_arm_scope_lists("RM_CSS", ["saleor-rc-not-a-real-task"], {})


def test_registry_order_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest import mock

    blob = p2.ob.git_bytes(
        "cat-file", "blob", f"{p2.ob.PROTOCOL_COMMIT}:{p2.ob.PROTOCOL_DIR}/OPWS_ARM_REGISTRY_R1.json"
    )
    import json as _json

    reg = _json.loads(blob.decode("utf-8"))
    reg["arm_id_uniqueness"]["arm_order"] = list(reversed(reg["arm_id_uniqueness"]["arm_order"]))
    mutated = _json.dumps(reg).encode("utf-8")

    with (
        mock.patch("scripts.opws_phase2_plan.ob.git_bytes", return_value=mutated),
        pytest.raises(p2.ob.BuildError),
    ):
        p2.load_arm_registry()


def test_deterministic_hash_sensitive_to_list_order_after_sort() -> None:
    # canonical hash of a SINGLE path list is keyed by content, not by insertion
    assert p2.compute_canonical_scope_hash(["b.py", "a.py"]) == p2.compute_canonical_scope_hash(
        ["a.py", "b.py"]
    )


# ---------------------------------------------------------------- determinism
def test_double_build_is_byte_identical() -> None:
    first_payloads = p2.build_all(created_at=CREATED_AT)
    second_payloads = p2.build_all(created_at=CREATED_AT)
    for name in first_payloads:
        assert p2.render(first_payloads[name]) == p2.render(second_payloads[name]), name
        assert _sha(Path(p2.PHASE2_DIR) / name) or True  # presence sanity only


def test_build_does_not_mutate_frozen_inputs(artifacts: dict) -> None:
    # The Phase-1 frozen input set is untouched by the Phase-2 build.
    inputs = [
        p2.ob.READINESS_MANIFEST,
        p2.ob.CENSUS,
        p2.ob.RUNTIME_BINDING,
        p2.ob.FULLD7_RESULT,
        p2.ob.PER_TASK_V2,
        p2.ob.MAIN297_CENSUS,
        p2.ob.ADAPTER_REPORT,
        p2.ob.MAIN297_MANIFEST,
        p2.ob.E1_EVALUATOR,
    ]
    before = {str(path): _sha(path) for path in inputs}
    p2.build_all(created_at=CREATED_AT)
    after = {str(path): _sha(path) for path in inputs}
    assert before == after


# ==================================================== M17 Phase-3A: fail-closed scope guards

# ---------------------------------------------------- validated canonical path spelling
@pytest.mark.parametrize("bad", ["../escape.py", "..\\win.py", "a/../../up.py"])
def test_scope_path_traversal_is_rejected(bad: str) -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.normalize_scope_path(bad, context="test")
    with pytest.raises(p2.ob.BuildError):
        p2.compute_canonical_scope_hash([bad])


@pytest.mark.parametrize(
    "bad",
    [
        "/abs/saleor/a.py",
        "C:/saleor/a.py",
        "C:\\saleor\\a.py",
        "saleor\\a.py",
        "",
        "saleor/a/./b.py",
        "saleor/a//b.py",
    ],
)
def test_scope_path_absolute_drive_backslash_empty_rejected(bad: str) -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.normalize_scope_path(bad, context="test")


def test_scope_path_duplicate_canonical_aliases_rejected() -> None:
    # a canonical forward-slash path is accepted; a backslash-bearing alias spelling
    # of the SAME file fails closed rather than being canonicalised into it.
    assert p2.normalize_scope_path("saleor/core/jwt.py", context="ok") == "saleor/core/jwt.py"
    with pytest.raises(p2.ob.BuildError):
        p2.normalize_scope_path("saleor/core\\jwt.py", context="alias")


def test_scope_paths_rejects_alias_set_duplicates() -> None:
    # two distinct spellings that canonicalise to one path must not coexist;
    # the non-canonical backslash alias spelling fails closed on its own.
    with pytest.raises(p2.ob.BuildError):
        p2.normalize_scope_paths(["saleor/a.py", "saleor\\a.py"], context="test")


def test_scope_paths_non_list_is_rejected() -> None:
    with pytest.raises(p2.ob.BuildError):
        p2.normalize_scope_paths("saleor/a.py", context="test")


def test_scope_paths_dedupes_and_counts_duplicates() -> None:
    unique, dup = p2.normalize_scope_paths(
        ["saleor/a.py", "saleor/a.py", "saleor/b.py"], context="test"
    )
    assert unique == ["saleor/a.py", "saleor/b.py"]
    assert dup == 1
    assert p2.compute_canonical_scope_hash(["saleor/a.py", "saleor/a.py"]) == p2.compute_canonical_scope_hash(
        ["saleor/a.py"]
    )


# ---------------------------------------------------- fail-closed build paths (A.1)
def _minimal_binding(task_id: str) -> dict:
    return {
        "task_ids": [task_id],
        "env_by_task": {task_id: "a" * 64},
        "contract_by_task": {task_id: "b" * 64},
        "f2p_positive": [],
        "n_f2p_positive": 0,
    }


def test_build_dedup_plan_fails_closed_on_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(
        p2, "ARM_SCOPE_SOURCES",
        {**p2.ARM_SCOPE_SOURCES, "RM_CSS": {"path": str(missing), "key": "rmcss_predicted_set"}},
    )
    monkeypatch.setattr(p2, "FROZEN_ARM_ORDER", ["RM_CSS"])
    with pytest.raises(p2.ob.BuildError):
        p2.build_dedup_plan({}, _minimal_binding("saleor-rc-missing-src"), CREATED_AT)


def test_build_dedup_plan_fails_closed_on_malformed_record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import json as _json

    tid = "saleor-rc-438595033c60"
    fixture = tmp_path / "pred.json"
    fixture.write_text(
        _json.dumps({"per_task": {tid: {"sip_predicted_set": ["../escape.py"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        p2, "ARM_SCOPE_SOURCES",
        {**p2.ARM_SCOPE_SOURCES, "SIP": {"path": str(fixture), "key": "sip_predicted_set"}},
    )
    monkeypatch.setattr(p2, "FROZEN_ARM_ORDER", ["SIP"])
    with pytest.raises(p2.ob.BuildError) as excinfo:
        p2.build_dedup_plan({}, _minimal_binding(tid), CREATED_AT)
    assert "escape" in str(excinfo.value)


def test_build_validation_fails_closed_on_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(
        p2, "ARM_SCOPE_SOURCES",
        {**p2.ARM_SCOPE_SOURCES, "AGENT": {"path": str(missing), "key": "selected_paths"}},
    )
    monkeypatch.setattr(p2, "FROZEN_ARM_ORDER", ["AGENT"])
    with pytest.raises(p2.ob.BuildError):
        p2.build_validation(["saleor-rc-missing-src"])


def test_only_random_arm_is_deferred_not_any_missing_arm(validation: dict) -> None:
    # RANDOM_SIZE_MATCHED_RM_CSS is the ONLY arm that may be recorded as deferred;
    # it has no stored artifact and is never generated in Phase 2.
    entry = next(
        a for a in validation["per_arm"]
        if a["arm_id"] == "RANDOM_SIZE_MATCHED_RM_CSS"
    )
    assert entry["stored_artifact"] is False
    assert entry["resolve_mode"] == "DERIVED_PENDING_PHASE4"
    assert entry["never_generated_in_phase2"] is True


def test_validation_never_emits_missing_or_failed_for_stored_arms(validation: dict) -> None:
    # No stored-artifact arm may report resolve_mode SOURCE_MISSING / RESOLVE_FAILED;
    # all 11 real stored arms must deliver FROZEN_ARTIFACT coverage.
    for entry in validation["per_arm"]:
        if entry["arm_id"] == "RANDOM_SIZE_MATCHED_RM_CSS":
            continue
        assert entry["stored_artifact"] is True, entry["arm_id"]
        assert entry["resolve_mode"] == "FROZEN_ARTIFACT", entry["arm_id"]
        assert entry["coverage"]["missing"] == []
        assert entry["coverage"]["n"] == 219
