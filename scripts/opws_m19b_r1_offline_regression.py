"""OPWS M19B-R1 -- evidence-backed OFFLINE regression (read-only, fails closed).

Replays ONE pilot task's strict F2P / P2P-S identities and per-repetition
stability from the RESCUED C2 JUnit evidence files -- no pytest, no Saleor,
no Docker, no classification submissions, no network.

Replay target default: ``saleor-rc-7e42fc67ce72`` (pilot task, frozen oracle:
BEHAVIORAL_F2P=3, P2P_ONLY=103, TARGET_ORACLE_INVALID=11; 117 nodes total).

Procedure (strict):
  * the 24 rescued raw JUnit files (12 target + 12 parent) must exist under
    the read-only evidence root and EVERY file sha256 must equal the FROZEN
    C2 manifest hash (research/opws/binding/C2_MAIN83_JUNIT_EVIDENCE_MANIFEST.json).
    Any missing/mismatched file => STOP (no node-set relaxation).
  * files are parsed with the FROZEN hash-pinned parser
    (benchmark.wp2.oracle_confirmation.parse_junit_with_failures) exactly like
    the M19A4 recovery, using the frozen per-(rep,file) enumeration.
  * classification uses the FROZEN strict rule (exactly 3 recorded outcomes,
    all 'passed') and the FROZEN per-repetition stability rule (distinct
    r0/r1/r2 present on a side, every observation passed).
  * the replayed strict P2P_ONLY node SET must EQUAL the frozen
    M19A4_P2P_ONLY_NODES_BY_TASK_83 strict_p2p_only list; the replayed
    BEHAVIORAL_F2P node SET must EQUAL the frozen
    OPWS_F2P_THREE_RUN_SENSITIVITY_83 strict_f2p_node_ids BEHAVIORAL_F2P list;
    counts must equal the REP_IDENTITY_DIAGNOSTIC per-task counts.
  * TARGET_ORACLE_INVALID nodes (previously invalid target nodes) are listed
    separately and must NOT be labeled F2P or P2P-S (set disjointness).

Outputs: deterministic attestation JSON + markdown report in a NEW directory.
Exit code 0 only when every equality holds and no evidence file drifted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(REPO / "src" / "benchmark" / "wp2"))

import oracle_confirmation  # noqa: E402  # frozen parser, hash-pinned below

from scripts.opws_m19a4_p2p_s_recover import (  # noqa: E402  # frozen logic
    CATEGORIES,
    CLASSIFIER_PINS,
    EVIDENCE_MANIFEST_SHA256,
    loader_variants_contain,
    recover_task,
)
from scripts.opws_m19a4_p2p_s_rep_identity_diagnostic import (  # noqa: E402
    per_rep_stable,
    per_task_rep_diagnostics,
)

DEFAULT_TASK = "saleor-rc-7e42fc67ce72"
DEFAULT_EVIDENCE = Path(r"D:\WP2\evidence\C2_MAIN83_JUNIT_RESCUE_2026-10-23")
FROZEN_MANIFEST = REPO / "research" / "opws" / "binding" / "C2_MAIN83_JUNIT_EVIDENCE_MANIFEST.json"
FROZEN_BY_TASK = REPO / "reports" / "m19a4_p2ps" / "M19A4_P2P_ONLY_NODES_BY_TASK_83.json"
FROZEN_SENSITIVITY = REPO / "research" / "opws" / "binding" / "OPWS_F2P_THREE_RUN_SENSITIVITY_83.json"
FROZEN_REPDIAG = REPO / "reports" / "m19a4_p2ps" / "M19A4_REP_IDENTITY_DIAGNOSTIC.json"
REPS = (0, 1, 2)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(p.read_bytes())


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def verify_classifier_pins() -> None:
    for name, pin in CLASSIFIER_PINS.items():
        src = REPO / "src" / "benchmark" / "wp2" / name
        if not loader_variants_contain(pin, src):
            raise SystemExit(f"FROZEN CLASSIFIER PIN BROKEN: {name} {pin}")


def frozen_manifest_entries(manifest: dict[str, Any], task_id: str) -> list[list[Any]]:
    t12 = task_id.split("saleor-rc-", 1)[1][:12]
    entries = [e for e in manifest["files"] if e[0].startswith(t12 + "_")]
    if len(entries) != 24:
        raise SystemExit(
            f"expected 24 frozen manifest entries for {task_id}, got {len(entries)}"
        )
    return entries


def verify_evidence_files(entries: list[list[Any]], evidence_root: Path) -> None:
    """Every rescued raw JUnit file must exist and match the FROZEN hash."""
    checked = 0
    for _name, _container, rel, expected_sha, _size in entries:
        p = evidence_root / rel
        if not p.is_file():
            raise SystemExit(f"EVIDENCE FILE MISSING: {p}")
        got = sha256_file(p)
        if got != expected_sha:
            raise SystemExit(
                f"EVIDENCE FILE HASH MISMATCH {rel}: {got} != frozen {expected_sha}"
            )
        checked += 1
        print(f"  [ok] {rel} sha256={got[:16]}...")
    print(f"  verified {checked}/24 rescued raw JUnit sha256 == frozen manifest")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task-id", default=DEFAULT_TASK)
    ap.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE)
    ap.add_argument("--out", type=Path, default=Path(r"D:\WP2\audit_results\M19B_R1_RECEIPT_2026-10-24"))
    ap.add_argument("--force", action="store_true", help="overwrite existing attestation (default: refuse)")
    args = ap.parse_args(argv)
    task_id = args.task_id
    if not task_id.startswith("saleor-rc-") or len(task_id.split("-")[-1]) != 12:
        raise SystemExit(f"invalid --task-id {task_id!r}")

    verify_classifier_pins()

    manifest = load_json(FROZEN_MANIFEST)
    if manifest.get("n_files") != 1801:
        raise SystemExit(f"unexpected frozen manifest n_files {manifest.get('n_files')}")
    entries = frozen_manifest_entries(manifest, task_id)
    verify_evidence_files(entries, args.evidence_root)

    # n_test_files from the frozen enumeration (max idx+1 across both states).
    # Manifest entries are [task_state_prefix, container_path, rel_path, sha, size];
    # the container_path basename carries the {tid}_{state}_r{rep}_f{idx}.xml name.
    idxs = sorted(
        {int(Path(str(e[1])).name.rsplit("_f", 1)[1].removesuffix(".xml")) for e in entries}
    )
    n_test_files = max(idxs) + 1
    expected = 2 * 3 * n_test_files
    if expected != 24:
        raise SystemExit(f"manifest enumeration inconsistent: {expected} != 24 files")
    print(f"  n_test_files={n_test_files} (2 states x 3 reps x {n_test_files} files = 24)")

    base = args.evidence_root / "junit" / "opt" / "wp2_v2" / "c2_artifact_rescue"
    rec = recover_task(
        task_id=task_id, n_test_files=n_test_files, base=base,
        parse_func=oracle_confirmation.parse_junit_with_failures,
    )
    ledger = {row["node_id"]: row for row in rec["ledger"]}

    # Per-repetition stability (definition C) from the SAME parsed files.
    parsed = {}
    t12 = task_id.split("saleor-rc-")[1][:12]
    for state in ("p", "t"):
        for rep in REPS:
            for idx in range(n_test_files):
                f = base / f"{t12}_{state}" / f"{t12}_{state}_r{rep}_f{idx}.xml"
                nodes, fails = oracle_confirmation.parse_junit_with_failures(
                    f.read_text(encoding="utf-8")
                )
                parsed[(state, rep, idx)] = (nodes, fails)
    per_node_reps = per_task_rep_diagnostics(parsed)

    strict_p2p = {n for n, row in ledger.items() if row["strict_class"] == "P2P_ONLY"}
    strict_f2p = {n for n, row in ledger.items() if row["strict_class"] == "BEHAVIORAL_F2P"}
    invalid = {n for n, row in ledger.items() if row["strict_class"] == "TARGET_ORACLE_INVALID"}
    rep_stable = {
        n
        for n, reps in per_node_reps.items()
        if per_rep_stable(reps["t"]) and per_rep_stable(reps["p"])
    }

    # ---- frozen oracle comparisons ----------------------------------- #
    by_task = {t["task_id"]: t for t in load_json(FROZEN_BY_TASK)["tasks"]}
    if task_id not in by_task:
        raise SystemExit(f"{task_id} missing from frozen M19A4 by-task artifact")
    frozen_task = by_task[task_id]
    frozen_strict_p2p_set = set(frozen_task["strict_p2p_only"])
    frozen_strict_counts = frozen_task["strict_counts"]

    sensitivity = {t["task_id"]: t for t in load_json(FROZEN_SENSITIVITY)["tasks"]}
    if task_id not in sensitivity:
        raise SystemExit(f"{task_id} missing from frozen F2P sensitivity artifact")
    frozen_f2p_set = set(sensitivity[task_id]["strict_f2p_node_ids"]["BEHAVIORAL_F2P"])
    frozen_sens_counts = sensitivity[task_id]["strict_three_run_counts"]

    repdiag = {
        t["task_id"]: t for t in load_json(FROZEN_REPDIAG)["per_task"]
    }
    if task_id not in repdiag:
        raise SystemExit(f"{task_id} missing from frozen REP_IDENTITY_DIAGNOSTIC")
    frozen_rd_counts = repdiag[task_id]["counts"]

    replayed_counts = {k: rec["strict_counts"].get(k, 0) for k in CATEGORIES}

    failures: list[str] = []
    if strict_p2p != frozen_strict_p2p_set:
        failures.append(
            "P2P-S node SET unequal: "
            f"observed-only={sorted(strict_p2p - frozen_strict_p2p_set)[:5]} "
            f"frozen-only={sorted(frozen_strict_p2p_set - strict_p2p)[:5]}"
        )
    if strict_f2p != frozen_f2p_set:
        failures.append(
            "F2P node SET unequal: "
            f"observed-only={sorted(strict_f2p - frozen_f2p_set)[:5]} "
            f"frozen-only={sorted(frozen_f2p_set - strict_f2p)[:5]}"
        )
    if rep_stable != strict_p2p:
        failures.append(
            "per-rep stable set differs from strict P2P_ONLY set: "
            f"{len(rep_stable)} != {len(strict_p2p)}"
        )
    if replayed_counts != frozen_strict_counts or replayed_counts != frozen_sens_counts:
        failures.append(
            f"strict counts drift: replayed={replayed_counts} "
            f"by_task={frozen_strict_counts} sensitivity={frozen_sens_counts}"
        )
    if frozen_rd_counts.get("B_strict_p2p") != len(strict_p2p):
        failures.append(
            f"diagnostic B_strict_p2p {frozen_rd_counts.get('B_strict_p2p')} "
            f"!= replayed {len(strict_p2p)}"
        )
    # previously invalid target nodes must not be mislabeled as F2P or P2P-S
    overlap = invalid & (strict_f2p | strict_p2p)
    if overlap:
        failures.append(f"invalid target nodes wrongly labeled: {sorted(overlap)[:5]}")
    if len(invalid) != 11:
        failures.append(f"expected 11 TARGET_ORACLE_INVALID, got {len(invalid)}")

    attest = {
        "schema": "opws-m19b-r1-offline-regression/1.0",
        "task_id": task_id,
        "t12": t12,
        "verdict": "FAIL" if failures else "PASS",
        "failures": failures,
        "counts_replayed": replayed_counts,
        "counts_frozen_by_task": frozen_strict_counts,
        "counts_frozen_sensitivity": frozen_sens_counts,
        "counts_frozen_repdiag": {
            k: frozen_rd_counts.get(k) for k in ("B_strict_p2p", "C_rep_stable_both_sides")
        },
        "n_nodes": rec["n_nodes"],
        "sets": {
            "strict_p2p_sha256": sha256_bytes(canonical_bytes(sorted(strict_p2p))),
            "strict_f2p_sha256": sha256_bytes(canonical_bytes(sorted(strict_f2p))),
            "target_oracle_invalid_sha256": sha256_bytes(canonical_bytes(sorted(invalid))),
            "rep_stable_sha256": sha256_bytes(canonical_bytes(sorted(rep_stable))),
        },
        "n_test_files": n_test_files,
        "evidence_manifest_sha256": EVIDENCE_MANIFEST_SHA256,
        "classifier_pins": CLASSIFIER_PINS,
        "inputs_sha256": {
            "by_task_artifact": sha256_file(FROZEN_BY_TASK),
            "sensitivity_artifact": sha256_file(FROZEN_SENSITIVITY),
            "repdiag_artifact": sha256_file(FROZEN_REPDIAG),
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    out_json = args.out / f"OFFLINE_REGRESSION_{t12}.json"
    if out_json.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {out_json} (use --force)")
    out_json.write_text(
        json.dumps(attest, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out_md = args.out / f"OFFLINE_REGRESSION_{t12}.md"
    lines = [
        f"# M19B-R1 offline regression — {task_id}",
        "",
        f"- Verdict: **{attest['verdict']}**",
        f"- Replayed strict counts: {json.dumps(replayed_counts)}",
        f"- Frozen by-task strict counts: {json.dumps(frozen_strict_counts)}",
        f"- Frozen sensitivity strict counts: {json.dumps(frozen_sens_counts)}",
        f"- Replayed node sets: {len(strict_p2p)} P2P_ONLY / "
        f"{len(strict_f2p)} BEHAVIORAL_F2P / "
        f"{len(invalid)} TARGET_ORACLE_INVALID",
        f"- Per-rep stable set size: {len(rep_stable)} (must equal P2P_ONLY)",
        f"- P2P-S set sha256: `{attest['sets']['strict_p2p_sha256']}`",
        f"- F2P set sha256: `{attest['sets']['strict_f2p_sha256']}`",
        f"- `{len(invalid)}` previously invalid target nodes are EXCLUDED",
        "",
        "NO behavioral claim is made: this replay only re-verifies frozen node",
        "identities against the rescued evidence files.",
        "```json",
        json.dumps(attest, indent=1, sort_keys=True, ensure_ascii=False),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nOFFLINE_REGRESSION_{t12} verdict={attest['verdict']}")
    if failures:
        for f in failures:
            print("  FAIL:", f)
        return 1
    print("HASHES", json.dumps(attest["sets"], sort_keys=True))
    print(f"WROTE {out_json}")
    print(f"WROTE {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
