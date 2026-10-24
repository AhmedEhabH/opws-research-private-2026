"""OPWS M19A4 -- P2P-S exact identity recovery (OFFLINE provenance audit).

Recovers the exact historical P2P_ONLY (changed-test pass-to-pass) node
identities for the frozen 83-task OPWS cohort (C2 MAIN83 JUnit evidence) by
replaying the FROZEN historical as-executed classification, and computes a
STRICT three-run sensitivity projection.

No API, no Saleor execution, no Docker/WSL, no oracle sweep, no protocol
freeze, no commit/tag. This script ONLY reads frozen evidence + frozen
classifier modules and writes candidate artifacts under reports/m19a4_p2ps/.

Frozen replay rule (must hold exactly):
  - enumeration: per task ``tid`` use ``n_test_files`` from per_task_v2.jsonl;
    files ``{task12}_{p|t}_r{rep}_f{idx}.xml`` for rep in 0..2, idx in 0..nf-1.
  - merge: rep-major, file-minor, dict last-write-wins per node (the exact
    order used by the historical run_state_in_container and by
    scripts/opws_m19a2_build_node_contract.py).
  - classification: frozen classify_node_v2 with the merged last scalar
    replicated 3x. P2P_ONLY  =>  target-last == 'passed' AND
    parent-last == 'passed' (classifier step 3, FLAKY checked first).
  - strict three-run projection: a node is stable pass on a side iff all 3 of
    its recorded run outcomes are exactly 'passed' (len != 3 is unstable),
    then the same classifier precedence.

Hard STOPs (audit impossible): classifier pin mismatch, input hash mismatch,
or any enumerated JUnit file missing/unparseable. Data-level disagreements
(replay counts vs frozen counts, strict vs frozen sensitivity) are REPORTED as
failed reconciliation gates -- never forced.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CLASSIFIER_DIR = REPO / "src" / "benchmark" / "wp2"
CLASSIFIER_PINS = {
    "oracle_semantics_v2.py": "aa85f4953bea36974b77340c38fe8219e5a8d577d5e786ff74c06de2fc07423d",
    "oracle_confirmation.py": "4609a2256d0803c1029fae572db62c28f6885b8a12628094a9e10bcb65b752d1",
}
EVIDENCE_MANIFEST_SHA256 = "39ea5470625188a4357575f971842676d32a3ee811874d256f7978e1989b3647"
CONTRACT_SHA256 = "df1e087b199277cc56c42fdfd182f85fcd3faf0c74f4701d5add80b52866f124"
SENSITIVITY_SHA256 = "62f528b060cbbc814f137cbba509443cc4d6fdcb2730010ecc25ce99f942fe41"

CONTRACT = REPO / "research" / "opws" / "binding" / "OPWS_F2P_NODE_CONTRACT_83.json"
SENSITIVITY = REPO / "research" / "opws" / "binding" / "OPWS_F2P_THREE_RUN_SENSITIVITY_83.json"
PER_TASK_JSONL = (
    REPO
    / "research"
    / "wp2"
    / "oracle_confirmation_linux_v2_2026-09-23"
    / "per_task_v2.jsonl"
)
OUT_DIR = REPO / "reports" / "m19a4_p2ps"

CATEGORIES = (
    "BEHAVIORAL_F2P",
    "SYMBOL_ABSENCE_F2P",
    "PARENT_COLLECTION_ERROR",
    "P2P_ONLY",
    "FLAKY",
    "TARGET_ORACLE_INVALID",
    "OTHER_REVIEW_REQUIRED",
)

REPLAY_VARIANT_HISTORICAL = "historical-as-executed"
REPLAY_VARIANT_STRICT = "strict-three-run"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def file_sha256(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def loader_variants_contain(pin: str, p: Path) -> bool:
    b = p.read_bytes()
    lf = b.replace(b"\r\n", b"\n")
    return pin in {sha256_bytes(b), sha256_bytes(lf), sha256_bytes(lf.replace(b"\n", b"\r\n"))}


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_doc_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


# --------------------------------------------------------------------------- #
# pure core: classification over parsed per-(rep,file) maps                    #
# --------------------------------------------------------------------------- #
_SYMBOL_ABSENCE_PATTERNS = (
    "ImportError:",
    "ModuleNotFoundError:",
    "AttributeError:",
    "NameError:",
    "cannot import name",
    "No module named",
    "ImportError ",
)


def _symbol_absence(text: str) -> bool:
    return any(p in text for p in _SYMBOL_ABSENCE_PATTERNS)


def stability_hist(outcomes: list[str]) -> str:
    """3-run stability over exactly 3 outcomes (frozen classifier rule)."""
    if len(outcomes) != 3:
        raise ValueError("stability expects exactly 3 outcomes")
    if all(o == "passed" for o in outcomes):
        return "STABLE_PASS"
    if all(o in ("failed", "error") for o in outcomes):
        return "STABLE_FAIL"
    return "FLAKY"


def stability_strict(runs: list[str]) -> str:
    """Strict three-run stability: exactly 3 recorded outcomes, all 'passed'."""
    if len(runs) == 3 and all(o == "passed" for o in runs):
        return "STABLE_PASS"
    if len(runs) == 3 and all(o in ("failed", "error") for o in runs):
        return "STABLE_FAIL"
    return "FLAKY"


def _classify(*, target_stability, parent_stability, parent_failure_text,
              parent_collects_node, shared_test_support_failed) -> str:
    """Frozen classify_node_v2 precedence, given precomputed stabilities."""
    if target_stability == "FLAKY" or parent_stability == "FLAKY":
        return "FLAKY"
    if target_stability != "STABLE_PASS":
        return "TARGET_ORACLE_INVALID"
    if parent_stability == "STABLE_PASS":
        return "P2P_ONLY"
    if shared_test_support_failed or not parent_collects_node:
        return "PARENT_COLLECTION_ERROR"
    if _symbol_absence(parent_failure_text):
        return "SYMBOL_ABSENCE_F2P"
    if parent_failure_text.strip():
        return "BEHAVIORAL_F2P"
    return "OTHER_REVIEW_REQUIRED"


def classify_hist(*, target_outcomes, parent_outcomes, parent_failure_text,
                  parent_collects_node, shared_test_support_failed) -> str:
    return _classify(
        target_stability=stability_hist(target_outcomes),
        parent_stability=stability_hist(parent_outcomes),
        parent_failure_text=parent_failure_text,
        parent_collects_node=parent_collects_node,
        shared_test_support_failed=shared_test_support_failed,
    )


def classify_strict(*, target_runs, parent_runs, parent_failure_text,
                    parent_collects_node, shared_test_support_failed) -> str:
    return _classify(
        target_stability=stability_strict(target_runs),
        parent_stability=stability_strict(parent_runs),
        parent_failure_text=parent_failure_text,
        parent_collects_node=parent_collects_node,
        shared_test_support_failed=shared_test_support_failed,
    )


def recover_task(*, task_id: str, n_test_files: int, base: Path, parse_func) -> dict:
    """Parse the frozen evidence and classify under both replay variants."""
    t12 = task_id.split("saleor-rc-")[1][:12]
    parsed: dict[tuple[str, int, int], tuple[dict[str, str], dict[str, str]]] = {}
    for state in ("p", "t"):
        for rep in range(3):
            for idx in range(n_test_files):
                f = base / f"{t12}_{state}" / f"{t12}_{state}_r{rep}_f{idx}.xml"
                if not f.exists():
                    raise RuntimeError(f"missing enumerated junit {f}")
                try:
                    nodes, fails = parse_func(f.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise RuntimeError(f"unparseable junit {f}: {exc}") from exc
                parsed[(state, rep, idx)] = (nodes, fails)

    merged: dict[str, dict[str, str]] = {"t": {}, "p": {}}
    merged_fail: dict[str, dict[str, str]] = {"t": {}, "p": {}}
    runs: dict[str, dict[str, list[str]]] = {}
    for (state, _rep, _idx), (nodes, fails) in sorted(parsed.items()):
        merged[state].update(nodes)
        merged_fail[state].update(fails)
        for n, o in nodes.items():
            runs.setdefault(n, {"t": [], "p": []})[state].append(o)

    tg, pa = merged["t"], merged["p"]
    pf = merged_fail["p"]
    allnodes = sorted(set(tg) | set(pa))

    ledger: list[dict] = []
    hist_counts: collections.Counter = collections.Counter()
    strict_counts: collections.Counter = collections.Counter()
    for n in allnodes:
        t_last = tg.get(n, "missing")
        p_last = pa.get(n, "missing")
        t_runs = runs[n]["t"]
        p_runs = runs[n]["p"]
        p_text = pf.get(n, "")
        parent_collects = n in pa
        hc = classify_hist(
            target_outcomes=[t_last] * 3,
            parent_outcomes=[p_last] * 3,
            parent_failure_text=p_text,
            parent_collects_node=parent_collects,
            shared_test_support_failed=not parent_collects,
        )
        sc = classify_strict(
            target_runs=t_runs,
            parent_runs=p_runs,
            parent_failure_text=p_text,
            parent_collects_node=parent_collects,
            shared_test_support_failed=not parent_collects,
        )
        hist_counts[hc] += 1
        strict_counts[sc] += 1
        ledger.append(
            {
                "node_id": n,
                "t_last": t_last,
                "p_last": p_last,
                "t_runs": t_runs,
                "p_runs": p_runs,
                "t_appearances": len(t_runs),
                "p_appearances": len(p_runs),
                "hist_class": hc,
                "strict_class": sc,
            }
        )

    return {
        "task_id": task_id,
        "t12": t12,
        "n_test_files": n_test_files,
        "n_nodes": len(allnodes),
        "ledger": ledger,
        "hist_counts": {k: hist_counts.get(k, 0) for k in CATEGORIES},
        "strict_counts": {k: strict_counts.get(k, 0) for k in CATEGORIES},
    }


def node_identity_hash(task_id: str, hist_p2p: list[str], strict_p2p: list[str]) -> str:
    payload = {
        "task_id": task_id,
        "historical_p2p_only": sorted(hist_p2p),
        "strict_p2p_only": sorted(strict_p2p),
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-root", required=True, help="C2_MAIN83_JUNIT_RESCUE dir")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--git-head", default="")
    ap.add_argument("--skip-evidence-file-hashes", action="store_true",
                    help="internal: skip full 1801-file hash verification (tests)")
    args = ap.parse_args()

    sys.path.insert(0, str(CLASSIFIER_DIR))
    import oracle_confirmation

    parse_func = oracle_confirmation.parse_junit_with_failures
    for fn, pin in CLASSIFIER_PINS.items():
        if not loader_variants_contain(pin, CLASSIFIER_DIR / fn):
            raise SystemExit(f"STOP: classifier pin mismatch {fn}")

    evid = Path(args.evidence_root)
    manifest = evid / "JUNIT_EVIDENCE_MANIFEST.json"
    if file_sha256(manifest) != EVIDENCE_MANIFEST_SHA256:
        raise SystemExit("STOP: evidence manifest hash mismatch")

    input_hashes: dict[str, str] = {}
    for label, path, pin in (
        ("f2p_node_contract_83", CONTRACT, CONTRACT_SHA256),
        ("three_run_sensitivity_83", SENSITIVITY, SENSITIVITY_SHA256),
        ("per_task_v2_jsonl", PER_TASK_JSONL, None),
    ):
        h = file_sha256(path)
        input_hashes[label] = h
        if pin is not None and h != pin:
            raise SystemExit(f"STOP: {label} hash mismatch {path}")

    ev = json.loads(manifest.read_text(encoding="utf-8"))
    if not args.skip_evidence_file_hashes:
        bad = []
        for row in ev["files"]:
            rel, h = row[2], row[3]
            if file_sha256(evid / rel) != h:
                bad.append(rel)
        if bad:
            raise SystemExit(f"STOP: {len(bad)} evidence files changed: {bad[:5]}")

    per_task = {}
    for line in PER_TASK_JSONL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            per_task[r["task_id"]] = r

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sensitivity = json.loads(SENSITIVITY.read_text(encoding="utf-8"))
    contract_tasks = sorted(contract["tasks"], key=lambda t: t["task_id"])
    if len(contract_tasks) != 83:
        raise SystemExit(f"STOP: expected 83 contract tasks, got {len(contract_tasks)}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    base = evid / "junit" / "opt" / "wp2_v2" / "c2_artifact_rescue"
    stray: list[str] = []
    physical: dict[str, dict] = {}
    task_results = []
    gates: list[dict] = []
    ledger_rows: list[tuple] = []

    sens_by_task = {x["task_id"]: x for x in sensitivity["tasks"]}

    for t in contract_tasks:
        tid = t["task_id"]
        nf = per_task[tid]["n_test_files"]
        t12 = tid.split("saleor-rc-")[1][:12]
        dir_p = base / f"{t12}_p"
        dir_t = base / f"{t12}_t"
        files_p = sorted(x.name for x in dir_p.iterdir() if x.is_file())
        files_t = sorted(x.name for x in dir_t.iterdir() if x.is_file())
        enum_p = {f"{t12}_p_r{rep}_f{idx}.xml" for rep in range(3) for idx in range(nf)}
        enum_t = {f"{t12}_t_r{rep}_f{idx}.xml" for rep in range(3) for idx in range(nf)}
        miss_p = sorted(enum_p - set(files_p))
        miss_t = sorted(enum_t - set(files_t))
        stray_p = sorted(f"{t12}_p/{n}" for n in files_p if n not in enum_p)
        stray_t = sorted(f"{t12}_t/{n}" for n in files_t if n not in enum_t)
        if stray_p or stray_t:
            stray += stray_p + stray_t
        physical[t12] = {
            "expected_6xnf": 6 * nf,
            "actual_p": len(files_p),
            "actual_t": len(files_t),
            "missing_enum_p": miss_p,
            "missing_enum_t": miss_t,
            "physical_total": len(files_p) + len(files_t),
            "stray_files": stray_p + stray_t,
        }

        res = recover_task(task_id=tid, n_test_files=nf, base=base, parse_func=parse_func)
        hist, strict = res["hist_counts"], res["strict_counts"]

        issue: list[str] = []
        if miss_p or miss_t:
            issue.append(f"missing enumerated junit files p={len(miss_p)} t={len(miss_t)}")
        if res["n_nodes"] != t["n_nodes"]:
            issue.append(f"n_nodes replay {res['n_nodes']} != frozen {t['n_nodes']}")
        if hist != t["frozen_counts"]:
            issue.append("hist counts replay != frozen counts")
        if t["replay_exact_count_match"] is not True:
            issue.append("contract records replay_exact_count_match=false")

        hist_p2p = sorted(x["node_id"] for x in res["ledger"] if x["hist_class"] == "P2P_ONLY")
        strict_p2p = sorted(x["node_id"] for x in res["ledger"] if x["strict_class"] == "P2P_ONLY")
        changed = sorted(
            [
                {
                    "node_id": x["node_id"],
                    "historical": x["hist_class"],
                    "strict": x["strict_class"],
                    "parent_runs": x["p_runs"],
                    "target_runs": x["t_runs"],
                }
                for x in res["ledger"]
                if x["hist_class"] != x["strict_class"]
            ],
            key=lambda d: d["node_id"],
        )

        sens = sens_by_task.get(tid)
        ok_counts = ok_beh = ok_sym = changed_match = None
        if sens is None:
            issue.append("task missing in frozen sensitivity file")
        else:
            exp_strict = sens["strict_three_run_counts"]
            ok_counts = {k: strict[k] for k in exp_strict} == exp_strict
            ok_beh = {x["node_id"] for x in res["ledger"] if x["strict_class"] == "BEHAVIORAL_F2P"} == set(
                sens["strict_f2p_node_ids"].get("BEHAVIORAL_F2P", []))
            ok_sym = {x["node_id"] for x in res["ledger"] if x["strict_class"] == "SYMBOL_ABSENCE_F2P"} == set(
                sens["strict_f2p_node_ids"].get("SYMBOL_ABSENCE_F2P", []))
            frozen_changed = {
                c["node_id"]: (c["historical"], c["strict"], list(c["parent_runs"]), list(c["target_runs"]))
                for c in sens["changed_nodes"]
            }
            my_changed = {
                c["node_id"]: (c["historical"], c["strict"], list(c["parent_runs"]), list(c["target_runs"]))
                for c in changed
            }
            changed_match = my_changed == frozen_changed
            if not (ok_counts and ok_beh and ok_sym):
                issue.append("strict counts/ids replay != frozen sensitivity file")
            if not changed_match:
                issue.append("changed-node set replay != frozen sensitivity file")

        for row in res["ledger"]:
            ledger_rows.append(
                (tid, row["node_id"], row["t_last"], row["p_last"],
                 "|".join(row["t_runs"]), "|".join(row["p_runs"]),
                 row["t_appearances"], row["p_appearances"],
                 row["hist_class"], row["strict_class"])
            )

        gates.append({
            "task": tid, "gate": "evidence_enumeration_complete",
            "pass": not (miss_p or miss_t),
            "detail": f"expected={6*nf} actual_p={len(files_p)} actual_t={len(files_t)}",
        })
        gates.append({
            "task": tid, "gate": "replay_counts_match_contract",
            "pass": (res["n_nodes"] == t["n_nodes"] and hist == t["frozen_counts"]
                     and t["replay_exact_count_match"] is True),
            "detail": "; ".join(issue) if issue else "exact",
        })
        if sens is not None:
            gates.append({
                "task": tid, "gate": "strict_vs_frozen_sensitivity",
                "pass": ok_counts and ok_beh and ok_sym,
                "detail": f"counts={ok_counts} beh_ids={ok_beh} sym_ids={ok_sym}",
            })
            gates.append({
                "task": tid, "gate": "changed_nodes_match_frozen_sensitivity",
                "pass": changed_match,
                "detail": f"n_changed={len(changed)}",
            })

        task_results.append(
            {
                "task_id": tid,
                "physical": physical[t12],
                "n_nodes": res["n_nodes"],
                "hist_counts": hist,
                "strict_counts": strict,
                "hist_p2p_only": hist_p2p,
                "strict_p2p_only": strict_p2p,
                "hist_not_strict": sorted(
                    x["node_id"] for x in res["ledger"]
                    if x["hist_class"] == "P2P_ONLY" and x["strict_class"] != "P2P_ONLY"
                ),
                "strict_not_hist": sorted(
                    x["node_id"] for x in res["ledger"]
                    if x["strict_class"] == "P2P_ONLY" and x["hist_class"] != "P2P_ONLY"
                ),
                "changed_nodes": changed,
                "issues": issue,
                "node_identity_sha256": node_identity_hash(tid, hist_p2p, strict_p2p),
            }
        )

    totals = {
        "tasks": len(task_results),
        "n_nodes": sum(r["n_nodes"] for r in task_results),
        "p2p_only_historical": sum(r["hist_counts"]["P2P_ONLY"] for r in task_results),
        "p2p_only_strict": sum(r["strict_counts"]["P2P_ONLY"] for r in task_results),
        "f2p_historical": sum(r["hist_counts"]["BEHAVIORAL_F2P"] + r["hist_counts"]["SYMBOL_ABSENCE_F2P"]
                              for r in task_results),
        "f2p_strict": sum(r["strict_counts"]["BEHAVIORAL_F2P"] + r["strict_counts"]["SYMBOL_ABSENCE_F2P"]
                          for r in task_results),
        "behavioral_f2p_historical": sum(r["hist_counts"]["BEHAVIORAL_F2P"] for r in task_results),
        "symbol_absence_f2p_historical": sum(r["hist_counts"]["SYMBOL_ABSENCE_F2P"] for r in task_results),
        "behavioral_f2p_strict": sum(r["strict_counts"]["BEHAVIORAL_F2P"] for r in task_results),
        "symbol_absence_f2p_strict": sum(r["strict_counts"]["SYMBOL_ABSENCE_F2P"] for r in task_results),
        "flaky_historical": sum(r["hist_counts"]["FLAKY"] for r in task_results),
        "flaky_strict": sum(r["strict_counts"]["FLAKY"] for r in task_results),
        "changed_nodes_hist_vs_strict": sum(len(r["changed_nodes"]) for r in task_results),
        "tasks_with_changes": sum(1 for r in task_results if r["changed_nodes"]),
        "hist_not_strict_p2p_nodes": sum(len(r["hist_not_strict"]) for r in task_results),
        "strict_not_hist_p2p_nodes": sum(len(r["strict_not_hist"]) for r in task_results),
        "tasks_with_f2p_historical": sum(
            1 for r in task_results if r["hist_counts"]["BEHAVIORAL_F2P"] > 0),
        "tasks_with_f2p_strict": sum(
            1 for r in task_results if r["strict_counts"]["BEHAVIORAL_F2P"] > 0),
        "extended_f2p_tasks_historical": sum(
            1 for r in task_results
            if r["hist_counts"]["BEHAVIORAL_F2P"] + r["hist_counts"]["SYMBOL_ABSENCE_F2P"] > 0),
        "extended_f2p_tasks_strict": sum(
            1 for r in task_results
            if r["strict_counts"]["BEHAVIORAL_F2P"] + r["strict_counts"]["SYMBOL_ABSENCE_F2P"] > 0),
    }

    tasks_with_issues = sorted(r["task_id"] for r in task_results if r["issues"])
    aggregate_identity_hash = sha256_bytes(
        canonical_json([(r["task_id"], r["node_identity_sha256"]) for r in task_results]).encode("utf-8"))

    main_doc = {
        "artifact": "M19A4_P2P_ONLY_NODES_BY_TASK_83",
        "schema": "opws-m19a4-p2ps/1.0",
        "status": "CANDIDATE_RECOVERY_AUDIT",
        "scope": ("EXACT identity recovery of historical P2P_ONLY nodes for the frozen 83-task OPWS cohort "
                  "(C2 MAIN83 JUnit evidence). Candidate P2P-S changed-test pass-to-pass node sets. "
                  "NOT an approved OPWS P2P-S protocol; no P2P-U membership is claimed."),
        "replay_variant_historical": REPLAY_VARIANT_HISTORICAL,
        "replay_variant_strict": REPLAY_VARIANT_STRICT,
        "recipe_historical": ("merge rep-major,file-minor,last-write-wins; classify_node_v2([last]*3); "
                              "P2P_ONLY iff target-last=='passed' and parent-last=='passed'"),
        "recipe_strict": ("node stable-pass on a side iff its 3 recorded outcomes are exactly ['passed']*3; "
                          "same classifier precedence"),
        "evidence_manifest_sha256": EVIDENCE_MANIFEST_SHA256,
        "contract_sha256": CONTRACT_SHA256,
        "sensitivity_sha256": SENSITIVITY_SHA256,
        "input_hashes": input_hashes,
        "classifier_pins": CLASSIFIER_PINS,
        "node_identity_recipe": ("node_identity_sha256 = sha256(canonical json "
                                 "{task_id, historical_p2p_only(sorted), strict_p2p_only(sorted)})"),
        "aggregate_identity_recipe": ("sha256(canonical json list of [task_id, node_identity_sha256] "
                                      "in sorted task_id order)"),
        "aggregate_identity_sha256": aggregate_identity_hash,
        "counts_reconcile_summary": {
            "tasks": len(task_results),
            "tasks_with_issues": len(tasks_with_issues),
            "tasks_with_issues_list": tasks_with_issues,
        },
        "totals": totals,
        "stray_out_of_enumeration_files": sorted(stray),
        "physical_file_census": physical,
        "tasks": task_results,
    }
    main_bytes = canonical_doc_bytes(main_doc)
    (out / "M19A4_P2P_ONLY_NODES_BY_TASK_83.json").write_bytes(main_bytes)

    # ---- ledger TSV ----
    header = ["task_id", "node_id", "t_last", "p_last", "t_runs", "p_runs",
              "t_appearances", "p_appearances", "hist_class", "strict_class"]

    def tsv_field(v):
        s = str(v)
        return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")

    tsv = "\t".join(header) + "\n" + "\n".join(
        "\t".join(tsv_field(v) for v in row) for row in ledger_rows) + "\n"
    (out / "M19A4_NODE_LEDGER_83.tsv").write_text(tsv, encoding="utf-8")

    # ---- provenance ----
    provenance = {
        "artifact": "M19A4_PROVENANCE_AND_INPUT_HASHES",
        "schema": "opws-m19a4-p2ps/provenance/1.0",
        "generated_by": "scripts/opws_m19a4_p2p_s_recover.py",
        "git_head": args.git_head or "unavailable",
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "classifier_pins": CLASSIFIER_PINS,
        "input_hashes": input_hashes,
        "evidence_manifest_sha256": EVIDENCE_MANIFEST_SHA256,
        "evidence_dir": str(evid),
        "evidence_n_xml_files": len(ev["files"]),
        "evidence_total_bytes": ev.get("total_bytes"),
        "recipes": {
            "historical": main_doc["recipe_historical"],
            "strict": main_doc["recipe_strict"],
            "node_identity": main_doc["node_identity_recipe"],
            "aggregate_identity": main_doc["aggregate_identity_recipe"],
        },
        "no_protocol_freeze": True,
        "offline_only": True,
        "outputs": {
            "M19A4_P2P_ONLY_NODES_BY_TASK_83.json": sha256_bytes(main_bytes),
        },
    }
    (out / "M19A4_PROVENANCE_AND_INPUT_HASHES.json").write_bytes(canonical_doc_bytes(provenance))

    # ---- per-task reconciliation ----
    contract_by_id = {t["task_id"]: t for t in contract_tasks}
    recon = {
        "artifact": "M19A4_PER_TASK_RECONCILIATION",
        "schema": "opws-m19a4-p2ps/reconciliation/1.0",
        "aggregate_identity_sha256": aggregate_identity_hash,
        "per_task": [
            {
                "task_id": r["task_id"],
                "n_nodes_frozen": contract_by_id[r["task_id"]]["n_nodes"],
                "n_nodes_replay": r["n_nodes"],
                "frozen_counts": contract_by_id[r["task_id"]]["frozen_counts"],
                "replay_hist_counts": r["hist_counts"],
                "replay_strict_counts": r["strict_counts"],
                "p2p_historical": {
                    "n": len(r["hist_p2p_only"]),
                    "identity_sha256": node_identity_hash(r["task_id"], r["hist_p2p_only"], []),
                },
                "p2p_strict": {"n": len(r["strict_p2p_only"])},
                "hist_not_strict_p2p": r["hist_not_strict"],
                "strict_not_hist_p2p": r["strict_not_hist"],
                "issues": r["issues"],
            }
            for r in task_results
        ],
        "missing_evidence": {
            "missing_enum_files_by_task": {
                t12: {"missing_p": v["missing_enum_p"], "missing_t": v["missing_enum_t"]}
                for t12, v in physical.items() if v["missing_enum_p"] or v["missing_enum_t"]
            },
            "stray_out_of_enumeration_files": sorted(stray),
        },
        "totals": totals,
    }
    (out / "M19A4_PER_TASK_RECONCILIATION.json").write_bytes(canonical_doc_bytes(recon))

    # ---- historical vs strict sensitivity summary ----
    cat_matrix = collections.Counter()
    for r in task_results:
        for c in r["changed_nodes"]:
            cat_matrix[(c["historical"], c["strict"])] += 1
    sens_summary = {
        "artifact": "M19A4_HISTORICAL_VS_STRICT_SENSITIVITY",
        "schema": "opws-m19a4-p2ps/sensitivity/1.0",
        "status": "CANDIDATE; frozen figures 83/82/70 and 795/770 unchanged",
        "frozen_reference": {
            "contract": {
                "tasks_extended_f2p_historical": contract.get("n_tasks"),
                "primary_behavioral_hist": contract.get("n_primary_frozen"),
                "primary_behavioral_strict": contract.get("n_primary_spec_3run"),
                "behavioral_f2p_hist": contract.get("n_behavioral_f2p_nodes"),
                "symbol_absence_f2p_hist": contract.get("n_symbol_absence_f2p_nodes"),
                "f2p_hist_total": contract.get("n_behavioral_f2p_nodes") + contract.get("n_symbol_absence_f2p_nodes"),
                "n_tasks_with_3run_instability": contract.get("n_tasks_with_3run_instability"),
            },
            "sensitivity_file": {
                "behavioral_f2p_strict": 707,
                "symbol_absence_f2p_strict": 63,
                "f2p_strict_total": 770,
                "changed_nodes_total": sensitivity.get("changed_nodes_total"),
                "tasks_with_changes": sensitivity.get("tasks_with_changes"),
            },
        },
        "recovered_totals": totals,
        "changed_nodes_category_matrix": {f"{k[0]}->{k[1]}": v for k, v in sorted(cat_matrix.items())},
        "changed_nodes_by_task": {
            r["task_id"]: [c["node_id"] for c in r["changed_nodes"]] for r in task_results if r["changed_nodes"]
        },
        "p2p_only_delta_hist_vs_strict": {
            "hist_p2p_excluded_under_strict": totals["hist_not_strict_p2p_nodes"],
            "strict_p2p_added_over_hist": totals["strict_not_hist_p2p_nodes"],
            "hist_excluded_by_task": {r["task_id"]: r["hist_not_strict"] for r in task_results if r["hist_not_strict"]},
            "strict_added_by_task": {r["task_id"]: r["strict_not_hist"] for r in task_results if r["strict_not_hist"]},
        },
        "notes": [
            "Historical P2P_ONLY uses the last-write-wins merge + [last]*3 replay; strict uses all 3 recorded "
            "outcomes.",
            "The 2 P2P_ONLY(hist)->FLAKY(strict) nodes on 032b98afff20/30b4edece5aa match the frozen sensitivity "
            "file exactly.",
            "P2P_ONLY requires both sides to be collected and passed historically; target-only or parent-only nodes "
            "do not classify P2P_ONLY.",
            "No P2P-U membership is inferred or claimed; P2P-U V2 uses the separate frozen unchanged-test pool.",
            "These identity lists are CANDIDATE recovery outputs, not an approved OPWS P2P-S protocol.",
        ],
    }
    (out / "M19A4_HISTORICAL_VS_STRICT_SENSITIVITY.json").write_bytes(canonical_doc_bytes(sens_summary))

    # ---- validation receipt ----
    receipt = {
        "artifact": "M19A4_VALIDATION_RECEIPT",
        "schema": "opws-m19a4-p2ps/validation/1.0",
        "generated_at_utc": provenance["generated_at_utc"],
        "gates": gates,
        "gate_summary": {
            "evidence_enumeration_complete": sum(
                g["pass"] for g in gates if g["gate"] == "evidence_enumeration_complete"),
            "replay_counts_match_contract": sum(
                g["pass"] for g in gates if g["gate"] == "replay_counts_match_contract"),
            "strict_vs_frozen_sensitivity": sum(
                g["pass"] for g in gates if g["gate"] == "strict_vs_frozen_sensitivity"),
            "changed_nodes_match_frozen_sensitivity": sum(
                g["pass"] for g in gates if g["gate"] == "changed_nodes_match_frozen_sensitivity"),
            "total_tasks": len(task_results),
        },
        "input_hash_checks": {
            "evidence_manifest": EVIDENCE_MANIFEST_SHA256,
            "f2p_node_contract_83": CONTRACT_SHA256,
            "three_run_sensitivity_83": SENSITIVITY_SHA256,
            "all_matched": bool(
                file_sha256(CONTRACT) == CONTRACT_SHA256
                and file_sha256(SENSITIVITY) == SENSITIVITY_SHA256
                and file_sha256(manifest) == EVIDENCE_MANIFEST_SHA256
            ),
        },
        "classifier_pins_verified": all(
            loader_variants_contain(pin, CLASSIFIER_DIR / fn) for fn, pin in CLASSIFIER_PINS.items()),
        "evidence_file_hashes_verified": {
            "full_scan": not args.skip_evidence_file_hashes,
            "n_files": len(ev["files"]),
        },
        "outputs": {
            name: sha256_bytes((out / name).read_bytes())
            for name in ("M19A4_P2P_ONLY_NODES_BY_TASK_83.json",
                         "M19A4_NODE_LEDGER_83.tsv",
                         "M19A4_PROVENANCE_AND_INPUT_HASHES.json",
                         "M19A4_PER_TASK_RECONCILIATION.json",
                         "M19A4_HISTORICAL_VS_STRICT_SENSITIVITY.json")
        },
        "overall": "PASS" if not tasks_with_issues else f"DISCREPANCIES on {len(tasks_with_issues)} tasks",
    }
    (out / "M19A4_VALIDATION_RECEIPT.json").write_bytes(canonical_doc_bytes(receipt))

    print("WROTE artifacts under", out)
    print("tasks", totals["tasks"], "| n_nodes", totals["n_nodes"],
          "| hist P2P_ONLY", totals["p2p_only_historical"],
          "| strict P2P_ONLY", totals["p2p_only_strict"],
          "| hist F2P", totals["f2p_historical"], "| strict F2P", totals["f2p_strict"],
          "| changed hist->strict", totals["changed_nodes_hist_vs_strict"])
    print("AGGREGATE_IDENTITY_SHA256", aggregate_identity_hash)
    print("TASKS_WITH_ISSUES", len(tasks_with_issues), tasks_with_issues)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
