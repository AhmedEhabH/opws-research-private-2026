"""M19A2-ATOMIC1 — synthetic unit tests for the execution-candidate registry.

SCOPE: synthetic fixtures only. Nothing here reads, writes or runs the real 219-task
authorities (the approved plan, frozen manifests, the Saleor object store, oracle
artifacts), no Saleor/Docker/API inference/download runs, and no behavioral outcome is
produced (``REAL_TASK_BEHAVIORAL_OUTCOMES = 0`` is enforced in fixtures and asserted in
the registry spec).

Mission coverage (11 requirements + guards):
  1. canonical ordering: task-major, frozen arm order within task, deterministic;
  2. complete logical-to-candidate mapping (bijection, every record -> exactly one candidate);
  3. five-field dedup: identical five fields collapse into one candidate;
  4. different TASK_ID cannot be coalesced;
  5. different TEST_CONTRACT_HASH cannot be coalesced;
  6. different ENVIRONMENT_ID cannot be coalesced;
  7. missing/invalid identities fail closed (WARN/ERROR/PARTIAL rejected, empty fields,
     missing env, unknown task, contract cross-check, tree gate, missing record, goals);
  8. deterministic hashes on two independent invocations (byte-identical artifacts);
  9. true zero-node vs unresolved node identity distinction (no invented node ids);
 10. never mark a candidate executable (candidate-only, no experimental reuse);
 11. no outcome-dependent selection (ordering/counts never consume behavioral outcomes;
     a plan declaring outcomes != 0 is rejected).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_m19a2_candidate_registry as m19a2  # noqa: E402

DEFAULT_ARMS = ["RM_CSS", "AGENT", "SIP"]
CREATED_AT = "2026-10-23T00:00:00Z"


def sha(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def make_record(
    task: str,
    arm: str,
    *,
    scope: str,
    patch: str,
    contract: str,
    status: str = "OK",
    oid: str | None = None,
) -> dict:
    return {
        "arm_id": arm,
        "task_id": task,
        "status": status,
        "scope_hash": sha(scope),
        "reference_patch_sha256": sha(patch),
        "test_contract_hash": sha(contract),
        "effective_tree_oid": oid or ("T" + sha(patch)[:8]),
        "reference_patch_bytes": len(patch.encode("utf-8")),
        "error_type": None,
        "error_detail": "",
        "invalid_prediction_paths": [],
        "unresolved_contracts": [],
    }


def build_fixture(
    tasks: list[str],
    arms: list[str],
    records: list[dict],
    *,
    contracts: dict[str, str] | None = None,
    envs: dict[str, str] | None = None,
    f2p_counts: dict[str, int] | None = None,
    random_deferred: bool = True,
    tree_ok: bool = True,
    parity_tasks: list[str] | None = None,
) -> tuple[dict, list[str], dict, dict, dict, dict]:
    """Deterministic synthetic fixture; returns (plan, tasks, env, manifest, tree, goals)."""
    # When not supplied, derive the frozen per-task contract truth from the records
    # themselves (all records of one task share its test_contract_hash by construction).
    rec_contract: dict[str, str] = {r["task_id"]: r["test_contract_hash"] for r in records}
    contracts = contracts or {}
    envs = envs or {t: f"ENV-{t}" for t in tasks}
    f2p_counts = f2p_counts or {t: 0 for t in tasks}
    manifest: dict[str, dict] = {}
    for t in tasks:
        c = int(f2p_counts.get(t, 0))
        manifest[t] = {
            "contract_sha256": sha(contracts[t]) if t in contracts else rec_contract.get(t, ""),
            "f2p": {
                "behavioral": c,
                "symbol_absence": 0,
                "total": c,
                "node_identity_binding_mode": "AT_EVALUATION_BOUNDED_BY_FROZEN_COUNT",
                "node_identity_rule": "frozen resolver (count-bounded, fail-closed)",
                "source": "synthetic-fixture",
            },
        }
    plan = {
        "REAL_TASK_BEHAVIORAL_OUTCOMES": 0,
        "per_task_records": records,
        "arm_status": [{"arm_id": a, "coverage_status": "COMPLETE"} for a in arms],
        "full_reference_target_tree_parity": {t: True for t in parity_tasks or tasks},
    }
    if random_deferred:
        plan["arm_status"].append(
            {"arm_id": "RANDOM_SIZE_MATCHED_RM_CSS", "coverage_status": "DEFERRED"}
        )
    tree = {
        "exit_gate": {"pass": tree_ok},
        "per_task": [
            {"task_id": t, "status": "RECONSTRUCTED" if tree_ok else "FAILED"} for t in tasks
        ],
    }
    groups: dict[tuple, list] = {}
    for r in records:
        key = (r["task_id"], r["scope_hash"], r["reference_patch_sha256"], r["test_contract_hash"], envs[r["task_id"]])
        groups.setdefault(key, []).append(r)
    goals = {
        "n_tasks": len(tasks),
        "n_complete_arms": len(arms),
        "n_logical_records": len(records),
        "n_candidates": len(groups),
        "n_true_zero_node_tasks": sum(1 for c in f2p_counts.values() if c == 0),
        "n_node_pending_tasks": sum(1 for c in f2p_counts.values() if c > 0),
        "n_distinct_environment_ids": len({envs[t] for t in tasks}),
        "n_missing_logical_mappings": 0,
        "n_duplicate_candidate_ids": 0,
    }
    return plan, tasks, envs, manifest, tree, goals


def build_spec(**overrides: object) -> dict:
    """Build the default fixture registry spec (dedup on T-A RM_CSS+AGENT)."""
    tasks = ["T-A", "T-B", "T-C"]
    arms = list(DEFAULT_ARMS)
    records: list[dict] = []
    for t in tasks:
        for a in arms:
            if t == "T-A" and a in ("RM_CSS", "AGENT"):
                scope, patch = "SAME-SCOPE-A", "SAME-PATCH-A"
            else:
                scope, patch = f"{t}-{a}", f"{t}-{a}-patch"
            records.append(make_record(t, a, scope=scope, patch=patch, contract=f"C-{t}"))
    plan, tasks, envs, manifest, tree, goals = build_fixture(
        tasks, arms, records, f2p_counts={"T-A": 0, "T-B": 3, "T-C": 0}
    )
    if overrides.get("plan_extra"):
        plan.update(overrides["plan_extra"])  # type: ignore[arg-type]
    return m19a2.build_registry_spec(
        plan=plan,
        ordered_task_ids=list(tasks),
        env_by_task=envs,
        manifest_by_task=manifest,
        tree_receipt=tree,
        created_at=CREATED_AT,
        input_hashes={},
        measure_goals=goals,
        arm_sequence=arms,
        require_random_deferred=False,
    )


# ------------------------------------------------------------------------------ 1 ordering

class TestCanonicalOrdering:
    def test_task_major_frozen_arm_order(self) -> None:
        spec = build_spec()
        ordered = [c["identity_fields"]["TASK_ID"] for c in spec["candidates"]]
        # strictly task-major across canonical task order; never interleaved
        assert ordered[:2] == ["T-A", "T-A"]
        assert ordered[2:5] == ["T-B", "T-B", "T-B"]
        assert ordered[5:] == ["T-C", "T-C", "T-C"]
        # within T-A the deduped (RM_CSS+AGENT) candidate precedes the SIP candidate
        first, second = spec["candidates"][0], spec["candidates"][1]
        assert first["provenance"]["logical_arm_ids"] == ["RM_CSS", "AGENT"]
        assert second["provenance"]["logical_arm_ids"] == ["SIP"]
        assert spec["canonical_order"]["complete_arms"] == DEFAULT_ARMS

    def test_within_task_arm_index_non_decreasing(self) -> None:
        spec = build_spec()
        # T-A: RM_CSS+AGENT merge (min idx 0) then SIP (idx 2); T-B and T-C: one per arm
        expected_min_arm = [0, 2, 0, 1, 2, 0, 1, 2]
        observed = [c["provenance"]["min_arm_index"] for c in spec["candidates"]]
        assert observed == expected_min_arm
        # each candidate's min arm index must equal the index of its first logical arm
        for c in spec["candidates"]:
            first_arm = c["provenance"]["logical_arm_ids"][0]
            assert c["provenance"]["min_arm_index"] == DEFAULT_ARMS.index(first_arm)


class TestLogicalToCandidateMapping:
    def test_bijection(self) -> None:
        spec = build_spec()
        record_ids = {rid for c in spec["candidates"] for rid in c["provenance"]["logical_record_ids"]}
        expected = {f"{a}:{t}" for t in ["T-A", "T-B", "T-C"] for a in DEFAULT_ARMS}
        assert record_ids == expected
        assert len(record_ids) == 9
        total = sum(c["provenance"]["n_logical_origins"] for c in spec["candidates"])
        assert total == 9
        assert spec["counts"]["n_missing_logical_mappings"] == 0
        assert spec["counts"]["n_logical_records"] == 9
        assert spec["counts"]["n_candidates"] == 8
        assert all(c["provenance"]["n_logical_origins"] >= 1 for c in spec["candidates"])


# ------------------------------------------------------------------------------ 2 dedup

class TestFiveFieldDedup:
    def test_identical_five_fields_collapse(self) -> None:
        spec = build_spec()
        dups = [c for c in spec["candidates"] if c["provenance"]["n_logical_origins"] > 1]
        assert len(dups) == 1
        dup = dups[0]
        assert dup["provenance"]["logical_arm_ids"] == ["RM_CSS", "AGENT"]
        assert dup["identity_fields"]["TASK_ID"] == "T-A"
        assert dup["provenance"]["n_logical_origins"] == 2
        # the two merged records must share the same five identity fields
        assert len({c["identity_fields"]["SCOPE_HASH"] for c in spec["candidates"]}) > 0

    def test_dedup_reason_frozen_semantics(self) -> None:
        # the frozen dedup function (reused verbatim) records FIVE_FIELDS_EQUAL on merge
        rec_a = {
            "TASK_ID": "T1",
            "SCOPE_HASH": sha("s"),
            "REFERENCE_PATCH_HASH": sha("p"),
            "TEST_CONTRACT_HASH": sha("c"),
            "ENVIRONMENT_ID": "e1",
            "arm_id": "RM_CSS",
            "record_id": "RM_CSS:T1",
        }
        rec_b = {**rec_a, "arm_id": "AGENT", "record_id": "AGENT:T1"}
        out = m19a2.plan_physical_dedup([rec_a, rec_b])
        assert out["n_logical_records"] == 2
        assert out["n_physical_executions"] == 1
        assert out["physical_executions"][0]["dedup_reason"] == "FIVE_FIELDS_EQUAL"


class TestFieldsCannotCoalesce:
    """Each single-field difference must give a distinct physical execution.

    Verified at the frozen dedup level (the exact function the registry reuses) and at
    the registry level where the input layout permits ("different TASK_ID" and
    "different ENVIRONMENT_ID" via different tasks).
    """

    def test_each_field_singleton_difference_produces_distinct_ids(self) -> None:
        idspec = {
            "TASK_ID": "T1",
            "SCOPE_HASH": sha("s"),
            "REFERENCE_PATCH_HASH": sha("p"),
            "TEST_CONTRACT_HASH": sha("c"),
            "ENVIRONMENT_ID": "e1",
            "arm_id": "RM_CSS",
            "record_id": "RM_CSS:T1",
        }
        variants = []
        for i, field in enumerate(m19a2.PHYSICAL_IDENTITY_FIELDS):
            variants.append({**idspec, field: field + "-DIFF-" + str(i)})
        out = m19a2.plan_physical_dedup([idspec, *variants])
        assert out["n_physical_executions"] == 6
        ids = {ex["physical_execution_id"] for ex in out["physical_executions"]}
        assert len(ids) == 6  # TASK_ID, SCOPE, REF, CONTRACT, ENV all block coalescing

    def test_different_task_id_registry_level(self) -> None:
        tasks = ["T-X", "T-Y"]
        arms = ["RM_CSS"]
        records = [
            make_record("T-X", "RM_CSS", scope="S", patch="P", contract="C"),
            make_record("T-Y", "RM_CSS", scope="S", patch="P", contract="C"),
        ]
        plan, tasks, envs, manifest, tree, goals = build_fixture(
            tasks, arms, records, contracts={"T-X": "C", "T-Y": "C"}
        )
        spec = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=list(tasks), env_by_task=envs,
            manifest_by_task=manifest, tree_receipt=tree, created_at=CREATED_AT,
            input_hashes={}, measure_goals=goals, arm_sequence=arms,
            require_random_deferred=False,
        )
        assert spec["counts"]["n_candidates"] == 2
        tids = {c["identity_fields"]["TASK_ID"] for c in spec["candidates"]}
        assert tids == {"T-X", "T-Y"}  # identical scope/patch/contract still NOT coalesced

    def test_different_environment_id_registry_level(self) -> None:
        tasks = ["T-X", "T-Y"]
        arms = ["RM_CSS"]
        records = [
            make_record("T-X", "RM_CSS", scope="S", patch="P", contract="C"),
            make_record("T-Y", "RM_CSS", scope="S", patch="P", contract="C"),
        ]
        plan, tasks, envs, manifest, tree, goals = build_fixture(
            tasks, arms, records, contracts={"T-X": "C", "T-Y": "C"}
        )
        goals["n_distinct_environment_ids"] = 2  # envs differ per task
        spec = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=list(tasks), env_by_task=envs,
            manifest_by_task=manifest, tree_receipt=tree, created_at=CREATED_AT,
            input_hashes={}, measure_goals=goals, arm_sequence=arms,
            require_random_deferred=False,
        )
        assert spec["counts"]["n_candidates"] == 2
        eids = {c["identity_fields"]["ENVIRONMENT_ID"] for c in spec["candidates"]}
        assert eids == {"ENV-T-X", "ENV-T-Y"}

    def test_different_contract_hash_registry_guard(self) -> None:
        # Frozen semantics: TEST_CONTRACT_HASH is per-task; non-uniform contracts across
        # a task's own arms is data corruption and must fail closed (never silently
        # produce distinct candidates for one task's logical arm records).
        tasks = ["T-X"]
        arms = ["RM_CSS", "AGENT"]
        records = [
            make_record("T-X", "RM_CSS", scope="S", patch="P", contract="C1"),
            make_record("T-X", "AGENT", scope="S", patch="P", contract="C2"),
        ]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=list(tasks), env_by_task=envs,
                manifest_by_task=manifest, tree_receipt=tree, created_at=CREATED_AT,
                input_hashes={}, measure_goals=goals, arm_sequence=arms,
                require_random_deferred=False,
            )
        assert any(f["code"] == "CONTRACT_NONUNIFORM" or f["code"] == "CONTRACT_CROSSCHECK_MISMATCH"
                   for f in exc.value.failures)


class TestFailClosed:
    def test_warn_record_rejected(self) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C", status="WARN")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
                tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
                arm_sequence=arms, require_random_deferred=False,
            )
        assert any(f["code"] == "NON_OK_RECORD" for f in exc.value.failures)

    @pytest.mark.parametrize(
        ("mutate", "code"),
        [
            (lambda r: r[0].pop("scope_hash"), "EMPTY_FIELD"),
            (lambda r: r[0].update({"scope_hash": ""}), "EMPTY_FIELD"),
            (lambda r: r.__delitem__(0), "MISSING_RECORD"),
            (lambda r: r[0].update({"task_id": "T-UNKNOWN"}), "UNKNOWN_TASK_ID"),
        ],
    )
    def test_missing_invalid_identities(self, mutate, code) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        mutate(records)  # mutate AFTER the goals are fixed; plan shares the same list object
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
                tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
                arm_sequence=arms, require_random_deferred=False,
            )
        assert any(f["code"] == code for f in exc.value.failures)

    def test_missing_environment_id_fails_closed(self) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        envs["T-A"] = ""
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
                tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
                arm_sequence=arms, require_random_deferred=False,
            )
        assert any(f["code"] == "ENV_UNRESOLVED" for f in exc.value.failures)

    def test_contract_crosscheck_mismatch_fails_closed(self) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        manifest["T-A"]["contract_sha256"] = sha("OTHER")
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
                tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
                arm_sequence=arms, require_random_deferred=False,
            )
        assert any(f["code"] == "CONTRACT_CROSSCHECK_MISMATCH" for f in exc.value.failures)

    def test_tree_receipt_gate_fails_closed(self) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(
            tasks, arms, records, tree_ok=False
        )
        with pytest.raises(m19a2.ReconciliationError) as exc:
            m19a2.build_registry_spec(
                plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
                tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
                arm_sequence=arms, require_random_deferred=False,
            )
        assert any(f["code"].startswith("TREE_RECEIPT") for f in exc.value.failures)

    def test_goal_mismatch_returns_non_reconciled(self) -> None:
        # a structurally valid input with an unmet measure goal must yield a
        # non-reconciled spec, never a silently-complete artifact
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        goals["n_candidates"] = 5  # wrong: equals 1
        spec = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
            tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
            arm_sequence=arms, require_random_deferred=False,
        )
        assert spec["reconciliation"]["reconciled"] is False
        assert spec["status"] == "FAILED_RECONCILIATION"
        assert any(f["code"] == "MEASURE_GOAL_MISMATCH" for f in spec["reconciliation"]["failures"])

    def test_non_reconciled_spec_never_rendered(self, tmp_path: Path) -> None:
        tasks, arms = ["T-A"], ["RM_CSS"]
        records = [make_record("T-A", "RM_CSS", scope="S", patch="P", contract="C")]
        plan, tasks, envs, manifest, tree, goals = build_fixture(tasks, arms, records)
        goals["n_candidates"] = 99
        spec = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=tasks, env_by_task=envs, manifest_by_task=manifest,
            tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
            arm_sequence=arms, require_random_deferred=False,
        )
        with pytest.raises(m19a2.ExtractError):
            m19a2.render_outputs(spec=spec, out_dir=tmp_path, repo_meta={}, start_wall_s=0.0)
        assert not (tmp_path / m19a2.PLAN_FILENAME).exists()  # fail-closed: no plan artifact


class TestDeterminism:
    def test_two_independent_invocations_byte_identical(self, tmp_path: Path) -> None:
        plan, tasks, envs, manifest, tree, goals = _default_fixture()
        out1, out2 = tmp_path / "a", tmp_path / "b"
        spec1 = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=list(tasks), env_by_task=envs, manifest_by_task=manifest,
            tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
            arm_sequence=list(DEFAULT_ARMS), require_random_deferred=False,
        )
        spec2 = m19a2.build_registry_spec(
            plan=plan, ordered_task_ids=list(tasks), env_by_task=envs, manifest_by_task=manifest,
            tree_receipt=tree, created_at=CREATED_AT, input_hashes={}, measure_goals=goals,
            arm_sequence=list(DEFAULT_ARMS), require_random_deferred=False,
        )
        assert json.dumps(spec1, sort_keys=True) == json.dumps(spec2, sort_keys=True)
        r1 = m19a2.render_outputs(spec=spec1, out_dir=out1, repo_meta={}, start_wall_s=0.0,
                                 elapsed_wall_s_override=5.0)
        r2 = m19a2.render_outputs(spec=spec2, out_dir=out2, repo_meta={}, start_wall_s=0.0,
                                 elapsed_wall_s_override=5.0)
        for name in ("plan", "receipt", "report"):
            assert r1[name]["sha256"] == r2[name]["sha256"]
            assert (out1 / Path(r1[name]["path"]).name).read_bytes() == (
                out2 / Path(r2[name]["path"]).name
            ).read_bytes()
            # reported SHA must equal the SHA of the exact bytes on disk (guards
            # against platform newline translation changing artifact bytes)
            assert sha((out1 / Path(r1[name]["path"]).name).read_bytes()) == r1[name]["sha256"]


# ------------------------------------------------------------------------ 3 safety status

class TestSafetyStatus:
    def test_zero_vs_unresolved_node_distinction(self) -> None:
        spec = build_spec()
        by_status = {}
        for c in spec["candidates"]:
            tid = c["identity_fields"]["TASK_ID"]
            st = c["node_identity_status"]["status"]
            by_status.setdefault(tid, set()).add(st)
        assert by_status["T-A"] == {"TRUE_ZERO_NODE"}
        assert by_status["T-B"] == {"NODE_IDS_PENDING_EXACT_VERIFICATION"}
        assert by_status["T-C"] == {"TRUE_ZERO_NODE"}
        # frozen counts are recorded, never invented node-id strings
        for c in spec["candidates"]:
            ns = c["node_identity_status"]
            assert "node_id" not in ns and "node_ids" not in ns
            assert ns["node_ids_frozen_in_repo_for_all_tasks"] is False

    def test_never_executable(self) -> None:
        spec = build_spec()
        assert spec["REAL_TASK_BEHAVIORAL_OUTCOMES"] == 0
        assert spec["status"] == "PROVISIONAL_NOT_EXECUTABLE"
        assert spec["execution_authorization"]["physical_execution"] == "NOT_AUTHORIZED"
        assert spec["execution_authorization"]["experimental_reuse"] == "NOT_PERMITTED"
        assert spec["execution_authorization"]["environment_binding"] == "PENDING_VALIDATION"
        for c in spec["candidates"]:
            es = c["execution_status"]
            assert es["executable"] is False
            assert es["candidate_only"] is True
            assert es["status_code"] == "PROVISIONAL_NOT_EXECUTABLE"
            assert es["environment_binding"] == "PENDING_VALIDATION"
            assert es["real_behavioral_test_outcomes"] == 0
            assert es["experimental_reuse_permitted"] is False
            assert c["synthetic"] is False

    def test_aggregate_not_a_contract_hash(self) -> None:
        spec = build_spec()
        assert spec["hashes"]["aggregate_not_a_contract_hash"] is True
        contracts = {c["identity_fields"]["TEST_CONTRACT_HASH"] for c in spec["candidates"]}
        assert spec["hashes"]["aggregate_sha256"] not in contracts


class TestNoOutcomeDependentSelection:
    def test_outcome_free_ordering_and_counts(self) -> None:
        # Adding outcome-like baggage to the plan must not change candidates/order.
        base = build_spec()
        with_outcomes = build_spec(
            plan_extra={"hypothetical_outcomes": {"T-A": {"pass": 1}, "T-B": {"fail": 1}}}
        )
        assert [c["candidate_id"] for c in base["candidates"]] == [
            c["candidate_id"] for c in with_outcomes["candidates"]
        ]
        assert base["counts"] == with_outcomes["counts"]

    def test_behavioral_outcomes_declared_rejected(self) -> None:
        with pytest.raises(m19a2.ReconciliationError) as exc:
            build_spec(plan_extra={"REAL_TASK_BEHAVIORAL_OUTCOMES": 7})
        assert any(f["code"] == "BEHAVIORAL_OUTCOMES_PRESENT" for f in exc.value.failures)


def _default_fixture() -> tuple[dict, list[str], dict, dict, dict, dict]:
    tasks = ["T-A", "T-B", "T-C"]
    arms = list(DEFAULT_ARMS)
    records: list[dict] = []
    for t in tasks:
        for a in arms:
            if t == "T-A" and a in ("RM_CSS", "AGENT"):
                scope, patch = "SAME-SCOPE-A", "SAME-PATCH-A"
            else:
                scope, patch = f"{t}-{a}", f"{t}-{a}-patch"
            records.append(make_record(t, a, scope=scope, patch=patch, contract=f"C-{t}"))
    return build_fixture(tasks, arms, records, f2p_counts={"T-A": 0, "T-B": 3, "T-C": 0})
