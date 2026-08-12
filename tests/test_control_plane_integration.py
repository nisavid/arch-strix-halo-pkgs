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
    OperationObligation,
    PromotionAuthorityChallenge,
    PromotionContract,
    PromotionDenied,
    PromotionObligation,
    PromotionPhase,
    RecordValidationError,
    RegisteredAttempt,
    RegisteredOperation,
    admit_promotion,
    assess_operation_obligations,
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


def _generation(
    record_id: str,
    generation_id: str,
    seed: str,
    *,
    generation_class: str = "c",
) -> ControlRecord:
    return ControlRecord.build(
        kind="generation",
        record_id=record_id,
        payload={
            "artifact_digests": [digest(seed)],
            "generation_id": generation_id,
            "input_closure_digest": digest("a"),
            "manifest_digest": digest("b"),
            "generation_class": generation_class,
        },
    )


def _build_registered_operation(
    *,
    subject_digest: str,
    context_digest: str,
    candidate_generation: ControlRecord,
    target_state: ControlRecord,
    operation_id: str = "blocking-scenario-1",
    operation_kind: str = "blocking_scenario",
    subject_kind: str = "gate_occurrence",
    lifecycle_phase: str = "accepted",
    target_kind: str = "live_root",
    target_id: str = "reference-host",
    generation_class: str = "c",
    generation_binding: dict[str, object] | None = None,
    intent_sequence: int = 4,
    terminal_sequence: int = 5,
    outcome: str = "succeeded",
    poststate_digest: str | None = None,
) -> RegisteredOperation:
    intent = ControlRecord.build(
        kind="intent",
        record_id=f"intent:{operation_id}",
        payload={
            "actor_identity_digest": digest("0"),
            "context_digest": context_digest,
            "intent_id": operation_id,
            "intent_type": "critical_operation",
            "journal_sequence": intent_sequence,
            "operation_plan_digest": digest("3"),
            "registered_at": "2026-08-12T10:10:30Z",
            "subject_digest": subject_digest,
        },
    )
    operation = ControlRecord.build(
        kind="operation",
        record_id=f"operation:{operation_id}",
        payload={
            "authority_head_digest": digest("9"),
            "declared_effects": [
                {
                    "classification": "poststate_observable",
                    "effect_id": "scenario-result",
                    "projection_digest": digest("8"),
                }
            ],
            "expected_protected_state_digest": digest("1"),
            "generation_binding": generation_binding
            or {
                "generation_digest": candidate_generation.digest(),
                "mode": "required_generation",
            },
            "generation_class": generation_class,
            "intended_protected_state_digest": target_state.digest(),
            "intent_digest": intent.digest(),
            "lifecycle_phase": lifecycle_phase,
            "operation_id": operation_id,
            "operation_kind": operation_kind,
            "plan_digest": digest("3"),
            "recovery_contract_digest": digest("4"),
            "recovery_target_digest": digest("5"),
            "subject_digest": subject_digest,
            "subject_kind": subject_kind,
            "target_id": target_id,
            "target_kind": target_kind,
            "terminal_validator_digest": digest("6"),
        },
    )
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id=f"terminal:{operation_id}",
        payload={
            "completed_at": "2026-08-12T10:11:00Z",
            "journal_sequence": terminal_sequence,
            "operation_digest": operation.digest(),
            "outcome": outcome,
            "poststate_digest": poststate_digest or target_state.digest(),
            "terminal_type": "critical_operation",
            "validator_attestation_digests": [digest("7")],
        },
    )
    return RegisteredOperation(
        intent_record=intent,
        operation_record=operation,
        terminal_record=terminal,
    )


def _operation_obligation(
    operation: RegisteredOperation,
    *,
    obligation_id: str,
) -> OperationObligation:
    payload = operation.operation_record.payload
    record = ControlRecord.build(
        kind="operation_obligation",
        record_id=f"operation-obligation:{obligation_id}",
        payload={
            "generation_binding": dict(payload["generation_binding"]),
            "generation_class": payload["generation_class"],
            "intent_digest": operation.intent_record.digest(),
            "lifecycle_phase": payload["lifecycle_phase"],
            "obligation_id": obligation_id,
            "operation_kind": payload["operation_kind"],
            "subject_digest": payload["subject_digest"],
            "subject_kind": payload["subject_kind"],
            "target_id": payload["target_id"],
            "target_kind": payload["target_kind"],
        },
    )
    return OperationObligation(record)


def _registered_operation(
    fixture: Fixture,
    *,
    intent_sequence: int = 4,
    outcome: str = "succeeded",
    poststate_digest: str | None = None,
) -> RegisteredOperation:
    obligation = fixture.contract.operation_obligations[0].obligation_record.payload
    return _build_registered_operation(
        subject_digest=obligation["subject_digest"],
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        operation_id="blocking-scenario-1",
        operation_kind=obligation["operation_kind"],
        subject_kind=obligation["subject_kind"],
        lifecycle_phase=fixture.contract.phase.value,
        target_kind=obligation["target_kind"],
        target_id=obligation["target_id"],
        intent_sequence=intent_sequence,
        outcome=outcome,
        poststate_digest=poststate_digest,
    )


def _cut_with_operation(
    fixture: Fixture,
    operation: RegisteredOperation,
) -> AtomicEvidenceCut:
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:with-operation",
        payload={
            **_payload(fixture.cut.cut_record),
            "complete_through_sequence": 5,
            "operation_digests": [operation.operation_digest],
            "operation_terminal_digests": [operation.terminal_digest],
        },
    )
    return replace(fixture.cut, cut_record=cut_record, operations=(operation,))


@dataclass(frozen=True)
class Fixture:
    contract: PromotionContract
    cut: AtomicEvidenceCut
    bound: BoundEvaluation
    attempt: RegisteredAttempt
    obligation: PromotionObligation
    requirements: ControlRecord
    validation_contract: ControlRecord
    candidate_generation: ControlRecord
    prior_generation: ControlRecord
    target: ControlRecord
    target_state: ControlRecord


class RecordingPromotionAuthority:
    authority_adapter_identity_digest = digest("1")
    authority_view_digest = digest("2")

    def __init__(self, *, proof_changes: dict[str, object] | None = None):
        self.proof_changes = proof_changes or {}
        self.challenge: PromotionAuthorityChallenge | None = None

    def verify_promotion_cut(
        self,
        challenge: PromotionAuthorityChallenge,
    ) -> ControlRecord:
        self.challenge = challenge
        payload = {
            "atomic_evidence_cut_digest": challenge.atomic_evidence_cut_digest,
            "attempt_digests": list(challenge.attempt_digests),
            "authority_adapter_identity_digest": (
                challenge.authority_adapter_identity_digest
            ),
            "authority_head_digest": challenge.authority_head_digest,
            "authority_manifest_digest": challenge.authority_manifest_digest,
            "authority_view_digest": challenge.authority_view_digest,
            "complete_through_sequence": challenge.complete_through_sequence,
            "completeness_proof_digest": challenge.completeness_proof_digest,
            "evaluation_digests": list(challenge.evaluation_digests),
            "fork_proof_digest": challenge.fork_proof_digest,
            "inclusion_edge_digests": list(challenge.inclusion_edge_digests),
            "journal_head_digest": challenge.journal_head_digest,
            "operation_digests": list(challenge.operation_digests),
            "operation_terminal_digests": list(
                challenge.operation_terminal_digests
            ),
            "promotion_contract_digest": challenge.promotion_contract_digest,
            "proof_id": "promotion-proof-1",
            "validation_contract_digest": challenge.validation_contract_digest,
            "verified_at": "2026-08-12T10:12:00Z",
            "verifier_identity_digest": digest("3"),
            **self.proof_changes,
        }
        return ControlRecord.build(
            kind="promotion_authority_proof",
            record_id="promotion-authority-proof:1",
            payload=payload,
        )


def _fixture(
    *,
    impact: GateImpact = GateImpact.BLOCKING,
    outcome: str = "pass",
    phase: PromotionPhase = PromotionPhase.ACCEPTED,
    preassembly: bool = False,
    not_applicable: bool = False,
    scenario_gate: bool | None = None,
    scenario_target_kind: str | None = None,
    scenario_target_id: str = "reference-host",
    include_repository_publication: bool = False,
    include_root_installation: bool = False,
) -> Fixture:
    if scenario_gate is None:
        scenario_gate = impact is GateImpact.BLOCKING
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
            "generation_digest": candidate.digest(),
            "observed_at": "2026-08-12T09:15:00Z",
            "projection_id": "active-generation",
            "state_digest": digest("7"),
            "target_digest": target.digest(),
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
    assignment_set = ControlRecord.build(
        kind="assignment_set",
        record_id="assignment-set:w0",
        payload={
            "assignment_digests": [assignment.digest()],
            "requirements_digest": requirements.digest(),
        },
    )
    validation_contract = ControlRecord.build(
        kind="validation_contract",
        record_id="validation-contract:w0",
        payload={
            "approval_digest": digest("4"),
            "assignments_digest": assignment_set.digest(),
            "authorization_policy_digest": digest("5"),
            "contract_id": "w0-validation-contract",
            "requirements_digest": requirements.digest(),
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
            "contract_digest": validation_contract.digest(),
            "generation_digest": candidate.digest(),
        }
        context_type = "active_contract"
    context = ControlRecord.build(
        kind="validation_context",
        record_id="context:w0-candidate",
        payload={
            "assignments_digest": assignment_set.digest(),
            "context_id": "w0-candidate",
            "context_type": context_type,
            "requirements_digest": requirements.digest(),
            **context_bindings,
        },
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
                "active_contract_digest": validation_contract.digest(),
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
    promotion_target_kind = (
        "isolated_root"
        if phase is PromotionPhase.PREVALIDATED
        else "package_repository"
        if phase is PromotionPhase.PUBLISHED
        else "live_root"
    )
    operations: list[RegisteredOperation] = []
    operation_obligations: list[OperationObligation] = []
    scenario_operation_obligation: OperationObligation | None = None
    next_operation_sequence = 4
    if scenario_gate:
        scenario_operation = _build_registered_operation(
            subject_digest=intent.digest(),
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=target_state,
            lifecycle_phase=phase.value,
            target_kind=scenario_target_kind or promotion_target_kind,
            target_id=scenario_target_id,
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
        )
        next_operation_sequence += 2
        operations.append(scenario_operation)
        scenario_operation_obligation = _operation_obligation(
            scenario_operation,
            obligation_id="blocking-scenario-1",
        )
        operation_obligations.append(scenario_operation_obligation)
    if include_repository_publication:
        publication = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=target_state,
            operation_id="repository-publication-1",
            operation_kind="repository_publication",
            lifecycle_phase=phase.value,
            target_kind="package_repository",
            target_id=target.payload["identity_id"],
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
        )
        next_operation_sequence += 2
        operations.append(publication)
        operation_obligations.append(
            _operation_obligation(
                publication,
                obligation_id="repository-publication-1",
            )
        )
    if include_root_installation:
        installation = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=target_state,
            operation_id="package-installation-1",
            operation_kind="package_installation",
            lifecycle_phase=phase.value,
            target_kind="live_root",
            target_id=target.payload["identity_id"],
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
        )
        next_operation_sequence += 2
        operations.append(installation)
        operation_obligations.append(
            _operation_obligation(
                installation,
                obligation_id="package-installation-1",
            )
        )
    obligation_payload = {
        "assignment_digest": assignment.digest(),
        "impact": impact.value,
        "obligation_id": "control-plane",
        "occurrence_digest": intent.digest(),
    }
    if scenario_operation_obligation is not None:
        obligation_payload["scenario_operation_obligation_digest"] = (
            scenario_operation_obligation.obligation_digest
        )
    obligation_record = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion-obligation:control-plane",
        payload=obligation_payload,
    )
    obligation = PromotionObligation(obligation_record)
    operation_obligations_tuple = tuple(operation_obligations)
    operations_tuple = tuple(operations)
    operation_obligation_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation-obligation-set:w0",
        payload={
            "obligation_digests": [
                item.obligation_digest for item in operation_obligations_tuple
            ],
            "requirements_digest": requirements.digest(),
        },
    )
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
            "operation_obligation_set_digest": operation_obligation_set.digest(),
            "phase": phase.value,
            "requirements_digest": requirements.digest(),
            "target_digest": target.digest(),
            "target_kind": promotion_target_kind,
            "target_protected_state_digest": target_state.digest(),
            "validation_contract_digest": validation_contract.digest(),
        },
    )
    contract = PromotionContract(
        requirements_record=requirements,
        assignment_set_record=assignment_set,
        operation_obligation_set_record=operation_obligation_set,
        validation_contract_record=validation_contract,
        generation_record=candidate,
        target_record=target,
        target_protected_state_record=target_state,
        contract_record=contract_record,
        obligations=(obligation,),
        operation_obligations=operation_obligations_tuple,
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
            "complete_through_sequence": max(3, next_operation_sequence - 1),
            "completeness_proof_digest": digest("b"),
            "contract_digest": contract_record.digest(),
            "evaluation_digests": [evaluation.digest()],
            "fork_proof_digest": digest("c"),
            "generation_digest": candidate.digest(),
            "inclusion_edge_digests": (
                [inclusion_edge.digest()] if inclusion_edge is not None else []
            ),
            "journal_head_digest": digest("d"),
            "operation_digests": [
                item.operation_digest for item in operations_tuple
            ],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations_tuple
            ],
            "phase": phase.value,
            "registration_set_digest": registration_set_digest(
                (registered_attempt,)
            ),
            "target_digest": target.digest(),
            "target_kind": promotion_target_kind,
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
        operations=operations_tuple,
    )
    return Fixture(
        contract=contract,
        cut=cut,
        bound=bound,
        attempt=registered_attempt,
        obligation=obligation,
        requirements=requirements,
        validation_contract=validation_contract,
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


def test_promotion_contract_requires_canonical_assignment_and_operation_sets():
    fixture = _fixture()

    assert fixture.validation_contract.payload["assignments_digest"] != digest("b")
    assert "operation_obligation_set_digest" in fixture.contract.contract_record.payload


def test_blocking_scenario_requires_an_explicit_acyclic_gate_link():
    fixture = _fixture()
    unlinked_obligation_record = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion-obligation:control-plane:unlinked",
        payload={
            key: value
            for key, value in _payload(fixture.obligation.obligation_record).items()
            if key != "scenario_operation_obligation_digest"
        },
    )
    unlinked_obligation = PromotionObligation(unlinked_obligation_record)
    unlinked_contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:w0:unlinked",
        payload={
            **_payload(fixture.contract.contract_record),
            "obligation_digests": [unlinked_obligation.obligation_digest],
        },
    )

    with pytest.raises(ValueError, match="explicit scenario-gate link"):
        replace(
            fixture.contract,
            contract_record=unlinked_contract_record,
            obligations=(unlinked_obligation,),
        )

    assert "promotion_obligation_digest" not in (
        fixture.contract.operation_obligations[0].obligation_record.payload
    )


def test_blocking_occurrence_requires_one_exact_critical_operation():
    fixture = _fixture()
    incomplete_cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:missing-operation",
        payload={
            **_payload(fixture.cut.cut_record),
            "operation_digests": [],
            "operation_terminal_digests": [],
        },
    )
    incomplete_cut = replace(
        fixture.cut,
        cut_record=incomplete_cut_record,
        operations=(),
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, incomplete_cut)

    assert exc_info.value.code == "PROMOTION_OPERATIONS_INCOMPLETE"


def test_atomic_cut_binds_the_complete_critical_operation_set():
    fixture = _fixture()
    operation = _registered_operation(fixture)
    cut = _cut_with_operation(fixture, operation)

    assessment = assess_promotion_cut(fixture.contract, cut)

    assert assessment.authoritative is False
    assert cut.cut_record.payload["operation_digests"] == (
        operation.operation_digest,
    )
    assert cut.cut_record.payload["operation_terminal_digests"] == (
        operation.terminal_digest,
    )


def test_critical_operation_must_bind_the_cut_authority_head():
    fixture = _fixture()
    operation = _registered_operation(fixture)
    changed_operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:blocking-scenario:foreign-authority",
        payload={
            **_payload(operation.operation_record),
            "authority_head_digest": digest("8"),
        },
    )
    changed_terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:blocking-scenario:foreign-authority",
        payload={
            **_payload(operation.terminal_record),
            "operation_digest": changed_operation_record.digest(),
        },
    )
    changed_operation = replace(
        operation,
        operation_record=changed_operation_record,
        terminal_record=changed_terminal_record,
    )
    cut = _cut_with_operation(fixture, changed_operation)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


@pytest.mark.parametrize(
    "changes",
    [
        {
            "generation_binding": {
                "generation_digest": digest("8"),
                "mode": "required_generation",
            }
        },
        {"lifecycle_phase": "active"},
        {"target_id": "different-service", "target_kind": "service"},
        {"operation_kind": "recovery", "subject_kind": "control_record"},
    ],
)
def test_critical_operation_matches_every_exact_obligation_coordinate(changes):
    fixture = _fixture()
    operation = fixture.cut.operations[0]
    changed_operation_record = ControlRecord.build(
        kind="operation",
        record_id=f"operation:blocking-scenario:changed:{len(changes)}",
        payload={**_payload(operation.operation_record), **changes},
    )
    changed_terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id=f"terminal:blocking-scenario:changed:{len(changes)}",
        payload={
            **_payload(operation.terminal_record),
            "operation_digest": changed_operation_record.digest(),
        },
    )
    changed_operation = replace(
        operation,
        operation_record=changed_operation_record,
        terminal_record=changed_terminal_record,
    )
    cut = _cut_with_operation(fixture, changed_operation)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_critical_operation_generation_class_is_an_exact_obligation_coordinate():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        include_repository_publication=True,
    )
    operation = fixture.cut.operations[0]
    foundation_operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:repository-publication:foundation-substitution",
        payload={
            **_payload(operation.operation_record),
            "generation_class": "f",
        },
    )
    foundation_terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:repository-publication:foundation-substitution",
        payload={
            **_payload(operation.terminal_record),
            "operation_digest": foundation_operation_record.digest(),
        },
    )
    foundation_operation = replace(
        operation,
        operation_record=foundation_operation_record,
        terminal_record=foundation_terminal_record,
    )
    cut = _cut_with_operation(fixture, foundation_operation)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_critical_operation_cannot_substitute_another_intent_for_the_same_subject():
    fixture = _fixture()
    operation = fixture.cut.operations[0]
    substituted_intent = ControlRecord.build(
        kind="intent",
        record_id="intent:blocking-scenario:substituted",
        payload=_payload(operation.intent_record),
    )
    substituted_operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:blocking-scenario:substituted",
        payload={
            **_payload(operation.operation_record),
            "intent_digest": substituted_intent.digest(),
        },
    )
    substituted_terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:blocking-scenario:substituted",
        payload={
            **_payload(operation.terminal_record),
            "operation_digest": substituted_operation_record.digest(),
        },
    )
    substituted = RegisteredOperation(
        intent_record=substituted_intent,
        operation_record=substituted_operation_record,
        terminal_record=substituted_terminal_record,
    )
    cut = _cut_with_operation(fixture, substituted)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_generic_operation_matcher_allows_two_intents_for_the_same_subject():
    fixture = _fixture()
    subject_digest = fixture.attempt.intent_record.digest()
    first = _build_registered_operation(
        subject_digest=subject_digest,
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        operation_id="blocking-scenario-first",
        intent_sequence=4,
        terminal_sequence=5,
    )
    second = _build_registered_operation(
        subject_digest=subject_digest,
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        operation_id="blocking-scenario-second",
        intent_sequence=6,
        terminal_sequence=7,
    )
    obligations = (
        _operation_obligation(first, obligation_id="blocking-scenario-first"),
        _operation_obligation(second, obligation_id="blocking-scenario-second"),
    )

    matched = assess_operation_obligations(
        obligations,
        (first, second),
        authority_head_digest=digest("9"),
    )

    assert matched == (first.operation_digest, second.operation_digest)
    assert first.intent_record.digest() != second.intent_record.digest()
    assert (
        first.operation_record.payload["subject_digest"]
        == second.operation_record.payload["subject_digest"]
    )


def test_generic_operation_matcher_covers_foundation_and_b0_authority_rows():
    foundation = _generation(
        "generation:foundation",
        "foundation-f",
        "e",
        generation_class="f",
    )
    baseline = _generation(
        "generation:baseline",
        "baseline-b0",
        "f",
        generation_class="b0",
    )
    target = _identity("identity:generic-target", "generic-target", "target", "1")

    def protected_state(
        record_id: str,
        generation: ControlRecord,
        seed: str,
    ) -> ControlRecord:
        return ControlRecord.build(
            kind="protected_state",
            record_id=record_id,
            payload={
                "fence_epoch": 1,
                "generation_digest": generation.digest(),
                "observed_at": "2026-08-12T09:15:00Z",
                "projection_id": "generic-projection",
                "state_digest": digest(seed),
                "target_digest": target.digest(),
            },
        )

    foundation_operation = _build_registered_operation(
        subject_digest=foundation.digest(),
        subject_kind="generation",
        context_digest=digest("2"),
        candidate_generation=foundation,
        target_state=protected_state("protected-state:foundation", foundation, "3"),
        operation_id="foundation-installation",
        operation_kind="package_installation",
        lifecycle_phase="foundation_validation",
        target_kind="isolated_root",
        target_id="foundation-root",
        generation_class="f",
        intent_sequence=1,
        terminal_sequence=2,
    )
    baseline_operation = _build_registered_operation(
        subject_digest=digest("4"),
        subject_kind="composite_authority",
        context_digest=digest("5"),
        candidate_generation=baseline,
        target_state=protected_state("protected-state:baseline", baseline, "6"),
        operation_id="baseline-capture",
        operation_kind="composite_authority_transition",
        lifecycle_phase="captured",
        target_kind="composite_register",
        target_id="authority-register",
        generation_class="b0",
        generation_binding={
            "generation_digest": baseline.digest(),
            "mode": "b0_capture_sentinel",
            "sentinel_digest": digest("7"),
        },
        intent_sequence=3,
        terminal_sequence=4,
    )
    obligations = (
        _operation_obligation(
            foundation_operation,
            obligation_id="foundation-installation",
        ),
        _operation_obligation(
            baseline_operation,
            obligation_id="baseline-capture",
        ),
    )

    matched = assess_operation_obligations(
        obligations,
        (foundation_operation, baseline_operation),
        authority_head_digest=digest("9"),
    )

    assert matched == (
        foundation_operation.operation_digest,
        baseline_operation.operation_digest,
    )


def test_published_blocking_proof_can_require_repository_publication_without_scenario_mutation():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        include_repository_publication=True,
    )

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.PUBLISHED
    assert fixture.obligation.impact is GateImpact.BLOCKING
    assert fixture.obligation.scenario_operation_obligation_digest is None
    assert tuple(
        item.obligation_record.payload["operation_kind"]
        for item in fixture.contract.operation_obligations
    ) == ("repository_publication",)


def test_promotion_contract_is_a_c_generation_consumer_of_generic_obligations():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    foundation = _generation(
        "generation:foundation:not-promotion",
        "foundation-f",
        "e",
        generation_class="f",
    )
    foundation_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:foundation:not-promotion",
        payload={
            **_payload(fixture.target_state),
            "generation_digest": foundation.digest(),
        },
    )
    foundation_contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:foundation:not-promotion",
        payload={
            **_payload(fixture.contract.contract_record),
            "generation_digest": foundation.digest(),
            "target_protected_state_digest": foundation_state.digest(),
        },
    )

    with pytest.raises(ValueError, match="C generation"):
        replace(
            fixture.contract,
            generation_record=foundation,
            target_protected_state_record=foundation_state,
            contract_record=foundation_contract_record,
        )


def test_phase_total_operations_can_bind_live_root_and_service_targets():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
        include_root_installation=True,
    )

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.ACTIVE
    assert {
        (
            item.obligation_record.payload["target_kind"],
            item.obligation_record.payload["target_id"],
        )
        for item in fixture.contract.operation_obligations
    } == {
        ("service", "inference-service"),
        ("live_root", "reference-host"),
    }
    assert fixture.contract.target.kind.value == "live_root"


def test_failed_critical_operation_cannot_satisfy_promotion():
    fixture = _fixture()
    operation = _registered_operation(
        fixture,
        outcome="failed",
        poststate_digest=digest("0"),
    )
    cut = _cut_with_operation(fixture, operation)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_DID_NOT_PASS"


def test_critical_operation_intent_must_precede_its_terminal_in_the_journal():
    fixture = _fixture()

    with pytest.raises(ValueError, match="journal order"):
        _registered_operation(fixture, intent_sequence=6)


def test_active_context_binds_a_validation_contract_distinct_from_requirements():
    fixture = _fixture()

    assert fixture.validation_contract.digest() != fixture.requirements.digest()
    assert (
        fixture.validation_contract.payload["requirements_digest"]
        == fixture.requirements.digest()
    )
    assert (
        fixture.bound.context_record.payload["contract_digest"]
        == fixture.validation_contract.digest()
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


def test_registered_attempt_orders_timestamps_as_instants_not_wire_strings():
    fixture = _fixture()
    late_intent = ControlRecord.build(
        kind="intent",
        record_id="intent:control-plane:late",
        payload={
            **_payload(fixture.attempt.intent_record),
            "registered_at": "2026-08-12T09:40:00.1Z",
        },
    )
    early_attempt = ControlRecord.build(
        kind="attempt",
        record_id="attempt:control-plane:early",
        payload={
            **_payload(fixture.attempt.attempt_record),
            "intent_digest": late_intent.digest(),
            "started_at": "2026-08-12T09:40:00Z",
        },
    )
    obligation = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion-obligation:control-plane:late",
        payload={
            **_payload(fixture.attempt.obligation_record),
            "occurrence_digest": late_intent.digest(),
        },
    )
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:late-intent",
        payload={
            **_payload(fixture.attempt.terminal_record),
            "attempt_digest": early_attempt.digest(),
        },
    )

    with pytest.raises(ValueError, match="timestamps"):
        replace(
            fixture.attempt,
            obligation_record=obligation,
            intent_record=late_intent,
            attempt_record=early_attempt,
            terminal_record=terminal,
        )


def test_evidence_observation_cannot_precede_attempt_start():
    fixture = _fixture()
    early_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:control-plane:pre-attempt",
        payload={
            **_payload(fixture.bound.evidence_records[0]),
            "observed_at": "2026-08-12T09:35:00Z",
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:control-plane:pre-attempt",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "attestation_digests": [early_attestation.digest()],
        },
    )

    with pytest.raises(ValueError, match="attempt start"):
        replace(
            fixture.bound,
            evidence_records=(early_attestation,),
            evaluation_record=evaluation,
        )


def test_prevalidated_cut_preserves_the_prior_active_and_accepted_generation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.PREVALIDATED
    assert fixture.cut.active_generation_record == fixture.prior_generation
    assert (
        fixture.cut.target_protected_state_record.payload["generation_digest"]
        == fixture.candidate_generation.digest()
    )


@pytest.mark.parametrize(
    ("phase", "accepted_is_candidate", "active_is_candidate"),
    [
        (PromotionPhase.PUBLISHED, False, False),
        (PromotionPhase.PREVALIDATED, False, False),
        (PromotionPhase.ACTIVE, False, True),
        (PromotionPhase.ACCEPTED, True, True),
    ],
)
def test_target_state_binds_candidate_independently_of_global_pointers(
    phase,
    accepted_is_candidate,
    active_is_candidate,
):
    fixture = _fixture(
        phase=phase,
        scenario_gate=False if phase is PromotionPhase.PUBLISHED else None,
    )

    assert (
        fixture.cut.target_protected_state_record.payload["generation_digest"]
        == fixture.candidate_generation.digest()
    )
    assert (
        fixture.cut.accepted_generation_record == fixture.candidate_generation
    ) is accepted_is_candidate
    assert (
        fixture.cut.active_generation_record == fixture.candidate_generation
    ) is active_is_candidate


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


def test_blocked_attempt_and_failed_terminal_cannot_satisfy_a_blocking_pass():
    fixture = _fixture()
    blocked_attempt_record = ControlRecord.build(
        kind="attempt",
        record_id="attempt:control-plane:blocked",
        payload={
            **_payload(fixture.attempt.attempt_record),
            "decision": "blocked",
        },
    )
    failed_terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:failed",
        payload={
            **_payload(fixture.attempt.terminal_record),
            "attempt_digest": blocked_attempt_record.digest(),
            "outcome": "failed",
        },
    )
    blocked_attempt = replace(
        fixture.attempt,
        attempt_record=blocked_attempt_record,
        terminal_record=failed_terminal_record,
    )
    bound = replace(fixture.bound, attempt_record=blocked_attempt_record)
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:blocked",
        payload={
            **_payload(fixture.cut.cut_record),
            "attempt_digests": [blocked_attempt_record.digest()],
            "registration_set_digest": registration_set_digest((blocked_attempt,)),
        },
    )
    cut = replace(
        fixture.cut,
        cut_record=cut_record,
        attempts=(blocked_attempt,),
        evaluations=(bound,),
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_ATTEMPT_DID_NOT_PASS"


def test_preassembly_evidence_requires_a_verified_inclusion_edge_without_relabelling():
    fixture = _fixture(preassembly=True)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.authoritative is False
    assert fixture.bound.context_record.payload["context_type"] == "preassembly_profile"
    assert fixture.bound.inclusion_edge_record is not None
    assert (
        fixture.bound.inclusion_edge_record.payload["active_contract_digest"]
        == fixture.validation_contract.digest()
    )
    with pytest.raises((TypeError, ValueError), match="inclusion_edge_record"):
        replace(fixture.bound, inclusion_edge_record=None)


def test_preassembly_inclusion_cannot_be_verified_before_its_evaluation():
    fixture = _fixture(preassembly=True)
    early_edge = ControlRecord.build(
        kind="inclusion_edge",
        record_id="inclusion-edge:control-plane:early",
        payload={
            **_payload(fixture.bound.inclusion_edge_record),
            "verified_at": "2026-08-12T09:59:59Z",
        },
    )

    with pytest.raises(ValueError, match="inclusion edge verification"):
        replace(fixture.bound, inclusion_edge_record=early_edge)


def test_complete_semantics_backed_by_fake_authority_remain_nonpromotional():
    fixture = _fixture()
    authority = InMemoryAuthority()
    authority.append_record(fixture.attempt.attempt_digest, kind="attempt")

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(fixture.contract, fixture.cut, authority.evidence_view())

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"


def test_exact_authority_proof_still_cannot_promote_without_production_authority():
    fixture = _fixture()
    operation = _registered_operation(fixture)
    cut = _cut_with_operation(fixture, operation)
    authority = RecordingPromotionAuthority()

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(fixture.contract, cut, authority)

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"
    assert authority.challenge is not None
    assert authority.challenge.atomic_evidence_cut_digest == cut.cut_record_digest
    assert authority.challenge.promotion_contract_digest == fixture.contract.contract_digest
    assert (
        authority.challenge.validation_contract_digest
        == fixture.validation_contract.digest()
    )
    assert (
        authority.challenge.authority_adapter_identity_digest
        == authority.authority_adapter_identity_digest
    )
    assert authority.challenge.authority_view_digest == authority.authority_view_digest
    assert authority.challenge.operation_digests == (operation.operation_digest,)
    assert authority.challenge.operation_terminal_digests == (
        operation.terminal_digest,
    )


def test_authority_proof_must_bind_the_exact_cut_and_fork_proof():
    fixture = _fixture()
    authority = RecordingPromotionAuthority(
        proof_changes={"fork_proof_digest": digest("f")}
    )

    with pytest.raises(PromotionDenied) as exc_info:
        admit_promotion(fixture.contract, fixture.cut, authority)

    assert exc_info.value.code == "PROMOTION_AUTHORITY_PROOF_MISMATCH"
