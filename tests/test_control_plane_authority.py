from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (  # noqa: E402
    AuthorityRole,
    AuthorityUnavailable,
    ForbiddenAuthoritySubstrate,
    NonPromotionalEvidence,
    OperationBinding,
    ProductionTopology,
    SubstrateBinding,
    production_authority,
    require_promotable,
)
from control_plane.testing import InMemoryAuthority  # noqa: E402


OLD_STATE = "sha256:" + "1" * 64
NEW_STATE = "sha256:" + "2" * 64
INTENT = "sha256:" + "3" * 64
PLAN = "sha256:" + "4" * 64
SUBJECT = "sha256:" + "5" * 64
ROLLBACK = "sha256:" + "6" * 64


def operation_binding(*, expected: str = OLD_STATE) -> OperationBinding:
    return OperationBinding(
        operation_id="op-activation-001",
        intent_digest=INTENT,
        plan_digest=PLAN,
        subject_digest=SUBJECT,
        target_id="reference-host",
        expected_state_digest=expected,
        intended_state_digest=NEW_STATE,
        generation_binding="required_generation",
        rollback_target_digest=ROLLBACK,
        fence_epoch=1,
    )


def test_production_authority_without_selected_topology_fails_closed():
    with pytest.raises(AuthorityUnavailable) as exc_info:
        production_authority()

    assert exc_info.value.code == "AUTHORITY_TOPOLOGY_UNBOUND"


@pytest.mark.parametrize(
    ("role", "provider"),
    [
        (AuthorityRole.SIGNER, "git"),
        (AuthorityRole.EVIDENCE_STORE, "mutable_local_file"),
        (AuthorityRole.JOURNAL, "target_host_log"),
    ],
)
def test_production_authority_rejects_non_authoritative_substrates(role, provider):
    topology = ProductionTopology(
        bindings=(SubstrateBinding(role=role, provider=provider),)
    )

    with pytest.raises(ForbiddenAuthoritySubstrate) as exc_info:
        production_authority(topology)

    assert exc_info.value.code == "AUTHORITY_SUBSTRATE_FORBIDDEN"
    assert provider in str(exc_info.value)


def test_unimplemented_production_binding_stays_unavailable():
    topology = ProductionTopology(
        bindings=(
            SubstrateBinding(
                role=AuthorityRole.SIGNER,
                provider="operator_selected_signer",
            ),
        )
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        production_authority(topology)

    assert exc_info.value.code == "AUTHORITY_TOPOLOGY_INCOMPLETE"


def test_fake_requires_an_observed_active_state():
    authority = InMemoryAuthority()

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.observe_active()

    assert exc_info.value.code == "AUTHORITY_OBSERVATION_MISSING"


def test_fake_records_intent_before_guarded_transition():
    authority = InMemoryAuthority(initial_active_digest=OLD_STATE)
    binding = operation_binding()

    intent_receipt = authority.append_intent(binding)
    transition_receipt = authority.guarded_compare_and_swap(binding)

    assert intent_receipt.sequence == 1
    assert transition_receipt.sequence == 2
    assert authority.observe_active() == NEW_STATE
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "guarded_transition",
    ]


def test_fake_refuses_unregistered_transition_without_mutation():
    authority = InMemoryAuthority(initial_active_digest=OLD_STATE)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(operation_binding())

    assert exc_info.value.code == "AUTHORITY_INTENT_MISSING"
    assert authority.observe_active() == OLD_STATE
    assert authority.journal_entries == ()


def test_fake_refuses_expected_state_mismatch_without_mutation():
    authority = InMemoryAuthority(initial_active_digest=OLD_STATE)
    binding = operation_binding(expected="sha256:" + "9" * 64)
    authority.append_intent(binding)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(binding)

    assert exc_info.value.code == "AUTHORITY_PRESTATE_MISMATCH"
    assert authority.observe_active() == OLD_STATE
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "precheck_failed",
    ]


def test_fake_evidence_cannot_be_promoted_even_after_success():
    authority = InMemoryAuthority(initial_active_digest=OLD_STATE)
    binding = operation_binding()
    authority.append_intent(binding)
    authority.guarded_compare_and_swap(binding)

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        require_promotable(authority.evidence_view())

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"


def test_fake_rejects_a_stale_fence_without_mutation():
    authority = InMemoryAuthority(initial_active_digest=OLD_STATE)
    first = operation_binding()
    authority.append_intent(first)
    authority.guarded_compare_and_swap(first)
    stale = OperationBinding(
        operation_id="op-activation-002",
        intent_digest="sha256:" + "7" * 64,
        plan_digest=PLAN,
        subject_digest=SUBJECT,
        target_id="reference-host",
        expected_state_digest=NEW_STATE,
        intended_state_digest="sha256:" + "8" * 64,
        generation_binding="required_generation",
        rollback_target_digest=OLD_STATE,
        fence_epoch=1,
    )
    authority.append_intent(stale)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(stale)

    assert exc_info.value.code == "AUTHORITY_FENCE_STALE"
    assert authority.observe_active() == NEW_STATE
    assert authority.journal_entries[-1].kind == "precheck_failed"
