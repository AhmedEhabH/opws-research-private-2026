"""M19A4-R -- adversarial synthetic tests for PHYSICAL repetition identity.

The strict M19A4 stability rule (`stability_strict`) requires exactly 3
recorded outcomes, all 'passed', but does NOT verify that those 3 observations
come from three DISTINCT repetition indices. These tests prove the count-based
rule can be fooled by duplicates within one rep, and that the per-repetition
identity logic (`per_rep_stable` in the M19A4-R diagnostic) fails closed on
every adversarial case:

  - three passing observations all from r0  =>  NOT 3/3 (missing r1, r2);
  - one passing observation per r0/r1/r2     =>  3/3 (per-repetition stable);
  - missing r1                                =>  fails closed;
  - failed r2                                 =>  fails closed;
  - duplicate conflicting fragments in r1     =>  fails closed;
  - parent/target mismatch (one side missing a rep) => fails closed.

All cases are synthetic XML (frozen parser, offline); no Saleor execution, no
real evidence, no modification of any M19A4 artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(ROOT / "src" / "benchmark" / "wp2"))

import oracle_confirmation  # noqa: E402

from scripts.opws_m19a4_p2p_s_recover import recover_task  # noqa: E402
from scripts.opws_m19a4_p2p_s_rep_identity_diagnostic import (  # noqa: E402
    per_rep_stable,
    rep_distribution,
)

P2P_ONLY = "P2P_ONLY"
FLAKY = "FLAKY"


def _junit_xml(cases):
    """cases: list of (node_id, kind); kind in passed/failed/error/skipped."""
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


def _write_evidence(tmp_path, plan) -> tuple[str, Path]:
    """Write per-(state,rep,idx) node maps as JUnit XML; return task_id.

    plan: dict[(state, rep, idx)] -> {node_id: outcome}
    """
    tid = "saleor-rc-aaaa1111bb22"
    t12 = "aaaa1111bb22"
    base = tmp_path / "junit" / "opt" / "wp2_v2" / "c2_artifact_rescue"
    for state in ("p", "t"):
        for rep in range(3):
            for idx in range(3):
                d = base / f"{t12}_{state}"
                d.mkdir(parents=True, exist_ok=True)
                case_map = plan.get((state, rep, idx), {})
                (d / f"{t12}_{state}_r{rep}_f{idx}.xml").write_text(
                    _junit_xml([(n, o) for n, o in sorted(case_map.items())]),
                    encoding="utf-8")
    return tid, base


def _evidence_base(tmp_path, plan):
    return _write_evidence(tmp_path, plan)[1]


NODE = "saleor/a/tests/test_a.py::test_n"


def _plan_with(case: str, nf: int = 3):
    """Build a per-(state,rep,idx) plan for one adversarial scenario."""
    plan = {}
    scenarios = {
        "r0_only": {  # three passing observations, ALL from r0, on both sides
            (rep, idx): "passed" for rep in (0,) for idx in range(nf)
        },
        "one_per_rep": {  # one passing observation per r0/r1/r2, both sides
            (rep, 0): "passed" for rep in (0, 1, 2)
        },
        "missing_r1": {  # r0 and r2 present, r1 absent
            (0, 0): "passed", (2, 0): "passed"
        },
        "failed_r2": {
            (0, 0): "passed", (1, 0): "passed", (2, 0): "failed"
        },
        "dup_conflict_r1": {  # r1 has two fragments with conflicting outcomes
            (0, 0): "passed", (1, 0): "passed", (1, 1): "error", (2, 0): "passed"
        },
        "target_only_missing_rep": {  # target 3/3, parent missing r2
            (0, 0): "passed", (1, 0): "passed", (2, 0): "passed"
        },
    }
    for (rep, idx), outcome in scenarios[case].items():
        for state in ("p", "t"):
            dst_rep = rep
            # parent/target mismatch: parent misses r2 entirely
            if case == "target_only_missing_rep" and state == "p" and rep == 2:
                continue
            plan[(state, dst_rep, idx)] = {NODE: outcome}
    return plan


def _evidence_base(tmp_path, plan):
    tid, base = _write_evidence(tmp_path, plan)
    return base


def _reps_of(parsed_per_fragment, state: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for (st, rep, _idx), (nodes, _fails) in parsed_per_fragment.items():
        if st == state and NODE in nodes:
            out.setdefault(rep, []).append(nodes[NODE])
    return out


@pytest.mark.parametrize(
    "case,expected_stable,expected_strict_class",
    [
        # three passing observations all from r0 -> NOT 3/3 per repetition
        ("r0_only", False, P2P_ONLY),
        # one passing observation per r0/r1/r2 -> IS 3/3
        ("one_per_rep", True, P2P_ONLY),
        # missing r1 -> fails closed
        ("missing_r1", False, FLAKY),
        # failed r2 -> fails closed
        ("failed_r2", False, FLAKY),
        # duplicate conflicting fragments in r1 -> fails closed
        ("dup_conflict_r1", False, FLAKY),
    ],
)
def test_adversarial_rep_identity(tmp_path, case, expected_stable, expected_strict_class):
    plan = _plan_with(case)
    base = _evidence_base(tmp_path, plan)
    res = recover_task(task_id="saleor-rc-aaaa1111bb22", n_test_files=3,
                       base=base, parse_func=oracle_confirmation.parse_junit_with_failures)
    by_id = {x["node_id"]: x for x in res["ledger"]}
    node = by_id[NODE]

    parsed: dict[tuple[str, int, int], tuple[dict[str, str], dict[str, str]]] = {}
    for state in ("p", "t"):
        for rep in range(3):
            for idx in range(3):
                f = base / f"aaaa1111bb22_{state}" / f"aaaa1111bb22_{state}_r{rep}_f{idx}.xml"
                if f.exists():
                    parsed[(state, rep, idx)] = oracle_confirmation.parse_junit_with_failures(
                        f.read_text(encoding="utf-8"))

    t_reps = _reps_of(parsed, "t")
    p_reps = _reps_of(parsed, "p")

    # count-based strict 3/3 (the CURRENT M19A4 rule) vs physical distinct reps
    assert per_rep_stable(t_reps) == per_rep_stable(p_reps) == expected_stable
    assert node["strict_class"] == expected_strict_class
    if case == "r0_only":
        # adversarial: count-based rule says 3/3 (3 passed observations)...
        assert node["t_appearances"] == 3 and node["p_appearances"] == 3
        assert node["strict_class"] == P2P_ONLY
        # ...but physical repetition identity must reject three obs from ONE rep
        assert per_rep_stable(t_reps) is False and per_rep_stable(p_reps) is False
    if case == "one_per_rep":
        assert per_rep_stable(t_reps) is True and per_rep_stable(p_reps) is True
    # rep distribution sanity
    t_dist = rep_distribution(t_reps)
    p_dist = rep_distribution(p_reps)
    if case == "r0_only":
        assert t_dist == (3, 0, 0) and p_dist == (3, 0, 0)
    elif case == "one_per_rep":
        assert t_dist == (1, 1, 1) and p_dist == (1, 1, 1)


def test_parent_target_mismatch_fails_closed(tmp_path):
    plan = _plan_with("target_only_missing_rep")
    base = _evidence_base(tmp_path, plan)
    res = recover_task(task_id="saleor-rc-aaaa1111bb22", n_test_files=3,
                       base=base, parse_func=oracle_confirmation.parse_junit_with_failures)
    by_id = {x["node_id"]: x for x in res["ledger"]}
    node = by_id[NODE]
    # target has 3 passing runs, parent has only 2 -> not 3/3 P2P_ONLY
    assert node["strict_class"] == FLAKY
    assert node["t_appearances"] == 3 and node["p_appearances"] == 2


def test_one_per_rep_true_stable_three_thirds(tmp_path):
    """One passing observation per r0/r1/r2 on BOTH sides is 3/3."""
    plan = _plan_with("one_per_rep")
    base = _evidence_base(tmp_path, plan)
    res = recover_task(task_id="saleor-rc-aaaa1111bb22", n_test_files=3,
                       base=base, parse_func=oracle_confirmation.parse_junit_with_failures)
    by_id = {x["node_id"]: x for x in res["ledger"]}
    node = by_id[NODE]
    assert node["strict_class"] == P2P_ONLY
    assert node["t_runs"] == ["passed", "passed", "passed"]
    assert node["p_runs"] == ["passed", "passed", "passed"]


def test_r0_duplicates_not_three_thirds():
    """Strict count-based rule alone cannot distinguish r0-only from 3 distinct
    reps; per_rep_stable is the check that must be added."""
    # per-rep maps: both sides see 3 observations, all in rep 0
    t_reps = {0: ["passed", "passed", "passed"]}
    p_reps = {0: ["passed", "passed", "passed"]}
    assert per_rep_stable(t_reps) is False
    assert per_rep_stable(p_reps) is False
    # if they had been spread one-per-rep, they WOULD be stable
    assert per_rep_stable({0: ["passed"], 1: ["passed"], 2: ["passed"]}) is True
