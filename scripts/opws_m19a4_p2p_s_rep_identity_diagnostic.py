"""OPWS M19A4-R -- P2P Physical-Repetition Identity DIAGNOSTIC (read-only).

Independent audit of the M19A4 P2P_ONLY recovery: does strict pass/pass
actually represent three DISTINCT repetition indices on both parent and
target?

This script is READ-ONLY. It:
  - re-enumerates the frozen 83-task evidence exactly like
    scripts/opws_m19a4_p2p_s_recover.py (same pins, frozen parser,
    rep-major/file-minor merge),
  - groups every observation per task/node/side by repetition index r0/r1/r2
    and by fragment index,
  - classifies each node under:
      A  historical P2P_ONLY  (last-write-wins + [last]*3),
      B  existing strict P2P_ONLY (exactly 3 recorded outcomes, all 'passed',
         count-based, no rep-distinctness check) -- the CURRENT M19A4 set,
      C  per-repetition stable pass: on BOTH sides, each rep r0..r2 is present
         with all-passed observations (>=1 observation per rep per side, no
         non-passed observation in any rep),
  - records MISSING rep indices, REPEATED observations within one rep
    (same node, same side, same rep, multiple fragments), and CONFLICTING
    observations (same node, same side, same rep, differing outcomes),
  - diffs A/B/C per task and reports exact node IDs for every B\\C (strict
    3/3 that is NOT three distinct passing reps on both sides).

No task artifact is modified. Output is written to a NEW file
M19A4_REP_IDENTITY_DIAGNOSTIC.json under the --out directory (default
reports/m19a4_p2ps/). Original M19A4 artifacts are untouched.

Exit code: 0 on completion (diagnostic findings are DATA, not failures);
the BLOCKING flag lives in the report artifact.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(REPO / "src" / "benchmark" / "wp2"))

import oracle_confirmation  # noqa: E402  (frozen parser, hash-pinned)

from scripts.opws_m19a4_p2p_s_recover import (  # noqa: E402
    CLASSIFIER_PINS,
    CONTRACT,
    CONTRACT_SHA256,
    EVIDENCE_MANIFEST_SHA256,
    PER_TASK_JSONL,
    SENSITIVITY,
    SENSITIVITY_SHA256,
    canonical_doc_bytes,
    file_sha256,
    loader_variants_contain,
    recover_task,
)

REPS = (0, 1, 2)
OUT_ARTIFACT = "M19A4_REP_IDENTITY_DIAGNOSTIC.json"


# --------------------------------------------------------------------------- #
# pure per-repetition logic (unit-testable, no I/O)                           #
# --------------------------------------------------------------------------- #
def rep_grouped(observations_by_rep: dict[int, list[str]]) -> dict[int, list[str]]:
    """Normalize {rep: [outcomes...]} -> {rep: sorted unique outcomes}.

    Keeps only observed reps; 'missing' reps are simply absent.
    """
    return {
        rep: sorted(set(outcomes))
        for rep, outcomes in sorted(observations_by_rep.items())
        if outcomes
    }


def per_rep_stable(observations_by_rep: dict[int, list[str]]) -> bool:
    """C: all three reps present, each with >=1 observation, all 'passed'."""
    if set(observations_by_rep) != set(REPS):
        return False
    return all(
        outcomes and all(o == "passed" for o in outcomes)
        for outcomes in observations_by_rep.values()
    )


def rep_distribution(observations_by_rep: dict[int, list[str]]) -> tuple[int, int, int]:
    """(n_r0, n_r1, n_r2) observation counts, missing reps = 0."""
    return tuple(len(observations_by_rep.get(r, ())) for r in REPS)  # type: ignore[return-value]


def per_task_rep_diagnostics(
    parsed_per_fragment: dict[tuple[str, int, int], tuple[dict[str, str], dict[str, str]]],
) -> dict:
    """Group parsed per-(state,rep,idx) node maps into per-node rep structures."""
    by_rep: dict[str, dict[str, dict[int, list[str]]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list))
    )
    for (state, rep, _idx), (nodes, _fails) in sorted(parsed_per_fragment.items()):
        for n, o in nodes.items():
            by_rep[n][state][rep].append(o)
    return {n: {"t": dict(by_rep[n]["t"]), "p": dict(by_rep[n]["p"])} for n in by_rep}


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="M19A4-R rep-identity diagnostic (read-only)")
    ap.add_argument("--evidence-root", required=True)
    ap.add_argument("--out", default=str(REPO / "reports" / "m19a4_p2ps"))
    ap.add_argument("--skip-evidence-file-hashes", action="store_true",
                    help="internal: skip full hash verification (tests)")
    ap.add_argument("--bench", action="store_true", help="report elapsed timing")
    args = ap.parse_args()

    t0 = datetime.datetime.now(datetime.UTC)

    for fn, pin in CLASSIFIER_PINS.items():
        if not loader_variants_contain(pin, Path(__file__).resolve().parents[1] / "src" / "benchmark" / "wp2" / fn):
            raise SystemExit(f"STOP: classifier pin mismatch {fn}")
    parse_func = oracle_confirmation.parse_junit_with_failures

    evid = Path(args.evidence_root)
    manifest = evid / "JUNIT_EVIDENCE_MANIFEST.json"
    if file_sha256(manifest) != EVIDENCE_MANIFEST_SHA256:
        raise SystemExit("STOP: evidence manifest hash mismatch")
    checks: list[tuple[str, Path, str | None]] = [
        ("f2p_node_contract_83", CONTRACT, CONTRACT_SHA256),
        ("three_run_sensitivity_83", SENSITIVITY, SENSITIVITY_SHA256),
        ("per_task_v2_jsonl", PER_TASK_JSONL, None),
    ]
    for label, path, expected_sha in checks:
        h = file_sha256(path)
        if expected_sha is not None and h != expected_sha:
            raise SystemExit(f"STOP: {label} hash mismatch {path}")

    ev = json.loads(manifest.read_text(encoding="utf-8"))
    if not args.skip_evidence_file_hashes:
        bad = [r[2] for r in ev["files"] if file_sha256(evid / r[2]) != r[3]]
        if bad:
            raise SystemExit(f"STOP: {len(bad)} evidence files changed: {bad[:5]}")

    per_task = {}
    for line in PER_TASK_JSONL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            per_task[r["task_id"]] = r

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract_tasks = sorted(contract["tasks"], key=lambda t: t["task_id"])
    if len(contract_tasks) != 83:
        raise SystemExit("STOP: expected 83 contract tasks")

    # on-disk B (existing strict P2P_ONLY set) for cross-check
    art_dir = Path(args.out)
    main_artifact = json.loads(
        (art_dir / "M19A4_P2P_ONLY_NODES_BY_TASK_83.json").read_text(encoding="utf-8"))
    disk_b_by_task = {
        r["task_id"]: set(r["strict_p2p_only"]) for r in main_artifact["tasks"]
    }

    base = evid / "junit" / "opt" / "wp2_v2" / "c2_artifact_rescue"

    per_task_out = []
    totals: collections.Counter[str] = collections.Counter()
    dup_total = 0
    conflict_total = 0
    b_not_c_nodes_total = 0
    c_not_b_nodes_total = 0
    a_not_c_nodes_total = 0

    for t in contract_tasks:
        tid = t["task_id"]
        t12 = tid.split("saleor-rc-")[1][:12]
        nf = per_task[tid]["n_test_files"]

        parsed: dict[tuple[str, int, int], tuple[dict[str, str], dict[str, str]]] = {}
        for state in ("p", "t"):
            for rep in REPS:
                for idx in range(nf):
                    f = base / f"{t12}_{state}" / f"{t12}_{state}_r{rep}_f{idx}.xml"
                    if not f.exists():
                        raise RuntimeError(f"missing enumerated junit {f}")
                    try:
                        nodes, fails = parse_func(f.read_text(encoding="utf-8"))
                    except Exception as exc:
                        raise RuntimeError(f"unparseable junit {f}: {exc}") from exc
                    parsed[(state, rep, idx)] = (nodes, fails)

        res = recover_task(task_id=tid, n_test_files=nf, base=base, parse_func=parse_func)
        hist_class = {x["node_id"]: x["hist_class"] for x in res["ledger"]}
        strict_class = {x["node_id"]: x["strict_class"] for x in res["ledger"]}
        ledger_by_id = {x["node_id"]: x for x in res["ledger"]}

        repmap = per_task_rep_diagnostics(parsed)

        a_set = {n for n, c in hist_class.items() if c == "P2P_ONLY"}
        b_computed = {n for n, c in strict_class.items() if c == "P2P_ONLY"}
        b_disk = disk_b_by_task.get(tid, set())
        if b_computed != b_disk:
            raise SystemExit(
                f"STOP: recomputed B != on-disk B for {tid}: "
                f"{len(b_computed ^ b_disk)} node delta")
        c_set = set()
        for n, sides in repmap.items():
            if per_rep_stable(sides["t"]) and per_rep_stable(sides["p"]):
                c_set.add(n)

        # duplicate / conflict diagnostics over ALL nodes
        dups: list[dict] = []
        conflicts: list[dict] = []
        for n, sides in repmap.items():
            for state in ("t", "p"):
                for rep, outcomes in sides[state].items():
                    if len(outcomes) > 1:
                        dup_total += 1
                        dups.append(
                            {"node_id": n, "side": state, "rep": rep,
                             "n_observations": len(outcomes)})
                    if len(set(outcomes)) > 1:
                        conflict_total += 1
                        conflicts.append(
                            {"node_id": n, "side": state, "rep": rep,
                             "outcomes": sorted(set(outcomes))})

        b_rep_dist = {
            n: (rep_distribution(repmap[n]["t"]), rep_distribution(repmap[n]["p"]))
            for n in sorted(b_computed)
        }
        dist_counter = collections.Counter((x[0], x[1]) for x in b_rep_dist.values())
        b_rep_hist = {f"t={k_t} p={k_p}": v for (k_t, k_p), v in dist_counter.items()}

        b_not_c = sorted(b_computed - c_set)
        c_not_b = sorted(c_set - b_computed)
        a_not_c = sorted(a_set - c_set)
        b_not_c_nodes_total += len(b_not_c)
        c_not_b_nodes_total += len(c_not_b)
        a_not_c_nodes_total += len(a_not_c)

        b_not_c_details = [
            {
                "node_id": n,
                "t_reps_present": sorted(repmap[n]["t"]),
                "p_reps_present": sorted(repmap[n]["p"]),
                "t_dist": list(rep_distribution(repmap[n]["t"])),
                "p_dist": list(rep_distribution(repmap[n]["p"])),
                "t_runs": ledger_by_id[n]["t_runs"],
                "p_runs": ledger_by_id[n]["p_runs"],
            }
            for n in b_not_c
        ]
        b_not_c_details.sort(key=lambda d: (d["node_id"]))

        totals["tasks"] += 1
        totals["n_nodes"] += res["n_nodes"]
        totals["a_hist_p2p"] += len(a_set)
        totals["b_strict_p2p"] += len(b_computed)
        totals["c_rep_stable"] += len(c_set)
        totals["b_not_c"] += len(b_not_c)
        totals["c_not_b"] += len(c_not_b)
        totals["a_not_c"] += len(a_not_c)
        totals["duplicates_within_rep"] += len(dups)
        totals["conflicts_within_rep"] += len(conflicts)

        per_task_out.append(
            {
                "task_id": tid,
                "n_nodes": res["n_nodes"],
                "counts": {
                    "A_hist_p2p": len(a_set),
                    "B_strict_p2p": len(b_computed),
                    "C_rep_stable_both_sides": len(c_set),
                    "B_not_C": len(b_not_c),
                    "C_not_B": len(c_not_b),
                    "A_not_C": len(a_not_c),
                },
                "b_rep_distribution_histogram": b_rep_hist,
                "b_not_c_nodes": b_not_c,
                "b_not_c_details": b_not_c_details,
                "c_not_b_nodes": c_not_b,
                "a_not_c_nodes": a_not_c,
                "duplicates_within_rep": dups,
                "conflicts_within_rep": conflicts,
            }
        )

    dup_records = [d for r in per_task_out for d in r["duplicates_within_rep"]]
    conf_records = [d for r in per_task_out for d in r["conflicts_within_rep"]]
    doc = {
        "artifact": "M19A4_REP_IDENTITY_DIAGNOSTIC",
        "schema": "opws-m19a4-p2ps/repid-diag/1.0",
        "status": "READ_ONLY_DIAGNOSTIC; no task artifact modified",
        "definition_A": "historical P2P_ONLY (last-write-wins merge + [last]*3; recover_task hist_class)",
        "definition_B": "existing strict P2P_ONLY (exactly 3 recorded outcomes, all 'passed'; count-based, "
                        "NO rep-distinctness check; matches on-disk M19A4 artifact node-for-node)",
        "definition_C": ("per-repetition stable pass on both sides: for each side t/p and each rep r0/r1/r2, "
                          ">=1 observation in that rep AND every observation in that rep is 'passed'"),
        "reps": list(REPS),
        "inputs": {
            "evidence_manifest_sha256": EVIDENCE_MANIFEST_SHA256,
            "contract_sha256": CONTRACT_SHA256,
            "sensitivity_sha256": SENSITIVITY_SHA256,
            "classifier_pins": CLASSIFIER_PINS,
            "evidence_file_hashes_full_scan": not args.skip_evidence_file_hashes,
        },
        "totals": dict(totals),
        "b_not_c_summary": {
            "definition": ("strict P2P_ONLY nodes whose 3 observations are NOT one per distinct rep "
                           "(>=1 rep missing on a side or >1 observation in some rep) or a rep contains "
                           "a non-passed observation -> NOT per-repetition stable"),
            "n_nodes": b_not_c_nodes_total,
            "tasks_affected": [r["task_id"] for r in per_task_out if r["b_not_c_nodes"]],
            "node_ids": sorted(
                n for r in per_task_out for n in r["b_not_c_nodes"]),
        },
        "c_not_b_summary": {
            "definition": ("per-repetition stable nodes NOT in the strict count-based 3/3 set "
                           "(e.g., >3 observations spread across reps, all passed)"),
            "n_nodes": c_not_b_nodes_total,
            "tasks_affected": [r["task_id"] for r in per_task_out if r["c_not_b_nodes"]],
            "node_ids": sorted(
                n for r in per_task_out for n in r["c_not_b_nodes"]),
        },
        "a_not_c_summary": {
            "definition": "historical P2P_ONLY nodes that are NOT per-repetition stable on both sides",
            "n_nodes": a_not_c_nodes_total,
            "tasks_affected": [r["task_id"] for r in per_task_out if r["a_not_c_nodes"]],
            "node_ids": sorted(
                n for r in per_task_out for n in r["a_not_c_nodes"]),
        },
        "duplicate_summary": {
            "definition": "same node, same side, same rep, >1 fragment observation",
            "n_observations": dup_total,
            "n_nodes": len({(d["node_id"], d["side"], d["rep"]) for d in dup_records}),
            "n_records_total": len(dup_records),
            "first_50_records": dup_records[:50],
        },
        "conflict_summary": {
            "definition": "same node, same side, same rep, differing outcomes across fragments",
            "n_records": conflict_total,
            "n_records_total": len(conf_records),
            "first_50_records": conf_records[:50],
        },
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "generated_by": "scripts/opws_m19a4_p2p_s_rep_identity_diagnostic.py",
        "per_task": per_task_out,
    }

    out_path = art_dir / OUT_ARTIFACT
    payload = canonical_doc_bytes(doc)
    out_path.write_bytes(payload)

    print(f"WROTE {out_path}")
    print("tasks", totals["tasks"], "| n_nodes", totals["n_nodes"],
          "| A_hist", totals["a_hist_p2p"], "| B_strict", totals["b_strict_p2p"],
          "| C_rep_stable", totals["c_rep_stable"],
          "| B_not_C", totals["b_not_c"], "| C_not_B", totals["c_not_b"],
          "| A_not_C", totals["a_not_c"])
    print("duplicates_within_rep", totals["duplicates_within_rep"],
          "| conflicts_within_rep", totals["conflicts_within_rep"])
    if args.bench:
        print("ELAPSED_S", (datetime.datetime.now(datetime.UTC) - t0).total_seconds())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
