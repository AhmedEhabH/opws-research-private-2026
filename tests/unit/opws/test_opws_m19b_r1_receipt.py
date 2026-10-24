"""M19B-R1 -- RED/GREEN fixtures for the fail-closed real-run receipt seam.

Offline and synthetic ONLY: no Saleor, no Docker, no network, no model.  The
receipt seam (``benchmark.wp2.receipt_schema_v1``) is exercised against:

T1  strict task identity: 7 pilot ids, corrected strict P2P-S counts
    (13,156,103,98,74,5,8 = 457), 032b98afff20 (=947 strict) NOT in the
    pilot, duplicate/missing-key rejection, list-length vs declared count,
    and an adversarial swapped-task fixture that MUST fail.
T5  fail-closed RED/GREEN cases: no test may pass with incomplete mandatory
    provenance; every adversarial fixture must raise ReceiptError.
T8  integration gate: synthetic plan-request -> command builder -> per-
    invocation raw XML parser -> schema receipt, with one negative case per
    boundary.

The evidence-level T6 offline regression lives in
``scripts/opws_m19b_r1_offline_regression.py`` (run in the mission, not in
pytest, because it reads the read-only rescued evidence directory).
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(ROOT / "src" / "benchmark" / "wp2"))

import oracle_confirmation  # noqa: E402  # frozen parser (read-only)

# src/benchmark/wp2 is on sys.path above, exposing the additive module
import receipt_schema_v1 as rs  # noqa: E402  # additive M19B-R1 module

FROZEN_CONTRACT_SHA = "df1e087b199277cc56c42fdfd182f85fcd3faf0c74f4701d5add80b52866f124"
EVIDENCE_MANIFEST_SHA = "39ea5470625188a4357575f971842676d32a3ee811874d256f7978e1989b3647"
T7E42 = "saleor-rc-7e42fc67ce72"
TID12 = "7e42fc67ce72"


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _xml(cases: list[tuple[str, str]]) -> str:
    """cases: (node_id, kind); kind in passed/failed/error/skipped."""
    body = []
    for node_id, kind in cases:
        fname, name = node_id.split("::", 1)
        if kind == "failed":
            inner = "<failure message='boom'>Traceback\nassert 1 == 2</failure>"
        elif kind == "error":
            inner = "<error message='err'>Traceback\nRuntimeError: boom</error>"
        elif kind == "skipped":
            inner = "<skipped/>"
        else:
            inner = ""
        body.append(f'<testcase file="{fname}" name="{name}">{inner}</testcase>')
    return f'<?xml version="1.0" encoding="utf-8"?><testsuite>{"".join(body)}</testsuite>'


def _raw_junit_files(prefix: str = TID12) -> list[dict[str, Any]]:
    items = []
    for side in ("t", "p"):
        for rep in ("r0", "r1", "r2"):
            name = f"{prefix}_{side}_{rep}_f0.xml"
            items.append(
                {
                    "file": name,
                    "sha256": hashlib.sha256(name.encode("utf-8")).hexdigest(),
                    "raw": True,
                }
            )
    return items


def _valid_node_outcomes() -> dict[str, Any]:
    node = "saleor/app/tests/test_app_commands.py::test_creates_app_from_manifest_fails_on_already_installed_app"
    z = lambda rep: {f"r{r}": [rep] for r in (0, 1, 2)}  # noqa: E731
    return {
        node: {
            "t": {"outcomes": ["passed", "passed", "passed"], "observations_by_rep": z("passed")},
            "p": {"outcomes": ["passed", "passed", "passed"], "observations_by_rep": z("passed")},
        }
    }


def _base_receipt(**overrides: Any) -> dict[str, Any]:
    """A fully valid receipt: 3 distinct reps, independent OS attestation,
    canonical node-identity hashes, production-only patch scope."""
    argv_order = [
        "wsl", "-d", "Ubuntu-24.04", "--", "docker", "run", "--rm",
        "wp2-era-py38", "bash", "-lc", "true",
    ]
    per_node_outcomes = _valid_node_outcomes()
    node_hash = rs.node_set_sha256(per_node_outcomes)
    payload: dict[str, Any] = {
        "schema": rs.RECEIPT_SCHEMA_VERSION,
        "schema_version": rs.RECEIPT_SCHEMA_REV,
        "task_id": T7E42,
        "parent_commit": "a" * 40,
        "target_commit": "b" * 40,
        "selected_arm": "real_v3_m17_r1",
        "control": "QUALIFICATION",
        "scope": {
            # EDITABLE PRODUCTION SCOPE only -- test-patch paths are rejected
            # by the hardened schema (M19B-R1H).
            "scope_patch_paths": ["saleor/app/manifest_validations.py"],
            "scope_patch_sha256": "0" * 64,  # zero digest: no patch claim
            "outside_allowed_paths": False,
        },
        "test_contract_sha256": FROZEN_CONTRACT_SHA,
        "env": {
            "linux_environment_digest": "1" * 64,
            "manifest_sha256": EVIDENCE_MANIFEST_SHA,
            "image_digest": "2" * 64,
        },
        "argv": {
            "kind": "OS_ATTESTED",
            "order": argv_order,
            "attestation": {
                "method": "CONTAINER_RUNTIME_INSPECT",
                "pid": 4242,
                "source": (
                    "independent reader inspected the container runtime cmdline "
                    "after spawn (not wrapper argv capture)"
                ),
                "attested_argv_sha256": rs.sha256_canonical(argv_order),
            },
        },
        "claim_os_attested": True,
        "rep_index": [0, 1, 2],
        "n_reps": 3,
        "process_returncode": 0,
        "container_returncode": 0,  # Docker/container RC is SEPARATE from pytest RC
        "returncode_provenance": (
            "RUN_0_RC=0;RUN_1_RC=0;RUN_2_RC=0 parsed from container run log"
        ),
        "outputs": {
            "junit": _raw_junit_files(),
            "snapshot_sha256_over_raw_files": "3" * 64,
            "container_completed": True,
        },
        "node_identity": {
            "set_equality": "EXACT_MATCH",
            "expected_sha256": node_hash,
            "observed_sha256": node_hash,
        },
        "per_node_outcomes": per_node_outcomes,
        "timeout_infra": {"category": "NONE", "detail": "all 6 invocations completed"},
        "control_qualification": {
            "decision": "PASS",
            "reason": "3 distinct reps on both sides, all passed; control met",
            "sensitivity_supported": True,
        },
        "p2p_s_claim": True,
    }
    payload.update(overrides)
    return payload


def _expect_blocked(payload: dict[str, Any], fragment: str) -> None:
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert fragment.lower() in str(ei.value).lower(), str(ei.value)


# --------------------------------------------------------------------------- #
# T1 -- strict task identity (pure fixtures)                                  #
# --------------------------------------------------------------------------- #
PILOT_FROZEN = [
    ("saleor-rc-0179b331be38", 13),
    ("saleor-rc-0f16ed78b02b", 156),
    ("saleor-rc-7e42fc67ce72", 103),
    ("saleor-rc-8b0cbe2fb72f", 98),
    ("saleor-rc-b2e3652af826", 74),
    ("saleor-rc-df7c7d4e8466", 5),
    ("saleor-rc-fe6e46266e81", 8),
]


def _by_task_fixture() -> dict[str, dict[str, Any]]:
    tasks = {}
    for tid, n in PILOT_FROZEN:
        tasks[tid] = {
            "task_id": tid,
            "strict_p2p_only": [f"node::{i}" for i in range(n)],
            "strict_counts": {"P2P_ONLY": n},
        }
    tasks[rs.NON_PILOT_032B] = {
        "task_id": rs.NON_PILOT_032B,
        "strict_p2p_only": [f"n::{i}" for i in range(rs.NON_PILOT_032B_STRICT)],
        "strict_counts": {"P2P_ONLY": rs.NON_PILOT_032B_STRICT},
    }
    return tasks


def _repdiag_fixture() -> dict[str, dict[str, Any]]:
    return {
        tid: {"task_id": tid, "counts": {"B_strict_p2p": n, "C_rep_stable_both_sides": n}}
        for tid, n in PILOT_FROZEN
    }


def test_t1_all_seven_counts_and_total() -> None:
    assert sum(n for _, n in PILOT_FROZEN) == 457
    assert list(rs.EXPECTED_PILOT_P2P_S.values()) == [n for _, n in PILOT_FROZEN]
    assert rs.verify_pilot_counts(_by_task_fixture(), _repdiag_fixture())


def test_t1_032b_is_not_pilot_and_has_947_strict() -> None:
    rs.verify_non_pilot_excluded(_by_task_fixture())
    with pytest.raises(rs.ReceiptError):
        rs.verify_non_pilot_excluded(_by_task_fixture(), pilot={rs.NON_PILOT_032B})


@pytest.mark.parametrize(
    "mutate_by_task, mutate_repdiag, fragment",
    [
        (lambda d: d["saleor-rc-0179b331be38"]["strict_counts"].__setitem__("P2P_ONLY", 99),
         lambda d: None, "!= declared strict P2P_ONLY"),
        (lambda d: d["saleor-rc-0179b331be38"].update(strict_p2p_only=["node::0"]),
         lambda d: None, "!= declared strict P2P_ONLY"),
        (lambda d: d.pop("saleor-rc-0179b331be38"),
         lambda d: None, "missing from M19A4 by-task"),
        # by-task is internally consistent (13/13); the DIAGNOSTIC side drifts
        (lambda d: None,
         lambda d: d["saleor-rc-0179b331be38"]["counts"].__setitem__("B_strict_p2p", 14),
         "!= expected 13"),
    ],
)
def test_t1_adversarial_count_fixtures_fail(
    mutate_by_task: Callable[[dict[str, Any]], None],
    mutate_repdiag: Callable[[dict[str, Any]], None],
    fragment: str,
) -> None:
    by_task = _by_task_fixture()
    repdiag = _repdiag_fixture()
    mutate_by_task(by_task)
    mutate_repdiag(repdiag)
    with pytest.raises(rs.ReceiptError) as ei:
        rs.verify_pilot_counts(by_task, repdiag)
    assert fragment.lower() in str(ei.value).lower()


def test_t1_adversarial_swapped_task_counts_fail() -> None:
    """Swapped counts: 103 attributed to 0179b331be38 must be rejected."""
    by_task = _by_task_fixture()
    by_task["saleor-rc-0179b331be38"]["strict_counts"]["P2P_ONLY"] = 103
    by_task["saleor-rc-0179b331be38"]["strict_p2p_only"] = [f"n::{i}" for i in range(103)]
    with pytest.raises(rs.ReceiptError) as ei:
        rs.verify_pilot_counts(by_task, _repdiag_fixture())
    assert "!= expected 13" in str(ei.value)


def test_t1_duplicate_and_missing_keys_rejected() -> None:
    with pytest.raises(rs.ReceiptError):
        rs.key_by_task_id(
            [{"task_id": "x"}, {"task_id": "x"}], collection_name="c"
        )
    with pytest.raises(rs.ReceiptError):
        rs.key_by_task_id([{"task_id": "x"}], collection_name="c", declared_total=2)
    with pytest.raises(rs.ReceiptError):
        rs.key_by_task_id([{"no_id": 1}], collection_name="c")


# --------------------------------------------------------------------------- #
# T5 -- fail-closed receipt RED/GREEN battery                                 #
# --------------------------------------------------------------------------- #
def test_green_correct_three_distinct_reps() -> None:
    assert rs.validate_receipt(_base_receipt()) == "PASS"


def test_red_three_copies_of_r0_are_not_3_of_3() -> None:
    payload = _base_receipt()
    payload["outputs"]["junit"] = []
    for side in ("t", "p"):
        for idx in (0, 1, 2):  # three copies, all from r0, distinct f-slots
            name = f"{TID12}_{side}_r0_f{idx}.xml"
            payload["outputs"]["junit"].append(
                {"file": name, "sha256": "5" * 64, "raw": True}
            )
    _expect_blocked(payload, "lacks distinct reps")


def test_red_missing_r1() -> None:
    payload = _base_receipt()
    payload["outputs"]["junit"] = [
        item for item in payload["outputs"]["junit"] if "_r1_" not in item["file"]
    ]
    _expect_blocked(payload, "distinct raw per-rep")


def test_red_duplicate_or_conflicting_fragments_within_rep() -> None:
    payload = _base_receipt()
    node = next(iter(payload["per_node_outcomes"]))
    payload["per_node_outcomes"][node]["t"]["observations_by_rep"]["r1"] = [
        "passed",
        "failed",
    ]
    _expect_blocked(payload, ">1 observation")


def test_red_extra_or_missing_node_ids_not_exact() -> None:
    payload = _base_receipt()
    payload["node_identity"]["set_equality"] = "OBSERVED_SUPERSET"
    _expect_blocked(payload, "EXACT_MATCH")


def test_red_parameterized_name_changed_ids_change_set_hash() -> None:
    """Same logical test renamed (``[param]`` suffix) changes the identity
    byte-for-byte; a receipt binding the OLD expected hash must not pass."""
    payload = _base_receipt()
    node = next(iter(payload["per_node_outcomes"]))
    renamed = node + "[param=1]"
    payload["per_node_outcomes"][renamed] = payload["per_node_outcomes"].pop(node)
    payload["node_identity"]["expected_sha256"] = "d" * 64  # drift
    payload["node_identity"]["observed_sha256"] = "d" * 64  # drift
    _expect_blocked(payload, "identity set")


def verify_commits_vs_census(payload: dict[str, Any], row: dict[str, Any]) -> None:
    """Consumer-side: the receipt's parent/target must EQUAL the frozen
    census commits for the task (swap detection)."""
    if (payload.get("parent_commit") != row.get("parent_commit")
            or payload.get("target_commit") != row.get("target_commit")):
        raise rs.ReceiptError(
            "parent/target commits do not match the frozen census (swap?)"
        )


def test_red_parent_target_swapped() -> None:
    census = json.loads(
        (ROOT / "research/wp2/wp2_saleor_main297_census_2026-09-22.json").read_text(
            encoding="utf-8"
        )
    )
    row = next(t for t in census["tasks"] if t["task_id"] == T7E42)
    payload = _base_receipt(
        parent_commit=row["parent_commit"], target_commit=row["target_commit"]
    )
    verify_commits_vs_census(payload, row)
    swapped = _base_receipt(
        parent_commit=row["target_commit"], target_commit=row["parent_commit"]
    )
    with pytest.raises(rs.ReceiptError) as ei:
        verify_commits_vs_census(swapped, row)
    assert "parent/target" in str(ei.value)


def test_red_pass_only_neg_unexpectedly_successful() -> None:
    payload = _base_receipt(control="NEG")
    payload["control_qualification"] = {
        "decision": "PASS",
        "reason": "all stable",
    }
    _expect_blocked(payload, "sensitivity_supported")


def test_red_full_reference_mismatch() -> None:
    payload = _base_receipt(control="FULL_REFERENCE")
    payload["control_qualification"] = {
        "decision": "PASS",
        "reason": "reference complete",
        "frozen_reference_sha256": "9" * 64,
        "reference_mismatch": True,
    }
    _expect_blocked(payload, "mismatch")


def test_red_wrong_or_missing_contract_hash() -> None:
    payload = _base_receipt()
    payload["test_contract_sha256"] = "short"
    _expect_blocked(payload, "test_contract_sha256")
    payload["test_contract_sha256"] = None
    _expect_blocked(payload, "test_contract_sha256")


def test_red_wrong_or_missing_image_digest() -> None:
    payload = _base_receipt()
    payload["env"]["image_digest"] = ""
    _expect_blocked(payload, "image_digest")


def test_red_scope_patch_outside_allowed_paths() -> None:
    payload = _base_receipt()
    payload["scope"]["outside_allowed_paths"] = True
    _expect_blocked(payload, "outside the allowed paths")


def test_red_terminal_pytest_rcs_never_pass() -> None:
    """Canonical pytest RC mapping (M19B-R1H): 2=INTERRUPTED,
    3=INTERNAL_ERROR, 4=USAGE_ERROR, 5=NO_TESTS_COLLECTED are terminal and
    must never qualify a receipt (pytest RC is separate from container RC)."""
    for rc, label in (
        (2, "INTERRUPTED"),
        (3, "INTERNAL_ERROR"),
        (4, "USAGE_ERROR"),
        (5, "NO_TESTS_COLLECTED"),
    ):
        payload = _base_receipt(process_returncode=rc)
        payload["timeout_infra"] = {"category": "NONE", "detail": "all done"}
        _expect_blocked(payload, label)


def test_green_return_code_1_recorded_as_outcomes() -> None:
    """rc=1 (TESTS_FAILED) WITH a recorded failing outcome is a REAL outcome;
    the receipt records it with provenance.  rc=1 on NEG may be expected
    evidence, not an infra failure -- and pytest RC is distinct from the
    container RC (the container propagated rc=1)."""
    payload = _base_receipt(process_returncode=1)
    payload["container_returncode"] = 1  # docker propagated the pytest rc
    node = next(iter(payload["per_node_outcomes"]))
    rec = payload["per_node_outcomes"][node]["t"]
    rec["outcomes"] = ["failed", "passed", "passed"]
    rec["observations_by_rep"] = {
        "r0": ["failed"],
        "r1": ["passed"],
        "r2": ["passed"],
    }
    payload["p2p_s_claim"] = False
    payload["returncode_provenance"] = "RUN_2_RC=1 from container run log"
    assert rs.validate_receipt(payload) == "PASS"


def test_red_silent_timeout_infra_collection_failure() -> None:
    payload = _base_receipt()
    payload["outputs"]["container_completed"] = False
    payload["timeout_infra"] = {"category": "NONE", "detail": "all done"}
    _expect_blocked(payload, "NONE")


def test_green_crlf_and_lf_hashes_are_distinct_and_pinned() -> None:
    """CRLF and LF serializations of the same JUnit must hash differently so
    a receipt cannot silently conflate the two byte images."""
    # a FAILED case embeds a real newline inside the failure element, so the
    # LF and CRLF byte images genuinely differ
    xml = _xml([("saleor/app/tests/test_app_commands.py::t1", "failed")])
    lf = xml.encode("utf-8")
    crlf = lf.replace(b"\n", b"\r\n")
    h_lf = hashlib.sha256(lf).hexdigest()
    h_crlf = hashlib.sha256(crlf).hexdigest()
    assert h_lf != h_crlf
    assert rs.sha256_canonical({"x": 1}) == rs.sha256_canonical({"x": 1})
    payload = _base_receipt()
    payload["outputs"]["snapshot_sha256_over_raw_files"] = h_lf
    assert rs.validate_receipt(payload) == "PASS"


def consumer_verify_snapshot(raw_files: list[Path], bound: str) -> bool:
    """Consumer-side re-verification: canonical snapshot over sorted raw
    file content hashes must equal the receipt's bound snapshot."""
    payload = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw_files)}
    return rs.sha256_canonical(payload) == bound


def test_red_mutable_late_arriving_evidence_detected(tmp_path: Path) -> None:
    """After a receipt snapshot is bound, mutating any raw file changes the
    snapshot; consumer re-verification against the mutated state must fail."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_files = []
    names = []
    cases = [("saleor/app/tests/test_app_commands.py::t1", "passed")]
    for side in ("t", "p"):
        for rep in ("r0", "r1", "r2"):
            p = raw_dir / f"7e42fc67ce72_{side}_{rep}_f0.xml"
            p.write_text(_xml(cases), encoding="utf-8")
            raw_files.append(p)
            names.append(p.name)
    bound = rs.sha256_canonical(
        {
            n: hashlib.sha256(p.read_bytes()).hexdigest()
            for n, p in zip(names, raw_files, strict=True)
        }
    )
    assert consumer_verify_snapshot(raw_files, bound) is True
    # Late-arriving mutation on disk: r1 target file is replaced.
    p_mut = next(p for p in raw_files if "_t_r1_" in p.name)
    p_mut.write_text(_xml(cases) + "\n<!-- touched later -->", encoding="utf-8")
    assert consumer_verify_snapshot(raw_files, bound) is False
    assert rs.validate_receipt(_base_receipt()) == "PASS"


def test_red_merged_dict_only_seam_cannot_pass() -> None:
    """A wrapper reading only a merged junit dictionary cannot substantiate
    three reps: every output entry must be a RAW per-rep file."""
    payload = _base_receipt()
    payload["outputs"]["junit"] = [
        {"file": "merged_junit.json", "sha256": "6" * 64, "raw": False,
         "derived_from_merged_dict": True}
    ]
    _expect_blocked(payload, "merged-dict")


def test_red_missing_or_raw_orphan_junit() -> None:
    payload = _base_receipt()
    payload["outputs"]["junit"] = []
    _expect_blocked(payload, "non-empty")


def test_red_rep_collision() -> None:
    """Two raw entries claiming the SAME rep/file slot for a side (r1 twice)
    collapse identity; must be blocked."""
    payload = _base_receipt()
    junit = payload["outputs"]["junit"]
    dup = {"file": f"{TID12}_t_r1_f0.xml", "sha256": "7" * 64, "raw": True}
    junit.append(dup)
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(payload)


def test_red_incongruent_argv_not_os_attested() -> None:
    payload = _base_receipt()
    payload["argv"] = {
        "kind": "HARNESS_CONSTRUCTED",
        "order": ["docker", "run", "wp2-era-py38"],
        "attestation": None,
    }
    payload["claim_os_attested"] = True
    _expect_blocked(payload, "not be confused")


def test_red_absent_return_code_provenance() -> None:
    payload = _base_receipt()
    payload["returncode_provenance"] = "  "
    _expect_blocked(payload, "returncode_provenance")


def test_red_absent_argv_attestation() -> None:
    payload = _base_receipt()
    payload["argv"]["attestation"] = None
    _expect_blocked(payload, "OS_ATTESTED")


# --------------------------------------------------------------------------- #
# T8 -- integration gate: plan -> command -> parse -> receipt                 #
# --------------------------------------------------------------------------- #
def materialize_plan(task_id: str, arm: str, control: str) -> dict[str, Any]:
    if task_id not in rs.EXPECTED_PILOT_P2P_S:
        raise rs.ReceiptError(f"task {task_id} not in the seven-task pilot")
    if arm not in ("v3", "real_v3_m17_r1"):
        raise rs.ReceiptError(f"unsupported arm {arm!r}")
    if control not in ("QUALIFICATION", "NEG", "FULL_REFERENCE"):
        raise rs.ReceiptError(f"unsupported control {control!r}")
    return {
        "task_id": task_id,
        "expected_p2p_s": rs.EXPECTED_PILOT_P2P_S[task_id],
        "arm": arm,
        "control": control,
    }


def build_command(plan: dict[str, Any], rep: int) -> list[str]:
    if plan["arm"] in ("v3", "real_v3_m17_r1"):
        return ["/opt/venv/bin/python", "-m", "pytest", "-p", "no:cacheprovider",
                "--ds=saleor.tests.settings", "--reuse-db",
                f"--junitxml=/workspace/wt/{TID12}_t_r{rep}_f0.xml", "-q", "tests_f0"]
    raise rs.ReceiptError("no command builder for unsupported arm")


def parse_invocation_xml(text: str) -> tuple[dict[str, str], dict[str, str]]:
    nodes, fails = oracle_confirmation.parse_junit_with_failures(text)
    return nodes, fails


def produce_receipt(plan: dict[str, Any], argv: list[str], rep_idx: int) -> dict[str, Any]:
    payload = _base_receipt(task_id=plan["task_id"], selected_arm=plan["arm"])
    payload["argv"] = {
        "kind": "OS_ATTESTED",
        "order": argv,
        "attestation": {
            "method": "CONTAINER_RUNTIME_INSPECT",
            "pid": 1,
            "source": "independent reader; synthetic T8 seam",
            "attested_argv_sha256": rs.sha256_canonical(argv),
        },
    }
    payload["claim_os_attested"] = True
    payload["rep_index"] = [0, 1, 2]
    payload["control"] = plan["control"]
    node_hash = rs.node_set_sha256(payload["per_node_outcomes"])
    payload["node_identity"] = {
        "set_equality": "EXACT_MATCH",
        "expected_sha256": node_hash,
        "observed_sha256": node_hash,
    }
    return payload


def test_t8_full_seam_pass() -> None:
    plan = materialize_plan(T7E42, "real_v3_m17_r1", "QUALIFICATION")
    argv = build_command(plan, rep=0)
    xml = _xml([("saleor/app/tests/test_app_commands.py::t1", "passed")])
    nodes, fails = parse_invocation_xml(xml)
    assert nodes  # parser actually extracted a node
    assert fails == {}
    payload = produce_receipt(plan, argv, 0)
    assert rs.validate_receipt(payload) == "PASS"
    summary = rs.receipt_summary(payload)
    assert summary["receipt_id"] == rs.hash_payload_core(payload)


def test_t8_negative_boundaries() -> None:
    with pytest.raises(rs.ReceiptError):
        materialize_plan("saleor-rc-032b98afff20", "real_v3_m17_r1", "QUALIFICATION")
    with pytest.raises(rs.ReceiptError):
        materialize_plan(T7E42, "unknown_arm", "QUALIFICATION")
    with pytest.raises(rs.ReceiptError):
        materialize_plan(T7E42, "real_v3_m17_r1", "RANDOM_CONTROL")
    import xml.etree.ElementTree as ET

    with pytest.raises(rs.ReceiptError):
        build_command({"arm": "bogus"}, 0)
    with pytest.raises(ET.ParseError):
        parse_invocation_xml("not xml at all <<<")

    payload = produce_receipt(
        materialize_plan(T7E42, "real_v3_m17_r1", "QUALIFICATION"),
        build_command(materialize_plan(T7E42, "real_v3_m17_r1", "QUALIFICATION"), 0),
        0,
    )
    payload["outputs"]["junit"][0]["sha256"] = "tampered-not-hex"  # corrupted
    _expect_blocked(payload, "sha256")


def test_t8_receipt_hash_excludes_nondeterministic_fields() -> None:
    a = _base_receipt()
    b = _base_receipt()
    b["generated_at_utc"] = "2026-10-24T23:59:59Z"
    b["wall_s"] = 99.9
    b["receipt_id"] = "irrelevant"
    assert rs.hash_payload_core(a) == rs.hash_payload_core(b)
    assert rs.hash_payload_core(a) != rs.sha256_canonical({"schema": "x"})


# --------------------------------------------------------------------------- #
# T1 -- strict join against LIVE frozen artifacts (read-only, committed)       #
# --------------------------------------------------------------------------- #
def test_t1_live_artifact_strict_join_457() -> None:
    """Loads the real committed artifacts under reports/ and research/ and
    verifies the corrected 457 join end-to-end (the T1 gate)."""
    per_task_v2 = []
    with open(ROOT / "research/wp2/oracle_confirmation_linux_v2_2026-09-23/per_task_v2.jsonl",
              encoding="utf-8") as f:
        per_task_v2 = [json.loads(line) for line in f if line.strip()]
    assert len(per_task_v2) == 220
    keyed = rs.key_by_task_id(per_task_v2, collection_name="per_task_v2", declared_total=220)
    for tid in rs.EXPECTED_PILOT_P2P_S:
        assert tid in keyed

    by_task_artifact = json.loads(
        (ROOT / "reports/m19a4_p2ps/M19A4_P2P_ONLY_NODES_BY_TASK_83.json").read_text(
            encoding="utf-8"
        )
    )
    by_task = rs.key_by_task_id(
        by_task_artifact["tasks"], collection_name="by_task_83", declared_total=83
    )
    repdiag_artifact = json.loads(
        (ROOT / "reports/m19a4_p2ps/M19A4_REP_IDENTITY_DIAGNOSTIC.json").read_text(
            encoding="utf-8"
        )
    )
    repdiag = rs.key_by_task_id(
        repdiag_artifact["per_task"], collection_name="repdiag", declared_total=83
    )
    joined = rs.verify_pilot_counts(by_task, repdiag)
    assert sum(v["by_task"] for v in joined.values()) == 457
    assert sum(v["repdiag"] for v in joined.values()) == 457
    rs.verify_non_pilot_excluded(by_task)
    # every task in the 83-cohort: declared strict list length == count, and
    # the seven-total check for full strict accountability
    total_full = 0
    for _tid, entry in by_task.items():
        n = rs.strict_p2p_s_from_task(entry)
        total_full += n
    assert total_full == sum(t["strict_counts"]["P2P_ONLY"] for t in by_task.values())


def test_t1_live_artifact_p2p_u_is_separate() -> None:
    """P2P-U inventories are NOT the P2P_ONLY/P2P-S lists (T7 guard)."""
    import p2p_u_v2  # noqa: F401  (module is on sys.path src/benchmark/wp2)

    by_task_artifact = json.loads(
        (ROOT / "reports/m19a4_p2ps/M19A4_P2P_ONLY_NODES_BY_TASK_83.json").read_text(
            encoding="utf-8"
        )
    )
    for t in by_task_artifact["tasks"]:
        if t["task_id"] in rs.EXPECTED_PILOT_P2P_S:
            assert t["strict_counts"]["P2P_ONLY"] == rs.EXPECTED_PILOT_P2P_S[t["task_id"]]
            # no P2P_U field is introduced by the M19A4 P2P-S artifact
            assert "p2p_u" not in t or t["p2p_u"] is None


# --------------------------------------------------------------------------- #
# M19B-R1H -- RECEIPT VALIDATOR HARDENING (adversarial battery)               #
# Each case documents a fail-open defect that MUST be repaired: the receipt   #
# seam must fail closed (raise ReceiptError, verdict BLOCKED) here.  Written  #
# and run RED against the original schema, then kept GREEN after hardening.  #
# --------------------------------------------------------------------------- #
PYTEST_RC_CANONICAL = {
    0: "OK",
    1: "TESTS_FAILED",
    2: "INTERRUPTED",
    3: "INTERNAL_ERROR",
    4: "USAGE_ERROR",
    5: "NO_TESTS_COLLECTED",
}


def test_hard_pytest_return_code_map_is_canonical() -> None:
    """0 OK; 1 TESTS_FAILED; 2 INTERRUPTED; 3 INTERNAL_ERROR;
    4 USAGE_ERROR; 5 NO_TESTS_COLLECTED -- pytest RC (canonical) is SEPARATE
    from Docker/container RC."""
    assert rs.PYTEST_RETURN_CODES == PYTEST_RC_CANONICAL


def test_hard_control_decision_blocked_must_block_receipt() -> None:
    """(a) control decision BLOCKED currently returns PASS -- must raise."""
    payload = _base_receipt(
        control_qualification={
            "decision": "BLOCKED",
            "reason": "control evidence incomplete",
        }
    )
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "BLOCKED" in str(ei.value)


def test_hard_n_reps_is_mandatory() -> None:
    """(b) n_reps omitted (or < 3) currently returns PASS -- must raise."""
    payload = _base_receipt()
    payload.pop("n_reps", None)
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "n_reps" in str(ei.value)
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(_base_receipt(n_reps=2))


def test_hard_empty_os_attested_attestation_must_block() -> None:
    """(c) an empty {} OS_ATTESTED attestation currently passes."""
    payload = _base_receipt()
    payload["argv"]["attestation"] = {}
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "attestation" in str(ei.value).lower()


def test_hard_boundary_capture_is_not_os_attestation() -> None:
    """Capture-at-subprocess-boundary must NOT satisfy OS_ATTESTED; the R1
    base fixture currently labels exactly that wording as its attestation."""
    payload = _base_receipt()
    payload["argv"]["attestation"] = {
        "pid": 4242,
        "source": "subprocess argv captured at launch (os-level)",
    }
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "attest" in str(ei.value).lower()


def test_hard_unexplained_return_code_cannot_pass() -> None:
    """(d) process_returncode 99 with category NONE currently passes; RCs
    3/4/5 (INTERNAL_ERROR/USAGE_ERROR/NO_TESTS_COLLECTED) are also accepted
    today.  Only the canonical 0..5 set may appear, and 2..5 never qualify."""
    for rc in (99, 6, -1):
        payload = _base_receipt(process_returncode=rc)
        with pytest.raises(rs.ReceiptError):
            rs.validate_receipt(payload)
    for rc in (2, 3, 4, 5):
        payload = _base_receipt(process_returncode=rc)
        payload["timeout_infra"] = {"category": "NONE", "detail": "rc ignored"}
        with pytest.raises(rs.ReceiptError):
            rs.validate_receipt(payload)


def test_hard_container_return_code_is_separate_field() -> None:
    """Docker/container RC must be a SEPARATE field; an unexplained nonzero
    container result must block even when the pytest RC looks clean."""
    payload = _base_receipt()
    payload["container_returncode"] = 137
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "container" in str(ei.value).lower()


def test_hard_rc1_tests_failed_is_expected_evidence_not_infra() -> None:
    """rc=1 (TESTS_FAILED) on NEG with a recorded failing outcome and
    sensitivity evidence is EXPECTED evidence -- hardening must NOT turn it
    into an infrastructure failure."""
    payload = _base_receipt(control="NEG", process_returncode=1)
    payload["container_returncode"] = 1  # docker propagated the pytest rc
    node = next(iter(payload["per_node_outcomes"]))
    rec = payload["per_node_outcomes"][node]["t"]
    rec["outcomes"] = ["failed", "passed", "passed"]
    rec["observations_by_rep"] = {
        "r0": ["failed"],
        "r1": ["passed"],
        "r2": ["passed"],
    }
    payload["p2p_s_claim"] = False
    payload["control_qualification"] = {
        "decision": "PASS",
        "reason": "NEG rc=1 recorded as expected test failures; sensitivity supported",
        "sensitivity_supported": True,
    }
    assert rs.validate_receipt(payload) == "PASS"


def test_hard_empty_per_node_outcomes_must_block() -> None:
    """(e) an empty per_node_outcomes object currently passes -- must raise."""
    payload = _base_receipt()
    payload["per_node_outcomes"] = {}
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "per_node_outcomes" in str(ei.value)


def test_hard_malformed_junit_names_raise_receipt_error_not_index_error() -> None:
    """(f) malformed JUnit filenames must raise ReceiptError -- today the
    name-splitting code either raises IndexError or silently ignores them."""
    t12 = TID12
    bad_names = [
        "no_underscores_at_all",
        t12,                     # truncated name
        f"{t12}_t",              # truncated name
        f"{t12}_t_r0",           # missing f-slots
        f"{t12}_t_r0_f0",        # missing .xml suffix
        f"{t12}_x_r0_f0.xml",    # side outside t/p
        "zzz_t_r0_f0.xml",       # not this task's file prefix
    ]
    for bad in bad_names:
        payload = _base_receipt()
        payload["outputs"]["junit"][0] = {
            "file": bad, "sha256": "8" * 64, "raw": True
        }
        with pytest.raises(rs.ReceiptError):
            rs.validate_receipt(payload)


def test_hard_scope_patch_paths_must_reject_test_paths() -> None:
    """A common test-patch path inside scope_patch_paths must be rejected:
    tests are NOT editable production scope."""
    payload = _base_receipt()
    payload["scope"]["scope_patch_paths"] = [
        "saleor/app/tests/test_app_commands.py"
    ]
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "test" in str(ei.value).lower()


def test_hard_patch_edits_outside_scope_or_in_tests_must_block() -> None:
    payload = _base_receipt()
    payload["scope"]["scope_patch_sha256"] = "a" * 64
    payload["scope"]["patch_edits"] = ["saleor/checkout/views.py"]
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(payload)
    payload["scope"]["patch_edits"] = ["saleor/app/tests/test_app_commands.py"]
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(payload)


def test_hard_node_identity_sha256_is_canonical_of_observed_set() -> None:
    """expected==observed is not enough: the observed hash must EQUAL the
    canonical hash of the per-node identity set carried in the receipt."""
    payload = _base_receipt()
    payload["node_identity"]["expected_sha256"] = "5" * 64
    payload["node_identity"]["observed_sha256"] = "5" * 64
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "identity set" in str(ei.value).lower()


def test_hard_task_keyed_node_identity_is_validated_not_flag_trusted() -> None:
    """Identity sets must be checked against authoritative task-keyed node
    ids -- the caller-supplied EXACT_MATCH flag alone is not enough."""
    payload = _base_receipt()
    node = next(iter(payload["per_node_outcomes"]))
    rs.validate_receipt(payload, expected_task_node_ids={node})
    payload["per_node_outcomes"]["ghost-node"] = payload["per_node_outcomes"][node]
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload, expected_task_node_ids={node})
    assert "identity set" in str(ei.value).lower()


def test_hard_raw_hashes_verified_at_trusted_consumer_boundary(tmp_path: Path) -> None:
    """Schema validation must NOT imply disk content; raw-file hashes are
    re-verified against the actual files at the trusted consumer boundary."""
    payload = _base_receipt()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for item in payload["outputs"]["junit"]:
        # fixture recorded hashes are sha256 of the FILE NAME bytes
        (raw_dir / item["file"]).write_text(item["file"], encoding="utf-8")
    verified = rs.verify_raw_file_hashes(payload, raw_dir)
    assert set(verified) == {i["file"] for i in payload["outputs"]["junit"]}
    # late-arriving mutation on disk must be caught at the boundary
    first = sorted(raw_dir.iterdir())[0]
    first.write_text("y" * 8, encoding="utf-8")
    with pytest.raises(rs.ReceiptError):
        rs.verify_raw_file_hashes(payload, raw_dir)


def test_hard_blocked_runs_kept_as_diagnostic_verdict() -> None:
    """Failed runs are KEPT as diagnostic evidence with an explicit BLOCKED
    verdict (never discarded, and never PASS)."""
    payload = _base_receipt(
        control_qualification={"decision": "BLOCKED", "reason": "not met"}
    )
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    record = rs.blocked_receipt_verdict(payload, ei.value)
    assert record["verdict"] == "BLOCKED"
    assert record["task_id"] == T7E42
    assert "BLOCKED" in record["blocking_reason"]


def test_hard_per_node_outcomes_agree_with_raw_repetition_evidence() -> None:
    """Per-node outcomes and raw-repetition identities must AGREE; synthetic
    outcome lists without matching observations_by_rep are rejected."""
    payload = _base_receipt()
    node = next(iter(payload["per_node_outcomes"]))
    rec = payload["per_node_outcomes"][node]["t"]
    rec["observations_by_rep"]["r1"] = ["failed"]
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "not agree" in str(ei.value).lower()
    payload = _base_receipt()
    node = next(iter(payload["per_node_outcomes"]))
    payload["per_node_outcomes"][node]["p"].pop("observations_by_rep")
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(payload)
    assert "observations_by_rep" in str(ei.value)


def test_hard_rep_index_must_cover_all_three_reps() -> None:
    payload = _base_receipt()
    payload["rep_index"] = [0, 1]
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(payload)
