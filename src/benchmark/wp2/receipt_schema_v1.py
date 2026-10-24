"""OPWS M19B-R1 -- RECEIPT_SCHEMA_v1 and canonical real-run identity (additive).

Pure, offline, stdlib-only definitions for the fail-closed real-run receipt
seam.  Nothing here executes Saleor, Docker, WSL or a model; no network; no
writes.  All functions are deterministic given their inputs.

Three layers:

1. Canonical hashing
   ``sha256_canonical`` serializes any JSON-compatible object with fixed
   LF/UTF-8/no-BOM bytes and ``sort_keys`` so a receipt payload hashes
   identically on Windows and Linux.  Timestamps and other nondeterministic
   values are NOT part of the content-hashed payload (see ``CORE_EXCLUDED``).

2. Strict task identity (T1)
   ``key_by_task_id`` keys a collection by ``task_id`` and fails on
   duplicate/missing keys or declared-count mismatches.
   ``expected_pilot_p2p_s`` holds the seven pilot tasks and the corrected
   strict P2P-S counts from ERRATUM_01_P2P_S_COUNTS.md (sum 457).
   ``saleor-rc-032b98afff20`` (strict 947) is explicitly NOT in the pilot.

3. Receipt validation (T3/T4/T5) -- M19B-R1H hardened, fail-closed
   ``validate_receipt`` returns 'PASS' ONLY when every mandatory provenance
   rule holds.  Every violation ends in a BLOCKED verdict (raised
   ``ReceiptError``); there is no partial PASS and a BLOCKED control decision
   can never yield PASS.  Hardened rules (M19B-R1H):

   - ``n_reps`` is MANDATORY and repetition coverage must be complete: a
     qualifying receipt requires exactly 3 distinct raw per-rep, per-side
     JUnit files (r0/r1/r2) and every required node must carry r0/r1/r2 raw
     repetition evidence on both sides.
   - Per-node outcomes and raw-repetition identities must AGREE; an outcome
     list without a matching per-rep observation ledger is a synthetic
     claim and is rejected.
   - pytest return codes are canonical: 0 OK; 1 TESTS_FAILED;
     2 INTERRUPTED; 3 INTERNAL_ERROR; 4 USAGE_ERROR; 5 NO_TESTS_COLLECTED.
     pytest RC and Docker/container RC are SEPARATE fields and both are
     validated; an unexplained RC (e.g. 99) or an unexplained nonzero
     container result can never yield PASS.  rc=1 with a recorded failing
     outcome is EXPECTED evidence (e.g. NEG), not an infrastructure failure.
   - ``control_qualification.decision == "BLOCKED"`` raises; failed runs are
     kept as diagnostic evidence via ``blocked_receipt_verdict``.
   - argv kind OS_ATTESTED requires a NON-EMPTY attestation block from an
     independent OS-attestation method; capture-at-subprocess-boundary is
     NOT independent OS attestation.
   - ``node_identity`` set equality must hold against the canonical hash of
     the receiver-carried per-node identity set, and -- when authoritative
     task-keyed node ids are supplied -- the sets themselves must match; a
     caller-supplied EXACT_MATCH flag alone is never trusted.
   - ``scope.scope_patch_paths`` is EDITABLE PRODUCTION SCOPE: common
     test-patch paths are rejected, and patch edits must be inside the
     allowed paths and outside test files.
   - SCHEMA VALIDATION DOES NOT PROVE DISK CONTENT.  The schema validates
     the receipt payload only; actual raw-file hashes MUST be re-verified
     against the files at the trusted consumer boundary with
     ``verify_raw_file_hashes``.

Design rule (M19B-R1): a wrapper that reads only a ``merged.update(...)``
``junit`` dictionary CANNOT substantiate three distinct repetitions.  A
receipt claiming ``n_reps == 3`` MUST name >=3 distinct raw per-rep, per-file
JUnit artifacts per side and MAY NOT derive per-node outcome lists from a
merged dict.  No crash: every violation ends in a BLOCKED verdict and no
uncaught exception escapes the validator (all malformed inputs become
``ReceiptError``, never ``IndexError`` or similar).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA_VERSION = "opws-receipt-v1"
RECEIPT_SCHEMA_REV = 1
CANONICAL_ENCODING = "utf-8"
REPS = (0, 1, 2)
PILOT_SUM_EXPECTED = 457

# Corrected strict P2P-S counts, source of truth:
# D:\\WP2\\audit_results\\M19B_P7_READINESS_2026-10-24\\ERRATUM_01_P2P_S_COUNTS.md
# (sha256 b8283999eae0307eb5719c33a2e14a823d37b23fbc18b43e5fa608343af2720f).
EXPECTED_PILOT_P2P_S: dict[str, int] = {
    "saleor-rc-0179b331be38": 13,
    "saleor-rc-0f16ed78b02b": 156,
    "saleor-rc-7e42fc67ce72": 103,
    "saleor-rc-8b0cbe2fb72f": 98,
    "saleor-rc-b2e3652af826": 74,
    "saleor-rc-df7c7d4e8466": 5,
    "saleor-rc-fe6e46266e81": 8,
}
assert sum(EXPECTED_PILOT_P2P_S.values()) == PILOT_SUM_EXPECTED

# Explicitly NOT a pilot task (erratum: 948 historical / 947 strict,
# historical vs strict confusion was the original count error).
NON_PILOT_032B = "saleor-rc-032b98afff20"
NON_PILOT_032B_STRICT = 947

# Canonical pytest return-code mapping (pytest.pytest_exitcodes):
# 0 OK; 1 TESTS_FAILED; 2 INTERRUPTED; 3 INTERNAL_ERROR;
# 4 USAGE_ERROR; 5 NO_TESTS_COLLECTED.  Any other value is UNEXPLAINED and
# cannot yield a qualified PASS.
PYTEST_RETURN_CODES: dict[int, str] = {
    0: "OK",
    1: "TESTS_FAILED",
    2: "INTERRUPTED",
    3: "INTERNAL_ERROR",
    4: "USAGE_ERROR",
    5: "NO_TESTS_COLLECTED",
}
# RCs that are terminal outcomes of the pytest process itself, never an
# observed, qualifiable test outcome.
TERMINAL_PYTEST_RCS = frozenset({2, 3, 4, 5})

# Independent OS-attestation methods for argv provenance.  Capture of argv at
# the subprocess/launcher boundary is NOT one of them.
OS_ATTESTATION_METHODS = frozenset(
    {"INDEPENDENT_OBSERVER", "CONTAINER_RUNTIME_INSPECT", "OS_PROC_CMDLINE_READ"}
)
# Wording that reveals an attestation was produced by the launching
# subprocess boundary rather than by an independent OS observer.
BOUNDARY_ATTESTATION_HINTS = ("subprocess", "at launch", "boundary")

EMPTY_PATCH_DIGEST = "0" * 64

# Fields that may NOT enter the deterministic content hash (nondeterministic
# by nature: wall-clock, monotonic deltas, host PIDs, ephemeral seeds).
CORE_EXCLUDED = frozenset(
    {
        "receipt_id",
        "generated_at_utc",
        "wall_s",
        "disk_free_before_gib",
        "disk_free_after_gib",
        "disk_growth_gib",
        "launcher_pid",
    }
)

MANDATORY_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "task_id",
        "parent_commit",
        "target_commit",
        "selected_arm",
        "control",
        "scope",
        "test_contract_sha256",
        "env",
        "argv",
        "rep_index",
        "n_reps",
        "process_returncode",
        "container_returncode",
        "returncode_provenance",
        "outputs",
        "node_identity",
        "per_node_outcomes",
        "timeout_infra",
        "control_qualification",
    }
)

SIDES = ("t", "p")
OUTCOME_LEVELS = frozenset({"passed", "failed", "error", "missing"})
REP_KEYS = frozenset({f"r{r}" for r in REPS})


class ReceiptError(ValueError):
    """A receipt payload violates the schema or its provenance rules (BLOCKED)."""


# --------------------------------------------------------------------------- #
# 1. canonical hashing                                                         #
# --------------------------------------------------------------------------- #
def canonical_bytes(obj: Any) -> bytes:
    """Deterministic JSON bytes: UTF-8, LF, no BOM, sorted keys, tight seps."""
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode(CANONICAL_ENCODING)


def sha256_canonical(obj: Any) -> str:
    """sha256 of the deterministic closed-form of ``obj`` (repr as-is)."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def hash_payload_core(payload: dict[str, Any]) -> str:
    """Deterministic receipt hash over the payload EXCLUDING nondeterminism."""
    core = {k: v for k, v in payload.items() if k not in CORE_EXCLUDED}
    return sha256_canonical(core)


def node_set_sha256(node_ids: Iterable[str]) -> str:
    """Canonical identity-set hash: sorted distinct node ids, tight JSON."""
    return sha256_canonical(sorted(set(node_ids)))


# --------------------------------------------------------------------------- #
# 2. strict task identity (T1)                                                #
# --------------------------------------------------------------------------- #
def key_by_task_id(
    entries: Iterable[dict[str, Any]],
    *,
    collection_name: str,
    declared_total: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Key a collection by ``task_id``; reject duplicate/missing keys.

    Fails when a ``task_id`` key is absent, when a key repeats, or when the
    number of keys disagrees with an explicit declared total.  This is the
    fail-closed form of "key each collection explicitly by ``task_id``".
    """
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        tid = entry.get("task_id")
        if not isinstance(tid, str) or not tid:
            raise ReceiptError(
                f"{collection_name}: entry missing non-empty str task_id"
            )
        if tid in out:
            raise ReceiptError(
                f"{collection_name}: duplicate task_id {tid!r}"
            )
        out[tid] = entry
    if declared_total is not None and len(out) != declared_total:
        raise ReceiptError(
            f"{collection_name}: {len(out)} keys != declared {declared_total}"
        )
    return out


def strict_p2p_s_from_task(task: dict[str, Any]) -> int:
    """Strict P2P_ONLY count of an M19A4 by-task entry; list length must
    equal the declared ``strict_counts.P2P_ONLY`` value."""
    strict_list = task.get("strict_p2p_only")
    counts = task.get("strict_counts")
    if not isinstance(strict_list, list) or not isinstance(counts, dict):
        raise ReceiptError(f"{task.get('task_id')}: malformed strict entry")
    declared = counts.get("P2P_ONLY")
    if not isinstance(declared, int) or declared < 0:
        raise ReceiptError(f"{task.get('task_id')}: missing strict P2P_ONLY count")
    if len(strict_list) != declared:
        raise ReceiptError(
            f"{task.get('task_id')}: len(strict_p2p_only)={len(strict_list)} "
            f"!= declared strict P2P_ONLY={declared}"
        )
    return declared


def verify_pilot_counts(
    by_task: dict[str, dict[str, Any]],
    repdiag: dict[str, dict[str, Any]],
    *,
    expected: dict[str, int] | None = None,
) -> dict[str, dict[str, int]]:
    """T1 strict join: each pilot task's M19A4 by-task strict P2P_ONLY and
    REP_IDENTITY_DIAGNOSTIC B_strict_p2p must both equal the erratum value."""
    exp = EXPECTED_PILOT_P2P_S if expected is None else expected
    joined: dict[str, dict[str, int]] = {}
    for tid, want in exp.items():
        if tid not in by_task:
            raise ReceiptError(f"pilot {tid} missing from M19A4 by-task")
        if tid not in repdiag:
            raise ReceiptError(f"pilot {tid} missing from REP_IDENTITY_DIAGNOSTIC")
        got_by_task = strict_p2p_s_from_task(by_task[tid])
        rd = repdiag[tid].get("counts", {})
        got_repdiag = rd.get("B_strict_p2p")
        if not isinstance(got_repdiag, int):
            raise ReceiptError(f"pilot {tid} missing B_strict_p2p in diagnostic")
        if got_by_task != want or got_repdiag != want:
            raise ReceiptError(
                f"pilot {tid}: by_task={got_by_task} diagnostic={got_repdiag} "
                f"!= expected {want}"
            )
        joined[tid] = {"by_task": got_by_task, "repdiag": got_repdiag}
    return joined


def verify_non_pilot_excluded(
    by_task: dict[str, dict[str, Any]],
    pilot: Iterable[str] = (),
) -> None:
    """032b98afff20 must exist with strict 947 and must NOT be a pilot task."""
    pilot_set = set(pilot) or set(EXPECTED_PILOT_P2P_S)
    if NON_PILOT_032B in pilot_set:
        raise ReceiptError(f"{NON_PILOT_032B} must not be in the pilot")
    if NON_PILOT_032B not in by_task:
        raise ReceiptError(f"{NON_PILOT_032B} missing from M19A4 by-task")
    got = strict_p2p_s_from_task(by_task[NON_PILOT_032B])
    if got != NON_PILOT_032B_STRICT:
        raise ReceiptError(
            f"{NON_PILOT_032B} strict={got} != expected {NON_PILOT_032B_STRICT}"
        )


# --------------------------------------------------------------------------- #
# 3. path / scope classification (M19B-R1H)                                   #
# --------------------------------------------------------------------------- #
def path_is_test_patch(path: str) -> bool:
    """True if ``path`` is a common test-patch path (not production scope).

    Classifies by directory segments named ``tests`` (anywhere above the
    basename) and by basenames matching the common pytest conventions
    (``test_*.py``, ``*_test.py``, ``conftest.py``).
    """
    p = path.replace("\\", "/").strip("/")
    segments = p.split("/")
    if any(seg == "tests" for seg in segments[:-1]):
        return True
    base = (segments[-1] if segments else "").lower()
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or base in ("conftest.py", "tests.py", "test.py")
    )


def path_is_within_scope(edit: str, allowed: Iterable[str]) -> bool:
    """True if ``edit`` targets a file inside one of the ``allowed`` path
    prefixes, with traversal / absolute / drive paths rejected."""
    e = edit.replace("\\", "/").strip("/")
    if not e or e.startswith("/") or e.startswith("..") or "/../" in "/" + e:
        return False
    if len(e) >= 2 and e[1] == ":":
        return False
    for a in allowed:
        a = a.replace("\\", "/").strip("/")
        if e == a or e.startswith(a.rstrip("/") + "/"):
            return True
    return False


# --------------------------------------------------------------------------- #
# 4. fail-closed receipt validation (T3/T4/T5, hardened)                      #
# --------------------------------------------------------------------------- #
def _require(payload: dict[str, Any], field: str) -> Any:
    if field not in payload or payload[field] is None:
        raise ReceiptError(f"missing mandatory provenance field: {field}")
    return payload[field]


def _require_commit_identity(payload: dict[str, Any]) -> None:
    parent = _require(payload, "parent_commit")
    target = _require(payload, "target_commit")
    if not isinstance(parent, str) or not isinstance(target, str):
        raise ReceiptError("parent/target commits must be strings")
    if parent == target:
        raise ReceiptError("parent_commit == target_commit is not a real task edge")
    if payload.get("parent_target_swapped") is True:
        raise ReceiptError("parent/target swapped is not a valid receipt")


def _require_env(payload: dict[str, Any]) -> None:
    env = _require(payload, "env")
    if not isinstance(env, dict):
        raise ReceiptError("env must be an object")
    digest = env.get("linux_environment_digest")
    manifest = env.get("manifest_sha256")
    image = env.get("image_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ReceiptError("env.linux_environment_digest missing (64-hex required)")
    if not isinstance(manifest, str) or len(manifest) != 64:
        raise ReceiptError("env.manifest_sha256 missing (signed manifest anchor)")
    if not isinstance(image, str) or len(image) != 64:
        raise ReceiptError("env.image_digest missing (immutable image digest)")


def _require_argv(payload: dict[str, Any]) -> None:
    argv = _require(payload, "argv")
    if not isinstance(argv, dict):
        raise ReceiptError("argv must be an object")
    kind = argv.get("kind")
    order = argv.get("order")
    if kind not in ("OS_ATTESTED", "HARNESS_CONSTRUCTED"):
        raise ReceiptError("argv.kind must be OS_ATTESTED or HARNESS_CONSTRUCTED")
    if not isinstance(order, list) or not all(
        isinstance(a, str) and a for a in order
    ):
        raise ReceiptError("argv.order must be a non-empty list of strings")
    claim = payload.get("claim_os_attested")
    if kind == "OS_ATTESTED":
        if claim is not True:
            raise ReceiptError(
                "argv.kind=OS_ATTESTED requires claim_os_attested=True"
            )
        attest = argv.get("attestation")
        if not isinstance(attest, dict) or not attest:
            raise ReceiptError(
                "argv claimed OS_ATTESTED without a NON-EMPTY attestation block"
            )
        method = attest.get("method")
        if method not in OS_ATTESTATION_METHODS:
            raise ReceiptError(
                f"attestation.method {method!r} is not an independent "
                f"OS-attestation method {sorted(OS_ATTESTATION_METHODS)}"
            )
        pid = attest.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ReceiptError("attestation.pid must be an integer")
        source = attest.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ReceiptError("attestation.source missing")
        if any(hint in source.lower() for hint in BOUNDARY_ATTESTATION_HINTS):
            raise ReceiptError(
                "capture-at-subprocess-boundary is NOT independent OS attestation"
            )
        attested_hash = attest.get("attested_argv_sha256")
        if attested_hash != sha256_canonical(order):
            raise ReceiptError(
                "attestation.attested_argv_sha256 does not match the receipt "
                "argv.order bytes"
            )
    else:  # HARNESS_CONSTRUCTED
        if claim is True:
            raise ReceiptError(
                "user-supplied argv claim must not be confused with OS attestation"
            )
        attest = argv.get("attestation")
        if isinstance(attest, dict) and attest:
            raise ReceiptError(
                "HARNESS_CONSTRUCTED argv must not carry an attestation block"
            )


def _require_outputs(payload: dict[str, Any]) -> None:
    outputs = _require(payload, "outputs")
    if not isinstance(outputs, dict):
        raise ReceiptError("outputs must be an object")
    junit = outputs.get("junit")
    if not isinstance(junit, list) or not junit:
        raise ReceiptError("outputs.junit must be a non-empty list")
    seen_names: set[str] = set()
    for item in junit:
        if not isinstance(item, dict):
            raise ReceiptError("outputs.junit entry must be an object")
        if not isinstance(item.get("file"), str) or not item["file"]:
            raise ReceiptError("outputs.junit entry missing file name")
        if item["file"] in seen_names:
            raise ReceiptError(
                f"rep collision: duplicate raw junit file {item['file']!r}"
            )
        seen_names.add(item["file"])
        digest = item.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ReceiptError(f"outputs.junit entry {item['file']} missing sha256")
        if item.get("derived_from_merged_dict") is True:
            raise ReceiptError(
                f"outputs.junit entry {item['file']} must be a RAW per-rep file, "
                "never a merged-dict artifact"
            )
    if outputs.get("snapshot_sha256_over_raw_files") is not None and not (
        isinstance(outputs["snapshot_sha256_over_raw_files"], str)
        and len(outputs["snapshot_sha256_over_raw_files"]) == 64
    ):
        raise ReceiptError("outputs.snapshot hash must be 64-hex")


def _task_short_id(task_id: Any) -> str:
    """The frozen raw-file prefix ({t12}) for a task id, or "" if unknown."""
    if not isinstance(task_id, str) or not task_id:
        return ""
    if task_id.startswith("saleor-rc-"):
        return task_id.split("saleor-rc-", 1)[1]
    return ""  # no authoritative short id: prefix check cannot be inferred


def _parse_raw_junit_name(name: str, task_id: Any) -> tuple[str, str, str]:
    """Strictly parse ``{t12}_{side}_r{rep}_f{idx}.xml``.

    Raises ReceiptError (never IndexError) on malformed names, unknown sides,
    unknown reps, or a prefix that does not belong to the receipt's task.
    """
    parts = name.split("_")
    if len(parts) != 4:
        raise ReceiptError(
            f"malformed raw junit file name {name!r}: expected "
            "{{t12}}_{{side}}_r{{rep}}_f{{idx}}.xml"
        )
    tid, side, rep, fidx = parts
    if side not in SIDES:
        raise ReceiptError(
            f"malformed raw junit file name {name!r}: side {side!r} not in {SIDES}"
        )
    if rep not in REP_KEYS:
        raise ReceiptError(
            f"malformed raw junit file name {name!r}: repetition {rep!r} not in "
            f"{sorted(REP_KEYS)}"
        )
    if not (fidx.startswith("f") and fidx.endswith(".xml") and fidx[1:-4].isdigit()):
        raise ReceiptError(
            f"malformed raw junit file name {name!r}: f-slot must be f<idx>.xml"
        )
    expected_prefix = _task_short_id(task_id)
    if expected_prefix and tid != expected_prefix:
        raise ReceiptError(
            f"raw junit file {name!r} does not belong to task {task_id!r} "
            f"(prefix {tid!r} != {expected_prefix!r})"
        )
    return side, rep, fidx


def _rep_grouping(outcomes_by_rep: dict[str, list[str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for rep in REPS:
        key = f"r{rep}"
        if key in outcomes_by_rep:
            grouped[key] = sorted(set(outcomes_by_rep[key]))
    return grouped


def per_rep_distinct_pass(per_side: dict[str, Any]) -> bool:
    """True iff the side claims 3 DISTINCT reps and every rep is all-pass."""
    raw = per_side.get("observations_by_rep")
    if not isinstance(raw, dict):
        return False
    grouped = _rep_grouping(raw)
    if tuple(sorted(grouped)) != ("r0", "r1", "r2"):
        return False
    return all(vals and all(v == "passed" for v in vals) for vals in grouped.values())


def _require_repetitions(payload: dict[str, Any]) -> None:
    """T4 (hardened): n_reps mandatory; complete r0/r1/r2 raw coverage per
    side; every required node carries r0/r1/r2 raw-repetition evidence on
    both sides; per-node outcomes agree with the observation ledger."""
    outputs = _require(payload, "outputs")
    junit = outputs.get("junit")
    if not isinstance(junit, list):
        raise ReceiptError("outputs.junit must be a list")

    n_reps = payload.get("n_reps")
    if isinstance(n_reps, bool) or not isinstance(n_reps, int) or n_reps < 1:
        raise ReceiptError("n_reps is mandatory and must be a positive integer")
    if n_reps != 3:
        raise ReceiptError(
            f"repetition coverage incomplete: n_reps={n_reps} -- a qualifying "
            "receipt requires 3 distinct reps (r0/r1/r2)"
        )

    rep_index = payload.get("rep_index")
    if not isinstance(rep_index, list) or rep_index != [0, 1, 2]:
        raise ReceiptError("rep_index must be [0, 1, 2] for n_reps=3")

    # Raw per-rep file identity coverage: 6 files minimum, distinct reps per
    # side, all names strictly parsed and bound to this task's prefix.
    raw: list[tuple[str, str, str]] = []
    for item in junit:
        if not isinstance(item, dict):
            continue
        if item.get("raw") is not True:
            continue
        name = item.get("file")
        if not isinstance(name, str) or not name:
            raise ReceiptError("outputs.junit raw entry missing file name")
        raw.append(_parse_raw_junit_name(name, payload.get("task_id")))
    if len(raw) < n_reps * len(SIDES):
        raise ReceiptError(
            "n_reps=3 requires >=6 distinct raw per-rep JUnit files "
            f"(got {len(raw)})"
        )
    for side in SIDES:
        side_reps = sorted({rep for s, rep, _ in raw if s == side})
        if side_reps != ["r0", "r1", "r2"]:
            raise ReceiptError(
                f"side {side} lacks distinct reps r0/r1/r2: {side_reps}"
            )

    # Per-node outcomes: non-empty, both sides, exactly n_reps outcomes
    # agreeing with the raw-repetition observation ledger.
    per_node = _require(payload, "per_node_outcomes")
    if not isinstance(per_node, dict) or not per_node:
        raise ReceiptError(
            "per_node_outcomes must be a NON-EMPTY object of "
            "{node_id: {side: record}}"
        )
    for node, sides in per_node.items():
        if not isinstance(node, str) or not node:
            raise ReceiptError("per_node_outcomes keys must be non-empty node ids")
        if not isinstance(sides, dict):
            raise ReceiptError(f"per_node_outcomes[{node!r}] malformed")
        for side in SIDES:
            rec = sides.get(side)
            if not isinstance(rec, dict):
                raise ReceiptError(
                    f"per_node_outcomes[{node!r}][{side}] malformed"
                )
            outcomes = rec.get("outcomes")
            if not isinstance(outcomes, list) or len(outcomes) != n_reps:
                raise ReceiptError(
                    f"per_node_outcomes[{node!r}][{side}] needs exactly "
                    f"{n_reps} outcomes"
                )
            if any(o not in OUTCOME_LEVELS for o in outcomes):
                raise ReceiptError(
                    f"per_node_outcomes[{node!r}][{side}] has non-level outcome"
                )
            obs = rec.get("observations_by_rep")
            if not isinstance(obs, dict) or sorted(obs) != ["r0", "r1", "r2"]:
                raise ReceiptError(
                    f"{node!r} {side}: raw-repetition evidence "
                    "(observations_by_rep) must cover exactly r0/r1/r2"
                )
            flat: list[str] = []
            for rep in REPS:
                vals = obs.get(f"r{rep}")
                if not isinstance(vals, list) or len(vals) != 1:
                    if isinstance(vals, list) and len(vals) > 1:
                        raise ReceiptError(
                            f"{node!r} {side} r{rep}: >1 observation = duplicate "
                            "or conflicting fragment within one rep"
                        )
                    raise ReceiptError(
                        f"{node!r} {side} r{rep}: expected exactly one raw "
                        "observation per rep"
                    )
                value = vals[0]
                if value not in OUTCOME_LEVELS:
                    raise ReceiptError(
                        f"{node!r} {side} r{rep}: non-level observation {value!r}"
                    )
                flat.append(value)
            if list(outcomes) != flat:
                raise ReceiptError(
                    f"{node!r} {side}: per-node outcomes do not agree with "
                    "raw-repetition observations_by_rep"
                )

    if payload.get("p2p_s_claim") is True:
        for node, sides in per_node.items():
            if not (
                per_rep_distinct_pass(sides.get("t", {}))
                and per_rep_distinct_pass(sides.get("p", {}))
            ):
                raise ReceiptError(
                    f"P2P-S claim on {node!r} without distinct all-pass reps "
                    "on BOTH sides"
                )


def _require_node_identity(
    payload: dict[str, Any],
    *,
    expected_task_node_ids: Iterable[str] | None = None,
) -> None:
    ni = _require(payload, "node_identity")
    if not isinstance(ni, dict):
        raise ReceiptError("node_identity must be an object")
    equality = ni.get("set_equality")
    if equality != "EXACT_MATCH":
        raise ReceiptError(
            f"node identity is {equality!r}; BLOCKED unless EXACT_MATCH"
        )
    expected = ni.get("expected_sha256")
    observed = ni.get("observed_sha256")
    for key, val in (("expected_sha256", expected), ("observed_sha256", observed)):
        if not isinstance(val, str) or len(val) != 64:
            raise ReceiptError(f"node_identity.{key} must be 64-hex")
    if expected != observed:
        raise ReceiptError(
            "node_identity EXACT_MATCH requires expected_sha256 == observed_sha256"
        )
    # The observed set is the per-node identity set carried by the receipt
    # itself; its canonical hash must equal the claimed observed hash.
    per_node = payload.get("per_node_outcomes")
    if not isinstance(per_node, dict) or not per_node:
        raise ReceiptError("node identity cannot be verified without per_node_outcomes")
    observed_nodes = [k for k in per_node if isinstance(k, str)]
    canonical_observed = node_set_sha256(observed_nodes)
    if observed != canonical_observed:
        raise ReceiptError(
            "node_identity.observed_sha256 does not equal the canonical hash "
            "of the observed per-node identity set carried by the receipt"
        )
    # Authoritative task-keyed node ids, when supplied, replace the naked
    # caller-supplied EXACT_MATCH flag: set equality is checked for real.
    if expected_task_node_ids is not None:
        exp_set = set(expected_task_node_ids)
        obs_set = set(observed_nodes)
        if obs_set != exp_set:
            raise ReceiptError(
                "node identity SET inequality vs authoritative task-keyed "
                f"node ids: observed-only={sorted(obs_set - exp_set)[:4]} "
                f"expected-only={sorted(exp_set - obs_set)[:4]}"
            )
        if expected != node_set_sha256(exp_set):
            raise ReceiptError(
                "node_identity.expected_sha256 does not match the "
                "authoritative task-keyed node identity set hash"
            )


def _require_timeout_infra(payload: dict[str, Any]) -> None:
    """T4/T5 (hardened): canonical pytest RC mapping; pytest RC is SEPARATE
    from Docker/container RC; an unexplained RC never qualifies."""
    ti = _require(payload, "timeout_infra")
    if not isinstance(ti, dict):
        raise ReceiptError("timeout_infra must be an object")
    category = ti.get("category")
    if category not in ("NONE", "TIMEOUT", "INFRA", "COLLECTION"):
        raise ReceiptError(
            "timeout_infra.category must be NONE/TIMEOUT/INFRA/COLLECTION"
        )

    # pytest return code: must be one of the canonical 0..5 set.  Anything
    # else (99, -1, 6, a string, a bool...) is UNEXPLAINED and can never
    # yield a qualified PASS.
    rc = payload.get("process_returncode")
    if isinstance(rc, bool) or not isinstance(rc, int) or rc not in PYTEST_RETURN_CODES:
        raise ReceiptError(
            f"unexplained pytest return code {rc!r}: must be one of "
            f"{sorted(PYTEST_RETURN_CODES)} "
            "(0=OK 1=TESTS_FAILED 2=INTERRUPTED 3=INTERNAL_ERROR "
            "4=USAGE_ERROR 5=NO_TESTS_COLLECTED)"
        )
    if rc in TERMINAL_PYTEST_RCS:
        raise ReceiptError(
            f"pytest return code {rc} = {PYTEST_RETURN_CODES[rc]}: terminal "
            "outcome, receipt cannot qualify"
        )

    # Docker/container return code is a SEPARATE field; a nonzero value must
    # be EXPLAINED (the container propagated the pytest rc) or the receipt is
    # blocked as an unexplained infra failure.
    ctrc = payload.get("container_returncode")
    if isinstance(ctrc, bool) or not isinstance(ctrc, int):
        raise ReceiptError("container_returncode must be an integer")
    if ctrc != 0:
        if ctrc != rc:
            raise ReceiptError(
                f"Docker/container return code {ctrc} != pytest rc {rc} and is "
                "not explained by any timeout/infra category: unexplained "
                "infra failure, receipt cannot qualify"
            )
        if category in ("TIMEOUT", "INFRA", "COLLECTION"):
            raise ReceiptError(
                f"timeout_infra.category={category} must block the receipt"
            )

    # rc congruence with the recorded per-node outcomes: rc=0 requires every
    # outcome passed; rc=1 (TESTS_FAILED) requires at least one non-passed
    # outcome.  Anything else is an unexplained RC claim and cannot PASS.
    per_node = payload.get("per_node_outcomes")
    if isinstance(per_node, dict) and per_node:
        any_nonpassed = any(
            o != "passed"
            for sides in per_node.values()
            if isinstance(sides, dict)
            for side in SIDES
            if isinstance(sides.get(side), dict)
            for o in (sides[side].get("outcomes") or [])
        )
    else:
        any_nonpassed = False
    if rc == 0 and any_nonpassed:
        raise ReceiptError(
            "pytest return code 0 (OK) but per-node outcomes contain "
            "failures/errors: incongruent receipt"
        )
    if rc == 1 and not any_nonpassed:
        raise ReceiptError(
            "pytest return code 1 (TESTS_FAILED) recorded but every per-node "
            "outcome is passed: unexplained RC, receipt cannot qualify"
        )

    # rc=1 (TESTS_FAILED) with zero failing outcomes is incongruent (above).
    # rc=2/3/4/5 are already blocked by TERMINAL_PYTEST_RCS.
    outputs = payload.get("outputs")
    if category == "NONE" and isinstance(outputs, dict) and (
        outputs.get("container_completed") is False
    ):
        raise ReceiptError(
            "category NONE with an incomplete container is a silent "
            "timeout/infra/collection failure"
        )
    if category in ("TIMEOUT", "INFRA", "COLLECTION"):
        raise ReceiptError(
            f"timeout_infra.category={category} must block the receipt"
        )
    if not isinstance(ti.get("detail"), str) or not ti["detail"]:
        raise ReceiptError("timeout_infra.detail missing")


def _require_control(payload: dict[str, Any]) -> None:
    """T5 (hardened): a BLOCKED control decision can never yield PASS."""
    cq = _require(payload, "control_qualification")
    if not isinstance(cq, dict):
        raise ReceiptError("control_qualification must be an object")
    decision = cq.get("decision")
    if decision not in ("PASS", "BLOCKED"):
        raise ReceiptError("control_qualification.decision must be PASS/BLOCKED")
    if decision == "BLOCKED":
        raise ReceiptError(
            "control_qualification.decision is BLOCKED: the receipt must be "
            "retained as diagnostic evidence with verdict BLOCKED, never PASS"
        )
    if not isinstance(cq.get("reason"), str) or not cq["reason"]:
        raise ReceiptError("control_qualification.reason missing")
    control = payload.get("control")
    # Fail-closed controls (T5): NEG with only pass-only all-stable outcomes is
    # suspicious; a FULL_REFERENCE run must match the frozen reference exactly.
    if control == "NEG" and decision == "PASS" and not cq.get(
        "sensitivity_supported"
    ):
        raise ReceiptError(
            "NEG control PASS requires sensitivity_supported evidence"
        )
    if control == "FULL_REFERENCE":
        ref = cq.get("frozen_reference_sha256")
        if not isinstance(ref, str) or len(ref) != 64:
            raise ReceiptError(
                "FULL_REFERENCE PASS requires frozen_reference_sha256 match"
            )
        if cq.get("reference_mismatch") is True:
            raise ReceiptError("FULL_REFERENCE mismatch must block the receipt")


def _require_scope(payload: dict[str, Any]) -> None:
    """(hardened) scope_patch_paths is EDITABLE PRODUCTION SCOPE: common
    test-patch paths are rejected, and each named patch edit must be inside
    the allowed paths and outside test files."""
    scope = _require(payload, "scope")
    if not isinstance(scope, dict):
        raise ReceiptError("scope must be an object")
    paths = scope.get("scope_patch_paths")
    if not isinstance(paths, list) or not paths:
        raise ReceiptError("scope.scope_patch_paths must be a non-empty list")
    for p in paths:
        if not isinstance(p, str) or not p:
            raise ReceiptError(
                "scope.scope_patch_paths entries must be non-empty path strings"
            )
        if path_is_test_patch(p):
            raise ReceiptError(
                f"scope_patch_path {p!r} is a TEST-patch path; tests are not "
                "editable production scope"
            )
    digest = scope.get("scope_patch_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ReceiptError("scope.scope_patch_sha256 missing")
    if scope.get("outside_allowed_paths") is True:
        raise ReceiptError("scope patch outside the allowed paths must block")

    edits = scope.get("patch_edits")
    if edits is not None:
        if not isinstance(edits, list) or not edits:
            raise ReceiptError("scope.patch_edits must be a non-empty list")
        for e in edits:
            if not isinstance(e, str) or not e:
                raise ReceiptError(
                    "scope.patch_edits entries must be non-empty path strings"
                )
            if path_is_test_patch(e):
                raise ReceiptError(
                    f"patch edit {e!r} targets a test file -- test-patch "
                    "edits are out of scope"
                )
            if not path_is_within_scope(e, paths):
                raise ReceiptError(
                    f"patch edit {e!r} is outside scope_patch_paths {paths}"
                )
        if digest == EMPTY_PATCH_DIGEST:
            raise ReceiptError(
                "scope.patch_edits claimed but scope_patch_sha256 is the zero "
                "digest: patch digest is mandatory with edits"
            )
    elif digest != EMPTY_PATCH_DIGEST:
        raise ReceiptError(
            "scope_patch_sha256 claims a patch but no patch_edits are named: "
            "the patch edits cannot be validated"
        )


def validate_receipt(
    payload: dict[str, Any],
    *,
    expected_task_node_ids: Iterable[str] | None = None,
) -> str:
    """Fail-closed receipt check.  Returns 'PASS' or raises ReceiptError with
    the exact blocking reason.  No partial PASS exists.

    ``expected_task_node_ids`` (optional): authoritative task-keyed node ids
    that the per-node identity set must EQUAL -- a caller-supplied EXACT_MATCH
    flag alone is never trusted.

    NOTE: this function is PURE and therefore does NOT prove disk content --
    the schema validates the payload only.  Raw-file hashes must be
    re-verified against the actual files at the trusted consumer boundary
    with ``verify_raw_file_hashes``.
    """
    if payload.get("schema") != RECEIPT_SCHEMA_VERSION:
        raise ReceiptError(
            f"schema {payload.get('schema')!r} != {RECEIPT_SCHEMA_VERSION!r}"
        )
    if payload.get("schema_version") != RECEIPT_SCHEMA_REV:
        raise ReceiptError("schema_version mismatch")
    for field in sorted(MANDATORY_FIELDS):
        _require(payload, field)
    tc = payload.get("test_contract_sha256")
    if not isinstance(tc, str) or len(tc) != 64:
        raise ReceiptError("test_contract_sha256 must be 64-hex")
    rcp = payload.get("returncode_provenance")
    if not isinstance(rcp, str) or not rcp.strip():
        raise ReceiptError("returncode_provenance must be a non-empty string")
    _require_commit_identity(payload)
    _require_scope(payload)
    _require_env(payload)
    _require_argv(payload)
    _require_outputs(payload)
    _require_repetitions(payload)
    _require_node_identity(
        payload, expected_task_node_ids=expected_task_node_ids
    )
    _require_timeout_infra(payload)
    _require_control(payload)
    return "PASS"


def blocked_receipt_verdict(payload: dict[str, Any], blocking_error: Any) -> dict[str, Any]:
    """Deterministic diagnostic record for a FAILED/BLOCKED run.

    Failed runs are NEVER discarded: the run's receipt is kept as diagnostic
    evidence together with an explicit BLOCKED verdict and the exact blocking
    reason.  No timestamps enter the record, so it hashes deterministically.
    """
    reason = (
        str(blocking_error)
        if isinstance(blocking_error, BaseException)
        else str(blocking_error)
    )
    return {
        "schema": RECEIPT_SCHEMA_VERSION,
        "schema_version": RECEIPT_SCHEMA_REV,
        "verdict": "BLOCKED",
        "task_id": payload.get("task_id"),
        "n_reps": payload.get("n_reps"),
        "blocking_reason": reason,
        "receipt_digest": hash_payload_core(payload),
    }


def verify_raw_file_hashes(
    payload: dict[str, Any], base_dir: Path | str
) -> dict[str, str]:
    """Trusted-consumer boundary verification: read the ACTUAL raw JUnit
    files under ``base_dir`` and require every recorded hash to match disk.

    This is the only place disk content is proven for a receipt; schema
    validation alone never implies disk content.  Raises ReceiptError with
    the exact missing/mismatched file on any drift, otherwise returns the
    verified {file name: sha256} mapping.
    """
    root = Path(base_dir)
    outputs = payload.get("outputs")
    junit = outputs.get("junit") if isinstance(outputs, dict) else None
    if not isinstance(junit, list):
        raise ReceiptError("cannot verify raw hashes without outputs.junit")
    verified: dict[str, str] = {}
    for item in junit:
        if not isinstance(item, dict):
            raise ReceiptError("outputs.junit entry must be an object")
        name = item.get("file")
        recorded = item.get("sha256")
        if not isinstance(name, str) or not name or not isinstance(recorded, str):
            raise ReceiptError("raw junit entry missing file/sha256")
        p = root / name
        if not p.is_file():
            raise ReceiptError(
                f"raw file missing at consumer boundary: {name}"
            )
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != recorded:
            raise ReceiptError(
                f"raw file hash mismatch at consumer boundary: {name} "
                f"recorded {recorded} but disk is {got}"
            )
        verified[name] = got
    return verified


def receipt_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Stable summary used by tests/reports (no timestamp fields)."""
    return {
        "schema": payload.get("schema"),
        "schema_version": payload.get("schema_version"),
        "task_id": payload.get("task_id"),
        "receipt_id": hash_payload_core(payload),
        "n_reps": payload.get("n_reps"),
        "node_identity": (payload.get("node_identity") or {}).get("set_equality"),
        "timeout_infra_category": (payload.get("timeout_infra") or {}).get(
            "category"
        ),
        "control_qualification": (payload.get("control_qualification") or {}).get(
            "decision"
        ),
    }
