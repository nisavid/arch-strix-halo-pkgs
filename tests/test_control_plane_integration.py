from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (
    AtomicEvidenceCut,
    BoundEvaluation,
    ControlRecord,
    GateImpact,
    NonPromotionalEvidence,
    PromotionContract,
    PromotionDenied,
    PromotionObligation,
    PromotionPhase,
    RecordValidationError,
    RegisteredAttempt,
    admit_promotion,
    assess_promotion_cut,
    registration_set_digest,
)
from control_plane.testing import InMemoryAuthority


def digest(character: str) -> str:
    return "sha256:" + character * 64


def _payload(record: ControlRecord) -> dict[str, object]:
    return json.loads(record.canonical_bytes())["payload"]


def _identity(record_id: str, identity_id: str, identity_type: str, seed: str):
    return ControlRecord.build(
        kind="identity",
        record_id=record_id,
        payload={
            "authority_digest": digest(seed),
            "identity_id": identity_id,
            "identity_type": identity_type,
        },
    )


def _generation(record_id: str, generation_id: str, seed: str) -> ControlRecord:
    return ControlRecord.build(
        kind="generation",
        record_id=record_id,
        payload={
            "artifact_digests": [digest(seed)],
            "generation_id": generation_id,
            "input_closure_digest": digest("a"),
            "manifest_digest": digest("b"),
            "generation_class": "c",
        },
    )


@dataclass(frozen=True)
class Fixture:
    contract: PromotionContract
    cut: AtomicEvidenceCut
    bound: BoundEvaluation
    attempt: RegisteredAttempt
    obligation: PromotionObligation
    requirements: ControlRecord
    candidate_generation: ControlRecord
    prior_generation: ControlRecord
    target: ControlRecord
    target_state: ControlRecord


def _fixture(
    *,
    impact: GateImpact = GateImpact.BLOCKING,
    outcome: str = "pass",
    phase: PromotionPhase = PromotionPhase.ACCEPTED,
    preassembly: bool = False,
    not_applicable: bool = False,
) -> Fixture:
    requirements = ControlRecord.build(
        kind="requirements",
        record_id="requirements:w0",
        payload={
            "approval_digest": digest("1"),
            "effective_at": "2026-08-12T09:00:00Z",
            "requirements_definition_digest": digest("2"),
            "requirement_digests": [digest("3")],
            "requirements_id": "w0-requirements",
            "requirements_version": 1,
        },
    )
    candidate = _generation("generation:candidate", "candidate-c", "4")
    prior = _generation("generation:prior", "prior-c", "5")
    accepted = candidate if phase is PromotionPhase.ACCEPTED else prior
    active = candidate if phase in {PromotionPhase.ACCEPTED, PromotionPhase.ACTIVE} else prior
    target = _identity("identity:target", "reference-host", "target", "6")
    target_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:target",
        payload={
            "fence_epoch": 7,
            "generation_digest": active.digest(),
            "observed_at": "2026-08-12T09:15:00Z",
            "projection_id": "active-generation",
            "state_digest": digest("7"),
            "target_digest": target.digest(),
        },
    )
    if preassembly:
        context_bindings = {
            "artifact_digests": [digest("8")],
            "profile_digest": digest("9"),
            "source_closure_digest": digest("a"),
        }
        context_type = "preassembly_profile"
    else:
        context_bindings = {
            "contract_digest": requirements.digest(),
            "generation_digest": candidate.digest(),
        }
        context_type = "active_contract"
    context = ControlRecord.build(
        kind="validation_context",
        record_id="context:w0-candidate",
        payload={
            "assignments_digest": digest("b"),
            "context_id": "w0-candidate",
            "context_type": context_type,
            "requirements_digest": requirements.digest(),
            **context_bindings,
        },
    )
    subject = _identity("identity:subject", "generation-c", "subject", "c")
    gate = ControlRecord.build(
        kind="gate",
        record_id="gate:control-plane",
        payload={
            "assertion_digest": digest("d"),
            "evidence_shape_digest": digest("e"),
            "fixture_role_digest": digest("f"),
            "gate_id": "control-plane",
            "validator_digest": digest("0"),
        },
    )
    dependency_projection = _identity(
        "identity:projection",
        "control-plane-dependencies",
        "input_closure",
        "1",
    )
    assignment_payload = {
        "applicability": "conditional" if not_applicable else "unconditional",
        "assignment_id": "control-plane",
        "authorization_policy_digest": digest("2"),
        "context_digest": context.digest(),
        "dependency_projection_digest": dependency_projection.digest(),
        "gate_digest": gate.digest(),
        "impact": impact.value,
        "invalidation_policy_digest": digest("3"),
        "separation_policy_digest": digest("4"),
        "subject_digest": subject.digest(),
        "validity_policy_digest": digest("5"),
    }
    if not_applicable:
        assignment_payload["predicate_digest"] = digest("6")
    assignment = ControlRecord.build(
        kind="assignment",
        record_id="assignment:control-plane",
        payload=assignment_payload,
    )
    actor = _identity("identity:validator", "validator-w0", "principal", "7")
    intent = ControlRecord.build(
        kind="intent",
        record_id="intent:control-plane:1",
        payload={
            "actor_identity_digest": actor.digest(),
            "assignment_digest": assignment.digest(),
            "context_digest": context.digest(),
            "intent_id": "control-plane-1",
            "intent_type": "gate_occurrence",
            "journal_sequence": 1,
            "registered_at": "2026-08-12T09:30:00Z",
            "subject_digest": subject.digest(),
        },
    )
    attempt_record = ControlRecord.build(
        kind="attempt",
        record_id="attempt:control-plane:1",
        payload={
            "actor_identity_digest": actor.digest(),
            "assignment_digest": assignment.digest(),
            "attempt_id": "control-plane-1",
            "context_digest": context.digest(),
            "decision": "admitted",
            "intent_digest": intent.digest(),
            "journal_sequence": 2,
            "started_at": "2026-08-12T09:40:00Z",
        },
    )
    if not_applicable:
        evidence = ControlRecord.build(
            kind="predicate_proof",
            record_id="predicate-proof:control-plane:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "actor_role": "validator",
                "assignment_digest": assignment.digest(),
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "gate_digest": gate.digest(),
                "is_applicable": False,
                "observed_at": "2026-08-12T09:50:00Z",
                "predicate_digest": assignment.payload["predicate_digest"],
                "subject_digest": subject.digest(),
            },
        )
        evaluation_payload = {
            "admissible": True,
            "applicability": "not_applicable",
            "assignment_digest": assignment.digest(),
            "attestation_digests": [],
            "context_digest": context.digest(),
            "currency": "current",
            "dependency_projection_digest": dependency_projection.digest(),
            "evaluated_at": "2026-08-12T10:00:00Z",
            "outcome": "not_applicable",
            "predicate_proof_digest": evidence.digest(),
        }
    else:
        evidence = ControlRecord.build(
            kind="attestation",
            record_id="attestation:control-plane:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "actor_role": "validator",
                "assignment_digest": assignment.digest(),
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "gate_digest": gate.digest(),
                "observed_at": "2026-08-12T09:50:00Z",
                "outcome": outcome,
                "subject_digest": subject.digest(),
            },
        )
        evaluation_payload = {
            "admissible": True,
            "applicability": "applicable",
            "assignment_digest": assignment.digest(),
            "attestation_digests": [evidence.digest()],
            "context_digest": context.digest(),
            "currency": "current",
            "dependency_projection_digest": dependency_projection.digest(),
            "evaluated_at": "2026-08-12T10:00:00Z",
            "outcome": outcome,
        }
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:control-plane:1",
        payload=evaluation_payload,
    )
    inclusion_edge = None
    if preassembly:
        inclusion_edge = ControlRecord.build(
            kind="inclusion_edge",
            record_id="inclusion-edge:control-plane:1",
            payload={
                "active_contract_digest": requirements.digest(),
                "approval_digest": digest("8"),
                "artifact_digests": list(context.payload["artifact_digests"]),
                "assignment_digests": [assignment.digest()],
                "generation_digest": candidate.digest(),
                "inclusion_edge_id": "control-plane-1",
                "preassembly_context_digest": context.digest(),
                "preassembly_evaluation_digests": [evaluation.digest()],
                "preassembly_profile_digest": context.payload["profile_digest"],
                "source_closure_digest": context.payload["source_closure_digest"],
                "verified_at": "2026-08-12T10:05:00Z",
                "verifier_identity_digest": actor.digest(),
            },
        )
    bound = BoundEvaluation(
        attempt_record=attempt_record,
        context_record=context,
        assignment_record=assignment,
        evidence_records=(evidence,),
        evaluation_record=evaluation,
        inclusion_edge_record=inclusion_edge,
    )
    terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:1",
        payload={
            "assignment_digest": assignment.digest(),
            "attempt_digest": attempt_record.digest(),
            "completed_at": "2026-08-12T10:10:00Z",
            "journal_sequence": 3,
            "outcome": (
                "succeeded"
                if not_applicable or outcome == "pass"
                else "failed"
            ),
            "poststate_digest": target_state.digest(),
            "terminal_type": "gate_attempt",
            "validator_attestation_digests": [evidence.digest()],
        },
    )
    obligation_record = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion-obligation:control-plane",
        payload={
            "assignment_digest": assignment.digest(),
            "impact": impact.value,
            "obligation_id": "control-plane",
            "occurrence_digest": intent.digest(),
        },
    )
    obligation = PromotionObligation(obligation_record)
    registered_attempt = RegisteredAttempt(
        obligation_record=obligation_record,
        intent_record=intent,
        attempt_record=attempt_record,
        terminal_record=terminal_record,
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:w0",
        payload={
            "contract_id": "w0-contract",
            "expected_accepted_generation_digest": accepted.digest(),
            "expected_active_generation_digest": active.digest(),
            "generation_digest": candidate.digest(),
            "obligation_digests": [obligation_record.digest()],
            "phase": phase.value,
            "requirements_digest": requirements.digest(),
            "target_digest": target.digest(),
            "target_kind": "live_root",
            "target_protected_state_digest": target_state.digest(),
        },
    )
    contract = PromotionContract(
        requirements_record=requirements,
        generation_record=candidate,
        target_record=target,
        target_protected_state_record=target_state,
        contract_record=contract_record,
        obligations=(obligation,),
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:w0",
        payload={
            "accepted_generation_digest": accepted.digest(),
            "active_generation_digest": active.digest(),
            "attempt_digests": [attempt_record.digest()],
            "authority_head_digest": digest("9"),
            "authority_manifest_digest": digest("a"),
            "complete_through_sequence": 3,
            "completeness_proof_digest": digest("b"),
            "contract_digest": contract_record.digest(),
            "evaluation_digests": [evaluation.digest()],
            "fork_proof_digest": digest("c"),
            "generation_digest": candidate.digest(),
            "inclusion_edge_digests": (
                [inclusion_edge.digest()] if inclusion_edge is not None else []
            ),
            "journal_head_digest": digest("d"),
            "phase": phase.value,
            "registration_set_digest": registration_set_digest(
                (registered_attempt,)
            ),
            "target_digest": target.digest(),
            "target_kind": "live_root",
            "target_protected_state_digest": target_state.digest(),
        },
    )
    cut = AtomicEvidenceCut(
        cut_record=cut_record,
        accepted_generation_record=accepted,
        active_generation_record=active,
        target_record=target,
        target_protected_state_record=target_state,
        attempts=(registered_attempt,),
        evaluations=(bound,),
        inclusion_edge_records=(
            (inclusion_edge,) if inclusion_edge is not None else ()
        ),
    )
    return Fixture(
        contract=contract,
        cut=cut,
        bound=bound,
        attempt=registered_attempt,
        obligation=obligation,
        requirements=requirements,
        candidate_generation=candidate,
        prior_generation=prior,
        target=target,
        target_state=target_state,
    )


def test_atomic_cut_assesses_total_canonical_obligation_coverage():
    fixture = _fixture()

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.contract_digest == fixture.contract.contract_digest
    assert assessment.generation_digest == fixture.candidate_generation.digest()
    assert assessment.authoritative is False
    assert assessment.obligation_evaluation_digests == (
        fixture.bound.evaluation_record.digest(),
    )


def test_bound_evaluation_rejects_a_record_chain_from_another_assignment():
    fixture = _fixture()
    other = ControlRecord.build(
        kind="assignment",
        record_id="assignment:other",
        payload={**_payload(fixture.bound.assignment_record), "assignment_id": "other"},
    )

    with pytest.raises(ValueError, match="assignment"):
        replace(fixture.bound, assignment_record=other)


def test_current_blocking_failure_denies_promotion():
    fixture = _fixture(outcome="fail")

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, fixture.cut)

    assert exc_info.value.code == "PROMOTION_EVIDENCE_DID_NOT_PASS"


def test_current_advisory_failure_is_covered_without_becoming_a_blocker():
    fixture = _fixture(impact=GateImpact.ADVISORY, outcome="fail")

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.obligation_evaluation_digests == (
        fixture.bound.evaluation_record.digest(),
    )


def test_blocked_attestation_outcome_is_preserved_in_the_canonical_chain():
    fixture = _fixture(outcome="blocked")

    assert fixture.bound.evidence_records[0].payload["outcome"] == "blocked"
    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, fixture.cut)
    assert exc_info.value.code == "PROMOTION_EVIDENCE_DID_NOT_PASS"


def test_registration_set_digest_binds_the_complete_terminal_record():
    fixture = _fixture()
    changed_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:changed",
        payload=_payload(fixture.attempt.terminal_record),
    )
    changed_attempt = replace(fixture.attempt, terminal_record=changed_terminal)

    assert registration_set_digest((fixture.attempt,)) != registration_set_digest(
        (changed_attempt,)
    )


def test_prevalidated_cut_preserves_the_prior_active_and_accepted_generation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.PREVALIDATED
    assert fixture.cut.active_generation_record == fixture.prior_generation


def test_accepted_contract_requires_both_pointers_to_equal_the_candidate():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    invalid_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:invalid-accepted",
        payload={**_payload(fixture.contract.contract_record), "phase": "accepted"},
    )

    with pytest.raises(ValueError, match="accepted phase"):
        replace(fixture.contract, contract_record=invalid_record)


def test_atomic_cut_rejects_missing_canonical_evaluations():
    fixture = _fixture()

    with pytest.raises(ValueError, match="evaluation_digests"):
        replace(fixture.cut, evaluations=())


def test_cut_must_bind_the_exact_protected_state_record():
    fixture = _fixture()
    alternate_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:alternate",
        payload=_payload(fixture.target_state),
    )
    alternate_cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:alternate",
        payload={
            **_payload(fixture.cut.cut_record),
            "target_protected_state_digest": alternate_state.digest(),
        },
    )
    alternate_cut = replace(
        fixture.cut,
        cut_record=alternate_cut_record,
        target_protected_state_record=alternate_state,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, alternate_cut)
    assert exc_info.value.code == "PROMOTION_TARGET_STATE_MISMATCH"


def test_not_applicable_requires_a_current_false_predicate_proof():
    fixture = _fixture(not_applicable=True)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.authoritative is False
    assert fixture.bound.evidence_records[0].kind == "predicate_proof"


def test_failed_attestation_cannot_be_relabelled_as_not_applicable():
    fixture = _fixture(outcome="fail")
    payload = {
        **_payload(fixture.bound.evaluation_record),
        "applicability": "not_applicable",
        "outcome": "not_applicable",
    }

    with pytest.raises(RecordValidationError):
        ControlRecord.build(
            kind="evaluation",
            record_id="evaluation:false-exemption",
            payload=payload,
        )


def test_preassembly_evidence_requires_a_verified_inclusion_edge_without_relabelling():
    fixture = _fixture(preassembly=True)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.authoritative is False
    assert fixture.bound.context_record.payload["context_type"] == "preassembly_profile"
    with pytest.raises((TypeError, ValueError), match="inclusion_edge_record"):
        replace(fixture.bound, inclusion_edge_record=None)


def test_complete_semantics_backed_by_fake_authority_remain_nonpromotional():
    fixture = _fixture()
    authority = InMemoryAuthority()
    authority.append_record(fixture.attempt.attempt_digest, kind="attempt")

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(fixture.contract, fixture.cut, authority.evidence_view())

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"
