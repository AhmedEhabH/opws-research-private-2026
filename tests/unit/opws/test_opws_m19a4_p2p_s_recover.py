"""M19A4-ATOMIC1 — offline unit tests for P2P-S exact identity recovery.

SCOPE: pure classification/stability semantics, canonical identity hashing and
a synthetic XML replay of the frozen merge+classify pipeline. Nothing here
touches real task evidence (no Saleor/Docker/API), and the real-evidence
integration test is skipped unless M19A4_EVIDENCE_TEST=1 is set.

The two frozen sensitivity examples that ground the historical-vs-strict
distinction are reproduced as synthetic fixtures:
  - saleor-rc-032b98afff20 style: parent runs [passed,failed,passed],
    target [passed,passed,passed]  =>  hist P2P_ONLY / strict FLAKY;
  - saleor-rc-30b4edece5aa style: parent runs [passed,passed,passed],
    target [failed,passed,passed]  =>  hist P2P_ONLY / strict FLAKY.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import opws_m19a4_p2p_s_recover as m19a4  # noqa: E402
from scripts.opws_m19a4_p2p_s_recover import (  # noqa: E402
    classify_hist,
    classify_strict,
    node_identity_hash,
    recover_task,
    stability_hist,
    stability_strict,
)

if str(ROOT / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(ROOT / "src" / "benchmark" / "wp2"))
import oracle_confirmation  # noqa: E402  (frozen parser, hash-pinned)

P2P_ONLY = "P2P_ONLY"
FLAKY = "FLAKY"
BEHAVIORAL_F2P = "BEHAVIORAL_F2P"
SYMBOL_ABSENCE_F2P = "SYMBOL_ABSENCE_F2P"
TARGET_ORACLE_INVALID = "TARGET_ORACLE_INVALID"
PARENT_COLLECTION_ERROR = "PARENT_COLLECTION_ERROR"


# --------------------------------------------------------------------------- #
# classification semantics (pure)                                             #
# --------------------------------------------------------------------------- #
def test_stability_hist_requires_exactly_three():
    with pytest.raises(ValueError):
        stability_hist(["passed", "passed"])


def test_hist_p2p_only_when_both_last_scalars_passed():
    cls = classify_hist(
        target_outcomes=["passed", "passed", "passed"],
        parent_outcomes=["passed", "passed", "passed"],
        parent_failure_text="",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert cls == P2P_ONLY


def test_hist_flaky_when_parent_absent():
    # historical: parent scalar missing -> [missing]*3 -> FLAKY
    cls = classify_hist(
        target_outcomes=["passed", "passed", "passed"],
        parent_outcomes=["missing", "missing", "missing"],
        parent_failure_text="",
        parent_collects_node=False,
        shared_test_support_failed=True,
    )
    assert cls == FLAKY


def test_strict_flaky_on_mixed_parent_runs():
    # frozen sensitivity example (saleor-rc-032b98afff20)
    cls = classify_strict(
        target_runs=["passed", "passed", "passed"],
        parent_runs=["passed", "failed", "passed"],
        parent_failure_text="",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert cls == FLAKY


def test_strict_flaky_on_mixed_target_runs():
    # frozen sensitivity example (saleor-rc-30b4edece5aa)
    cls = classify_strict(
        target_runs=["failed", "passed", "passed"],
        parent_runs=["passed", "passed", "passed"],
        parent_failure_text="",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert cls == FLAKY


def test_strict_requires_full_pass_triple():
    # appearance shortage is instability, never stable pass
    assert stability_strict(["passed", "passed"]) == FLAKY
    assert stability_strict(["passed", "passed", "passed"]) == "STABLE_PASS"


def test_symbol_absence_vs_behavioral():
    sym = classify_hist(
        target_outcomes=["passed"] * 3,
        parent_outcomes=["failed"] * 3,
        parent_failure_text="ModuleNotFoundError: No module named 'x'",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert sym == SYMBOL_ABSENCE_F2P
    beh = classify_hist(
        target_outcomes=["passed"] * 3,
        parent_outcomes=["failed"] * 3,
        parent_failure_text="assert 1 == 2",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert beh == BEHAVIORAL_F2P


def test_parent_collection_error_precedence():
    cls = classify_hist(
        target_outcomes=["passed"] * 3,
        parent_outcomes=["failed"] * 3,
        parent_failure_text="",
        parent_collects_node=False,
        shared_test_support_failed=True,
    )
    assert cls == PARENT_COLLECTION_ERROR


def test_target_invalid_when_target_scalar_not_passed():
    cls = classify_hist(
        target_outcomes=["failed", "failed", "failed"],
        parent_outcomes=["passed"] * 3,
        parent_failure_text="",
        parent_collects_node=True,
        shared_test_support_failed=False,
    )
    assert cls == TARGET_ORACLE_INVALID


# --------------------------------------------------------------------------- #
# canonical identity hashing                                                  #
# --------------------------------------------------------------------------- #
def test_node_identity_hash_deterministic_and_order_free():
    a = node_identity_hash("saleor-rc-aaaa1111bb22", ["b.py::t", "a.py::t"], ["a.py::t", "b.py::t"])
    b = node_identity_hash("saleor-rc-aaaa1111bb22", ["a.py::t", "b.py::t"], ["a.py::t", "b.py::t"])
    assert a == b
    assert len(a) == 64
    c = node_identity_hash("saleor-rc-aaaa1111bb22", ["a.py::t"], ["a.py::t", "b.py::t"])
    assert c != a


def test_canonical_json_is_sorted_and_compact():
    blob = m19a4.canonical_json({"z": 1, "a": [3, 1]})
    assert blob == '{"a":[3,1],"z":1}'


# --------------------------------------------------------------------------- #
# synthetic XML replay (frozen merge order + real frozen parser)             #
# --------------------------------------------------------------------------- #
def _junit_xml(cases):
    """cases: list of (node_id, kind) with kind in passed/failed/error/skipped."""
    body = []
    for node_id, kind in cases:
        fname, name = node_id.split("::", 1)
        if kind == "failed":
            inner = "<failure message='boom'>Traceback\nassert 1 == 2</failure>"
        elif kind == "error":
            inner = "<error message='err'>Traceback\nModuleNotFoundError: No module named x</error>"
        elif kind == "skipped":
            inner = "<skipped/>"
        else:
            inner = ""
        body.append(f'<testcase file="{fname}" name="{name}">{inner}</testcase>')
    return f'<?xml version="1.0" encoding="utf-8"?><testsuite>{"".join(body)}</testsuite>'


def _synthetic_evidence(tmp_path):
    """One mini task, nf=2, covering merge, classification and appearance rules.

    A: only in f0 -> 3 appearances per side => P2P_ONLY both variants.
    B: only in f1, parent runs [passed,failed,passed] => hist P2P_ONLY / strict FLAKY.
    C: only in f1, target runs [passed,passed,failed] => TARGET_ORACLE_INVALID both.
    D: in f0 AND f1 of every rep (6 appearances/side) while every scalar passes
       => hist P2P_ONLY / strict FLAKY (appearance count != 3 is instability).
    """
    tid = "saleor-rc-aaaa1111bb22"
    t12 = "aaaa1111bb22"
    base = tmp_path / "junit" / "opt" / "wp2_v2" / "c2_artifact_rescue"
    n_a = "saleor/a/tests/test_a.py::test_stable"
    n_b = "saleor/b/tests/test_b.py::test_mixed_parent"
    n_c = "saleor/c/tests/test_c.py::test_target_broken"
    n_d = "saleor/d/tests/test_d.py::test_multi_file"
    plan = {}
    for state in ("p", "t"):
        for rep in range(3):
            plan[(state, rep, 0)] = {n_a: "passed", n_d: "passed"}
            plan[(state, rep, 1)] = {
                n_d: "passed",
                n_b: "failed" if state == "p" and rep == 1 else "passed",
                n_c: "failed" if state == "t" and rep == 2 else "passed",
            }
    for (state, rep, idx), case_map in sorted(plan.items()):
        d = base / f"{t12}_{state}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{t12}_{state}_r{rep}_f{idx}.xml").write_text(
            _junit_xml([(n, o) for n, o in sorted(case_map.items())]), encoding="utf-8")
    return tid, base


def test_synthetic_replay_classification(tmp_path):
    tid, base = _synthetic_evidence(tmp_path)
    res = recover_task(task_id=tid, n_test_files=2, base=base,
                       parse_func=oracle_confirmation.parse_junit_with_failures)
    assert res["n_nodes"] == 4
    by_id = {x["node_id"]: x for x in res["ledger"]}
    a = by_id["saleor/a/tests/test_a.py::test_stable"]
    assert a["t_appearances"] == 3 and a["p_appearances"] == 3
    assert a["hist_class"] == P2P_ONLY and a["strict_class"] == P2P_ONLY
    b = by_id["saleor/b/tests/test_b.py::test_mixed_parent"]
    assert b["p_runs"] == ["passed", "failed", "passed"]
    assert b["hist_class"] == P2P_ONLY and b["strict_class"] == FLAKY
    c = by_id["saleor/c/tests/test_c.py::test_target_broken"]
    assert c["t_runs"] == ["passed", "passed", "failed"]
    assert c["hist_class"] == TARGET_ORACLE_INVALID
    assert c["strict_class"] == FLAKY  # mixed runs are flaky, not target-invalid, under strict
    d = by_id["saleor/d/tests/test_d.py::test_multi_file"]
    assert d["t_appearances"] == 6 and d["p_appearances"] == 6
    assert d["hist_class"] == P2P_ONLY and d["strict_class"] == FLAKY
    assert res["hist_counts"][P2P_ONLY] == 3
    assert res["strict_counts"][P2P_ONLY] == 1
    assert res["strict_counts"][FLAKY] == 3


# --------------------------------------------------------------------------- #
# guarded real-evidence integration check                                    #
# --------------------------------------------------------------------------- #
REAL_EVIDENCE = Path("D:/WP2/evidence/C2_MAIN83_JUNIT_RESCUE_2026-10-23")
RUN_REAL = os.environ.get("M19A4_EVIDENCE_TEST") == "1"


@pytest.mark.skipif(not RUN_REAL or not REAL_EVIDENCE.exists(),
                    reason="set M19A4_EVIDENCE_TEST=1 with evidence on disk to run")
def test_real_evidence_aggregates(tmp_path):
    """Full 83-task replay against frozen evidence (opt-in, slow)."""
    import scripts.opws_m19a4_p2p_s_recover as mod

    out = tmp_path / "out"
    sys.argv = [
        "opws_m19a4_p2p_s_recover.py",
        "--evidence-root", str(REAL_EVIDENCE),
        "--out", str(out),
        "--skip-evidence-file-hashes",
    ]
    rc = mod.main()
    assert rc == 0
    doc = json.loads((out / "M19A4_P2P_ONLY_NODES_BY_TASK_83.json").read_text(encoding="utf-8"))
    assert doc["totals"]["tasks"] == 83
    assert doc["totals"]["p2p_only_historical"] == 9275
    assert doc["totals"]["p2p_only_strict"] == 9273
    assert doc["totals"]["f2p_historical"] == 795
    assert doc["totals"]["f2p_strict"] == 770
    assert doc["totals"]["changed_nodes_hist_vs_strict"] == 27
    assert doc["counts_reconcile_summary"]["tasks_with_issues"] == 0
    # determinism: identical byte output on identical evidence input
    assert doc["aggregate_identity_sha256"] == (
        "9fc10bc12d382ba2ee83bb1c6498046483b162ff2b3016b77ea2fa3cb0edf10a")
