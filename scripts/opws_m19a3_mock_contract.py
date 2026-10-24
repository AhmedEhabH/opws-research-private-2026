#!/usr/bin/env python3
"""OPWS M19A3 exact-node mock evaluator contract seam -- MOCK-ONLY, ZERO API.

Scientific role
  Standalone mock seam for the OPWS (Oracle Patch Within Scope) exact-node
  instrument. It validates that a physical pytest execution observed EXACTLY
  the designated node identity set (F2P + P2P) declared in a typed request,
  under a canonical digest, before any arm is scored. It runs no Saleor pytest,
  no Docker, no model calls, and it NEVER reads the frozen F2P contract, an
  expected-arm node list, a gold file list, a target diff or any held-out
  oracle outcome. Expected nodes are caller-supplied inputs from a separately
  frozen contract; they are never derived from observed JUnit records (the
  request digest is checked against the REQUEST's declared identity, never
  recomputed from observations).

Status taxonomy (mirrors frozen E1 semantics where applicable):
  PASS                -- FULL_REFERENCE: every designated F2P and P2P node
                         observed with outcome == passed; success True but
                         eligible False (a mock instrument check is never a
                         real eligible task), mock-only provenance attached,
                         never promotable.
  NEG_DISCRIMINATIVE  -- NEG arm: >=1 designated F2P node failed; success True,
                         eligible False, mock-only provenance attached (no
                         behavioral claim from a control, never promotable).
  NEG_FAILED          -- NEG arm: every designated F2P node passed; success False.
  FAIL                -- SCOPE arm partial repair, or P2P preservation broken by
                         an OBSERVED failed/error outcome (FAIL_PRESERVATION).
  MOCK_SCOPE_PASS     -- SCOPE arm with every designated node passed; success True
                         but eligible False, mock_only True, promotable False; it
                         is an instrument check, NEVER an OPWS behavioral success.
  BLOCKED_TIMEOUT     -- per-run timeout flag on ANY repetition; success None.
  BLOCKED_COLLECTION  -- collection/import error flag, or pytest exit_code >= 2
                         (or < 0); success None. Code 1 is NOT a collection error.
  BLOCKED_INFRA       -- junit artifact missing; success None.
  BLOCKED_TEST_ORACLE -- collected run but an expected F2P or P2P node reports
                         'missing'/'skipped' (unscorable oracle observation);
                         success None (E1 G2 semantics). Never FAIL for P2P.
  BLOCKED_FLAKY       -- per-node outcomes differ across the 3 physical
                         repetitions; success None (never repeat one scalar).
ContractError is RAISED (fail closed) on: exact node-set mismatch in ANY run
(missing/extra/duplicate, parameterized IDs compared byte-exact), overlap
between declared F2P and P2P identities, empty or omitted P2P contract,
digest mismatch, unknown outcome token, duplicate expected IDs, request-vs-
observation physical repetition id mismatch, an observation argv that is empty
or does not reproduce the ordered request argv, self-inconsistent exit_code
receipts, and ANY non-mock task id (there is NO bypass flag in a MOCK-ONLY
module).

exit_code semantics (caller-supplied claim; never captured here):
  pytest exit 0 = clean completion, exit 1 = expected test failures, exit >= 2
  = collection/infrastructure failure, negative = invalid receipt. The receipt
  must be self-consistent with the node outcomes (1 requires >=1 failed/error
  outcome; 0 forbids any). Inconsistent or abnormal receipts fail closed.

Integration gate (identity provenance):
  The digest check proves INTERNAL REQUEST CONSISTENCY only: the request's ids
  and digest agree with each other. It does NOT prove the caller used the
  trusted, frozen ``git show HEAD:<contract>`` bytes. Expected-node identities
  and their digest are caller-supplied inputs; this module never derives them,
  never fabricates P2P identities, and never claims physical run provenance
  from the repetition ids 0/1/2 (those are REQUESTED run labels). See the
  ``_MOCK_PROVENANCE`` block attached to every success result.

MOCK namespace: task ids MUST match ``^mock(?:[-_][A-Za-z0-9_-]+)+$``. Nothing
here ever qualifies a mock PASS as an OPWS behavioral outcome.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Frozen outcome vocabulary (JUnit-derived)
# ---------------------------------------------------------------------------
PASSED = "passed"
FAILED = "failed"
ERROR = "error"
SKIPPED = "skipped"
MISSING = "missing"
FAIL_LIKE = (FAILED, ERROR)
_ALL_OUTCOMES = (PASSED, FAILED, ERROR, SKIPPED, MISSING)

# ---------------------------------------------------------------------------
# Synthetic arm vocabulary (real arms remain STOP)
# ---------------------------------------------------------------------------
FULL_REFERENCE = "FULL_REFERENCE"
NEG = "NEG"
SCOPE = "SCOPE"
_ARM_VALUES = (FULL_REFERENCE, NEG, SCOPE)

# Statuses -----------------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
MOCK_SCOPE_PASS = "MOCK_SCOPE_PASS"
NEG_DISCRIMINATIVE = "NEG_DISCRIMINATIVE"
NEG_FAILED = "NEG_FAILED"
BLOCKED_TIMEOUT = "BLOCKED_TIMEOUT"
BLOCKED_COLLECTION = "BLOCKED_COLLECTION"
BLOCKED_INFRA = "BLOCKED_INFRA"
BLOCKED_TEST_ORACLE = "BLOCKED_TEST_ORACLE"
BLOCKED_FLAKY = "BLOCKED_FLAKY"

MOCK_TASK_RE = re.compile(r"^mock(?:[-_][A-Za-z0-9_-]+)+$")

# Provenance attached to every success result. These flags are structural:
# a mock-only result can never be promoted to real OPWS behavioral evidence.
_MOCK_PROVENANCE: dict[str, Any] = {
    "mock_only": True,
    "promotable_to_real_opws": False,
    "identity_origin": "caller_supplied_ids_only",
    "digest_role": "internal_request_consistency_only",
    "frozen_contract_bound": False,
    "physical_provenance": "requested_repetition_ids_only",
    "raw_receipt_capture": False,
}


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


class ContractError(Exception):
    """Fail-closed contract breach. The message is the reason."""


def ids_from_sequence(ids: Sequence[str], name: str) -> frozenset[str]:
    """Validate an expected-ID input: strings, non-empty, NO duplicates."""
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        raise ContractError(f"{name} must be a sequence of node-id strings")
    for i, n in enumerate(ids):
        if not isinstance(n, str) or not n:
            raise ContractError(f"{name}[{i}] is not a non-empty node-id string")
    if len(set(ids)) != len(ids):
        raise ContractError(f"duplicate node IDs in {name}")
    return frozenset(ids)


# ---------------------------------------------------------------------------
# Typed request
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ContractRequest:
    task_id: str
    synthetic_arm: str
    scope_sha256: str
    effective_patch_sha256: str
    parent_revision: str
    environment_id: str
    run_id: str
    physical_repetition_id: int
    argv: tuple[str, ...]
    test_contract_sha256: str
    expected_f2p_ids: frozenset[str] = field(default_factory=frozenset)
    expected_p2p_ids: frozenset[str] = field(default_factory=frozenset)
    timeout_s: float | None = 0.0

    def key(self) -> str:
        """Canonical execution identity: task + arm + scope + patch + parent
        + env + run + physical repetition + ORDERED argv + declared contract
        digest + timeout. Distinct argument orders AND distinct declared node
        identities (via their validated caller-supplied digest) are DISTINCT
        execution identities."""
        return sha256_of({
            "task_id": self.task_id,
            "synthetic_arm": self.synthetic_arm,
            "scope_sha256": self.scope_sha256,
            "effective_patch_sha256": self.effective_patch_sha256,
            "parent_revision": self.parent_revision,
            "environment_id": self.environment_id,
            "run_id": self.run_id,
            "physical_repetition_id": self.physical_repetition_id,
            "argv": list(self.argv),
            "test_contract_sha256": self.test_contract_sha256,
            "timeout_s": self.timeout_s,
        })

    def designated_ids(self) -> frozenset[str]:
        return self.expected_f2p_ids | self.expected_p2p_ids


def ensure_synthetic(req: ContractRequest) -> None:
    """MOCK-ONLY hard guard: real (Saleor) task ids ALWAYS fail closed.
    There is deliberately NO bypass flag in a MOCK-ONLY module; authorization
    for real tasks lives outside this seam (real runner + frozen contract), so
    no flag or argument can ever admit a real task here."""
    if not isinstance(req.task_id, str) or not MOCK_TASK_RE.fullmatch(req.task_id):
        raise ContractError(f"mock runner rejected task id {req.task_id!r} "
                            "(real tasks require separate authorization)")
    if req.synthetic_arm not in _ARM_VALUES:
        raise ContractError(f"unknown synthetic arm {req.synthetic_arm!r}")


def canonical_identity_digest(task_id: str, f2p: frozenset[str], p2p: frozenset[str]) -> str:
    """Canonical digest over the DECLARED exact node identities only."""
    return sha256_of({"task_id": task_id,
                      "expected_f2p_ids": sorted(f2p),
                      "expected_p2p_ids": sorted(p2p)})


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MockObservation:
    """A caller-supplied claim of ONE requested physical repetition's receipt.

    ``exit_code`` uses pytest semantics: 0 clean, 1 expected test failures,
    >=2 collection/infra failure, <0 invalid. The mock NEVER captures raw
    physical run receipts -- it only validates the caller's claim, and it
    fails closed on self-inconsistent or abnormal claims.
    """
    physical_repetition_id: int
    # mapping OR item sequence (sequence form preserves duplicate output for
    # fail-closed detection at verify time)
    node_outcomes: Mapping[str, str] | Sequence[tuple[str, str]]
    timeout: bool = False
    collection_error: bool = False
    junit_missing: bool = False
    exit_code: int = 0
    argv: tuple[str, ...] = ()

    @property
    def outcome_tokens(self) -> set[str]:
        items = self.node_outcomes.items() \
            if isinstance(self.node_outcomes, Mapping) else self.node_outcomes
        return {out for _, out in items}

    def validate(self) -> None:
        unknown = self.outcome_tokens - set(_ALL_OUTCOMES)
        if unknown:
            raise ContractError(f"unknown outcome token(s): {sorted(unknown)}")


def collect_observed(node_outcomes: Mapping[str, str] | Sequence[tuple[str, str]]
                     ) -> dict[str, str]:
    """Flatten per-node outcomes; detect duplicate observed output."""
    counts: dict[str, int] = {}
    outcomes: dict[str, str] = {}
    items = node_outcomes.items() if isinstance(node_outcomes, Mapping) else node_outcomes
    for node_id, out in items:
        if not isinstance(node_id, str) or not isinstance(out, str):
            raise ContractError("observed node id/outcome must be strings")
        counts[node_id] = counts.get(node_id, 0) + 1
        outcomes[node_id] = out
    dups = sorted(n for n, c in counts.items() if c > 1)
    if dups:
        raise ContractError(f"duplicate observed node ID(s): {dups}")
    return outcomes


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def _exact_set_equality(expected: frozenset[str], observed: set[str]) -> None:
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra:
        raise ContractError(
            "exact observed node ID set mismatch: "
            f"missing={missing[:8]}{'...' if len(missing) > 8 else ''} "
            f"extra={extra[:8]}{'...' if len(extra) > 8 else ''}")


def verify_mock(req: ContractRequest, obs: MockObservation) -> dict[str, Any]:
    """Score ONE physical repetition against the declared contract.

    Fail-closed order (shared with verify_repetitions via _validate_rep):
    synthetic guard -> P2P/F2P presence -> F2P/P2P overlap -> digest ->
    physical repetition binding -> observation argv binding -> outcome
    vocabulary -> exit_code/collection/junit/timeout blocking -> exact node-set
    equality -> oracle gaps -> receipt consistency -> per-category arm
    semantics.
    ``req.test_contract_sha256`` is compared against the canonical digest of
    the DECLARED identities inside the request; observed data never feeds the
    digest (prevents deriving expected nodes from the tested arm). The digest
    proves internal request consistency ONLY, never frozen-contract usage.
    """
    blocked = _validate_rep(req, obs)
    if blocked is not None:
        return blocked
    collected = collect_observed(obs.node_outcomes)
    f2p = req.expected_f2p_ids
    p2p = req.expected_p2p_ids
    failing_f2p = sorted(n for n in f2p if collected.get(n) in FAIL_LIKE)
    passing_f2p = sorted(n for n in f2p if collected.get(n) == PASSED)
    # P2P gaps (missing/skipped) were blocked above; what remains non-passed on
    # a P2P node is an OBSERVED failure/error -> real preservation break.
    failed_p2p = sorted(n for n in p2p if collected.get(n) in FAIL_LIKE)
    if failed_p2p:
        return {"status": FAIL, "success": False, "eligible": False,
                "arm": req.synthetic_arm, "reason": "FAIL_PRESERVATION",
                "failed_p2p": failed_p2p, "detail": {"request_key": req.key()}}

    if req.synthetic_arm == NEG:
        if failing_f2p:
            return {"status": NEG_DISCRIMINATIVE, "success": True, "eligible": False,
                    "arm": NEG, "reason": "control detected absent fix",
                    "failing_f2p": failing_f2p,
                    "mock_only": True, "promotable_to_real_opws": False,
                    "detail": {"request_key": req.key(),
                                "provenance": _MOCK_PROVENANCE,
                                "n_f2p": len(f2p), "n_p2p": len(p2p)}}
        return {"status": NEG_FAILED, "success": False, "eligible": False,
                "arm": NEG, "reason": "control did not discriminate",
                "failing_f2p": [], "detail": {"request_key": req.key()}}

    if req.synthetic_arm == FULL_REFERENCE:
        if failing_f2p:
            return {"status": FAIL, "success": False, "eligible": False,
                    "arm": FULL_REFERENCE, "reason": "FAIL_F2P",
                    "failing_f2p": failing_f2p, "detail": {"request_key": req.key()}}
        return {"status": PASS, "success": True, "eligible": False,
                "arm": FULL_REFERENCE, "reason": "exact node identities confirmed",
                "mock_only": True, "promotable_to_real_opws": False,
                "detail": {"request_key": req.key(), "provenance": _MOCK_PROVENANCE,
                           "n_f2p": len(f2p), "n_p2p": len(p2p)}}

    # SCOPE arm: an all-passed run is an instrument check ONLY (MOCK_SCOPE_PASS);
    # it is eligible=False and structurally non-promotable to real success.
    if failing_f2p:
        return {"status": FAIL, "success": False, "eligible": False,
                "arm": SCOPE,
                "reason": "SCOPE_INSUFFICIENT" if passing_f2p else "SCOPE_NO_FIX",
                "failing_f2p": failing_f2p, "passing_f2p": passing_f2p,
                "detail": {"request_key": req.key()}}
    return {"status": MOCK_SCOPE_PASS, "success": True, "eligible": False,
            "arm": SCOPE, "reason": "synthetic scope arm fully passed (mock-only)",
            "mock_only": True, "promotable_to_real_opws": False,
            "detail": {"request_key": req.key(), "provenance": _MOCK_PROVENANCE}}


def _validate_rep(req: ContractRequest, obs: MockObservation,
                  check_rep_id: bool = True) -> dict[str, Any] | None:
    """Per-run fail-closed validation shared by verify_mock/verify_repetitions.

    Returns a BLOCKED result dict when the run cannot be scored, or None when
    the run IS scorable. Contract breaches (exact-set mismatch, digest, overlap,
    rep-binding, inconsistent receipts) RAISE ContractError -- the mission rule:
    a missing/extra testcase in ANY run is a contract violation, and timeout /
    collection failure in ANY run must never produce PASS.
    """
    ensure_synthetic(req)
    if not req.expected_p2p_ids:
        raise ContractError("P2P preservation IDs missing from the contract request")
    if not req.expected_f2p_ids:
        raise ContractError("F2P IDs missing from the contract request")
    overlap = sorted(req.expected_f2p_ids & req.expected_p2p_ids)
    if overlap:
        raise ContractError(f"F2P and P2P node identities overlap: {overlap}")
    if req.test_contract_sha256 != canonical_identity_digest(
            req.task_id, req.expected_f2p_ids, req.expected_p2p_ids):
        raise ContractError("node contract hash mismatch")
    if check_rep_id and obs.physical_repetition_id != req.physical_repetition_id:
        raise ContractError(
            f"physical repetition id mismatch: request={req.physical_repetition_id} "
            f"observation={obs.physical_repetition_id}")
    # The observation must attest the SAME ordered argv as the request; an
    # empty or different argv is a contract breach (never a silent default).
    if not obs.argv:
        raise ContractError(
            "observation argv is empty; the ordered request argv must be attested")
    if tuple(obs.argv) != tuple(req.argv):
        raise ContractError(
            "observation argv does not reproduce the ordered request argv: "
            f"request={list(req.argv)} observation={list(obs.argv)}")
    obs.validate()
    # exit_code >= 2 is a pytest collection/infra failure (code 1 is expected
    # test failures); < 0 is an invalid receipt. All abnormal cases fail closed.
    if obs.exit_code < 0 or obs.exit_code >= 2:
        return _blocked(BLOCKED_COLLECTION,
                        f"pytest exit code {obs.exit_code} is a collection/infra "
                        f"failure, not an expected test result", req)
    if obs.collection_error:
        return _blocked(BLOCKED_COLLECTION, "collection/import error", req)
    if obs.junit_missing:
        return _blocked(BLOCKED_INFRA, "JUnit artifact missing", req)
    if obs.timeout:
        return _blocked(BLOCKED_TIMEOUT, f"timeout (limit {req.timeout_s}s)", req)

    collected = collect_observed(obs.node_outcomes)
    expected = req.designated_ids()
    _exact_set_equality(expected, set(collected))

    raw_failures = any(out in FAIL_LIKE for out in collected.values())
    if obs.exit_code == 1 and not raw_failures:
        raise ContractError(
            "inconsistent receipt: pytest exit code 1 (test failures) but no "
            "failed/error node outcome observed")
    if obs.exit_code == 0 and raw_failures:
        raise ContractError(
            "inconsistent receipt: pytest exit code 0 (no failures) but "
            "failed/error node outcome observed")

    # Unscorable oracle observations (missing/skipped) on ANY expected node
    # (F2P or P2P) are BLOCKED, never observed FAIL (E1 G2 semantics).
    unscorable = sorted(n for n in expected if collected.get(n) in (MISSING, SKIPPED))
    if unscorable:
        return _blocked(BLOCKED_TEST_ORACLE,
                        f"expected node(s) with missing/skipped outcome in a "
                        f"collected run (unscorable oracle observation): {unscorable}",
                        req)
    return None


def _blocked(status: str, reason: str, req: ContractRequest) -> dict[str, Any]:
    return {"status": status, "success": None, "eligible": False,
            "arm": req.synthetic_arm, "reason": reason,
            "detail": {"request_key": req.key()}}


def verify_repetitions(req: ContractRequest, reps: Sequence[MockObservation]) -> dict[str, Any]:
    """Score 3 physical repetitions with per-node stability.

    EVERY repetition is independently validated (flags, exact F2P+P2P node-ID
    equality, outcome vocabulary, requested run identity, blocked statuses)
    BEFORE cross-repetition stability. A missing/extra testcase in ANY run is a
    contract violation; timeout/collection in ANY run is BLOCKED (never PASS).
    Only after all three runs are scorable is flakiness evaluated, and the
    requested physical repetition is the one scored. The ids 0,1,2 are
    REQUESTED run labels -- this mock never claims physical run provenance.
    """
    got = sorted(obs.physical_repetition_id for obs in reps)
    if got != [0, 1, 2]:
        raise ContractError(f"require explicit evidence for 3 physical runs, got {got}")
    per_node: dict[str, set[str]] = {}
    for obs in reps:
        blocked = _validate_rep(req, obs, check_rep_id=False)
        if blocked is not None:
            return blocked
        for n, out in collect_observed(obs.node_outcomes).items():
            per_node.setdefault(n, set()).add(out)
    flaky = sorted(n for n, outs in per_node.items() if len(outs) > 1)
    if flaky:
        return {"status": BLOCKED_FLAKY, "success": None, "eligible": False,
                "arm": req.synthetic_arm, "reason": "outcome changed across physical runs",
                "flaky_nodes": flaky, "detail": {"request_key": req.key()}}
    scored = next((obs for obs in reps
                   if obs.physical_repetition_id == req.physical_repetition_id), None)
    if scored is None:
        raise ContractError(
            f"requested physical repetition {req.physical_repetition_id} not among "
            "the observed runs 0,1,2")
    return verify_mock(req, scored)


# ---------------------------------------------------------------------------
# Synthetic fixtures (isolated; disjoint from real Saleor tasks)
# ---------------------------------------------------------------------------
SYNTH_F2P = frozenset({
    "synthetic/product/tests/test_tasks.py::test_fix_behavior",
    "synthetic/product/tests/test_tasks.py::test_fix_behavior_param[0]",
    "synthetic/product/tests/test_tasks.py::test_fix_behavior_param[1]",
})
SYNTH_P2P = frozenset({
    "synthetic/product/tests/test_tasks.py::test_existing_behavior_a",
    "synthetic/product/tests/test_tasks.py::test_existing_behavior_b",
})
SYNTH_SCOPE_SHA = "6" * 64
SYNTH_PATCH_SHA = "7" * 64
SYNTH_PARENT = "9" * 40
SYNTH_ENV = "mock-image:v1"
SYNTH_ARGV = ("python", "-m", "pytest", "-q", "--junitxml=-")


def synthetic_request(arm: str = FULL_REFERENCE, *, task_id: str = "mock-opws-m19a3-0001",
                      f2p: frozenset[str] | None = None, p2p: frozenset[str] | None = None,
                      environment_id: str = SYNTH_ENV, run_id: str = "mock-run-1",
                      repetition: int = 0, patch_sha: str = SYNTH_PATCH_SHA,
                      scope_sha: str = SYNTH_SCOPE_SHA, parent: str = SYNTH_PARENT,
                      timeout_s: float = 30.0) -> ContractRequest:
    f2p = SYNTH_F2P if f2p is None else f2p
    p2p = SYNTH_P2P if p2p is None else p2p
    digest = canonical_identity_digest(task_id, f2p, p2p)
    return ContractRequest(
        task_id=task_id, synthetic_arm=arm,
        expected_f2p_ids=frozenset(f2p), expected_p2p_ids=frozenset(p2p),
        test_contract_sha256=digest, scope_sha256=scope_sha,
        effective_patch_sha256=patch_sha, parent_revision=parent,
        environment_id=environment_id, run_id=run_id,
        physical_repetition_id=repetition, argv=SYNTH_ARGV, timeout_s=timeout_s,
    )


def synthetic_observation(outcomes: Mapping[str, str] | Sequence[tuple[str, str]],
                          *, rep: int = 0,
                          timeout: bool = False, collection_error: bool = False,
                          junit_missing: bool = False,
                          exit_code: int | None = None,
                          argv: tuple[str, ...] = SYNTH_ARGV) -> MockObservation:
    # preserve sequence form (duplicates survive to verify-time detection)
    if isinstance(outcomes, Mapping):
        stored: tuple[tuple[str, str], ...] = tuple(outcomes.items())
    else:
        stored = tuple(outcomes)
    if exit_code is None:
        # derive a receipt-consistent default: code 1 iff any failed/error outcome
        exit_code = 1 if any(out in FAIL_LIKE for _, out in stored) else 0
    return MockObservation(physical_repetition_id=rep, node_outcomes=stored,
                           timeout=timeout, collection_error=collection_error,
                           junit_missing=junit_missing, exit_code=exit_code, argv=argv)


def three_observations(outcomes: Mapping[str, str],
                       all_pass_except: dict[int, dict[str, str]] | None = None) -> list[MockObservation]:
    """Three DISTINCT physical repetitions; optionally flip per-rep outcomes."""
    variants = [dict(outcomes) for _ in (0, 1, 2)]
    for r in (0, 1, 2):
        variants[r].update(all_pass_except.get(r, {}) if all_pass_except else {})
    return [synthetic_observation(variants[r], rep=r) for r in (0, 1, 2)]
