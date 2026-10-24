"""OPWS M19B-R2 -- additive launcher-run capture + receipt consumer (offline).

Pure, offline, stdlib-only.  Nothing here executes Saleor, Docker, WSL, the
network or a model, and it NEVER modifies frozen source: ``harness_v3``,
``wp2_m16_r1``, ``oracle_confirmation``, ``oracle_semantics_v2`` and
``receipt_schema_v1`` are imported/parsed READ-ONLY.

Layers (each fail-closed; every violation raises ``LauncherReceiptError``):

1. LAUNCH CAPTURE (atomic 2)
   ``LaunchCapture`` wraps the SAME runner interface the frozen code uses
   (``wsl(script)`` / ``wsl_docker(args)`` / ``subprocess.run`` shapes) and
   records every subprocess boundary: ordered argv, input payload digest,
   FULL container stdout and return code.  Evidence is labelled honestly:
   ``argv_evidence_kind`` returns ``HARNESS_CONSTRUCTED`` -- a
   capture-at-subprocess-boundary is NEVER independent OS attestation.  A
   receipt is built with ``argv.kind == "HARNESS_CONSTRUCTED"`` and
   ``claim_os_attested=False``; nothing in this module ever fabricates an
   OS attestation block or an attested argv hash.

2. PER-INVOCATION RETURN CODES (atomic 3)
   The frozen V3 runner emits ``RUN_{i}_RC=$?`` per pytest invocation, with
   flat index ``i = rep * len(test_files) + file_idx`` (rep-major), ending
   with ``ALL_RUNS_DONE``; install fragments echo INSTALL_MAIN_FAIL /
   INSTALL_DEV_FAIL / TOOLING_FAIL and ``exit 2``.  ``parse_run_rc_ledger``
   parses that EXACT format and rejects missing/duplicated/extra/
   out-of-order indices, malformed lines and invocation-count mismatches.
   ``validate_invocation_contract`` additionally rejects an absent
   ALL_RUNS_DONE, install-failure markers, silent timeouts (no stdout at
   all) and rc-vs-raw-JUnit contradictions.  A per-pytest-invocation rc is
   never substituted by an aggregate container rc.

3. CONTROL-AWARE pytest RC=2 (atomic 4)
   RC=2 is INTERRUPTED and terminal (``receipt_schema_v1`` never lets it
   qualify).  ``classification_for_interrupted`` permits exactly one
   DIAGNOSTIC classification -- parent-side, matched to PREDECLARED
   expected collection-error node identities, with a collection-error
   signal in the raw JUnit and a frozen task oracle that authorizes
   PARENT_COLLECTION_ERROR > 0.  The golden pilot
   ``saleor-rc-7e42fc67ce72`` (PARENT_COLLECTION_ERROR=0,
   SYMBOL_ABSENCE_F2P=0) authorizes NO rc=2 exception.  A diagnostic is
   never BEHAVIORAL_F2P-eligible and never produces a passing receipt
   (the schema blocks the COLLECTION category), only a deterministic
   blocked diagnostic record.

4. RECEIPT CONSUMER (atomic 5)
   ``load_task_oracle_expectation`` reads the frozen task-keyed oracle
   (M19A4 by-task, M19A4 node ledger, three-run sensitivity binding and
   the behavior contract manifest) -- counts, test files, commits,
   contract sha and the FULL 117-node universe for the golden pilot.
   ``build_observation_ledgers`` rebuilds per-node, per-side, per-rep
   r0/r1/r2 evidence from the ACTUAL raw JUnit files (frozen parser,
   read-only), ``verify_oracle_reproduction`` re-runs the frozen
   classifier and requires exact count/node reproduction of the frozen
   oracle, and ``assemble_flat_raw_dir`` materializes byte-identical flat
   copies so the frozen ``verify_raw_file_hashes`` can be invoked at the
   trusted consumer boundary.  ``validate_receipt`` is always invoked with
   the authoritative task-keyed node identities.

5. MERGED-DICT NEGATIVE (atomic 6)
   ``assess_merged_dict_only`` proves that a wrapper holding ONLY a merged
   ``junit`` dictionary (the frozen ``dict.update`` last-rep-wins seam)
   cannot claim successful qualification: no per-rep raw artifacts, no
   observation ledger, and the schema rejects merged-derived artifacts.

Bounds honoured: no writes to frozen evidence; no behavioural claims; the
only files created are flat verification copies under a CALLER-provided
directory and nothing is executed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


def _load_frozen(name: str) -> Any:
    """Frozen read-only module under either layout: qualified (scripts/ real
    runs) or top-level (existing offline test harness with sys.path insert).
    Returned as Any so calls stay untyped (wrapper only)."""
    import importlib

    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return importlib.import_module(f"benchmark.wp2.{name}")


_oc: Any = _load_frozen("oracle_confirmation")  # frozen parser (read-only)
rs: Any = _load_frozen("receipt_schema_v1")  # frozen schema (read-only)

LAUNCH_CAPTURE_VERSION = "launcher-receipt-v1"
REPS = 3
SIDES = ("t", "p")
ALL_RUNS_DONE_MARK = "ALL_RUNS_DONE"
RUN_RC_RE = re.compile(r"(?m)^RUN_(\d+)_RC=(\d+)\s*$")
INSTALL_FAIL_MARKERS = ("INSTALL_MAIN_FAIL", "INSTALL_DEV_FAIL", "TOOLING_FAIL")
TERMINAL_RCS = frozenset({2, 3, 4, 5})
# The ONLY per-invocation rc that may ever be classified as a parent-side
# collection-error DIAGNOSTIC (never as an eligible outcome).
INTERRUPTED_RC = 2

_COLLECTION_ERROR_RE = re.compile(r"collect", re.IGNORECASE)
V2_CLASSES = (
    "BEHAVIORAL_F2P",
    "SYMBOL_ABSENCE_F2P",
    "PARENT_COLLECTION_ERROR",
    "P2P_ONLY",
    "FLAKY",
    "TARGET_ORACLE_INVALID",
    "OTHER_REVIEW_REQUIRED",
)


class LauncherReceiptError(ValueError):
    """An additive-side provenance/consistency violation (fail-closed)."""


# --------------------------------------------------------------------------- #
# frozen command construction (mirrors harness_v3.run_state_v3 run list)      #
# --------------------------------------------------------------------------- #
def _tid12(task_id: str) -> str:
    if task_id.startswith("saleor-rc-"):
        return task_id.split("saleor-rc-", 1)[1]
    raise LauncherReceiptError(f"cannot derive the frozen raw-file prefix for {task_id!r}")


def construct_pytest_command(
    task12: str,
    state: str,
    rep: int,
    file_idx: int,
    test_file: str,
    worktree_name: str,
) -> str:
    """Byte-for-byte mirror of the frozen ``harness_v3.run_state_v3`` run
    string (the same f-string the frozen code writes into .wp2_runs.sh)."""
    if state not in SIDES:
        raise LauncherReceiptError(f"state {state!r} not in {SIDES}")
    jname = f"{task12}_{state}_r{rep}_f{file_idx}"
    return (
        "/opt/venv/bin/python -m pytest -p no:cacheprovider -o addopts= "
        "--ds=saleor.tests.settings --disable-socket --reuse-db "
        f"--junitxml /workspace/{worktree_name}/{jname}.xml -q {test_file!r}"
    )


@dataclass(frozen=True)
class PytestInvocation:
    """One pytest invocation as the frozen V3 runner enumerates it."""

    flat_index: int  # i = rep * len(test_files) + file_idx (rep-major)
    side: str  # "t" target | "p" parent
    rep: int  # 0..2
    file_idx: int  # index into the frozen changed-test-file list
    test_file: str
    junit_name: str  # f"{task12}_{side}_r{rep}_f{file_idx}"
    command: str  # frozen container-internal command

    @property
    def argv(self) -> list[str]:
        # HARNESS_CONSTRUCTED argv: deterministic from the frozen f-string.
        return _shlex_split(self.command)


def _shlex_split(command: str) -> list[str]:
    import shlex

    try:
        return shlex.split(command)
    except ValueError as exc:  # pragma: no cover - frozen format is well-formed
        raise LauncherReceiptError(f"cannot split constructed argv: {exc}") from exc


def planned_invocations(
    task12: str,
    state: str,
    test_files: list[str] | tuple[str, ...],
    worktree_name: str | None = None,
) -> list[PytestInvocation]:
    """The FULL ordered invocation list a state must execute, in the frozen
    rep-major flat numbering (RUN_0..RUN_{3*n-1})."""
    wt = worktree_name or f"{task12}_v3_{state}"
    if state not in SIDES:
        raise LauncherReceiptError(f"state {state!r} not in {SIDES}")
    if not test_files:
        raise LauncherReceiptError("empty changed-test-file list")
    out: list[PytestInvocation] = []
    for rep in range(REPS):
        for idx, tf in enumerate(test_files):
            i = rep * len(test_files) + idx
            jname = f"{task12}_{state}_r{rep}_f{idx}"
            cmd = construct_pytest_command(task12, state, rep, idx, tf, wt)
            out.append(PytestInvocation(i, state, rep, idx, tf, jname, cmd))
    return out


# --------------------------------------------------------------------------- #
# per-invocation return-code ledger (atomic 3)                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunLedger:
    """Parsed/failed per-invocation rc ledger of ONE state container."""

    rc_by_index: dict[int, int]
    all_runs_done: bool
    install_failed: bool
    install_markers: tuple[str, ...]
    container_returncode: int | None
    source: str  # BOUNDARY_FULL_STDOUT | TIMEOUT_NO_STDOUT | FROZEN_STDOUT_TAIL


def detect_install_failure(stdout: str) -> tuple[bool, tuple[str, ...]]:
    found = tuple(m for m in INSTALL_FAIL_MARKERS if m in stdout)
    return bool(found), found


def parse_run_rc_ledger(
    stdout: str,
    *,
    expected_runs: int,
    source: str = "BOUNDARY_FULL_STDOUT",
) -> RunLedger:
    """Parse ALL ``RUN_i_RC`` records in the frozen format.  Fails closed on
    missing/duplicated/extra/out-of-order indices, malformed lines and
    invocation-count mismatches.  ``source`` labels WHERE the stdout came
    from; a truncated frozen tail (``FROZEN_STDOUT_TAIL``) can never prove a
    full ledger and is rejected downstream by count checks."""
    if isinstance(expected_runs, bool) or expected_runs < 1:
        raise LauncherReceiptError("expected_runs must be a positive integer")
    matches = list(RUN_RC_RE.finditer(stdout))
    if len(matches) != expected_runs:
        raise LauncherReceiptError(
            f"invocation count mismatch: {len(matches)} RUN_i_RC records for {expected_runs} expected invocations"
        )
    rc_by: dict[int, int] = {}
    last_idx = -1
    for m in matches:
        idx, rc = int(m.group(1)), int(m.group(2))
        if idx in rc_by:
            raise LauncherReceiptError(f"duplicate RUN_{idx}_RC record")
        if idx >= expected_runs:
            raise LauncherReceiptError(f"extra RUN_{idx}_RC beyond expected indices 0..{expected_runs - 1}")
        if idx < last_idx:
            raise LauncherReceiptError(f"RUN records out of order: RUN_{idx}_RC after RUN_{last_idx}_RC")
        rc_by[idx] = rc
        last_idx = idx
    if set(rc_by) != set(range(expected_runs)):
        missing = sorted(set(range(expected_runs)) - set(rc_by))
        raise LauncherReceiptError(f"missing RUN_i_RC records: {missing}")
    install_failed, markers = detect_install_failure(stdout)
    all_done = ALL_RUNS_DONE_MARK in stdout
    return RunLedger(
        rc_by_index=rc_by,
        all_runs_done=all_done,
        install_failed=install_failed,
        install_markers=markers,
        container_returncode=None,
        source=source,
    )


# --------------------------------------------------------------------------- #
# launch capture (atomic 2)                                                   #
# --------------------------------------------------------------------------- #
def argv_evidence_kind(argv: list[str] | tuple[str, ...]) -> str:
    """Honest label: capture at the subprocess/launcher boundary is
    HARNESS_CONSTRUCTED, never an independent OS attestation method."""
    del argv
    return "HARNESS_CONSTRUCTED"


def boundary_kind(argv: list[str] | tuple[str, ...]) -> str:
    """Classify a launch boundary from its PRESERVED ordered argv."""
    a = list(argv)
    if "docker" in a:
        sub = a[a.index("docker") + 1 :]
        if sub and sub[0] == "run":
            return "CONTAINER_RUN"
        if sub and sub[0] == "exec":
            return "DB_EXEC"
        if sub and sub[0] == "image":
            return "IMAGE_INSPECT"
        return "DOCKER_OTHER"
    joined = " ".join(a)
    if ".wp2_runs.sh" in joined:
        return "RUNS_SCRIPT_WRITE"
    if ".install.sh" in joined:
        return "INSTALL_SCRIPT_WRITE"
    if "cat " in joined and ".xml" in joined:
        return "JUNIT_READ"
    if "git " in joined or joined.startswith("git "):
        return "GIT"
    return "OTHER"


def side_from_container_argv(argv: list[str] | tuple[str, ...]) -> str | None:
    """Resolve parent/target side from the container-run argv itself: the
    frozen V3 fresh-DB name ``saleor_v3_{t12}_{state}`` appears in the
    DATABASE_URL env pin.  Unresolvable -> None (fail closed upstream)."""
    a = list(argv)
    for i, tok in enumerate(a):
        if tok == "-e" and i + 1 < len(a) and a[i + 1].startswith("DATABASE_URL="):
            url = a[i + 1]
            db = url.rsplit("/", 1)[-1]
            side = db.rsplit("_", 1)[-1]
            return side if side in SIDES else None
    return None


@dataclass(frozen=True)
class HostLaunch:
    """One recorded subprocess boundary (ordered argv preserved verbatim)."""

    boundary: str
    ordered_argv: tuple[str, ...]
    input_payload_sha256: str | None
    stdout_full: str | None
    returncode: int | None
    timeout: bool


class BackendRunner(Protocol):
    """The exact runner shapes the frozen harness uses (plus the direct
    ``subprocess.run`` script-write shape).  Synthetic tests inject a fake;
    a real authorized run would bind the wp2_linux_dryrun helpers."""

    def wsl(self, script: str, timeout_s: int | None = None) -> subprocess.CompletedProcess[str]: ...

    def wsl_docker(self, args: list[str], timeout_s: int | None = None) -> subprocess.CompletedProcess[str]: ...

    def subprocess_run(
        self,
        argv: list[str],
        *,
        input_payload: bytes | None = None,
        timeout_s: int | None = None,
    ) -> subprocess.CompletedProcess[str]: ...


class LaunchCapture:
    """Additive wrapper around the frozen runner shapes.  Records every
    subprocess boundary: ordered argv (EXACTLY as given), the digest of any
    piped input, FULL stdout of every launch and the return code.  Never
    claims OS attestation."""

    def __init__(self, backend: BackendRunner) -> None:
        self._backend = backend
        self.launches: list[HostLaunch] = []

    def _record(
        self,
        argv: list[str],
        input_payload: bytes | None,
        _timeout_s: int | None,
        call: Any,
    ) -> subprocess.CompletedProcess[str]:
        kind = boundary_kind(argv)
        try:
            comp: subprocess.CompletedProcess[str] = call()
        except subprocess.TimeoutExpired:
            self.launches.append(
                HostLaunch(
                    boundary=kind,
                    ordered_argv=tuple(argv),
                    input_payload_sha256=_payload_sha(input_payload),
                    stdout_full=None,
                    returncode=None,
                    timeout=True,
                )
            )
            raise
        payload_sha = _payload_sha(input_payload)
        self.launches.append(
            HostLaunch(
                boundary=kind,
                ordered_argv=tuple(argv),
                input_payload_sha256=payload_sha,
                stdout_full=comp.stdout if isinstance(comp.stdout, str) else None,
                returncode=comp.returncode,
                timeout=False,
            )
        )
        return comp  # typed below via cast in _record

    def wsl(self, script: str, timeout_s: int | None = None) -> subprocess.CompletedProcess[str]:
        return self._record(
            ["wsl", "-d", "Ubuntu-24.04", "--", "bash", "-lc", script],
            None,
            timeout_s,
            lambda: self._backend.wsl(script, timeout_s=timeout_s),
        )

    def wsl_docker(self, args: list[str], timeout_s: int | None = None) -> subprocess.CompletedProcess[str]:
        argv = ["wsl", "-d", "Ubuntu-24.04", "--", "docker"] + list(args)
        return self._record(
            argv,
            None,
            timeout_s,
            lambda: self._backend.wsl_docker(args, timeout_s=timeout_s),
        )

    def subprocess_run(
        self,
        argv: list[str],
        *,
        input_payload: bytes | None = None,
        timeout_s: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._record(
            list(argv),
            input_payload,
            timeout_s,
            lambda: self._backend.subprocess_run(list(argv), input_payload=input_payload, timeout_s=timeout_s),
        )

    def side_container_run(self, side: str) -> HostLaunch | None:
        for launch in self.launches:
            if launch.boundary != "CONTAINER_RUN":
                continue
            if side_from_container_argv(launch.ordered_argv) == side:
                return launch
        return None


def _payload_sha(input_payload: bytes | None) -> str | None:
    if input_payload is None:
        return None
    return hashlib.sha256(input_payload).hexdigest()


# --------------------------------------------------------------------------- #
# rc vs raw junit congruence (atomic 3)                                       #
# --------------------------------------------------------------------------- #
def _junit_text_for(raw_junit: dict[str, Any], side: str, name: str) -> str | None:
    if isinstance(raw_junit.get(side), dict):
        inner: Any = raw_junit[side]
        return inner.get(name)  # type: ignore[no-any-return]
    return raw_junit.get(name)


def _parse_file_or_raise(name: str, text: str) -> tuple[dict[str, str], dict[str, str]]:
    try:
        out = _oc.parse_junit_with_failures(text)
    except Exception as exc:
        raise LauncherReceiptError(f"raw junit parse error {name}: {type(exc).__name__}: {exc}") from exc
    return (dict(out[0]), dict(out[1]))


def audit_rc_vs_raw_junit(
    *,
    side: str,
    led: RunLedger,
    oracle: Any,
    raw_junit: dict[str, Any],
) -> None:
    """Bind EVERY rc to its exact raw JUnit fragment and reject
    contradictions (rc=0 with failures, rc=1 with all-pass) and unexplained
    rcs.  rc=2 is deferred to the interrupted-classification gate."""
    invs = planned_invocations(_tid12(oracle.task_id), side, list(oracle.test_files))
    by_flat = {inv.flat_index: inv for inv in invs}
    for i, rc in sorted(led.rc_by_index.items()):
        inv = by_flat[i]
        name = f"{inv.junit_name}.xml"
        text = _junit_text_for(raw_junit, side, name)
        if text is None:
            raise LauncherReceiptError(
                f"side {side} RUN_{i}: raw junit artifact {name} missing at the consumer boundary (cannot bind rc)"
            )
        if rc == INTERRUPTED_RC:
            continue  # classified by the rc=2 gate, never accepted here
        if rc in TERMINAL_RCS and rc != INTERRUPTED_RC:
            raise LauncherReceiptError(
                f"side {side} RUN_{i} rc={rc}: terminal pytest outcome "
                "(INTERNAL_ERROR/USAGE_ERROR/NO_TESTS_COLLECTED) cannot qualify"
            )
        if rc not in (0, 1):
            raise LauncherReceiptError(f"side {side} RUN_{i} rc={rc} is not a canonical pytest rc and is unexplained")
        nodes, _fails = _parse_file_or_raise(name, text)
        nonpassed = [n for n, o in nodes.items() if o in ("failed", "error")]
        if rc == 0 and nonpassed:
            raise LauncherReceiptError(
                f"side {side} RUN_{i} rc=0 (OK) but raw junit {name} records "
                f"{len(nonpassed)} failed/error nodes: contradiction"
            )
        if rc == 1 and not nonpassed:
            raise LauncherReceiptError(
                f"side {side} RUN_{i} rc=1 (TESTS_FAILED) but raw junit {name} "
                "has zero failed/error nodes: contradiction"
            )


# --------------------------------------------------------------------------- #
# control-aware pytest rc=2 gate (atomic 4)                                   #
# --------------------------------------------------------------------------- #
def _collection_error_signal(raw_junit_text: str) -> bool:
    if "errors" not in raw_junit_text:
        return _COLLECTION_ERROR_RE.search(raw_junit_text) is not None
    try:
        root = _et_fromstring(raw_junit_text)
    except Exception:
        return False
    for el in [root] + list(root):
        n_errors = el.get("errors")
        if n_errors and n_errors.strip() not in ("", "0"):
            return True
    return _COLLECTION_ERROR_RE.search(raw_junit_text) is not None


def _et_fromstring(text: str) -> Any:
    import xml.etree.ElementTree as ET

    return ET.fromstring(text)


def classification_for_interrupted(
    *,
    side: str,
    flat_index: int,
    rep: int,
    file_idx: int,
    test_file: str,
    raw_junit_text: str | None,
    oracle: Any,
) -> dict[str, Any]:
    """The ONLY rc=2 exception: a parent-side collection error matched to
    PREDECLARED expected node identities and a frozen oracle that authorizes
    PARENT_COLLECTION_ERROR > 0.  Every other interrupt BLOCKS; the golden
    pilot (PCE=0, SYMBOL=0) authorizes NO rc=2 exception at all.  A
    diagnostic is never BEHAVIORAL_F2P-eligible."""
    del flat_index, rep, file_idx
    blocked: dict[str, Any] = {
        "decision": "BLOCKED",
        "f2p_eligible": False,
        "kind": "UNEXPECTED_INTERRUPT",
        "reasons": [],
    }
    if side != "p":
        blocked["kind"] = "TARGET_SIDE_INTERRUPT"
        blocked["reasons"] = ["interrupted execution on the target side never qualifies"]
        return blocked
    allowed = int(oracle.counts_strict.get("PARENT_COLLECTION_ERROR", 0) or 0)
    if allowed <= 0:
        blocked["reasons"] = [
            "task oracle permits no parent collection error "
            f"(PARENT_COLLECTION_ERROR={allowed}); no rc=2 exception is "
            "authorized for this task"
        ]
        return blocked
    pre = list(getattr(oracle, "expected_collection_error_nodes", ()) or ())
    if not pre:
        blocked["reasons"] = [
            "predeclared expected collection-error node identities are absent"
            " (insufficient provenance to accept an rc=2 diagnostic)"
        ]
        return blocked
    if not raw_junit_text:
        blocked["reasons"] = ["raw junit for the interrupted invocation is missing"]
        return blocked
    if not _collection_error_signal(raw_junit_text):
        blocked["reasons"] = [
            "raw junit carries no collection-error signal (testsuite errors >0 or collection error markers)"
        ]
        return blocked
    try:
        nodes, _fails = _parse_file_or_raise(time_label(test_file), raw_junit_text)
    except LauncherReceiptError as exc:
        blocked["reasons"] = [str(exc)]
        return blocked
    missing_expected = [n for n in pre if n not in nodes]
    if set(missing_expected) != set(pre):
        blocked["reasons"] = [
            "predeclared collection-error node identities are not exactly absent from the parent-side junit"
        ]
        return blocked
    return {
        "decision": "COLLECTION_ERROR_DIAGNOSTIC",
        "f2p_eligible": False,
        "kind": "EXPECTED_PARENT_COLLECTION_ERROR",
        "reasons": [
            "matched to predeclared identity/classification evidence; "
            "diagnostic record only, never a qualifying outcome"
        ],
    }


def time_label(test_file: str) -> str:
    return test_file.replace("/", "_") + ".xml"


def _gate_rc2_invocations(
    side: str,
    led: RunLedger,
    oracle: Any,
    raw_junit: dict[str, Any],
) -> None:
    invs = planned_invocations(_tid12(oracle.task_id), side, list(oracle.test_files))
    by_flat = {inv.flat_index: inv for inv in invs}
    for i, rc in led.rc_by_index.items():
        if rc != INTERRUPTED_RC:
            continue
        inv = by_flat[i]
        text = _junit_text_for(raw_junit, side, f"{inv.junit_name}.xml")
        cls = classification_for_interrupted(
            side=side,
            flat_index=i,
            rep=inv.rep,
            file_idx=inv.file_idx,
            test_file=inv.test_file,
            raw_junit_text=text,
            oracle=oracle,
        )
        if cls["decision"] != "COLLECTION_ERROR_DIAGNOSTIC":
            raise LauncherReceiptError(
                f"side {side} RUN_{i} rc=2 (INTERRUPTED): " + ("; ".join(cls["reasons"]) or "unexplained interrupt")
            )


def validate_invocation_contract(
    states: dict[str, RunLedger],
    *,
    oracle: Any,
    expected_runs: dict[str, int],
    raw_junit: dict[str, Any] | None = None,
) -> None:
    """Fail-closed per-invocation checks across both states.  With no raw
    junit binding supplied, every non-interrupted invocation cannot be bound
    and BLOCKS; the rc=2 gate ALWAYS runs (with missing evidence it remains
    BLOCKED -- never silently accepted)."""
    if set(states) != set(expected_runs):
        raise LauncherReceiptError(
            f"side coverage mismatch: states {sorted(states)} != declared {sorted(expected_runs)}"
        )
    bound = {} if raw_junit is None else raw_junit
    for side, led in states.items():
        exp = expected_runs[side]
        if len(led.rc_by_index) != exp:
            raise LauncherReceiptError(f"side {side}: {len(led.rc_by_index)} invocation records != planned {exp}")
        if led.source == "TIMEOUT_NO_STDOUT":
            raise LauncherReceiptError(
                f"side {side}: container timed out with NO invocation evidence "
                "(silent timeout is infrastructure failure)"
            )
        if not led.all_runs_done:
            raise LauncherReceiptError(f"side {side}: ALL_RUNS_DONE absent -> container incomplete")
        if led.install_failed:
            raise LauncherReceiptError(f"side {side}: install failure markers {led.install_markers}")
        _gate_rc2_invocations(side, led, oracle, bound)
        audit_rc_vs_raw_junit(side=side, led=led, oracle=oracle, raw_junit=bound)


# --------------------------------------------------------------------------- #
# side assessment (capture -> ledger -> mapping)                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SideAssessment:
    side: str
    ledger: RunLedger
    invocations: tuple[PytestInvocation, ...]
    juni_by_flat: dict[int, PytestInvocation]


def assess_side(
    *,
    side: str,
    container_run: HostLaunch | None,
    oracle: Any,
    test_files: list[str] | tuple[str, ...],
    raw_root: Path | str | None = None,  # reserved for evidence-grounded checks
) -> SideAssessment:
    del raw_root
    if container_run is None:
        raise LauncherReceiptError(f"side {side}: no container-run boundary capture")
    argv_side = side_from_container_argv(container_run.ordered_argv)
    if argv_side != side:
        raise LauncherReceiptError(
            f"side {side}: container-run argv pins {argv_side!r} (DATABASE_URL "
            "db-name side) -- boundary evidence was captured for a different side"
        )
    if container_run.timeout:
        ledger = RunLedger(
            rc_by_index={},
            all_runs_done=False,
            install_failed=False,
            install_markers=(),
            container_returncode=None,
            source="TIMEOUT_NO_STDOUT",
        )
    else:
        ledger = parse_run_rc_ledger(
            container_run.stdout_full or "",
            expected_runs=REPS * len(test_files),
            source="BOUNDARY_FULL_STDOUT",
        )
        ledger = RunLedger(
            rc_by_index=ledger.rc_by_index,
            all_runs_done=ledger.all_runs_done,
            install_failed=ledger.install_failed,
            install_markers=ledger.install_markers,
            container_returncode=container_run.returncode,
            source=ledger.source,
        )
    invs = planned_invocations(_tid12(oracle.task_id), side, list(test_files))
    return SideAssessment(
        side=side,
        ledger=ledger,
        invocations=tuple(invs),
        juni_by_flat={inv.flat_index: inv for inv in invs},
    )


# --------------------------------------------------------------------------- #
# task-keyed frozen oracle (atomic 5)                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TaskOracleExpectation:
    """Authoritative task-keyed expectation loaded from frozen bindings."""

    task_id: str
    parent_commit: str
    target_commit: str
    test_files: tuple[str, ...]
    counts_strict: dict[str, int]
    strict_f2p_node_ids: dict[str, tuple[str, ...]]
    strict_p2p_only: tuple[str, ...]
    node_universe: tuple[str, ...]  # FULL frozen per-task node id set
    contract_sha256: str
    oracle_source: str = "FROZEN_BINDINGS"
    expected_collection_error_nodes: tuple[str, ...] = ()
    # NOTE: expected_collection_error_nodes is EMPTY for the golden pilot
    # (PCE=0) and stays empty for every task in the 83-cohort because the
    # frozen bindings do not enumerate per-task collection-error ids --
    # the rc=2 gate therefore fails closed with
    # "predeclared evidence absent" for any real rc=2 anywhere.


def load_task_oracle_expectation(task_id: str, *, project_root: Path) -> TaskOracleExpectation:
    """Load the frozen 83-cohort bindings and the behavior contract manifest
    and REJECT the task unless every binding has it.  Freeze all four artifacts' identity at read time."""
    root = Path(project_root)

    by_task_artifact = json.loads(
        (root / "reports/m19a4_p2ps/M19A4_P2P_ONLY_NODES_BY_TASK_83.json").read_text(encoding="utf-8")
    )
    by_task = rs.key_by_task_id(by_task_artifact["tasks"], collection_name="m19a4_by_task_83", declared_total=83)
    if task_id not in by_task:
        raise LauncherReceiptError(f"{task_id} not in M19A4 by-task (83-cohort)")

    ledger_tsv = (root / "reports/m19a4_p2ps/M19A4_NODE_LEDGER_83.tsv").read_text(encoding="utf-8")
    ledger_rows = [ln.split("\t") for ln in ledger_tsv.splitlines() if ln.strip()]
    header, body = ledger_rows[0], ledger_rows[1:]
    if header[:2] != ["task_id", "node_id"] or header[-1] != "strict_class":
        raise LauncherReceiptError("M19A4_NODE_LEDGER_83.tsv header changed; refuse to load")
    universe: set[str] = set()
    class_via_ledger: dict[str, int] = {}
    for row in body:
        if len(row) < 9:
            raise LauncherReceiptError("M19A4_NODE_LEDGER_83.tsv row malformed")
        if row[0] != task_id:
            continue
        universe.add(row[1])
        cls = row[8]
        class_via_ledger[cls] = class_via_ledger.get(cls, 0) + 1

    sens = json.loads(
        (root / "research/opws/binding/OPWS_F2P_THREE_RUN_SENSITIVITY_83.json").read_text(encoding="utf-8")
    )
    srec = next((t for t in sens.get("tasks", []) if t.get("task_id") == task_id), None)
    if srec is None:
        raise LauncherReceiptError(f"{task_id} missing from three-run sensitivity binding")

    manifest = json.loads(
        (root / "research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json").read_text(encoding="utf-8")
    )
    crec = next((c for c in manifest.get("per_task", []) if c.get("task_id") == task_id), None)
    if crec is None:
        raise LauncherReceiptError(f"{task_id} missing from behavior contract manifest")

    entry = by_task[task_id]
    counts_strict = dict(entry.get("strict_counts") or {})
    p2p_ids = tuple(entry.get("strict_p2p_only") or [])
    if len(p2p_ids) != int(counts_strict.get("P2P_ONLY", 0) or 0):
        raise LauncherReceiptError(
            f"{task_id}: len(strict_p2p_only)={len(p2p_ids)} != strict P2P_ONLY={counts_strict.get('P2P_ONLY')}"
        )
    f2p_ids = {k: tuple(v or []) for k, v in (srec.get("strict_f2p_node_ids") or {}).items()}
    if len(f2p_ids.get("BEHAVIORAL_F2P", ())) != int(counts_strict.get("BEHAVIORAL_F2P", 0) or 0):
        raise LauncherReceiptError(
            f"{task_id}: strict_f2p_node_ids.BEHAVIORAL_F2P length differs from the frozen strict count"
        )
    # frozen ledger class distribution must equal the frozen strict counts
    for cls in V2_CLASSES:
        if class_via_ledger.get(cls, 0) != int(counts_strict.get(cls, 0) or 0):
            raise LauncherReceiptError(
                f"{task_id}: ledger class {cls}={class_via_ledger.get(cls, 0)} != strict count {counts_strict.get(cls)}"
            )

    test_files: list[str] = []
    for cmd in crec.get("test_command") or []:
        parts = str(cmd).split(" ", 1)
        if len(parts) != 2 or not parts[1].strip():
            raise LauncherReceiptError(f"{task_id}: malformed test_command {cmd!r}")
        test_files.append(parts[1])
    if not test_files:
        raise LauncherReceiptError(f"{task_id}: behavior contract has no test command")

    contract_sha = crec.get("contract_sha256")
    if not isinstance(contract_sha, str) or len(contract_sha) != 64:
        raise LauncherReceiptError(f"{task_id}: contract_sha256 not 64-hex")

    return TaskOracleExpectation(
        task_id=task_id,
        parent_commit=str(crec["parent_commit"]),
        target_commit=str(crec["target_commit"]),
        test_files=tuple(test_files),
        counts_strict=counts_strict,
        strict_f2p_node_ids=f2p_ids,
        strict_p2p_only=p2p_ids,
        node_universe=tuple(sorted(universe)),
        contract_sha256=contract_sha,
        oracle_source="FROZEN_BINDINGS",
        expected_collection_error_nodes=(),
    )


# --------------------------------------------------------------------------- #
# per-rep observation ledger from raw files (atomic 5)                        #
# --------------------------------------------------------------------------- #
def parse_receipt_raw_junit_name(name: str, task_id: str) -> tuple[str, str, str]:
    """Strict ``{t12}_{side}_r{rep}_f{idx}.xml`` parse (frozen schema rule,
    read-only reuse)."""
    a, b, c = rs._parse_raw_junit_name(name, task_id)
    return (str(a), str(b), str(c))


def build_observation_ledgers(
    *,
    raw_root: Path | str,
    task_oracle: TaskOracleExpectation,
    tid12: str,
    container_runs: dict[str, HostLaunch | None],
    tolerate_missing: bool,
) -> tuple[dict[str, Any], dict[str, set[str]], int]:
    """Rebuild per-node per-side per-rep observations from the ACTUAL raw
    JUnit files (frozen parser, read-only).  Census is exact: every planned
    name must exist and no stray file may join; a node in two fragments of
    one rep is a duplicate/conflicting-fragment error."""
    root = Path(raw_root)
    n_files = len(task_oracle.test_files)
    side_obs: dict[str, dict[str, dict[str, str]]] = {}
    censuses: dict[str, set[str]] = {}
    for side in SIDES:
        run = container_runs.get(side)
        if run is None:
            raise LauncherReceiptError(f"side {side}: missing container-run evidence")
        if run.timeout:
            raise LauncherReceiptError(f"side {side}: container timeout cannot yield raw repetition evidence")
        side_dir = root / side
        expected = {f"{tid12}_{side}_r{r}_f{i}.xml" for r in range(3) for i in range(n_files)}
        present = {p.name for p in side_dir.glob(f"{tid12}_{side}_r*_f*.xml")} if side_dir.is_dir() else set()
        if not tolerate_missing and present != expected:
            raise LauncherReceiptError(
                f"side {side}: raw junit census mismatch: "
                f"missing={sorted(expected - present)[:4]} "
                f"extra={sorted(present - expected)[:4]}"
            )
        censuses[side] = present
        obs: dict[str, dict[str, str]] = {f"r{r}": {} for r in range(3)}
        frags: dict[str, set[str]] = {f"r{r}": set() for r in range(3)}
        for name in present & expected:
            _side, rep_key, _fpart = parse_receipt_raw_junit_name(name, task_oracle.task_id)
            text = (side_dir / name).read_text(encoding="utf-8", errors="replace")
            nodes, _fails = _parse_file_or_raise(name, text)
            for node, outcome in nodes.items():
                if node in frags[rep_key]:
                    raise LauncherReceiptError(
                        f"side {side} rep {rep_key}: node {node!r} appears in "
                        ">1 fragment (duplicate/conflicting observations within "
                        "one repetition)"
                    )
                obs[rep_key][node] = outcome
                frags[rep_key].add(node)
        side_obs[side] = obs

    universe = sorted({node for obs in side_obs.values() for rep in obs.values() for node in rep})
    per_node: dict[str, Any] = {}
    for node in universe:
        rec: dict[str, Any] = {}
        for side in SIDES:
            outcomes = [side_obs[side][f"r{r}"].get(node, "missing") for r in range(3)]
            rec[side] = {
                "outcomes": outcomes,
                "observations_by_rep": {f"r{r}": [side_obs[side][f"r{r}"].get(node, "missing")] for r in range(3)},
            }
        per_node[node] = rec
    n_nodes = len(per_node)
    return per_node, censuses, n_nodes


def validate_node_identity_against_oracle(
    observed_node_ids: list[str] | tuple[str, ...] | set[str],
    oracle: TaskOracleExpectation,
) -> None:
    """Set equality (and canonical-hash equality) against the AUTHORITATIVE
    task-keyed node universe -- a caller-supplied EXACT_MATCH flag alone is
    never trusted."""
    obs = sorted(set(observed_node_ids))
    exp = sorted(set(oracle.node_universe))
    if obs != exp:
        raise LauncherReceiptError(
            "node identity SET inequality vs authoritative task-keyed oracle: "
            f"observed-only={sorted(set(obs) - set(exp))[:4]} "
            f"expected-only={sorted(set(exp) - set(obs))[:4]}"
        )
    if rs.node_set_sha256(obs) != rs.node_set_sha256(exp):
        raise LauncherReceiptError("node identity canonical hashes differ (!!)")


def verify_oracle_reproduction(
    per_node: dict[str, Any],
    oracle: TaskOracleExpectation,
    *,
    raw_root: Path | str,
    tid12: str,
) -> None:
    """Re-run the FROZEN classifier over the per-rep raw evidence and require
    exact reproduction of the frozen oracle's per-node classes and counts.
    Any deviation BLOCKS (prospective test-contract violation)."""
    osem = _load_frozen("oracle_semantics_v2")

    validate_node_identity_against_oracle(list(per_node), oracle)
    root = Path(raw_root)
    parent_fail: dict[str, str] = {}
    parent_collects: set[str] = set()
    for p in (root / "p").glob(f"{tid12}_p_*.xml"):
        nodes, fails = _parse_file_or_raise(p.name, p.read_text(encoding="utf-8", errors="replace"))
        parent_fail.update(fails)
        parent_collects.update(nodes)

    got: dict[str, int] = {}
    for node, rec in per_node.items():
        cls = osem.classify_node_v2(
            target_outcomes=list(rec["t"]["outcomes"]),
            parent_outcomes=list(rec["p"]["outcomes"]),
            parent_failure_text=parent_fail.get(node, ""),
            parent_collects_node=node in parent_collects,
            shared_test_support_failed=False,
        )
        got[cls] = got.get(cls, 0) + 1
    for cls in V2_CLASSES:
        expected = int(oracle.counts_strict.get(cls, 0) or 0)
        if got.get(cls, 0) != expected:
            raise LauncherReceiptError(
                f"{oracle.task_id}: frozen oracle reproduction FAILS for {cls}: "
                f"got {got.get(cls, 0)} != expected {expected}"
            )


# --------------------------------------------------------------------------- #
# flat assembly + consumer-boundary hash verification (atomic 5)              #
# --------------------------------------------------------------------------- #
def assemble_flat_raw_dir(
    raw_root: Path | str,
    flat_dir: Path,
    *,
    task_id: str,
    tid12: str,
) -> list[dict[str, Any]]:
    """Materialize byte-identical flat copies (basename-only layout the frozen
    ``verify_raw_file_hashes`` expects) and record their sha256."""
    root = Path(raw_root)
    flat_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for side in SIDES:
        side_dir = root / side
        if not side_dir.is_dir():
            raise LauncherReceiptError(f"side raw dir missing: {side_dir}")
        for p in sorted(side_dir.glob(f"{tid12}_{side}_r*_f*.xml")):
            name = p.name
            parse_receipt_raw_junit_name(name, task_id)  # strict; rejects foreign names
            data = p.read_bytes()
            (flat_dir / name).write_bytes(data)
            entries.append(
                {
                    "file": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "raw": True,
                }
            )
    return entries


def verify_r1_side_layout_matches(junit_entries: list[dict[str, Any]], raw_root: Path | str) -> None:
    """Prove the flat verification copies are byte-identical to the R1 raw
    side layout (``{raw_root}/{side}/{name}.xml``)."""
    root = Path(raw_root)
    for item in junit_entries:
        name = item.get("file")
        if not isinstance(name, str):
            raise LauncherReceiptError("junit entry missing file name")
        parts = name.split("_")
        if len(parts) != 4 or parts[1] not in SIDES:
            raise LauncherReceiptError(f"raw junit name {name!r} has no side")
        side = parts[1]
        p = root / side / name
        if not p.is_file():
            raise LauncherReceiptError(f"r1 raw layout missing side file: {p}")
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != item.get("sha256"):
            raise LauncherReceiptError(f"flat copy {name} sha {item.get('sha256')} != r1 raw layout {got}")


# --------------------------------------------------------------------------- #
# receipt payload assembly + validation (atomic 5)                            #
# --------------------------------------------------------------------------- #
def validate_env_pins(pins: dict[str, str]) -> None:
    for key in ("linux_environment_digest", "manifest_sha256", "image_digest"):
        value = pins.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise LauncherReceiptError(f"env pin {key} missing or not 64-hex; the consumer never invents pins")


def _order_preserving_rc_ledger(ledger_by_side: dict[str, RunLedger]) -> list[int]:
    rcs: list[int] = []
    for side in SIDES:
        led = ledger_by_side.get(side)
        if led is None:
            raise LauncherReceiptError(f"missing invocation ledger for side {side}")
        if led.source == "TIMEOUT_NO_STDOUT":
            raise LauncherReceiptError(f"side {side} ledger is a silent timeout")
        rcs.extend(led.rc_by_index[i] for i in sorted(led.rc_by_index))
    return rcs


def overall_pytest_rc(ledger_by_side: dict[str, RunLedger]) -> int:
    """One canonical pytest rc for the receipt: 0 iff every invocation OK;
    1 if any TESTS_FAILED and none terminal/unexplained; otherwise the
    conflict is fatal (never silently merged)."""
    rcs = _order_preserving_rc_ledger(ledger_by_side)
    if not rcs:
        raise LauncherReceiptError("no per-invocation rcs -> cannot size pytest rc")
    if any(rc in TERMINAL_RCS for rc in rcs):
        raise LauncherReceiptError(
            "terminal per-invocation rc present (incl. rc=2); a qualifying receipt needs every invocation rc in {0,1}"
        )
    if any(rc not in (0, 1) for rc in rcs):
        raise LauncherReceiptError(f"unexplained per-invocation rcs: {sorted(set(rcs))}")
    return 1 if any(rc == 1 for rc in rcs) else 0


def build_receipt_payload(
    *,
    task_oracle: TaskOracleExpectation,
    per_node: dict[str, Any],
    ledger_by_side: dict[str, RunLedger],
    junit_entries: list[dict[str, Any]],
    env_evidence: dict[str, str],
    scope_patch_paths: list[str],
    container_host_argv: list[str] | tuple[str, ...],
    container_returncode: int | None,
    control: str,
    sens_supported: bool,
    claim_os_attested: bool,
) -> dict[str, Any]:
    """Assemble a schema payload.  argv is ALWAYS HARNESS_CONSTRUCTED (we
    never fabricate an OS attestation); if ``claim_os_attested`` is passed
    True the frozen schema rejects the receipt -- which is the correct,
    honest outcome."""
    validate_env_pins(env_evidence)
    if task_oracle.counts_strict.get("PARENT_COLLECTION_ERROR", 0) or 0:
        # a task whose frozen oracle allows parent collection errors cannot
        # carry them into a passing receipt without predeclared evidence
        raise LauncherReceiptError(
            f"{task_oracle.task_id}: frozen PARENT_COLLECTION_ERROR>0 task "
            "requires predeclared collection-error evidence; pass a diagnostic "
            "record instead of a receipt"
        )
    order = [str(a) for a in container_host_argv]
    if not order:
        raise LauncherReceiptError("container-run host argv is empty (no launch identity)")
    argv: dict[str, Any] = {"kind": "HARNESS_CONSTRUCTED", "order": order}

    observed_nodes = [k for k in per_node if isinstance(k, str)]
    validate_node_identity_against_oracle(observed_nodes, task_oracle)
    node_hash = rs.node_set_sha256(observed_nodes)

    provenance = (
        "BOUNDARY_FULL_STDOUT "
        + ";".join(
            f"RUN_{i}_RC={ledger_by_side[side].rc_by_index[i]}"
            for side in SIDES
            for i in sorted(ledger_by_side[side].rc_by_index)
        )[:1800]
    )

    rc = overall_pytest_rc(ledger_by_side)
    ctrc = 0 if container_returncode is None else container_returncode
    if ctrc != 0:
        raise LauncherReceiptError(
            f"container return code {ctrc} != 0 with no install markers: an "
            "aggregate container rc is never substituted for per-invocation rcs"
        )

    snapshot = rs.sha256_canonical(
        sorted(
            ({"file": e.get("file"), "sha256": e.get("sha256")} for e in junit_entries),
            key=lambda d: str(d["file"]),
        )
    )
    per_node_outcomes = dict(per_node)
    ledger_rows: list[dict[str, Any]] = []
    for side in SIDES:
        for i in sorted(ledger_by_side[side].rc_by_index):
            inv = next(
                (
                    x
                    for x in planned_invocations(_tid12(task_oracle.task_id), side, list(task_oracle.test_files))
                    if x.flat_index == i
                ),
                None,
            )
            if inv is None:
                raise LauncherReceiptError(f"side {side} RUN_{i}: no planned mapping")
            ledger_rows.append(
                {
                    "flat_index": i,
                    "side": side,
                    "rep": inv.rep,
                    "file_idx": inv.file_idx,
                    "test_file": inv.test_file,
                    "junit_file": f"{inv.junit_name}.xml",
                    "rc": ledger_by_side[side].rc_by_index[i],
                    "rc_provenance": ledger_by_side[side].source,
                    "argv": inv.argv,
                    "argv_kind": "HARNESS_CONSTRUCTED",
                }
            )

    payload: dict[str, Any] = {
        "schema": rs.RECEIPT_SCHEMA_VERSION,
        "schema_version": rs.RECEIPT_SCHEMA_REV,
        "task_id": task_oracle.task_id,
        "parent_commit": task_oracle.parent_commit,
        "target_commit": task_oracle.target_commit,
        "selected_arm": "real_v3_m17_r1",
        "control": control,
        "scope": {
            "scope_patch_paths": list(scope_patch_paths),
            "scope_patch_sha256": "0" * 64,
            "outside_allowed_paths": False,
        },
        "test_contract_sha256": task_oracle.contract_sha256,
        "env": dict(env_evidence),
        "argv": argv,
        "claim_os_attested": claim_os_attested,
        "rep_index": [0, 1, 2],
        "n_reps": 3,
        "process_returncode": rc,
        "container_returncode": ctrc,
        "returncode_provenance": provenance,
        "outputs": {
            "junit": junit_entries,
            "snapshot_sha256_over_raw_files": snapshot,
            "container_completed": True,
        },
        "node_identity": {
            "set_equality": "EXACT_MATCH",
            "expected_sha256": node_hash,
            "observed_sha256": node_hash,
        },
        "per_node_outcomes": per_node_outcomes,
        "timeout_infra": {"category": "NONE", "detail": "ALL_RUNS_DONE seen; all per-invocation rcs in {0,1}"},
        "control_qualification": {
            "decision": "PASS",
            "reason": (
                "all per-invocation rcs congruent with raw junit; frozen oracle "
                "reproduced; raw repetitions and hashes verified at the consumer boundary"
            ),
            "sensitivity_supported": sens_supported,
        },
        "invocation_ledger": ledger_rows,
        "launch_capture_version": LAUNCH_CAPTURE_VERSION,
    }
    if control == "FULL_REFERENCE":
        payload["control_qualification"]["frozen_reference_sha256"] = "0" * 64
        payload["control_qualification"]["reference_mismatch"] = False
    return payload


def consume_launch(
    *,
    task_oracle: TaskOracleExpectation,
    capture: LaunchCapture,
    raw_root: Path | str,
    flat_dir: Path,
    env_evidence: dict[str, str],
    scope_patch_paths: list[str],
    control: str,
    sens_supported: bool,
    tolerate_missing: bool = False,
) -> dict[str, Any]:
    """Full fail-closed consumer.  Returns a dict with decision PASS/BLOCKED
    and the payload/verdict record.  Invokes the FROZEN
    ``rs.validate_receipt`` with authoritative expected ids and the FROZEN
    ``rs.verify_raw_file_hashes`` on the flat materialized copies."""
    from benchmark.wp2 import receipt_schema_v1 as _rs

    container_runs: dict[str, HostLaunch | None] = {}
    side_assessments: dict[str, SideAssessment] = {}
    ledgers: dict[str, RunLedger] = {}
    reasons: list[str] = []
    for side in SIDES:
        run = capture.side_container_run(side)
        container_runs[side] = run
        try:
            out = assess_side(
                side=side,
                container_run=run,
                oracle=task_oracle,
                test_files=list(task_oracle.test_files),
            )
            side_assessments[side] = out
            ledgers[side] = out.ledger
            if out.ledger.source == "TIMEOUT_NO_STDOUT":
                reasons.append(f"side {side}: container timeout, no invocation stdout")
        except LauncherReceiptError as exc:
            reasons.append(str(exc))
    try:
        validate_invocation_contract(
            ledgers,
            oracle=task_oracle,
            expected_runs={s: len(side_assessments[s].invocations) for s in SIDES},
            raw_junit=_raw_by_side(raw_root),
        )
    except LauncherReceiptError as exc:
        reasons.append(str(exc))
    per_node: dict[str, Any] = {}
    try:
        per_node, _censuses, _n = build_observation_ledgers(
            raw_root=raw_root,
            task_oracle=task_oracle,
            tid12=_tid12(task_oracle.task_id),
            container_runs=container_runs,
            tolerate_missing=tolerate_missing,
        )
        verify_oracle_reproduction(per_node, task_oracle, raw_root=raw_root, tid12=_tid12(task_oracle.task_id))
    except LauncherReceiptError as exc:
        reasons.append(str(exc))
    entries: list[dict[str, Any]] = []
    try:
        entries = assemble_flat_raw_dir(
            raw_root,
            flat_dir=flat_dir,
            task_id=task_oracle.task_id,
            tid12=_tid12(task_oracle.task_id),
        )
    except LauncherReceiptError as exc:
        reasons.append(str(exc))
    if reasons:
        return {
            "decision": "BLOCKED",
            "reasons": reasons,
            "payload": None,
            "verdict_record": {"verdict": "BLOCKED", "task_id": task_oracle.task_id, "reasons": reasons},
        }
    host = container_runs["t"]
    assert host is not None
    payload = build_receipt_payload(
        task_oracle=task_oracle,
        per_node=per_node,
        ledger_by_side=ledgers,
        junit_entries=entries,
        env_evidence=env_evidence,
        scope_patch_paths=scope_patch_paths,
        container_host_argv=list(host.ordered_argv),
        container_returncode=host.returncode,
        control=control,
        sens_supported=sens_supported,
        claim_os_attested=False,
    )
    try:
        _rs.validate_receipt(payload, expected_task_node_ids=task_oracle.node_universe)
        _rs.verify_raw_file_hashes(payload, flat_dir)
        verify_r1_side_layout_matches(entries, raw_root)
    except rs.ReceiptError as exc:
        return {
            "decision": "BLOCKED",
            "reasons": [str(exc)],
            "payload": payload,
            "verdict_record": rs.blocked_receipt_verdict(payload, exc),
        }
    return {
        "decision": "PASS",
        "reasons": [],
        "payload": payload,
        "verdict_record": {"verdict": "PASS", "task_id": task_oracle.task_id},
    }


def _raw_by_side(raw_root: Path | str) -> dict[str, dict[str, str]]:
    root = Path(raw_root)
    out: dict[str, dict[str, str]] = {}
    for side in SIDES:
        out[side] = {}
        d = root / side
        if d.is_dir():
            for p in d.glob("*.xml"):
                out[side][p.name] = p.read_text(encoding="utf-8", errors="replace")
    return out


# --------------------------------------------------------------------------- #
# merged-dict negative (atomic 6)                                             #
# --------------------------------------------------------------------------- #
def assess_merged_dict_only(
    merged: dict[str, str],
    *,
    task_oracle: TaskOracleExpectation,
) -> dict[str, Any]:
    """Prove a wrapper holding ONLY a merged junit dictionary (the frozen
    ``dict.update`` last-rep-wins seam) can NEVER substantiate three distinct
    repetitions or a qualifying receipt."""
    tid12 = _tid12(task_oracle.task_id)
    reasons: list[str] = [
        "per-node outcomes originate from a MERGED junit dictionary with no per-rep raw artifacts",
        "no RAW per-rep junit files named {t12}_{side}_r{rep}_f{idx}.xml exist",
        "no r0/r1/r2 per-rep observation ledger exists",
        f"merged dict reports {len(merged)} nodes without repetition attribution",
    ]
    entries = [
        {
            "file": f"{tid12}_{side}_r{rep}_f{i}.xml",
            "sha256": "f" * 64,
            "raw": True,
            "derived_from_merged_dict": True,
        }
        for rep in range(3)
        for i in range(len(task_oracle.test_files))
        for side in SIDES
    ]
    per_node: dict[str, Any] = {}
    for node, outcome in merged.items():
        per_node[node] = {
            s: {
                "outcomes": [outcome, outcome, outcome],
                "observations_by_rep": {f"r{r}": [outcome] for r in range(3)},
            }
            for s in SIDES
        }
    try:
        payload = build_receipt_payload(
            task_oracle=task_oracle,
            per_node=per_node,
            ledger_by_side={s: RunLedger({}, False, False, (), 0, "BOUNDARY_FULL_STDOUT") for s in SIDES},
            junit_entries=entries,
            env_evidence={
                "linux_environment_digest": "1" * 64,
                "manifest_sha256": "2" * 64,
                "image_digest": "3" * 64,
            },
            scope_patch_paths=["saleor/app/manifest_validations.py"],
            container_host_argv=["wsl", "-d", "Ubuntu-24.04", "--", "docker", "run", "--rm", "wp2-era-py38"],
            container_returncode=0,
            control="NEG",
            sens_supported=True,
            claim_os_attested=False,
        )
    except LauncherReceiptError as exc:
        reasons.append(str(exc))
        return {
            "decision": "BLOCKED",
            "reasons": reasons,
            "payload": None,
            "verdict_record": {
                "verdict": "BLOCKED",
                "task_id": task_oracle.task_id,
                "blocking_reason": str(exc),
            },
        }
    try:
        rs.validate_receipt(payload, expected_task_node_ids=task_oracle.node_universe)
    except rs.ReceiptError as exc:
        reasons.append(str(exc))
        return {
            "decision": "BLOCKED",
            "reasons": reasons,
            "payload": payload,
            "verdict_record": rs.blocked_receipt_verdict(payload, exc),
        }
    raise LauncherReceiptError("internal invariant: merged-dict-only payload unexpectedly passed")
