"""M19B-R4 P2P-U PILOT adapter - synthetic unit tests (ZERO API).

Covers the mission Part C gate required synthetic cases for the prospective
MAIN pilot candidate selection:
- determinism (identical membership across repeated runs);
- cap nesting (cap200 subset cap400);
- salt pin (frozen V2 salt reused, never invented);
- zero-pool (no candidates -> empty membership, no crash);
- candidate contamination (changed-test node must be rejected fail-closed);
- parent/target mismatch (rejected fail-closed);
- duplicate IDs (rejected fail-closed);
- B3 changed-test / conftest / fixture / non-py exclusions.
"""

from __future__ import annotations

import pytest

from benchmark.wp2.p2p_inventory_v1 import associate_unchanged_test_files
from benchmark.wp2.p2p_u_pilot_v1 import (
    P2P_U_PILOT_VERSION,
    PILOT_PARENT_COMMIT,
    PILOT_TARGET_COMMIT,
    REUSED_PRIMARY_CAP,
    REUSED_SALT,
    REUSED_SENSITIVITY_CAP,
    apply_pilot_freeze,
    build_pilot_selection,
    collect_files_from_associated,
    derive_candidate_files,
    membership_sha256,
)

TOUCHED = [
    "CHANGELOG.md",
    "saleor/app/installation_utils.py",
    "saleor/app/management/commands/install_app.py",
    "saleor/app/manifest_validations.py",
]
CHANGED_TESTS = [
    "saleor/app/tests/test_app_commands.py",
    "saleor/app/tests/test_installation_utils.py",
    "saleor/app/tests/test_validators.py",
    "saleor/graphql/app/tests/mutations/test_app_fetch_manifest.py",
]

NODES = [
    "saleor/app/tests/tasks/test_saleor3_23.py::test_fill_settings_json_for_new_tab_target",
    "saleor/app/tests/tasks/test_saleor3_23.py::test_fill_settings_json_skips_non_widget_non_new_tab_targets",
    "saleor/app/tests/tasks/test_saleor3_23.py::test_skip_settings_if_filled",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_installation_error",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_job_id_does_not_exist",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_request_timeout",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_undefined_error",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_wrong_format_of_target_token_url",
    "saleor/app/tests/test_app_tasks.py::test_install_app_task_wrong_response_code",
    "saleor/app/tests/test_app_tasks.py::test_remove_app_task",
    "saleor/app/tests/test_app_tasks.py::test_remove_app_task_delete_period_in_progress",
    "saleor/app/tests/test_app_tasks.py::test_remove_app_task_no_app_to_remove",
    "saleor/app/tests/test_app_tasks.py::test_remove_app_task_not_remove_not_own_payloads",
    "saleor/app/tests/test_models.py::test_app_installation_set_message_truncates",
    "saleor/app/tests/test_models.py::test_qs_for_event_type",
    "saleor/app/tests/test_models.py::test_qs_for_event_type_inactive_app",
    "saleor/app/tests/test_models.py::test_qs_for_event_type_inactive_webhook",
    "saleor/app/tests/test_models.py::test_qs_for_event_type_no_payment_permissions",
    "saleor/app/tests/test_models.py::test_qs_for_event_type_no_webhook_event",
    "saleor/app/tests/test_utils.py::test_get_active_tax_app_no_permission",
    "saleor/app/tests/test_utils.py::test_get_active_tax_app_only_one_webhook",
    "saleor/app/tests/test_utils.py::test_get_active_tax_apps",
]


def test_pilot_version_pins() -> None:
    assert P2P_U_PILOT_VERSION == "p2p-u-pilot-v1-2026-10-24"
    assert PILOT_PARENT_COMMIT == "798632158394c9f2911e6d36e8e424fd55007dc4"
    assert PILOT_TARGET_COMMIT == "7e42fc67ce72770720440781fc83685a48bd91b8"


def test_reuses_frozen_v2_salt_and_caps() -> None:
    # frozen V2 constants, not newly invented
    assert REUSED_SALT == "wp2-p2p-u-v2-2026-09-25"
    assert REUSED_PRIMARY_CAP == 200
    assert REUSED_SENSITIVITY_CAP == 400


def test_determinism() -> None:
    a = apply_pilot_freeze(candidate_node_ids=NODES, touched_production_files=TOUCHED)
    b = apply_pilot_freeze(candidate_node_ids=list(reversed(NODES)), touched_production_files=TOUCHED)
    assert a["payload_sha256"] == b["payload_sha256"]
    assert a["membership_sha256"] == b["membership_sha256"]
    assert a["collected"]["selection"]["ordered_node_ids"] == b["collected"]["selection"]["ordered_node_ids"]


def test_cap_nesting() -> None:
    m = apply_pilot_freeze(candidate_node_ids=NODES, touched_production_files=TOUCHED)
    sel = m["collected"]["selection"]
    assert set(sel["cap200_node_ids"]) <= set(sel["cap400_node_ids"])
    assert sel["cap200_node_ids"] == sel["ordered_node_ids"][: sel["primary_cap"]]
    assert sel["cap400_node_ids"] == sel["ordered_node_ids"][: sel["sensitivity_cap"]]


def test_membership_contains_exact_node_ids_plus_hash() -> None:
    m = apply_pilot_freeze(candidate_node_ids=NODES, touched_production_files=TOUCHED)
    # ordered pool diagonal covers every raw candidate exactly once (23<200 caps)
    assert set(m["collected"]["selection"]["ordered_node_ids"]) == set(NODES)
    assert len(m["collected"]["selection"]["ordered_node_ids"]) == len(NODES)
    # membership hash is canonical over the sorted unique ids
    assert membership_sha256(NODES) == m["membership_sha256"]
    assert m["evaluator_only"] is True
    assert m["invisible_to_generation"] is True


def test_zero_pool_is_defined_not_crash() -> None:
    m = apply_pilot_freeze(candidate_node_ids=[], touched_production_files=TOUCHED)
    sel = m["collected"]["selection"]
    assert sel["n_raw_candidates"] == 0
    assert sel["ordered_node_ids"] == []
    assert sel["cap200_node_ids"] == []
    assert sel["cap400_node_ids"] == []
    assert m["collected"]["all_checks_pass"] is True


def test_changed_test_contamination_rejected() -> None:
    bad = list(NODES) + ["saleor/app/tests/test_app_commands.py::test_fake_changed_node"]
    with pytest.raises(ValueError, match="contamination"):
        apply_pilot_freeze(candidate_node_ids=bad, touched_production_files=TOUCHED, changed_test_files=CHANGED_TESTS)


def test_parent_target_mismatch_rejected() -> None:
    parent_side = list(NODES)
    parent_side[-1] = "saleor/app/tests/test_utils.py::test_different_node"
    with pytest.raises(ValueError, match="mismatch"):
        apply_pilot_freeze(candidate_node_ids=NODES, touched_production_files=TOUCHED, parent_node_ids=parent_side)


def test_duplicate_ids_rejected() -> None:
    dup = list(NODES) + [NODES[0]]
    with pytest.raises(ValueError, match="duplicate"):
        apply_pilot_freeze(candidate_node_ids=dup, touched_production_files=TOUCHED)


def test_v2_verification_must_pass() -> None:
    rec = build_pilot_selection(candidate_node_ids=NODES, touched_production_files=TOUCHED)
    assert rec["all_checks_pass"] is True
    assert rec["verify_checks"]["all_pass"] is True


def test_b3_file_exclusions() -> None:
    # conftest/__init__/cassettes/fixtures/[]-paths are never candidates
    assoc = [
        "saleor/app/tests/test_app_tasks.py",
        "saleor/app/tests/tasks/__init__.py",
        "conftest.py",
        "saleor/app/tests/cassettes/x.yaml",
        "saleor/app/tests/fixtures/app.py",
        "saleor/app/tests/test_utils.py",
    ]
    out = collect_files_from_associated(assoc)
    assert out == [
        "saleor/app/tests/test_app_tasks.py",
        "saleor/app/tests/test_utils.py",
    ]


def test_derive_candidate_files_unchanged_same_app() -> None:
    all_tests = [
        "saleor/app/tests/test_app_tasks.py",
        "saleor/app/tests/test_app_commands.py",  # changed -> excluded
        "saleor/graphql/app/tests/mutations/test_app_fetch_manifest.py",  # changed
        "saleor/checkout/tests/test_checkout.py",  # different app
    ]
    out = derive_candidate_files(
        touched_production_files=["saleor/app/installation_utils.py"],
        all_test_files=all_tests,
        target_diff_paths=set(CHANGED_TESTS),
    )
    assert out == ["saleor/app/tests/test_app_tasks.py"]


def test_frozen_v1_association_contamination_exclusion() -> None:
    # the frozen V1 association itself must exclude diff-modified test files
    assoc = associate_unchanged_test_files(
        touched_production_files=["saleor/app/installation_utils.py"],
        all_test_files=["saleor/app/tests/test_app_tasks.py", "saleor/app/tests/test_app_commands.py"],
        target_diff_paths=set(CHANGED_TESTS),
    )
    assert assoc == ["saleor/app/tests/test_app_tasks.py"]
