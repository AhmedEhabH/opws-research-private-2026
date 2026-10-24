"""M19B-R2 -- RED/GREEN synthetic tests for the launcher-run capture + receipt consumer.

OFFLINE and SYNTHETIC ONLY: fake subprocess backends and generated JUnit XML.
No Saleor, Docker, WSL, network or model.  Frozen source (harness_v3,
wp2_m16_r1, receipt_schema_v1, oracle_semantics_v2, oracle_confirmation) is
imported READ-ONLY and never modified.

Coverage demanded by the mission:
  * correct invocation mapping (frozen rep-major flat numbering RUN_i_RC)
  * duplicate/missing/extra/out-of-order RC records -> BLOCKED
  * no ALL_RUNS_DONE -> infra BLOCKED
  * installation markers (INSTALL_MAIN_FAIL / INSTALL_DEV_FAIL / TOOLING_FAIL)
  * container timeout -> BLOCKED with diagnostic
  * control-aware pytest RC=2 gate: golden pilot (PARENT_COLLECTION_ERROR=0,
    SYMBOL_ABSENCE_F2P=0) BLOCKS every RC=2; an expected parent-side
    collection error is DIAGNOSTIC ONLY, never BEHAVIORAL_F2P eligibility
  * mismatched invocation counts, wrong side, missing repetition, swapped
    node identity, corrupt raw XML, mismatched hash
  * negative integration: a wrapper holding only a MERGED junit dictionary
    cannot claim successful qualification
  * launch capture preserves ordered argv per subprocess boundary and labels
    evidence HARNESS_CONSTRUCTED (never OS_ATTESTED)
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src" / "benchmark" / "wp2") not in sys.path:
    sys.path.insert(0, str(ROOT / "src" / "benchmark" / "wp2"))

import launcher_receipt_v1 as lr  # noqa: E402  # M19B-R2 additive adapter
import receipt_schema_v1 as rs  # noqa: E402  # frozen additive schema (read-only)

TASK = "saleor-rc-7e42fc67ce72"
TID12 = "7e42fc67ce72"
PARENT = "798632158394c9f2911e6d36e8e424fd55007dc4"
TARGET = "7e42fc67ce72770720440781fc83685a48bd91b8"
# Frozen behavior-contract manifest test_command files (4) for the golden pilot.
PILOT_TEST_FILES = [
    "saleor/app/tests/test_app_commands.py",
    "saleor/app/tests/test_installation_utils.py",
    "saleor/app/tests/test_validators.py",
    "saleor/graphql/app/tests/mutations/test_app_fetch_manifest.py",
]
PILOT_CONTRACT_SHA = "ddb6e5401178f2af766b490477186e2cc4f295f413316b898754342a7a7cf279"
WT_NAME = "7e42fc67ce72_v3_t"

P2P_A = "saleor/app/tests/test_app_commands.py::test_app_has_all_required_permissions"
P2P_B = "saleor/app/tests/test_installation_utils.py::test_install_app_created_app"
BEH_C = "saleor/app/tests/test_validators.py::test_new_tab_relative_url_without_app_url"
INV_D = "saleor/graphql/app/tests/mutations/test_app_fetch_manifest.py::test_app_fetch_manifest"

TINY_FILES = [
    "saleor/app/tests/test_app_commands.py",
    "saleor/app/tests/test_installation_utils.py",
]
# (file idx, file, node, t_outcomes, p_outcomes, expected_class)
TINY_NODE_PLAN: list[tuple[int, str, str, list[str], list[str], str]] = [
    (0, TINY_FILES[0], P2P_A, ["passed", "passed", "passed"], ["passed", "passed", "passed"], "P2P_ONLY"),
    (1, TINY_FILES[1], P2P_B, ["passed", "passed", "passed"], ["passed", "passed", "passed"], "P2P_ONLY"),
    (0, TINY_FILES[0], BEH_C, ["passed", "passed", "passed"], ["failed", "failed", "failed"], "BEHAVIORAL_F2P"),
    (1, TINY_FILES[1], INV_D, ["failed", "failed", "failed"], ["passed", "passed", "passed"], "TARGET_ORACLE_INVALID"),
]
TINY_COUNTS = {
    "BEHAVIORAL_F2P": 1,
    "SYMBOL_ABSENCE_F2P": 0,
    "PARENT_COLLECTION_ERROR": 0,
    "FLAKY": 0,
    "TARGET_ORACLE_INVALID": 1,
    "P2P_ONLY": 2,
    "OTHER_REVIEW_REQUIRED": 0,
}


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _sh(*args: str) -> str:
    return " ".join(repr(a) for a in args)


def _junit_xml(nodes: list[tuple[str, str]]) -> str:
    """nodes: (node_id, kind) kind in passed/failed/error."""
    cases = []
    for node_id, kind in nodes:
        fname, name = node_id.split("::", 1)
        if kind == "failed":
            inner = "<failure message='boom'>Traceback\nassert 1 == 2</failure>"
        elif kind == "error":
            inner = "<error message='err'>RuntimeError: boom</error>"
        else:
            inner = ""
        cases.append(f'<testcase file="{fname}" name="{name}">{inner}</testcase>')
    return f'<?xml version="1.0"?><testsuite>{"".join(cases)}</testsuite>'


def _collection_error_junit() -> str:
    """A junit that signals a parent-side collection error (tests=0 errors>0)."""
    return (
        '<?xml version="1.0"?><testsuite errors="1" tests="0">'
        "<testcase name='test_collection'>"
        "<error message='ERROR: couldn&#x27;t collect test_x'/>"
        "</testcase></testsuite>"
    )


def _rc_stdout(rc_by_index: dict[int, int], *, all_done: bool = True, markers: tuple[str, ...] = ()) -> str:
    lines = list(markers)
    for i in sorted(rc_by_index):
        lines.append(f"RUN_{i}_RC={rc_by_index[i]}")
    if all_done:
        lines.append("ALL_RUNS_DONE")
    return "\n".join(lines) + "\n"


def _tiny_oracle(with_contract_sha: bool = True) -> lr.TaskOracleExpectation:
    node_ids = [n for _, _, n, _, _, _ in TINY_NODE_PLAN]
    return lr.TaskOracleExpectation(
        task_id=TASK,
        parent_commit=PARENT,
        target_commit=TARGET,
        test_files=tuple(TINY_FILES),
        counts_strict=dict(TINY_COUNTS),
        strict_f2p_node_ids={"BEHAVIORAL_F2P": (BEH_C,), "SYMBOL_ABSENCE_F2P": ()},
        strict_p2p_only=(P2P_A, P2P_B),
        node_universe=tuple(sorted(node_ids)),
        contract_sha256=PILOT_CONTRACT_SHA if with_contract_sha else "c" * 64,
        oracle_source="SYNTHETIC_TEST",
    )


def _container_argv(side: str, db: str | None = None) -> list[str]:
    """FOLLOWS the frozen wsl_docker contract: without the leading 'docker'
    (wsl_docker prepends 'wsl -d <distro> -- docker')."""
    db = db or f"saleor_v3_{TID12}_{side}"
    return [
        "run",
        "--rm",
        "--network",
        "host",
        "--ulimit",
        "nofile=65536:65536",
        "-e",
        f"DATABASE_URL=postgres://saleor:saleor@127.0.0.1:5433/{db}",
        "-e",
        "CACHE_URL=locmem://",
        "-v",
        f"/opt/wp2_v2/worktrees/{TID12}_v3_{side}:/workspace/{TID12}_v3_{side}",
        "-v",
        "wp2-uv-cache:/root/.cache/uv",
        "wp2-era-py38",
        "bash",
        f"/workspace/{TID12}_v3_{side}/.install.sh",
    ]


def _write_raw_tree(root: Path) -> dict[str, str]:
    """Write raw_root/{side}/{name}.xml for the tiny plan; return name->sha256."""
    hashes: dict[str, str] = {}
    for rep in range(3):
        for fidx in (0, 1):
            t_nodes = [
                (n, "failed" if not all(o == "passed" for o in t_out) else "passed")
                for (f_, _tf, n, t_out, _p_, _c) in TINY_NODE_PLAN
                if f_ == fidx
            ]
            p_nodes = [
                (n, "failed" if not all(o == "passed" for o in p_out) else "passed")
                for (f_, _tf, n, _t_, p_out, _c) in TINY_NODE_PLAN
                if f_ == fidx
            ]
            for side, nodes in (("t", t_nodes), ("p", p_nodes)):
                name = f"{TID12}_{side}_r{rep}_f{fidx}.xml"
                d = root / side
                d.mkdir(parents=True, exist_ok=True)
                xml_bytes = _junit_xml(nodes).encode("utf-8")
                (d / name).write_bytes(xml_bytes)
                hashes[f"{side}/{name}"] = hashlib.sha256(xml_bytes).hexdigest()
    return hashes


def _tiny_per_node() -> dict[str, Any]:
    """Per-node observation ledger matching TINY_NODE_PLAN (3 reps each side)."""
    per_node: dict[str, Any] = {}
    for _f0, _tf, node, t_out, p_out, _c in TINY_NODE_PLAN:
        per_node[node] = {
            "t": {
                "outcomes": list(t_out),
                "observations_by_rep": {f"r{r}": [t_out[r]] for r in range(3)},
            },
            "p": {
                "outcomes": list(p_out),
                "observations_by_rep": {f"r{r}": [p_out[r]] for r in range(3)},
            },
        }
    return per_node


def _six_flat_junit(side: str, nodes: list[tuple[str, str]]) -> dict[str, str]:
    """{name: xml} for 3 reps x 2 files of one side."""
    xml = _junit_xml(nodes)
    return {f"{TID12}_{side}_r{r}_f{i}.xml": xml for r in range(3) for i in (0, 1)}


def _side_content_plan() -> dict[str, list[int]]:
    """Per side: per-rep-file rc matrix [i0..i5] (rep-major, 2 files x 3 reps).

    Target: f0 (P2P_A passed + BEH_C passed) ok; f1 (INV_D FAILS at target) rc=1.
    Parent: f0 (BEH_C FAILS at parent -- that IS the behavioral F2P) rc=1;
    f1 (P2P_B + INV_D passed) ok."""
    t = [0 if fidx == 0 else 1 for _rep in range(3) for fidx in (0, 1)]
    p = [1 if fidx == 0 else 0 for _rep in range(3) for fidx in (0, 1)]
    return {"t": t, "p": p}


@dataclass
class FakeBackend:
    """Injectable runner: scripts replies by launch kind; records every launch."""

    replies: dict[str, Any]
    calls: list[tuple[tuple[str, ...], bytes | None]] = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    @staticmethod
    def _kind(argv: list[str]) -> str:
        if "docker" in argv[:5]:
            sub = argv[argv.index("docker") + 1 :]
            if sub and sub[0] == "run":
                return "CONTAINER"
            if sub and sub[0] == "exec":
                return "DB"
            if sub and sub[0] == "image":
                return "IMAGE"
            return "DOCKER_OTHER"
        joined = " ".join(argv)
        if ".wp2_runs.sh" in joined:
            return "RUNS_SCRIPT"
        if ".install.sh" in joined:
            return "INSTALL_SCRIPT"
        if "git" in joined:
            return "GIT"
        return "OTHER"

    def _run(
        self, argv: list[str], input_payload: bytes | None, timeout_s: int | None
    ) -> subprocess.CompletedProcess[str]:
        kind = self._kind(argv)
        self.calls.append((argv, input_payload))
        if kind not in self.replies:
            raise AssertionError(f"unprogrammed backend kind {kind}: {argv}")
        item = self.replies[kind]
        if isinstance(item, list):
            item = item.pop(0)
        if isinstance(item, BaseException):
            raise item
        out, rc = item
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")

    def wsl(self, script: str, timeout_s: int | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(["wsl", "-d", "Ubuntu-24.04", "--", "bash", "-lc", script], None, timeout_s)

    def wsl_docker(self, args: list[str], timeout_s: int | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(["wsl", "-d", "Ubuntu-24.04", "--", "docker"] + args, None, timeout_s)

    def subprocess_run(
        self, argv: list[str], *, input_payload: bytes | None = None, timeout_s: int | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self._run(argv, input_payload, timeout_s)


# --------------------------------------------------------------------------- #
# 1. frozen command construction / mapping                                     #
# --------------------------------------------------------------------------- #
def test_r2_construct_pytest_command_matches_frozen_format() -> None:
    """Byte-for-byte mirror of the frozen harness_v3.run_state_v3 f-string."""
    cmd = lr.construct_pytest_command(TID12, "t", 0, 0, PILOT_TEST_FILES[0], WT_NAME)
    frozen = (
        "/opt/venv/bin/python -m pytest -p no:cacheprovider -o addopts= "
        "--ds=saleor.tests.settings --disable-socket --reuse-db "
        f"--junitxml /workspace/{WT_NAME}/{TID12}_t_r0_f0.xml -q {PILOT_TEST_FILES[0]!r}"
    )
    assert cmd == frozen


def test_r2_planned_invocations_rep_major_flat_numbering() -> None:
    invs = lr.planned_invocations(TID12, "t", PILOT_TEST_FILES, WT_NAME)
    assert len(invs) == 3 * len(PILOT_TEST_FILES) == 12
    for i, inv in enumerate(invs):
        rep, fidx = divmod(i, len(PILOT_TEST_FILES))
        assert (inv.flat_index, inv.rep, inv.file_idx) == (i, rep, fidx)
        assert inv.junit_name == f"{TID12}_t_r{rep}_f{fidx}"
        assert inv.test_file == PILOT_TEST_FILES[fidx]
    assert invs[5].junit_name == f"{TID12}_t_r1_f1"


def test_r2_parse_run_rc_ledger_green() -> None:
    n = 6
    ledger = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(n)}), expected_runs=n, source="BOUNDARY_FULL_STDOUT"
    )
    assert ledger.rc_by_index == {i: 0 for i in range(n)}
    assert ledger.all_runs_done and not ledger.install_failed


@pytest.mark.parametrize(
    "lines",
    [
        ["RUN_0_RC=0", "RUN_1_RC=0", "RUN_2_RC=0", "RUN_3_RC=0", "RUN_4_RC=0"],  # missing 5
        ["RUN_0_RC=0", "RUN_1_RC=0", "RUN_1_RC=0", "RUN_2_RC=0", "RUN_3_RC=0", "RUN_4_RC=0", "RUN_5_RC=0"],  # duplicate
        ["RUN_0_RC=0", "RUN_1_RC=0", "RUN_2_RC=0", "RUN_3_RC=0", "RUN_4_RC=0", "RUN_5_RC=0", "RUN_6_RC=0"],  # extra
        ["RUN_5_RC=0", "RUN_0_RC=0", "RUN_1_RC=0", "RUN_2_RC=0", "RUN_3_RC=0", "RUN_4_RC=0"],  # out-of-order
    ],
)
def test_r2_parse_run_rc_ledger_malformed_rejected(lines: list[str]) -> None:
    text = "\n".join(lines) + "\nALL_RUNS_DONE\n"
    with pytest.raises(lr.LauncherReceiptError):
        lr.parse_run_rc_ledger(text, expected_runs=6, source="BOUNDARY_FULL_STDOUT")


def test_r2_parse_run_rc_ledger_malformed_line_rejected() -> None:
    text = "RUN_0_RC=0\nRUN_1_RC=abc\nRUN_2_RC=0\nRUN_3_RC=0\nRUN_4_RC=0\nRUN_5_RC=0\nALL_RUNS_DONE\n"
    with pytest.raises(lr.LauncherReceiptError):
        lr.parse_run_rc_ledger(text, expected_runs=6, source="BOUNDARY_FULL_STDOUT")


# --------------------------------------------------------------------------- #
# 2. install markers / completeness                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("marker", ["INSTALL_MAIN_FAIL", "INSTALL_DEV_FAIL", "TOOLING_FAIL"])
def test_r2_install_failure_markers_detected(marker: str) -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({0: 2}, markers=(marker,), all_done=False), expected_runs=1, source="BOUNDARY_FULL_STDOUT"
    )
    assert led.install_failed and marker in led.install_markers
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract({"t": led}, oracle=_tiny_oracle(), expected_runs={"t": 1})


def test_r2_absent_all_runs_done_blocks() -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(6)}, all_done=False), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract({"t": led}, oracle=_tiny_oracle(), expected_runs={"t": 6})


def test_r2_invocation_count_mismatch_blocks() -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(6)}, all_done=True), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    # planned runs are 6 per side = 3 reps x 2 files; a state claim of 12 mismatches
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract({"t": led}, oracle=_tiny_oracle(), expected_runs={"t": 12})


def test_r2_timeout_blocks_with_missing_provenance() -> None:
    backend = FakeBackend({"CONTAINER": subprocess.TimeoutExpired("wsl", timeout=7200)})
    cap = lr.LaunchCapture(backend)
    with pytest.raises(subprocess.TimeoutExpired):
        cap.wsl_docker(_container_argv("t"))
    launches = cap.side_container_run("t")
    assert launches is not None and launches.timeout
    out = lr.assess_side(
        side="t",
        container_run=launches,
        oracle=_tiny_oracle(),
        test_files=TINY_FILES,
        raw_root=Path("does-not-exist"),
    )
    assert out.ledger.source == "TIMEOUT_NO_STDOUT"
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract({"t": out.ledger}, oracle=_tiny_oracle(), expected_runs={"t": 6})


# --------------------------------------------------------------------------- #
# 3. RC=2 classification gate                                                  #
# --------------------------------------------------------------------------- #
def test_r2_unexpected_rc2_target_side_blocks() -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(5)} | {5: 2}), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract(
            {"t": led},
            oracle=_tiny_oracle(),
            expected_runs={"t": 6},
            raw_junit=_six_flat_junit("t", [(P2P_A, "passed")]),
        )


def test_r2_rc2_parent_golden_pilot_blocks_no_exception() -> None:
    """Golden pilot: PARENT_COLLECTION_ERROR=0 and SYMBOL_ABSENCE_F2P=0, so every
    parent-side pytest rc=2 must BLOCK regardless of any claim."""
    oracle = _tiny_oracle()
    assert oracle.counts_strict["PARENT_COLLECTION_ERROR"] == 0
    assert oracle.counts_strict["SYMBOL_ABSENCE_F2P"] == 0
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(5)} | {5: 2}), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    with pytest.raises(lr.LauncherReceiptError) as ei:
        lr.validate_invocation_contract(
            {"p": led},
            oracle=oracle,
            expected_runs={"p": 6},
            raw_junit=_six_flat_junit("p", [(P2P_A, "passed")]),
        )
    assert "no rc=2 exception" in str(ei.value).lower()


def test_r2_expected_parent_collection_error_is_diagnostic_only() -> None:
    """A task whose frozen oracle ALLOWS parent collection errors: the rc=2 run is
    classified COLLECTION_ERROR_DIAGNOSTIC when matched to predeclared evidence,
    and is never treated as an eligible BEHAVIORAL_F2P run."""
    missing_node = "saleor/app/tests/test_new_thing.py::test_new_feature"
    oracle = lr.TaskOracleExpectation(
        task_id="saleor-rc-0179b331be38",
        parent_commit="a" * 40,
        target_commit="b" * 40,
        test_files=TINY_FILES,
        counts_strict={
            "BEHAVIORAL_F2P": 0,
            "SYMBOL_ABSENCE_F2P": 0,
            "PARENT_COLLECTION_ERROR": 1,
            "FLAKY": 0,
            "TARGET_ORACLE_INVALID": 0,
            "P2P_ONLY": 0,
            "OTHER_REVIEW_REQUIRED": 0,
        },
        strict_f2p_node_ids={"BEHAVIORAL_F2P": (), "SYMBOL_ABSENCE_F2P": ()},
        strict_p2p_only=(),
        node_universe=(missing_node,),
        contract_sha256="d" * 64,
        oracle_source="SYNTHETIC_TEST",
        expected_collection_error_nodes=(missing_node,),
    )
    cls = lr.classification_for_interrupted(
        side="p",
        flat_index=5,
        rep=2,
        file_idx=1,
        test_file=TINY_FILES[1],
        raw_junit_text=_collection_error_junit(),
        oracle=oracle,
    )
    assert cls["decision"] == "COLLECTION_ERROR_DIAGNOSTIC"
    assert cls["kind"] == "EXPECTED_PARENT_COLLECTION_ERROR"
    assert cls["f2p_eligible"] is False
    # a target-side rc=2 is never diagnostic
    cls2 = lr.classification_for_interrupted(
        side="t",
        flat_index=5,
        rep=2,
        file_idx=1,
        test_file=TINY_FILES[1],
        raw_junit_text=_collection_error_junit(),
        oracle=oracle,
    )
    assert cls2["decision"] == "BLOCKED"


def test_r2_rc2_without_predeclared_evidence_blocks() -> None:
    # golden-like oracle (PCE=0): the no-exception rule fires first
    oracle = _tiny_oracle()
    cls = lr.classification_for_interrupted(
        side="p",
        flat_index=5,
        rep=2,
        file_idx=1,
        test_file=TINY_FILES[1],
        raw_junit_text=_collection_error_junit(),
        oracle=oracle,
    )
    assert cls["decision"] == "BLOCKED"
    assert "no rc=2 exception" in cls["reasons"][0].lower()
    # an oracle that ALLOWS parent collection errors but has NO predeclared
    # expected node identities -> insufficient provenance -> BLOCKED
    oracle_pce = lr.TaskOracleExpectation(
        task_id="saleor-rc-0179b331be38",
        parent_commit="a" * 40,
        target_commit="b" * 40,
        test_files=TINY_FILES,
        counts_strict={
            "BEHAVIORAL_F2P": 0,
            "SYMBOL_ABSENCE_F2P": 0,
            "PARENT_COLLECTION_ERROR": 1,
            "FLAKY": 0,
            "TARGET_ORACLE_INVALID": 0,
            "P2P_ONLY": 0,
            "OTHER_REVIEW_REQUIRED": 0,
        },
        strict_f2p_node_ids={"BEHAVIORAL_F2P": (), "SYMBOL_ABSENCE_F2P": ()},
        strict_p2p_only=(),
        node_universe=(),
        contract_sha256="d" * 64,
        oracle_source="SYNTHETIC_TEST",
        expected_collection_error_nodes=(),
    )
    cls2 = lr.classification_for_interrupted(
        side="p",
        flat_index=5,
        rep=2,
        file_idx=1,
        test_file=TINY_FILES[1],
        raw_junit_text=_collection_error_junit(),
        oracle=oracle_pce,
    )
    assert cls2["decision"] == "BLOCKED"
    assert "predeclared" in cls2["reasons"][0].lower()


@pytest.mark.parametrize("rc", [3, 4, 5])
def test_r2_terminal_rcs_3_4_5_block(rc: int) -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 for i in range(5)} | {5: rc}), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_invocation_contract(
            {"t": led},
            oracle=_tiny_oracle(),
            expected_runs={"t": 6},
            raw_junit=_six_flat_junit("t", [(P2P_A, "passed")]),
        )


# --------------------------------------------------------------------------- #
# 4. rc vs raw junit congruence                                                #
# --------------------------------------------------------------------------- #
def test_r2_rc0_with_failed_junit_is_contradiction() -> None:
    led = lr.parse_run_rc_ledger(_rc_stdout({i: 0 for i in range(6)}), expected_runs=6, source="BOUNDARY_FULL_STDOUT")
    # f1 target side contains INV_D which failed, but rc=0 is claimed
    raw = _six_flat_junit("t", [(P2P_A, "passed")])
    for r in range(3):
        raw[f"{TID12}_t_r{r}_f1.xml"] = _junit_xml([(INV_D, "failed"), (P2P_B, "passed")])
    with pytest.raises(lr.LauncherReceiptError) as ei:
        lr.audit_rc_vs_raw_junit(side="t", led=led, oracle=_tiny_oracle(), raw_junit=raw)
    assert "contradiction" in str(ei.value).lower()


def test_r2_rc1_with_all_passing_junit_blocks() -> None:
    led = lr.parse_run_rc_ledger(
        _rc_stdout({i: 0 if i % 2 == 0 else 1 for i in range(6)}), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
    )
    # rc=1 claim but every junit fragment is all-pass
    with pytest.raises(lr.LauncherReceiptError):
        lr.audit_rc_vs_raw_junit(
            side="t",
            led=led,
            oracle=_tiny_oracle(),
            raw_junit=_six_flat_junit("t", [(P2P_A, "passed")]),
        )


def test_r2_corrupt_raw_xml_blocks() -> None:
    with pytest.raises(lr.LauncherReceiptError):
        lr.audit_rc_vs_raw_junit(
            side="t",
            led=lr.parse_run_rc_ledger(
                _rc_stdout({i: 0 for i in range(6)}), expected_runs=6, source="BOUNDARY_FULL_STDOUT"
            ),
            oracle=_tiny_oracle(),
            raw_junit={f"7e42fc67ce72_t_r{r}_f{i}.xml": "<not-xml" for r in range(3) for i in (0, 1)},
        )


# --------------------------------------------------------------------------- #
# 5. launch capture: ordered argv + honest labels                              #
# --------------------------------------------------------------------------- #
def test_r2_launch_capture_preserves_ordered_argv_and_env() -> None:
    backend = FakeBackend(
        {
            "CONTAINER": (_rc_stdout({i: 0 for i in range(12)}, all_done=True), 0),
            "RUNS_SCRIPT": ("", 0),
            "INSTALL_SCRIPT": ("", 0),
            "DB": ("", 0),
            "IMAGE": ("sha256:" + "e" * 64, 0),
            "GIT": ("", 0),
            "OTHER": ("", 0),
        }
    )
    cap = lr.LaunchCapture(backend)
    run_argv = ["wsl", "-d", "Ubuntu-24.04", "--", "docker"] + _container_argv("t")
    comp = cap.wsl_docker(_container_argv("t"))
    assert comp.returncode == 0
    # the subprocess-boundary argv is preserved EXACTLY in order
    assert tuple([a for a in backend.calls[-1][0]]) == tuple(run_argv)
    launch = cap.launches[-1]
    assert launch.boundary == "CONTAINER_RUN"
    assert launch.ordered_argv == tuple(run_argv)
    assert not launch.timeout
    # the container-run boundary exposes the FULL stdout (not the 3000-char tail)
    assert "RUN_11_RC=0" in (launch.stdout_full or "")
    assert "ALL_RUNS_DONE" in (launch.stdout_full or "")
    # side is resolved FROM the preserved argv (DATABASE_URL db name), not guessed
    assert cap.side_container_run("t") is launch


def test_r2_capture_labels_harness_constructed_never_os_attested() -> None:
    capture_argv = ["docker", "run", "--rm", "wp2-era-py38", "bash", "true"]
    kind = lr.argv_evidence_kind(capture_argv)
    assert kind == "HARNESS_CONSTRUCTED"
    assert kind not in rs.OS_ATTESTATION_METHODS
    # schema: HARNESS_CONSTRUCTED must NOT carry claim_os_attested=True
    order = ["wsl", "-d", "Ubuntu-24.04", "--", "docker"] + _container_argv("p")
    per_node = _tiny_per_node()
    jed = [{"file": f"{TID12}_p_r{r}_f{i}.xml", "sha256": "e" * 64, "raw": True} for r in range(3) for i in (0, 1)]
    with pytest.raises(rs.ReceiptError) as ei:
        rs.validate_receipt(
            lr.build_receipt_payload(
                task_oracle=_tiny_oracle(),
                per_node=per_node,
                ledger_by_side={"t": _ok_ledger(), "p": _ok_ledger()},
                junit_entries=jed,
                env_evidence=_env(),
                scope_patch_paths=["saleor/app/manifest_validations.py"],
                container_host_argv=order,
                container_returncode=0,
                control="NEG",
                sens_supported=True,
                claim_os_attested=True,
            )
        )
    assert "claim" in str(ei.value).lower()


def _env() -> dict[str, str]:
    return {"linux_environment_digest": "1" * 64, "manifest_sha256": "2" * 64, "image_digest": "3" * 64}


def test_r2_env_pin_missing_blocks() -> None:
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_env_pins({"linux_environment_digest": "1" * 64})


# --------------------------------------------------------------------------- #
# 6. node identity / repetitions / side                                        #
# --------------------------------------------------------------------------- #
def test_r2_swapped_node_identity_blocks() -> None:
    oracle = _tiny_oracle()
    observed = list(oracle.node_universe)
    observed[0], observed[1] = observed[1], observed[0]  # an observation set that is NOT the universe
    with pytest.raises(lr.LauncherReceiptError):
        lr.validate_node_identity_against_oracle(observed[1:], oracle)


def test_r2_wrong_task_prefix_in_raw_junit_blocks() -> None:
    with pytest.raises(rs.ReceiptError):
        lr.parse_receipt_raw_junit_name("6e42fc67ce72_t_r0_f0.xml", TASK)
    name = lr.parse_receipt_raw_junit_name(f"{TID12}_p_r2_f1.xml", TASK)
    assert name == ("p", "r2", "f1.xml")


def test_r2_missing_repetition_blocks(tmp_path: Path) -> None:
    oracle = _tiny_oracle()
    raw_root = tmp_path / "raw"
    flat = tmp_path / "flat"
    _write_raw_tree(raw_root)
    for p in list((raw_root / "t").glob("*_r2_*.xml")) + list((raw_root / "p").glob("*_r2_*.xml")):
        p.unlink()
    # physical repetition r2 is entirely absent
    per_node, censuses, _ = lr.build_observation_ledgers(
        raw_root=raw_root,
        task_oracle=oracle,
        tid12=TID12,
        container_runs={"t": _dummy_run("t"), "p": _dummy_run("p")},
        tolerate_missing=True,
    )
    assert all("r2" not in (q or "") for c in censuses.values() for q in c)
    entries = lr.assemble_flat_raw_dir(raw_root, flat_dir=flat, task_id=TASK, tid12=TID12)
    assert len([e for e in entries if e["file"].endswith("_r2_f0.xml")]) == 0
    side_ledgers = {"t": _ok_ledger(), "p": _ok_ledger()}
    payload = lr.build_receipt_payload(
        task_oracle=oracle,
        per_node=per_node,
        ledger_by_side=side_ledgers,
        junit_entries=entries,
        env_evidence=_env(),
        scope_patch_paths=["saleor/app/manifest_validations.py"],
        container_host_argv=["wsl", "-d", "Ubuntu-24.04", "--", "docker"] + _container_argv("t"),
        container_returncode=0,
        control="NEG",
        sens_supported=True,
        claim_os_attested=False,
    )
    with pytest.raises(rs.ReceiptError):
        rs.validate_receipt(payload, expected_task_node_ids=oracle.node_universe)


class _DummyHost:
    """Minimal non-timeout container-run stand-in for pure raw-file tests."""

    def __init__(self, side: str) -> None:
        self.boundary = "CONTAINER_RUN"
        self.ordered_argv = ("wsl", "-d", "Ubuntu-24.04", "--") + tuple(_container_argv(side))
        self.input_payload_sha256 = None
        self.stdout_full = "ALL_RUNS_DONE\n"
        self.returncode = 0
        self.timeout = False


def _dummy_run(side: str) -> lr.HostLaunch:
    d = _DummyHost(side)
    return lr.HostLaunch(**d.__dict__)


def _ok_ledger() -> lr.RunLedger:
    return lr.RunLedger(
        rc_by_index={i: 0 for i in range(6)},
        all_runs_done=True,
        install_failed=False,
        install_markers=(),
        container_returncode=0,
        source="BOUNDARY_FULL_STDOUT",
    )


def test_r2_mismatched_hash_blocks(tmp_path: Path) -> None:
    flat = tmp_path / "flat"
    flat.mkdir(parents=True, exist_ok=True)
    (flat / "7e42fc67ce72_t_r0_f0.xml").write_bytes(b"<?xml version='1.0'?><testsuite/>")
    # missing file at the consumer boundary
    payload_missing = {"outputs": {"junit": [{"file": "nope.xml", "sha256": "1" * 64}]}}
    with pytest.raises(rs.ReceiptError):
        rs.verify_raw_file_hashes(payload_missing, flat)
    # file exists but recorded sha256 does not match disk bytes
    payload_bad = {"outputs": {"junit": [{"file": "7e42fc67ce72_t_r0_f0.xml", "sha256": "0" * 64}]}}
    with pytest.raises(rs.ReceiptError):
        rs.verify_raw_file_hashes(payload_bad, flat)


# --------------------------------------------------------------------------- #
# 7. negative integration: merged junit dict can never qualify                 #
# --------------------------------------------------------------------------- #
def test_r2_merged_dict_only_cannot_claim_qualification() -> None:
    """A wrapper that read ONLY a merged ``junit`` dictionary (frozen dict.update
    last-rep-wins seam) carries NO per-rep raw files and NO invocation ledger; it
    must fail closed instead of claiming a successful qualification."""
    merged = {P2P_A: "passed", P2P_B: "passed"}  # shallow M16-style merged dict
    n = lr.assess_merged_dict_only(merged, task_oracle=_tiny_oracle())
    assert n["decision"] == "BLOCKED"
    assert "merged" in " ".join(n["reasons"]).lower()
    assert n["verdict_record"]["verdict"] == "BLOCKED"


# --------------------------------------------------------------------------- #
# 8. live frozen oracle (read-only, minimal)                                   #
# --------------------------------------------------------------------------- #
def test_r2_loader_golden_pilot_frozen_counts() -> None:
    oracle = lr.load_task_oracle_expectation(TASK, project_root=ROOT)
    assert oracle.counts_strict["BEHAVIORAL_F2P"] == 3
    assert oracle.counts_strict["P2P_ONLY"] == 103
    assert oracle.counts_strict["TARGET_ORACLE_INVALID"] == 11
    assert oracle.counts_strict["PARENT_COLLECTION_ERROR"] == 0
    assert oracle.counts_strict["SYMBOL_ABSENCE_F2P"] == 0
    assert len(oracle.strict_p2p_only) == 103
    assert len(oracle.node_universe) == 117
    assert oracle.test_files == tuple(PILOT_TEST_FILES)
    assert oracle.parent_commit == PARENT and oracle.target_commit == TARGET
    assert oracle.contract_sha256 == PILOT_CONTRACT_SHA
    assert oracle.expected_collection_error_nodes == ()


def _rc_lines(rc_list: list[int]) -> str:
    return "\n".join(f"RUN_{i}_RC={rc}" for i, rc in enumerate(rc_list)) + "\nALL_RUNS_DONE\n"


def _raw_junit_by_name(raw_root: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for side in ("t", "p"):
        out[side] = {}
        for p in (raw_root / side).glob("*.xml"):
            out[side][p.name] = p.read_text(encoding="utf-8")
    return out


def test_r2_full_seam_synthetic_green_pass(tmp_path: Path) -> None:
    """End-to-end: capture -> ledger -> per-rep raw files -> flat assembly ->
    receipt payload -> validate_receipt PASS -> verify_raw_file_hashes PASS."""
    oracle = _tiny_oracle()
    raw_root = tmp_path / "raw"
    flat_dir = tmp_path / "flat"
    _write_raw_tree(raw_root)
    rcs = _side_content_plan()
    backend = FakeBackend(
        {
            "CONTAINER": [(_rc_lines(rcs["t"]), 0), (_rc_lines(rcs["p"]), 0)],
            "RUNS_SCRIPT": ("", 0),
            "INSTALL_SCRIPT": ("", 0),
            "OTHER": ("", 0),
        }
    )
    cap = lr.LaunchCapture(backend)
    cap.wsl_docker(_container_argv("t"))
    cap.wsl_docker(_container_argv("p"))
    t_run = cap.side_container_run("t")
    p_run = cap.side_container_run("p")
    assert t_run is not None and p_run is not None
    t_out = lr.assess_side(side="t", container_run=t_run, oracle=oracle, test_files=TINY_FILES, raw_root=raw_root)
    p_out = lr.assess_side(side="p", container_run=p_run, oracle=oracle, test_files=TINY_FILES, raw_root=raw_root)
    assert "".join(map(str, ledger_rcs(t_out))) == "010101"
    assert "".join(map(str, ledger_rcs(p_out))) == "101010"
    lr.validate_invocation_contract(
        {"t": t_out.ledger, "p": p_out.ledger},
        oracle=oracle,
        expected_runs={"t": 6, "p": 6},
        raw_junit=_raw_junit_by_name(raw_root),
    )
    per_node, censuses, n_nodes = lr.build_observation_ledgers(
        raw_root=raw_root,
        task_oracle=oracle,
        tid12=TID12,
        container_runs={"t": t_run, "p": p_run},
        tolerate_missing=False,
    )
    assert n_nodes == 4
    assert set(per_node) == set(oracle.node_universe)
    for side in ("t", "p"):
        assert len(censuses[side]) == 6
    lr.verify_oracle_reproduction(per_node, oracle, raw_root=raw_root, tid12=TID12)
    entries = lr.assemble_flat_raw_dir(raw_root, flat_dir=flat_dir, task_id=TASK, tid12=TID12)
    assert len(entries) == 12  # 2 sides x 3 reps x 2 files
    side_ledgers = {"t": t_out.ledger, "p": p_out.ledger}
    payload = lr.build_receipt_payload(
        task_oracle=oracle,
        per_node=per_node,
        ledger_by_side=side_ledgers,
        junit_entries=entries,
        env_evidence=_env(),
        scope_patch_paths=["saleor/app/manifest_validations.py"],
        container_host_argv=list(t_run.ordered_argv),
        container_returncode=0,
        control="NEG",
        sens_supported=True,
        claim_os_attested=False,
    )
    assert rs.validate_receipt(payload, expected_task_node_ids=oracle.node_universe) == "PASS"
    verified = rs.verify_raw_file_hashes(payload, flat_dir)
    assert len(verified) == 12
    lr.verify_r1_side_layout_matches(entries, raw_root)


def ledger_rcs(side_out: lr.SideAssessment) -> list[int]:
    return [side_out.ledger.rc_by_index[i] for i in sorted(side_out.ledger.rc_by_index)]


def test_r2_assess_side_binds_ledger_to_mapping(tmp_path: Path) -> None:
    oracle = _tiny_oracle()
    raw_root = tmp_path / "raw"
    _write_raw_tree(raw_root)
    backend = FakeBackend(
        {
            "CONTAINER": (_rc_stdout({i: 0 for i in range(6)}), 0),
            "OTHER": ("", 0),
        }
    )
    cap = lr.LaunchCapture(backend)
    cap.wsl_docker(_container_argv("p"))
    run = cap.side_container_run("p")
    assert run is not None
    out = lr.assess_side(side="p", container_run=run, oracle=oracle, test_files=TINY_FILES, raw_root=raw_root)
    assert out.juni_by_flat[0].junit_name == f"{TID12}_p_r0_f0"
    assert out.juni_by_flat[5].junit_name == f"{TID12}_p_r2_f1"
    assert out.ledger.source == "BOUNDARY_FULL_STDOUT"
