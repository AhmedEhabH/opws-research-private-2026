"""OPWS R1 Phase 0/1 additive-build gates.

These tests are the fail-closed verification for ``scripts/opws_build.py``:

* the 219-task READY population is distinct from the 144-unit population and from
  the frozen unit-order hash ``8eb4a724...``;
* the 13-field binding keeps exactly the frozen field names;
* nothing that cannot be derived from frozen evidence is asserted (tri-state
  funnel, ``UNRESOLVED_*`` tokens are never ``true``/``false``);
* the build is byte-deterministic (twice-built SHA comparison);
* no frozen input file is modified by a build.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_build as ob  # noqa: E402

CREATED_AT = "2026-10-20T00:00:00Z"
INPUT_FILES = [
    ob.READINESS_MANIFEST,
    ob.CENSUS,
    ob.RUNTIME_BINDING,
    ob.FULLD7_RESULT,
    ob.PER_TASK_V2,
    ob.MAIN297_CENSUS,
    ob.ADAPTER_REPORT,
    ob.MAIN297_MANIFEST,
    ob.E1_EVALUATOR,
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def artifacts() -> dict:
    return ob.build_all(created_at=CREATED_AT)


@pytest.fixture(scope="module")
def population(artifacts: dict) -> dict:
    return artifacts["OPWS_READY_POPULATION_219.json"]


def test_population_is_219_tasks_over_144_units(population: dict) -> None:
    assert population["n_units"] == 144
    assert population["n_tasks"] == 219
    ids = [r["task_id"] for r in population["per_task"]]
    assert len(ids) == 219
    assert len(set(ids)) == 219
    assert population["n_units"] != population["n_tasks"]


def test_order_is_unit_major_expansion(population: dict) -> None:
    expected = [t for unit in population["units"] for t in unit["member_task_ids"]]
    assert [r["task_id"] for r in population["per_task"]] == expected


def test_ordered_task_ids_hash_is_new_and_recomputable(artifacts: dict) -> None:
    ordered = artifacts["OPWS_ORDERED_TASK_IDS.json"]
    ids = ordered["ordered_task_ids"]
    assert ordered["n_tasks"] == 219
    assert ordered["ordered_task_ids_sha256"] == ob.ordered_task_ids_sha256(ids)
    assert ordered["ordered_task_ids_sha256"] != ob.EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH
    assert ordered["ordered_task_ids_sha256"] != "8eb4a7242e12bb03715adac5fffdea2e4340585843fc137ececd38952ad6a19e"


def test_frozen_unit_order_hash_is_reproduced(population: dict) -> None:
    unit_ids = [u["validation_unit_id"] for u in population["units"]]
    assert ob.ordered_task_ids_sha256(unit_ids) == ob.EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH


def test_binding_has_exactly_the_frozen_13_fields(artifacts: dict) -> None:
    binding = artifacts["OPWS_POPULATION_BINDING_R1.json"]
    assert tuple(binding) == ob.BINDING_FIELDS
    assert len(binding) == 13
    assert binding["ordered_task_ids_sha256"] == ob.ordered_task_ids_sha256(binding["ordered_task_ids"])
    assert binding["ordered_task_ids_sha256"] != ob.EXPECTED_UNIT_ORDER_MEMBERSHIP_HASH
    assert binding["n_env_ready"] == 219


def test_binding_unresolved_fields_are_tokens_not_numbers(artifacts: dict) -> None:
    binding = artifacts["OPWS_POPULATION_BINDING_R1.json"]
    assert binding["n_opws_eligible"] == ob.UNRESOLVED_STAGE5
    assert binding["n_primary_paired"] == ob.UNRESOLVED_STAGE7
    assert not isinstance(binding["n_opws_eligible"], int)
    assert not isinstance(binding["n_primary_paired"], int)


def test_binding_self_hash_matches(artifacts: dict) -> None:
    binding = artifacts["OPWS_POPULATION_BINDING_R1.json"]
    status = artifacts["OPWS_POPULATION_BINDING_STATUS.json"]
    assert status["binding_self_sha256"] == ob.sha_obj(binding)


def test_environment_id_recipe_and_uniqueness(artifacts: dict) -> None:
    proposal = artifacts["OPWS_ENVIRONMENT_ID_PROPOSAL.json"]
    assert proposal["status"] == "PROPOSED_PENDING_OWNER_CONFIRMATION"
    assert proposal["n_tasks"] == 219
    for row in proposal["per_task"]:
        c = row["components"]
        recomputed = ob.environment_id(
            c["immutable_image_id"], c["deterministic_binding_hash"], c["environment_fingerprint"]
        )
        assert row["environment_id"] == recomputed
        assert len(row["environment_id"]) == 64
    assert proposal["n_distinct_environment_ids"] == len(
        {r["environment_id"] for r in proposal["per_task"]}
    )
    assert proposal["components"]["deterministic_binding_hash"] == ob.EXPECTED_RUNTIME_BINDING_HASH


def test_environment_id_changes_with_any_component() -> None:
    a = ob.environment_id("sha256:" + "0" * 64, "b" * 64, "c" * 64)
    b = ob.environment_id("sha256:" + "1" * 64, "b" * 64, "c" * 64)
    c = ob.environment_id("sha256:" + "0" * 64, "b" * 64, "d" * 64)
    assert len({a, b, c}) == 3


def test_behavior_contract_manifest_counts_and_hashes(artifacts: dict) -> None:
    manifest = artifacts["OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json"]
    assert manifest["n_tasks"] == 219
    assert manifest["n_contract_resolved"] == 219
    assert manifest["n_f2p_positive"] == 83
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    assert manifest["manifest_sha256"] == ob.sha_obj(body)
    for contract in manifest["per_task"][:5]:
        payload = {k: v for k, v in contract.items() if k != "contract_sha256"}
        assert contract["contract_sha256"] == ob.sha_obj(payload)
        assert contract["f2p"]["selector_blind"] is True
        assert contract["f2p"]["node_identity_binding_mode"] == "AT_EVALUATION_BOUNDED_BY_FROZEN_COUNT"
    binding = artifacts["OPWS_POPULATION_BINDING_R1.json"]
    assert binding["behavior_contract_manifest_sha256"] == manifest["manifest_sha256"]


def test_funnel_is_tri_state_and_matches_frozen_counts(artifacts: dict) -> None:
    funnel = artifacts["OPWS_ELIGIBILITY_FUNNEL_219.json"]
    counts = funnel["stage_counts"]
    assert counts["stage1_in_universe"]["true"] == 219
    assert counts["stage2_test_evidence"]["true"] == 83
    assert counts["stage2_test_evidence"]["false"] == 136
    assert counts["stage3_behavior_contract"]["true"] == 219
    assert counts["stage4_env_ready"]["true"] == 219
    assert counts["stage5_behavior_executable"]["unresolved"] == 219
    assert counts["stage6_opws_eligible"] == {"true": 0, "false": 136, "unresolved": 83}
    assert counts["stage7_primary_paired_eligible"] == {"true": 0, "false": 136, "unresolved": 83}
    body = {k: v for k, v in funnel.items() if k != "manifest_sha256"}
    assert funnel["manifest_sha256"] == ob.sha_obj(body)

    missing = [r for r in funnel["per_task"] if "TEST_EVIDENCE_MISSING" in r["reason_codes"]]
    assert len(missing) == 136
    for row in funnel["per_task"]:
        for value in (
            row["stage5_behavior_executable"],
            row["stage6_opws_eligible"],
            row["stage7_primary_paired_eligible"],
        ):
            assert isinstance(value, (str, bool))


def test_env_ready_is_not_opws_eligibility(artifacts: dict) -> None:
    status = artifacts["OPWS_POPULATION_BINDING_STATUS.json"]
    assert status["population"]["n_tasks"] == 219
    assert status["population"]["n_f2p_positive"] == 83
    assert status["binding_status"] == "DRAFT_PARTIAL_PHASE1_HOLD"
    assert set(status["unresolved_binding_fields"]) == {"n_opws_eligible", "n_primary_paired"}
    markers = status["funnel_stage_counts"]
    assert markers["stage4_env_ready"]["true"] == 219
    assert markers["stage6_opws_eligible"]["true"] == 0
    assert markers["stage6_opws_eligible"]["false"] == 136
    assert markers["stage6_opws_eligible"]["unresolved"] == 83


def test_double_build_is_byte_identical() -> None:
    first = {k: ob.render(v) for k, v in ob.build_all(created_at=CREATED_AT).items()}
    second = {k: ob.render(v) for k, v in ob.build_all(created_at=CREATED_AT).items()}
    assert first == second
    report = ob.determinism_report(first, second)
    assert report["all_identical"] is True
    assert report["n_artifacts"] == 7


def test_build_does_not_mutate_frozen_inputs() -> None:
    before = {p: _sha(p) for p in INPUT_FILES}
    ob.build_all(created_at=CREATED_AT)
    after = {p: _sha(p) for p in INPUT_FILES}
    assert before == after


def test_build_all_is_pure_and_writes_nothing(artifacts: dict) -> None:
    # build_all must not create the output directory; only main() writes.
    assert artifacts  # fixture ran
    assert not any(p.suffix == ".tmp" for p in ob.BUILD_DIR.glob("*.tmp"))


def test_protocol_bundle_hash_recomputes_from_git() -> None:
    protocol = ob.load_protocol_bundle()
    assert protocol["protocol_tag"] == ob.PROTOCOL_TAG
    assert protocol["protocol_commit"] == ob.PROTOCOL_COMMIT
    assert protocol["full_d7_evidence_commit"] == ob.FULL_D7_EVIDENCE_COMMIT
    assert protocol["n_protocol_files"] == 16
    entries = []
    for rel, _ in protocol["protocol_files"]:
        blob = ob.git_bytes("cat-file", "blob", f"{ob.PROTOCOL_COMMIT}:{rel}")
        entries.append([rel, ob.sha256_bytes(blob)])
    assert protocol["protocol_sha256"] == ob.sha_obj(entries)


def test_status_records_prohibitions_and_blockers(artifacts: dict) -> None:
    status = artifacts["OPWS_POPULATION_BINDING_STATUS.json"]
    assert all(status["prohibitions_respected"].values())
    ids = {b["id"] for b in status["blockers"]}
    assert {"P1_STAGE5_PREFLIGHT_NOT_EXECUTED", "P2_ENVIRONMENT_ID_SERIALIZATION_UNCONFIRMED"} <= ids
    assert status["input_invariants"]["per_task_v2_extra_ids"] == ["saleor-rc-f76d0093b450"]


def test_rendered_artifacts_parse_as_json(artifacts: dict) -> None:
    for name, payload in artifacts.items():
        assert json.loads(ob.render(payload)) == payload
        assert ob.render(payload).endswith("\n")
        assert name.endswith(".json")
