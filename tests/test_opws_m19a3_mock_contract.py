"""M19A3-ATOMIC2 — adversarial synthetic tests for the exact-node mock contract seam.

SCOPE: isolated synthetic fixtures only. Nothing here reads the frozen F2P/P2P
contracts, the 219/83-task authorities, the Saleor object store, oracle
artifacts, or runs Saleor/Docker/API. No behavioral outcome is produced; every
synthetic PASS is a mock-only instrument check and is never an OPWS result.

Covered adversarial cases (mission M19A3.1 items 4-8):
  - exact node-set equality: missing / extra / duplicate / parameterized IDs;
  - digest binding (declared identities, never observed data);
  - P2P omission and F2P omission fail closed;
  - collection/import error, junit-missing, timeout and per-node 'missing' are
    BLOCKED (success None) and never become PASS/FAIL;
  - outcome changes across three physical runs -> BLOCKED_FLAKY (three explicit
    per-run observations are required; scalar status is never replicated);
  - env/patch/parent/run identity changes the execution key;
  - real (Saleor) task ids are rejected by the mock runner.

M19A3-FIX1 regression set (each defect isolated in its own test):
  1) a node omitted from an INTERIOR repetition is a contract violation
     (not just reps[0]);
  2) timeout/collection flags on ANY repetition block (never PASS);
  3) an extra node in an interior repetition is a contract violation;
  4) no allow_real_task bypass exists: real task ids ALWAYS fail closed;
  5) argv ORDER is preserved in the execution identity key;
  6) P2P missing/skipped are unscorable oracle gaps -> BLOCKED_TEST_ORACLE,
     never FAIL_PRESERVATION (distinct from observed failed/error P2P);
  7) overlapping F2P/P2P identities and request-vs-observation physical
     repetition binding are enforced;
  8) SCOPE all-passed is MOCK_SCOPE_PASS (mock-only, non-promotable, never
     a real OPWS behavioral success);
  9) digest match proves internal request consistency only -- it never
     proves the caller used the frozen git show HEAD: contract;
  10) exit_code semantics: 0 = clean, 1 = expected test failures (needs
      >=1 failed/error outcome), >=2 or <0 = collection/infra (BLOCKED).
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT / "scripts" / "opws_m19a3_mock_contract.py"


def _load() -> Any:
    """Load the mock contract module from source (module object)."""
    spec = importlib.util.spec_from_file_location("opws_m19a3_mock_contract", str(SCRIPT))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mock = _load()
ContractError = mock.ContractError


class TestFullReferenceMockPass:
    def test_full_reference_passes_designated_f2p_and_preserves_p2p(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "PASS"
        assert r["success"] is True
        # M19A3-FIX2: even a synthetic PASS is a mock-only instrument check and
        # is NEVER a real eligible task (see TestFix2EligibilityNeverClaimed).
        assert r["eligible"] is False

    def test_three_physical_runs_stable_pass(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        reps = mock.three_observations({n: "passed" for n in req.designated_ids()})
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "PASS"


class TestNegativeControlDiscrimination:
    def test_negative_discriminates_when_f2p_fails(self):
        req = mock.synthetic_request("NEG")
        obs = mock.synthetic_observation(
            {n: ("failed" if n in req.expected_f2p_ids else "passed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "NEG_DISCRIMINATIVE"
        assert r["success"] is True
        assert r["eligible"] is False  # a control is never a behavioral success

    def test_negative_that_passes_does_not_qualify(self):
        req = mock.synthetic_request("NEG")
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        assert mock.verify_mock(req, obs)["status"] == "NEG_FAILED"

    def test_arm_label_does_not_alter_expected_identity(self):
        """The tested arm is a request label, never a selector input for the
        expected node contract (no expected nodes derived from the arm)."""
        a = mock.synthetic_request("FULL_REFERENCE")
        b = mock.synthetic_request("NEG")
        assert a.expected_f2p_ids == b.expected_f2p_ids
        assert a.expected_p2p_ids == b.expected_p2p_ids


class TestScopeArm:
    def test_scope_partial_fix_fails(self):
        req = mock.synthetic_request("SCOPE")
        # P2P preserved; only ONE of the F2P nodes (param[0]) is fixed
        obs = mock.synthetic_observation(
            {n: ("passed" if n in req.expected_p2p_ids
                 or n.endswith("param[0]") else "failed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "FAIL"
        assert r["reason"] == "SCOPE_INSUFFICIENT"
        assert r["success"] is False

    def test_scope_no_fix_fails(self):
        req = mock.synthetic_request("SCOPE")
        # P2P preserved; ALL F2P nodes still fail -> no fix inside scope
        obs = mock.synthetic_observation(
            {n: ("passed" if n in req.expected_p2p_ids else "failed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "FAIL" and r["reason"] == "SCOPE_NO_FIX"

    def test_preservation_failure_fails(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: ("failed" if n in req.expected_p2p_ids else "passed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "FAIL"
        assert r["reason"] == "FAIL_PRESERVATION"
        assert r["success"] is False


class TestExactNodeSetEquality:
    def test_missing_node_fails_closed(self):
        req = mock.synthetic_request()
        ids = set(req.designated_ids())
        ids.remove(sorted(ids)[0])
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_mock(req, mock.synthetic_observation({n: "passed" for n in ids}))

    def test_extra_node_fails_closed(self):
        req = mock.synthetic_request()
        obs = {n: "passed" for n in req.designated_ids()}
        obs["synthetic/extra.py::test_extra"] = "passed"
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_mock(req, mock.synthetic_observation(obs))

    def test_duplicate_observed_node_fails_closed(self):
        req = mock.synthetic_request()
        seq = [(n, "passed") for n in sorted(req.designated_ids())]
        seq.append((sorted(req.designated_ids())[0], "passed"))
        with self._violation("duplicate observed node ID"):
            mock.verify_mock(req, mock.synthetic_observation(seq))

    def test_parameterized_ids_compared_exactly(self):
        """[0]/[1] parameterized variants are distinct exact node identities."""
        req = mock.synthetic_request()
        base = {n: "passed" for n in req.designated_ids() if "param[" not in n}
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_mock(req, mock.synthetic_observation(base))
        # and an unknown parameterized variant is an EXTRA node
        obs = {n: "passed" for n in req.designated_ids()}
        obs["synthetic/product/tests/test_tasks.py::test_fix_behavior_param[99]"] = "passed"
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_mock(req, mock.synthetic_observation(obs))

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestContractDigestAndLeakGuard:
    def test_p2p_omission_fails_closed(self):
        req = replace(mock.synthetic_request(), expected_p2p_ids=frozenset())
        with self._violation("P2P preservation IDs missing"):
            mock.verify_mock(req, mock.synthetic_observation({}))

    def test_f2p_omission_fails_closed(self):
        req = replace(mock.synthetic_request(), expected_f2p_ids=frozenset())
        with self._violation("F2P IDs missing"):
            mock.verify_mock(req, mock.synthetic_observation({}))

    def test_wrong_digest_fails_closed(self):
        req = replace(mock.synthetic_request(), test_contract_sha256="0" * 64)
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        with self._violation("node contract hash mismatch"):
            mock.verify_mock(req, obs)

    def test_digest_bound_to_expected_not_observed(self):
        """Even with observations identical to the expected set, a tampered
        declared digest fails; the digest is never recomputed from observed
        data (no expected-from-observed derivation)."""
        req = mock.synthetic_request()
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "PASS"
        tampered = replace(req, test_contract_sha256="1" * 64)
        with self._violation("node contract hash mismatch"):
            mock.verify_mock(tampered, obs)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestBlockedCategoriesNeverPassFail:
    def test_collection_error_blocked(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()},
                                         collection_error=True)
        r = mock.verify_mock(req, obs)
        assert r["status"] == "BLOCKED_COLLECTION"
        assert r["success"] is None

    def test_junit_missing_infra_blocked(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation({}, junit_missing=True)
        r = mock.verify_mock(req, obs)
        assert r["status"] == "BLOCKED_INFRA"
        assert r["success"] is None

    def test_timeout_blocked_not_failed(self):
        req = mock.synthetic_request("FULL_REFERENCE", timeout_s=5.0)
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()},
                                         timeout=True)
        r = mock.verify_mock(req, obs)
        assert r["status"] == "BLOCKED_TIMEOUT"
        assert r["success"] is None

    def test_per_node_missing_blocked_test_oracle(self):
        req = mock.synthetic_request()
        obs = {n: "passed" for n in req.designated_ids()}
        one_f2p = sorted(req.expected_f2p_ids)[0]
        obs[one_f2p] = "missing"  # present in junit but outcome missing (E1 G2)
        r = mock.verify_mock(req, mock.synthetic_observation(obs))
        assert r["status"] == "BLOCKED_TEST_ORACLE"
        assert r["success"] is None
        assert one_f2p in r["reason"]

    def test_unknown_outcome_token_fails_closed(self):
        req = mock.synthetic_request()
        obs = {n: "passed" for n in req.designated_ids()}
        obs[sorted(req.designated_ids())[0]] = "weird"
        with self._violation("unknown outcome token"):
            mock.verify_mock(req, mock.synthetic_observation(obs))

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestThreePhysicalRepetitions:
    def test_status_flips_across_three_runs_blocked_flaky(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        node = sorted(req.expected_f2p_ids)[0]
        base = {n: "passed" for n in req.designated_ids()}
        reps = mock.three_observations(
            base, all_pass_except={1: {node: "failed"}})
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "BLOCKED_FLAKY"
        assert r["success"] is None
        assert node in r["flaky_nodes"]

    def test_three_explicit_physical_runs_required(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        reps = mock.three_observations(base)
        with self._violation("3 physical runs"):
            mock.verify_repetitions(req, reps[:2])
        with self._violation("3 physical runs"):
            # same physical repetition id repeated is NOT three runs
            dup = [mock.synthetic_observation(base, rep=0),
                   mock.synthetic_observation(base, rep=0),
                   mock.synthetic_observation(base, rep=2)]
            mock.verify_repetitions(req, dup)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestRuntimeGuardsAndIdentity:
    def test_real_saleor_task_id_rejected_by_mock_runner(self):
        req = replace(mock.synthetic_request(),
                      task_id="saleor-rc-0179b331be38")
        with self._violation("mock runner rejected task id"):
            mock.verify_mock(req, mock.synthetic_observation({}))

    def test_real_task_id_never_admitted_no_bypass_flag_exists(self):
        """M19A3-FIX1 defect 4: a MOCK-ONLY module has NO bypass flag. Real
        Saleor task ids always fail closed, even when the request carries a
        self-consistent canonical digest over the declared identities."""
        req = replace(mock.synthetic_request(), task_id="saleor-rc-0179b331be38")
        req = replace(req, test_contract_sha256=mock.canonical_identity_digest(
            req.task_id, req.expected_f2p_ids, req.expected_p2p_ids))
        assert not hasattr(req, "allow_real_task")
        with self._violation("mock runner rejected task id"):
            mock.verify_mock(req, mock.synthetic_observation({}))

    def test_environment_mismatch_changes_execution_identity(self):
        a = mock.synthetic_request(environment_id="env-1")
        b = mock.synthetic_request(environment_id="env-2")
        assert a.key() != b.key()

    def test_patch_mismatch_changes_execution_identity(self):
        a = mock.synthetic_request()
        b = mock.synthetic_request(patch_sha="f" * 64)
        assert a.key() != b.key()

    def test_scope_parent_run_repetition_argv_identity(self):
        base = mock.synthetic_request()
        assert base.key() != mock.synthetic_request(scope_sha="e" * 64).key()
        assert base.key() != mock.synthetic_request(parent="a" * 40).key()
        assert base.key() != mock.synthetic_request(run_id="run-2").key()
        assert base.key() != mock.synthetic_request(repetition=1).key()
        assert base.key() != mock.synthetic_request(timeout_s=60.0).key()
        alt = replace(base, argv=("python", "-m", "pytest", "-x"))
        assert base.key() != alt.key()

    def test_expected_duplicate_ids_rejected(self):
        with self._violation("duplicate node IDs"):
            mock.ids_from_sequence(["a::x", "a::x"], "expected_p2p_ids")

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix1MissedNodeInInteriorRepetition:
    """M19A3-FIX1 defect 1: reps[1] omitting an expected node must be a
    contract violation; exact-set validation is per-run, never only reps[0]."""

    def test_missing_node_in_rep1_is_contract_violation(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        rep1 = dict(base)
        rep1.pop(sorted(req.designated_ids())[0])
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(rep1, rep=1),
                mock.synthetic_observation(base, rep=2)]
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_repetitions(req, reps)

    def test_missing_node_in_rep2_is_contract_violation(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        rep2 = dict(base)
        rep2.pop(sorted(req.expected_p2p_ids)[0])
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(base, rep=1),
                mock.synthetic_observation(rep2, rep=2)]
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_repetitions(req, reps)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix2TimeoutOrCollectionInInteriorRepetition:
    """M19A3-FIX1 defect 2: interruption flags are interpreted for EVERY
    repetition; a timeout on reps[1] must never produce PASS."""

    def test_timeout_in_rep1_never_passes(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(base, rep=1, timeout=True),
                mock.synthetic_observation(base, rep=2)]
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "BLOCKED_TIMEOUT"
        assert r["success"] is None

    def test_collection_error_in_rep2_never_passes(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(base, rep=1),
                mock.synthetic_observation(base, rep=2, collection_error=True)]
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "BLOCKED_COLLECTION"
        assert r["success"] is None

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix3ExtraNodeInInteriorRepetition:
    """M19A3-FIX1 defect 3: an extra node ID in any interior repetition is a
    contract violation, never silently swallowed by scoring reps[0]."""

    def test_extra_node_in_rep1_is_contract_violation(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        rep1 = dict(base)
        rep1["synthetic/extra.py::test_extra"] = "passed"
        reps = mock.three_observations(base, all_pass_except={1: rep1})
        with self._violation("exact observed node ID set mismatch"):
            mock.verify_repetitions(req, reps)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix5ArgvOrderPreservedInIdentity:
    """M19A3-FIX1 defect 5: key() must preserve ordered argv; reversing the
    order of two flags changes the execution identity."""

    def test_argv_reorder_changes_execution_identity(self):
        a = replace(mock.synthetic_request(), argv=("-q", "-x"))
        b = replace(mock.synthetic_request(), argv=("-x", "-q"))
        assert a.key() != b.key()
        # and the reordered variant differs from the default argv too
        assert a.key() != mock.synthetic_request().key()

    def test_same_argv_same_order_same_key(self):
        a = replace(mock.synthetic_request(), argv=("-q", "-x"))
        b = replace(mock.synthetic_request(), argv=("-q", "-x"))
        assert a.key() == b.key()

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix6P2pOracleGapsBlockedNotFailed:
    """M19A3-FIX1 defect 6: P2P missing/skipped are unscorable oracle
    observations -> BLOCKED_TEST_ORACLE; only failed/error P2P is an observed
    preservation regression (FAIL_PRESERVATION)."""

    def test_p2p_missing_blocked_test_oracle(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = {n: "passed" for n in req.designated_ids()}
        one_p2p = sorted(req.expected_p2p_ids)[0]
        obs[one_p2p] = "missing"
        r = mock.verify_mock(req, mock.synthetic_observation(obs))
        assert r["status"] == "BLOCKED_TEST_ORACLE"
        assert r["success"] is None
        assert one_p2p in r["reason"]

    def test_p2p_skipped_blocked_test_oracle(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = {n: "passed" for n in req.designated_ids()}
        one_p2p = sorted(req.expected_p2p_ids)[0]
        obs[one_p2p] = "skipped"
        r = mock.verify_mock(req, mock.synthetic_observation(obs))
        assert r["status"] == "BLOCKED_TEST_ORACLE"
        assert r["success"] is None

    def test_p2p_failed_still_observed_regression(self):
        """Contrast: an actual failed P2P outcome is a REAL observed
        preservation break and remains FAIL_PRESERVATION."""
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = {n: "passed" for n in req.designated_ids()}
        one_p2p = sorted(req.expected_p2p_ids)[0]
        obs[one_p2p] = "failed"
        r = mock.verify_mock(req, mock.synthetic_observation(obs))
        assert r["status"] == "FAIL"
        assert r["reason"] == "FAIL_PRESERVATION"

    def test_p2p_error_is_observed_regression(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = {n: "passed" for n in req.designated_ids()}
        one_p2p = sorted(req.expected_p2p_ids)[0]
        obs[one_p2p] = "error"
        r = mock.verify_mock(req, mock.synthetic_observation(obs))
        assert r["status"] == "FAIL"
        assert r["reason"] == "FAIL_PRESERVATION"

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix7OverlapAndRunBinding:
    """M19A3-FIX1 defect 7: overlapping F2P/P2P identities and inconsistent
    request-vs-observation physical repetition binding fail closed. IDs 0,1,2
    are requested runs, never fabricated physical provenance."""

    def test_overlapping_f2p_p2p_identities_rejected(self):
        req = replace(mock.synthetic_request(),
                      expected_f2p_ids=frozenset({"syn/a.py::f1", "syn/shared.py::x"}),
                      expected_p2p_ids=frozenset({"syn/b.py::p2", "syn/shared.py::x"}))
        req = replace(req, test_contract_sha256=mock.canonical_identity_digest(
            req.task_id, req.expected_f2p_ids, req.expected_p2p_ids))
        with self._violation("overlap"):
            mock.verify_mock(req, mock.synthetic_observation(
                {n: "passed" for n in req.designated_ids()}))

    def test_observation_rep_id_must_match_request(self):
        req = mock.synthetic_request("FULL_REFERENCE", repetition=0)
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}, rep=2)
        with self._violation("physical repetition id mismatch"):
            mock.verify_mock(req, obs)

    def test_requested_run_must_be_among_observed_runs(self):
        req = mock.synthetic_request("FULL_REFERENCE", repetition=3)
        reps = mock.three_observations({n: "passed" for n in req.designated_ids()})
        with self._violation("physical repetition"):
            mock.verify_repetitions(req, reps)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix8MockScopePassNeverPromoted:
    """M19A3-FIX1 defect 8: an all-passed SCOPE run is MOCK_SCOPE_PASS with
    mock-only provenance; it is never an OPWS behavioral success."""

    def test_scope_all_passed_is_mock_scope_pass_not_real_success(self):
        req = mock.synthetic_request("SCOPE")
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "MOCK_SCOPE_PASS"
        assert r["arm"] == "SCOPE"
        assert r["eligible"] is False
        assert r["mock_only"] is True
        assert r["promotable_to_real_opws"] is False
        prov = r["detail"]["provenance"]
        assert prov["mock_only"] is True
        assert prov["promotable_to_real_opws"] is False
        assert prov["frozen_contract_bound"] is False

    def test_mock_scope_pass_across_three_stable_runs(self):
        req = mock.synthetic_request("SCOPE")
        reps = mock.three_observations({n: "passed" for n in req.designated_ids()})
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "MOCK_SCOPE_PASS"
        assert r["eligible"] is False
        assert r["mock_only"] is True

    def test_scope_partial_fix_still_fails_closed(self):
        """Regression guard: only the all-passed SCOPE case becomes
        MOCK_SCOPE_PASS; a partial fix is still FAIL/SCOPE_INSUFFICIENT."""
        req = mock.synthetic_request("SCOPE")
        obs = mock.synthetic_observation(
            {n: ("passed" if n in req.expected_p2p_ids
                 or n.endswith("param[0]") else "failed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "FAIL"
        assert r["reason"] == "SCOPE_INSUFFICIENT"

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix9ProvenanceDigestRole:
    """M19A3-FIX1 defect 9: the digest gate proves internal request consistency
    ONLY; the mock never claims the caller used the frozen git show HEAD:
    contract, and result provenance is explicitly non-promotable."""

    def test_full_reference_pass_provenance_is_mock_only(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "PASS"
        prov = r["detail"]["provenance"]
        assert prov["mock_only"] is True
        assert prov["promotable_to_real_opws"] is False
        assert prov["frozen_contract_bound"] is False
        assert prov["identity_origin"] == "caller_supplied_ids_only"
        assert prov["digest_role"] == "internal_request_consistency_only"
        assert prov["physical_provenance"] == "requested_repetition_ids_only"
        assert prov["raw_receipt_capture"] is False

    def test_digest_match_does_not_prove_frozen_contract_use(self):
        """A self-consistent digest over caller-supplied IDs is not evidence
        the caller used the archived contract; the result must say so."""
        req = mock.synthetic_request()
        r = mock.verify_mock(req, mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}))
        assert r["status"] == "PASS"
        prov = r["detail"]["provenance"]
        assert prov["frozen_contract_bound"] is False
        assert prov["identity_origin"] == "caller_supplied_ids_only"
        assert prov["physical_provenance"] == "requested_repetition_ids_only"

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix2ExecutionKeyBindsContractDigest:
    """M19A3-FIX2 defect 1: key() must include the test-contract SHA so two
    requests differing ONLY in declared node identities (with the properly
    corresponding different digests) are DISTINCT execution identities."""

    def test_different_expected_ids_with_matching_digests_give_different_keys(self):
        a = mock.synthetic_request(task_id="mock-opws-m19a3-0001")
        b = mock.synthetic_request(task_id="mock-opws-m19a3-0001",
                                   p2p=frozenset({"syn/alt.py::test_alt"}))
        # preconditions: different declared identities and the corresponding
        # (correctly re-digested) test contract hashes differ as well
        assert a.expected_p2p_ids != b.expected_p2p_ids
        assert a.test_contract_sha256 != b.test_contract_sha256
        assert a.key() != b.key()

    def test_key_binds_to_the_declared_digest_itself(self):
        req = mock.synthetic_request()
        tampered = replace(req, test_contract_sha256="1" * 64)
        assert req.key() != tampered.key()

    def test_identical_payloads_keep_identical_keys(self):
        assert mock.synthetic_request().key() == mock.synthetic_request().key()


class TestFix2ObservationArgvMustMatchRequestArgv:
    """M19A3-FIX2 defect 2: obs.argv is part of the requested execution
    identity. An observation that does not reproduce the ordered request argv
    (or claims no argv at all) fails closed as a ContractError; it must never
    be silently defaulted into a PASS."""

    def test_mismatched_observation_argv_fails_closed_single_repetition(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()},
            argv=("python", "-c", "print('not the request argv')"))
        with self._violation("argv"):
            mock.verify_mock(req, obs)

    def test_empty_observation_argv_fails_closed(self):
        """An observation carrying no argv claim cannot silently default."""
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}, argv=())
        with self._violation("argv"):
            mock.verify_mock(req, obs)

    def test_mismatched_observation_argv_in_interior_repetition_fails_closed(self):
        """argv binding applies to EACH of the three repetitions: a wrong argv
        on rep1 must fail closed, never a PASS over a stable body."""
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(base, rep=1,
                                           argv=("pytest", "--wrong")),
                mock.synthetic_observation(base, rep=2)]
        with self._violation("argv"):
            mock.verify_repetitions(req, reps)

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix2EligibilityNeverClaimedByMockResults:
    """M19A3-FIX2 defects 3-4: EVERY mock result is eligible=False; every
    success==True result carries explicit non-promotable provenance; and no
    error/blocked path may accidentally claim eligible=True."""

    def test_full_reference_pass_is_eligible_false_and_non_promotable(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        r = mock.verify_mock(req, mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}))
        assert r["status"] == "PASS"
        assert r["success"] is True   # the mock instrument outcome is preserved
        assert r["eligible"] is False  # never a real eligible task
        assert r["mock_only"] is True
        assert r["promotable_to_real_opws"] is False

    def test_neg_discriminative_success_carries_mock_provenance(self):
        req = mock.synthetic_request("NEG")
        obs = mock.synthetic_observation(
            {n: ("failed" if n in req.expected_f2p_ids else "passed")
             for n in req.designated_ids()})
        r = mock.verify_mock(req, obs)
        assert r["status"] == "NEG_DISCRIMINATIVE"
        assert r["success"] is True
        assert r["eligible"] is False
        assert r["mock_only"] is True
        assert r["promotable_to_real_opws"] is False
        prov = r["detail"]["provenance"]
        assert prov["mock_only"] is True
        assert prov["promotable_to_real_opws"] is False
        assert prov["frozen_contract_bound"] is False
        assert prov["physical_provenance"] == "requested_repetition_ids_only"

    def test_error_and_blocked_paths_never_claim_eligible(self):
        """Every error/blocked result stays eligible=False; any success==True
        path must carry explicit non-promotable flags (negative guard)."""
        req_full = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req_full.designated_ids()}

        missing = dict(base)
        missing[sorted(req_full.expected_p2p_ids)[0]] = "missing"
        p2p_fail = dict(base)
        p2p_fail[sorted(req_full.expected_p2p_ids)[0]] = "failed"
        f2p_fail = dict(base)
        f2p_fail[sorted(req_full.expected_f2p_ids)[0]] = "failed"

        scope = mock.synthetic_request("SCOPE")
        scope_partial = mock.synthetic_observation(
            {n: ("passed" if n in scope.expected_p2p_ids
                 or n.endswith("param[0]") else "failed")
             for n in scope.designated_ids()})

        results = [
            mock.verify_mock(req_full, mock.synthetic_observation(base, timeout=True)),
            mock.verify_mock(req_full, mock.synthetic_observation(base, collection_error=True)),
            mock.verify_mock(req_full, mock.synthetic_observation({}, junit_missing=True)),
            mock.verify_mock(req_full, mock.synthetic_observation(missing)),
            mock.verify_repetitions(req_full, mock.three_observations(
                base, all_pass_except={1: f2p_fail})),  # BLOCKED_FLAKY
            mock.verify_mock(req_full, mock.synthetic_observation(p2p_fail)),
            mock.verify_mock(req_full, mock.synthetic_observation(f2p_fail)),
            mock.verify_mock(scope, scope_partial),
            mock.verify_mock(mock.synthetic_request("NEG"),
                             mock.synthetic_observation(dict(base))),  # NEG_FAILED
        ]
        assert {r["status"] for r in results} == {
            "BLOCKED_TIMEOUT", "BLOCKED_COLLECTION", "BLOCKED_INFRA",
            "BLOCKED_TEST_ORACLE", "BLOCKED_FLAKY", "FAIL",
            "NEG_FAILED"}
        for r in results:
            assert r["eligible"] is False, r["status"]
            if r["success"] is True:
                assert r["mock_only"] is True, r["status"]
                assert r["promotable_to_real_opws"] is False, r["status"]

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)


class TestFix10ExitCodeSemantics:
    """M19A3-FIX1 defect 10: explicit exit_code semantics. 0 = clean;
    1 = expected test failures (must be corroborated by failed/error outcomes);
    >=2 or <0 = pytest collection/infra failure -> BLOCKED_COLLECTION. Abnormal
    or self-inconsistent receipts always fail closed."""

    def test_exit_code_2_collection_error_blocks_even_with_pass_outcomes(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}, exit_code=2)
        r = mock.verify_mock(req, obs)
        assert r["status"] == "BLOCKED_COLLECTION"
        assert r["success"] is None

    def test_negative_exit_code_fails_closed(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}, exit_code=-1)
        assert mock.verify_mock(req, obs)["status"] == "BLOCKED_COLLECTION"

    def test_exit_code_1_without_failed_outcomes_is_inconsistent_receipt(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = mock.synthetic_observation(
            {n: "passed" for n in req.designated_ids()}, exit_code=1)
        with self._violation("exit code 1"):
            mock.verify_mock(req, obs)

    def test_exit_code_0_with_failed_outcomes_is_inconsistent_receipt(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        obs = {n: "passed" for n in req.designated_ids()}
        obs[sorted(req.expected_f2p_ids)[0]] = "failed"
        with self._violation("exit code 0"):
            mock.verify_mock(req, mock.synthetic_observation(obs, exit_code=0))

    def test_exit_code_1_with_failure_proceeds_to_verdict(self):
        req = mock.synthetic_request("NEG")
        obs = mock.synthetic_observation(
            {n: ("failed" if n in req.expected_f2p_ids else "passed")
             for n in req.designated_ids()}, exit_code=1)
        assert mock.verify_mock(req, obs)["status"] == "NEG_DISCRIMINATIVE"

    def test_exit_code_2_in_rep1_blocks_three_run_verdict(self):
        req = mock.synthetic_request("FULL_REFERENCE")
        base = {n: "passed" for n in req.designated_ids()}
        reps = [mock.synthetic_observation(base, rep=0),
                mock.synthetic_observation(base, rep=1, exit_code=3),
                mock.synthetic_observation(base, rep=2)]
        r = mock.verify_repetitions(req, reps)
        assert r["status"] == "BLOCKED_COLLECTION"
        assert r["success"] is None

    def test_synthetic_observation_auto_exit_code_is_consistent(self):
        """Regression guard: the fixture derives a consistent default exit_code
        from the outcomes instead of a hardcoded 0."""
        req = mock.synthetic_request()
        ok = mock.synthetic_observation({n: "passed" for n in req.designated_ids()})
        assert ok.exit_code == 0
        bad = {n: "passed" for n in req.designated_ids()}
        bad[sorted(req.expected_f2p_ids)[0]] = "failed"
        assert mock.synthetic_observation(bad).exit_code == 1

    @staticmethod
    def _violation(msg: str):
        import pytest
        return pytest.raises(ContractError, match=msg)
