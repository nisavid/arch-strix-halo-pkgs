from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, fields, replace
from itertools import pairwise
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import control_plane
from control_plane import (
    AtomicEvidenceCut,
    BaselineRestorationReceipt,
    BoundEvaluation,
    CompositeAuthorityCheckpoint,
    CompositeAuthorityManifest,
    CompositeChangeSet,
    CompositeRegisterReinstatement,
    ControlRecord,
    CriticalOperationKind,
    DeclaredEffect,
    EffectClass,
    FencedCapability,
    FinalServiceAnchorReceipt,
    GateImpact,
    GenerationBinding,
    GenerationBindingMode,
    GenerationClass,
    LifecycleCheckpoint,
    LifecyclePhase,
    NonPromotionalEvidence,
    OperationBinding,
    OperationObligation,
    OperationRealization,
    OperationRequirement,
    OperationSubject,
    OperationSubjectKind,
    OperationTarget,
    OperationTargetKind,
    PromotionAuthorityChallenge,
    PromotionContract,
    PromotionDenied,
    PromotionObligation,
    PromotionPhase,
    ProtectedStateSnapshot,
    RecordValidationError,
    RecoveryCapability,
    RecoveryMode,
    RegisteredAttempt,
    RegisteredOperation,
    RollbackRecoveryContract,
    ServiceAnchorReceipt,
    StructuralBaselineCapture,
    StructuralFoundationCandidate,
    StructuralLifecycleCandidate,
    TerminalObservation,
    TerminalOutcome,
    admit_promotion,
    assess_operation_obligations,
    assess_promotion_cut,
    build_acceptance_request,
    registration_set_digest,
)
from control_plane.testing import (
    InMemoryAuthority,
    issue_lifecycle_checkpoint_for_testing,
    seal_authority_issued_checkpoint_for_testing,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


class DeceptiveControlRecord(ControlRecord):
    """Masquerade as an operation while retaining subclass dispatch."""

    def __getattribute__(self, name: str) -> object:
        if name == "kind":
            return "operation"
        return super().__getattribute__(name)


def _deceptive_operation_record(record: ControlRecord) -> DeceptiveControlRecord:
    deceptive = object.__new__(DeceptiveControlRecord)
    for field_name in ("kind", "record_id", "payload", "_digest", "signature"):
        object.__setattr__(
            deceptive,
            field_name,
            object.__getattribute__(record, field_name),
        )
    return deceptive


def _payload(record: ControlRecord) -> dict[str, object]:
    return json.loads(record.canonical_bytes())["payload"]


def _reparse(record: ControlRecord) -> ControlRecord:
    return ControlRecord.parse(record.canonical_bytes())


def _bound_with_evaluation(
    bound: BoundEvaluation,
    evaluation_record: ControlRecord,
    evidence_records: tuple[ControlRecord, ...],
) -> BoundEvaluation:
    currency_proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id=f"{bound.currency_proof_record.record_id}:rebound",
        payload={
            **_payload(bound.currency_proof_record),
            "evaluation_digest": evaluation_record.digest(),
        },
    )
    return replace(
        bound,
        evidence_records=tuple(_reparse(record) for record in evidence_records),
        evaluation_record=_reparse(evaluation_record),
        currency_proof_record=currency_proof,
    )


_PHASE_TIMES = {
    PromotionPhase.PUBLISHED: {
        "state": "2026-08-12T06:15:00Z",
        "registered": "2026-08-12T06:30:00Z",
        "scenario_registered": "2026-08-12T06:35:00Z",
        "scenario_capability": "2026-08-12T06:36:00Z",
        "started": "2026-08-12T06:40:00Z",
        "observed": "2026-08-12T06:50:00Z",
        "evaluated": "2026-08-12T07:00:00Z",
        "included": "2026-08-12T07:05:00Z",
        "terminal": "2026-08-12T07:10:00Z",
        "operation_registered": "2026-08-12T07:10:30Z",
        "capability_issued": "2026-08-12T07:10:35Z",
        "operation_observed": "2026-08-12T07:11:00Z",
        "operation_terminal": "2026-08-12T07:11:00Z",
        "currency_checkpoint": "2026-08-12T07:11:05Z",
        "trusted_time": "2026-08-12T07:11:10Z",
        "capability_expires": "2026-08-12T07:12:00Z",
        "proof": "2026-08-12T07:12:00Z",
        "checkpoint": "2026-08-12T07:13:00Z",
    },
    PromotionPhase.PREVALIDATED: {
        "state": "2026-08-12T07:15:00Z",
        "registered": "2026-08-12T07:30:00Z",
        "scenario_registered": "2026-08-12T07:35:00Z",
        "scenario_capability": "2026-08-12T07:36:00Z",
        "started": "2026-08-12T08:11:20Z",
        "observed": "2026-08-12T08:11:25Z",
        "evaluated": "2026-08-12T08:11:30Z",
        "included": "2026-08-12T08:11:32Z",
        "terminal": "2026-08-12T08:11:35Z",
        "operation_registered": "2026-08-12T08:10:30Z",
        "capability_issued": "2026-08-12T08:10:35Z",
        "operation_observed": "2026-08-12T08:11:00Z",
        "operation_terminal": "2026-08-12T08:11:00Z",
        "scenario_operation_observed": "2026-08-12T08:11:36Z",
        "scenario_operation_terminal": "2026-08-12T08:11:37Z",
        "currency_checkpoint": "2026-08-12T08:11:40Z",
        "trusted_time": "2026-08-12T08:11:45Z",
        "capability_expires": "2026-08-12T08:12:00Z",
        "proof": "2026-08-12T08:12:00Z",
        "checkpoint": "2026-08-12T08:13:00Z",
    },
    PromotionPhase.ACTIVE: {
        "state": "2026-08-12T08:15:00Z",
        "registered": "2026-08-12T08:30:00Z",
        "scenario_registered": "2026-08-12T09:10:30Z",
        "scenario_capability": "2026-08-12T09:10:35Z",
        "started": "2026-08-12T09:10:40Z",
        "observed": "2026-08-12T09:10:45Z",
        "evaluated": "2026-08-12T09:10:50Z",
        "included": "2026-08-12T09:10:52Z",
        "terminal": "2026-08-12T09:10:55Z",
        "operation_registered": "2026-08-12T09:10:05Z",
        "capability_issued": "2026-08-12T09:10:06Z",
        "operation_observed": "2026-08-12T09:11:00Z",
        "operation_terminal": "2026-08-12T09:11:00Z",
        "phase_operation_observed": "2026-08-12T09:10:20Z",
        "phase_operation_terminal": "2026-08-12T09:10:20Z",
        "currency_checkpoint": "2026-08-12T09:11:05Z",
        "trusted_time": "2026-08-12T09:11:10Z",
        "capability_expires": "2026-08-12T09:12:00Z",
        "proof": "2026-08-12T09:12:00Z",
        "checkpoint": "2026-08-12T09:13:00Z",
    },
    PromotionPhase.ACCEPTED: {
        "state": "2026-08-12T09:13:01Z",
        "registered": "2026-08-12T09:13:10Z",
        "scenario_registered": "2026-08-12T09:13:20Z",
        "scenario_capability": "2026-08-12T09:13:21Z",
        "started": "2026-08-12T09:13:30Z",
        "observed": "2026-08-12T09:13:35Z",
        "evaluated": "2026-08-12T09:13:40Z",
        "included": "2026-08-12T09:13:42Z",
        "terminal": "2026-08-12T09:13:45Z",
        "operation_registered": "2026-08-12T09:13:20Z",
        "capability_issued": "2026-08-12T09:13:21Z",
        "operation_observed": "2026-08-12T09:14:00Z",
        "operation_terminal": "2026-08-12T09:14:00Z",
        "currency_checkpoint": "2026-08-12T09:14:10Z",
        "trusted_time": "2026-08-12T09:14:10Z",
        "capability_expires": "2026-08-12T09:15:00Z",
        "proof": "2026-08-12T09:14:20Z",
        "checkpoint": "2026-08-12T09:14:30Z",
    },
}


def _identity(
    record_id: str,
    identity_id: str,
    identity_type: str,
    seed: str,
    *,
    roles: list[str] | None = None,
):
    if roles is None and identity_type in {"principal", "validator"}:
        roles = ["validator"]
    return ControlRecord.build(
        kind="identity",
        record_id=record_id,
        payload={
            "authority_digest": digest(seed),
            "identity_id": identity_id,
            "identity_type": identity_type,
            **({"roles": roles} if roles is not None else {}),
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


def _protected_state(
    record_id: str,
    *,
    generation: ControlRecord,
    target: ControlRecord,
    phase: str,
    seed: str,
    observed_at: str = "2026-08-12T09:15:00Z",
    fence_epoch: int = 7,
    target_kind: str = "live_root",
) -> ControlRecord:
    return ControlRecord.build(
        kind="protected_state",
        record_id=record_id,
        payload={
            "fence_epoch": fence_epoch,
            "generation_digest": generation.digest(),
            "lifecycle_phase": phase,
            "observed_at": observed_at,
            "projection_id": "active-generation",
            "state_digest": digest(seed),
            "target_digest": target.digest(),
            "target_kind": target_kind,
        },
    )


def _target_prestate_observation(
    record_id: str,
    *,
    source_state: ControlRecord,
    target_record: ControlRecord,
    target_kind: str,
    observed_at: str,
) -> ControlRecord:
    return ControlRecord.build(
        kind="protected_state",
        record_id=record_id,
        payload={
            **_payload(source_state),
            "observed_at": observed_at,
            "target_digest": target_record.digest(),
            "target_kind": target_kind,
        },
    )


def _captured_checkpoint(*, target: ControlRecord) -> StructuralBaselineCapture:
    baseline = _generation(
        "generation:baseline",
        "captured-b0",
        "0",
        generation_class="b0",
    )
    baseline_state = _protected_state(
        "protected-state:captured",
        generation=baseline,
        target=target,
        phase="captured",
        seed="0",
        observed_at="2026-08-12T05:55:00Z",
        fence_epoch=1,
    )
    capture_actor = _identity(
        "identity:baseline-capture-operator",
        "baseline-capture-operator",
        "principal",
        "1",
    )
    capture_separation = ControlRecord.build(
        kind="separation_policy",
        record_id="separation-policy:baseline-capture",
        payload={
            "forbidden_actor_identity_digests": [],
            "policy_id": "baseline-capture-separation",
            "required_actor_roles": ["validator"],
        },
    )
    capture_policy = ControlRecord.build(
        kind="authorization",
        record_id="authorization:baseline-capture",
        payload={
            "action": "capture_baseline",
            "allowed_actor_identity_digests": [capture_actor.digest()],
            "allowed_actor_roles": ["validator"],
            "approver_roles": ["validator"],
            "policy_id": "baseline-capture",
            "recovery_root_digest": digest("1"),
            "separation_policy_digest": capture_separation.digest(),
            "subject_kind": "protected_state",
            "validity_policy_digest": digest("2"),
        },
    )
    capture_authorization = ControlRecord.build(
        kind="approval",
        record_id="approval:capture-baseline",
        payload={
            "action": "capture_baseline",
            "actor_identity_digest": capture_actor.digest(),
            "actor_role": "validator",
            "authorization_digest": capture_policy.digest(),
            "decided_at": "2026-08-12T05:59:00Z",
            "decision": "approved",
            "subject_digest": baseline_state.digest(),
        },
    )
    checkpoint = StructuralBaselineCapture(
        structural_record=ControlRecord.build(
            kind="lifecycle_checkpoint",
            record_id="lifecycle-checkpoint:captured",
            payload={
                "checkpoint_id": "captured-b0",
                "established_at": "2026-08-12T06:00:00Z",
                "generation_class": "b0",
                "generation_digest": baseline.digest(),
                "phase": "captured",
                "root_authorization_digest": capture_authorization.digest(),
                "target_digest": target.digest(),
                "target_protected_state_digest": baseline_state.digest(),
            },
        ),
        generation_record=baseline,
        target_record=target,
        target_protected_state_record=baseline_state,
        capture_approval_record=capture_authorization,
        capture_authorization_record=capture_policy,
        capture_actor_identity_record=capture_actor,
        capture_separation_policy_record=capture_separation,
    )
    return checkpoint


def _build_registered_operation(
    *,
    subject_digest: str,
    context_digest: str,
    candidate_generation: ControlRecord,
    target_state: ControlRecord,
    target_record: ControlRecord | None = None,
    expected_state_record: ControlRecord | None = None,
    bind_intended_state: bool = False,
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
    registered_at: str = "2026-08-12T10:10:30Z",
    issued_at: str = "2026-08-12T10:10:35Z",
    attested_at: str = "2026-08-12T10:10:45Z",
    completed_at: str = "2026-08-12T10:11:00Z",
    expires_at: str = "2026-08-12T10:12:00Z",
    recovery_contract_digest: str = digest("4"),
    recovery_target_digest: str | None = None,
    recovery_predecessor_operation: RegisteredOperation | None = None,
    recovery_owner_identity_record: ControlRecord | None = None,
) -> RegisteredOperation:
    if target_record is None:
        target_record = _identity(
            f"identity:operation-target:{operation_id}",
            target_id,
            "target",
            "6",
        )
    if (
        target_state.payload["target_digest"] != target_record.digest()
        or not bind_intended_state
    ):
        target_state = ControlRecord.build(
            kind="protected_state",
            record_id=f"protected-state:intended:{operation_id}",
            payload={
                **_payload(target_state),
                "lifecycle_phase": lifecycle_phase,
                "observed_at": (
                    attested_at if outcome == "succeeded" else completed_at
                ),
                "projection_id": f"operation-{operation_id}",
                "state_digest": digest("7"),
                "target_digest": target_record.digest(),
                "target_kind": target_kind,
            },
        )
    expected_state = expected_state_record or ControlRecord.build(
        kind="protected_state",
        record_id=f"protected-state:expected:{operation_id}",
        payload={
            **_payload(target_state),
            "fence_epoch": max(0, target_state.payload["fence_epoch"] - 1),
            "observed_at": registered_at,
            "state_digest": digest("1"),
        },
    )
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
            "registered_at": registered_at,
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
            "expected_protected_state_digest": expected_state.digest(),
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
            "recovery_contract_digest": recovery_contract_digest,
            "recovery_target_digest": (
                recovery_target_digest or expected_state.digest()
            ),
            "subject_digest": subject_digest,
            "subject_kind": subject_kind,
            "target_id": target_id,
            "target_digest": target_record.digest(),
            "target_kind": target_kind,
            "terminal_validator_digest": digest("6"),
        },
    )
    terminal_poststate_digest = poststate_digest or target_state.digest()
    validator_attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id=f"operation-attestation:{operation_id}",
        payload={
            "observed_at": attested_at,
            "operation_digest": operation.digest(),
            "outcome": outcome,
            "poststate_digest": terminal_poststate_digest,
            "subject_digest": subject_digest,
            "validator_digest": operation.payload["terminal_validator_digest"],
        },
    )
    capability = ControlRecord.build(
        kind="capability",
        record_id=f"capability:{operation_id}",
        payload={
            "authority_head_digest": operation.payload["authority_head_digest"],
            "authorizer_digest": digest("2"),
            "capability_id": digest("3"),
            "capability_type": (
                "recovery" if operation_kind == "recovery" else "operation"
            ),
            "expires_at": expires_at,
            "fence_epoch": target_state.payload["fence_epoch"],
            "intended_protected_state_digest": target_state.digest(),
            "intent_digest": intent.digest(),
            "issued_at": issued_at,
            "operation_digest": operation.digest(),
            "operation_id": operation_id,
            "plan_digest": operation.payload["plan_digest"],
            "single_use_scope_digest": operation.digest(),
            "status": "consumed",
            "subject_digest": subject_digest,
            "target_id": target_id,
            "target_kind": target_kind,
            "target_lease_digest": digest("4"),
            **(
                {
                    "authorizer_digest": recovery_owner_identity_record.digest(),
                    "predecessor_failure_record_digest": (
                        recovery_predecessor_operation.terminal_digest
                    ),
                    "predecessor_fence_epoch": (
                        recovery_predecessor_operation.capability_record.payload[
                            "fence_epoch"
                        ]
                    ),
                    "predecessor_operation_id": (
                        recovery_predecessor_operation.operation_record.payload[
                            "operation_id"
                        ]
                    ),
                    "recovery_contract_digest": recovery_predecessor_operation.operation_record.payload[
                        "recovery_contract_digest"
                    ],
                    "recovery_owner_role": recovery_owner_identity_record.payload[
                        "roles"
                    ][0],
                }
                if recovery_predecessor_operation is not None
                and recovery_owner_identity_record is not None
                else {}
            ),
        },
    )
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id=f"terminal:{operation_id}",
        payload={
            "completed_at": completed_at,
            "journal_sequence": terminal_sequence,
            "capability_digest": capability.digest(),
            "operation_digest": operation.digest(),
            "outcome": outcome,
            "poststate_digest": terminal_poststate_digest,
            "terminal_type": "critical_operation",
            "validator_attestation_digests": [validator_attestation.digest()],
        },
    )
    return RegisteredOperation(
        intent_record=intent,
        operation_record=operation,
        target_record=target_record,
        expected_protected_state_record=expected_state,
        intended_protected_state_record=target_state,
        capability_record=capability,
        terminal_record=terminal,
        validator_attestation_records=(validator_attestation,),
        **(
            {
                "recovery_predecessor_operation": recovery_predecessor_operation,
                "recovery_owner_identity_record": recovery_owner_identity_record,
            }
            if recovery_predecessor_operation is not None
            and recovery_owner_identity_record is not None
            else {}
        ),
    )


def _operation_requirement(
    *,
    requirement_id: str,
    target_record: ControlRecord,
    operation_kind: str,
    subject_kind: str,
    generation_binding_mode: str,
    generation_class: str,
    lifecycle_phase: str,
    target_kind: str,
    plan_digest: str = digest("3"),
    declared_effects: list[dict[str, object]] | None = None,
    recovery_contract_digest: str = digest("4"),
    recovery_target_role: str = "expected_prestate",
    terminal_validator_digest: str = digest("6"),
    purpose: str = "phase_transition",
    assignment_record: ControlRecord | None = None,
    rollback_contract_digest: str | None = None,
    recovery_target_digest: str | None = None,
) -> OperationRequirement:
    subject_binding_role = {
        "composite_authority": "composite_authority",
        "control_record": "control_record",
        "gate_occurrence": "gate_occurrence",
        "generation": "candidate_generation",
    }[subject_kind]
    generation_binding_role = {
        "b0_capture_sentinel": "b0_capture_sentinel",
        "no_generation": "no_generation",
        "required_generation": "candidate_generation",
    }[generation_binding_mode]
    payload: dict[str, object] = {
        "declared_effects": declared_effects
        or [
            {
                "classification": "poststate_observable",
                "effect_id": "scenario-result",
                "projection_digest": digest("8"),
            }
        ],
        "generation_binding_mode": generation_binding_mode,
        "generation_binding_role": generation_binding_role,
        "generation_class": generation_class,
        "lifecycle_phase": lifecycle_phase,
        "operation_kind": operation_kind,
        "plan_digest": plan_digest,
        "purpose": purpose,
        "realization_condition": (
            "always"
            if purpose == "final_service_restart"
            else "when_assignment_applicable"
            if assignment_record is not None
            else "always"
        ),
        "recovery_contract_digest": recovery_contract_digest,
        "recovery_target_role": recovery_target_role,
        "requirement_id": requirement_id,
        "subject_binding_role": subject_binding_role,
        "subject_kind": subject_kind,
        "target_digest": target_record.digest(),
        "target_id": target_record.payload["identity_id"],
        "target_kind": target_kind,
        "terminal_validator_digest": terminal_validator_digest,
        **(
            {"assignment_digest": assignment_record.digest()}
            if assignment_record is not None
            else {}
        ),
        **(
            {"rollback_contract_digest": rollback_contract_digest}
            if rollback_contract_digest is not None
            else {}
        ),
    }
    return OperationRequirement(
        ControlRecord.build(
            kind="operation_requirement",
            record_id=f"operation-requirement:{requirement_id}",
            payload=payload,
        ),
        target_record,
        assignment_record,
    )


def _operation_obligation(
    operation: RegisteredOperation,
    *,
    obligation_id: str,
    requirement: OperationRequirement | None = None,
    purpose: str = "phase_transition",
    assignment_record: ControlRecord | None = None,
) -> OperationObligation:
    payload = operation.operation_record.payload
    if requirement is None:
        if assignment_record is not None and purpose == "phase_transition":
            purpose = "blocking_scenario"
        requirement = _operation_requirement(
            requirement_id=obligation_id,
            target_record=operation.target_record,
            operation_kind=payload["operation_kind"],
            subject_kind=payload["subject_kind"],
            generation_binding_mode=payload["generation_binding"]["mode"],
            generation_class=payload["generation_class"],
            lifecycle_phase=payload["lifecycle_phase"],
            target_kind=payload["target_kind"],
            plan_digest=payload["plan_digest"],
            declared_effects=list(payload["declared_effects"]),
            recovery_contract_digest=payload["recovery_contract_digest"],
            terminal_validator_digest=payload["terminal_validator_digest"],
            purpose=purpose,
            assignment_record=assignment_record,
            rollback_contract_digest=payload.get("rollback_contract_digest"),
            recovery_target_digest=payload["recovery_target_digest"],
        )
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
            "operation_digest": operation.operation_digest,
            "operation_requirement_digest": requirement.requirement_digest,
            "subject_digest": payload["subject_digest"],
            "subject_kind": payload["subject_kind"],
            "target_id": payload["target_id"],
            "target_kind": payload["target_kind"],
        },
    )
    return OperationObligation(record, requirement)


def _recovery_operation_material(
    *,
    predecessor_recovery_contract_digest: str = digest("4"),
    predecessor_recovery_target_digest: str | None = None,
    successor_recovery_contract_digest: str = digest("5"),
    successor_recovery_target_digest: str | None = None,
    predecessor_phase: str = PromotionPhase.ACTIVE.value,
    predecessor_target_kind: str = "live_root",
    successor_phase: str = PromotionPhase.ACTIVE.value,
    successor_operation_phase: str | None = None,
    successor_target_kind: str = "live_root",
    predecessor_intent_sequence: int = 1,
    predecessor_terminal_sequence: int = 2,
    successor_intent_sequence: int = 3,
    successor_terminal_sequence: int = 4,
    predecessor_completed_at: str = "2026-08-12T10:00:08Z",
    successor_registered_at: str = "2026-08-12T10:00:10Z",
    recovery_expected_observed_at: str | None = None,
    time_changes: dict[str, str] | None = None,
) -> tuple[
    RegisteredOperation,
    RegisteredOperation,
    OperationObligation,
    ControlRecord,
]:
    times = {
        "predecessor_state": "2026-08-12T10:00:05Z",
        "predecessor_registered": "2026-08-12T10:00:01Z",
        "predecessor_issued": "2026-08-12T10:00:02Z",
        "predecessor_attested": "2026-08-12T10:00:07Z",
        "predecessor_completed": predecessor_completed_at,
        "successor_state": "2026-08-12T10:00:15Z",
        "successor_registered": successor_registered_at,
        "successor_issued": "2026-08-12T10:00:11Z",
        "successor_attested": "2026-08-12T10:00:15Z",
        "successor_completed": "2026-08-12T10:00:16Z",
        "expires": "2026-08-12T10:00:30Z",
        **(time_changes or {}),
    }
    generation = _generation(
        "generation:recovery-candidate",
        "recovery-candidate",
        "a",
    )
    target = _identity(
        "identity:recovery-target",
        "recovery-target",
        "target",
        "b",
    )
    owner = _identity(
        "identity:recovery-owner",
        "recovery-owner",
        "principal",
        "c",
        roles=["recovery-owner"],
    )
    predecessor_state = _protected_state(
        "protected-state:failed-predecessor",
        generation=generation,
        target=target,
        phase=predecessor_phase,
        seed="d",
        observed_at=times["predecessor_state"],
        fence_epoch=2,
        target_kind=predecessor_target_kind,
    )
    recovery_state = _protected_state(
        "protected-state:recovery-successor",
        generation=generation,
        target=target,
        phase=successor_phase,
        seed="e",
        observed_at=times["successor_state"],
        fence_epoch=3,
        target_kind=successor_target_kind,
    )
    recovery_expected_state = predecessor_state
    if (
        successor_target_kind != predecessor_state.payload["target_kind"]
        or recovery_expected_observed_at is not None
    ):
        recovery_expected_state = _protected_state(
            "protected-state:failed-predecessor-poststate",
            generation=generation,
            target=target,
            phase=predecessor_phase,
            seed="f",
            observed_at=(
                times["predecessor_completed"]
                if recovery_expected_observed_at is None
                else recovery_expected_observed_at
            ),
            fence_epoch=2,
            target_kind=successor_target_kind,
        )
    predecessor = _build_registered_operation(
        subject_digest=(
            digest("7")
            if predecessor_target_kind == "service"
            else generation.digest()
        ),
        subject_kind=(
            "gate_occurrence"
            if predecessor_target_kind == "service"
            else "generation"
        ),
        context_digest=digest("e"),
        candidate_generation=generation,
        target_state=predecessor_state,
        target_record=target,
        bind_intended_state=True,
        operation_id="failed-predecessor",
        operation_kind=(
            "blocking_scenario"
            if predecessor_target_kind == "service"
            else "package_installation"
        ),
        lifecycle_phase=predecessor_phase,
        target_kind=predecessor_target_kind,
        target_id=target.payload["identity_id"],
        intent_sequence=predecessor_intent_sequence,
        terminal_sequence=predecessor_terminal_sequence,
        outcome="failed",
        poststate_digest=recovery_expected_state.digest(),
        registered_at=times["predecessor_registered"],
        issued_at=times["predecessor_issued"],
        attested_at=times["predecessor_attested"],
        completed_at=times["predecessor_completed"],
        expires_at=times["expires"],
        recovery_contract_digest=predecessor_recovery_contract_digest,
        recovery_target_digest=(
            predecessor_recovery_target_digest or recovery_state.digest()
        ),
    )
    recovery = _build_registered_operation(
        subject_digest=predecessor_recovery_contract_digest,
        subject_kind="control_record",
        context_digest=digest("e"),
        candidate_generation=generation,
        target_state=recovery_state,
        target_record=target,
        expected_state_record=recovery_expected_state,
        bind_intended_state=True,
        operation_id="recovery-successor",
        operation_kind="recovery",
        lifecycle_phase=successor_operation_phase or successor_phase,
        target_kind=successor_target_kind,
        target_id=target.payload["identity_id"],
        intent_sequence=successor_intent_sequence,
        terminal_sequence=successor_terminal_sequence,
        registered_at=times["successor_registered"],
        issued_at=times["successor_issued"],
        attested_at=times["successor_attested"],
        completed_at=times["successor_completed"],
        expires_at=times["expires"],
        recovery_contract_digest=successor_recovery_contract_digest,
        recovery_target_digest=(
            successor_recovery_target_digest or recovery_expected_state.digest()
        ),
        recovery_predecessor_operation=predecessor,
        recovery_owner_identity_record=owner,
    )
    obligation = _operation_obligation(
        recovery,
        obligation_id="recovery-successor",
    )
    return predecessor, recovery, obligation, owner


def _b0_recovery_operation_material(
    *,
    predecessor_sentinel_digest: str = digest("1"),
    successor_sentinel_digest: str = digest("1"),
    successor_generation_seed: str | None = None,
    successor_binding_mode: str = "b0_capture_sentinel",
    predecessor_recovery_target_digest: str | None = None,
) -> tuple[RegisteredOperation, RegisteredOperation, OperationObligation]:
    predecessor_generation = _generation(
        "generation:b0-recovery",
        "b0-recovery",
        "0",
        generation_class="b0",
    )
    successor_generation = (
        predecessor_generation
        if successor_generation_seed is None
        else _generation(
            "generation:b0-recovery-destination",
            "b0-recovery-destination",
            successor_generation_seed,
            generation_class="b0",
        )
    )
    target = _identity(
        "identity:b0-recovery-register",
        "b0-recovery-register",
        "target",
        "2",
    )
    owner = _identity(
        "identity:b0-recovery-owner",
        "b0-recovery-owner",
        "principal",
        "3",
        roles=["recovery-owner"],
    )
    failed_state = _protected_state(
        "protected-state:b0-failed-predecessor",
        generation=predecessor_generation,
        target=target,
        phase=LifecyclePhase.CAPTURED.value,
        seed="4",
        observed_at="2026-08-12T10:00:05Z",
        fence_epoch=2,
        target_kind="composite_register",
    )
    recovery_state = _protected_state(
        "protected-state:b0-recovery-successor",
        generation=successor_generation,
        target=target,
        phase=LifecyclePhase.CAPTURED.value,
        seed="5",
        observed_at="2026-08-12T10:00:15Z",
        fence_epoch=3,
        target_kind="composite_register",
    )
    predecessor = _build_registered_operation(
        subject_digest=digest("6"),
        subject_kind="composite_authority",
        context_digest=digest("7"),
        candidate_generation=predecessor_generation,
        target_state=failed_state,
        target_record=target,
        bind_intended_state=True,
        operation_id="b0-failed-predecessor",
        operation_kind="composite_authority_transition",
        lifecycle_phase=LifecyclePhase.CAPTURED.value,
        target_kind="composite_register",
        target_id=target.payload["identity_id"],
        generation_class="b0",
        generation_binding={
            "generation_digest": predecessor_generation.digest(),
            "mode": "b0_capture_sentinel",
            "sentinel_digest": predecessor_sentinel_digest,
        },
        intent_sequence=1,
        terminal_sequence=2,
        outcome="failed",
        poststate_digest=failed_state.digest(),
        registered_at="2026-08-12T10:00:01Z",
        issued_at="2026-08-12T10:00:02Z",
        attested_at="2026-08-12T10:00:07Z",
        completed_at="2026-08-12T10:00:08Z",
        expires_at="2026-08-12T10:00:30Z",
        recovery_contract_digest=digest("8"),
        recovery_target_digest=(
            predecessor_recovery_target_digest or recovery_state.digest()
        ),
    )
    recovery = _build_registered_operation(
        subject_digest=predecessor.operation_record.payload[
            "recovery_contract_digest"
        ],
        subject_kind="control_record",
        context_digest=digest("7"),
        candidate_generation=successor_generation,
        target_state=recovery_state,
        target_record=target,
        expected_state_record=failed_state,
        bind_intended_state=True,
        operation_id="b0-recovery-successor",
        operation_kind="recovery",
        lifecycle_phase=LifecyclePhase.CAPTURED.value,
        target_kind="composite_register",
        target_id=target.payload["identity_id"],
        generation_class="b0",
        generation_binding={
            "generation_digest": successor_generation.digest(),
            "mode": successor_binding_mode,
            **(
                {"sentinel_digest": successor_sentinel_digest}
                if successor_binding_mode == "b0_capture_sentinel"
                else {}
            ),
        },
        intent_sequence=3,
        terminal_sequence=4,
        registered_at="2026-08-12T10:00:10Z",
        issued_at="2026-08-12T10:00:11Z",
        attested_at="2026-08-12T10:00:15Z",
        completed_at="2026-08-12T10:00:16Z",
        expires_at="2026-08-12T10:00:30Z",
        recovery_contract_digest=digest("9"),
        recovery_target_digest=failed_state.digest(),
        recovery_predecessor_operation=predecessor,
        recovery_owner_identity_record=owner,
    )
    return predecessor, recovery, _operation_obligation(
        recovery,
        obligation_id="b0-recovery-successor",
    )


def _multi_hop_recovery_operations(
    recovery_hops: int,
) -> tuple[RegisteredOperation, ...]:
    if recovery_hops not in {2, 3}:
        raise ValueError("review fixture supports exactly two or three recovery hops")
    generation = _generation(
        "generation:multi-hop-recovery",
        "multi-hop-recovery",
        "a",
    )
    target = _identity(
        "identity:multi-hop-recovery-target",
        "multi-hop-recovery-target",
        "target",
        "b",
    )
    owner = _identity(
        "identity:multi-hop-recovery-owner",
        "multi-hop-recovery-owner",
        "principal",
        "c",
        roles=["recovery-owner"],
    )
    state_seeds = "8abc"
    states = tuple(
        _protected_state(
            f"protected-state:multi-hop-recovery-{index}",
            generation=generation,
            target=target,
            phase=PromotionPhase.ACTIVE.value,
            seed=state_seeds[index],
            observed_at=f"2026-08-12T10:00:{index * 4 + 3:02d}Z",
            fence_epoch=index + 2,
        )
        for index in range(recovery_hops + 1)
    )
    contracts = tuple(digest(character) for character in "4567")
    predecessor = _build_registered_operation(
        subject_digest=generation.digest(),
        subject_kind="generation",
        context_digest=digest("e"),
        candidate_generation=generation,
        target_state=states[0],
        target_record=target,
        bind_intended_state=True,
        operation_id="multi-hop-failed-predecessor",
        operation_kind="package_installation",
        lifecycle_phase=PromotionPhase.ACTIVE.value,
        target_kind="live_root",
        target_id=target.payload["identity_id"],
        intent_sequence=1,
        terminal_sequence=2,
        outcome="failed",
        poststate_digest=states[0].digest(),
        registered_at="2026-08-12T10:00:01Z",
        issued_at="2026-08-12T10:00:02Z",
        attested_at="2026-08-12T10:00:03Z",
        completed_at="2026-08-12T10:00:04Z",
        expires_at="2026-08-12T10:00:30Z",
        recovery_contract_digest=contracts[0],
        recovery_target_digest=states[1].digest(),
    )
    operations = [predecessor]
    for hop in range(1, recovery_hops + 1):
        final = hop == recovery_hops
        registered_at_second = hop * 4 + 1
        successor = _build_registered_operation(
            subject_digest=contracts[hop - 1],
            subject_kind="control_record",
            context_digest=digest("e"),
            candidate_generation=generation,
            target_state=states[hop],
            target_record=target,
            expected_state_record=states[hop - 1],
            bind_intended_state=True,
            operation_id=f"multi-hop-recovery-{hop}",
            operation_kind="recovery",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_kind="live_root",
            target_id=target.payload["identity_id"],
            intent_sequence=hop * 2 + 1,
            terminal_sequence=hop * 2 + 2,
            outcome="succeeded" if final else "failed",
            poststate_digest=states[hop].digest(),
            registered_at=(
                f"2026-08-12T10:00:{registered_at_second:02d}Z"
            ),
            issued_at=f"2026-08-12T10:00:{registered_at_second + 1:02d}Z",
            attested_at=f"2026-08-12T10:00:{registered_at_second + 2:02d}Z",
            completed_at=(
                f"2026-08-12T10:00:{registered_at_second + 3:02d}Z"
            ),
            expires_at="2026-08-12T10:00:30Z",
            recovery_contract_digest=contracts[hop],
            recovery_target_digest=(
                states[hop + 1].digest()
                if not final
                else states[hop - 1].digest()
            ),
            recovery_predecessor_operation=operations[-1],
            recovery_owner_identity_record=owner,
        )
        operations.append(successor)
    return tuple(operations)


def _operation_realization(
    operation: RegisteredOperation,
    obligation: OperationObligation,
    *,
    realization_id: str,
    resolved_subject_record: ControlRecord | None = None,
    resolved_generation_record: ControlRecord | None = None,
) -> OperationRealization:
    return OperationRealization(
        realization_record=ControlRecord.build(
            kind="operation_realization",
            record_id=f"operation-realization:{realization_id}",
            payload={
                "observed_prestate_digest": (
                    operation.expected_protected_state_record.digest()
                ),
                "operation_digest": operation.operation_digest,
                "operation_obligation_digest": obligation.obligation_digest,
                "operation_requirement_digest": (
                    obligation.requirement.requirement_digest
                ),
                "realization_id": realization_id,
                "resolved_generation_binding": dict(
                    operation.operation_record.payload["generation_binding"]
                ),
                "resolved_subject_digest": operation.operation_record.payload[
                    "subject_digest"
                ],
            },
        ),
        requirement=obligation.requirement,
        obligation=obligation,
        operation=operation,
        observed_prestate_record=operation.expected_protected_state_record,
        resolved_subject_record=resolved_subject_record,
        resolved_generation_record=resolved_generation_record,
    )


def _registered_operation(
    fixture: Fixture,
    *,
    intent_sequence: int | None = None,
    outcome: str = "succeeded",
    poststate_digest: str | None = None,
    attested_at: str | None = None,
) -> RegisteredOperation:
    obligation = fixture.contract.operation_obligations[0].obligation_record.payload
    template = fixture.cut.operations[0]
    return _build_registered_operation(
        subject_digest=obligation["subject_digest"],
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=template.intended_protected_state_record,
        target_record=template.target_record,
        operation_id="blocking-scenario-1",
        operation_kind=obligation["operation_kind"],
        subject_kind=obligation["subject_kind"],
        lifecycle_phase=obligation["lifecycle_phase"],
        target_kind=obligation["target_kind"],
        target_id=obligation["target_id"],
        intent_sequence=(
            template.intent_record.payload["journal_sequence"]
            if intent_sequence is None
            else intent_sequence
        ),
        terminal_sequence=template.terminal_sequence,
        outcome=outcome,
        poststate_digest=poststate_digest,
        expected_state_record=template.expected_protected_state_record,
        bind_intended_state=True,
        registered_at=template.intent_record.payload["registered_at"],
        issued_at=template.capability_record.payload["issued_at"],
        attested_at=(
            template.validator_attestation_records[0].payload["observed_at"]
            if attested_at is None
            else attested_at
        ),
        completed_at=template.terminal_record.payload["completed_at"],
        expires_at=template.capability_record.payload["expires_at"],
    )


def _cut_with_operation(
    fixture: Fixture,
    operation: RegisteredOperation,
) -> AtomicEvidenceCut:
    operations = (operation, *fixture.cut.operations[1:])
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:with-operation",
        payload={
            **_payload(fixture.cut.cut_record),
            "complete_through_sequence": max(
                *(item.terminal_sequence for item in fixture.cut.attempts),
                *(item.terminal_sequence for item in operations),
            ),
            "capability_digests": [item.capability_digest for item in operations],
            "operation_digests": [item.operation_digest for item in operations],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations
            ],
            "registration_set_digest": registration_set_digest(
                fixture.cut.attempts,
                operations,
            ),
        },
    )
    return replace(
        fixture.cut,
        cut_record=cut_record,
        operations=operations,
        validator_attestation_records=tuple(
            attestation
            for item in operations
            for attestation in item.validator_attestation_records
        ),
    )


def _cut_with_operations(
    cut: AtomicEvidenceCut,
    operations: tuple[RegisteredOperation, ...],
    *,
    record_suffix: str,
    complete_through_sequence: int | None = None,
    observed_at: str | None = None,
) -> AtomicEvidenceCut:
    complete_through_sequence = (
        cut.cut_record.payload["complete_through_sequence"]
        if complete_through_sequence is None
        else complete_through_sequence
    )
    evaluations: list[BoundEvaluation] = []
    for index, evaluation in enumerate(cut.evaluations, start=1):
        stream = evaluation.invalidation_stream_checkpoint_record
        if stream.payload["complete_through_sequence"] != complete_through_sequence:
            stream = ControlRecord.build(
                kind="invalidation_stream_checkpoint",
                record_id=(
                    f"invalidation-stream-checkpoint:{record_suffix}:{index}"
                ),
                payload={
                    **_payload(stream),
                    "complete_through_sequence": complete_through_sequence,
                },
            )
        currency = evaluation.currency_proof_record
        if (
            currency.payload["invalidation_stream_checkpoint_digest"]
            != stream.digest()
        ):
            currency = ControlRecord.build(
                kind="evidence_currency_proof",
                record_id=f"evidence-currency-proof:{record_suffix}:{index}",
                payload={
                    **_payload(currency),
                    "invalidation_stream_checkpoint_digest": stream.digest(),
                },
            )
        evaluations.append(
            replace(
                evaluation,
                invalidation_stream_checkpoint_record=stream,
                currency_proof_record=currency,
            )
        )
    evaluations_tuple = tuple(evaluations)
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id=f"atomic-evidence-cut:{record_suffix}",
        payload={
            **_payload(cut.cut_record),
            "capability_digests": [item.capability_digest for item in operations],
            "complete_through_sequence": complete_through_sequence,
            "currency_proof_digests": [
                item.currency_proof_record.digest() for item in evaluations_tuple
            ],
            "operation_digests": [item.operation_digest for item in operations],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations
            ],
            "observed_at": observed_at or cut.cut_record.payload["observed_at"],
            "registration_set_digest": registration_set_digest(
                cut.attempts,
                operations,
            ),
        },
    )
    return replace(
        cut,
        cut_record=cut_record,
        evaluations=evaluations_tuple,
        operations=operations,
        validator_attestation_records=tuple(
            attestation
            for operation in operations
            for attestation in operation.validator_attestation_records
        ),
    )


def _cut_with_observations(
    cut: AtomicEvidenceCut,
    observation_records: tuple[ControlRecord, ...],
    *,
    record_suffix: str,
) -> AtomicEvidenceCut:
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id=f"atomic-evidence-cut:{record_suffix}",
        payload={
            **_payload(cut.cut_record),
            "observation_digests": [
                record.digest() for record in observation_records
            ],
        },
    )
    return replace(
        cut,
        cut_record=cut_record,
        observation_records=observation_records,
    )


def _rebind_registered_operation(
    operation: RegisteredOperation,
    *,
    record_suffix: str,
    intent_record: ControlRecord | None = None,
    operation_record: ControlRecord | None = None,
    expected_protected_state_record: ControlRecord | None = None,
    intended_protected_state_record: ControlRecord | None = None,
) -> RegisteredOperation:
    intent = intent_record or operation.intent_record
    rebound_operation = operation_record or operation.operation_record
    expected_state = (
        expected_protected_state_record
        or operation.expected_protected_state_record
    )
    intended_state = (
        intended_protected_state_record
        or operation.intended_protected_state_record
    )
    capability = ControlRecord.build(
        kind="capability",
        record_id=f"capability:{record_suffix}",
        payload={
            **_payload(operation.capability_record),
            "authority_head_digest": rebound_operation.payload[
                "authority_head_digest"
            ],
            "fence_epoch": intended_state.payload["fence_epoch"],
            "intended_protected_state_digest": rebound_operation.payload[
                "intended_protected_state_digest"
            ],
            "intent_digest": intent.digest(),
            "operation_digest": rebound_operation.digest(),
            "operation_id": rebound_operation.payload["operation_id"],
            "plan_digest": rebound_operation.payload["plan_digest"],
            "single_use_scope_digest": rebound_operation.digest(),
            "subject_digest": rebound_operation.payload["subject_digest"],
            "target_id": rebound_operation.payload["target_id"],
            "target_kind": rebound_operation.payload["target_kind"],
        },
    )
    terminal_payload = {
        **_payload(operation.terminal_record),
        "capability_digest": capability.digest(),
        "operation_digest": rebound_operation.digest(),
        **(
            {
                "poststate_digest": rebound_operation.payload[
                    "intended_protected_state_digest"
                ]
            }
            if operation.terminal_record.payload["outcome"] == "succeeded"
            else {}
        ),
    }
    validator_attestations = tuple(
        ControlRecord.build(
            kind="operation_attestation",
            record_id=f"operation-attestation:{record_suffix}:{index}",
            payload={
                **_payload(attestation_record),
                "operation_digest": rebound_operation.digest(),
                "outcome": terminal_payload["outcome"],
                "poststate_digest": terminal_payload["poststate_digest"],
                "subject_digest": rebound_operation.payload["subject_digest"],
                "validator_digest": rebound_operation.payload[
                    "terminal_validator_digest"
                ],
            },
        )
        for index, attestation_record in enumerate(
            operation.validator_attestation_records,
            start=1,
        )
    )
    terminal_payload["validator_attestation_digests"] = [
        item.digest() for item in validator_attestations
    ]
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id=f"terminal:{record_suffix}",
        payload=terminal_payload,
    )
    return RegisteredOperation(
        intent_record=intent,
        operation_record=rebound_operation,
        target_record=operation.target_record,
        expected_protected_state_record=expected_state,
        intended_protected_state_record=intended_state,
        capability_record=capability,
        terminal_record=terminal,
        validator_attestation_records=validator_attestations,
        recovery_predecessor_operation=(
            operation.recovery_predecessor_operation
        ),
        recovery_owner_identity_record=operation.recovery_owner_identity_record,
    )


def _replace_operation_validator_attestations(
    operation: RegisteredOperation,
    validator_attestations: tuple[ControlRecord, ...],
    *,
    record_suffix: str,
) -> RegisteredOperation:
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id=f"terminal:{record_suffix}",
        payload={
            **_payload(operation.terminal_record),
            "validator_attestation_digests": [
                item.digest() for item in validator_attestations
            ],
        },
    )
    return RegisteredOperation(
        intent_record=operation.intent_record,
        operation_record=operation.operation_record,
        target_record=operation.target_record,
        expected_protected_state_record=operation.expected_protected_state_record,
        intended_protected_state_record=operation.intended_protected_state_record,
        capability_record=operation.capability_record,
        terminal_record=terminal,
        validator_attestation_records=validator_attestations,
        recovery_predecessor_operation=(
            operation.recovery_predecessor_operation
        ),
        recovery_owner_identity_record=operation.recovery_owner_identity_record,
    )


def _replace_exact_contract_operation(
    fixture: Fixture,
    original: RegisteredOperation,
    replacement: RegisteredOperation,
) -> tuple[PromotionContract, AtomicEvidenceCut]:
    obligation_index = next(
        index
        for index, obligation in enumerate(fixture.contract.operation_obligations)
        if obligation.operation_digest == original.operation_digest
    )
    original_obligation = fixture.contract.operation_obligations[obligation_index]
    replacement_obligation = _operation_obligation(
        replacement,
        obligation_id=original_obligation.obligation_record.payload["obligation_id"],
        requirement=original_obligation.requirement,
    )
    obligations = list(fixture.contract.operation_obligations)
    obligations[obligation_index] = replacement_obligation
    obligation_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation-obligation-set:replacement",
        payload={
            "obligation_digests": [item.obligation_digest for item in obligations],
            "operation_requirement_set_digest": (
                fixture.contract.operation_requirement_set_record.digest()
            ),
            "requirements_digest": fixture.requirements.digest(),
        },
    )
    original_realization = next(
        realization
        for realization in fixture.contract.operation_realizations
        if realization.obligation.obligation_digest
        == original_obligation.obligation_digest
    )
    replacement_realization = _operation_realization(
        replacement,
        replacement_obligation,
        realization_id=original_realization.realization_record.payload[
            "realization_id"
        ],
        resolved_subject_record=original_realization.resolved_subject_record,
        resolved_generation_record=(
            original_realization.resolved_generation_record
        ),
    )
    realizations = tuple(
        replacement_realization
        if item.obligation.obligation_digest
        == original_obligation.obligation_digest
        else item
        for item in fixture.contract.operation_realizations
    )
    realization_set = ControlRecord.build(
        kind="operation_realization_set",
        record_id="operation-realization-set:replacement",
        payload={
            "operation_obligation_set_digest": obligation_set.digest(),
            "operation_realization_digests": [
                item.realization_digest for item in realizations
            ],
        },
    )
    contract_payload = {
        **_payload(fixture.contract.contract_record),
        "operation_obligation_set_digest": obligation_set.digest(),
        "operation_realization_set_digest": realization_set.digest(),
    }
    if (
        fixture.contract.contract_record.payload.get(
            "phase_establishing_operation_obligation_digest"
        )
        == original_obligation.obligation_digest
    ):
        contract_payload["phase_establishing_operation_obligation_digest"] = (
            replacement_obligation.obligation_digest
        )
    promotion_obligations = fixture.contract.obligations
    attempts = fixture.cut.attempts
    rebound_promotion_records: dict[str, ControlRecord] = {}
    rebound_promotion_obligations: list[PromotionObligation] = []
    for promotion_obligation in promotion_obligations:
        if (
            promotion_obligation.scenario_operation_obligation_digest
            != original_obligation.obligation_digest
        ):
            rebound_promotion_obligations.append(promotion_obligation)
            continue
        promotion_obligation_record = ControlRecord.build(
            kind="promotion_obligation",
            record_id=(
                f"{promotion_obligation.obligation_record.record_id}:replacement-operation"
            ),
            payload={
                **_payload(promotion_obligation.obligation_record),
                "scenario_operation_obligation_digest": (
                    replacement_obligation.obligation_digest
                ),
            },
        )
        rebound_promotion_records[
            promotion_obligation.obligation_digest
        ] = promotion_obligation_record
        rebound_promotion_obligations.append(
            PromotionObligation(promotion_obligation_record)
        )
    if rebound_promotion_records:
        promotion_obligations = tuple(rebound_promotion_obligations)
        attempts = tuple(
            replace(
                attempt,
                obligation_record=rebound_promotion_records[
                    attempt.obligation_record.digest()
                ],
            )
            if attempt.obligation_record.digest() in rebound_promotion_records
            else attempt
            for attempt in attempts
        )
        contract_payload["obligation_digests"] = [
            item.obligation_digest for item in promotion_obligations
        ]
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:replacement-operation",
        payload=contract_payload,
    )
    contract = replace(
        fixture.contract,
        operation_obligation_set_record=obligation_set,
        operation_realization_set_record=realization_set,
        contract_record=contract_record,
        obligations=promotion_obligations,
        operation_obligations=tuple(obligations),
        operation_realizations=realizations,
    )
    operations = tuple(
        replacement if item.operation_digest == original.operation_digest else item
        for item in fixture.cut.operations
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:replacement-operation",
        payload={
            **_payload(fixture.cut.cut_record),
            "capability_digests": [item.capability_digest for item in operations],
            "contract_digest": contract.contract_digest,
            "operation_digests": [item.operation_digest for item in operations],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations
            ],
            "registration_set_digest": registration_set_digest(attempts, operations),
        },
    )
    return contract, replace(
        fixture.cut,
        cut_record=cut_record,
        attempts=attempts,
        operations=operations,
        validator_attestation_records=tuple(
            attestation
            for operation in operations
            for attestation in operation.validator_attestation_records
        ),
    )


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


def _acceptance_material(
    fixture: Fixture,
    cut: AtomicEvidenceCut | None = None,
) -> tuple[ControlRecord, ControlRecord]:
    cut = cut or fixture.cut
    final_service_anchor_receipt = _final_service_anchor_receipt(fixture, cut)
    request = build_acceptance_request(
        fixture.contract,
        cut,
        assess_promotion_cut(fixture.contract, cut),
        final_service_anchor_receipt,
        record_id="acceptance-request:w0",
        requested_at="2026-08-12T09:14:12Z",
    )
    actor = fixture.contract.acceptance_actor_identity_record
    assert actor is not None
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:acceptance:w0",
        payload={
            "action": "accept_generation",
            "actor_identity_digest": actor.digest(),
            "actor_role": "control-owner",
            "authorization_digest": request.payload[
                "acceptance_authorization_digest"
            ],
            "decided_at": "2026-08-12T09:14:15Z",
            "decision": "approved",
            "subject_digest": request.digest(),
        },
    )
    return request, approval


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
            "capability_digests": list(challenge.capability_digests),
            "complete_through_sequence": challenge.complete_through_sequence,
            "completeness_proof_digest": challenge.completeness_proof_digest,
            "currency_proof_digests": list(challenge.currency_proof_digests),
            "evaluation_digests": list(challenge.evaluation_digests),
            "fork_proof_digest": challenge.fork_proof_digest,
            "inclusion_edge_digests": list(challenge.inclusion_edge_digests),
            "journal_head_digest": challenge.journal_head_digest,
            "operation_digests": list(challenge.operation_digests),
            "operation_terminal_digests": list(
                challenge.operation_terminal_digests
            ),
            "observation_digests": list(challenge.observation_digests),
            "phase": challenge.phase.value,
            "predecessor_checkpoint_digest": (
                challenge.predecessor_checkpoint_digest
            ),
            "promotion_contract_digest": challenge.promotion_contract_digest,
            "proof_id": "promotion-proof-1",
            "validation_contract_digest": challenge.validation_contract_digest,
            "verified_at": _PHASE_TIMES[challenge.phase]["proof"],
            "verifier_identity_digest": digest("3"),
            **(
                {"acceptance_request_digest": challenge.acceptance_request_digest}
                if challenge.acceptance_request_digest is not None
                else {}
            ),
            **(
                {"approval_digest": challenge.approval_digest}
                if challenge.approval_digest is not None
                else {}
            ),
            **(
                {
                    "final_service_anchor_receipt_digest": (
                        challenge.final_service_anchor_receipt_digest
                    )
                }
                if challenge.final_service_anchor_receipt_digest is not None
                else {}
            ),
            **self.proof_changes,
        }
        return ControlRecord.build(
            kind="promotion_authority_proof",
            record_id="promotion-authority-proof:1",
            payload=payload,
        )


def _operation_for_purpose(
    fixture: Fixture,
    purpose: str,
) -> RegisteredOperation:
    matching_digests = {
        obligation.operation_digest
        for obligation in fixture.contract.operation_obligations
        if obligation.requirement.requirement_record.payload["purpose"] == purpose
    }
    matches = [
        operation
        for operation in fixture.cut.operations
        if operation.operation_digest in matching_digests
    ]
    assert len(matches) == 1
    return matches[0]


def _service_observation_authorization(
    observer: ControlRecord,
    separation_policy: ControlRecord,
) -> ControlRecord:
    return ControlRecord.build(
        kind="authorization",
        record_id="authorization:service-observation",
        payload={
            "action": "observe_service",
            "allowed_actor_identity_digests": [observer.digest()],
            "allowed_actor_roles": list(observer.payload.get("roles", ())),
            "approver_roles": list(observer.payload.get("roles", ())),
            "policy_id": "service-observation",
            "recovery_root_digest": digest("1"),
            "separation_policy_digest": separation_policy.digest(),
            "subject_kind": "protected_state",
            "validity_policy_digest": digest("2"),
        },
    )


def _baseline_restoration_receipt(
    fixture: Fixture,
) -> BaselineRestorationReceipt:
    assert fixture.contract.phase is PromotionPhase.PREVALIDATED
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    isolated = _operation_for_purpose(fixture, "phase_transition")
    rehearsal = _operation_for_purpose(fixture, "baseline_rehearsal_install")
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    phase_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == isolated.operation_digest
    )
    smoke_attempt = fixture.cut.attempts[0]
    smoke_evaluation = fixture.cut.evaluations[0]
    restored_state = restoration.intended_protected_state_record
    rollback = ControlRecord.build(
        kind="rollback",
        record_id="rollback:w4-baseline-restoration",
        payload={
            "destination_generation_digest": restored_state.payload[
                "generation_digest"
            ],
            "generation_binding": {
                "generation_digest": fixture.contract.generation_digest,
                "mode": "required_generation",
            },
            "operation_digest": restoration.operation_digest,
            "origin_generation_digest": fixture.contract.generation_digest,
            "rollback_id": "w4-baseline-restoration",
            "target_digest": fixture.target.digest(),
            "target_generation_digest": restored_state.payload[
                "generation_digest"
            ],
            "target_projection_digest": restoration.operation_record.payload[
                "declared_effects"
            ][0]["projection_digest"],
            "target_protected_state_digest": restored_state.digest(),
            "target_state_digest": restored_state.payload["state_digest"],
            "terminal_gate_digest": smoke_attempt.terminal_record.digest(),
        },
    )
    smoke_contract = ControlRecord.build(
        kind="restored_baseline_smoke_contract",
        record_id="restored-baseline-smoke-contract:w4",
        payload={
            "assignment_digest": smoke_evaluation.assignment_record.digest(),
            "attestation_authorization_digest": (
                smoke_evaluation.attestation_authorization_record.digest()
            ),
            "expected_outcome": "pass",
            "gate_digest": smoke_evaluation.gate_record.digest(),
            "restored_protected_state_digest": restored_state.digest(),
            "smoke_contract_id": "w4-restored-baseline-smoke",
            "target_digest": fixture.target.digest(),
            "validation_contract_digest": fixture.validation_contract.digest(),
            "validator_digest": smoke_evaluation.validator_identity_record.digest(),
        },
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4",
        payload={
            "candidate_live_protected_state_digest": (
                rehearsal.intended_protected_state_record.digest()
            ),
            "captured_checkpoint_digest": captured.checkpoint_digest,
            "captured_generation_digest": captured.generation_record.digest(),
            "captured_protected_state_digest": (
                captured.target_protected_state_record.digest()
            ),
            "isolated_install_operation_digest": isolated.operation_digest,
            "isolated_install_operation_terminal_digest": isolated.terminal_digest,
            "live_prestate_protected_state_digest": (
                rehearsal.expected_protected_state_record.digest()
            ),
            "post_restoration_gate_terminal_digest": (
                smoke_attempt.terminal_record.digest()
            ),
            "post_restoration_smoke_attempt_digest": smoke_attempt.attempt_digest,
            "post_restoration_smoke_evaluation_digest": (
                smoke_evaluation.evaluation_record_digest
            ),
            "phase_establishing_operation_obligation_digest": (
                phase_obligation.obligation_digest
            ),
            "post_restoration_smoke_contract_digest": smoke_contract.digest(),
            "prevalidated_promotion_contract_digest": (
                fixture.contract.contract_digest
            ),
            "receipt_id": "w4-baseline-restoration",
            "rehearsal_install_operation_digest": rehearsal.operation_digest,
            "rehearsal_install_operation_terminal_digest": rehearsal.terminal_digest,
            "restoration_evidence_cut_digest": fixture.cut.cut_record_digest,
            "restoration_operation_digest": restoration.operation_digest,
            "restoration_operation_terminal_digest": restoration.terminal_digest,
            "restored_generation_digest": restored_state.payload[
                "generation_digest"
            ],
            "restored_fence_epoch": restored_state.payload["fence_epoch"],
            "restored_projection_digest": rollback.payload[
                "target_projection_digest"
            ],
            "restored_protected_state_digest": restored_state.digest(),
            "rollback_digest": rollback.digest(),
            "target_digest": fixture.target.digest(),
        },
    )
    return BaselineRestorationReceipt(
        receipt_record=receipt_record,
        promotion_contract=fixture.contract,
        captured_checkpoint=captured,
        target_record=fixture.target,
        isolated_install_operation=isolated,
        phase_establishing_operation_obligation=phase_obligation,
        live_prestate_protected_state_record=(
            rehearsal.expected_protected_state_record
        ),
        rehearsal_install_operation=rehearsal,
        rollback_record=rollback,
        restoration_operation=restoration,
        smoke_attempt=smoke_attempt,
        smoke_evaluation=smoke_evaluation,
        smoke_contract_record=smoke_contract,
        evidence_cut=fixture.cut,
    )


def _service_anchor_receipt(fixture: Fixture) -> ServiceAnchorReceipt:
    operation = _operation_for_purpose(fixture, "service_anchor")
    phase_obligation_digest = fixture.contract.contract_record.payload[
        "phase_establishing_operation_obligation_digest"
    ]
    phase_obligation = next(
        item
        for item in fixture.contract.operation_obligations
        if item.obligation_digest == phase_obligation_digest
    )
    active_phase_operation = next(
        item
        for item in fixture.cut.operations
        if item.operation_digest == phase_obligation.operation_digest
    )
    backend_provenance = next(
        item
        for item in fixture.cut.observation_records
        if item.kind == "backend_provenance"
    )
    readiness = next(
        item for item in fixture.cut.observation_records if item.kind == "readiness"
    )
    health_records = tuple(
        item
        for item in fixture.cut.observation_records
        if item.kind == "service_health_observation"
    )
    observation_authorization = _service_observation_authorization(
        fixture.bound.validator_identity_record,
        fixture.bound.separation_policy_record,
    )
    receipt_record = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:w5",
        payload={
            "active_evidence_cut_digest": fixture.cut.cut_record_digest,
            "active_phase_operation_terminal_digest": (
                active_phase_operation.terminal_digest
            ),
            "active_promotion_contract_digest": fixture.contract.contract_digest,
            "anchor_id": "w5-service-anchor",
            "backend_provenance_digest": backend_provenance.digest(),
            "establishing_operation_digest": operation.operation_digest,
            "expires_at": "2026-08-12T09:16:10Z",
            "generation_digest": fixture.contract.generation_digest,
            "issued_at": "2026-08-12T09:11:10Z",
            "operation_terminal_digest": operation.terminal_digest,
            "process_epoch": operation.intended_protected_state_record.payload[
                "process_epoch"
            ],
            "readiness_digest": readiness.digest(),
            "service_protected_state_digest": (
                operation.intended_protected_state_record.digest()
            ),
            "target_digest": operation.target_record.digest(),
        },
    )
    return ServiceAnchorReceipt(
        receipt_record=receipt_record,
        promotion_contract=fixture.contract,
        evidence_cut=fixture.cut,
        target_record=operation.target_record,
        service_protected_state_record=operation.intended_protected_state_record,
        establishing_operation=operation,
        active_phase_operation=active_phase_operation,
        backend_provenance_record=backend_provenance,
        service_health_observation_records=health_records,
        readiness_record=readiness,
        observer_authorization_record=observation_authorization,
        observer_separation_policy_record=fixture.bound.separation_policy_record,
        observer_identity_record=fixture.bound.validator_identity_record,
    )


def _service_observation_records(
    contract: PromotionContract,
    bound: BoundEvaluation,
    operation: RegisteredOperation,
    *,
    record_suffix: str,
    backend_observed_at: str,
    health_observed_at: str,
    readiness_observed_at: str,
    state_record: ControlRecord | None = None,
) -> tuple[ControlRecord, ControlRecord, ControlRecord, ControlRecord]:
    state_record = state_record or operation.intended_protected_state_record
    state = state_record.payload
    authorization = _service_observation_authorization(
        bound.validator_identity_record,
        bound.separation_policy_record,
    )
    backend = ControlRecord.build(
        kind="backend_provenance",
        record_id=f"backend-provenance:{record_suffix}",
        payload={
            "authorization_digest": authorization.digest(),
            "backend_id": "llama-cpp-vulkan",
            "backend_manifest_digest": digest("1"),
            "configuration_digest": digest("2"),
            "driver_device_digest": digest("3"),
            "generation_digest": contract.generation_digest,
            "model_identity_digest": digest("4"),
            "observed_at": backend_observed_at,
            "observer_identity_digest": (
                bound.validator_identity_record.digest()
            ),
            "package_manifest_digest": digest("5"),
            "process_epoch": state["process_epoch"],
            "provenance_id": f"{record_suffix}-service-backend",
            "service_protected_state_digest": state_record.digest(),
            "target_digest": operation.target_record.digest(),
        },
    )
    health = ControlRecord.build(
        kind="service_health_observation",
        record_id=f"service-health-observation:{record_suffix}",
        payload={
            "authorization_digest": authorization.digest(),
            "backend_provenance_digest": backend.digest(),
            "generation_digest": contract.generation_digest,
            "observation_id": f"{record_suffix}-service-health",
            "observed_at": health_observed_at,
            "observer_identity_digest": (
                bound.validator_identity_record.digest()
            ),
            "process_epoch": state["process_epoch"],
            "service_protected_state_digest": state_record.digest(),
            "status": "ready",
            "target_digest": operation.target_record.digest(),
        },
    )
    readiness = ControlRecord.build(
        kind="readiness",
        record_id=f"readiness:{record_suffix}",
        payload={
            "backend_manifest_digest": backend.payload["backend_manifest_digest"],
            "backend_provenance_digest": backend.digest(),
            "generation_digest": contract.generation_digest,
            "observed_at": readiness_observed_at,
            "process_epoch": state["process_epoch"],
            "service_health_observation_digests": [health.digest()],
            "service_protected_state_digest": state_record.digest(),
            "status": "ready",
            "target_digest": operation.target_record.digest(),
        },
    )
    return authorization, backend, health, readiness


def _final_service_observation_records(
    contract: PromotionContract,
    bound: BoundEvaluation,
    operation: RegisteredOperation,
) -> tuple[ControlRecord, ControlRecord, ControlRecord, ControlRecord]:
    return _service_observation_records(
        contract,
        bound,
        operation,
        record_suffix="w6-final",
        backend_observed_at="2026-08-12T09:14:09.1Z",
        health_observed_at="2026-08-12T09:14:10Z",
        readiness_observed_at="2026-08-12T09:14:10Z",
    )


def _final_service_anchor_receipt(
    fixture: Fixture,
    cut: AtomicEvidenceCut | None = None,
    contract: PromotionContract | None = None,
) -> FinalServiceAnchorReceipt:
    cut = cut or fixture.cut
    contract = contract or fixture.contract
    operation = _operation_for_purpose(fixture, "final_service_restart")
    state_record = operation.intended_protected_state_record
    state = state_record.payload
    predecessor = contract.service_anchor_receipt
    assert isinstance(predecessor, ServiceAnchorReceipt)
    authorization, backend, health, readiness = (
        _final_service_observation_records(
            contract,
            fixture.bound,
            operation,
        )
    )
    receipt_record = ControlRecord.build(
        kind="final_service_anchor_receipt",
        record_id="final-service-anchor-receipt:w6",
        payload={
            "anchor_id": "w6-final-service-anchor",
            "backend_provenance_digest": backend.digest(),
            "evidence_cut_digest": cut.cut_record_digest,
            "expires_at": "2026-08-12T09:19:11Z",
            "final_restart_operation_digest": operation.operation_digest,
            "final_restart_operation_terminal_digest": operation.terminal_digest,
            "generation_digest": contract.generation_digest,
            "issued_at": "2026-08-12T09:14:11Z",
            "predecessor_service_anchor_receipt_digest": predecessor.receipt_digest,
            "process_epoch": state["process_epoch"],
            "promotion_contract_digest": contract.contract_digest,
            "readiness_digest": readiness.digest(),
            "service_protected_state_digest": state_record.digest(),
            "target_digest": operation.target_record.digest(),
        },
    )
    return FinalServiceAnchorReceipt(
        receipt_record=receipt_record,
        promotion_contract=contract,
        evidence_cut=cut,
        predecessor_service_anchor_receipt=predecessor,
        final_restart_operation=operation,
        target_record=operation.target_record,
        service_protected_state_record=state_record,
        backend_provenance_record=backend,
        service_health_observation_records=(health,),
        readiness_record=readiness,
        observer_authorization_record=authorization,
        observer_separation_policy_record=(
            fixture.bound.separation_policy_record
        ),
        observer_identity_record=fixture.bound.validator_identity_record,
    )


def _materialize_structural_checkpoint(
    fixture: Fixture,
) -> StructuralLifecycleCandidate:
    acceptance_request = None
    approval = None
    final_service_receipt = None
    if fixture.contract.phase is PromotionPhase.ACCEPTED:
        final_service_receipt = _final_service_anchor_receipt(fixture)
        acceptance_request, approval = _acceptance_material(fixture)
    baseline_receipt = (
        _baseline_restoration_receipt(fixture)
        if fixture.contract.phase is PromotionPhase.PREVALIDATED
        else None
    )
    service_receipt = (
        _service_anchor_receipt(fixture)
        if fixture.contract.phase is PromotionPhase.ACTIVE
        and any(
            requirement.requirement_record.payload["purpose"] == "service_anchor"
            for requirement in fixture.contract.operation_requirements
        )
        else None
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"lifecycle-checkpoint:{fixture.contract.phase.value}",
        payload={
            "authority_proof_digest": digest("f"),
            "checkpoint_id": f"candidate-{fixture.contract.phase.value}",
            "contract_digest": fixture.contract.contract_digest,
            "evidence_cut_digest": fixture.cut.cut_record_digest,
            "established_at": _PHASE_TIMES[fixture.contract.phase]["checkpoint"],
            "generation_class": "c",
            "generation_digest": fixture.contract.generation_digest,
            "phase": fixture.contract.phase.value,
            "predecessor_checkpoint_digest": (
                fixture.contract.predecessor_checkpoint.checkpoint_digest
            ),
            "target_digest": fixture.contract.target_record.digest(),
            "target_protected_state_digest": (
                fixture.contract.target_protected_state_record.digest()
            ),
            **(
                {
                    "acceptance_request_digest": acceptance_request.digest(),
                    "approval_digest": approval.digest(),
                    "final_service_anchor_receipt_digest": (
                        final_service_receipt.receipt_digest
                    ),
                }
                if acceptance_request is not None and approval is not None
                else {}
            ),
            **(
                {
                    "baseline_restoration_receipt_digest": (
                        baseline_receipt.receipt_digest
                    )
                }
                if baseline_receipt is not None
                else {}
            ),
            **(
                {"service_anchor_receipt_digest": service_receipt.receipt_digest}
                if service_receipt is not None
                else {}
            ),
        },
    )
    return StructuralLifecycleCandidate(
        structural_record=checkpoint,
        generation_record=fixture.contract.generation_record,
        target_record=fixture.contract.target_record,
        target_protected_state_record=(
            fixture.contract.target_protected_state_record
        ),
        predecessor_checkpoint=fixture.contract.predecessor_checkpoint,
        promotion_contract=fixture.contract,
        evidence_cut=fixture.cut,
        acceptance_request_record=acceptance_request,
        approval_record=approval,
        final_service_anchor_receipt=final_service_receipt,
        baseline_restoration_receipt=baseline_receipt,
        service_anchor_receipt=service_receipt,
    )


def _fixture(
    *,
    impact: GateImpact = GateImpact.BLOCKING,
    outcome: str = "pass",
    phase: PromotionPhase = PromotionPhase.ACCEPTED,
    preassembly: bool = False,
    not_applicable: bool = False,
    conditional_applicable: bool = False,
    scenario_gate: bool | None = None,
    scenario_target_kind: str | None = None,
    scenario_target_id: str = "reference-host",
    scenario_lifecycle_phase: str | None = None,
    include_repository_publication: bool = False,
    include_root_installation: bool = False,
    predecessor_checkpoint: (
        LifecycleCheckpoint
        | StructuralBaselineCapture
        | StructuralLifecycleCandidate
        | None
    ) = None,
    attestor_roles: list[str] | None = None,
    attestation_actor_role: str = "validator",
    allowed_attestor_roles: list[str] | None = None,
    max_live_attempt_seconds: int = 3600,
    max_suite_seconds: int = 28800,
    evidence_max_age_seconds: int = 7200,
    attestation_max_age_seconds: int | None = None,
    predicate_proof_max_age_seconds: int | None = None,
    inclusion_edge_max_age_seconds: int | None = None,
    evidence_cut_max_age_seconds: int | None = None,
    phase_time_changes: dict[str, str] | None = None,
    gate_terminal_completed_at: str | None = None,
    final_restart_operation_completed_at: str = "2026-08-12T09:14:09Z",
    final_restart_capability_expires_at: str = "2026-08-12T09:15:00Z",
    mid_attempt_renewal_times: tuple[str, str, str] | None = None,
    final_service_observation_times: tuple[str, str, str] = (
        "2026-08-12T09:14:09.1Z",
        "2026-08-12T09:14:10Z",
        "2026-08-12T09:14:10Z",
    ),
) -> Fixture:
    phase_times = {
        **_PHASE_TIMES[phase],
        **(phase_time_changes or {}),
    }
    conditional = not_applicable or conditional_applicable
    if scenario_gate is None:
        assignment_requires_scenario = (
            impact is GateImpact.BLOCKING
            and phase is not PromotionPhase.PREVALIDATED
        )
    else:
        assignment_requires_scenario = scenario_gate
    scenario_gate = assignment_requires_scenario and not not_applicable
    requirements = ControlRecord.build(
        kind="requirements",
        record_id="requirements:w0",
        payload={
            "approval_digest": digest("1"),
            "effective_at": "2026-08-12T05:30:00Z",
            "requirements_definition_digest": digest("2"),
            "requirement_digests": [digest("3")],
            "requirements_id": "w0-requirements",
            "requirements_version": 1,
        },
    )
    candidate = _generation("generation:candidate", "candidate-c", "4")
    target = _identity("identity:target", "reference-host", "target", "6")
    if predecessor_checkpoint is None:
        if phase is PromotionPhase.PUBLISHED:
            predecessor_checkpoint = _captured_checkpoint(target=target)
        else:
            predecessor_phase = {
                PromotionPhase.PREVALIDATED: PromotionPhase.PUBLISHED,
                PromotionPhase.ACTIVE: PromotionPhase.PREVALIDATED,
                PromotionPhase.ACCEPTED: PromotionPhase.ACTIVE,
            }[phase]
            predecessor_kwargs: dict[str, object] = {
                "phase": predecessor_phase,
                "scenario_gate": predecessor_phase is PromotionPhase.ACTIVE,
            }
            if predecessor_phase is PromotionPhase.ACTIVE:
                predecessor_kwargs.update(
                    scenario_target_kind="service",
                    scenario_target_id="inference-service",
                )
            predecessor_checkpoint = _materialize_structural_checkpoint(
                _fixture(**predecessor_kwargs)
            )
    if phase is PromotionPhase.PUBLISHED:
        accepted = predecessor_checkpoint.generation_record
        active = predecessor_checkpoint.generation_record
    else:
        predecessor_cut = predecessor_checkpoint.evidence_cut
        assert predecessor_cut is not None
        if phase is PromotionPhase.PREVALIDATED:
            accepted = predecessor_cut.accepted_generation_record
            active = predecessor_cut.active_generation_record
        elif phase is PromotionPhase.ACTIVE:
            accepted = predecessor_cut.accepted_generation_record
            active = candidate
        else:
            accepted = candidate
            active = candidate
    captured_checkpoint = predecessor_checkpoint
    while isinstance(
        captured_checkpoint,
        (LifecycleCheckpoint, StructuralLifecycleCandidate),
    ) and captured_checkpoint.predecessor_checkpoint is not None:
        captured_checkpoint = captured_checkpoint.predecessor_checkpoint
    assert isinstance(
        captured_checkpoint,
        (LifecycleCheckpoint, StructuralBaselineCapture),
    )
    prior = accepted
    if phase is PromotionPhase.ACCEPTED:
        target_state = predecessor_checkpoint.target_protected_state_record
    else:
        promotion_target_kind = (
            "isolated_root"
            if phase is PromotionPhase.PREVALIDATED
            else "package_repository"
            if phase is PromotionPhase.PUBLISHED
            else "live_root"
        )
        target_state = _protected_state(
            "protected-state:target",
            generation=candidate,
            target=target,
            phase=phase.value,
            seed={
                PromotionPhase.PUBLISHED: "7",
                PromotionPhase.PREVALIDATED: "8",
                PromotionPhase.ACTIVE: "9",
            }[phase],
            observed_at=(
                phase_times.get("phase_operation_terminal")
                if phase is PromotionPhase.ACTIVE and scenario_gate
                else phase_times["operation_terminal"]
            ),
            fence_epoch=(
                (
                    predecessor_checkpoint.baseline_restoration_receipt.restored_protected_state_record.payload[
                        "fence_epoch"
                    ]
                    if phase is PromotionPhase.ACTIVE
                    and isinstance(
                        predecessor_checkpoint,
                        (LifecycleCheckpoint, StructuralLifecycleCandidate),
                    )
                    and isinstance(
                        predecessor_checkpoint.baseline_restoration_receipt,
                        BaselineRestorationReceipt,
                    )
                    else captured_checkpoint.target_protected_state_record.payload[
                        "fence_epoch"
                    ]
                    if phase is PromotionPhase.PREVALIDATED
                    else predecessor_checkpoint.target_protected_state_record.payload[
                        "fence_epoch"
                    ]
                )
                + 1
            ),
            target_kind=promotion_target_kind,
        )
        target_state = ControlRecord.build(
            kind="protected_state",
            record_id="protected-state:target:phase-transition",
            payload={
                **_payload(target_state),
                "projection_id": (
                    predecessor_checkpoint.target_protected_state_record.payload[
                        "projection_id"
                    ]
                ),
            },
        )
    promotion_target_kind = {
        PromotionPhase.PUBLISHED: "package_repository",
        PromotionPhase.PREVALIDATED: "isolated_root",
        PromotionPhase.ACTIVE: "live_root",
        PromotionPhase.ACCEPTED: "live_root",
    }[phase]
    if phase is PromotionPhase.ACCEPTED:
        scenario_target_kind = scenario_target_kind or "service"
        if scenario_target_id == "reference-host":
            scenario_target_id = "inference-service"
    predecessor_service_receipt = (
        predecessor_checkpoint.service_anchor_receipt
        if phase is PromotionPhase.ACCEPTED
        and isinstance(
            predecessor_checkpoint,
            (LifecycleCheckpoint, StructuralLifecycleCandidate),
        )
        else None
    )
    scenario_target = (
        predecessor_service_receipt.target_record
        if isinstance(predecessor_service_receipt, ServiceAnchorReceipt)
        else
        target
        if scenario_target_id == target.payload["identity_id"]
        else _identity(
            "identity:scenario-target",
            scenario_target_id,
            "target",
            "8",
        )
    )
    subject = _identity("identity:subject", "generation-c", "subject", "c")
    actor = _identity(
        "identity:validator",
        "validator-w0",
        "principal",
        "7",
        roles=attestor_roles,
    )
    separation_policy = ControlRecord.build(
        kind="separation_policy",
        record_id="separation-policy:control-plane",
        payload={
            "forbidden_actor_identity_digests": [],
            "policy_id": "control-plane-separation",
            "required_actor_roles": ["validator"],
        },
    )
    acceptance_actor = None
    acceptance_separation = None
    acceptance_authorization = None
    if phase is PromotionPhase.ACCEPTED:
        acceptance_actor = _identity(
            "identity:acceptance-owner",
            "acceptance-owner",
            "principal",
            "8",
            roles=["control-owner"],
        )
        acceptance_separation = ControlRecord.build(
            kind="separation_policy",
            record_id="separation-policy:acceptance",
            payload={
                "forbidden_actor_identity_digests": [actor.digest()],
                "policy_id": "acceptance-separation",
                "required_actor_roles": ["control-owner"],
            },
        )
        acceptance_authorization = ControlRecord.build(
            kind="authorization",
            record_id="authorization:acceptance",
            payload={
                "action": "accept_generation",
                "allowed_actor_identity_digests": [acceptance_actor.digest()],
                "allowed_actor_roles": ["control-owner"],
                "approver_roles": ["control-owner"],
                "policy_id": "acceptance",
                "recovery_root_digest": digest("1"),
                "separation_policy_digest": acceptance_separation.digest(),
                "subject_kind": "acceptance_request",
                "validity_policy_digest": digest("2"),
            },
        )
    attestation_authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:control-plane-attestation",
        payload={
            "action": "attest_gate",
            "allowed_actor_identity_digests": [actor.digest()],
            "allowed_actor_roles": (
                ["validator"]
                if allowed_attestor_roles is None
                else allowed_attestor_roles
            ),
            "approver_roles": ["control-owner"],
            "policy_id": "control-plane-attestation",
            "recovery_root_digest": digest("1"),
            "separation_policy_digest": separation_policy.digest(),
            "subject_kind": "gate",
            "validity_policy_digest": digest("2"),
        },
    )
    predicate_authorization = None
    if conditional:
        predicate_authorization = ControlRecord.build(
            kind="authorization",
            record_id="authorization:control-plane-predicate",
            payload={
                **_payload(attestation_authorization),
                "action": "evaluate_gate_predicate",
                "policy_id": "control-plane-predicate",
            },
        )
    gate = ControlRecord.build(
        kind="gate",
        record_id="gate:control-plane",
        payload={
            "assertion_digest": digest("d"),
            "attestation_authorization_digest": attestation_authorization.digest(),
            "evidence_shape_digest": digest("e"),
            "fixture_role_digest": digest("f"),
            "gate_id": "control-plane",
            "validator_digest": actor.digest(),
            **(
                {"predicate_authorization_digest": predicate_authorization.digest()}
                if predicate_authorization is not None
                else {}
            ),
        },
    )
    dependency_projection = ControlRecord.build(
        kind="dependency_projection",
        record_id="dependency-projection:control-plane",
        payload={
            "dependency_digests": [digest("1")],
            "dependency_keys": ["source:control-plane"],
            "projection_id": "control-plane-dependencies",
        },
    )
    validity_policy = ControlRecord.build(
        kind="validity_policy",
        record_id="validity-policy:control-plane",
        payload={
            "attestation_max_age_seconds": (
                evidence_max_age_seconds
                if attestation_max_age_seconds is None
                else attestation_max_age_seconds
            ),
            "evidence_cut_max_age_seconds": (
                evidence_max_age_seconds
                if evidence_cut_max_age_seconds is None
                else evidence_cut_max_age_seconds
            ),
            "expiry_rule": "earliest_constituent_expiry",
            "inclusion_edge_max_age_seconds": (
                evidence_max_age_seconds
                if inclusion_edge_max_age_seconds is None
                else inclusion_edge_max_age_seconds
            ),
            "policy_id": "control-plane-validity",
            "predicate_proof_max_age_seconds": (
                evidence_max_age_seconds
                if predicate_proof_max_age_seconds is None
                else predicate_proof_max_age_seconds
            ),
        },
    )
    invalidation_policy = ControlRecord.build(
        kind="invalidation_policy",
        record_id="invalidation-policy:control-plane",
        payload={
            "dependency_keys": ["source:control-plane"],
            "policy_id": "control-plane-invalidation",
        },
    )
    assignment_payload = {
        "applicability": "conditional" if conditional else "unconditional",
        "assignment_id": "control-plane",
        "authorization_policy_digest": attestation_authorization.digest(),
        "dependency_projection_digest": dependency_projection.digest(),
        "gate_digest": gate.digest(),
        "impact": impact.value,
        "execution_requirement": (
            "blocking_scenario"
            if assignment_requires_scenario
            else "evidence_only"
        ),
        "invalidation_policy_digest": invalidation_policy.digest(),
        "separation_policy_digest": separation_policy.digest(),
        "subject_digest": subject.digest(),
        "validity_policy_digest": validity_policy.digest(),
    }
    if conditional:
        assignment_payload["predicate_digest"] = digest("6")
    assignment = ControlRecord.build(
        kind="assignment",
        record_id="assignment:control-plane",
        payload=assignment_payload,
    )
    final_restart_assignment = (
        ControlRecord.build(
            kind="assignment",
            record_id="assignment:final-service-restart",
            payload={
                **{
                    key: value
                    for key, value in assignment_payload.items()
                    if key != "predicate_digest"
                },
                "applicability": "unconditional",
                "assignment_id": "final-service-restart",
                "execution_requirement": "blocking_scenario",
                "impact": GateImpact.BLOCKING.value,
            },
        )
        if phase is PromotionPhase.ACCEPTED
        else None
    )
    assignment_records = (
        (assignment, final_restart_assignment)
        if final_restart_assignment is not None
        else (assignment,)
    )
    assignment_set = ControlRecord.build(
        kind="assignment_set",
        record_id="assignment-set:w0",
        payload={
            "assignment_digests": [item.digest() for item in assignment_records],
            "requirements_digest": requirements.digest(),
        },
    )
    operation_requirements: list[OperationRequirement] = []
    operation_requirement_by_id: dict[str, OperationRequirement] = {}

    def add_operation_requirement(
        requirement_id: str,
        *,
        operation_kind: str,
        subject_kind: str,
        lifecycle_phase: str,
        target_record: ControlRecord,
        target_kind: str,
        purpose: str,
        assignment_record: ControlRecord | None = None,
        recovery_target_role: str = "expected_prestate",
    ) -> None:
        requirement = _operation_requirement(
            requirement_id=requirement_id,
            target_record=target_record,
            operation_kind=operation_kind,
            subject_kind=subject_kind,
            generation_binding_mode="required_generation",
            generation_class="c",
            lifecycle_phase=lifecycle_phase,
            target_kind=target_kind,
            purpose=purpose,
            assignment_record=assignment_record,
            recovery_target_role=recovery_target_role,
        )
        operation_requirements.append(requirement)
        operation_requirement_by_id[requirement_id] = requirement

    if assignment_requires_scenario:
        scenario_requirement_purpose = (
            "service_anchor"
            if phase is PromotionPhase.ACTIVE
            and (scenario_target_kind or promotion_target_kind) == "service"
            else "service_restart"
            if phase is PromotionPhase.ACCEPTED
            else "blocking_scenario"
        )
        add_operation_requirement(
            "blocking-scenario-1",
            operation_kind="blocking_scenario",
            subject_kind="gate_occurrence",
            lifecycle_phase=(
                PromotionPhase.ACTIVE.value
                if phase is PromotionPhase.ACCEPTED
                else phase.value
            ),
            target_record=scenario_target,
            target_kind=scenario_target_kind or promotion_target_kind,
            purpose=scenario_requirement_purpose,
            assignment_record=assignment,
        )
    if final_restart_assignment is not None:
        add_operation_requirement(
            "final-service-restart-1",
            operation_kind="blocking_scenario",
            subject_kind="gate_occurrence",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_record=scenario_target,
            target_kind="service",
            purpose="final_service_restart",
            assignment_record=final_restart_assignment,
        )
    phase_requirement_id = {
        PromotionPhase.PUBLISHED: (
            "repository-publication-1"
            if include_repository_publication
            else "phase-published-1"
        ),
        PromotionPhase.PREVALIDATED: "phase-prevalidated-1",
        PromotionPhase.ACTIVE: (
            "package-installation-1"
            if include_root_installation
            else "phase-active-1"
        ),
    }.get(phase)
    if phase_requirement_id is not None:
        add_operation_requirement(
            phase_requirement_id,
            operation_kind=(
                "repository_publication"
                if phase is PromotionPhase.PUBLISHED
                else "package_installation"
            ),
            subject_kind="generation",
            lifecycle_phase=phase.value,
            target_record=target,
            target_kind=promotion_target_kind,
            purpose="phase_transition",
        )
    if phase is PromotionPhase.PREVALIDATED:
        add_operation_requirement(
            "w4-baseline-rehearsal-install-1",
            operation_kind="package_installation",
            subject_kind="generation",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_record=target,
            target_kind="live_root",
            purpose="baseline_rehearsal_install",
        )
        add_operation_requirement(
            "w4-baseline-restoration-1",
            operation_kind="rollback",
            subject_kind="generation",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_record=target,
            target_kind="live_root",
            purpose="baseline_restoration",
            recovery_target_role="captured_baseline",
        )
    operation_requirement_set = ControlRecord.build(
        kind="operation_requirement_set",
        record_id="operation-requirement-set:w0",
        payload={
            "operation_requirement_digests": [
                item.requirement_digest for item in operation_requirements
            ],
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
            "max_live_attempt_seconds": max_live_attempt_seconds,
            "max_suite_seconds": max_suite_seconds,
            "operation_requirement_set_digest": (
                operation_requirement_set.digest()
            ),
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
    if phase is PromotionPhase.PREVALIDATED:
        gate_attempt_sequence = 9 if scenario_gate else 8
        gate_terminal_sequence = 10 if scenario_gate else 9
        complete_through_sequence = 11 if scenario_gate else 9
    elif phase is PromotionPhase.ACTIVE and scenario_gate:
        gate_attempt_sequence = 5
        gate_terminal_sequence = 6
        complete_through_sequence = 7
    else:
        gate_attempt_sequence = 3
        gate_terminal_sequence = 4
        complete_through_sequence = (
            10
            if phase is PromotionPhase.ACCEPTED
            else 7
            if scenario_gate
            else 6
        )
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
            "registered_at": phase_times["registered"],
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
            "journal_sequence": gate_attempt_sequence,
            "started_at": phase_times["started"],
        },
    )
    predicate_proof = None
    if conditional:
        predicate_proof = ControlRecord.build(
            kind="predicate_proof",
            record_id="predicate-proof:control-plane:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "actor_role": attestation_actor_role,
                "assignment_digest": assignment.digest(),
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "gate_digest": gate.digest(),
                "is_applicable": conditional_applicable,
                "observed_at": phase_times["observed"],
                "predicate_digest": assignment.payload["predicate_digest"],
                "subject_digest": subject.digest(),
            },
        )
    if not_applicable:
        evidence_records = (predicate_proof,)
        evaluation_payload = {
            "applicability": "not_applicable",
            "assignment_digest": assignment.digest(),
            "attestation_digests": [],
            "context_digest": context.digest(),
            "dependency_projection_digest": dependency_projection.digest(),
            "evaluated_at": phase_times["evaluated"],
            "outcome": "not_applicable",
            "predicate_proof_digest": predicate_proof.digest(),
        }
    else:
        attestation = ControlRecord.build(
            kind="attestation",
            record_id="attestation:control-plane:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "actor_role": attestation_actor_role,
                "assignment_digest": assignment.digest(),
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "gate_digest": gate.digest(),
                "observed_at": phase_times["observed"],
                "outcome": outcome,
                "subject_digest": subject.digest(),
            },
        )
        evaluation_payload = {
            "applicability": "applicable",
            "assignment_digest": assignment.digest(),
            "attestation_digests": [attestation.digest()],
            "context_digest": context.digest(),
            "dependency_projection_digest": dependency_projection.digest(),
            "evaluated_at": phase_times["evaluated"],
            "outcome": outcome,
            **(
                {"predicate_proof_digest": predicate_proof.digest()}
                if predicate_proof is not None
                else {}
            ),
        }
        evidence_records = (
            (predicate_proof, attestation)
            if predicate_proof is not None
            else (attestation,)
        )
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
                "verified_at": phase_times["included"],
                "verifier_identity_digest": actor.digest(),
            },
        )
    trusted_time = ControlRecord.build(
        kind="trusted_time_observation",
        record_id="trusted-time:control-plane",
        payload={
            "authority_head_digest": digest("9"),
            "observation_id": "control-plane-currency",
            "observed_at": phase_times["trusted_time"],
            "time_authority_digest": digest("8"),
            "time_proof_digest": digest("7"),
        },
    )
    invalidation_checkpoint = ControlRecord.build(
        kind="invalidation_stream_checkpoint",
        record_id="invalidation-stream-checkpoint:control-plane",
        payload={
            "authority_head_digest": digest("9"),
            "authority_manifest_digest": digest("a"),
            "authority_view_digest": digest("2"),
            "checkpoint_id": "control-plane-currency",
            "checkpointed_at": phase_times["currency_checkpoint"],
            "complete_through_sequence": complete_through_sequence,
            "completeness_proof_digest": digest("b"),
            "current_dependency_projection_digest": dependency_projection.digest(),
            "fork_proof_digest": digest("c"),
            "invalidation_policy_digest": invalidation_policy.digest(),
            "stream_head_digest": digest("6"),
            "stream_id": "control-plane-invalidations",
        },
    )
    currency_proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence-currency-proof:control-plane",
        payload={
            "evaluated_dependency_projection_digest": (
                dependency_projection.digest()
            ),
            "evaluation_digest": evaluation.digest(),
            "inclusion_edge_digests": (
                [inclusion_edge.digest()] if inclusion_edge is not None else []
            ),
            "invalidation_policy_digest": invalidation_policy.digest(),
            "invalidation_stream_checkpoint_digest": (
                invalidation_checkpoint.digest()
            ),
            "trusted_time_observation_digest": trusted_time.digest(),
            "validity_policy_digest": validity_policy.digest(),
        },
    )
    bound = BoundEvaluation(
        attempt_record=attempt_record,
        context_record=context,
        assignment_record=assignment,
        gate_record=gate,
        attestation_authorization_record=attestation_authorization,
        predicate_authorization_record=predicate_authorization,
        separation_policy_record=separation_policy,
        validator_identity_record=actor,
        evidence_records=evidence_records,
        evaluation_record=evaluation,
        validity_policy_record=validity_policy,
        invalidation_policy_record=invalidation_policy,
        evaluated_dependency_projection_record=dependency_projection,
        current_dependency_projection_record=dependency_projection,
        trusted_time_observation_record=trusted_time,
        invalidation_stream_checkpoint_record=invalidation_checkpoint,
        currency_proof_record=currency_proof,
        inclusion_edge_record=inclusion_edge,
    )
    terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:1",
        payload={
            "assignment_digest": assignment.digest(),
            "attempt_digest": attempt_record.digest(),
            "completed_at": gate_terminal_completed_at or phase_times["terminal"],
            "journal_sequence": gate_terminal_sequence,
            "outcome": (
                "succeeded"
                if not_applicable or outcome == "pass"
                else "failed"
            ),
            "poststate_digest": target_state.digest(),
            "terminal_type": "gate_attempt",
            "validator_attestation_digests": (
                [] if not_applicable else [attestation.digest()]
            ),
            **(
                {"predicate_proof_digest": predicate_proof.digest()}
                if predicate_proof is not None
                else {}
            ),
        },
    )
    final_restart_intent = (
        ControlRecord.build(
            kind="intent",
            record_id="intent:final-service-restart:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "assignment_digest": final_restart_assignment.digest(),
                "context_digest": context.digest(),
                "intent_id": "final-service-restart-1",
                "intent_type": "gate_occurrence",
                "journal_sequence": 6,
                "registered_at": "2026-08-12T09:14:01Z",
                "subject_digest": subject.digest(),
            },
        )
        if final_restart_assignment is not None
        else None
    )
    operations: list[RegisteredOperation] = []
    operation_obligations: list[OperationObligation] = []
    scenario_operation_obligation: OperationObligation | None = None
    active_service_state = None
    next_operation_sequence = 2 if phase is PromotionPhase.PREVALIDATED else 5
    if scenario_gate:
        scenario_phase = scenario_lifecycle_phase or (
            PromotionPhase.ACTIVE.value
            if phase is PromotionPhase.ACCEPTED
            else phase.value
        )
        scenario_state = target_state
        scenario_expected_state = None
        if phase is PromotionPhase.ACCEPTED:
            assert isinstance(predecessor_service_receipt, ServiceAnchorReceipt)
            active_service_state = (
                predecessor_service_receipt.service_protected_state_record
            )
            scenario_expected_state = active_service_state
            scenario_state = _protected_state(
                "protected-state:scenario-intended",
                generation=candidate,
                target=scenario_target,
                phase=scenario_phase,
                seed="c",
                observed_at=phase_times["operation_terminal"],
                fence_epoch=active_service_state.payload["fence_epoch"] + 1,
                target_kind="service",
            )
            scenario_state = ControlRecord.build(
                kind="protected_state",
                record_id="protected-state:scenario-intended:active-projection",
                payload={
                    **_payload(scenario_state),
                    "process_epoch": "service-epoch-2",
                    "projection_id": active_service_state.payload["projection_id"],
                },
            )
        elif phase is PromotionPhase.ACTIVE and scenario_target_kind == "service":
            scenario_expected_state = _protected_state(
                "protected-state:service-prestate",
                generation=candidate,
                target=scenario_target,
                phase=PromotionPhase.ACTIVE.value,
                seed="a",
                observed_at="2026-08-12T09:10:25Z",
                fence_epoch=20,
                target_kind="service",
            )
            scenario_expected_state = ControlRecord.build(
                kind="protected_state",
                record_id="protected-state:service-prestate:active-projection",
                payload={
                    **_payload(scenario_expected_state),
                    "projection_id": "active-service-state",
                },
            )
            scenario_state = _protected_state(
                "protected-state:service-anchor",
                generation=candidate,
                target=scenario_target,
                phase=PromotionPhase.ACTIVE.value,
                seed="b",
                observed_at=phase_times["operation_terminal"],
                fence_epoch=scenario_expected_state.payload["fence_epoch"] + 1,
                target_kind="service",
            )
            scenario_state = ControlRecord.build(
                kind="protected_state",
                record_id="protected-state:service-anchor:active-projection",
                payload={
                    **_payload(scenario_state),
                    "process_epoch": "service-epoch-1",
                    "projection_id": scenario_expected_state.payload[
                        "projection_id"
                    ],
                },
            )
        scenario_operation = _build_registered_operation(
            subject_digest=intent.digest(),
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=scenario_state,
            target_record=scenario_target,
            lifecycle_phase=scenario_phase,
            target_kind=scenario_target_kind or promotion_target_kind,
            target_id=scenario_target_id,
            intent_sequence=(
                4 if phase is PromotionPhase.ACTIVE else 2
            ),
            terminal_sequence=(
                7
                if phase is PromotionPhase.ACTIVE
                else 11
                if phase is PromotionPhase.PREVALIDATED
                else 5
            ),
            expected_state_record=scenario_expected_state,
            bind_intended_state=(
                phase is PromotionPhase.ACCEPTED
                or phase is PromotionPhase.ACTIVE
                and scenario_target_kind == "service"
            ),
            registered_at=phase_times["scenario_registered"],
            issued_at=phase_times["scenario_capability"],
            attested_at=phase_times.get(
                "scenario_operation_observed",
                phase_times["operation_observed"],
            ),
            completed_at=phase_times.get(
                "scenario_operation_terminal",
                phase_times["operation_terminal"],
            ),
            expires_at=phase_times["capability_expires"],
        )
        next_operation_sequence = (
            8
            if phase is PromotionPhase.ACTIVE
            else 3
            if phase is PromotionPhase.PREVALIDATED
            else 6
        )
        operations.append(scenario_operation)
        scenario_operation_obligation = _operation_obligation(
            scenario_operation,
            obligation_id="blocking-scenario-1",
            requirement=operation_requirement_by_id["blocking-scenario-1"],
        )
        operation_obligations.append(scenario_operation_obligation)
    final_restart_operation = None
    final_restart_operation_obligation = None
    final_restart_promotion_obligation = None
    final_restart_registered_attempt = None
    if final_restart_assignment is not None:
        assert isinstance(predecessor_service_receipt, ServiceAnchorReceipt)
        assert final_restart_intent is not None
        final_restart_expected_state = (
            operations[-1].intended_protected_state_record
            if operations
            else predecessor_service_receipt.service_protected_state_record
        )
        final_restart_state = _protected_state(
            "protected-state:final-service-restart",
            generation=candidate,
            target=scenario_target,
            phase=PromotionPhase.ACTIVE.value,
            seed="e",
            observed_at=final_restart_operation_completed_at,
            fence_epoch=final_restart_expected_state.payload["fence_epoch"] + 1,
            target_kind="service",
        )
        final_restart_state = ControlRecord.build(
            kind="protected_state",
            record_id="protected-state:final-service-restart:active-projection",
            payload={
                **_payload(final_restart_state),
                "process_epoch": "service-epoch-3",
                "projection_id": final_restart_expected_state.payload[
                    "projection_id"
                ],
            },
        )
        final_restart_operation = _build_registered_operation(
            subject_digest=final_restart_intent.digest(),
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=final_restart_state,
            target_record=scenario_target,
            expected_state_record=final_restart_expected_state,
            bind_intended_state=True,
            operation_id="final-service-restart-1",
            operation_kind="blocking_scenario",
            subject_kind="gate_occurrence",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_kind="service",
            target_id=scenario_target.payload["identity_id"],
            intent_sequence=7,
            terminal_sequence=10,
            registered_at="2026-08-12T09:14:02Z",
            issued_at="2026-08-12T09:14:03Z",
            attested_at=final_restart_operation_completed_at,
            completed_at=final_restart_operation_completed_at,
            expires_at=final_restart_capability_expires_at,
        )
        operations.append(final_restart_operation)
        final_restart_operation_obligation = _operation_obligation(
            final_restart_operation,
            obligation_id="final-service-restart-1",
            requirement=operation_requirement_by_id[
                "final-service-restart-1"
            ],
        )
        operation_obligations.append(final_restart_operation_obligation)
        final_restart_promotion_obligation_record = ControlRecord.build(
            kind="promotion_obligation",
            record_id="promotion-obligation:final-service-restart",
            payload={
                "assignment_digest": final_restart_assignment.digest(),
                "impact": GateImpact.BLOCKING.value,
                "obligation_id": "final-service-restart",
                "occurrence_digest": final_restart_intent.digest(),
                "scenario_operation_obligation_digest": (
                    final_restart_operation_obligation.obligation_digest
                ),
            },
        )
        final_restart_promotion_obligation = PromotionObligation(
            final_restart_promotion_obligation_record
        )
    if include_repository_publication:
        publication_prestate = _target_prestate_observation(
            "protected-state:repository-publication-prestate",
            source_state=predecessor_checkpoint.target_protected_state_record,
            target_record=target,
            target_kind="package_repository",
            observed_at=phase_times["operation_registered"],
        )
        publication = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=target_state,
            target_record=target,
            operation_id="repository-publication-1",
            operation_kind="repository_publication",
            lifecycle_phase=phase.value,
            target_kind="package_repository",
            target_id=target.payload["identity_id"],
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
            registered_at=phase_times["operation_registered"],
            issued_at=phase_times["capability_issued"],
            attested_at=phase_times["operation_observed"],
            completed_at=phase_times["operation_terminal"],
            expires_at=phase_times["capability_expires"],
            expected_state_record=(
                publication_prestate
                if phase is PromotionPhase.PUBLISHED
                else None
            ),
            bind_intended_state=phase is PromotionPhase.PUBLISHED,
        )
        next_operation_sequence += 2
        operations.append(publication)
        operation_obligations.append(
            _operation_obligation(
                publication,
                obligation_id="repository-publication-1",
                requirement=operation_requirement_by_id[
                    "repository-publication-1"
                ],
            )
        )
    if include_root_installation:
        installation_expected_state = (
            predecessor_checkpoint.baseline_restoration_receipt.restored_protected_state_record
            if phase is PromotionPhase.ACTIVE
            and isinstance(
                predecessor_checkpoint.baseline_restoration_receipt,
                BaselineRestorationReceipt,
            )
            else predecessor_checkpoint.target_protected_state_record
            if phase is PromotionPhase.ACTIVE
            else None
        )
        installation_intent_sequence = (
            2 if phase is PromotionPhase.ACTIVE and scenario_gate else next_operation_sequence
        )
        installation = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=target_state,
            target_record=target,
            operation_id="package-installation-1",
            operation_kind="package_installation",
            lifecycle_phase=phase.value,
            target_kind="live_root",
            target_id=target.payload["identity_id"],
            intent_sequence=installation_intent_sequence,
            terminal_sequence=installation_intent_sequence + 1,
            registered_at=(
                "2026-08-12T09:10:56Z"
                if phase is PromotionPhase.ACTIVE and not scenario_gate
                else phase_times["operation_registered"]
            ),
            issued_at=(
                "2026-08-12T09:10:57Z"
                if phase is PromotionPhase.ACTIVE and not scenario_gate
                else phase_times["capability_issued"]
            ),
            attested_at=(
                phase_times["operation_terminal"]
                if phase is PromotionPhase.ACTIVE and not scenario_gate
                else phase_times.get(
                    "phase_operation_observed",
                    phase_times["operation_observed"],
                )
            ),
            completed_at=(
                phase_times["operation_terminal"]
                if phase is PromotionPhase.ACTIVE and not scenario_gate
                else phase_times.get(
                    "phase_operation_terminal",
                    phase_times["operation_terminal"],
                )
            ),
            expires_at=phase_times["capability_expires"],
            expected_state_record=installation_expected_state,
            bind_intended_state=phase is PromotionPhase.ACTIVE,
        )
        if not (phase is PromotionPhase.ACTIVE and scenario_gate):
            next_operation_sequence += 2
        operations.append(installation)
        operation_obligations.append(
            _operation_obligation(
                installation,
                obligation_id="package-installation-1",
                requirement=operation_requirement_by_id[
                    "package-installation-1"
                ],
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
    promotion_obligations = (
        (obligation, final_restart_promotion_obligation)
        if final_restart_promotion_obligation is not None
        else (obligation,)
    )
    operation_obligations_tuple = tuple(operation_obligations)
    operations_tuple = tuple(operations)
    operation_obligation_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation-obligation-set:w0",
        payload={
            "obligation_digests": [
                item.obligation_digest for item in operation_obligations_tuple
            ],
            "operation_requirement_set_digest": (
                operation_requirement_set.digest()
            ),
            "requirements_digest": requirements.digest(),
        },
    )
    registered_attempt = RegisteredAttempt(
        obligation_record=obligation_record,
        intent_record=intent,
        attempt_record=attempt_record,
        terminal_record=terminal_record,
    )
    final_restart_intent = None
    final_restart_attempt_record = None
    final_restart_bound = None
    final_restart_terminal_record = None
    final_restart_inclusion_edge = None
    if final_restart_assignment is not None:
        final_restart_intent = ControlRecord.build(
            kind="intent",
            record_id="intent:final-service-restart:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "assignment_digest": final_restart_assignment.digest(),
                "context_digest": context.digest(),
                "intent_id": "final-service-restart-1",
                "intent_type": "gate_occurrence",
                "journal_sequence": 6,
                "registered_at": "2026-08-12T09:14:01Z",
                "subject_digest": subject.digest(),
            },
        )
        final_restart_attempt_record = ControlRecord.build(
            kind="attempt",
            record_id="attempt:final-service-restart:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "assignment_digest": final_restart_assignment.digest(),
                "attempt_id": "final-service-restart-1",
                "context_digest": context.digest(),
                "decision": "admitted",
                "intent_digest": final_restart_intent.digest(),
                "journal_sequence": 8,
                "started_at": "2026-08-12T09:14:04Z",
            },
        )
        final_restart_attestation = ControlRecord.build(
            kind="attestation",
            record_id="attestation:final-service-restart:1",
            payload={
                "actor_identity_digest": actor.digest(),
                "actor_role": attestation_actor_role,
                "assignment_digest": final_restart_assignment.digest(),
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "gate_digest": gate.digest(),
                "observed_at": "2026-08-12T09:14:05Z",
                "outcome": "pass",
                "subject_digest": subject.digest(),
            },
        )
        final_restart_evaluation = ControlRecord.build(
            kind="evaluation",
            record_id="evaluation:final-service-restart:1",
            payload={
                "applicability": "applicable",
                "assignment_digest": final_restart_assignment.digest(),
                "attestation_digests": [final_restart_attestation.digest()],
                "context_digest": context.digest(),
                "dependency_projection_digest": dependency_projection.digest(),
                "evaluated_at": "2026-08-12T09:14:06Z",
                "outcome": "pass",
            },
        )
        if inclusion_edge is not None:
            final_restart_inclusion_edge = ControlRecord.build(
                kind="inclusion_edge",
                record_id="inclusion-edge:final-service-restart:1",
                payload={
                    **_payload(inclusion_edge),
                    "assignment_digests": [final_restart_assignment.digest()],
                    "inclusion_edge_id": "final-service-restart-1",
                    "preassembly_evaluation_digests": [
                        final_restart_evaluation.digest()
                    ],
                    "verified_at": "2026-08-12T09:14:06Z",
                },
            )
        final_restart_terminal_record = ControlRecord.build(
            kind="terminal_record",
            record_id="terminal:final-service-restart:1",
            payload={
                "assignment_digest": final_restart_assignment.digest(),
                "attempt_digest": final_restart_attempt_record.digest(),
                "completed_at": "2026-08-12T09:14:07Z",
                "journal_sequence": 9,
                "outcome": "succeeded",
                "poststate_digest": target_state.digest(),
                "terminal_type": "gate_attempt",
                "validator_attestation_digests": [
                    final_restart_attestation.digest()
                ],
            },
        )
        final_restart_stream = ControlRecord.build(
            kind="invalidation_stream_checkpoint",
            record_id="invalidation-stream-checkpoint:final-service-restart",
            payload={
                **_payload(invalidation_checkpoint),
                "checkpoint_id": "final-service-restart-currency",
                "complete_through_sequence": 10,
            },
        )
        final_restart_currency = ControlRecord.build(
            kind="evidence_currency_proof",
            record_id="evidence-currency-proof:final-service-restart",
            payload={
                **_payload(currency_proof),
                "evaluation_digest": final_restart_evaluation.digest(),
                "inclusion_edge_digests": (
                    [final_restart_inclusion_edge.digest()]
                    if final_restart_inclusion_edge is not None
                    else []
                ),
                "invalidation_stream_checkpoint_digest": (
                    final_restart_stream.digest()
                ),
            },
        )
        final_restart_bound = BoundEvaluation(
            attempt_record=final_restart_attempt_record,
            context_record=context,
            assignment_record=final_restart_assignment,
            gate_record=gate,
            attestation_authorization_record=attestation_authorization,
            predicate_authorization_record=None,
            separation_policy_record=separation_policy,
            validator_identity_record=actor,
            evidence_records=(final_restart_attestation,),
            evaluation_record=final_restart_evaluation,
            validity_policy_record=validity_policy,
            invalidation_policy_record=invalidation_policy,
            evaluated_dependency_projection_record=dependency_projection,
            current_dependency_projection_record=dependency_projection,
            trusted_time_observation_record=trusted_time,
            invalidation_stream_checkpoint_record=final_restart_stream,
            currency_proof_record=final_restart_currency,
            inclusion_edge_record=final_restart_inclusion_edge,
        )
        assert final_restart_promotion_obligation is not None
        final_restart_registered_attempt = RegisteredAttempt(
            obligation_record=(
                final_restart_promotion_obligation.obligation_record
            ),
            intent_record=final_restart_intent,
            attempt_record=final_restart_attempt_record,
            terminal_record=final_restart_terminal_record,
        )
    if phase is not PromotionPhase.ACCEPTED:
        phase_operation_kind = {
            PromotionPhase.PUBLISHED: "repository_publication",
            PromotionPhase.PREVALIDATED: "package_installation",
            PromotionPhase.ACTIVE: "package_installation",
        }[phase]
        phase_establishing_obligation = next(
            (
                item
                for item in operation_obligations_tuple
                if item.obligation_record.payload["operation_kind"]
                == phase_operation_kind
                and item.obligation_record.payload["lifecycle_phase"] == phase.value
                and item.obligation_record.payload["target_kind"]
                == promotion_target_kind
            ),
            None,
        )
        if phase_establishing_obligation is None:
            phase_expected_state = (
                predecessor_checkpoint.target_protected_state_record
            )
            if phase is PromotionPhase.PUBLISHED:
                phase_expected_state = _target_prestate_observation(
                    "protected-state:published-target-prestate",
                    source_state=phase_expected_state,
                    target_record=target,
                    target_kind=promotion_target_kind,
                    observed_at=phase_times["operation_registered"],
                )
            elif phase is PromotionPhase.PREVALIDATED:
                captured_baseline = predecessor_checkpoint.predecessor_checkpoint
                assert isinstance(captured_baseline, StructuralBaselineCapture)
                captured_state = captured_baseline.target_protected_state_record
                phase_expected_state = _protected_state(
                    "protected-state:w4-isolated-baseline",
                    generation=captured_baseline.generation_record,
                    target=target,
                    phase=LifecyclePhase.CAPTURED.value,
                    seed="0",
                    observed_at=captured_state.payload["observed_at"],
                    fence_epoch=captured_state.payload["fence_epoch"],
                    target_kind="isolated_root",
                )
                phase_expected_state = ControlRecord.build(
                    kind="protected_state",
                    record_id="protected-state:w4-isolated-baseline:projection",
                    payload={
                        **_payload(phase_expected_state),
                        "projection_id": captured_state.payload["projection_id"],
                        "state_digest": captured_state.payload["state_digest"],
                    },
                )
            elif phase is PromotionPhase.ACTIVE:
                receipt = predecessor_checkpoint.baseline_restoration_receipt
                assert isinstance(receipt, BaselineRestorationReceipt)
                phase_expected_state = receipt.restored_protected_state_record
            phase_intent_sequence = (
                2
                if phase is PromotionPhase.ACTIVE and scenario_gate
                else next_operation_sequence
            )
            phase_operation = _build_registered_operation(
                subject_digest=candidate.digest(),
                subject_kind="generation",
                context_digest=context.digest(),
                candidate_generation=candidate,
                target_state=target_state,
                target_record=target,
                operation_id=f"phase-{phase.value}-1",
                operation_kind=phase_operation_kind,
                lifecycle_phase=phase.value,
                target_kind=promotion_target_kind,
                target_id=target.payload["identity_id"],
                intent_sequence=phase_intent_sequence,
                terminal_sequence=phase_intent_sequence + 1,
                expected_state_record=phase_expected_state,
                bind_intended_state=True,
                registered_at=(
                    "2026-08-12T09:10:56Z"
                    if phase is PromotionPhase.ACTIVE and not scenario_gate
                    else phase_times["operation_registered"]
                ),
                issued_at=(
                    "2026-08-12T09:10:57Z"
                    if phase is PromotionPhase.ACTIVE and not scenario_gate
                    else phase_times["capability_issued"]
                ),
                attested_at=(
                    phase_times["operation_terminal"]
                    if phase is PromotionPhase.ACTIVE and not scenario_gate
                    else phase_times.get(
                        "phase_operation_observed",
                        phase_times["operation_observed"],
                    )
                ),
                completed_at=(
                    phase_times["operation_terminal"]
                    if phase is PromotionPhase.ACTIVE and not scenario_gate
                    else phase_times.get(
                        "phase_operation_terminal",
                        phase_times["operation_terminal"],
                    )
                ),
                expires_at=phase_times["capability_expires"],
            )
            if not (phase is PromotionPhase.ACTIVE and scenario_gate):
                next_operation_sequence += 2
            operations.append(phase_operation)
            phase_establishing_obligation = _operation_obligation(
                phase_operation,
                obligation_id=f"phase-{phase.value}-1",
                requirement=operation_requirement_by_id[
                    f"phase-{phase.value}-1"
                ],
            )
            operation_obligations.append(phase_establishing_obligation)
            operation_obligations_tuple = tuple(operation_obligations)
            operations_tuple = tuple(operations)
            operation_obligation_set = ControlRecord.build(
                kind="operation_obligation_set",
                record_id="operation-obligation-set:w0:phase-total",
                payload={
                    "obligation_digests": [
                        item.obligation_digest
                        for item in operation_obligations_tuple
                    ],
                    "operation_requirement_set_digest": (
                        operation_requirement_set.digest()
                    ),
                    "requirements_digest": requirements.digest(),
                },
            )
    else:
        phase_establishing_obligation = None

    if phase is PromotionPhase.PREVALIDATED:
        captured_baseline = predecessor_checkpoint.predecessor_checkpoint
        assert isinstance(captured_baseline, StructuralBaselineCapture)
        live_prestate = _target_prestate_observation(
            "protected-state:w4-live-prestate",
            source_state=captured_baseline.target_protected_state_record,
            target_record=target,
            target_kind="live_root",
            observed_at="2026-08-12T08:11:00Z",
        )
        rehearsal_state = _protected_state(
            "protected-state:w4-candidate-live",
            generation=candidate,
            target=target,
            phase=PromotionPhase.ACTIVE.value,
            seed="d",
            observed_at="2026-08-12T08:11:06Z",
            fence_epoch=live_prestate.payload["fence_epoch"] + 1,
            target_kind="live_root",
        )
        rehearsal_state = ControlRecord.build(
            kind="protected_state",
            record_id="protected-state:w4-candidate-live:projection",
            payload={
                **_payload(rehearsal_state),
                "projection_id": live_prestate.payload["projection_id"],
            },
        )
        rehearsal_operation = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=rehearsal_state,
            target_record=target,
            expected_state_record=live_prestate,
            bind_intended_state=True,
            operation_id="w4-baseline-rehearsal-install-1",
            operation_kind="package_installation",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_kind="live_root",
            target_id=target.payload["identity_id"],
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
            registered_at="2026-08-12T08:11:01Z",
            issued_at="2026-08-12T08:11:02Z",
            attested_at="2026-08-12T08:11:06Z",
            completed_at="2026-08-12T08:11:06Z",
            expires_at=phase_times["capability_expires"],
        )
        next_operation_sequence += 2
        operations.append(rehearsal_operation)
        operation_obligations.append(
            _operation_obligation(
                rehearsal_operation,
                obligation_id="w4-baseline-rehearsal-install-1",
                requirement=operation_requirement_by_id[
                    "w4-baseline-rehearsal-install-1"
                ],
            )
        )
        restored_state = _protected_state(
            "protected-state:w4-restored-baseline",
            generation=captured_baseline.generation_record,
            target=target,
            phase=PromotionPhase.ACTIVE.value,
            seed="0",
            observed_at="2026-08-12T08:11:15Z",
            fence_epoch=rehearsal_state.payload["fence_epoch"] + 1,
            target_kind="live_root",
        )
        restored_state = ControlRecord.build(
            kind="protected_state",
            record_id="protected-state:w4-restored-baseline:projection",
            payload={
                **_payload(restored_state),
                "projection_id": live_prestate.payload["projection_id"],
                "state_digest": live_prestate.payload["state_digest"],
            },
        )
        restoration_operation = _build_registered_operation(
            subject_digest=candidate.digest(),
            subject_kind="generation",
            context_digest=context.digest(),
            candidate_generation=candidate,
            target_state=restored_state,
            target_record=target,
            expected_state_record=rehearsal_state,
            bind_intended_state=True,
            operation_id="w4-baseline-restoration-1",
            operation_kind="rollback",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_kind="live_root",
            target_id=target.payload["identity_id"],
            intent_sequence=next_operation_sequence,
            terminal_sequence=next_operation_sequence + 1,
            registered_at="2026-08-12T08:11:10Z",
            issued_at="2026-08-12T08:11:11Z",
            attested_at="2026-08-12T08:11:15Z",
            completed_at="2026-08-12T08:11:16Z",
            expires_at=phase_times["capability_expires"],
            recovery_target_digest=(
                captured_baseline.target_protected_state_record.digest()
            ),
        )
        next_operation_sequence += 2
        operations.append(restoration_operation)
        operation_obligations.append(
            _operation_obligation(
                restoration_operation,
                obligation_id="w4-baseline-restoration-1",
                requirement=operation_requirement_by_id[
                    "w4-baseline-restoration-1"
                ],
            )
        )
        operation_obligations_tuple = tuple(operation_obligations)
        operations_tuple = tuple(operations)
        operation_obligation_set = ControlRecord.build(
            kind="operation_obligation_set",
            record_id="operation-obligation-set:w0:w4-restoration",
            payload={
                "obligation_digests": [
                    item.obligation_digest for item in operation_obligations_tuple
                ],
                "operation_requirement_set_digest": (
                    operation_requirement_set.digest()
                ),
                "requirements_digest": requirements.digest(),
            },
        )
        terminal_record = ControlRecord.build(
            kind="terminal_record",
            record_id="terminal:control-plane:1:w4-smoke",
            payload={
                **_payload(terminal_record),
                "poststate_digest": restored_state.digest(),
            },
        )
        registered_attempt = RegisteredAttempt(
            obligation_record=obligation_record,
            intent_record=intent,
            attempt_record=attempt_record,
            terminal_record=terminal_record,
        )

    registered_attempts = (
        (registered_attempt, final_restart_registered_attempt)
        if final_restart_registered_attempt is not None
        else (registered_attempt,)
    )
    bound_evaluations = (
        (bound, final_restart_bound)
        if final_restart_bound is not None
        else (bound,)
    )
    inclusion_edge_records_tuple = tuple(
        edge
        for edge in (inclusion_edge, final_restart_inclusion_edge)
        if edge is not None
    )
    observation_records_tuple: tuple[ControlRecord, ...] = ()
    if phase is PromotionPhase.ACTIVE and any(
        requirement.requirement_record.payload["purpose"] == "service_anchor"
        for requirement in operation_requirements
    ):
        service_operation = next(
            operation
            for operation in operations_tuple
            if any(
                obligation.operation_digest == operation.operation_digest
                and obligation.requirement.requirement_record.payload["purpose"]
                == "service_anchor"
                for obligation in operation_obligations_tuple
            )
        )
        service_state = service_operation.intended_protected_state_record
        process_epoch = service_state.payload["process_epoch"]
        service_observation_authorization = _service_observation_authorization(
            actor,
            separation_policy,
        )
        backend_provenance = ControlRecord.build(
            kind="backend_provenance",
            record_id="backend-provenance:w5",
            payload={
                "authorization_digest": service_observation_authorization.digest(),
                "backend_id": "llama-cpp-vulkan",
                "backend_manifest_digest": digest("1"),
                "configuration_digest": digest("2"),
                "driver_device_digest": digest("3"),
                "generation_digest": candidate.digest(),
                "model_identity_digest": digest("4"),
                "observed_at": "2026-08-12T09:11:01Z",
                "observer_identity_digest": actor.digest(),
                "package_manifest_digest": digest("5"),
                "process_epoch": process_epoch,
                "provenance_id": "w5-service-backend",
                "service_protected_state_digest": service_state.digest(),
                "target_digest": service_operation.target_record.digest(),
            },
        )
        service_health = ControlRecord.build(
            kind="service_health_observation",
            record_id="service-health-observation:w5",
            payload={
                "authorization_digest": service_observation_authorization.digest(),
                "backend_provenance_digest": backend_provenance.digest(),
                "generation_digest": candidate.digest(),
                "observation_id": "w5-service-health",
                "observed_at": "2026-08-12T09:11:02Z",
                "observer_identity_digest": actor.digest(),
                "process_epoch": process_epoch,
                "service_protected_state_digest": service_state.digest(),
                "status": "ready",
                "target_digest": service_operation.target_record.digest(),
            },
        )
        readiness = ControlRecord.build(
            kind="readiness",
            record_id="readiness:w5",
            payload={
                "backend_provenance_digest": backend_provenance.digest(),
                "generation_digest": candidate.digest(),
                "backend_manifest_digest": backend_provenance.payload[
                    "backend_manifest_digest"
                ],
                "observed_at": "2026-08-12T09:11:03Z",
                "process_epoch": process_epoch,
                "service_health_observation_digests": [service_health.digest()],
                "service_protected_state_digest": service_state.digest(),
                "status": "ready",
                "target_digest": service_operation.target_record.digest(),
            },
        )
        observation_records_tuple = (
            backend_provenance,
            service_health,
            readiness,
        )

    operation_by_digest = {
        item.operation_digest: item for item in operations_tuple
    }
    gate_occurrence_records = {
        intent.digest(): intent,
        **(
            {final_restart_intent.digest(): final_restart_intent}
            if final_restart_intent is not None
            else {}
        ),
    }
    operation_realizations: list[OperationRealization] = []
    for operation_obligation in operation_obligations_tuple:
        operation = operation_by_digest[operation_obligation.operation_digest]
        requirement_payload = (
            operation_obligation.requirement.requirement_record.payload
        )
        subject_role = requirement_payload["subject_binding_role"]
        resolved_subject_record = {
            "candidate_generation": candidate,
            "captured_baseline": captured_checkpoint.generation_record,
            "gate_occurrence": gate_occurrence_records.get(
                operation.operation_record.payload["subject_digest"]
            ),
        }.get(subject_role)
        generation_role = requirement_payload["generation_binding_role"]
        resolved_generation_record = {
            "candidate_generation": candidate,
            "captured_baseline_generation": captured_checkpoint.generation_record,
            "predecessor_generation": predecessor_checkpoint.generation_record,
            "b0_capture_sentinel": captured_checkpoint.generation_record,
        }.get(generation_role)
        operation_realizations.append(
            _operation_realization(
                operation,
                operation_obligation,
                realization_id=operation_obligation.obligation_record.payload[
                    "obligation_id"
                ],
                resolved_subject_record=resolved_subject_record,
                resolved_generation_record=resolved_generation_record,
            )
        )
    operation_realizations_tuple = tuple(operation_realizations)
    operation_realization_set = ControlRecord.build(
        kind="operation_realization_set",
        record_id="operation-realization-set:w0",
        payload={
            "operation_obligation_set_digest": operation_obligation_set.digest(),
            "operation_realization_digests": [
                item.realization_digest for item in operation_realizations_tuple
            ],
        },
    )

    baseline_restoration_receipt = None
    if phase is PromotionPhase.ACTIVE:
        baseline_restoration_receipt = (
            predecessor_checkpoint.baseline_restoration_receipt
        )
        assert isinstance(
            baseline_restoration_receipt,
            BaselineRestorationReceipt,
        )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:w0",
        payload={
            "contract_id": "w0-contract",
            "expected_accepted_generation_digest": accepted.digest(),
            "expected_active_generation_digest": active.digest(),
            "generation_digest": candidate.digest(),
            "obligation_digests": [
                item.obligation_digest for item in promotion_obligations
            ],
            "operation_obligation_set_digest": operation_obligation_set.digest(),
            "operation_realization_set_digest": operation_realization_set.digest(),
            "predecessor_checkpoint_digest": (
                predecessor_checkpoint.checkpoint_digest
            ),
            "phase": phase.value,
            **(
                {
                    "acceptance_authorization_digest": (
                        acceptance_authorization.digest()
                    )
                }
                if phase is PromotionPhase.ACCEPTED
                else {
                    "phase_establishing_operation_obligation_digest": (
                        phase_establishing_obligation.obligation_digest
                    )
                }
            ),
            **(
                {
                    "baseline_restoration_receipt_digest": (
                        baseline_restoration_receipt.receipt_digest
                    )
                }
                if baseline_restoration_receipt is not None
                else {}
            ),
            **(
                {
                    "predecessor_service_anchor_receipt_digest": (
                        predecessor_service_receipt.receipt_digest
                    )
                }
                if isinstance(predecessor_service_receipt, ServiceAnchorReceipt)
                else {}
            ),
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
        operation_requirement_set_record=operation_requirement_set,
        operation_obligation_set_record=operation_obligation_set,
        operation_realization_set_record=operation_realization_set,
        validation_contract_record=validation_contract,
        generation_record=candidate,
        target_record=target,
        target_protected_state_record=target_state,
        contract_record=contract_record,
        obligations=promotion_obligations,
        operation_requirements=tuple(operation_requirements),
        operation_obligations=operation_obligations_tuple,
        operation_realizations=operation_realizations_tuple,
        assignment_records=assignment_records,
        predecessor_checkpoint=predecessor_checkpoint,
        acceptance_authorization_record=acceptance_authorization,
        acceptance_separation_policy_record=acceptance_separation,
        acceptance_actor_identity_record=acceptance_actor,
        baseline_restoration_receipt=baseline_restoration_receipt,
        service_anchor_receipt=predecessor_service_receipt,
    )
    if phase is PromotionPhase.ACCEPTED:
        service_restart_operation = next(
            (
                operation_by_digest[obligation.operation_digest]
                for obligation in operation_obligations_tuple
                if obligation.requirement.requirement_record.payload["purpose"]
                == "service_restart"
            ),
            None,
        )
        final_operation = next(
            operation_by_digest[obligation.operation_digest]
            for obligation in operation_obligations_tuple
            if obligation.requirement.requirement_record.payload["purpose"]
            == "final_service_restart"
        )
        renewal_records: tuple[ControlRecord, ...] = ()
        if service_restart_operation is not None:
            _, renewed_backend, renewed_health, renewed_readiness = (
                _service_observation_records(
                    contract,
                    bound,
                    service_restart_operation,
                    record_suffix="w6-renewal-1",
                    backend_observed_at="2026-08-12T09:14:00.1Z",
                    health_observed_at="2026-08-12T09:14:01Z",
                    readiness_observed_at="2026-08-12T09:14:01Z",
                )
            )
            renewal_records = (
                renewed_backend,
                renewed_health,
                renewed_readiness,
            )
        mid_attempt_renewal_records: tuple[ControlRecord, ...] = ()
        if mid_attempt_renewal_times is not None:
            _, mid_backend, mid_health, mid_readiness = (
                _service_observation_records(
                    contract,
                    bound,
                    final_operation,
                    record_suffix="w6-mid-attempt-renewal",
                    backend_observed_at=mid_attempt_renewal_times[0],
                    health_observed_at=mid_attempt_renewal_times[1],
                    readiness_observed_at=mid_attempt_renewal_times[2],
                    state_record=(
                        final_operation.expected_protected_state_record
                    ),
                )
            )
            mid_attempt_renewal_records = (
                mid_backend,
                mid_health,
                mid_readiness,
            )
        _, backend_provenance, service_health, readiness = (
            _service_observation_records(
                contract,
                bound,
                final_operation,
                record_suffix="w6-final",
                backend_observed_at=final_service_observation_times[0],
                health_observed_at=final_service_observation_times[1],
                readiness_observed_at=final_service_observation_times[2],
            )
        )
        observation_records_tuple = (
            *renewal_records,
            *mid_attempt_renewal_records,
            backend_provenance,
            service_health,
            readiness,
        )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:w0",
        payload={
            "accepted_generation_digest": accepted.digest(),
            "active_generation_digest": active.digest(),
            "attempt_digests": [item.attempt_digest for item in registered_attempts],
            "capability_digests": [
                item.capability_digest for item in operations_tuple
            ],
            "authority_head_digest": digest("9"),
            "authority_manifest_digest": digest("a"),
            "complete_through_sequence": complete_through_sequence,
            "completeness_proof_digest": digest("b"),
            "contract_digest": contract_record.digest(),
            "currency_proof_digests": [
                item.currency_proof_record.digest() for item in bound_evaluations
            ],
            "evaluation_digests": [
                item.evaluation_record_digest for item in bound_evaluations
            ],
            "fork_proof_digest": digest("c"),
            "generation_digest": candidate.digest(),
            "inclusion_edge_digests": (
                [edge.digest() for edge in inclusion_edge_records_tuple]
            ),
            "journal_head_digest": digest("d"),
            "operation_digests": [
                item.operation_digest for item in operations_tuple
            ],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations_tuple
            ],
            "observation_digests": [
                item.digest() for item in observation_records_tuple
            ],
            "observed_at": phase_times["trusted_time"],
            "phase": phase.value,
            "registration_set_digest": registration_set_digest(
                registered_attempts, operations_tuple
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
        attempts=registered_attempts,
        evaluations=bound_evaluations,
        inclusion_edge_records=inclusion_edge_records_tuple,
        operations=operations_tuple,
        validator_attestation_records=tuple(
            attestation_record
            for operation in operations_tuple
            for attestation_record in operation.validator_attestation_records
        ),
        observation_records=observation_records_tuple,
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
    assert assessment.obligation_evaluation_digests == tuple(
        item.evaluation_record_digest for item in fixture.cut.evaluations
    )


@pytest.mark.parametrize(
    "observation_kind",
    ("backend_provenance", "service_health_observation", "readiness"),
)
def test_atomic_cut_observation_may_coincide_with_its_cut(
    observation_kind,
):
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    source = next(
        record
        for record in _fixture(
            phase=PromotionPhase.ACCEPTED,
        ).cut.observation_records
        if record.kind == observation_kind
    )
    observation = ControlRecord.build(
        kind=source.kind,
        record_id=f"{source.record_id}:cut-boundary",
        payload={
            **_payload(source),
            "observed_at": fixture.cut.cut_record.payload["observed_at"],
        },
    )

    cut = _cut_with_observations(
        fixture.cut,
        (observation,),
        record_suffix=f"{observation_kind}-at-cut-boundary",
    )

    assert cut.observation_records == (observation,)


@pytest.mark.parametrize(
    "observation_kind",
    ("backend_provenance", "service_health_observation", "readiness"),
)
def test_atomic_cut_rejects_an_observation_after_its_cut(
    observation_kind,
):
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    source = next(
        record
        for record in _fixture(
            phase=PromotionPhase.ACCEPTED,
        ).cut.observation_records
        if record.kind == observation_kind
    )
    future_observation = ControlRecord.build(
        kind=source.kind,
        record_id=f"{source.record_id}:after-cut",
        payload={
            **_payload(source),
            "observed_at": "2026-08-12T07:11:11Z",
        },
    )

    with pytest.raises(
        ValueError,
        match="atomic cut observation cannot precede its evidence",
    ):
        _cut_with_observations(
            fixture.cut,
            (future_observation,),
            record_suffix=f"{observation_kind}-after-cut",
        )


def test_gate_attempt_over_its_contract_budget_fails_closed():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        max_live_attempt_seconds=3600,
        gate_terminal_completed_at="2026-08-12T07:40:01Z",
        phase_time_changes={
            "operation_registered": "2026-08-12T07:40:02Z",
            "capability_issued": "2026-08-12T07:40:03Z",
            "operation_observed": "2026-08-12T07:40:05Z",
            "operation_terminal": "2026-08-12T07:40:05Z",
            "currency_checkpoint": "2026-08-12T07:40:06Z",
            "trusted_time": "2026-08-12T07:40:07Z",
            "capability_expires": "2026-08-12T07:41:00Z",
        },
    )

    with pytest.raises(PromotionDenied, match="attempt time budget") as exc_info:
        assess_promotion_cut(fixture.contract, fixture.cut)

    assert exc_info.value.code == "PROMOTION_ATTEMPT_DID_NOT_PASS"


def test_critical_operation_over_its_contract_budget_fails_closed():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        max_live_attempt_seconds=3600,
        phase_time_changes={
            "operation_observed": "2026-08-12T08:10:31Z",
            "operation_terminal": "2026-08-12T08:10:31Z",
            "currency_checkpoint": "2026-08-12T08:10:35Z",
            "trusted_time": "2026-08-12T08:10:40Z",
            "capability_expires": "2026-08-12T08:11:00Z",
        },
    )

    with pytest.raises(PromotionDenied, match="attempt time budget") as exc_info:
        assess_promotion_cut(fixture.contract, fixture.cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_DID_NOT_PASS"


@pytest.mark.parametrize(
    ("phase", "cut_observed_at"),
    [
        (PromotionPhase.PREVALIDATED, "2026-08-12T15:30:01Z"),
        (PromotionPhase.ACCEPTED, "2026-08-12T17:13:11Z"),
    ],
)
def test_terminal_lifecycle_suite_over_eight_hours_fails_closed(
    phase,
    cut_observed_at,
):
    fixture = _fixture(
        phase=phase,
        max_suite_seconds=28800,
        evidence_max_age_seconds=36000,
        phase_time_changes={
            "currency_checkpoint": cut_observed_at,
            "trusted_time": cut_observed_at,
        },
    )

    with pytest.raises(PromotionDenied, match="suite time budget") as exc_info:
        assess_promotion_cut(fixture.contract, fixture.cut)

    assert exc_info.value.code == "PROMOTION_EVIDENCE_NOT_CURRENT"


def test_bound_unknown_evaluation_preserves_its_exact_attestation_provenance():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    original_attestation = fixture.bound.evidence_records[0]
    unknown_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:reported-unknown",
        payload={
            **_payload(original_attestation),
            "outcome": "unknown",
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:reported-unknown",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [unknown_attestation.digest()],
            "outcome": "unknown",
            "unknown_reason": "reported_unknown",
        },
    )

    bound = _bound_with_evaluation(
        fixture.bound,
        evaluation,
        (unknown_attestation,),
    )

    assert bound.evaluation_record.payload["unknown_reason"] == "reported_unknown"
    assert bound.evidence_records[0].digest() == unknown_attestation.digest()
    assert bound.structural_admissibility is False


def test_bound_unknown_evaluation_preserves_missing_evidence_reason():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:missing-attestation",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "unknown_reason": "missing_attestation",
        },
    )

    bound = _bound_with_evaluation(fixture.bound, evaluation, ())

    assert bound.evaluation_record.payload["unknown_reason"] == "missing_attestation"
    assert bound.evidence_records == ()
    assert bound.structural_admissibility is False


def test_bound_conditional_unknown_preserves_its_true_applicability_proof():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        conditional_applicable=True,
    )
    proof, original_attestation = fixture.bound.evidence_records
    missing_attestation_evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:conditional-missing-attestation",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "unknown_reason": "missing_attestation",
        },
    )
    missing_attestation = _bound_with_evaluation(
        fixture.bound,
        missing_attestation_evaluation,
        (proof,),
    )

    unknown_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:conditional-reported-unknown",
        payload={
            **_payload(original_attestation),
            "outcome": "unknown",
        },
    )
    reported_unknown_evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:conditional-reported-unknown",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [unknown_attestation.digest()],
            "outcome": "unknown",
            "unknown_reason": "reported_unknown",
        },
    )
    reported_unknown = _bound_with_evaluation(
        fixture.bound,
        reported_unknown_evaluation,
        (proof, unknown_attestation),
    )

    assert missing_attestation.evidence_records == (proof,)
    assert reported_unknown.evidence_records == (proof, unknown_attestation)
    assert missing_attestation.structural_admissibility is False
    assert reported_unknown.structural_admissibility is False


def test_bound_conditional_unknown_rejects_a_false_applicability_proof():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        conditional_applicable=True,
    )
    original_proof = fixture.bound.evidence_records[0]
    false_proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="predicate-proof:false-before-missing-attestation",
        payload={
            **_payload(original_proof),
            "is_applicable": False,
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:false-before-missing-attestation",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "predicate_proof_digest": false_proof.digest(),
            "unknown_reason": "missing_attestation",
        },
    )

    with pytest.raises(ValueError, match="must prove true"):
        _bound_with_evaluation(fixture.bound, evaluation, (false_proof,))


def test_bound_conditional_post_proof_unknown_rejects_omitted_proof():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        conditional_applicable=True,
    )
    original_attestation = fixture.bound.evidence_records[1]
    unknown_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:conditional-omitted-proof",
        payload={
            **_payload(original_attestation),
            "outcome": "unknown",
        },
    )

    for suffix, reason, attestations in (
        ("missing-attestation", "missing_attestation", ()),
        ("reported-unknown", "reported_unknown", (unknown_attestation,)),
    ):
        payload = {
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [
                attestation.digest() for attestation in attestations
            ],
            "outcome": "unknown",
            "unknown_reason": reason,
        }
        payload.pop("predicate_proof_digest")
        evaluation = ControlRecord.build(
            kind="evaluation",
            record_id=f"evaluation:conditional-omitted-proof:{suffix}",
            payload=payload,
        )

        with pytest.raises(ValueError, match="exact predicate-proof provenance"):
            _bound_with_evaluation(fixture.bound, evaluation, attestations)


def test_bound_unknown_evaluation_preserves_mismatched_predicate_proof():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
        conditional_applicable=True,
    )
    original_proof = next(
        record
        for record in fixture.bound.evidence_records
        if record.kind == "predicate_proof"
    )
    mismatched_proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="predicate-proof:mismatched",
        payload={
            **_payload(original_proof),
            "predicate_digest": digest("f"),
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:predicate-mismatch",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "predicate_proof_digest": mismatched_proof.digest(),
            "unknown_reason": "applicability_proof_mismatch",
        },
    )

    bound = _bound_with_evaluation(
        fixture.bound,
        evaluation,
        (mismatched_proof,),
    )

    assert bound.evidence_records[0].digest() == mismatched_proof.digest()
    assert bound.structural_admissibility is False


def test_bound_unknown_evaluation_rejects_substituted_reason_provenance():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    original_attestation = fixture.bound.evidence_records[0]
    mismatched_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:assignment-mismatch-labelled-reported",
        payload={
            **_payload(original_attestation),
            "assignment_digest": digest("f"),
            "outcome": "unknown",
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:substituted-unknown-reason",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [mismatched_attestation.digest()],
            "outcome": "unknown",
            "unknown_reason": "reported_unknown",
        },
    )

    with pytest.raises(ValueError, match="does not match its exact attestation"):
        _bound_with_evaluation(
            fixture.bound,
            evaluation,
            (mismatched_attestation,),
        )


def test_promotion_contract_requires_canonical_assignment_and_operation_sets():
    fixture = _fixture()

    assert fixture.validation_contract.payload["assignments_digest"] != digest("b")
    assert "operation_obligation_set_digest" in fixture.contract.contract_record.payload


def test_promotion_contract_rejects_a_substituted_exact_operation_set_digest():
    fixture = _fixture()
    record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:substituted-operation-set",
        payload={
            **_payload(fixture.contract.contract_record),
            "operation_obligation_set_digest": digest("e"),
        },
    )

    with pytest.raises(ValueError, match="operation_obligation_set_digest"):
        replace(fixture.contract, contract_record=record)


def test_promotion_rejects_an_obligation_relabelled_from_blocking_to_advisory():
    fixture = _fixture(scenario_gate=False)
    advisory_obligation_record = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion-obligation:control-plane:advisory-substitution",
        payload={
            **_payload(fixture.obligation.obligation_record),
            "impact": "advisory",
        },
    )
    advisory_obligation = PromotionObligation(advisory_obligation_record)
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:w0:advisory-substitution",
        payload={
            **_payload(fixture.contract.contract_record),
            "obligation_digests": [
                advisory_obligation.obligation_digest,
                *(item.obligation_digest for item in fixture.contract.obligations[1:]),
            ],
        },
    )
    contract = replace(
        fixture.contract,
        contract_record=contract_record,
        obligations=(advisory_obligation, *fixture.contract.obligations[1:]),
    )
    attempt = replace(
        fixture.attempt,
        obligation_record=advisory_obligation_record,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:w0:advisory-substitution",
        payload={
            **_payload(fixture.cut.cut_record),
            "contract_digest": contract.contract_digest,
            "registration_set_digest": registration_set_digest(
                (attempt, *fixture.cut.attempts[1:]),
                fixture.cut.operations,
            ),
        },
    )
    cut = replace(
        fixture.cut,
        cut_record=cut_record,
        attempts=(attempt, *fixture.cut.attempts[1:]),
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(contract, cut)

    assert exc_info.value.code == "PROMOTION_EVIDENCE_BINDING_MISMATCH"


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
            "obligation_digests": [
                unlinked_obligation.obligation_digest,
                *(item.obligation_digest for item in fixture.contract.obligations[1:]),
            ],
        },
    )

    with pytest.raises(ValueError, match="explicit scenario-gate link"):
        replace(
            fixture.contract,
            contract_record=unlinked_contract_record,
            obligations=(unlinked_obligation, *fixture.contract.obligations[1:]),
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
            "capability_digests": [],
            "operation_digests": [],
            "operation_terminal_digests": [],
            "registration_set_digest": registration_set_digest(
                fixture.cut.attempts,
                (),
            ),
        },
    )
    incomplete_cut = replace(
        fixture.cut,
        cut_record=incomplete_cut_record,
        operations=(),
        validator_attestation_records=(),
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
    assert cut.cut_record.payload["operation_digests"][0] == (
        operation.operation_digest
    )
    assert cut.cut_record.payload["operation_terminal_digests"][0] == (
        operation.terminal_digest
    )


@pytest.mark.parametrize(
    ("registered_at", "issued_at", "completed_at"),
    [
        (
            "2026-08-12T09:40:01Z",
            "2026-08-12T09:40:02Z",
            "2026-08-12T10:11:00Z",
        ),
        (
            "2026-08-12T09:35:00Z",
            "2026-08-12T09:36:00Z",
            "2026-08-12T10:09:59Z",
        ),
    ],
)
def test_scenario_operation_must_frame_its_gate_attempt_and_terminal(
    registered_at,
    issued_at,
    completed_at,
):
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    original = fixture.cut.operations[0]
    intended_state = original.intended_protected_state_record
    with pytest.raises(ValueError, match="live fenced capability"):
        _build_registered_operation(
            subject_digest=original.operation_record.payload["subject_digest"],
            context_digest=fixture.bound.context_record.digest(),
            candidate_generation=fixture.candidate_generation,
            target_state=intended_state,
            target_record=original.target_record,
            expected_state_record=original.expected_protected_state_record,
            bind_intended_state=True,
            operation_id=original.operation_record.payload["operation_id"],
            operation_kind="blocking_scenario",
            lifecycle_phase=PromotionPhase.ACTIVE.value,
            target_kind="service",
            target_id=original.target_record.payload["identity_id"],
            intent_sequence=2,
            terminal_sequence=5,
            registered_at=registered_at,
            issued_at=issued_at,
            attested_at=completed_at,
            completed_at=completed_at,
            expires_at="2026-08-12T10:12:00Z",
        )


@pytest.mark.parametrize(
    ("issued_at", "completed_at"),
    [
        ("2026-08-12T09:13:30Z", "2026-08-12T09:14:00Z"),
        ("2026-08-12T09:13:21Z", "2026-08-12T09:13:45Z"),
    ],
)
def test_scenario_capability_and_terminal_strictly_frame_gate_work(
    issued_at,
    completed_at,
):
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    original = fixture.cut.operations[0]
    intended_state = original.intended_protected_state_record
    if completed_at < intended_state.payload["observed_at"]:
        with pytest.raises(ValueError, match="live fenced capability"):
            _build_registered_operation(
                subject_digest=original.operation_record.payload["subject_digest"],
                context_digest=fixture.bound.context_record.digest(),
                candidate_generation=fixture.candidate_generation,
                target_state=intended_state,
                target_record=original.target_record,
                expected_state_record=original.expected_protected_state_record,
                bind_intended_state=True,
                operation_id=original.operation_record.payload["operation_id"],
                operation_kind="blocking_scenario",
                lifecycle_phase=PromotionPhase.ACTIVE.value,
                target_kind="service",
                target_id=original.target_record.payload["identity_id"],
                intent_sequence=2,
                terminal_sequence=5,
                registered_at="2026-08-12T09:13:20Z",
                issued_at=issued_at,
                attested_at=completed_at,
                completed_at=completed_at,
                expires_at="2026-08-12T09:15:00Z",
            )
        return
    replacement = _build_registered_operation(
        subject_digest=original.operation_record.payload["subject_digest"],
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=intended_state,
        target_record=original.target_record,
        expected_state_record=original.expected_protected_state_record,
        bind_intended_state=True,
        operation_id=original.operation_record.payload["operation_id"],
        operation_kind="blocking_scenario",
        lifecycle_phase=PromotionPhase.ACTIVE.value,
        target_kind="service",
        target_id=original.target_record.payload["identity_id"],
        intent_sequence=2,
        terminal_sequence=5,
        registered_at="2026-08-12T09:13:20Z",
        issued_at=issued_at,
        attested_at=completed_at,
        completed_at=completed_at,
        expires_at="2026-08-12T09:15:00Z",
    )
    contract, cut = _replace_exact_contract_operation(
        fixture,
        original,
        replacement,
    )

    with pytest.raises(PromotionDenied, match="fenced before gate work"):
        assess_promotion_cut(contract, cut)


def test_scenario_with_missing_evidence_denies_with_a_stable_promotion_code() -> None:
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:scenario-missing-evidence",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "unknown_reason": "missing_attestation",
        },
    )
    bound = _bound_with_evaluation(fixture.bound, evaluation, ())
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:scenario-missing-evidence",
        payload={
            **_payload(fixture.attempt.terminal_record),
            "outcome": "unknown",
            "validator_attestation_digests": [],
        },
    )
    attempt = replace(fixture.attempt, terminal_record=terminal)
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:scenario-missing-evidence",
        payload={
            **_payload(fixture.cut.cut_record),
            "attempt_digests": [attempt.attempt_digest],
            "currency_proof_digests": [bound.currency_proof_record.digest()],
            "evaluation_digests": [bound.evaluation_record_digest],
            "registration_set_digest": registration_set_digest(
                (attempt,), fixture.cut.operations
            ),
        },
    )
    cut = replace(
        fixture.cut,
        cut_record=cut_record,
        attempts=(attempt,),
        evaluations=(bound,),
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_EVIDENCE_NOT_CURRENT"


def test_atomic_cut_carries_the_exact_operation_validator_attestations():
    fixture = _fixture()
    assert fixture.cut.validator_attestation_records == tuple(
        attestation
        for operation in fixture.cut.operations
        for attestation in operation.validator_attestation_records
    )


def test_registered_operation_rejects_an_unresolved_terminal_attestation_digest():
    operation = _fixture().cut.operations[0]
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:blocking-scenario:unresolved-attestation",
        payload={
            **_payload(operation.terminal_record),
            "validator_attestation_digests": [digest("f")],
        },
    )

    with pytest.raises(ValueError, match="exact operation validator attestations"):
        replace(operation, terminal_record=terminal)


def test_registered_operation_rejects_missing_terminal_attestation_material():
    operation = _fixture().cut.operations[0]

    with pytest.raises(ValueError, match="exact operation validator attestations"):
        replace(operation, validator_attestation_records=())


def test_registered_operation_rejects_an_attestation_from_another_operation():
    fixture = _fixture()
    operation = fixture.cut.operations[0]
    other = _build_registered_operation(
        subject_digest=operation.operation_record.payload["subject_digest"],
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        operation_id="blocking-scenario-other",
        intent_sequence=6,
        terminal_sequence=7,
    )

    with pytest.raises(ValueError, match="critical operation"):
        _replace_operation_validator_attestations(
            operation,
            other.validator_attestation_records,
            record_suffix="blocking-scenario:substituted-attestation",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("operation_digest", digest("a"), "critical operation"),
        ("subject_digest", digest("b"), "operation subject"),
        ("validator_digest", digest("c"), "terminal validator"),
        ("outcome", "failed", "terminal outcome"),
        ("poststate_digest", digest("d"), "terminal poststate"),
    ],
)
def test_operation_validator_attestation_binds_every_terminal_coordinate(
    field,
    value,
    message,
):
    operation = _fixture().cut.operations[0]
    changed_attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id=f"operation-attestation:changed:{field}",
        payload={
            **_payload(operation.validator_attestation_records[0]),
            field: value,
        },
    )

    with pytest.raises(ValueError, match=message):
        _replace_operation_validator_attestations(
            operation,
            (changed_attestation,),
            record_suffix=f"blocking-scenario:changed-attestation:{field}",
        )


def test_successful_operation_attestation_may_coincide_with_intended_observation():
    operation = _fixture().cut.operations[0]
    boundary_attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id="operation-attestation:at-intended-observation",
        payload={
            **_payload(operation.validator_attestation_records[0]),
            "observed_at": operation.intended_protected_state_record.payload[
                "observed_at"
            ],
        },
    )

    rebound = _replace_operation_validator_attestations(
        operation,
        (boundary_attestation,),
        record_suffix="blocking-scenario:attestation-at-intended-observation",
    )

    assert rebound.validator_attestation_records == (boundary_attestation,)


def test_successful_operation_attestation_cannot_precede_intended_observation():
    operation = _fixture().cut.operations[0]
    early_attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id="operation-attestation:before-intended-observation",
        payload={
            **_payload(operation.validator_attestation_records[0]),
            "observed_at": "2026-08-12T09:13:59Z",
        },
    )

    with pytest.raises(
        ValueError,
        match="intended protected state and terminal",
    ):
        _replace_operation_validator_attestations(
            operation,
            (early_attestation,),
            record_suffix="blocking-scenario:attestation-before-intended-observation",
        )


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-08-12T09:34:59Z",
        "2026-08-12T10:11:01Z",
    ],
)
def test_operation_validator_attestation_must_be_observed_during_the_operation(
    observed_at,
):
    operation = _fixture().cut.operations[0]
    changed_attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id="operation-attestation:outside-operation",
        payload={
            **_payload(operation.validator_attestation_records[0]),
            "observed_at": observed_at,
        },
    )

    with pytest.raises(ValueError, match="validator attestation observation"):
        _replace_operation_validator_attestations(
            operation,
            (changed_attestation,),
            record_suffix="blocking-scenario:attestation-outside-operation",
        )


def test_atomic_cut_rejects_missing_operation_validator_attestation_material():
    cut = _fixture().cut

    with pytest.raises(ValueError, match="exact operation validator attestations"):
        replace(cut, validator_attestation_records=())


def test_atomic_cut_rejects_extra_operation_validator_attestation_material():
    fixture = _fixture()
    other = _build_registered_operation(
        subject_digest=fixture.attempt.intent_record.digest(),
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        operation_id="blocking-scenario-extra-attestation",
        intent_sequence=6,
        terminal_sequence=7,
    )

    with pytest.raises(ValueError, match="exact operation validator attestations"):
        replace(
            fixture.cut,
            validator_attestation_records=(
                *fixture.cut.validator_attestation_records,
                *other.validator_attestation_records,
            ),
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
    changed_operation = _rebind_registered_operation(
        operation,
        record_suffix="blocking-scenario:foreign-authority",
        operation_record=changed_operation_record,
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
    with pytest.raises((ValueError, PromotionDenied)):
        changed_operation = _rebind_registered_operation(
            operation,
            record_suffix=f"blocking-scenario:changed:{len(changes)}",
            operation_record=changed_operation_record,
        )
        cut = _cut_with_operation(fixture, changed_operation)
        assess_promotion_cut(fixture.contract, cut)


def test_critical_operation_cannot_change_declared_effects_behind_an_exact_obligation():
    fixture = _fixture()
    operation = fixture.cut.operations[0]
    changed_operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:blocking-scenario:changed-effects",
        payload={
            **_payload(operation.operation_record),
            "declared_effects": [
                {
                    "classification": "poststate_observable",
                    "effect_id": "different-result",
                    "projection_digest": digest("f"),
                }
            ],
        },
    )
    changed_operation = _rebind_registered_operation(
        operation,
        record_suffix="blocking-scenario:changed-effects",
        operation_record=changed_operation_record,
    )
    cut = _cut_with_operation(fixture, changed_operation)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_operation_terminal_rejects_a_substituted_capability_record():
    operation = _fixture().cut.operations[0]
    substituted_capability = ControlRecord.build(
        kind="capability",
        record_id="capability:substituted-authorizer",
        payload={
            **_payload(operation.capability_record),
            "authorizer_digest": digest("f"),
        },
    )

    with pytest.raises(ValueError, match="fenced capability"):
        replace(operation, capability_record=substituted_capability)


def test_registered_operation_rejects_a_deceptive_control_record_subclass():
    operation = _fixture().cut.operations[0]

    with pytest.raises(TypeError, match="exact ControlRecord"):
        replace(
            operation,
            operation_record=_deceptive_operation_record(
                operation.operation_record
            ),
        )


def test_registered_operation_rejects_a_wrong_expected_state_target_kind() -> None:
    operation = _fixture().cut.operations[0]
    wrong_target_kind = (
        "service"
        if operation.operation_record.payload["target_kind"] == "live_root"
        else "live_root"
    )
    wrong_expected_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:wrong-expected-target-kind",
        payload={
            **_payload(operation.expected_protected_state_record),
            "target_kind": wrong_target_kind,
        },
    )
    changed_operation = ControlRecord.build(
        kind="operation",
        record_id="operation:wrong-expected-target-kind",
        payload={
            **_payload(operation.operation_record),
            "expected_protected_state_digest": wrong_expected_state.digest(),
        },
    )

    with pytest.raises(ValueError, match="target kind"):
        _rebind_registered_operation(
            operation,
            record_suffix="wrong-expected-target-kind",
            operation_record=changed_operation,
            expected_protected_state_record=wrong_expected_state,
        )


def test_recovery_operation_binds_exact_failed_predecessor_owner_and_assessment():
    predecessor, recovery, obligation, owner = _recovery_operation_material()
    capability = recovery.capability_record.payload

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert capability["capability_type"] == "recovery"
    assert capability["predecessor_operation_id"] == (
        predecessor.operation_record.payload["operation_id"]
    )
    assert capability["predecessor_failure_record_digest"] == (
        predecessor.terminal_digest
    )
    assert predecessor.terminal_record.payload["operation_digest"] == (
        predecessor.operation_digest
    )
    assert capability["predecessor_fence_epoch"] == (
        predecessor.capability_record.payload["fence_epoch"]
    )
    assert predecessor.operation_record.payload["recovery_contract_digest"] == (
        capability["recovery_contract_digest"]
    )
    assert predecessor.operation_record.payload["recovery_target_digest"] == (
        recovery.intended_protected_state_record.digest()
    )
    assert capability["authorizer_digest"] == owner.digest()


def test_recovery_operation_can_realize_an_exact_cross_phase_target() -> None:
    predecessor, recovery, obligation, _ = _recovery_operation_material(
        predecessor_phase=PromotionPhase.ACTIVE.value,
        predecessor_target_kind="service",
        successor_phase=PromotionPhase.PREVALIDATED.value,
        successor_target_kind="service",
    )

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert predecessor.operation_record.payload["lifecycle_phase"] == "active"
    assert recovery.operation_record.payload["lifecycle_phase"] == "prevalidated"
    assert recovery.intended_protected_state_record.payload["lifecycle_phase"] == (
        "prevalidated"
    )
    assert predecessor.operation_record.payload["recovery_target_digest"] == (
        recovery.intended_protected_state_record.digest()
    )
    assert predecessor.terminal_record.payload["poststate_digest"] == (
        recovery.expected_protected_state_record.digest()
    )


def test_recovery_journal_order_allows_an_equal_timestamp_boundary() -> None:
    predecessor, recovery, obligation, _ = _recovery_operation_material(
        predecessor_completed_at="2026-08-12T10:00:10Z",
        successor_registered_at="2026-08-12T10:00:10Z",
    )

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert predecessor.terminal_sequence < (
        recovery.intent_record.payload["journal_sequence"]
    )
    assert predecessor.terminal_record.payload["completed_at"] == (
        recovery.intent_record.payload["registered_at"]
    )


def test_recovery_expected_snapshot_may_coincide_with_predecessor_terminal() -> None:
    predecessor, recovery, obligation, _ = _recovery_operation_material(
        recovery_expected_observed_at="2026-08-12T10:00:08Z",
    )

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert recovery.expected_protected_state_record.payload["observed_at"] == (
        predecessor.terminal_record.payload["completed_at"]
    )


@pytest.mark.parametrize(
    "observed_at",
    ("2026-08-12T10:00:08.000001Z", "2026-08-12T10:00:09Z"),
    ids=("fractional", "one-second"),
)
def test_recovery_rejects_expected_snapshot_observed_after_predecessor_terminal(
    observed_at: str,
) -> None:
    with pytest.raises(ValueError, match="expected snapshot observation"):
        _recovery_operation_material(
            recovery_expected_observed_at=observed_at,
        )


@pytest.mark.parametrize(
    ("predecessor_terminal_sequence", "successor_intent_sequence"),
    [(3, 3), (4, 3)],
    ids=("equal", "reversed"),
)
def test_recovery_rejects_nonincreasing_predecessor_journal_order(
    predecessor_terminal_sequence: int,
    successor_intent_sequence: int,
) -> None:
    with pytest.raises(ValueError, match="journal order"):
        _recovery_operation_material(
            predecessor_terminal_sequence=predecessor_terminal_sequence,
            successor_intent_sequence=successor_intent_sequence,
        )


def test_recovery_operation_phase_must_match_its_exact_target_state() -> None:
    with pytest.raises(ValueError, match="lifecycle phase"):
        _recovery_operation_material(
            predecessor_phase=PromotionPhase.ACTIVE.value,
            predecessor_target_kind="service",
            successor_phase=PromotionPhase.PREVALIDATED.value,
            successor_operation_phase=PromotionPhase.ACTIVE.value,
            successor_target_kind="service",
        )


def test_b0_recovery_retains_the_exact_capture_sentinel() -> None:
    predecessor, recovery, obligation = _b0_recovery_operation_material()

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert recovery.operation_record.payload["generation_binding"] == (
        predecessor.operation_record.payload["generation_binding"]
    )


def test_b0_recovery_can_advance_to_the_declared_destination_generation() -> None:
    predecessor, recovery, obligation = _b0_recovery_operation_material(
        successor_generation_seed="a",
    )

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    predecessor_binding = predecessor.operation_record.payload[
        "generation_binding"
    ]
    recovery_binding = recovery.operation_record.payload["generation_binding"]
    assert matched == (recovery.operation_digest,)
    assert recovery_binding["mode"] == predecessor_binding["mode"]
    assert recovery_binding["sentinel_digest"] == (
        predecessor_binding["sentinel_digest"]
    )
    assert recovery_binding["generation_digest"] != (
        predecessor_binding["generation_digest"]
    )
    assert recovery_binding["generation_digest"] == (
        recovery.intended_protected_state_record.payload["generation_digest"]
    )
    assert predecessor.operation_record.payload["recovery_target_digest"] == (
        recovery.intended_protected_state_record.digest()
    )


def test_b0_recovery_rejects_a_substituted_capture_sentinel() -> None:
    with pytest.raises(ValueError, match="capture sentinel"):
        _b0_recovery_operation_material(successor_sentinel_digest=digest("f"))


def test_b0_recovery_rejects_a_successor_without_capture_sentinel_mode() -> None:
    with pytest.raises(RecordValidationError, match="operation envelope coordinates"):
        _b0_recovery_operation_material(
            successor_binding_mode="required_generation",
        )


def test_b0_recovery_rejects_a_foreign_declared_destination() -> None:
    with pytest.raises(ValueError, match="predecessor recovery target"):
        _b0_recovery_operation_material(
            successor_generation_seed="a",
            predecessor_recovery_target_digest=digest("f"),
        )


def _validation_only_recovery(
    *,
    expected_state_changes: dict[str, object] | None = None,
    expected_process_epoch: str | None = None,
    intended_process_epoch: str | None = None,
    target_kind: str = "live_root",
) -> tuple[RegisteredOperation, RegisteredOperation]:
    predecessor, recovery, _, owner = _recovery_operation_material(
        predecessor_target_kind=target_kind,
        successor_target_kind=target_kind,
    )
    already_realized_payload = {
        **_payload(recovery.intended_protected_state_record),
        "fence_epoch": recovery.expected_protected_state_record.payload[
            "fence_epoch"
        ],
        "observed_at": predecessor.terminal_record.payload["completed_at"],
    }
    if expected_process_epoch is not None:
        already_realized_payload["process_epoch"] = expected_process_epoch
    already_realized_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:already-realized-recovery-target",
        payload=already_realized_payload,
    )
    validation_payload = {
        **_payload(already_realized_state),
        "fence_epoch": already_realized_state.payload["fence_epoch"] + 1,
        "observed_at": "2026-08-12T10:00:15Z",
    }
    if intended_process_epoch is None:
        validation_payload.pop("process_epoch", None)
    else:
        validation_payload["process_epoch"] = intended_process_epoch
    validation_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:validated-already-realized-recovery-target",
        payload=validation_payload,
    )
    if expected_state_changes:
        already_realized_state = ControlRecord.build(
            kind="protected_state",
            record_id="protected-state:substituted-already-realized-target",
            payload={
                **_payload(already_realized_state),
                **expected_state_changes,
            },
        )
    changed_predecessor = _build_registered_operation(
        subject_digest=predecessor.operation_record.payload["subject_digest"],
        subject_kind=predecessor.operation_record.payload["subject_kind"],
        context_digest=digest("e"),
        candidate_generation=recovery.intended_protected_state_record,
        target_state=predecessor.intended_protected_state_record,
        target_record=predecessor.target_record,
        bind_intended_state=True,
        operation_id="already-realized-recovery-predecessor",
        operation_kind=predecessor.operation_record.payload["operation_kind"],
        lifecycle_phase=predecessor.operation_record.payload["lifecycle_phase"],
        target_kind=predecessor.operation_record.payload["target_kind"],
        target_id=predecessor.operation_record.payload["target_id"],
        generation_binding=dict(predecessor.operation_record.payload["generation_binding"]),
        intent_sequence=1,
        terminal_sequence=2,
        outcome="failed",
        poststate_digest=already_realized_state.digest(),
        registered_at="2026-08-12T10:00:01Z",
        issued_at="2026-08-12T10:00:02Z",
        attested_at="2026-08-12T10:00:07Z",
        completed_at="2026-08-12T10:00:08Z",
        expires_at="2026-08-12T10:00:30Z",
        recovery_contract_digest=predecessor.operation_record.payload[
            "recovery_contract_digest"
        ],
        recovery_target_digest=validation_state.digest(),
    )
    validation_only = _build_registered_operation(
        subject_digest=changed_predecessor.operation_record.payload[
            "recovery_contract_digest"
        ],
        subject_kind="control_record",
        context_digest=digest("e"),
        candidate_generation=recovery.intended_protected_state_record,
        target_state=validation_state,
        target_record=recovery.target_record,
        expected_state_record=already_realized_state,
        bind_intended_state=True,
        operation_id="already-realized-recovery-validation",
        operation_kind="recovery",
        lifecycle_phase=recovery.operation_record.payload["lifecycle_phase"],
        target_kind=recovery.operation_record.payload["target_kind"],
        target_id=recovery.operation_record.payload["target_id"],
        generation_binding=dict(recovery.operation_record.payload["generation_binding"]),
        intent_sequence=3,
        terminal_sequence=4,
        registered_at="2026-08-12T10:00:10Z",
        issued_at="2026-08-12T10:00:11Z",
        attested_at="2026-08-12T10:00:15Z",
        completed_at="2026-08-12T10:00:16Z",
        expires_at="2026-08-12T10:00:30Z",
        recovery_contract_digest=digest("5"),
        recovery_target_digest=already_realized_state.digest(),
        recovery_predecessor_operation=changed_predecessor,
        recovery_owner_identity_record=owner,
    )
    return changed_predecessor, validation_only


def test_recovery_operation_can_validate_an_already_realized_exact_target() -> None:
    changed_predecessor, validation_only = _validation_only_recovery()

    assert validation_only.expected_protected_state_record.payload["state_digest"] == (
        validation_only.intended_protected_state_record.payload["state_digest"]
    )
    assert validation_only.intended_protected_state_record.digest() == (
        changed_predecessor.operation_record.payload["recovery_target_digest"]
    )
    assert validation_only.expected_protected_state_record.digest() == (
        changed_predecessor.terminal_record.payload["poststate_digest"]
    )


def test_validation_only_service_recovery_retains_one_exact_process_epoch() -> None:
    _, validation_only = _validation_only_recovery(
        expected_process_epoch="service-epoch-1",
        intended_process_epoch="service-epoch-1",
        target_kind="service",
    )
    obligation = _operation_obligation(
        validation_only,
        obligation_id="validation-only-service-recovery",
    )

    matched = assess_operation_obligations(
        (obligation,),
        (validation_only,),
        authority_head_digest=digest("9"),
    )

    assert matched == (validation_only.operation_digest,)
    assert validation_only.expected_protected_state_record.payload["process_epoch"] == (
        validation_only.intended_protected_state_record.payload["process_epoch"]
    )


def _authority_snapshot_from_protected_state(
    record: ControlRecord,
) -> ProtectedStateSnapshot:
    state = record.payload
    projection_digest = "sha256:" + hashlib.sha256(
        state["projection_id"].encode("utf-8")
    ).hexdigest()
    return ProtectedStateSnapshot(
        record_digest=record.digest(),
        generation_digest=state["generation_digest"],
        lifecycle_phase=LifecyclePhase(state["lifecycle_phase"]),
        projection_digest=projection_digest,
        state_digest=state["state_digest"],
        process_epoch=state.get("process_epoch"),
    )


def _authority_binding_from_registered_operation(
    operation: RegisteredOperation,
    *,
    recovery_target_record: ControlRecord,
) -> OperationBinding:
    payload = operation.operation_record.payload
    generation = payload["generation_binding"]
    expected = _authority_snapshot_from_protected_state(
        operation.expected_protected_state_record
    )
    intended = _authority_snapshot_from_protected_state(
        operation.intended_protected_state_record
    )
    recovery_target = _authority_snapshot_from_protected_state(
        recovery_target_record
    )
    assert expected.projection_digest == intended.projection_digest
    return OperationBinding(
        operation_id=payload["operation_id"],
        operation_kind=CriticalOperationKind(payload["operation_kind"]),
        generation_class=GenerationClass(payload["generation_class"]),
        lifecycle_phase=LifecyclePhase(payload["lifecycle_phase"]),
        intent_digest=operation.intent_record.digest(),
        plan_digest=payload["plan_digest"],
        authority_head_digest=payload["authority_head_digest"],
        subject=OperationSubject(
            kind=OperationSubjectKind(payload["subject_kind"]),
            record_digest=payload["subject_digest"],
        ),
        target=OperationTarget(
            kind=OperationTargetKind(payload["target_kind"]),
            target_id=payload["target_id"],
        ),
        expected_state=expected,
        intended_state=intended,
        generation=GenerationBinding(
            mode=GenerationBindingMode(generation["mode"]),
            generation_digest=generation.get("generation_digest"),
            sentinel_digest=generation.get("sentinel_digest"),
        ),
        effects=tuple(
            DeclaredEffect(
                effect_id=effect["effect_id"],
                classification=EffectClass(effect["classification"]),
                projection_digest=intended.projection_digest,
            )
            for effect in payload["declared_effects"]
        ),
        rollback=RollbackRecoveryContract(
            mode=RecoveryMode.RECOVERY_ONLY,
            recovery_plan_digest=payload["plan_digest"],
            recovery_owner_role="recovery-owner",
            recovery_contract_digest=payload["recovery_contract_digest"],
            recovery_target=recovery_target,
            recovery_destination_generation_digest=(
                recovery_target.generation_digest
            ),
            recovery_origin_generation_digest=generation["generation_digest"],
        ),
        terminal_validator_digest=payload["terminal_validator_digest"],
    )


def _terminal_observation_from_registered_operation(
    operation: RegisteredOperation,
    binding: OperationBinding,
    capability: FencedCapability,
    *,
    outcome: TerminalOutcome,
) -> TerminalObservation:
    return TerminalObservation(
        record_digest=operation.terminal_digest,
        operation_digest=binding.digest(),
        capability_digest=capability.capability_id,
        validator_digest=binding.terminal_validator_digest,
        observed_state=binding.intended_state,
        outcome=outcome,
        observed_effect_ids=frozenset(
            effect.effect_id
            for effect in binding.effects
            if effect.classification is EffectClass.POSTSTATE_OBSERVABLE
        ),
    )


def _materialize_redelivered_capability(
    operation: RegisteredOperation,
    capability: FencedCapability | RecoveryCapability,
) -> RegisteredOperation:
    fenced = capability.fenced if isinstance(capability, RecoveryCapability) else capability
    payload = operation.operation_record.payload
    intended = operation.intended_protected_state_record
    assert fenced.operation_id == payload["operation_id"]
    assert fenced.intent_digest == operation.intent_record.digest()
    assert fenced.plan_digest == payload["plan_digest"]
    assert fenced.authority_head_digest == payload["authority_head_digest"]
    assert fenced.subject_digest == payload["subject_digest"]
    assert fenced.target.kind.value == payload["target_kind"]
    assert fenced.target.target_id == payload["target_id"]
    assert fenced.intended_state.record_digest == intended.digest()
    assert fenced.fence_epoch == intended.payload["fence_epoch"]
    capability_payload = {
        **_payload(operation.capability_record),
        "authority_head_digest": fenced.authority_head_digest,
        "capability_id": fenced.capability_id,
        "fence_epoch": fenced.fence_epoch,
        "intended_protected_state_digest": fenced.intended_state.record_digest,
        "intent_digest": fenced.intent_digest,
        "operation_digest": operation.operation_digest,
        "operation_id": fenced.operation_id,
        "plan_digest": fenced.plan_digest,
        "single_use_scope_digest": operation.operation_digest,
        "subject_digest": fenced.subject_digest,
        "target_id": fenced.target.target_id,
        "target_kind": fenced.target.kind.value,
    }
    if isinstance(capability, RecoveryCapability):
        capability_payload.update(
            predecessor_failure_record_digest=(
                capability.predecessor_failure_record_digest
            ),
            predecessor_fence_epoch=capability.predecessor_fence_epoch,
            predecessor_operation_id=capability.predecessor_operation_id,
            recovery_contract_digest=capability.recovery_contract_digest,
            recovery_owner_role=capability.recovery_owner_role,
        )
    capability_record = ControlRecord.build(
        kind="capability",
        record_id=f"{operation.capability_record.record_id}:redelivered",
        payload=capability_payload,
    )
    terminal_record = ControlRecord.build(
        kind="terminal_record",
        record_id=f"{operation.terminal_record.record_id}:redelivered",
        payload={
            **_payload(operation.terminal_record),
            "capability_digest": capability_record.digest(),
        },
    )
    return RegisteredOperation(
        intent_record=operation.intent_record,
        operation_record=operation.operation_record,
        target_record=operation.target_record,
        expected_protected_state_record=operation.expected_protected_state_record,
        intended_protected_state_record=operation.intended_protected_state_record,
        capability_record=capability_record,
        terminal_record=terminal_record,
        validator_attestation_records=operation.validator_attestation_records,
        recovery_predecessor_operation=operation.recovery_predecessor_operation,
        recovery_owner_identity_record=operation.recovery_owner_identity_record,
    )


def test_forward_capability_redelivery_materializes_current_canonical_evidence() -> None:
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    operation = _operation_for_purpose(fixture, "phase_transition")
    assert operation.operation_record.payload["recovery_target_digest"] == (
        operation.expected_protected_state_record.digest()
    )
    binding = _authority_binding_from_registered_operation(
        operation,
        recovery_target_record=operation.expected_protected_state_record,
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    fence_epoch = operation.intended_protected_state_record.payload["fence_epoch"]
    issued = authority.acquire_capability(binding, fence_epoch=fence_epoch)
    journal_after_issue = authority.journal_entries

    redelivered = authority.acquire_capability(binding, fence_epoch=fence_epoch)

    assert redelivered == issued
    assert redelivered is not issued
    assert redelivered.fence_epoch == fence_epoch
    assert authority.journal_entries == journal_after_issue
    authority.guarded_compare_and_swap(
        binding,
        capability=redelivered,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        _terminal_observation_from_registered_operation(
            operation,
            binding,
            redelivered,
            outcome=TerminalOutcome.PASS,
        ),
    )
    materialized = _materialize_redelivered_capability(operation, redelivered)
    operations = tuple(
        materialized if item.operation_digest == operation.operation_digest else item
        for item in fixture.cut.operations
    )
    cut = _cut_with_operations(
        fixture.cut,
        operations,
        record_suffix="forward-redelivery",
    )

    assessment = assess_promotion_cut(fixture.contract, cut)

    assert assessment.phase is PromotionPhase.PUBLISHED
    assert materialized.capability_record.payload["capability_id"] == (
        redelivered.capability_id
    )
    assert materialized.capability_record.payload["fence_epoch"] == (
        materialized.intended_protected_state_record.payload["fence_epoch"]
    )


def test_recovery_capability_redelivery_materializes_current_canonical_evidence() -> None:
    predecessor, recovery, obligation, _ = _recovery_operation_material()
    failed_binding = _authority_binding_from_registered_operation(
        predecessor,
        recovery_target_record=recovery.intended_protected_state_record,
    )
    recovery_binding = _authority_binding_from_registered_operation(
        recovery,
        recovery_target_record=recovery.expected_protected_state_record,
    )
    authority = InMemoryAuthority(initial_active_state=failed_binding.expected_state)
    authority.append_intent(failed_binding)
    predecessor_fence = predecessor.intended_protected_state_record.payload[
        "fence_epoch"
    ]
    forward_capability = authority.acquire_capability(
        failed_binding,
        fence_epoch=predecessor_fence,
    )
    authority.guarded_compare_and_swap(
        failed_binding,
        capability=forward_capability,
        observed_state=failed_binding.expected_state,
    )
    failure = authority.terminalize_operation(
        failed_binding,
        _terminal_observation_from_registered_operation(
            predecessor,
            failed_binding,
            forward_capability,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    authority.append_intent(recovery_binding)
    recovery_fence = recovery.intended_protected_state_record.payload["fence_epoch"]
    issued = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=recovery_fence,
    )
    journal_after_issue = authority.journal_entries

    redelivered = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=recovery_fence,
    )

    assert redelivered == issued
    assert redelivered is not issued
    assert redelivered.fenced is not issued.fenced
    assert redelivered.predecessor_fence_epoch == predecessor_fence
    assert redelivered.fenced.fence_epoch == recovery_fence
    assert authority.journal_entries == journal_after_issue
    authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=redelivered,
        observed_state=recovery_binding.expected_state,
    )
    authority.terminalize_recovery(
        failed_binding,
        recovery_binding,
        _terminal_observation_from_registered_operation(
            recovery,
            recovery_binding,
            redelivered.fenced,
            outcome=TerminalOutcome.PASS,
        ),
    )
    materialized = _materialize_redelivered_capability(recovery, redelivered)

    matched = assess_operation_obligations(
        (obligation,),
        (materialized,),
        authority_head_digest=digest("9"),
    )

    assert matched == (materialized.operation_digest,)
    assert materialized.capability_record.payload["predecessor_fence_epoch"] == (
        predecessor.capability_record.payload["fence_epoch"]
    )
    assert materialized.expected_protected_state_record.payload["fence_epoch"] == (
        predecessor.capability_record.payload["fence_epoch"]
    )
    assert materialized.intended_protected_state_record.payload["fence_epoch"] == (
        materialized.expected_protected_state_record.payload["fence_epoch"] + 1
    )


def test_validation_only_recovery_bridges_distinct_authority_state_occurrences() -> None:
    _, validation_only = _validation_only_recovery(
        expected_process_epoch="service-epoch-1",
        intended_process_epoch="service-epoch-1",
        target_kind="service",
    )
    expected_record = validation_only.expected_protected_state_record
    intended_record = validation_only.intended_protected_state_record
    expected = expected_record.payload
    intended = intended_record.payload
    expected_snapshot = _authority_snapshot_from_protected_state(expected_record)
    intended_snapshot = _authority_snapshot_from_protected_state(intended_record)

    assert expected_record.digest() != intended_record.digest()
    assert intended["fence_epoch"] == expected["fence_epoch"] + 1
    assert (
        intended["generation_digest"],
        intended["lifecycle_phase"],
        intended["projection_id"],
        intended["state_digest"],
        intended["process_epoch"],
    ) == (
        expected["generation_digest"],
        expected["lifecycle_phase"],
        expected["projection_id"],
        expected["state_digest"],
        expected["process_epoch"],
    )
    assert expected_snapshot.record_digest != intended_snapshot.record_digest
    assert replace(
        expected_snapshot,
        record_digest=intended_snapshot.record_digest,
    ) == intended_snapshot


@pytest.mark.parametrize(
    ("expected_process_epoch", "intended_process_epoch"),
    [
        ("service-epoch-1", "service-epoch-2"),
        ("service-epoch-1", None),
        (None, "service-epoch-1"),
    ],
    ids=("changed", "removed", "added"),
)
def test_validation_only_service_recovery_rejects_a_process_epoch_change(
    expected_process_epoch,
    intended_process_epoch,
) -> None:
    with pytest.raises(ValueError, match="protected state"):
        _validation_only_recovery(
            expected_process_epoch=expected_process_epoch,
            intended_process_epoch=intended_process_epoch,
            target_kind="service",
        )


@pytest.mark.parametrize(
    "expected_state_changes",
    [
        {"generation_digest": digest("f")},
        {"lifecycle_phase": PromotionPhase.PUBLISHED.value},
    ],
)
def test_validation_only_recovery_rejects_a_substituted_snapshot_coordinate(
    expected_state_changes,
) -> None:
    with pytest.raises(ValueError, match="protected state"):
        _validation_only_recovery(expected_state_changes=expected_state_changes)


def test_nonrecovery_operation_still_rejects_an_unchanged_protected_state() -> None:
    operation = _fixture().cut.operations[0]
    unchanged_intended = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:unchanged-nonrecovery",
        payload={
            **_payload(operation.intended_protected_state_record),
            "state_digest": operation.expected_protected_state_record.payload[
                "state_digest"
            ],
        },
    )
    unchanged_operation = ControlRecord.build(
        kind="operation",
        record_id="operation:unchanged-nonrecovery",
        payload={
            **_payload(operation.operation_record),
            "intended_protected_state_digest": unchanged_intended.digest(),
        },
    )

    with pytest.raises(ValueError, match="protected state"):
        _rebind_registered_operation(
            operation,
            record_suffix="unchanged-nonrecovery",
            operation_record=unchanged_operation,
            intended_protected_state_record=unchanged_intended,
        )


def test_recovery_operation_cannot_cross_target_kinds_behind_one_identity() -> None:
    with pytest.raises(ValueError, match="target kind"):
        _, recovery, obligation, _ = _recovery_operation_material(
            successor_target_kind="service",
        )
        assess_operation_obligations(
            (obligation,),
            (recovery,),
            authority_head_digest=digest("9"),
        )


def test_recovery_operation_uses_its_predecessor_contract_for_immediate_authority():
    predecessor, recovery, obligation, _ = _recovery_operation_material(
        predecessor_recovery_contract_digest=digest("f"),
        successor_recovery_contract_digest=digest("5"),
    )

    matched = assess_operation_obligations(
        (obligation,),
        (recovery,),
        authority_head_digest=digest("9"),
    )

    assert matched == (recovery.operation_digest,)
    assert recovery.capability_record.payload["recovery_contract_digest"] == (
        predecessor.operation_record.payload["recovery_contract_digest"]
    )
    assert recovery.operation_record.payload["subject_digest"] == (
        predecessor.operation_record.payload["recovery_contract_digest"]
    )
    assert recovery.operation_record.payload["recovery_contract_digest"] == digest("5")
    assert recovery.operation_record.payload["recovery_target_digest"] == (
        recovery.expected_protected_state_record.digest()
    )
    assert recovery.operation_record.payload["recovery_target_digest"] != (
        predecessor.operation_record.payload["recovery_target_digest"]
    )


@pytest.mark.parametrize("recovery_hops", [2, 3])
def test_multi_hop_recovery_binds_each_immediate_predecessor(
    recovery_hops: int,
) -> None:
    operations = _multi_hop_recovery_operations(recovery_hops)

    for predecessor, successor in pairwise(operations):
        predecessor_contract = predecessor.operation_record.payload[
            "recovery_contract_digest"
        ]
        assert successor.capability_record.payload["recovery_contract_digest"] == (
            predecessor_contract
        )
        assert successor.operation_record.payload["subject_digest"] == (
            predecessor_contract
        )
        assert successor.operation_record.payload["recovery_contract_digest"] != (
            predecessor_contract
        )
        assert predecessor.operation_record.payload["recovery_target_digest"] == (
            successor.intended_protected_state_record.digest()
        )
        assert predecessor.terminal_record.payload["poststate_digest"] == (
            successor.expected_protected_state_record.digest()
        )


def test_multi_hop_recovery_rejects_a_next_fallback_contract_as_current_authority():
    operations = _multi_hop_recovery_operations(3)
    recovery = operations[2]
    substituted_capability = ControlRecord.build(
        kind="capability",
        record_id="capability:multi-hop-next-fallback-substitution",
        payload={
            **_payload(recovery.capability_record),
            "recovery_contract_digest": recovery.operation_record.payload[
                "recovery_contract_digest"
            ],
        },
    )
    substituted_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:multi-hop-next-fallback-substitution",
        payload={
            **_payload(recovery.terminal_record),
            "capability_digest": substituted_capability.digest(),
        },
    )

    with pytest.raises(ValueError, match="exact failed predecessor"):
        replace(
            recovery,
            capability_record=substituted_capability,
            terminal_record=substituted_terminal,
        )


def test_multi_hop_recovery_rejects_a_next_fallback_subject_as_current_authority():
    recovery = _multi_hop_recovery_operations(3)[2]
    substituted_subject = recovery.operation_record.payload[
        "recovery_contract_digest"
    ]
    substituted_intent = ControlRecord.build(
        kind="intent",
        record_id="intent:multi-hop-next-fallback-subject",
        payload={
            **_payload(recovery.intent_record),
            "subject_digest": substituted_subject,
        },
    )
    substituted_operation = ControlRecord.build(
        kind="operation",
        record_id="operation:multi-hop-next-fallback-subject",
        payload={
            **_payload(recovery.operation_record),
            "intent_digest": substituted_intent.digest(),
            "subject_digest": substituted_subject,
        },
    )

    with pytest.raises(ValueError, match="exact failed predecessor"):
        _rebind_registered_operation(
            recovery,
            record_suffix="multi-hop-next-fallback-subject",
            intent_record=substituted_intent,
            operation_record=substituted_operation,
        )


def test_recovery_operation_rejects_a_foreign_predecessor_recovery_target():
    with pytest.raises(ValueError, match="predecessor recovery target"):
        _, recovery, obligation, _ = _recovery_operation_material(
            predecessor_recovery_target_digest=digest("f"),
        )
        assess_operation_obligations(
            (obligation,),
            (recovery,),
            authority_head_digest=digest("9"),
        )


def test_recovery_operation_rejects_an_ordinary_operation_capability():
    _, recovery, _, _ = _recovery_operation_material()
    ordinary_payload = _payload(recovery.capability_record)
    ordinary_payload["capability_type"] = "operation"
    for field_name in (
        "predecessor_failure_record_digest",
        "predecessor_fence_epoch",
        "predecessor_operation_id",
        "recovery_contract_digest",
        "recovery_owner_role",
    ):
        del ordinary_payload[field_name]
    ordinary_capability = ControlRecord.build(
        kind="capability",
        record_id="capability:ordinary-recovery-substitution",
        payload=ordinary_payload,
    )

    with pytest.raises(ValueError, match="recovery capability"):
        replace(
            recovery,
            capability_record=ordinary_capability,
        )


@pytest.mark.parametrize(
    ("field_name", "substituted_value"),
    [
        ("predecessor_operation_id", "substituted-predecessor"),
        ("predecessor_failure_record_digest", digest("f")),
        ("predecessor_fence_epoch", 1),
        ("recovery_contract_digest", digest("f")),
        ("authorizer_digest", digest("f")),
        ("recovery_owner_role", "substituted-owner"),
    ],
)
def test_recovery_operation_rejects_substituted_capability_provenance(
    field_name: str,
    substituted_value: object,
):
    _, recovery, _, _ = _recovery_operation_material()
    substituted_capability = ControlRecord.build(
        kind="capability",
        record_id=f"capability:recovery-substituted-{field_name}",
        payload={
            **_payload(recovery.capability_record),
            field_name: substituted_value,
        },
    )

    with pytest.raises(ValueError, match="exact failed predecessor"):
        replace(recovery, capability_record=substituted_capability)


@pytest.mark.parametrize(
    "field_name",
    [
        "predecessor_failure_record_digest",
        "predecessor_fence_epoch",
        "predecessor_operation_id",
        "recovery_contract_digest",
        "recovery_owner_role",
    ],
)
def test_recovery_capability_rejects_missing_structural_provenance(
    field_name: str,
):
    _, recovery, _, _ = _recovery_operation_material()
    incomplete_payload = _payload(recovery.capability_record)
    del incomplete_payload[field_name]

    with pytest.raises(
        RecordValidationError,
        match="complete predecessor and owner binding",
    ):
        ControlRecord.build(
            kind="capability",
            record_id=f"capability:recovery-missing-{field_name}",
            payload=incomplete_payload,
        )


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("recovery_predecessor_operation", "failed predecessor operation"),
        ("recovery_owner_identity_record", "recovery_owner_identity_record"),
    ],
)
def test_recovery_operation_rejects_missing_typed_provenance(
    field_name: str,
    message: str,
):
    _, recovery, _, _ = _recovery_operation_material()

    with pytest.raises((TypeError, ValueError), match=message):
        replace(recovery, **{field_name: None})


def test_recovery_operation_rejects_a_substituted_owner_record():
    _, recovery, _, _ = _recovery_operation_material()
    substituted_owner = _identity(
        "identity:substituted-recovery-owner",
        "substituted-recovery-owner",
        "principal",
        "f",
        roles=["recovery-owner"],
    )

    with pytest.raises(ValueError, match="exact failed predecessor"):
        replace(
            recovery,
            recovery_owner_identity_record=substituted_owner,
        )


def test_recovery_operation_rejects_a_substituted_predecessor_graph():
    predecessor, recovery, _, _ = _recovery_operation_material()
    substituted_operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:substituted-failed-predecessor",
        payload={
            **_payload(predecessor.operation_record),
            "operation_id": "substituted-failed-predecessor",
        },
    )
    substituted_predecessor = _rebind_registered_operation(
        predecessor,
        record_suffix="substituted-failed-predecessor",
        operation_record=substituted_operation_record,
    )

    with pytest.raises(ValueError, match="exact failed predecessor"):
        replace(
            recovery,
            recovery_predecessor_operation=substituted_predecessor,
        )


def test_nonrecovery_operation_rejects_a_recovery_capability():
    predecessor, _, _, owner = _recovery_operation_material()
    recovery_capability = ControlRecord.build(
        kind="capability",
        record_id="capability:nonrecovery-with-recovery-authority",
        payload={
            **_payload(predecessor.capability_record),
            "authorizer_digest": owner.digest(),
            "capability_type": "recovery",
            "predecessor_failure_record_digest": digest("f"),
            "predecessor_fence_epoch": 1,
            "predecessor_operation_id": "earlier-failed-operation",
            "recovery_contract_digest": predecessor.operation_record.payload[
                "recovery_contract_digest"
            ],
            "recovery_owner_role": "recovery-owner",
        },
    )

    with pytest.raises(ValueError, match="non-recovery operation"):
        replace(predecessor, capability_record=recovery_capability)


def test_w4_rollback_operation_rejects_a_rollback_capability_substitution():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    substituted_capability = ControlRecord.build(
        kind="capability",
        record_id="capability:w4-rollback-capability-substitution",
        payload={
            **_payload(restoration.capability_record),
            "capability_type": "rollback",
        },
    )
    substituted_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:w4-rollback-capability-substitution",
        payload={
            **_payload(restoration.terminal_record),
            "capability_digest": substituted_capability.digest(),
        },
    )

    with pytest.raises(ValueError, match="non-recovery operation"):
        replace(
            restoration,
            capability_record=substituted_capability,
            terminal_record=substituted_terminal,
        )


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
    foundation_operation = _rebind_registered_operation(
        operation,
        record_suffix="repository-publication:foundation-substitution",
        operation_record=foundation_operation_record,
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
    substituted = _rebind_registered_operation(
        operation,
        record_suffix="blocking-scenario:substituted",
        intent_record=substituted_intent,
        operation_record=substituted_operation_record,
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
        _operation_obligation(
            first,
            obligation_id="blocking-scenario-first",
            assignment_record=fixture.contract.assignment_records[0],
        ),
        _operation_obligation(
            second,
            obligation_id="blocking-scenario-second",
            assignment_record=fixture.contract.assignment_records[0],
        ),
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
        lifecycle_phase: str,
        target_kind: str,
    ) -> ControlRecord:
        return ControlRecord.build(
            kind="protected_state",
            record_id=record_id,
            payload={
                "fence_epoch": 1,
                "generation_digest": generation.digest(),
                "lifecycle_phase": lifecycle_phase,
                "observed_at": "2026-08-12T09:15:00Z",
                "projection_id": "generic-projection",
                "state_digest": digest(seed),
                "target_digest": target.digest(),
                "target_kind": target_kind,
            },
        )

    foundation_operation = _build_registered_operation(
        subject_digest=foundation.digest(),
        subject_kind="generation",
        context_digest=digest("2"),
        candidate_generation=foundation,
        target_state=protected_state(
            "protected-state:foundation",
            foundation,
            "3",
            "foundation_validation",
            "isolated_root",
        ),
        target_record=target,
        operation_id="foundation-installation",
        operation_kind="package_installation",
        lifecycle_phase="foundation_validation",
        target_kind="isolated_root",
        target_id=target.payload["identity_id"],
        generation_class="f",
        intent_sequence=1,
        terminal_sequence=2,
    )
    baseline_operation = _build_registered_operation(
        subject_digest=digest("4"),
        subject_kind="composite_authority",
        context_digest=digest("5"),
        candidate_generation=baseline,
        target_state=protected_state(
            "protected-state:baseline",
            baseline,
            "6",
            "captured",
            "composite_register",
        ),
        target_record=target,
        operation_id="baseline-capture",
        operation_kind="composite_authority_transition",
        lifecycle_phase="captured",
        target_kind="composite_register",
        target_id=target.payload["identity_id"],
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


def test_generic_operation_matcher_rejects_rollback_to_candidate_generation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    restoration_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == restoration.operation_digest
    )
    candidate_destination = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:w4-candidate-masquerading-as-baseline",
        payload={
            **_payload(restoration.intended_protected_state_record),
            "generation_digest": fixture.candidate_generation.digest(),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:w4-candidate-masquerading-as-baseline",
        payload={
            **_payload(restoration.operation_record),
            "intended_protected_state_digest": candidate_destination.digest(),
        },
    )
    substituted = _rebind_registered_operation(
        restoration,
        record_suffix="w4-candidate-masquerading-as-baseline",
        operation_record=operation_record,
        intended_protected_state_record=candidate_destination,
    )
    substituted_obligation = _operation_obligation(
        substituted,
        obligation_id="w4-candidate-masquerading-as-baseline",
        requirement=restoration_obligation.requirement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_operation_obligations(
            (substituted_obligation,),
            (substituted,),
            authority_head_digest=digest("9"),
            captured_baseline_protected_state_record=(
                captured.target_protected_state_record
            ),
        )

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_generic_operation_matcher_accepts_exact_baseline_restoration():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    restoration_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == restoration.operation_digest
    )

    matched = assess_operation_obligations(
        (restoration_obligation,),
        (restoration,),
        authority_head_digest=digest("9"),
        captured_baseline_protected_state_record=(
            captured.target_protected_state_record
        ),
    )

    assert matched == (restoration.operation_digest,)


def test_generic_operation_matcher_rejects_rollback_to_wrong_projection():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    restoration_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == restoration.operation_digest
    )
    wrong_expected = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:w4-wrong-projection:expected",
        payload={
            **_payload(restoration.expected_protected_state_record),
            "projection_id": "wrong-projection",
        },
    )
    wrong_destination = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:w4-wrong-projection:intended",
        payload={
            **_payload(restoration.intended_protected_state_record),
            "projection_id": "wrong-projection",
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:w4-wrong-projection",
        payload={
            **_payload(restoration.operation_record),
            "expected_protected_state_digest": wrong_expected.digest(),
            "intended_protected_state_digest": wrong_destination.digest(),
        },
    )
    substituted = _rebind_registered_operation(
        restoration,
        record_suffix="w4-wrong-projection",
        operation_record=operation_record,
        expected_protected_state_record=wrong_expected,
        intended_protected_state_record=wrong_destination,
    )
    substituted_obligation = _operation_obligation(
        substituted,
        obligation_id="w4-wrong-projection",
        requirement=restoration_obligation.requirement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_operation_obligations(
            (substituted_obligation,),
            (substituted,),
            authority_head_digest=digest("9"),
            captured_baseline_protected_state_record=(
                captured.target_protected_state_record
            ),
        )

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_generic_operation_matcher_rejects_rollback_to_wrong_state():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    restoration_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == restoration.operation_digest
    )
    wrong_destination = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:w4-wrong-state",
        payload={
            **_payload(restoration.intended_protected_state_record),
            "state_digest": digest("f"),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:w4-wrong-state",
        payload={
            **_payload(restoration.operation_record),
            "intended_protected_state_digest": wrong_destination.digest(),
        },
    )
    substituted = _rebind_registered_operation(
        restoration,
        record_suffix="w4-wrong-state",
        operation_record=operation_record,
        intended_protected_state_record=wrong_destination,
    )
    substituted_obligation = _operation_obligation(
        substituted,
        obligation_id="w4-wrong-state",
        requirement=restoration_obligation.requirement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_operation_obligations(
            (substituted_obligation,),
            (substituted,),
            authority_head_digest=digest("9"),
            captured_baseline_protected_state_record=(
                captured.target_protected_state_record
            ),
        )

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_generic_operation_matcher_rejects_wrong_baseline_recovery_target():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    captured = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert isinstance(captured, StructuralBaselineCapture)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")
    restoration_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.operation_digest == restoration.operation_digest
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:w4-wrong-recovery-target",
        payload={
            **_payload(restoration.operation_record),
            "recovery_target_digest": digest("f"),
        },
    )
    substituted = _rebind_registered_operation(
        restoration,
        record_suffix="w4-wrong-recovery-target",
        operation_record=operation_record,
    )
    substituted_obligation = _operation_obligation(
        substituted,
        obligation_id="w4-wrong-recovery-target",
        requirement=restoration_obligation.requirement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_operation_obligations(
            (substituted_obligation,),
            (substituted,),
            authority_head_digest=digest("9"),
            captured_baseline_protected_state_record=(
                captured.target_protected_state_record
            ),
        )

    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_prevalidated_w4_assessment_enforces_exact_baseline_restoration():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    restoration = _operation_for_purpose(fixture, "baseline_restoration")

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)
    checkpoint = _materialize_structural_checkpoint(fixture)

    assert assessment.phase is PromotionPhase.PREVALIDATED
    assert restoration.operation_record.payload["operation_kind"] == "rollback"
    assert restoration.capability_record.payload["capability_type"] == "operation"
    assert isinstance(
        checkpoint.baseline_restoration_receipt,
        BaselineRestorationReceipt,
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


@pytest.mark.parametrize(
    ("field", "substitute"),
    [
        ("plan_digest", digest("d")),
        (
            "declared_effects",
            [
                {
                    "classification": "poststate_observable",
                    "effect_id": "substituted-effect",
                    "projection_digest": digest("e"),
                }
            ],
        ),
        ("recovery_contract_digest", digest("e")),
        ("terminal_validator_digest", digest("f")),
    ],
)
def test_realized_operation_cannot_substitute_its_approved_requirement(
    field,
    substitute,
):
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    operation = _operation_for_purpose(fixture, "phase_transition")
    intent = operation.intent_record
    operation_payload = {
        **_payload(operation.operation_record),
        field: substitute,
    }
    if field == "plan_digest":
        intent = ControlRecord.build(
            kind="intent",
            record_id="intent:substituted-approved-plan",
            payload={
                **_payload(intent),
                "operation_plan_digest": substitute,
            },
        )
        operation_payload["intent_digest"] = intent.digest()
    operation_record = ControlRecord.build(
        kind="operation",
        record_id=f"operation:substituted-approved-{field}",
        payload=operation_payload,
    )
    replacement = _rebind_registered_operation(
        operation,
        record_suffix=f"substituted-approved-{field}",
        intent_record=intent,
        operation_record=operation_record,
    )
    contract, cut = _replace_exact_contract_operation(
        fixture,
        operation,
        replacement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(contract, cut)
    assert exc_info.value.code == "PROMOTION_OPERATION_BINDING_MISMATCH"


def test_operation_requirement_realizations_reject_duplicates_and_orphans():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    requirement = fixture.contract.operation_requirements[0]
    obligation = fixture.contract.operation_obligations[0]

    with pytest.raises(ValueError, match="duplicate operation requirements"):
        replace(
            fixture.contract,
            operation_requirements=(requirement, requirement),
        )
    with pytest.raises(ValueError, match="duplicate operation obligations"):
        replace(
            fixture.contract,
            operation_obligations=(obligation, obligation),
        )

    same_id_requirement = OperationRequirement(
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation-requirement:same-stable-id",
            payload={
                **_payload(requirement.requirement_record),
                "plan_digest": digest("d"),
            },
        ),
        requirement.target_record,
        requirement.assignment_record,
    )
    with pytest.raises(ValueError, match="duplicate operation requirements"):
        replace(
            fixture.contract,
            operation_requirements=(requirement, same_id_requirement),
        )

    same_id_obligation = OperationObligation(
        ControlRecord.build(
            kind="operation_obligation",
            record_id="operation-obligation:same-stable-id",
            payload={
                **_payload(obligation.obligation_record),
                "operation_digest": digest("f"),
            },
        ),
        obligation.requirement,
    )
    with pytest.raises(ValueError, match="duplicate operation obligations"):
        replace(
            fixture.contract,
            operation_obligations=(obligation, same_id_obligation),
        )

    orphan_requirement = OperationRequirement(
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation-requirement:unapproved-orphan",
            payload={
                **_payload(requirement.requirement_record),
                "requirement_id": "unapproved-orphan",
            },
        ),
        requirement.target_record,
        requirement.assignment_record,
    )
    orphan_obligation = OperationObligation(
        ControlRecord.build(
            kind="operation_obligation",
            record_id="operation-obligation:unapproved-orphan",
            payload={
                **_payload(obligation.obligation_record),
                "obligation_id": "unapproved-orphan",
                "operation_requirement_digest": (
                    orphan_requirement.requirement_digest
                ),
            },
        ),
        orphan_requirement,
    )
    obligation_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation-obligation-set:unapproved-orphan",
        payload={
            **_payload(fixture.contract.operation_obligation_set_record),
            "obligation_digests": [orphan_obligation.obligation_digest],
        },
    )
    original_realization = fixture.contract.operation_realizations[0]
    orphan_realization = _operation_realization(
        original_realization.operation,
        orphan_obligation,
        realization_id="unapproved-orphan",
        resolved_subject_record=original_realization.resolved_subject_record,
        resolved_generation_record=original_realization.resolved_generation_record,
    )
    realization_set = ControlRecord.build(
        kind="operation_realization_set",
        record_id="operation-realization-set:unapproved-orphan",
        payload={
            "operation_obligation_set_digest": obligation_set.digest(),
            "operation_realization_digests": [
                orphan_realization.realization_digest
            ],
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:unapproved-orphan",
        payload={
            **_payload(fixture.contract.contract_record),
            "operation_obligation_set_digest": obligation_set.digest(),
            "operation_realization_set_digest": realization_set.digest(),
            "phase_establishing_operation_obligation_digest": (
                orphan_obligation.obligation_digest
            ),
        },
    )

    with pytest.raises(ValueError, match="unapproved requirement"):
        replace(
            fixture.contract,
            operation_obligation_set_record=obligation_set,
            operation_realization_set_record=realization_set,
            contract_record=contract_record,
            operation_obligations=(orphan_obligation,),
            operation_realizations=(orphan_realization,),
        )


def test_operation_realization_binds_the_exact_approved_lifecycle_roles():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    realization = fixture.contract.operation_realizations[0]

    assert isinstance(realization, OperationRealization)
    assert realization.resolved_subject_digest == fixture.candidate_generation.digest()
    assert realization.resolved_generation_binding == {
        "generation_digest": fixture.candidate_generation.digest(),
        "mode": "required_generation",
    }
    assert (
        realization.observed_prestate_record.digest()
        == realization.operation.expected_protected_state_record.digest()
    )
    assert (
        realization.observed_prestate_record.digest()
        != fixture.contract.predecessor_checkpoint.target_protected_state_record.digest()
    )
    assert (
        realization.observed_prestate_record.digest()
        != fixture.contract.target_protected_state_record.digest()
    )


def test_operation_rejects_a_caller_selected_candidate_subject():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    original = fixture.cut.operations[0]
    caller_subject = _generation(
        "generation:caller-selected-subject",
        "caller-selected-subject",
        "f",
    )
    intent = ControlRecord.build(
        kind="intent",
        record_id="intent:caller-selected-subject",
        payload={
            **_payload(original.intent_record),
            "subject_digest": caller_subject.digest(),
        },
    )
    with pytest.raises(ValueError, match="generation subject must equal"):
        ControlRecord.build(
            kind="operation",
            record_id="operation:caller-selected-subject",
            payload={
                **_payload(original.operation_record),
                "intent_digest": intent.digest(),
                "subject_digest": caller_subject.digest(),
            },
        )


def test_operation_graph_rejects_a_lifecycle_pointer_as_target_prestate():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    original = fixture.cut.operations[0]
    lifecycle_pointer = (
        fixture.contract.predecessor_checkpoint.target_protected_state_record
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:lifecycle-pointer-prestate",
        payload={
            **_payload(original.operation_record),
            "expected_protected_state_digest": lifecycle_pointer.digest(),
            "recovery_target_digest": lifecycle_pointer.digest(),
        },
    )
    with pytest.raises(
        ValueError,
        match=(
            "exact target kind|target-specific observed prestate|"
            "distinct from lifecycle pointer"
        ),
    ):
        replacement = _rebind_registered_operation(
            original,
            record_suffix="lifecycle-pointer-prestate",
            operation_record=operation_record,
            expected_protected_state_record=lifecycle_pointer,
        )
        _replace_exact_contract_operation(fixture, original, replacement)


def test_always_operation_requirement_cannot_be_left_unrealized():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    empty_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation-obligation-set:missing-always-realization",
        payload={
            **_payload(fixture.contract.operation_obligation_set_record),
            "obligation_digests": [],
        },
    )
    empty_realization_set = ControlRecord.build(
        kind="operation_realization_set",
        record_id="operation-realization-set:missing-always-realization",
        payload={
            "operation_obligation_set_digest": empty_set.digest(),
            "operation_realization_digests": [],
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:missing-always-realization",
        payload={
            **_payload(fixture.contract.contract_record),
            "operation_obligation_set_digest": empty_set.digest(),
            "operation_realization_set_digest": empty_realization_set.digest(),
        },
    )

    with pytest.raises(ValueError, match="lacks its exact realization"):
        replace(
            fixture.contract,
            operation_obligation_set_record=empty_set,
            operation_realization_set_record=empty_realization_set,
            contract_record=contract_record,
            operation_obligations=(),
            operation_realizations=(),
        )


def test_accepted_closeout_scenario_runs_after_active_on_the_candidate_service_fence():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = fixture.cut.operations[0]
    service_receipt = fixture.contract.service_anchor_receipt
    assert isinstance(service_receipt, ServiceAnchorReceipt)
    service_anchor = service_receipt.service_protected_state_record

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.ACCEPTED
    assert operation.operation_record.payload["lifecycle_phase"] == "active"
    assert operation.operation_record.payload["target_kind"] == "service"
    assert (
        operation.expected_protected_state_record.payload["generation_digest"]
        == fixture.candidate_generation.digest()
    )
    assert (
        operation.expected_protected_state_record.digest()
        == service_anchor.digest()
    )
    assert service_anchor.payload["target_kind"] == "service"
    assert service_anchor.payload["projection_id"] == "active-service-state"
    assert (
        operation.intended_protected_state_record.payload["fence_epoch"]
        == service_anchor.payload["fence_epoch"] + 1
    )


def test_accepted_cut_forbids_accepted_phase_critical_operations():
    with pytest.raises(ValueError, match="approved requirement coordinates"):
        _fixture(
            phase=PromotionPhase.ACCEPTED,
            scenario_lifecycle_phase=PromotionPhase.ACCEPTED.value,
        )


def test_accepted_closeout_scenario_rejects_an_arbitrary_service_prestate():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = fixture.cut.operations[0]
    wrong_expected = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:accepted-scenario:arbitrary-expected",
        payload={
            **_payload(operation.expected_protected_state_record),
            "fence_epoch": (
                operation.expected_protected_state_record.payload["fence_epoch"]
                + 4
            ),
            "state_digest": digest("e"),
        },
    )
    wrong_intended = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:accepted-scenario:arbitrary-intended",
        payload={
            **_payload(operation.intended_protected_state_record),
            "fence_epoch": wrong_expected.payload["fence_epoch"] + 1,
            "state_digest": digest("f"),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:accepted-scenario:arbitrary-state",
        payload={
            **_payload(operation.operation_record),
            "expected_protected_state_digest": wrong_expected.digest(),
            "intended_protected_state_digest": wrong_intended.digest(),
        },
    )
    replacement = _rebind_registered_operation(
        operation,
        record_suffix="accepted-scenario:arbitrary-state",
        operation_record=operation_record,
        expected_protected_state_record=wrong_expected,
        intended_protected_state_record=wrong_intended,
    )
    with pytest.raises(ValueError, match="prior exact terminal poststate"):
        _cut_with_operation(fixture, replacement)


def test_accepted_scenario_cannot_copy_the_live_root_anchor():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = fixture.cut.operations[0]
    live_root = fixture.contract.predecessor_checkpoint.target_protected_state_record
    copied = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:scenario:copied-live-root",
        payload={
            **_payload(live_root),
            "process_epoch": operation.expected_protected_state_record.payload[
                "process_epoch"
            ],
            "target_digest": operation.target_record.digest(),
            "target_kind": "service",
        },
    )
    intended = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:scenario:copied-live-root:intended",
        payload={
            **_payload(copied),
            "fence_epoch": copied.payload["fence_epoch"] + 1,
            "observed_at": operation.intended_protected_state_record.payload[
                "observed_at"
            ],
            "process_epoch": operation.intended_protected_state_record.payload[
                "process_epoch"
            ],
            "state_digest": digest("f"),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:scenario:copied-live-root",
        payload={
            **_payload(operation.operation_record),
            "expected_protected_state_digest": copied.digest(),
            "intended_protected_state_digest": intended.digest(),
        },
    )
    replacement = _rebind_registered_operation(
        operation,
        record_suffix="scenario:copied-live-root",
        operation_record=operation_record,
        expected_protected_state_record=copied,
        intended_protected_state_record=intended,
    )
    with pytest.raises(
        ValueError,
        match="prior exact terminal poststate",
    ):
        _replace_exact_contract_operation(
            fixture,
            operation,
            replacement,
        )


def test_second_accepted_scenario_must_consume_the_first_scenario_poststate():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    final_operation = _operation_for_purpose(fixture, "final_service_restart")
    service_receipt = fixture.contract.service_anchor_receipt
    assert isinstance(service_receipt, ServiceAnchorReceipt)
    service_anchor = service_receipt.service_protected_state_record
    intended_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:final-restart:stale-predecessor-anchor",
        payload={
            **_payload(final_operation.intended_protected_state_record),
            "fence_epoch": service_anchor.payload["fence_epoch"] + 1,
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:final-restart:stale-predecessor-anchor",
        payload={
            **_payload(final_operation.operation_record),
            "expected_protected_state_digest": service_anchor.digest(),
            "intended_protected_state_digest": intended_state.digest(),
        },
    )
    replacement = _rebind_registered_operation(
        final_operation,
        record_suffix="final-restart:stale-predecessor-anchor",
        operation_record=operation_record,
        expected_protected_state_record=service_anchor,
        intended_protected_state_record=intended_state,
    )
    with pytest.raises(ValueError, match="prior exact terminal poststate"):
        _replace_exact_contract_operation(
            fixture,
            final_operation,
            replacement,
        )


def test_next_service_scenario_cannot_start_before_the_prior_scenario_terminal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    first = fixture.cut.operations[0]
    delayed_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:first-scenario:delayed-journal-position",
        payload={
            **_payload(first.terminal_record),
            "completed_at": "2026-08-12T09:14:03Z",
        },
    )
    delayed_first = replace(first, terminal_record=delayed_terminal)
    operations = (delayed_first, *fixture.cut.operations[1:])
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:w0:early-second-scenario",
        payload={
            **_payload(fixture.cut.cut_record),
            "capability_digests": [item.capability_digest for item in operations],
            "operation_digests": [item.operation_digest for item in operations],
            "operation_terminal_digests": [
                item.terminal_digest for item in operations
            ],
            "registration_set_digest": registration_set_digest(
                fixture.cut.attempts,
                operations,
            ),
        },
    )

    with pytest.raises(ValueError, match="journal time contradicts sequence order"):
        replace(
            fixture.cut,
            cut_record=cut_record,
            operations=operations,
            validator_attestation_records=tuple(
                attestation
                for operation in operations
                for attestation in operation.validator_attestation_records
            ),
        )


def test_accepted_closeout_scenario_rejects_an_arbitrary_terminal_poststate():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = fixture.cut.operations[0]
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:accepted-scenario:arbitrary-poststate",
        payload={
            **_payload(operation.terminal_record),
            "poststate_digest": digest("f"),
        },
    )

    with pytest.raises(ValueError, match="intended protected state"):
        replace(operation, terminal_record=terminal)


def test_active_installation_terminal_must_equal_the_contract_target_state():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_gate=False,
        include_root_installation=True,
    )
    contract_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:contract-active",
        payload={
            **_payload(fixture.target_state),
            "state_digest": digest("f"),
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:wrong-active-poststate",
        payload={
            **_payload(fixture.contract.contract_record),
            "target_protected_state_digest": contract_state.digest(),
        },
    )
    contract = replace(
        fixture.contract,
        target_protected_state_record=contract_state,
        contract_record=contract_record,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:wrong-active-poststate",
        payload={
            **_payload(fixture.cut.cut_record),
            "contract_digest": contract.contract_digest,
            "target_protected_state_digest": contract_state.digest(),
        },
    )
    cut = replace(
        fixture.cut,
        cut_record=cut_record,
        target_protected_state_record=contract_state,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(contract, cut)

    assert exc_info.value.code == "PROMOTION_TARGET_STATE_MISMATCH"


@pytest.mark.parametrize("outcome", ("failed", "unknown"))
def test_non_successful_critical_operation_retains_its_attestation_window(
    outcome,
):
    fixture = _fixture()
    operation = _registered_operation(
        fixture,
        outcome=outcome,
        poststate_digest=digest("0"),
        attested_at="2026-08-12T09:13:50Z",
    )
    cut = _cut_with_operation(fixture, operation)

    assert (
        operation.validator_attestation_records[0].payload["observed_at"]
        < operation.intended_protected_state_record.payload["observed_at"]
    )
    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)

    assert exc_info.value.code == "PROMOTION_OPERATION_DID_NOT_PASS"


def test_critical_operation_intent_must_precede_its_terminal_in_the_journal():
    fixture = _fixture()

    with pytest.raises(ValueError, match="journal order"):
        _registered_operation(fixture, intent_sequence=6)


def test_atomic_cut_rejects_a_cross_kind_journal_sequence_collision():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = fixture.cut.operations[0]
    colliding_intent = ControlRecord.build(
        kind="intent",
        record_id="intent:scenario:collides-with-gate-attempt",
        payload={
            **_payload(operation.intent_record),
            "journal_sequence": fixture.attempt.attempt_record.payload[
                "journal_sequence"
            ],
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:scenario:collides-with-gate-attempt",
        payload={
            **_payload(operation.operation_record),
            "intent_digest": colliding_intent.digest(),
        },
    )
    replacement = _rebind_registered_operation(
        operation,
        record_suffix="scenario:collides-with-gate-attempt",
        intent_record=colliding_intent,
        operation_record=operation_record,
    )

    with pytest.raises(ValueError, match="globally unique"):
        _replace_exact_contract_operation(fixture, operation, replacement)


def test_atomic_cut_rejects_a_nested_recovery_predecessor_sequence_collision():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    _, recovery, _, _ = _recovery_operation_material(
        predecessor_intent_sequence=2,
        predecessor_terminal_sequence=3,
        successor_intent_sequence=5,
        successor_terminal_sequence=6,
        time_changes={
            "predecessor_state": "2026-08-12T06:35:00Z",
            "predecessor_registered": "2026-08-12T06:31:00Z",
            "predecessor_issued": "2026-08-12T06:32:00Z",
            "predecessor_attested": "2026-08-12T06:38:00Z",
            "predecessor_completed": "2026-08-12T06:39:00Z",
            "successor_state": "2026-08-12T07:10:45Z",
            "successor_registered": "2026-08-12T07:10:30Z",
            "successor_issued": "2026-08-12T07:10:35Z",
            "successor_attested": "2026-08-12T07:10:50Z",
            "successor_completed": "2026-08-12T07:11:00Z",
            "expires": "2026-08-12T07:12:00Z",
        },
    )
    operations = (recovery, *fixture.cut.operations[1:])

    with pytest.raises(ValueError, match="globally unique"):
        _cut_with_operations(
            fixture.cut,
            operations,
            record_suffix="nested-recovery-sequence-collision",
            complete_through_sequence=6,
        )


def test_atomic_cut_rejects_nested_recovery_journal_time_order_contradiction():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    _, recovery, _, _ = _recovery_operation_material(
        predecessor_intent_sequence=2,
        predecessor_terminal_sequence=5,
        successor_intent_sequence=6,
        successor_terminal_sequence=7,
        time_changes={
            "predecessor_state": "2026-08-12T07:10:24Z",
            "predecessor_registered": "2026-08-12T07:10:20Z",
            "predecessor_issued": "2026-08-12T07:10:21Z",
            "predecessor_attested": "2026-08-12T07:10:24Z",
            "predecessor_completed": "2026-08-12T07:10:25Z",
            "successor_state": "2026-08-12T07:10:45Z",
            "successor_registered": "2026-08-12T07:10:30Z",
            "successor_issued": "2026-08-12T07:10:35Z",
            "successor_attested": "2026-08-12T07:10:50Z",
            "successor_completed": "2026-08-12T07:11:00Z",
            "expires": "2026-08-12T07:12:00Z",
        },
    )
    operations = (recovery, *fixture.cut.operations[1:])

    with pytest.raises(ValueError, match="journal time contradicts sequence order"):
        _cut_with_operations(
            fixture.cut,
            operations,
            record_suffix="nested-recovery-sequence-order",
            complete_through_sequence=7,
        )


def test_atomic_cut_accepts_an_ordered_nested_recovery_journal_graph():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    predecessor, recovery, _, _ = _recovery_operation_material(
        predecessor_intent_sequence=5,
        predecessor_terminal_sequence=6,
        successor_intent_sequence=7,
        successor_terminal_sequence=8,
        time_changes={
            "predecessor_state": "2026-08-12T07:10:15Z",
            "predecessor_registered": "2026-08-12T07:10:10Z",
            "predecessor_issued": "2026-08-12T07:10:11Z",
            "predecessor_attested": "2026-08-12T07:10:18Z",
            "predecessor_completed": "2026-08-12T07:10:20Z",
            "successor_state": "2026-08-12T07:10:45Z",
            "successor_registered": "2026-08-12T07:10:30Z",
            "successor_issued": "2026-08-12T07:10:35Z",
            "successor_attested": "2026-08-12T07:10:50Z",
            "successor_completed": "2026-08-12T07:11:00Z",
            "expires": "2026-08-12T07:12:00Z",
        },
    )
    operations = (recovery, *fixture.cut.operations[1:])

    cut = _cut_with_operations(
        fixture.cut,
        operations,
        record_suffix="nested-recovery-sequence-ordered",
        complete_through_sequence=8,
    )

    assert predecessor.terminal_sequence < (
        recovery.intent_record.payload["journal_sequence"]
    )
    assert cut.cut_record.payload["complete_through_sequence"] == 8


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


def test_canonical_gate_evidence_rejects_an_unauthorized_attestor():
    fixture = _fixture()
    attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:unauthorized",
        payload={
            **_payload(fixture.bound.evidence_records[0]),
            "actor_identity_digest": digest("f"),
            "actor_role": "unauthorized",
        },
    )
    evaluation_record = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:unauthorized",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "attestation_digests": [attestation.digest()],
        },
    )
    with pytest.raises(ValueError, match="not authorized"):
        replace(
            fixture.bound,
            evidence_records=(attestation,),
            evaluation_record=evaluation_record,
        )


def test_gate_attestation_accepts_an_exact_identity_grant_without_a_role_grant():
    fixture = _fixture(
        allowed_attestor_roles=[],
    )

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.authoritative is False


def test_identity_only_gate_attestation_rejects_a_same_role_outsider():
    fixture = _fixture(allowed_attestor_roles=[])
    original_actor = fixture.bound.validator_identity_record
    outsider = _identity(
        "identity:attestation-outsider:validator",
        "attestation-outsider-validator",
        "validator",
        "f",
        roles=["validator"],
    )
    authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:gate:identity-only-outsider",
        payload={
            **_payload(fixture.bound.attestation_authorization_record),
            "allowed_actor_identity_digests": [original_actor.digest()],
            "allowed_actor_roles": [],
        },
    )
    gate = ControlRecord.build(
        kind="gate",
        record_id="gate:identity-only-outsider",
        payload={
            **_payload(fixture.bound.gate_record),
            "attestation_authorization_digest": authorization.digest(),
            "validator_digest": outsider.digest(),
        },
    )
    assignment = ControlRecord.build(
        kind="assignment",
        record_id="assignment:identity-only-outsider",
        payload={
            **_payload(fixture.bound.assignment_record),
            "authorization_policy_digest": authorization.digest(),
            "gate_digest": gate.digest(),
        },
    )

    with pytest.raises(ValueError, match="validator authorization"):
        replace(
            fixture.bound,
            assignment_record=assignment,
            gate_record=gate,
            attestation_authorization_record=authorization,
            validator_identity_record=outsider,
        )


def test_selected_attestor_role_must_be_required_by_the_separation_policy():
    with pytest.raises(ValueError, match="not authorized"):
        _fixture(
            attestor_roles=["auditor", "validator"],
            attestation_actor_role="auditor",
            allowed_attestor_roles=["auditor", "validator"],
        )


def test_canonical_gate_evidence_forbids_a_serialized_admissibility_projection():
    fixture = _fixture()
    with pytest.raises(RecordValidationError, match="admissible"):
        ControlRecord.build(
            kind="evaluation",
            record_id="evaluation:forged-inadmissible",
            payload={
                **_payload(fixture.bound.evaluation_record),
                "admissible": False,
            },
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

    assert assessment.obligation_evaluation_digests == tuple(
        evaluation.evaluation_record.digest()
        for evaluation in fixture.cut.evaluations
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


def test_registered_attempt_rejects_context_substitution_after_intent():
    fixture = _fixture()
    substituted_attempt = ControlRecord.build(
        kind="attempt",
        record_id="attempt:control-plane:substituted-context",
        payload={
            **_payload(fixture.attempt.attempt_record),
            "context_digest": digest("f"),
        },
    )
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:substituted-context",
        payload={
            **_payload(fixture.attempt.terminal_record),
            "attempt_digest": substituted_attempt.digest(),
        },
    )

    with pytest.raises(ValueError, match="attempt context does not bind intent"):
        replace(
            fixture.attempt,
            attempt_record=substituted_attempt,
            terminal_record=terminal,
        )


def test_evidence_observation_cannot_precede_attempt_start():
    fixture = _fixture()
    early_attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:control-plane:pre-attempt",
        payload={
            **_payload(fixture.bound.evidence_records[0]),
            "observed_at": "2026-08-12T09:13:29Z",
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


@pytest.mark.parametrize(
    ("complete_through_sequence", "checkpointed_at"),
    [
        (4, "2026-08-12T09:14:05Z"),
        (5, "2026-08-12T09:13:59Z"),
    ],
)
def test_currency_checkpoint_must_equal_cut_completeness_and_follow_latest_terminal(
    complete_through_sequence,
    checkpointed_at,
):
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    stream = ControlRecord.build(
        kind="invalidation_stream_checkpoint",
        record_id="invalidation-stream-checkpoint:before-terminal",
        payload={
            **_payload(fixture.bound.invalidation_stream_checkpoint_record),
            "complete_through_sequence": complete_through_sequence,
            "checkpointed_at": checkpointed_at,
        },
    )
    proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence-currency-proof:before-terminal",
        payload={
            **_payload(fixture.bound.currency_proof_record),
            "invalidation_stream_checkpoint_digest": stream.digest(),
        },
    )
    bound = replace(
        fixture.bound,
        invalidation_stream_checkpoint_record=stream,
        currency_proof_record=proof,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:currency-before-terminal",
        payload={
            **_payload(fixture.cut.cut_record),
            "currency_proof_digests": [
                proof.digest(),
                *(
                    evaluation.currency_proof_record.digest()
                    for evaluation in fixture.cut.evaluations[1:]
                ),
            ],
        },
    )

    with pytest.raises(
        ValueError,
        match="exact authority view|after every terminal",
    ):
        replace(
            fixture.cut,
            cut_record=cut_record,
            evaluations=(bound, *fixture.cut.evaluations[1:]),
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


def test_prevalidated_w4_receipt_allows_an_authorized_blocking_scenario():
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=True,
        scenario_target_kind="service",
        scenario_target_id="qualification-service",
    )

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)
    checkpoint = _materialize_structural_checkpoint(fixture)
    receipt = checkpoint.baseline_restoration_receipt

    assert assessment.phase is PromotionPhase.PREVALIDATED
    assert fixture.cut.cut_record.payload["complete_through_sequence"] == 11
    assert len(fixture.cut.operations) == 4
    assert isinstance(receipt, BaselineRestorationReceipt)
    assert receipt.evidence_cut.cut_record_digest == fixture.cut.cut_record_digest


def test_prevalidated_w4_receipt_rejects_a_missing_referenced_operation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    receipt = _baseline_restoration_receipt(fixture)
    operations = tuple(
        operation
        for operation in fixture.cut.operations
        if operation.operation_digest
        != receipt.isolated_install_operation.operation_digest
    )
    incomplete_cut = _cut_with_operations(
        fixture.cut,
        operations,
        record_suffix="w4-missing-isolated-install",
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4:missing-isolated-install",
        payload={
            **_payload(receipt.receipt_record),
            "restoration_evidence_cut_digest": incomplete_cut.cut_record_digest,
        },
    )

    with pytest.raises(ValueError, match="exact W4 cut"):
        replace(
            receipt,
            receipt_record=receipt_record,
            evidence_cut=incomplete_cut,
        )


def test_prevalidated_w4_receipt_rejects_a_substituted_referenced_operation():
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=True,
        scenario_target_kind="service",
        scenario_target_id="qualification-service",
    )
    receipt = _baseline_restoration_receipt(fixture)
    scenario = next(
        operation
        for operation in fixture.cut.operations
        if operation.operation_record.payload["operation_kind"]
        == "blocking_scenario"
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4:substituted-isolated-install",
        payload={
            **_payload(receipt.receipt_record),
            "isolated_install_operation_digest": scenario.operation_digest,
            "isolated_install_operation_terminal_digest": scenario.terminal_digest,
        },
    )

    with pytest.raises(ValueError, match="exact W4 cut"):
        replace(
            receipt,
            receipt_record=receipt_record,
            isolated_install_operation=scenario,
        )


def test_prevalidated_w4_receipt_rejects_a_substituted_smoke_terminal():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    receipt = _baseline_restoration_receipt(fixture)
    substituted_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:control-plane:1:w4-substituted-smoke",
        payload=_payload(receipt.smoke_attempt.terminal_record),
    )
    substituted_attempt = replace(
        receipt.smoke_attempt,
        terminal_record=substituted_terminal,
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4:substituted-smoke",
        payload={
            **_payload(receipt.receipt_record),
            "post_restoration_gate_terminal_digest": substituted_terminal.digest(),
        },
    )

    with pytest.raises(ValueError, match="exact W4 cut"):
        replace(
            receipt,
            receipt_record=receipt_record,
            smoke_attempt=substituted_attempt,
        )


def test_prevalidated_w4_checkpoint_rejects_an_orphan_cut_operation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    orphan = _build_registered_operation(
        subject_digest=fixture.candidate_generation.digest(),
        subject_kind="generation",
        context_digest=fixture.bound.context_record.digest(),
        candidate_generation=fixture.candidate_generation,
        target_state=fixture.target_state,
        target_record=fixture.target,
        operation_id="unapproved-w4-extra",
        operation_kind="package_installation",
        lifecycle_phase=PromotionPhase.PREVALIDATED.value,
        target_kind="isolated_root",
        target_id=fixture.target.payload["identity_id"],
        intent_sequence=10,
        terminal_sequence=11,
        registered_at="2026-08-12T08:11:36Z",
        issued_at="2026-08-12T08:11:36.1Z",
        attested_at="2026-08-12T08:11:36.8Z",
        completed_at="2026-08-12T08:11:37Z",
        expires_at="2026-08-12T08:12:00Z",
    )
    orphan_cut = _cut_with_operations(
        fixture.cut,
        (*fixture.cut.operations, orphan),
        record_suffix="w4-orphan-operation",
        complete_through_sequence=11,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        _materialize_structural_checkpoint(replace(fixture, cut=orphan_cut))

    assert exc_info.value.code == "PROMOTION_OPERATIONS_INCOMPLETE"


def test_prevalidated_w4_cut_rejects_a_duplicate_referenced_operation():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)

    with pytest.raises(ValueError, match="must not contain duplicates"):
        _cut_with_operations(
            fixture.cut,
            (*fixture.cut.operations, fixture.cut.operations[0]),
            record_suffix="w4-duplicate-isolated-install",
        )


def test_prevalidated_w4_receipt_rejects_a_cut_from_another_contract():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED)
    receipt = _baseline_restoration_receipt(fixture)
    foreign = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=True,
        scenario_target_kind="service",
        scenario_target_id="qualification-service",
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4:foreign-cut",
        payload={
            **_payload(receipt.receipt_record),
            "restoration_evidence_cut_digest": foreign.cut.cut_record_digest,
        },
    )

    with pytest.raises(ValueError, match="exact W4 cut"):
        replace(
            receipt,
            receipt_record=receipt_record,
            evidence_cut=foreign.cut,
        )


def test_accepted_cut_requires_the_immutable_active_predecessor_transition():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    wrong_predecessor = fixture.contract.predecessor_checkpoint.predecessor_checkpoint
    assert wrong_predecessor is not None

    wrong_contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:wrong-accepted-predecessor",
        payload={
            **_payload(fixture.contract.contract_record),
            "predecessor_checkpoint_digest": wrong_predecessor.checkpoint_digest,
        },
    )
    with pytest.raises(ValueError, match="prior phase"):
        replace(
            fixture.contract,
            contract_record=wrong_contract_record,
            predecessor_checkpoint=wrong_predecessor,
        )

    assert (
        fixture.contract.predecessor_checkpoint.phase
        is LifecyclePhase.ACTIVE
    )


def test_structural_c_candidate_requires_materialized_exact_phase_evidence():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    active_checkpoint = fixture.contract.predecessor_checkpoint

    with pytest.raises(TypeError, match="materialized"):
        replace(active_checkpoint, promotion_contract=None)


def test_accepted_structural_candidate_rejects_relabelled_request_or_approval_digests():
    checkpoint = _materialize_structural_checkpoint(
        _fixture(phase=PromotionPhase.ACCEPTED)
    )
    relabelled = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:accepted:relabelled-approval",
        payload={
            **_payload(checkpoint.checkpoint_record),
            "approval_digest": digest("e"),
        },
    )

    with pytest.raises(ValueError, match="exact request and approval"):
        replace(checkpoint, structural_record=relabelled)


def test_structural_lifecycle_candidate_follows_its_complete_cut_and_approval():
    checkpoint = _materialize_structural_checkpoint(
        _fixture(phase=PromotionPhase.ACCEPTED)
    )
    early = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:accepted:before-cut",
        payload={
            **_payload(checkpoint.checkpoint_record),
            "established_at": "2026-08-12T09:14:00Z",
        },
    )

    with pytest.raises(ValueError, match="complete cut, predecessor, or approval"):
        replace(checkpoint, structural_record=early)


def test_structural_candidate_chain_recurses_through_the_b0_capture():
    accepted_checkpoint = _materialize_structural_checkpoint(
        _fixture(phase=PromotionPhase.ACCEPTED)
    )
    checkpoints: list[
        StructuralLifecycleCandidate | StructuralBaselineCapture
    ] = []
    checkpoint: StructuralLifecycleCandidate | StructuralBaselineCapture | None = (
        accepted_checkpoint
    )
    while checkpoint is not None:
        checkpoints.append(checkpoint)
        checkpoint = checkpoint.predecessor_checkpoint

    assert [item.phase.value for item in checkpoints] == [
        "accepted",
        "active",
        "prevalidated",
        "published",
        "captured",
    ]
    for item in checkpoints[:-1]:
        assert isinstance(item, StructuralLifecycleCandidate)
        assert item.promotional is False
        assert item.promotion_contract is not None
        assert item.evidence_cut is not None
    root = checkpoints[-1]
    assert isinstance(root, StructuralBaselineCapture)
    assert root.promotional is False
    assert root.root_authorization_record is not None
    assert (
        root.checkpoint_record.payload["root_authorization_digest"]
        == root.root_authorization_record.digest()
    )
    assert accepted_checkpoint.acceptance_request_record is not None
    assert accepted_checkpoint.approval_record is not None

    active = checkpoints[1]
    phase_obligation_digest = active.promotion_contract.contract_record.payload[
        "phase_establishing_operation_obligation_digest"
    ]
    phase_obligation = next(
        item
        for item in active.promotion_contract.operation_obligations
        if item.obligation_digest == phase_obligation_digest
    )
    phase_operation = next(
        item
        for item in active.evidence_cut.operations
        if item.operation_digest == phase_obligation.operation_digest
    )
    assert (
        phase_operation.terminal_record.payload["poststate_digest"]
        == active.target_protected_state_record.digest()
    )


def test_public_checkpoint_constructor_cannot_mint_an_authoritative_root():
    target = _identity("identity:constructor-target", "constructor-target", "target", "b")
    root = _captured_checkpoint(target=target)

    with pytest.raises(TypeError, match="authority admission"):
        LifecycleCheckpoint(
            checkpoint_record=root.checkpoint_record,
            generation_record=root.generation_record,
            target_record=root.target_record,
            target_protected_state_record=root.target_protected_state_record,
            root_authorization_record=root.root_authorization_record,
            root_authorization_policy_record=root.root_authorization_policy_record,
            root_actor_identity_record=root.root_actor_identity_record,
            root_separation_policy_record=root.root_separation_policy_record,
        )


def test_object_protocol_cannot_mint_an_authority_issued_checkpoint():
    target = _identity("identity:forged-target", "forged-target", "target", "b")
    structural_root = _captured_checkpoint(target=target)
    forged = object.__new__(LifecycleCheckpoint)
    material = {
        "checkpoint_record": structural_root.checkpoint_record,
        "generation_record": structural_root.generation_record,
        "target_record": structural_root.target_record,
        "target_protected_state_record": (
            structural_root.target_protected_state_record
        ),
        "predecessor_checkpoint": None,
        "promotion_contract": None,
        "evidence_cut": None,
        "authority_proof_record": None,
        "acceptance_request_record": None,
        "approval_record": None,
        "final_service_anchor_receipt": None,
        "baseline_restoration_receipt": None,
        "service_anchor_receipt": None,
        "root_authorization_record": structural_root.root_authorization_record,
        "root_authorization_policy_record": (
            structural_root.root_authorization_policy_record
        ),
        "root_actor_identity_record": structural_root.root_actor_identity_record,
        "root_separation_policy_record": (
            structural_root.root_separation_policy_record
        ),
    }
    for field_name, value in material.items():
        object.__setattr__(forged, field_name, value)

    forged.__post_init__()

    assert forged.promotional is False

    published = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    structural_predecessor = published.contract.predecessor_checkpoint
    forged_predecessor = object.__new__(LifecycleCheckpoint)
    predecessor_material = {
        "checkpoint_record": structural_predecessor.checkpoint_record,
        "generation_record": structural_predecessor.generation_record,
        "target_record": structural_predecessor.target_record,
        "target_protected_state_record": (
            structural_predecessor.target_protected_state_record
        ),
        "predecessor_checkpoint": None,
        "promotion_contract": None,
        "evidence_cut": None,
        "authority_proof_record": None,
        "acceptance_request_record": None,
        "approval_record": None,
        "final_service_anchor_receipt": None,
        "baseline_restoration_receipt": None,
        "service_anchor_receipt": None,
        "root_authorization_record": (
            structural_predecessor.root_authorization_record
        ),
        "root_authorization_policy_record": (
            structural_predecessor.root_authorization_policy_record
        ),
        "root_actor_identity_record": (
            structural_predecessor.root_actor_identity_record
        ),
        "root_separation_policy_record": (
            structural_predecessor.root_separation_policy_record
        ),
    }
    for field_name, value in predecessor_material.items():
        object.__setattr__(forged_predecessor, field_name, value)
    forged_predecessor.__post_init__()

    with pytest.raises(TypeError, match="authority-issued"):
        replace(
            published.contract,
            predecessor_checkpoint=forged_predecessor,
        )


def test_testing_checkpoint_allocators_are_not_main_control_plane_exports():
    assert {
        "issue_lifecycle_checkpoint_for_testing",
        "seal_authority_issued_checkpoint_for_testing",
    }.isdisjoint(control_plane.__all__)


def _authority_issued_published_checkpoint() -> LifecycleCheckpoint:
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    structural_root = fixture.contract.predecessor_checkpoint
    assert isinstance(structural_root, StructuralBaselineCapture)
    root = object.__new__(LifecycleCheckpoint)
    root_material = {
        "checkpoint_record": structural_root.checkpoint_record,
        "generation_record": structural_root.generation_record,
        "target_record": structural_root.target_record,
        "target_protected_state_record": (
            structural_root.target_protected_state_record
        ),
        "predecessor_checkpoint": None,
        "promotion_contract": None,
        "evidence_cut": None,
        "authority_proof_record": None,
        "acceptance_request_record": None,
        "approval_record": None,
        "final_service_anchor_receipt": None,
        "baseline_restoration_receipt": None,
        "service_anchor_receipt": None,
        "root_authorization_record": structural_root.root_authorization_record,
        "root_authorization_policy_record": (
            structural_root.root_authorization_policy_record
        ),
        "root_actor_identity_record": structural_root.root_actor_identity_record,
        "root_separation_policy_record": (
            structural_root.root_separation_policy_record
        ),
    }
    for field_name, value in root_material.items():
        object.__setattr__(root, field_name, value)
    root.__post_init__()
    seal_authority_issued_checkpoint_for_testing(root)

    contract = replace(fixture.contract, predecessor_checkpoint=root)
    authority = RecordingPromotionAuthority()
    challenge = PromotionAuthorityChallenge.from_cut(
        contract,
        fixture.cut,
        authority_adapter_identity_digest=(
            authority.authority_adapter_identity_digest
        ),
        authority_view_digest=authority.authority_view_digest,
        predecessor_checkpoint=root,
    )
    proof = authority.verify_promotion_cut(challenge)
    checkpoint_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:internally-issued-published",
        payload={
            "authority_proof_digest": proof.digest(),
            "checkpoint_id": "internally-issued-published",
            "contract_digest": contract.contract_digest,
            "evidence_cut_digest": fixture.cut.cut_record_digest,
            "established_at": _PHASE_TIMES[PromotionPhase.PUBLISHED][
                "checkpoint"
            ],
            "generation_class": "c",
            "generation_digest": contract.generation_digest,
            "phase": PromotionPhase.PUBLISHED.value,
            "predecessor_checkpoint_digest": root.checkpoint_digest,
            "target_digest": contract.target_record.digest(),
            "target_protected_state_digest": (
                contract.target_protected_state_record.digest()
            ),
        },
    )
    return issue_lifecycle_checkpoint_for_testing(
        checkpoint_record=checkpoint_record,
        generation_record=contract.generation_record,
        target_record=contract.target_record,
        target_protected_state_record=contract.target_protected_state_record,
        predecessor_checkpoint=root,
        promotion_contract=contract,
        evidence_cut=fixture.cut,
        authority_proof_record=proof,
        acceptance_request_record=None,
        approval_record=None,
        final_service_anchor_receipt=None,
        baseline_restoration_receipt=None,
        service_anchor_receipt=None,
    )


def _reconstructed_structural_checkpoint(
    checkpoint: LifecycleCheckpoint,
) -> StructuralLifecycleCandidate:
    root = checkpoint.predecessor_checkpoint
    assert isinstance(root, LifecycleCheckpoint)
    assert root.predecessor_checkpoint is None
    structural_root = StructuralBaselineCapture(
        structural_record=_reparse(root.checkpoint_record),
        generation_record=_reparse(root.generation_record),
        target_record=_reparse(root.target_record),
        target_protected_state_record=_reparse(
            root.target_protected_state_record
        ),
        capture_approval_record=_reparse(root.root_authorization_record),
        capture_authorization_record=_reparse(
            root.root_authorization_policy_record
        ),
        capture_actor_identity_record=_reparse(root.root_actor_identity_record),
        capture_separation_policy_record=_reparse(
            root.root_separation_policy_record
        ),
    )
    contract = replace(
        checkpoint.promotion_contract,
        requirements_record=_reparse(
            checkpoint.promotion_contract.requirements_record
        ),
        predecessor_checkpoint=structural_root,
    )
    cut = replace(
        checkpoint.evidence_cut,
        cut_record=_reparse(checkpoint.evidence_cut.cut_record),
    )
    return StructuralLifecycleCandidate(
        structural_record=_reparse(checkpoint.checkpoint_record),
        generation_record=_reparse(checkpoint.generation_record),
        target_record=_reparse(checkpoint.target_record),
        target_protected_state_record=_reparse(
            checkpoint.target_protected_state_record
        ),
        predecessor_checkpoint=structural_root,
        promotion_contract=contract,
        evidence_cut=cut,
    )


def _checkpoint_with_changed_child_graph(
    checkpoint: StructuralLifecycleCandidate,
) -> StructuralLifecycleCandidate:
    realization = next(
        item
        for item in checkpoint.promotion_contract.operation_realizations
        if item.resolved_generation_record is not None
    )
    changed_realization = replace(realization, resolved_generation_record=None)
    changed_contract = replace(
        checkpoint.promotion_contract,
        operation_realizations=tuple(
            changed_realization if item is realization else item
            for item in checkpoint.promotion_contract.operation_realizations
        ),
    )
    return replace(checkpoint, promotion_contract=changed_contract)


def _issue_prevalidated_checkpoint(
    fixture: Fixture,
    predecessor: LifecycleCheckpoint,
    *,
    checkpoint_id: str,
    proof_verified_at: str | None = None,
    established_at: str | None = None,
    reconstruct_records: bool = False,
) -> LifecycleCheckpoint:
    authority = RecordingPromotionAuthority(
        proof_changes=(
            {"verified_at": proof_verified_at}
            if proof_verified_at is not None
            else None
        )
    )
    challenge = PromotionAuthorityChallenge.from_cut(
        fixture.contract,
        fixture.cut,
        authority_adapter_identity_digest=(
            authority.authority_adapter_identity_digest
        ),
        authority_view_digest=authority.authority_view_digest,
        predecessor_checkpoint=predecessor,
    )
    proof = authority.verify_promotion_cut(challenge)
    if reconstruct_records:
        proof = _reparse(proof)
    baseline_receipt = _baseline_restoration_receipt(fixture)
    checkpoint_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"lifecycle-checkpoint:{checkpoint_id}",
        payload={
            "authority_proof_digest": proof.digest(),
            "baseline_restoration_receipt_digest": baseline_receipt.receipt_digest,
            "checkpoint_id": checkpoint_id,
            "contract_digest": fixture.contract.contract_digest,
            "evidence_cut_digest": fixture.cut.cut_record_digest,
            "established_at": established_at
            or _PHASE_TIMES[PromotionPhase.PREVALIDATED]["checkpoint"],
            "generation_class": "c",
            "generation_digest": fixture.contract.generation_digest,
            "phase": PromotionPhase.PREVALIDATED.value,
            "predecessor_checkpoint_digest": predecessor.checkpoint_digest,
            "target_digest": fixture.contract.target_record.digest(),
            "target_protected_state_digest": (
                fixture.contract.target_protected_state_record.digest()
            ),
        },
    )
    if reconstruct_records:
        checkpoint_record = _reparse(checkpoint_record)
    return issue_lifecycle_checkpoint_for_testing(
        checkpoint_record=checkpoint_record,
        generation_record=fixture.contract.generation_record,
        target_record=fixture.contract.target_record,
        target_protected_state_record=(
            fixture.contract.target_protected_state_record
        ),
        predecessor_checkpoint=predecessor,
        promotion_contract=fixture.contract,
        evidence_cut=fixture.cut,
        authority_proof_record=proof,
        acceptance_request_record=None,
        approval_record=None,
        final_service_anchor_receipt=None,
        baseline_restoration_receipt=baseline_receipt,
        service_anchor_receipt=None,
    )


def test_admission_rejects_same_digest_predecessor_with_changed_child_graph_before_authority():
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    divergent = _checkpoint_with_changed_child_graph(reconstructed)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=divergent,
    )
    authority = RecordingPromotionAuthority()

    assert divergent.checkpoint_digest == authoritative.checkpoint_digest
    with pytest.raises(PromotionDenied, match="exact authoritative predecessor"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            authority,
            baseline_restoration_receipt=_baseline_restoration_receipt(fixture),
            checkpoint_id="prevalidated-divergent-predecessor",
            established_at=_PHASE_TIMES[PromotionPhase.PREVALIDATED]["checkpoint"],
        )
    assert authority.challenge is None


def test_admission_accepts_a_reconstructed_canonical_predecessor_graph():
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
    )
    authority = RecordingPromotionAuthority()

    with pytest.raises(NonPromotionalEvidence, match="verified production authority"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            authority,
            baseline_restoration_receipt=_baseline_restoration_receipt(fixture),
            checkpoint_id="prevalidated-reconstructed-predecessor",
            established_at=_PHASE_TIMES[PromotionPhase.PREVALIDATED]["checkpoint"],
        )
    assert authority.challenge is not None


def test_structural_checkpoint_rejects_an_inconsistent_predecessor_graph():
    authoritative = _authority_issued_published_checkpoint()
    divergent = _checkpoint_with_changed_child_graph(
        _reconstructed_structural_checkpoint(authoritative)
    )
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=divergent,
    )
    checkpoint = _materialize_structural_checkpoint(fixture)

    with pytest.raises(ValueError, match="object graph"):
        replace(checkpoint, predecessor_checkpoint=authoritative)


def test_lifecycle_checkpoint_rejects_an_inconsistent_predecessor_graph():
    authoritative = _authority_issued_published_checkpoint()
    divergent = _checkpoint_with_changed_child_graph(
        _reconstructed_structural_checkpoint(authoritative)
    )
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=divergent,
    )
    with pytest.raises(ValueError, match="object graph"):
        _issue_prevalidated_checkpoint(
            fixture,
            authoritative,
            checkpoint_id="inconsistent-predecessor",
        )


def test_lifecycle_checkpoint_accepts_a_reconstructed_predecessor_graph():
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
    )

    checkpoint = _issue_prevalidated_checkpoint(
        fixture,
        authoritative,
        checkpoint_id="reconstructed-predecessor",
    )

    assert checkpoint.promotional is True
    assert checkpoint.predecessor_checkpoint is authoritative


@pytest.mark.parametrize(
    "currency_case",
    [
        {"attestation_max_age_seconds": 35},
        {
            "conditional_applicable": True,
            "predicate_proof_max_age_seconds": 35,
        },
        {
            "preassembly": True,
            "inclusion_edge_max_age_seconds": 28,
        },
    ],
    ids=("attestation", "predicate-proof", "inclusion-edge"),
)
def test_admission_revalidates_constituent_currency_at_proof_time(currency_case):
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
        **currency_case,
    )
    baseline_receipt = _baseline_restoration_receipt(fixture)

    exact_authority = RecordingPromotionAuthority()
    with pytest.raises(NonPromotionalEvidence, match="verified production authority"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            exact_authority,
            baseline_restoration_receipt=baseline_receipt,
            checkpoint_id="proof-at-constituent-expiry",
            established_at="2026-08-12T08:12:00Z",
        )
    assert exact_authority.challenge is not None
    exact_checkpoint = _issue_prevalidated_checkpoint(
        fixture,
        authoritative,
        checkpoint_id="proof-at-constituent-expiry",
        established_at="2026-08-12T08:12:00Z",
    )
    assert exact_checkpoint.promotional is True

    late_authority = RecordingPromotionAuthority(
        proof_changes={"verified_at": "2026-08-12T08:12:01Z"}
    )
    with pytest.raises(PromotionDenied) as exc_info:
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            late_authority,
            baseline_restoration_receipt=baseline_receipt,
            checkpoint_id="proof-after-constituent-expiry",
            established_at="2026-08-12T08:12:01Z",
        )
    assert exc_info.value.code == "PROMOTION_EVIDENCE_NOT_CURRENT"


def test_admission_revalidates_cut_currency_at_checkpoint_time():
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
        evidence_cut_max_age_seconds=75,
    )
    baseline_receipt = _baseline_restoration_receipt(fixture)

    exact_authority = RecordingPromotionAuthority()
    with pytest.raises(NonPromotionalEvidence, match="verified production authority"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            exact_authority,
            baseline_restoration_receipt=baseline_receipt,
            checkpoint_id="checkpoint-at-cut-expiry",
            established_at="2026-08-12T08:13:00Z",
        )
    assert exact_authority.challenge is not None
    exact_checkpoint = _issue_prevalidated_checkpoint(
        fixture,
        authoritative,
        checkpoint_id="checkpoint-at-cut-expiry",
    )
    assert exact_checkpoint.promotional is True

    late_authority = RecordingPromotionAuthority()
    with pytest.raises(PromotionDenied) as exc_info:
        admit_promotion(
            fixture.contract,
            fixture.cut,
            authoritative,
            late_authority,
            baseline_restoration_receipt=baseline_receipt,
            checkpoint_id="checkpoint-after-cut-expiry",
            established_at="2026-08-12T08:13:01Z",
        )
    assert exc_info.value.code == "PROMOTION_EVIDENCE_NOT_CURRENT"


@pytest.mark.parametrize(
    ("fixture_changes", "proof_verified_at", "established_at"),
    [
        (
            {"attestation_max_age_seconds": 35},
            "2026-08-12T08:12:01Z",
            "2026-08-12T08:13:00Z",
        ),
        (
            {"evidence_cut_max_age_seconds": 75},
            "2026-08-12T08:12:00Z",
            "2026-08-12T08:13:01Z",
        ),
    ],
    ids=("proof", "established"),
)
def test_reconstructed_checkpoint_rejects_expired_admission_material(
    fixture_changes,
    proof_verified_at,
    established_at,
):
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
        **fixture_changes,
    )

    with pytest.raises(ValueError, match="not current at issuance boundary"):
        _issue_prevalidated_checkpoint(
            fixture,
            authoritative,
            checkpoint_id="expired-reconstructed-material",
            proof_verified_at=proof_verified_at,
            established_at=established_at,
            reconstruct_records=True,
        )


def test_authority_view_invalidation_rejects_before_authority_proof():
    authoritative = _authority_issued_published_checkpoint()
    reconstructed = _reconstructed_structural_checkpoint(authoritative)
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=reconstructed,
    )
    original = fixture.cut.evaluations[0]
    stream = ControlRecord.build(
        kind="invalidation_stream_checkpoint",
        record_id="invalidation-stream-checkpoint:intervening-view",
        payload={
            **_payload(original.invalidation_stream_checkpoint_record),
            "authority_view_digest": digest("f"),
        },
    )
    currency_proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence-currency-proof:intervening-view",
        payload={
            **_payload(original.currency_proof_record),
            "invalidation_stream_checkpoint_digest": stream.digest(),
        },
    )
    rebound = replace(
        original,
        invalidation_stream_checkpoint_record=stream,
        currency_proof_record=currency_proof,
    )
    evaluations = (rebound, *fixture.cut.evaluations[1:])
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:intervening-view",
        payload={
            **_payload(fixture.cut.cut_record),
            "currency_proof_digests": [
                item.currency_proof_record.digest() for item in evaluations
            ],
        },
    )
    cut = replace(fixture.cut, cut_record=cut_record, evaluations=evaluations)
    authority = RecordingPromotionAuthority()

    with pytest.raises(ValueError, match="challenged production view"):
        admit_promotion(
            fixture.contract,
            cut,
            authoritative,
            authority,
            baseline_restoration_receipt=_baseline_restoration_receipt(fixture),
            checkpoint_id="intervening-authority-view",
            established_at="2026-08-12T08:13:00Z",
        )
    assert authority.challenge is None


def _clone_lifecycle_checkpoint(checkpoint: LifecycleCheckpoint) -> LifecycleCheckpoint:
    clone = object.__new__(LifecycleCheckpoint)
    for field in fields(LifecycleCheckpoint):
        object.__setattr__(clone, field.name, getattr(checkpoint, field.name))
    clone.__post_init__()
    return clone


def test_authority_issuance_seal_binds_nested_identities_and_live_records():
    direct = _authority_issued_published_checkpoint()
    assert direct.promotional is True
    forged_predecessor = _clone_lifecycle_checkpoint(
        direct.predecessor_checkpoint
    )
    object.__setattr__(direct, "predecessor_checkpoint", forged_predecessor)

    nested = _authority_issued_published_checkpoint()
    assert nested.promotional is True
    nested_forged_predecessor = _clone_lifecycle_checkpoint(
        nested.predecessor_checkpoint
    )
    object.__setattr__(
        nested.promotion_contract,
        "predecessor_checkpoint",
        nested_forged_predecessor,
    )

    record_mutated = _authority_issued_published_checkpoint()
    assert record_mutated.promotional is True
    object.__setattr__(
        record_mutated.checkpoint_record,
        "payload",
        {
            **_payload(record_mutated.checkpoint_record),
            "checkpoint_id": "object-protocol-substitution",
        },
    )

    assert direct.promotional is False
    assert nested.promotional is False
    assert record_mutated.promotional is False


def test_unsigned_b0_shape_is_structural_and_cannot_bootstrap_admission():
    fixture = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    shaped = fixture.contract.predecessor_checkpoint
    assert isinstance(shaped, StructuralBaselineCapture)
    unsigned = replace(
        shaped,
        capture_approval_record=None,
        capture_authorization_record=None,
        capture_actor_identity_record=None,
        capture_separation_policy_record=None,
    )
    contract = replace(fixture.contract, predecessor_checkpoint=unsigned)
    authority = RecordingPromotionAuthority()

    assert unsigned.promotional is False
    with pytest.raises(NonPromotionalEvidence, match="root-authority bootstrap"):
        admit_promotion(
            contract,
            fixture.cut,
            unsigned,  # type: ignore[arg-type]
            authority,
            checkpoint_id="published-with-unsigned-root",
            established_at="2026-08-12T07:13:00Z",
        )
    assert authority.challenge is None


def _checkpoint_established_at(
    checkpoint: StructuralLifecycleCandidate,
    established_at: str,
) -> StructuralLifecycleCandidate:
    record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"{checkpoint.checkpoint_record.record_id}:retimed",
        payload={
            **_payload(checkpoint.checkpoint_record),
            "established_at": established_at,
        },
    )
    return replace(checkpoint, structural_record=record)


@pytest.mark.parametrize(
    "approval_changes",
    [
        {"authorization_digest": digest("f")},
        {"decision": "rejected"},
        {"decided_at": "2026-08-12T06:00:01Z"},
        {"action": "accept_generation"},
        {"subject_digest": digest("e")},
        {"actor_identity_digest": digest("d")},
        {"actor_role": "auditor"},
    ],
)
def test_captured_root_rejects_arbitrary_or_malformed_approval(approval_changes):
    target = _identity("identity:root-target", "root-target", "target", "a")
    root = _captured_checkpoint(target=target)
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:capture-baseline:malformed",
        payload={
            **_payload(root.root_authorization_record),
            **approval_changes,
        },
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:captured:malformed",
        payload={
            **_payload(root.checkpoint_record),
            "root_authorization_digest": approval.digest(),
        },
    )

    with pytest.raises(ValueError, match="capture approval"):
        replace(
            root,
            structural_record=checkpoint,
            capture_approval_record=approval,
        )


def test_captured_root_rejects_an_actor_outside_its_authorization_policy():
    target = _identity("identity:root-target", "root-target", "target", "a")
    root = _captured_checkpoint(target=target)
    outsider = _identity(
        "identity:root-outsider",
        "root-outsider",
        "principal",
        "b",
        roles=["auditor"],
    )
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:capture-baseline:outsider",
        payload={
            **_payload(root.root_authorization_record),
            "actor_identity_digest": outsider.digest(),
        },
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:captured:outsider",
        payload={
            **_payload(root.checkpoint_record),
            "root_authorization_digest": approval.digest(),
        },
    )

    with pytest.raises(ValueError, match="capture approval"):
        replace(
            root,
            structural_record=checkpoint,
            capture_approval_record=approval,
            capture_actor_identity_record=outsider,
        )


def test_captured_root_accepts_an_exact_identity_grant_without_a_role_grant():
    target = _identity("identity:root-target", "root-target", "target", "a")
    root = _captured_checkpoint(target=target)
    policy = ControlRecord.build(
        kind="authorization",
        record_id="authorization:baseline-capture:identity-only",
        payload={
            **_payload(root.root_authorization_policy_record),
            "allowed_actor_roles": [],
        },
    )
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:capture-baseline:identity-only",
        payload={
            **_payload(root.root_authorization_record),
            "authorization_digest": policy.digest(),
        },
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:captured:identity-only",
        payload={
            **_payload(root.checkpoint_record),
            "root_authorization_digest": approval.digest(),
        },
    )

    identity_granted = replace(
        root,
        structural_record=checkpoint,
        capture_approval_record=approval,
        capture_authorization_record=policy,
    )

    assert identity_granted.promotional is False


def test_identity_only_root_authorization_rejects_a_same_role_outsider():
    target = _identity("identity:root-target", "root-target", "target", "a")
    root = _captured_checkpoint(target=target)
    outsider = _identity(
        "identity:root-outsider:validator",
        "root-outsider-validator",
        "principal",
        "b",
        roles=["validator"],
    )
    policy = ControlRecord.build(
        kind="authorization",
        record_id="authorization:baseline-capture:identity-only-outsider",
        payload={
            **_payload(root.root_authorization_policy_record),
            "allowed_actor_roles": [],
        },
    )
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:capture-baseline:identity-only-outsider",
        payload={
            **_payload(root.root_authorization_record),
            "actor_identity_digest": outsider.digest(),
            "authorization_digest": policy.digest(),
        },
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:captured:identity-only-outsider",
        payload={
            **_payload(root.checkpoint_record),
            "root_authorization_digest": approval.digest(),
        },
    )

    with pytest.raises(ValueError, match="capture approval"):
        replace(
            root,
            structural_record=checkpoint,
            capture_approval_record=approval,
            capture_authorization_record=policy,
            capture_actor_identity_record=outsider,
        )


def test_accepted_contract_rejects_an_unauthorized_approval_actor():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    outsider = _identity(
        "identity:acceptance-outsider",
        "acceptance-outsider",
        "principal",
        "d",
        roles=["auditor"],
    )

    with pytest.raises(ValueError, match="authorized acceptance actor"):
        replace(
            fixture.contract,
            acceptance_actor_identity_record=outsider,
        )


def test_acceptance_accepts_an_exact_identity_grant_without_a_role_grant():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    authorization = fixture.contract.acceptance_authorization_record
    assert authorization is not None
    identity_only = ControlRecord.build(
        kind="authorization",
        record_id="authorization:acceptance:identity-only",
        payload={
            **_payload(authorization),
            "allowed_actor_roles": [],
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:acceptance:identity-only",
        payload={
            **_payload(fixture.contract.contract_record),
            "acceptance_authorization_digest": identity_only.digest(),
        },
    )
    contract = replace(
        fixture.contract,
        contract_record=contract_record,
        acceptance_authorization_record=identity_only,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:acceptance:identity-only",
        payload={
            **_payload(fixture.cut.cut_record),
            "contract_digest": contract.contract_digest,
        },
    )
    rebound = replace(
        fixture,
        contract=contract,
        cut=replace(fixture.cut, cut_record=cut_record),
    )

    candidate = _materialize_structural_checkpoint(rebound)

    assert candidate.promotional is False


def test_identity_only_acceptance_rejects_a_same_role_outsider():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    authorization = fixture.contract.acceptance_authorization_record
    assert authorization is not None
    outsider = _identity(
        "identity:acceptance-outsider:control-owner",
        "acceptance-outsider-control-owner",
        "principal",
        "d",
        roles=["control-owner"],
    )
    identity_only = ControlRecord.build(
        kind="authorization",
        record_id="authorization:acceptance:identity-only-outsider",
        payload={
            **_payload(authorization),
            "allowed_actor_roles": [],
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:acceptance:identity-only-outsider",
        payload={
            **_payload(fixture.contract.contract_record),
            "acceptance_authorization_digest": identity_only.digest(),
        },
    )

    with pytest.raises(ValueError, match="authorized acceptance actor"):
        replace(
            fixture.contract,
            contract_record=contract_record,
            acceptance_actor_identity_record=outsider,
            acceptance_authorization_record=identity_only,
        )


def test_acceptance_approval_rejects_a_selected_role_outside_required_separation_roles():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    request, approval = _acceptance_material(fixture)
    actor = fixture.contract.acceptance_actor_identity_record
    assert actor is not None
    multi_role_actor = ControlRecord.build(
        kind="identity",
        record_id="identity:acceptance-owner:multi-role",
        payload={
            **_payload(actor),
            "roles": ["auditor", "control-owner"],
        },
    )
    authorization = fixture.contract.acceptance_authorization_record
    assert authorization is not None
    rebound_authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:acceptance:multi-role",
        payload={
            **_payload(authorization),
            "allowed_actor_identity_digests": [multi_role_actor.digest()],
            "allowed_actor_roles": ["auditor", "control-owner"],
            "approver_roles": ["auditor", "control-owner"],
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:acceptance:multi-role",
        payload={
            **_payload(fixture.contract.contract_record),
            "acceptance_authorization_digest": rebound_authorization.digest(),
        },
    )
    contract = replace(
        fixture.contract,
        contract_record=contract_record,
        acceptance_actor_identity_record=multi_role_actor,
        acceptance_authorization_record=rebound_authorization,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:acceptance:multi-role",
        payload={
            **_payload(fixture.cut.cut_record),
            "contract_digest": contract.contract_digest,
        },
    )
    cut = replace(fixture.cut, cut_record=cut_record)
    final_receipt = _final_service_anchor_receipt(
        fixture,
        cut,
        contract,
    )
    rebound_request = ControlRecord.build(
        kind="acceptance_request",
        record_id="acceptance-request:multi-role",
        payload={
            **_payload(request),
            "acceptance_authorization_digest": rebound_authorization.digest(),
            "atomic_evidence_cut_digest": cut.cut_record_digest,
            "final_service_anchor_receipt_digest": final_receipt.receipt_digest,
            "promotion_contract_digest": contract.contract_digest,
        },
    )
    wrong_role_approval = ControlRecord.build(
        kind="approval",
        record_id="approval:acceptance:wrong-selected-role",
        payload={
            **_payload(approval),
            "actor_identity_digest": multi_role_actor.digest(),
            "actor_role": "auditor",
            "authorization_digest": rebound_authorization.digest(),
            "subject_digest": rebound_request.digest(),
        },
    )
    with pytest.raises(PromotionDenied, match="exact request"):
        admit_promotion(
            contract,
            cut,
            contract.predecessor_checkpoint,
            RecordingPromotionAuthority(),
            acceptance_request=rebound_request,
            approval=wrong_role_approval,
            final_service_anchor_receipt=final_receipt,
            checkpoint_id="accepted-with-wrong-selected-role",
            established_at="2026-08-12T09:14:30Z",
        )


@pytest.mark.parametrize(
    ("roles", "required_roles", "allowed_roles", "approver_roles"),
    [
        (["control-owner"], ["control-owner"], ["auditor"], ["control-owner"]),
        (["control-owner"], ["control-owner"], ["control-owner"], ["auditor"]),
        (
            ["control-owner"],
            ["auditor", "control-owner"],
            ["control-owner"],
            ["control-owner"],
        ),
    ],
)
def test_acceptance_contract_rejects_an_ineligible_approval_actor(
    roles,
    required_roles,
    allowed_roles,
    approver_roles,
):
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    original_actor = fixture.contract.acceptance_actor_identity_record
    original_policy = fixture.contract.acceptance_authorization_record
    original_separation = fixture.contract.acceptance_separation_policy_record
    assert original_actor is not None
    assert original_policy is not None
    assert original_separation is not None
    actor = ControlRecord.build(
        kind="identity",
        record_id="identity:acceptance-role-case",
        payload={
            **_payload(original_actor),
            "roles": roles,
        },
    )
    separation = ControlRecord.build(
        kind="separation_policy",
        record_id="separation-policy:acceptance-role-case",
        payload={
            **_payload(original_separation),
            "required_actor_roles": required_roles,
        },
    )
    authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:acceptance-role-case",
        payload={
            **_payload(original_policy),
            "allowed_actor_identity_digests": [],
            "allowed_actor_roles": allowed_roles,
            "approver_roles": approver_roles,
            "separation_policy_digest": separation.digest(),
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:acceptance-role-case",
        payload={
            **_payload(fixture.contract.contract_record),
            "acceptance_authorization_digest": authorization.digest(),
        },
    )
    with pytest.raises(ValueError, match="authorized acceptance actor"):
        replace(
            fixture.contract,
            contract_record=contract_record,
            acceptance_actor_identity_record=actor,
            acceptance_authorization_record=authorization,
            acceptance_separation_policy_record=separation,
        )


def test_acceptance_approval_allows_one_eligible_role_when_separation_requires_none():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    original_actor = fixture.contract.acceptance_actor_identity_record
    original_policy = fixture.contract.acceptance_authorization_record
    original_separation = fixture.contract.acceptance_separation_policy_record
    assert original_actor is not None
    assert original_policy is not None
    assert original_separation is not None
    actor = ControlRecord.build(
        kind="identity",
        record_id="identity:acceptance-empty-separation",
        payload={
            **_payload(original_actor),
            "roles": ["auditor", "control-owner"],
        },
    )
    separation = ControlRecord.build(
        kind="separation_policy",
        record_id="separation-policy:acceptance-empty",
        payload={
            **_payload(original_separation),
            "required_actor_roles": [],
        },
    )
    authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:acceptance-empty",
        payload={
            **_payload(original_policy),
            "allowed_actor_identity_digests": [actor.digest()],
            "allowed_actor_roles": ["auditor", "control-owner"],
            "approver_roles": ["auditor", "control-owner"],
            "separation_policy_digest": separation.digest(),
        },
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:acceptance-empty",
        payload={
            **_payload(fixture.contract.contract_record),
            "acceptance_authorization_digest": authorization.digest(),
        },
    )
    contract = replace(
        fixture.contract,
        contract_record=contract_record,
        acceptance_actor_identity_record=actor,
        acceptance_authorization_record=authorization,
        acceptance_separation_policy_record=separation,
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:acceptance-empty",
        payload={
            **_payload(fixture.cut.cut_record),
            "contract_digest": contract.contract_digest,
        },
    )
    cut = replace(fixture.cut, cut_record=cut_record)
    final_receipt = _final_service_anchor_receipt(
        fixture,
        cut,
        contract,
    )
    request = build_acceptance_request(
        contract,
        cut,
        assess_promotion_cut(contract, cut),
        final_receipt,
        record_id="acceptance-request:empty-separation",
        requested_at="2026-08-12T09:14:12Z",
    )
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval:acceptance-empty-separation",
        payload={
            "action": "accept_generation",
            "actor_identity_digest": actor.digest(),
            "actor_role": "auditor",
            "authorization_digest": authorization.digest(),
            "decided_at": "2026-08-12T09:14:15Z",
            "decision": "approved",
            "subject_digest": request.digest(),
        },
    )

    with pytest.raises(NonPromotionalEvidence, match="root-authority bootstrap"):
        admit_promotion(
            contract,
            cut,
            contract.predecessor_checkpoint,
            RecordingPromotionAuthority(),
            acceptance_request=request,
            approval=approval,
            final_service_anchor_receipt=final_receipt,
            checkpoint_id="accepted-with-empty-separation",
            established_at="2026-08-12T09:14:30Z",
        )


def test_accepted_cut_evidence_cannot_predate_the_active_checkpoint():
    accepted = _fixture(phase=PromotionPhase.ACCEPTED)
    late_active = _checkpoint_established_at(
        accepted.contract.predecessor_checkpoint,
        "2026-08-12T09:15:00Z",
    )
    fixture = _fixture(
        phase=PromotionPhase.ACCEPTED,
        predecessor_checkpoint=late_active,
        scenario_gate=False,
    )
    with pytest.raises(PromotionDenied, match="predecessor checkpoint"):
        assess_promotion_cut(fixture.contract, fixture.cut)


def test_acceptance_assessment_rejects_a_checkpoint_after_its_cut_evidence():
    accepted = _fixture(phase=PromotionPhase.ACCEPTED)
    late_active = _checkpoint_established_at(
        accepted.contract.predecessor_checkpoint,
        "2026-08-12T09:15:00Z",
    )
    fixture = _fixture(
        phase=PromotionPhase.ACCEPTED,
        predecessor_checkpoint=late_active,
        scenario_gate=False,
    )

    with pytest.raises(PromotionDenied, match="predecessor checkpoint"):
        _acceptance_material(fixture)


def test_acceptance_approval_cannot_predate_its_active_predecessor():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    request, approval = _acceptance_material(fixture)
    early = ControlRecord.build(
        kind="approval",
        record_id="approval:acceptance:before-active",
        payload={
            **_payload(approval),
            "decided_at": "2026-08-12T09:12:59Z",
        },
    )

    with pytest.raises(PromotionDenied, match="after it exists"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            RecordingPromotionAuthority(),
            acceptance_request=request,
            approval=early,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-with-early-approval",
            established_at="2026-08-12T09:14:30Z",
        )


def test_prevalidated_cut_cannot_reuse_predecessor_phase_evidence():
    prevalidated = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
    )
    late_published = _checkpoint_established_at(
        prevalidated.contract.predecessor_checkpoint,
        "2026-08-12T08:10:31Z",
    )
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
        predecessor_checkpoint=late_published,
    )

    with pytest.raises(PromotionDenied, match="predecessor checkpoint"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            late_published,
            RecordingPromotionAuthority(),
            checkpoint_id="prevalidated-with-reused-evidence",
            established_at="2026-08-12T10:13:00Z",
        )


def test_phase_operation_requires_the_exact_predecessor_protected_state():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    phase_obligation_digest = fixture.contract.contract_record.payload[
        "phase_establishing_operation_obligation_digest"
    ]
    obligation = next(
        item
        for item in fixture.contract.operation_obligations
        if item.obligation_digest == phase_obligation_digest
    )
    operation = next(
        item
        for item in fixture.cut.operations
        if item.operation_digest == obligation.operation_digest
    )
    wrong_prestate = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:wrong-active-prestate",
        payload={
            **_payload(operation.expected_protected_state_record),
            "state_digest": digest("f"),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:active:wrong-prestate",
        payload={
            **_payload(operation.operation_record),
            "expected_protected_state_digest": wrong_prestate.digest(),
        },
    )
    replacement = _rebind_registered_operation(
        operation,
        record_suffix="active:wrong-prestate",
        operation_record=operation_record,
        expected_protected_state_record=wrong_prestate,
    )
    contract, cut = _replace_exact_contract_operation(
        fixture,
        operation,
        replacement,
    )

    with pytest.raises(PromotionDenied) as exc_info:
        admit_promotion(
            contract,
            cut,
            contract.predecessor_checkpoint,
            RecordingPromotionAuthority(),
            checkpoint_id="active-with-wrong-prestate",
            established_at="2026-08-12T10:13:00Z",
        )
    assert exc_info.value.code == "PROMOTION_TARGET_STATE_MISMATCH"


def test_active_phase_consumes_the_exact_w4_baseline_restoration_state():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    receipt = fixture.contract.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    restoration_operation = receipt.restoration_operation
    phase_obligation_digest = fixture.contract.contract_record.payload[
        "phase_establishing_operation_obligation_digest"
    ]
    phase_operation_digest = next(
        obligation.operation_digest
        for obligation in fixture.contract.operation_obligations
        if obligation.obligation_digest == phase_obligation_digest
    )
    phase_operation = next(
        operation
        for operation in fixture.cut.operations
        if operation.operation_digest == phase_operation_digest
    )

    assert (
        phase_operation.expected_protected_state_record.digest()
        == restoration_operation.intended_protected_state_record.digest()
    )
    assert receipt.receipt_record.payload["restoration_evidence_cut_digest"] == (
        fixture.contract.predecessor_checkpoint.evidence_cut.cut_record_digest
    )


def test_prevalidated_checkpoint_requires_its_w4_restoration_receipt():
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
    )
    checkpoint = _materialize_structural_checkpoint(fixture)
    payload = _payload(checkpoint.structural_record)
    del payload["baseline_restoration_receipt_digest"]
    without_receipt = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:prevalidated:without-restoration",
        payload=payload,
    )

    with pytest.raises(ValueError, match="exact W4 baseline restoration receipt"):
        replace(
            checkpoint,
            structural_record=without_receipt,
            baseline_restoration_receipt=None,
        )


def test_prevalidated_checkpoint_accepts_a_reconstructed_canonical_w4_contract():
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
    )
    checkpoint = _materialize_structural_checkpoint(fixture)
    receipt = checkpoint.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    reconstructed_contract = replace(
        receipt.promotion_contract,
        requirements_record=_reparse(
            receipt.promotion_contract.requirements_record
        ),
    )
    reconstructed_receipt = replace(
        receipt,
        promotion_contract=reconstructed_contract,
    )

    reconstructed_checkpoint = replace(
        checkpoint,
        baseline_restoration_receipt=reconstructed_receipt,
    )

    assert reconstructed_checkpoint.checkpoint_digest == checkpoint.checkpoint_digest


def test_prevalidated_checkpoint_rejects_a_same_root_w4_contract_with_a_changed_child_graph():
    fixture = _fixture(
        phase=PromotionPhase.PREVALIDATED,
        scenario_gate=False,
    )
    checkpoint = _materialize_structural_checkpoint(fixture)
    receipt = checkpoint.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    original_contract = receipt.promotion_contract
    realization = next(
        item
        for item in original_contract.operation_realizations
        if item.resolved_generation_record is not None
    )
    alternate_realization = replace(realization, resolved_generation_record=None)
    alternate_contract = replace(
        original_contract,
        operation_realizations=tuple(
            alternate_realization if item is realization else item
            for item in original_contract.operation_realizations
        ),
    )
    alternate_receipt = replace(
        receipt,
        promotion_contract=alternate_contract,
    )

    assert alternate_receipt.receipt_digest == receipt.receipt_digest
    with pytest.raises(ValueError, match="exact W4 baseline restoration receipt"):
        replace(
            checkpoint,
            baseline_restoration_receipt=alternate_receipt,
        )


def test_active_checkpoint_requires_its_cut_derived_service_anchor_receipt():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    checkpoint = _materialize_structural_checkpoint(fixture)
    payload = _payload(checkpoint.structural_record)
    del payload["service_anchor_receipt_digest"]
    without_receipt = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:active:without-service-anchor",
        payload=payload,
    )

    with pytest.raises(ValueError, match="exact service anchor receipt"):
        replace(
            checkpoint,
            structural_record=without_receipt,
            service_anchor_receipt=None,
        )


@pytest.mark.parametrize("boundary_field", ["issued_at", "expires_at"])
def test_active_checkpoint_accepts_service_anchor_validity_boundaries(
    boundary_field,
):
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    checkpoint = _materialize_structural_checkpoint(fixture)
    receipt = checkpoint.service_anchor_receipt
    assert isinstance(receipt, ServiceAnchorReceipt)
    established_at = receipt.receipt_record.payload[boundary_field]
    assert isinstance(established_at, str)

    retimed = _checkpoint_established_at(checkpoint, established_at)

    assert retimed.checkpoint_record.payload["established_at"] == established_at


@pytest.mark.parametrize(
    "established_at",
    [
        "2026-08-12T09:11:09Z",
        "2026-08-12T09:16:11Z",
    ],
)
def test_active_checkpoint_rejects_establishment_outside_service_anchor_validity(
    established_at,
):
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    checkpoint = _materialize_structural_checkpoint(fixture)

    with pytest.raises(ValueError, match="service anchor validity window"):
        _checkpoint_established_at(checkpoint, established_at)


def test_active_contract_accepts_a_reconstructed_canonical_w4_receipt():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    receipt = fixture.contract.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    reconstructed_receipt = replace(
        receipt,
        receipt_record=_reparse(receipt.receipt_record),
        target_record=_reparse(receipt.target_record),
        rollback_record=_reparse(receipt.rollback_record),
        smoke_contract_record=_reparse(receipt.smoke_contract_record),
    )

    reconstructed = replace(
        fixture.contract,
        baseline_restoration_receipt=reconstructed_receipt,
    )

    assert reconstructed.contract_digest == fixture.contract.contract_digest


def test_w4_receipt_rejects_a_smoke_contract_for_another_restored_state():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    receipt = fixture.contract.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    wrong_smoke_contract = ControlRecord.build(
        kind="restored_baseline_smoke_contract",
        record_id="restored-baseline-smoke-contract:wrong-state",
        payload={
            **_payload(receipt.smoke_contract_record),
            "restored_protected_state_digest": digest("f"),
        },
    )
    receipt_record = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:wrong-smoke-contract",
        payload={
            **_payload(receipt.receipt_record),
            "post_restoration_smoke_contract_digest": (
                wrong_smoke_contract.digest()
            ),
        },
    )

    with pytest.raises(ValueError, match="post-restoration smoke"):
        replace(
            receipt,
            receipt_record=receipt_record,
            smoke_contract_record=wrong_smoke_contract,
        )


def test_service_anchor_receipt_rejects_forged_cut_material():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    forged_record = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:forged-state",
        payload={
            **_payload(receipt.receipt_record),
            "service_protected_state_digest": digest("f"),
        },
    )

    with pytest.raises(ValueError, match="exact active material"):
        replace(receipt, receipt_record=forged_record)


def test_service_anchor_starts_only_after_the_active_installation_is_complete():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    active_terminal = receipt.active_phase_operation.terminal_record.payload
    service_operation = receipt.establishing_operation

    assert active_terminal["journal_sequence"] < (
        service_operation.intent_record.payload["journal_sequence"]
    )
    assert active_terminal["completed_at"] < (
        service_operation.expected_protected_state_record.payload["observed_at"]
    )


def test_service_anchor_rejects_installation_completion_after_its_prestate_observation():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    active_operation = receipt.active_phase_operation
    late_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:active-install-after-service-prestate",
        payload={
            **_payload(active_operation.terminal_record),
            "completed_at": "2026-08-12T09:10:26Z",
        },
    )
    late_active_operation = replace(
        active_operation,
        terminal_record=late_terminal,
    )
    relabelled_receipt = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:late-active-install",
        payload={
            **_payload(receipt.receipt_record),
            "active_phase_operation_terminal_digest": late_terminal.digest(),
        },
    )

    with pytest.raises(ValueError, match="active phase installation"):
        replace(
            receipt,
            receipt_record=relabelled_receipt,
            active_phase_operation=late_active_operation,
        )


def test_service_anchor_rejects_readiness_from_another_process_epoch():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness:w5:restarted-process",
        payload={
            **_payload(receipt.readiness_record),
            "process_epoch": "service-epoch-2",
        },
    )
    receipt_record = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:w5:restarted-process",
        payload={
            **_payload(receipt.receipt_record),
            "readiness_digest": readiness.digest(),
        },
    )

    with pytest.raises(ValueError, match="one authorized process epoch"):
        replace(
            receipt,
            receipt_record=receipt_record,
            readiness_record=readiness,
        )


def test_accepted_scenarios_consume_sequential_epoch_readiness_renewals():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)
    final_anchor = _final_service_anchor_receipt(fixture)

    assert assessment.phase is PromotionPhase.ACCEPTED
    assert [
        record.payload["process_epoch"]
        for record in fixture.cut.observation_records
        if record.kind == "readiness"
    ] == ["service-epoch-2", "service-epoch-3"]
    assert (
        final_anchor.backend_provenance_record.digest()
        == fixture.cut.observation_records[-3].digest()
    )


def test_accepted_scenario_rejects_a_terminal_after_its_readiness_lease():
    fixture = _fixture(
        phase=PromotionPhase.ACCEPTED,
        final_restart_operation_completed_at="2026-08-12T09:20:00Z",
        final_restart_capability_expires_at="2026-08-12T09:21:00Z",
        final_service_observation_times=(
            "2026-08-12T09:20:00.1Z",
            "2026-08-12T09:20:01Z",
            "2026-08-12T09:20:01Z",
        ),
        phase_time_changes={
            "currency_checkpoint": "2026-08-12T09:20:02Z",
            "trusted_time": "2026-08-12T09:20:02Z",
        },
    )

    with pytest.raises(PromotionDenied, match="cover"):
        assess_promotion_cut(fixture.contract, fixture.cut)


def test_accepted_scenario_allows_a_needed_same_epoch_mid_attempt_renewal():
    fixture = _fixture(
        phase=PromotionPhase.ACCEPTED,
        final_restart_operation_completed_at="2026-08-12T09:20:00Z",
        final_restart_capability_expires_at="2026-08-12T09:21:00Z",
        mid_attempt_renewal_times=(
            "2026-08-12T09:18:00Z",
            "2026-08-12T09:18:01Z",
            "2026-08-12T09:18:01Z",
        ),
        final_service_observation_times=(
            "2026-08-12T09:20:00.1Z",
            "2026-08-12T09:20:01Z",
            "2026-08-12T09:20:01Z",
        ),
        phase_time_changes={
            "currency_checkpoint": "2026-08-12T09:20:02Z",
            "trusted_time": "2026-08-12T09:20:02Z",
        },
    )

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.phase is PromotionPhase.ACCEPTED


def test_accepted_second_scenario_rejects_missing_epoch_readiness_renewal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    cut = _cut_with_observations(
        fixture.cut,
        fixture.cut.observation_records[-3:],
        record_suffix="missing-intermediate-renewal",
    )

    with pytest.raises(PromotionDenied, match="substituted, or cross-epoch"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_second_scenario_rejects_cross_epoch_readiness_renewal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    final_restart = _operation_for_purpose(fixture, "final_service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        final_restart,
        record_suffix="wrong-intermediate-epoch",
        backend_observed_at="2026-08-12T09:14:00Z",
        health_observed_at="2026-08-12T09:14:01Z",
        readiness_observed_at="2026-08-12T09:14:01Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (backend, health, readiness, *fixture.cut.observation_records[-3:]),
        record_suffix="cross-epoch-renewal",
    )

    with pytest.raises(PromotionDenied, match="substituted, or cross-epoch"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_scenario_rejects_substituted_backend_provenance_renewal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    original_backend, original_health, original_readiness = (
        fixture.cut.observation_records[:3]
    )
    backend = ControlRecord.build(
        kind="backend_provenance",
        record_id="backend-provenance:substituted-configuration",
        payload={
            **_payload(original_backend),
            "configuration_digest": digest("f"),
        },
    )
    health = ControlRecord.build(
        kind="service_health_observation",
        record_id="service-health-observation:substituted-configuration",
        payload={
            **_payload(original_health),
            "backend_provenance_digest": backend.digest(),
        },
    )
    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness:substituted-configuration",
        payload={
            **_payload(original_readiness),
            "backend_provenance_digest": backend.digest(),
            "service_health_observation_digests": [health.digest()],
        },
    )
    cut = _cut_with_observations(
        fixture.cut,
        (
            backend,
            health,
            readiness,
            *fixture.cut.observation_records[3:],
        ),
        record_suffix="substituted-backend-provenance",
    )

    with pytest.raises(PromotionDenied, match="backend provenance"):
        assess_promotion_cut(fixture.contract, cut)


def test_final_service_anchor_rejects_substituted_backend_provenance():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    anchor = _final_service_anchor_receipt(fixture)
    backend = ControlRecord.build(
        kind="backend_provenance",
        record_id="backend-provenance:final-substituted-package",
        payload={
            **_payload(anchor.backend_provenance_record),
            "package_manifest_digest": digest("f"),
        },
    )
    health = ControlRecord.build(
        kind="service_health_observation",
        record_id="service-health-observation:final-substituted-package",
        payload={
            **_payload(anchor.service_health_observation_records[0]),
            "backend_provenance_digest": backend.digest(),
        },
    )
    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness:final-substituted-package",
        payload={
            **_payload(anchor.readiness_record),
            "backend_provenance_digest": backend.digest(),
            "service_health_observation_digests": [health.digest()],
        },
    )
    cut = _cut_with_observations(
        fixture.cut,
        (
            *fixture.cut.observation_records[:-3],
            backend,
            health,
            readiness,
        ),
        record_suffix="final-substituted-backend-provenance",
    )
    receipt = ControlRecord.build(
        kind="final_service_anchor_receipt",
        record_id="final-service-anchor-receipt:substituted-package",
        payload={
            **_payload(anchor.receipt_record),
            "backend_provenance_digest": backend.digest(),
            "evidence_cut_digest": cut.cut_record_digest,
            "readiness_digest": readiness.digest(),
        },
    )

    with pytest.raises(ValueError, match="backend provenance"):
        replace(
            anchor,
            receipt_record=receipt,
            evidence_cut=cut,
            backend_provenance_record=backend,
            service_health_observation_records=(health,),
            readiness_record=readiness,
        )


def test_final_service_anchor_requires_provenance_strictly_after_restart_terminal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    operation = _operation_for_purpose(fixture, "final_service_restart")
    authorization, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        operation,
        record_suffix="final-terminal-equality",
        backend_observed_at=operation.terminal_record.payload["completed_at"],
        health_observed_at="2026-08-12T09:14:10Z",
        readiness_observed_at="2026-08-12T09:14:10Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (*fixture.cut.observation_records[:-3], backend, health, readiness),
        record_suffix="final-terminal-equality",
    )
    anchor = _final_service_anchor_receipt(fixture)
    receipt = ControlRecord.build(
        kind="final_service_anchor_receipt",
        record_id="final-service-anchor-receipt:terminal-equality",
        payload={
            **_payload(anchor.receipt_record),
            "backend_provenance_digest": backend.digest(),
            "evidence_cut_digest": cut.cut_record_digest,
            "readiness_digest": readiness.digest(),
        },
    )

    with pytest.raises(ValueError, match="stale or noncausal"):
        replace(
            anchor,
            receipt_record=receipt,
            evidence_cut=cut,
            backend_provenance_record=backend,
            service_health_observation_records=(health,),
            readiness_record=readiness,
            observer_authorization_record=authorization,
        )


def test_accepted_second_scenario_rejects_readiness_after_its_intent():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    first_restart = _operation_for_purpose(fixture, "service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        first_restart,
        record_suffix="late-intermediate-renewal",
        backend_observed_at="2026-08-12T09:14:00Z",
        health_observed_at="2026-08-12T09:14:02Z",
        readiness_observed_at="2026-08-12T09:14:03Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (backend, health, readiness, *fixture.cut.observation_records[-3:]),
        record_suffix="late-intermediate-renewal",
    )

    with pytest.raises(PromotionDenied, match="stale, substituted, or cross-epoch"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_second_scenario_rejects_readiness_at_its_intent():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    first_restart = _operation_for_purpose(fixture, "service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        first_restart,
        record_suffix="intent-equality-intermediate-renewal",
        backend_observed_at="2026-08-12T09:14:00.1Z",
        health_observed_at="2026-08-12T09:14:01Z",
        readiness_observed_at="2026-08-12T09:14:02Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (backend, health, readiness, *fixture.cut.observation_records[-3:]),
        record_suffix="intent-equality-intermediate-renewal",
    )

    with pytest.raises(PromotionDenied, match="stale, substituted, or cross-epoch"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_second_scenario_requires_provenance_after_prior_terminal():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    first_restart = _operation_for_purpose(fixture, "service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        first_restart,
        record_suffix="prior-terminal-equality-renewal",
        backend_observed_at=first_restart.terminal_record.payload["completed_at"],
        health_observed_at="2026-08-12T09:14:01Z",
        readiness_observed_at="2026-08-12T09:14:01Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (backend, health, readiness, *fixture.cut.observation_records[-3:]),
        record_suffix="prior-terminal-equality-renewal",
    )

    with pytest.raises(PromotionDenied, match="stale, substituted, or cross-epoch"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_closeout_rejects_a_readiness_group_over_five_minutes_wide():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    first_restart = _operation_for_purpose(fixture, "service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        first_restart,
        record_suffix="overlong-intermediate-renewal",
        backend_observed_at="2026-08-12T09:08:00Z",
        health_observed_at="2026-08-12T09:14:00Z",
        readiness_observed_at="2026-08-12T09:14:01Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (backend, health, readiness, *fixture.cut.observation_records[-3:]),
        record_suffix="overlong-intermediate-renewal",
    )

    with pytest.raises(PromotionDenied, match="renewal is stale or noncausal"):
        assess_promotion_cut(fixture.contract, cut)


def test_accepted_closeout_rejects_an_orphan_service_readiness_group():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    final_restart = _operation_for_purpose(fixture, "final_service_restart")
    _, backend, health, readiness = _service_observation_records(
        fixture.contract,
        fixture.bound,
        final_restart,
        record_suffix="orphan-final-renewal",
        backend_observed_at="2026-08-12T09:14:09Z",
        health_observed_at="2026-08-12T09:14:10Z",
        readiness_observed_at="2026-08-12T09:14:10Z",
    )
    cut = _cut_with_observations(
        fixture.cut,
        (*fixture.cut.observation_records, backend, health, readiness),
        record_suffix="orphan-readiness-group",
    )

    with pytest.raises(PromotionDenied, match="unused service readiness"):
        assess_promotion_cut(fixture.contract, cut)


def test_service_anchor_rejects_readiness_for_another_backend_manifest():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness:w5:another-backend-manifest",
        payload={
            **_payload(receipt.readiness_record),
            "backend_manifest_digest": digest("f"),
        },
    )
    observations = tuple(
        readiness if item.kind == "readiness" else item
        for item in receipt.evidence_cut.observation_records
    )
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:w5:another-backend-manifest",
        payload={
            **_payload(receipt.evidence_cut.cut_record),
            "observation_digests": [item.digest() for item in observations],
        },
    )
    cut = replace(
        receipt.evidence_cut,
        cut_record=cut_record,
        observation_records=observations,
    )
    receipt_record = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:w5:another-backend-manifest",
        payload={
            **_payload(receipt.receipt_record),
            "active_evidence_cut_digest": cut.cut_record_digest,
            "readiness_digest": readiness.digest(),
        },
    )

    with pytest.raises(ValueError, match="backend manifest"):
        replace(
            receipt,
            receipt_record=receipt_record,
            evidence_cut=cut,
            readiness_record=readiness,
        )


def test_service_anchor_rejects_a_health_lease_issued_from_stale_readiness():
    fixture = _fixture(
        phase=PromotionPhase.ACTIVE,
        scenario_target_kind="service",
        scenario_target_id="inference-service",
    )
    receipt = _service_anchor_receipt(fixture)
    late_receipt = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service-anchor-receipt:w5:late-issuance",
        payload={
            **_payload(receipt.receipt_record),
            "issued_at": "2026-08-12T09:16:11Z",
            "expires_at": "2026-08-12T09:21:11Z",
        },
    )

    with pytest.raises(ValueError, match="stale or noncausal"):
        replace(receipt, receipt_record=late_receipt)


def test_accepted_contract_accepts_a_reconstructed_canonical_service_receipt():
    accepted = _fixture(phase=PromotionPhase.ACCEPTED)
    predecessor_receipt = accepted.contract.service_anchor_receipt
    assert isinstance(predecessor_receipt, ServiceAnchorReceipt)
    detached_receipt = replace(
        predecessor_receipt,
        receipt_record=_reparse(predecessor_receipt.receipt_record),
        target_record=_reparse(predecessor_receipt.target_record),
        service_protected_state_record=_reparse(
            predecessor_receipt.service_protected_state_record
        ),
        backend_provenance_record=_reparse(
            predecessor_receipt.backend_provenance_record
        ),
        service_health_observation_records=tuple(
            _reparse(item)
            for item in predecessor_receipt.service_health_observation_records
        ),
        readiness_record=_reparse(predecessor_receipt.readiness_record),
    )

    reconstructed = replace(
        accepted.contract,
        service_anchor_receipt=detached_receipt,
    )

    assert reconstructed.contract_digest == accepted.contract.contract_digest


def test_accepted_contract_rejects_a_same_root_service_receipt_with_a_changed_child_graph():
    accepted = _fixture(phase=PromotionPhase.ACCEPTED)
    predecessor_receipt = accepted.contract.service_anchor_receipt
    assert isinstance(predecessor_receipt, ServiceAnchorReceipt)
    original_contract = predecessor_receipt.promotion_contract
    realization = next(
        item
        for item in original_contract.operation_realizations
        if item.resolved_generation_record is not None
    )
    alternate_realization = replace(realization, resolved_generation_record=None)
    alternate_contract = replace(
        original_contract,
        operation_realizations=tuple(
            alternate_realization if item is realization else item
            for item in original_contract.operation_realizations
        ),
    )
    alternate_receipt = replace(
        predecessor_receipt,
        promotion_contract=alternate_contract,
    )

    assert alternate_receipt.receipt_digest == predecessor_receipt.receipt_digest
    with pytest.raises(ValueError, match="predecessor's exact service anchor receipt"):
        replace(accepted.contract, service_anchor_receipt=alternate_receipt)


@pytest.mark.parametrize(
    "receipt_change",
    [
        {"restoration_evidence_cut_digest": digest("e")},
        {"restored_protected_state_digest": digest("f")},
        {"restoration_operation_terminal_digest": digest("d")},
    ],
)
def test_active_contract_rejects_relabelled_w4_restoration_receipt(receipt_change):
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    receipt = fixture.contract.baseline_restoration_receipt
    assert isinstance(receipt, BaselineRestorationReceipt)
    changed_receipt = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline-restoration-receipt:w4:relabelled",
        payload={
            **_payload(receipt.receipt_record),
            **receipt_change,
        },
    )
    with pytest.raises(ValueError, match="restoration"):
        replace(
            receipt,
            receipt_record=changed_receipt,
        )


def test_w4_structural_checkpoint_cannot_precede_restoration_completion():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    predecessor = fixture.contract.predecessor_checkpoint
    assert isinstance(predecessor, StructuralLifecycleCandidate)

    with pytest.raises(ValueError, match="complete cut, predecessor, or approval"):
        _checkpoint_established_at(
            predecessor,
            "2026-08-12T08:10:59Z",
        )


def test_phase_operation_fence_must_advance_exactly_once():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    operation = fixture.cut.operations[0]
    wrong_prestate = ControlRecord.build(
        kind="protected_state",
        record_id="protected-state:stale-fence",
        payload={
            **_payload(operation.expected_protected_state_record),
            "fence_epoch": max(
                0,
                operation.expected_protected_state_record.payload["fence_epoch"]
                - 1,
            ),
        },
    )
    operation_record = ControlRecord.build(
        kind="operation",
        record_id="operation:active:stale-fence",
        payload={
            **_payload(operation.operation_record),
            "expected_protected_state_digest": wrong_prestate.digest(),
        },
    )

    with pytest.raises(ValueError, match="advance one fence epoch"):
        _rebind_registered_operation(
            operation,
            record_suffix="active:stale-fence",
            operation_record=operation_record,
            expected_protected_state_record=wrong_prestate,
        )


def test_phase_target_kind_must_match_the_route():
    fixture = _fixture(phase=PromotionPhase.ACTIVE, scenario_gate=False)
    record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:active:wrong-target-kind",
        payload={
            **_payload(fixture.contract.contract_record),
            "target_kind": "service",
        },
    )

    with pytest.raises(ValueError, match="phase-establishing operation"):
        replace(fixture.contract, contract_record=record)


def test_prevalidated_generation_pointers_must_continue_the_predecessor():
    fixture = _fixture(phase=PromotionPhase.PREVALIDATED, scenario_gate=False)
    unrelated = _generation("generation:unrelated", "unrelated-c", "e")
    record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:prevalidated:unrelated-pointers",
        payload={
            **_payload(fixture.contract.contract_record),
            "expected_accepted_generation_digest": unrelated.digest(),
            "expected_active_generation_digest": unrelated.digest(),
        },
    )

    with pytest.raises(ValueError, match="exact predecessor state"):
        replace(fixture.contract, contract_record=record)


def test_structural_chain_rejects_substituted_material_and_incomplete_capture_material():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    active = fixture.contract.predecessor_checkpoint
    substituted_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:substituted-proof",
        payload={
            **_payload(active.checkpoint_record),
            "contract_digest": digest("f"),
        },
    )
    with pytest.raises(ValueError, match="exact material"):
        replace(active, structural_record=substituted_record)

    root = active
    while root.predecessor_checkpoint is not None:
        root = root.predecessor_checkpoint
    with pytest.raises(ValueError, match="must be complete"):
        replace(root, capture_approval_record=None)


def test_foundation_checkpoint_is_structural_and_nonpromotional():
    target = _identity(
        "identity:foundation-target",
        "foundation-host",
        "target",
        "a",
    )
    root = _captured_checkpoint(target=target)
    foundation = _generation(
        "generation:foundation",
        "foundation-f",
        "b",
        generation_class="f",
    )
    foundation_state = _protected_state(
        "protected-state:foundation",
        generation=foundation,
        target=target,
        phase="foundation_validation",
        seed="c",
        observed_at="2026-08-12T08:00:00Z",
        target_kind="isolated_root",
    )
    checkpoint_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:foundation",
        payload={
            "checkpoint_id": "foundation-validation",
            "established_at": "2026-08-12T08:30:00Z",
            "generation_class": "f",
            "generation_digest": foundation.digest(),
            "phase": "foundation_validation",
            "predecessor_checkpoint_digest": root.checkpoint_digest,
            "target_digest": target.digest(),
            "target_protected_state_digest": foundation_state.digest(),
        },
    )

    with pytest.raises(TypeError, match="authority admission"):
        LifecycleCheckpoint(
            checkpoint_record=checkpoint_record,
            generation_record=foundation,
            target_record=target,
            target_protected_state_record=foundation_state,
            predecessor_checkpoint=root,
        )

    candidate = StructuralFoundationCandidate(
        structural_record=checkpoint_record,
        generation_record=foundation,
        target_record=target,
        target_protected_state_record=foundation_state,
        predecessor_checkpoint=root,
    )

    assert candidate.promotional is False
    assert candidate.predecessor_checkpoint.checkpoint_digest == root.checkpoint_digest

    accepted = _fixture(phase=PromotionPhase.ACCEPTED)

    wrong_phase_predecessor = accepted.contract.predecessor_checkpoint
    wrong_predecessor_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:foundation-wrong-phase-predecessor",
        payload={
            **_payload(candidate.structural_record),
            "established_at": "2026-08-12T10:13:00Z",
            "predecessor_checkpoint_digest": (
                wrong_phase_predecessor.checkpoint_digest
            ),
        },
    )
    with pytest.raises(TypeError, match="captured lifecycle material"):
        replace(
            candidate,
            structural_record=wrong_predecessor_record,
            predecessor_checkpoint=wrong_phase_predecessor,
        )

    other_target = _identity(
        "identity:other-foundation-target",
        "other-foundation-host",
        "target",
        "d",
    )
    other_root = _captured_checkpoint(target=other_target)
    wrong_target_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:foundation-wrong-target-predecessor",
        payload={
            **_payload(candidate.structural_record),
            "predecessor_checkpoint_digest": other_root.checkpoint_digest,
        },
    )
    with pytest.raises(ValueError, match="another target"):
        replace(
            candidate,
            structural_record=wrong_target_record,
            predecessor_checkpoint=other_root,
        )


@pytest.mark.parametrize("target_kind", ["live_root", "service"])
def test_foundation_candidate_rejects_nonisolated_target_kinds(target_kind):
    target = _identity(
        "identity:foundation-kind-target",
        "foundation-kind-host",
        "target",
        "a",
    )
    root = _captured_checkpoint(target=target)
    foundation = _generation(
        "generation:foundation-kind",
        "foundation-kind-f",
        "b",
        generation_class="f",
    )
    isolated_state = _protected_state(
        "protected-state:foundation-kind:isolated",
        generation=foundation,
        target=target,
        phase="foundation_validation",
        seed="c",
        observed_at="2026-08-12T08:00:00Z",
        target_kind="isolated_root",
    )
    checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="lifecycle-checkpoint:foundation-kind",
        payload={
            "checkpoint_id": "foundation-kind-validation",
            "established_at": "2026-08-12T08:30:00Z",
            "generation_class": "f",
            "generation_digest": foundation.digest(),
            "phase": "foundation_validation",
            "predecessor_checkpoint_digest": root.checkpoint_digest,
            "target_digest": target.digest(),
            "target_protected_state_digest": isolated_state.digest(),
        },
    )
    candidate = StructuralFoundationCandidate(
        structural_record=checkpoint,
        generation_record=foundation,
        target_record=target,
        target_protected_state_record=isolated_state,
        predecessor_checkpoint=root,
    )
    wrong_state = ControlRecord.build(
        kind="protected_state",
        record_id=f"protected-state:foundation-kind:{target_kind}",
        payload={
            **_payload(isolated_state),
            "target_kind": target_kind,
        },
    )
    wrong_checkpoint = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"lifecycle-checkpoint:foundation-kind:{target_kind}",
        payload={
            **_payload(checkpoint),
            "target_protected_state_digest": wrong_state.digest(),
        },
    )

    with pytest.raises(ValueError, match="foundation candidate material"):
        replace(
            candidate,
            structural_record=wrong_checkpoint,
            target_protected_state_record=wrong_state,
        )


def test_foundation_checkpoint_cannot_be_a_c_promotion_predecessor():
    published = _fixture(
        phase=PromotionPhase.PUBLISHED,
        scenario_gate=False,
    )
    target = published.target
    root = published.contract.predecessor_checkpoint
    foundation = _generation(
        "generation:foundation-predecessor",
        "foundation-predecessor-f",
        "e",
        generation_class="f",
    )
    state = _protected_state(
        "protected-state:foundation-predecessor",
        generation=foundation,
        target=target,
        phase="foundation_validation",
        seed="f",
        observed_at="2026-08-12T08:00:00Z",
        target_kind="isolated_root",
    )
    foundation_checkpoint = StructuralFoundationCandidate(
        structural_record=ControlRecord.build(
            kind="lifecycle_checkpoint",
            record_id="lifecycle-checkpoint:foundation-predecessor",
            payload={
                "checkpoint_id": "foundation-predecessor",
                "established_at": "2026-08-12T08:30:00Z",
                "generation_class": "f",
                "generation_digest": foundation.digest(),
                "phase": "foundation_validation",
                "predecessor_checkpoint_digest": root.checkpoint_digest,
                "target_digest": target.digest(),
                "target_protected_state_digest": state.digest(),
            },
        ),
        generation_record=foundation,
        target_record=target,
        target_protected_state_record=state,
        predecessor_checkpoint=root,
    )

    rebound_contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:foundation-predecessor",
        payload={
            **_payload(published.contract.contract_record),
            "predecessor_checkpoint_digest": foundation_checkpoint.structural_digest,
        },
    )
    with pytest.raises(TypeError, match="explicit structural"):
        replace(
            published.contract,
            contract_record=rebound_contract_record,
            predecessor_checkpoint=foundation_checkpoint,  # type: ignore[arg-type]
        )


def test_acceptance_approval_must_follow_and_name_the_exact_assessed_cut_request():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    request, _ = _acceptance_material(fixture)
    wrong_approval = ControlRecord.build(
        kind="approval",
        record_id="approval:wrong-acceptance-request",
        payload={
            "action": "accept_generation",
            "actor_identity_digest": digest("a"),
            "actor_role": "control-owner",
            "authorization_digest": request.payload[
                "acceptance_authorization_digest"
            ],
            "decided_at": "2026-08-12T09:14:15Z",
            "decision": "approved",
            "subject_digest": digest("f"),
        },
    )

    with pytest.raises(PromotionDenied, match="exact request"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            InMemoryAuthority().evidence_view(),
            acceptance_request=request,
            approval=wrong_approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T09:14:30Z",
        )


def test_acceptance_request_must_follow_the_complete_assessed_cut():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    request, approval = _acceptance_material(fixture)
    early_request = ControlRecord.build(
        kind="acceptance_request",
        record_id="acceptance-request:before-evidence",
        payload={
            **_payload(request),
            "requested_at": "2026-08-12T09:14:09Z",
        },
    )
    rebound_approval = ControlRecord.build(
        kind="approval",
        record_id="approval:early-acceptance-request",
        payload={
            **_payload(approval),
            "subject_digest": early_request.digest(),
        },
    )

    with pytest.raises(PromotionDenied, match="complete evidence cut"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            RecordingPromotionAuthority(),
            acceptance_request=early_request,
            approval=rebound_approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T09:14:30Z",
        )


def test_structural_predecessor_blocks_authority_verification():
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    request, approval = _acceptance_material(fixture)
    authority = RecordingPromotionAuthority()

    with pytest.raises(NonPromotionalEvidence, match="root-authority bootstrap"):
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            authority,
            acceptance_request=request,
            approval=approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T09:14:30Z",
        )
    assert authority.challenge is None


def test_nonaccepted_admission_forbids_acceptance_material():
    active = _fixture(phase=PromotionPhase.ACTIVE)
    accepted = _fixture(phase=PromotionPhase.ACCEPTED)
    request, approval = _acceptance_material(accepted)

    with pytest.raises(PromotionDenied, match="forbids acceptance"):
        admit_promotion(
            active.contract,
            active.cut,
            active.contract.predecessor_checkpoint,
            InMemoryAuthority().evidence_view(),
            acceptance_request=request,
            approval=approval,
            checkpoint_id="active-w0",
            established_at="2026-08-12T09:14:30Z",
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
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    predecessor_cut = fixture.contract.predecessor_checkpoint.evidence_cut
    assert predecessor_cut is not None
    invalid_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:invalid-accepted",
        payload={
            **_payload(fixture.contract.contract_record),
            "expected_accepted_generation_digest": (
                predecessor_cut.accepted_generation_record.digest()
            ),
        },
    )

    with pytest.raises(ValueError, match="accepted phase"):
        replace(fixture.contract, contract_record=invalid_record)


@pytest.mark.parametrize(
    ("link_mode", "message"),
    [
        ("missing", "unconditional blocking-scenario assignments require"),
        ("wrong", "scenario gate does not link"),
        ("reused", "distinct critical-operation obligations"),
    ],
)
def test_final_restart_requires_one_exact_promotion_obligation_link(
    link_mode,
    message,
):
    fixture = _fixture(phase=PromotionPhase.ACCEPTED)
    final_operation_obligation = next(
        obligation
        for obligation in fixture.contract.operation_obligations
        if obligation.requirement.requirement_record.payload["purpose"]
        == "final_service_restart"
    )
    final_promotion_obligation = next(
        obligation
        for obligation in fixture.contract.obligations
        if obligation.scenario_operation_obligation_digest
        == final_operation_obligation.obligation_digest
    )
    payload = _payload(final_promotion_obligation.obligation_record)
    if link_mode == "missing":
        payload.pop("scenario_operation_obligation_digest")
    elif link_mode == "wrong":
        payload["scenario_operation_obligation_digest"] = digest("f")
    else:
        payload["scenario_operation_obligation_digest"] = next(
            obligation.scenario_operation_obligation_digest
            for obligation in fixture.contract.obligations
            if obligation is not final_promotion_obligation
            and obligation.scenario_operation_obligation_digest is not None
        )
    replacement = PromotionObligation(
        ControlRecord.build(
            kind="promotion_obligation",
            record_id=f"promotion-obligation:final-restart:{link_mode}",
            payload=payload,
        )
    )
    obligations = tuple(
        replacement
        if obligation is final_promotion_obligation
        else obligation
        for obligation in fixture.contract.obligations
    )
    contract_record = ControlRecord.build(
        kind="promotion_contract",
        record_id=f"promotion-contract:final-restart:{link_mode}",
        payload={
            **_payload(fixture.contract.contract_record),
            "obligation_digests": [
                obligation.obligation_digest for obligation in obligations
            ],
        },
    )

    with pytest.raises(ValueError, match=message):
        replace(
            fixture.contract,
            contract_record=contract_record,
            obligations=obligations,
        )


def test_active_contract_requires_the_accepted_pointer_to_remain_prior():
    fixture = _fixture(phase=PromotionPhase.ACTIVE)
    invalid_record = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion-contract:invalid-active",
        payload={
            **_payload(fixture.contract.contract_record),
            "expected_accepted_generation_digest": (
                fixture.candidate_generation.digest()
            ),
        },
    )

    with pytest.raises(ValueError, match="active phase"):
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
    conditional_requirements = tuple(
        requirement
        for requirement in fixture.contract.operation_requirements
        if requirement.realization_condition == "when_assignment_applicable"
    )
    assert len(conditional_requirements) == 1
    conditional_requirement_digests = {
        requirement.requirement_digest for requirement in conditional_requirements
    }
    assert all(
        obligation.requirement.requirement_digest
        not in conditional_requirement_digests
        for obligation in fixture.contract.operation_obligations
    )


def test_conditional_applicable_requires_a_current_true_predicate_proof():
    fixture = _fixture(conditional_applicable=True)

    assessment = assess_promotion_cut(fixture.contract, fixture.cut)

    assert assessment.authoritative is False
    assert tuple(item.kind for item in fixture.bound.evidence_records) == (
        "predicate_proof",
        "attestation",
    )
    predicate_proof = fixture.bound.evidence_records[0]
    assert predicate_proof.payload["is_applicable"] is True
    assert (
        fixture.attempt.terminal_record.payload["predicate_proof_digest"]
        == predicate_proof.digest()
    )


def test_conditional_applicable_accepts_reconstructed_exact_proof_material():
    fixture = _fixture(conditional_applicable=True)

    reconstructed = replace(
        fixture.bound,
        attempt_record=_reparse(fixture.bound.attempt_record),
        context_record=_reparse(fixture.bound.context_record),
        assignment_record=_reparse(fixture.bound.assignment_record),
        gate_record=_reparse(fixture.bound.gate_record),
        attestation_authorization_record=_reparse(
            fixture.bound.attestation_authorization_record
        ),
        predicate_authorization_record=_reparse(
            fixture.bound.predicate_authorization_record
        ),
        separation_policy_record=_reparse(
            fixture.bound.separation_policy_record
        ),
        validator_identity_record=_reparse(
            fixture.bound.validator_identity_record
        ),
        evidence_records=tuple(
            _reparse(record) for record in fixture.bound.evidence_records
        ),
        evaluation_record=_reparse(fixture.bound.evaluation_record),
        validity_policy_record=_reparse(fixture.bound.validity_policy_record),
        invalidation_policy_record=_reparse(
            fixture.bound.invalidation_policy_record
        ),
        evaluated_dependency_projection_record=_reparse(
            fixture.bound.evaluated_dependency_projection_record
        ),
        current_dependency_projection_record=_reparse(
            fixture.bound.current_dependency_projection_record
        ),
        trusted_time_observation_record=_reparse(
            fixture.bound.trusted_time_observation_record
        ),
        invalidation_stream_checkpoint_record=_reparse(
            fixture.bound.invalidation_stream_checkpoint_record
        ),
        currency_proof_record=_reparse(fixture.bound.currency_proof_record),
    )

    assert reconstructed.structural_admissibility is True


def test_conditional_applicable_rejects_a_missing_predicate_proof():
    fixture = _fixture(conditional_applicable=True)
    attestation = fixture.bound.evidence_records[1]
    evaluation_payload = _payload(fixture.bound.evaluation_record)
    evaluation_payload.pop("predicate_proof_digest")
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:conditional-without-proof",
        payload=evaluation_payload,
    )
    currency_proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence-currency-proof:conditional-without-proof",
        payload={
            **_payload(fixture.bound.currency_proof_record),
            "evaluation_digest": evaluation.digest(),
        },
    )

    with pytest.raises(ValueError, match="requires one current predicate proof"):
        replace(
            fixture.bound,
            evidence_records=(attestation,),
            evaluation_record=evaluation,
            currency_proof_record=currency_proof,
        )


def test_conditional_applicable_rejects_a_false_or_unauthorized_proof():
    fixture = _fixture(conditional_applicable=True)
    original_proof, attestation = fixture.bound.evidence_records

    for suffix, changes, match in (
        ("false", {"is_applicable": False}, "must prove true"),
        ("outsider", {"actor_role": "outsider"}, "not authorized"),
    ):
        proof = ControlRecord.build(
            kind="predicate_proof",
            record_id=f"predicate-proof:conditional-{suffix}",
            payload={**_payload(original_proof), **changes},
        )
        evaluation = ControlRecord.build(
            kind="evaluation",
            record_id=f"evaluation:conditional-{suffix}",
            payload={
                **_payload(fixture.bound.evaluation_record),
                "predicate_proof_digest": proof.digest(),
            },
        )
        currency_proof = ControlRecord.build(
            kind="evidence_currency_proof",
            record_id=f"evidence-currency-proof:conditional-{suffix}",
            payload={
                **_payload(fixture.bound.currency_proof_record),
                "evaluation_digest": evaluation.digest(),
            },
        )

        with pytest.raises(ValueError, match=match):
            replace(
                fixture.bound,
                evidence_records=(proof, attestation),
                evaluation_record=evaluation,
                currency_proof_record=currency_proof,
            )


def test_conditional_predicate_proof_participates_in_currency_expiry():
    fixture = _fixture(conditional_applicable=True)
    original_proof, original_attestation = fixture.bound.evidence_records
    validity_policy = ControlRecord.build(
        kind="validity_policy",
        record_id="validity-policy:conditional-short-proof-lease",
        payload={
            **_payload(fixture.bound.validity_policy_record),
            "predicate_proof_max_age_seconds": 1,
        },
    )
    assignment = ControlRecord.build(
        kind="assignment",
        record_id="assignment:conditional-short-proof-lease",
        payload={
            **_payload(fixture.bound.assignment_record),
            "validity_policy_digest": validity_policy.digest(),
        },
    )
    attempt = ControlRecord.build(
        kind="attempt",
        record_id="attempt:conditional-short-proof-lease",
        payload={
            **_payload(fixture.bound.attempt_record),
            "assignment_digest": assignment.digest(),
        },
    )
    proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="predicate-proof:conditional-short-proof-lease",
        payload={
            **_payload(original_proof),
            "assignment_digest": assignment.digest(),
            "observed_at": "2026-08-12T09:13:31Z",
        },
    )
    attestation = ControlRecord.build(
        kind="attestation",
        record_id="attestation:conditional-short-proof-lease",
        payload={
            **_payload(original_attestation),
            "assignment_digest": assignment.digest(),
        },
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation:conditional-short-proof-lease",
        payload={
            **_payload(fixture.bound.evaluation_record),
            "assignment_digest": assignment.digest(),
            "attestation_digests": [attestation.digest()],
            "predicate_proof_digest": proof.digest(),
        },
    )
    currency_proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence-currency-proof:conditional-short-proof-lease",
        payload={
            **_payload(fixture.bound.currency_proof_record),
            "evaluation_digest": evaluation.digest(),
            "validity_policy_digest": validity_policy.digest(),
        },
    )

    with pytest.raises(ValueError, match="stale under its currency proof"):
        replace(
            fixture.bound,
            attempt_record=attempt,
            assignment_record=assignment,
            evidence_records=(proof, attestation),
            evaluation_record=evaluation,
            validity_policy_record=validity_policy,
            currency_proof_record=currency_proof,
        )


def test_gate_terminal_must_bind_the_exact_conditional_predicate_proof():
    fixture = _fixture(conditional_applicable=True)
    terminal_payload = _payload(fixture.attempt.terminal_record)
    terminal_payload.pop("predicate_proof_digest")
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="terminal:conditional-without-proof",
        payload=terminal_payload,
    )
    attempt = replace(fixture.attempt, terminal_record=terminal)
    attempts = (attempt, *fixture.cut.attempts[1:])
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:conditional-without-proof",
        payload={
            **_payload(fixture.cut.cut_record),
            "registration_set_digest": registration_set_digest(
                attempts, fixture.cut.operations
            ),
        },
    )
    cut = replace(fixture.cut, cut_record=cut_record, attempts=attempts)

    with pytest.raises(PromotionDenied) as exc_info:
        assess_promotion_cut(fixture.contract, cut)
    assert exc_info.value.code == "PROMOTION_EVIDENCE_BINDING_MISMATCH"


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
    attempts = (blocked_attempt, *fixture.cut.attempts[1:])
    evaluations = (bound, *fixture.cut.evaluations[1:])
    cut_record = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic-evidence-cut:blocked",
        payload={
            **_payload(fixture.cut.cut_record),
            "attempt_digests": [
                attempt.attempt_digest for attempt in attempts
            ],
            "registration_set_digest": registration_set_digest(
                attempts,
                fixture.cut.operations,
            ),
        },
    )
    cut = replace(
        fixture.cut,
        cut_record=cut_record,
        attempts=attempts,
        evaluations=evaluations,
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
            "verified_at": "2026-08-12T09:13:39Z",
        },
    )

    with pytest.raises(ValueError, match="inclusion edge verification"):
        replace(fixture.bound, inclusion_edge_record=early_edge)


def test_complete_semantics_backed_by_fake_authority_remain_nonpromotional():
    fixture = _fixture()
    authority = InMemoryAuthority()
    authority.append_record(fixture.attempt.attempt_digest, kind="attempt")
    request, approval = _acceptance_material(fixture)

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            authority.evidence_view(),
            acceptance_request=request,
            approval=approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T09:14:30Z",
        )

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"


def test_exact_authority_proof_still_cannot_promote_without_production_authority():
    fixture = _fixture()
    operation = _registered_operation(fixture)
    cut = _cut_with_operation(fixture, operation)
    authority = RecordingPromotionAuthority()
    request, approval = _acceptance_material(fixture, cut)

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(
            fixture.contract,
            cut,
            fixture.contract.predecessor_checkpoint,
            authority,
            acceptance_request=request,
            approval=approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture, cut),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T09:14:30Z",
        )

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"
    assert authority.challenge is None


def test_fake_proof_shape_cannot_bypass_the_structural_predecessor_boundary():
    fixture = _fixture()
    authority = RecordingPromotionAuthority(
        proof_changes={"fork_proof_digest": digest("f")}
    )
    request, approval = _acceptance_material(fixture)

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(
            fixture.contract,
            fixture.cut,
            fixture.contract.predecessor_checkpoint,
            authority,
            acceptance_request=request,
            approval=approval,
            final_service_anchor_receipt=_final_service_anchor_receipt(fixture),
            checkpoint_id="accepted-w0",
            established_at="2026-08-12T10:13:00Z",
        )

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"
    assert authority.challenge is None


@dataclass(frozen=True)
class CompositeFixture:
    change_set: CompositeChangeSet
    old_manifest: CompositeAuthorityManifest
    candidate_manifest: CompositeAuthorityManifest
    authorization_record: ControlRecord
    separation_policy_record: ControlRecord
    coordinator_identity_record: ControlRecord
    receipts: tuple[ControlRecord, ...]
    approvals: tuple[ControlRecord, ...]


class CompositeManifestWithoutValidation(CompositeAuthorityManifest):
    def __post_init__(self) -> None:
        pass


class CompositeChangeSetWithoutValidation(CompositeChangeSet):
    def __post_init__(self) -> None:
        pass


class CompositeCheckpointWithoutValidation(CompositeAuthorityCheckpoint):
    def __post_init__(self) -> None:
        pass


def _copy_as_unchecked_composite_subclass(
    value: object,
    subclass: type[object],
) -> object:
    unchecked = object.__new__(subclass)
    for item in fields(value):
        object.__setattr__(unchecked, item.name, getattr(value, item.name))
    return unchecked


def _composite_manifest(
    manifest_id: str,
    *,
    requirements: ControlRecord,
    contract: ControlRecord,
    inventory: ControlRecord,
    accepted: ControlRecord,
    active: ControlRecord,
    rollback: ControlRecord,
    rollback_registry: ControlRecord,
    selected_rollback: ControlRecord,
    recovery_policy: ControlRecord,
    recovery_authorization: ControlRecord,
    recovery_separation: ControlRecord,
    recovery_root: ControlRecord,
    authorization: ControlRecord,
    fallback: ControlRecord,
    roster: ControlRecord,
    quorum: ControlRecord,
    witnesses: tuple[ControlRecord, ...],
) -> CompositeAuthorityManifest:
    record = ControlRecord.build(
        kind="composite_authority",
        record_id=f"composite-authority:{manifest_id}",
        payload={
            "accepted_generation_digest": accepted.digest(),
            "active_generation_digest": active.digest(),
            "authorization_policy_digest": authorization.digest(),
            "contract_digest": contract.digest(),
            "fallback_digest": fallback.digest(),
            "inventory_digest": inventory.digest(),
            "manifest_id": manifest_id,
            "quorum_policy_digest": quorum.digest(),
            "recovery_policy_digest": recovery_policy.digest(),
            "requirements_digest": requirements.digest(),
            "rollback_generation_digest": rollback.digest(),
            "rollback_registry_digest": rollback_registry.digest(),
            "witness_roster_digest": roster.digest(),
        },
    )
    return CompositeAuthorityManifest.materialize(
        manifest_record=record,
        requirements_record=requirements,
        contract_record=contract,
        inventory_record=inventory,
        accepted_generation_record=accepted,
        active_generation_record=active,
        rollback_generation_record=rollback,
        rollback_registry_record=rollback_registry,
        selected_rollback_record=selected_rollback,
        recovery_policy_record=recovery_policy,
        recovery_authorization_record=recovery_authorization,
        recovery_separation_policy_record=recovery_separation,
        recovery_root_identity_record=recovery_root,
        authorization_policy_record=authorization,
        fallback_record=fallback,
        witness_roster_record=roster,
        quorum_policy_record=quorum,
        witness_identity_records=witnesses,
    )


def _rebuild_composite_manifest(
    manifest: CompositeAuthorityManifest,
) -> CompositeAuthorityManifest:
    return CompositeAuthorityManifest.materialize(
        manifest_record=_reparse(manifest.manifest_record),
        requirements_record=_reparse(manifest.requirements_record),
        contract_record=_reparse(manifest.contract_record),
        inventory_record=_reparse(manifest.inventory_record),
        accepted_generation_record=_reparse(manifest.accepted_generation_record),
        active_generation_record=_reparse(manifest.active_generation_record),
        rollback_generation_record=_reparse(manifest.rollback_generation_record),
        rollback_registry_record=_reparse(manifest.rollback_registry_record),
        selected_rollback_record=_reparse(manifest.selected_rollback_record),
        recovery_policy_record=_reparse(manifest.recovery_policy_record),
        recovery_authorization_record=_reparse(
            manifest.recovery_authorization_record
        ),
        recovery_separation_policy_record=_reparse(
            manifest.recovery_separation_policy_record
        ),
        recovery_root_identity_record=_reparse(
            manifest.recovery_root_identity_record
        ),
        authorization_policy_record=_reparse(
            manifest.authorization_policy_record
        ),
        fallback_record=_reparse(manifest.fallback_record),
        witness_roster_record=_reparse(manifest.witness_roster_record),
        quorum_policy_record=_reparse(manifest.quorum_policy_record),
        witness_identity_records=tuple(
            _reparse(identity) for identity in manifest.witness_identity_records
        ),
    )


def _composite_fixture(
    *,
    joint: bool = False,
    transition: str | None = None,
    generation_class: str = "c",
    inconsistent_old_pointers: bool = False,
    activation_acceptance_collapse: bool = False,
    standalone_rollback_drift: bool = False,
) -> CompositeFixture:
    transition = transition or ("control_update" if joint else "activation")
    if joint and transition != "control_update":
        raise ValueError("joint fixture models a control update")
    coordinator = _identity(
        "identity:composite-coordinator",
        "composite-coordinator",
        "principal",
        "1",
        roles=["coordinator"],
    )
    witness_pool = tuple(
        sorted(
            (
                _identity(
                    f"identity:composite-witness-{index}",
                    f"composite-witness-{index}",
                    "principal",
                    str(index + 1),
                    roles=["witness"],
                )
                for index in range(4)
            ),
            key=lambda identity: identity.digest(),
        )
    )
    old_witnesses = witness_pool[:3]
    candidate_witnesses = witness_pool[1:] if joint else old_witnesses
    separation = ControlRecord.build(
        kind="separation_policy",
        record_id="separation-policy:composite",
        payload={
            "forbidden_actor_identity_digests": [],
            "policy_id": "composite-transition",
            "required_actor_roles": [],
        },
    )
    authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:composite",
        payload={
            "action": "transition_composite_authority",
            "allowed_actor_identity_digests": sorted(
                {
                    coordinator.digest(),
                    *(identity.digest() for identity in witness_pool),
                }
            ),
            "allowed_actor_roles": ["coordinator", "witness"],
            "approver_roles": ["witness"],
            "policy_id": "composite-transition",
            "recovery_root_digest": coordinator.digest(),
            "separation_policy_digest": separation.digest(),
            "subject_kind": "composite_change_set",
            "validity_policy_digest": digest("1"),
        },
    )
    recovery_authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization:composite-recovery",
        payload={
            **_payload(authorization),
            "action": "reinstate_composite_authority",
            "allowed_actor_identity_digests": [coordinator.digest()],
            "allowed_actor_roles": ["coordinator"],
            "approver_roles": ["coordinator"],
            "policy_id": "composite-recovery",
        },
    )
    requirements = ControlRecord.build(
        kind="requirements",
        record_id="requirements:composite",
        payload={
            "approval_digest": digest("2"),
            "effective_at": "2026-08-12T11:00:00Z",
            "requirement_digests": [digest("3")],
            "requirements_definition_digest": digest("4"),
            "requirements_id": "composite-requirements",
            "requirements_version": 1,
        },
    )
    accepted_base = _generation(
        "generation:composite-accepted",
        "composite-accepted",
        "9",
        generation_class=generation_class,
    )
    activated = _generation(
        "generation:composite-candidate-active",
        "composite-candidate-active",
        "c",
        generation_class=generation_class,
    )
    if transition == "activation":
        accepted = active = rollback = accepted_base
        candidate_accepted = (
            activated if activation_acceptance_collapse else accepted_base
        )
        candidate_active = activated
        candidate_rollback = accepted_base
    elif transition == "acceptance":
        accepted = accepted_base
        active = activated
        rollback = (
            _generation(
                "generation:composite-unrelated-rollback",
                "composite-unrelated-rollback",
                "d",
                generation_class=generation_class,
            )
            if inconsistent_old_pointers
            else accepted_base
        )
        candidate_accepted = activated
        candidate_active = activated
        candidate_rollback = accepted_base
    elif transition == "control_update":
        accepted = active = rollback = accepted_base
        candidate_accepted = candidate_active = accepted_base
        candidate_rollback = (
            activated if standalone_rollback_drift else accepted_base
        )
    else:
        raise ValueError(f"unsupported composite fixture transition: {transition}")
    contract = ControlRecord.build(
        kind="validation_contract",
        record_id="validation-contract:composite",
        payload={
            "approval_digest": digest("5"),
            "assignments_digest": digest("6"),
            "authorization_policy_digest": authorization.digest(),
            "contract_id": "composite-validation",
            "max_live_attempt_seconds": 3600,
            "max_suite_seconds": 28800,
            "operation_requirement_set_digest": digest("7"),
            "requirements_digest": requirements.digest(),
        },
    )

    def inventory(name: str, generation: ControlRecord) -> ControlRecord:
        return ControlRecord.build(
            kind="installed_inventory",
            record_id=f"installed-inventory:{name}",
            payload={
                "authorization_digest": authorization.digest(),
                "configuration_digest": digest("8"),
                "driver_device_digest": digest("9"),
                "generation_digest": generation.digest(),
                "inventory_id": name,
                "model_identity_digests": [digest("a")],
                "observed_at": "2026-08-12T11:00:00Z",
                "observer_identity_digest": coordinator.digest(),
                "package_manifest_digest": digest("b"),
            },
        )

    old_inventory = inventory("composite-old", active)
    candidate_inventory = (
        inventory("composite-candidate", candidate_active)
        if transition == "activation"
        else old_inventory
    )
    def selected_rollback(
        name: str,
        *,
        origin: ControlRecord,
        destination: ControlRecord,
    ) -> ControlRecord:
        return ControlRecord.build(
            kind="rollback",
            record_id=f"rollback:composite:{name}",
            payload={
                "destination_generation_digest": destination.digest(),
                "generation_binding": {
                    "generation_digest": origin.digest(),
                    "mode": "required_generation",
                },
                "operation_digest": digest("d"),
                "origin_generation_digest": origin.digest(),
                "rollback_id": f"composite-{name}",
                "target_digest": coordinator.digest(),
                "target_generation_digest": destination.digest(),
                "target_projection_digest": digest("e"),
                "target_protected_state_digest": digest("f"),
                "target_state_digest": digest("0"),
                "terminal_gate_digest": digest("1"),
            },
        )

    def rollback_registry(
        name: str,
        selected: ControlRecord,
    ) -> ControlRecord:
        return ControlRecord.build(
            kind="rollback_registry",
            record_id=f"rollback-registry:composite:{name}",
            payload={
                "authorization_digest": authorization.digest(),
                "established_at": "2026-08-12T11:00:00Z",
                "registry_head_digest": digest("c"),
                "registry_id": f"composite-rollbacks-{name}",
                "rollback_digests": [selected.digest()],
                "selected_rollback_digest": selected.digest(),
            },
        )

    old_rollback_origin = (
        active if active.digest() != rollback.digest() else activated
    )
    candidate_rollback_origin = (
        candidate_active
        if candidate_active.digest() != candidate_rollback.digest()
        else activated
    )
    old_selected_rollback = selected_rollback(
        "old",
        origin=old_rollback_origin,
        destination=rollback,
    )
    old_rollback_registry = rollback_registry("old", old_selected_rollback)
    if (
        candidate_rollback_origin.digest() == old_rollback_origin.digest()
        and candidate_rollback.digest() == rollback.digest()
    ):
        candidate_selected_rollback = old_selected_rollback
        candidate_rollback_registry = old_rollback_registry
    else:
        candidate_selected_rollback = selected_rollback(
            "candidate",
            origin=candidate_rollback_origin,
            destination=candidate_rollback,
        )
        candidate_rollback_registry = rollback_registry(
            "candidate",
            candidate_selected_rollback,
        )
    recovery_policy = ControlRecord.build(
        kind="recovery_policy",
        record_id="recovery-policy:composite",
        payload={
            "authorization_digest": recovery_authorization.digest(),
            "policy_id": "composite-recovery",
            "recovery_contract_digests": [digest("e")],
            "recovery_owner_roles": ["coordinator"],
            "recovery_root_digest": coordinator.digest(),
            "separation_policy_digest": separation.digest(),
            "validity_policy_digest": digest("f"),
        },
    )
    old_fallback = ControlRecord.build(
        kind="composite_fallback_reference",
        record_id="composite-fallback-reference:old",
        payload={
            "authorization_digest": authorization.digest(),
            "committed_checkpoint_digest": digest("1"),
            "reference_id": "composite-old-fallback",
            "referenced_manifest_digest": digest("2"),
        },
    )

    def roster(name: str, identities: tuple[ControlRecord, ...]) -> ControlRecord:
        return ControlRecord.build(
            kind="witness_roster",
            record_id=f"witness-roster:{name}",
            payload={
                "roster_id": name,
                "witness_identity_digests": [
                    identity.digest() for identity in identities
                ],
            },
        )

    def quorum(name: str, roster_record: ControlRecord) -> ControlRecord:
        return ControlRecord.build(
            kind="quorum_policy",
            record_id=f"quorum-policy:{name}",
            payload={
                "policy_id": name,
                "threshold": 2,
                "witness_roster_digest": roster_record.digest(),
            },
        )

    old_roster = roster("composite-old", old_witnesses)
    old_quorum = quorum("composite-old", old_roster)
    candidate_roster = (
        roster("composite-candidate", candidate_witnesses)
        if joint
        else old_roster
    )
    candidate_quorum = (
        quorum("composite-candidate", candidate_roster)
        if joint
        else old_quorum
    )
    old_manifest = _composite_manifest(
        "composite-old",
        requirements=requirements,
        contract=contract,
        inventory=old_inventory,
        accepted=accepted,
        active=active,
        rollback=rollback,
        rollback_registry=old_rollback_registry,
        selected_rollback=old_selected_rollback,
        recovery_policy=recovery_policy,
        recovery_authorization=recovery_authorization,
        recovery_separation=separation,
        recovery_root=coordinator,
        authorization=authorization,
        fallback=old_fallback,
        roster=old_roster,
        quorum=old_quorum,
        witnesses=old_witnesses,
    )
    candidate_manifest = _composite_manifest(
        "composite-candidate",
        requirements=requirements,
        contract=contract,
        inventory=candidate_inventory,
        accepted=candidate_accepted,
        active=candidate_active,
        rollback=candidate_rollback,
        rollback_registry=candidate_rollback_registry,
        selected_rollback=candidate_selected_rollback,
        recovery_policy=recovery_policy,
        recovery_authorization=recovery_authorization,
        recovery_separation=separation,
        recovery_root=coordinator,
        authorization=authorization,
        fallback=old_manifest.manifest_record,
        roster=candidate_roster,
        quorum=candidate_quorum,
        witnesses=candidate_witnesses,
    )
    composite_projection_fields = {
        "accepted_generation_digest": "accepted_generation",
        "active_generation_digest": "active_generation",
        "authorization_policy_digest": "authorization_policy",
        "contract_digest": "contract",
        "fallback_digest": "fallback",
        "inventory_digest": "inventory",
        "quorum_policy_digest": "quorum_policy",
        "recovery_policy_digest": "recovery_policy",
        "requirements_digest": "requirements",
        "rollback_generation_digest": "rollback_generation",
        "rollback_registry_digest": "rollback_registry",
        "witness_roster_digest": "witness_roster",
    }
    changed_fields = sorted(
        projection
        for field, projection in composite_projection_fields.items()
        if old_manifest.manifest_record.payload[field]
        != candidate_manifest.manifest_record.payload[field]
    )
    change_set_record = ControlRecord.build(
        kind="composite_change_set",
        record_id=f"composite-change-set:{'joint' if joint else 'existing'}",
        payload={
            "authorization_action": "transition_composite_authority",
            "authorization_digest": authorization.digest(),
            "candidate_manifest_digest": candidate_manifest.manifest_digest,
            "change_set_id": f"composite-{transition}",
            "changed_fields": changed_fields,
            "coordinator_identity_digest": coordinator.digest(),
            "generation_binding": (
                {"mode": "no_generation"}
                if transition == "control_update"
                else {
                    "generation_digest": (
                        candidate_active.digest()
                        if transition == "activation"
                        else candidate_accepted.digest()
                    ),
                    "mode": "required_generation",
                }
            ),
            "old_manifest_digest": old_manifest.manifest_digest,
            "quorum_mode": "joint_consensus" if joint else "existing",
            "rollback_manifest_digest": old_manifest.manifest_digest,
            "terminal_rule": "conjunctive",
            "transition_mode": transition,
        },
    )

    def approval(identity: ControlRecord, name: str) -> ControlRecord:
        return ControlRecord.build(
            kind="approval",
            record_id=f"approval:composite:{name}",
            payload={
                "action": "transition_composite_authority",
                "actor_identity_digest": identity.digest(),
                "actor_role": "witness",
                "authorization_digest": authorization.digest(),
                "decided_at": "2026-08-12T11:01:00Z",
                "decision": "approved",
                "subject_digest": change_set_record.digest(),
            },
        )

    existing_approvals = (
        approval(old_witnesses[0], "existing-one"),
        approval(old_witnesses[1], "shared"),
    )
    candidate_approvals = (
        (
            existing_approvals[1],
            approval(candidate_witnesses[-1], "candidate-new"),
        )
        if joint
        else ()
    )

    def receipt(
        side: str,
        manifest: CompositeAuthorityManifest,
        approvals: tuple[ControlRecord, ...],
    ) -> ControlRecord:
        return ControlRecord.build(
            kind="quorum_receipt",
            record_id=f"quorum-receipt:composite:{side}",
            payload={
                "approval_digests": sorted(item.digest() for item in approvals),
                "approved_at": "2026-08-12T11:02:00Z",
                "authorization_digest": authorization.digest(),
                "change_set_digest": change_set_record.digest(),
                "quorum_policy_digest": manifest.quorum_policy_record.digest(),
                "receipt_id": f"composite-{side}",
                "side": side,
                "witness_roster_digest": manifest.witness_roster_record.digest(),
            },
        )

    receipts = (
        receipt("existing", old_manifest, existing_approvals),
        *(
            (receipt("candidate", candidate_manifest, candidate_approvals),)
            if joint
            else ()
        ),
    )
    approvals = tuple(
        {
            item.digest(): item
            for item in (*existing_approvals, *candidate_approvals)
        }.values()
    )
    change_set = CompositeChangeSet(
        change_set_record=change_set_record,
        old_manifest=old_manifest,
        candidate_manifest=candidate_manifest,
        rollback_manifest=old_manifest,
        authorization_record=authorization,
        separation_policy_record=separation,
        coordinator_identity_record=coordinator,
        quorum_receipt_records=receipts,
        approval_records=approvals,
    )
    return CompositeFixture(
        change_set=change_set,
        old_manifest=old_manifest,
        candidate_manifest=candidate_manifest,
        authorization_record=authorization,
        separation_policy_record=separation,
        coordinator_identity_record=coordinator,
        receipts=receipts,
        approvals=approvals,
    )


def test_composite_manifest_constructor_requires_all_exact_material():
    with pytest.raises(TypeError, match="materialize"):
        CompositeAuthorityManifest()


def test_composite_manifest_materialize_rejects_an_inherited_factory() -> None:
    manifest = _composite_fixture().old_manifest
    arguments = {
        item.name: getattr(manifest, item.name)
        for item in fields(CompositeAuthorityManifest)
    }

    with pytest.raises(TypeError, match="exact CompositeAuthorityManifest class"):
        CompositeManifestWithoutValidation.materialize(**arguments)


def test_composite_manifest_materializes_its_exact_selected_rollback() -> None:
    manifest = _composite_fixture().old_manifest

    assert (
        manifest.active_generation_record.digest()
        == manifest.rollback_generation_record.digest()
    )
    assert manifest.selected_rollback_record.payload[
        "origin_generation_digest"
    ] != manifest.active_generation_record.digest()
    assert manifest.selected_rollback_record.digest() == (
        manifest.rollback_registry_record.payload["selected_rollback_digest"]
    )
    assert manifest.selected_rollback_record.payload[
        "destination_generation_digest"
    ] == manifest.rollback_generation_record.digest()
    assert manifest.selected_rollback_record.payload[
        "target_generation_digest"
    ] == manifest.rollback_generation_record.digest()


def test_composite_manifest_materializes_its_exact_divergent_rollback() -> None:
    manifest = _rebuild_composite_manifest(
        _composite_fixture(transition="acceptance").old_manifest
    )
    active_digest = manifest.active_generation_record.digest()
    rollback_digest = manifest.rollback_generation_record.digest()

    assert active_digest != rollback_digest
    assert (
        manifest.selected_rollback_record.payload["origin_generation_digest"]
        == active_digest
    )
    assert manifest.selected_rollback_record.payload["generation_binding"] == {
        "generation_digest": active_digest,
        "mode": "required_generation",
    }
    assert manifest.selected_rollback_record.payload[
        "destination_generation_digest"
    ] == rollback_digest
    assert manifest.selected_rollback_record.payload[
        "target_generation_digest"
    ] == rollback_digest


def test_composite_manifest_rejects_missing_selected_rollback_material() -> None:
    manifest = _composite_fixture().old_manifest
    arguments = {
        item.name: getattr(manifest, item.name)
        for item in fields(CompositeAuthorityManifest)
        if item.name != "selected_rollback_record"
    }

    with pytest.raises(TypeError, match="selected_rollback_record"):
        CompositeAuthorityManifest.materialize(**arguments)


def test_composite_manifest_rejects_an_unselected_rollback_member() -> None:
    manifest = _composite_fixture().old_manifest
    unselected = ControlRecord.build(
        kind="rollback",
        record_id="rollback:composite:unselected",
        payload=_payload(manifest.selected_rollback_record),
    )
    arguments = {
        item.name: getattr(manifest, item.name)
        for item in fields(CompositeAuthorityManifest)
    }
    arguments["selected_rollback_record"] = unselected

    with pytest.raises(ValueError, match="exact selected registry member"):
        CompositeAuthorityManifest.materialize(**arguments)


def test_composite_manifest_rejects_a_selected_rollback_to_another_generation() -> None:
    manifest = _composite_fixture(transition="acceptance").old_manifest
    wrong_destination = manifest.active_generation_record
    wrong_origin = manifest.rollback_generation_record
    wrong_selected = ControlRecord.build(
        kind="rollback",
        record_id="rollback:composite:wrong-destination",
        payload={
            **_payload(manifest.selected_rollback_record),
            "destination_generation_digest": wrong_destination.digest(),
            "generation_binding": {
                "generation_digest": wrong_origin.digest(),
                "mode": "required_generation",
            },
            "origin_generation_digest": wrong_origin.digest(),
            "rollback_id": "composite-wrong-destination",
            "target_generation_digest": wrong_destination.digest(),
        },
    )
    wrong_registry = ControlRecord.build(
        kind="rollback_registry",
        record_id="rollback-registry:composite:wrong-destination",
        payload={
            **_payload(manifest.rollback_registry_record),
            "registry_id": "composite-rollbacks-wrong-destination",
            "rollback_digests": [wrong_selected.digest()],
            "selected_rollback_digest": wrong_selected.digest(),
        },
    )
    wrong_manifest_record = ControlRecord.build(
        kind="composite_authority",
        record_id="composite-authority:wrong-rollback-destination",
        payload={
            **_payload(manifest.manifest_record),
            "manifest_id": "wrong-rollback-destination",
            "rollback_registry_digest": wrong_registry.digest(),
        },
    )
    arguments = {
        item.name: getattr(manifest, item.name)
        for item in fields(CompositeAuthorityManifest)
    }
    arguments.update(
        manifest_record=wrong_manifest_record,
        rollback_registry_record=wrong_registry,
        selected_rollback_record=wrong_selected,
    )

    with pytest.raises(ValueError, match="exact rollback generation"):
        CompositeAuthorityManifest.materialize(**arguments)


def test_composite_manifest_rejects_a_foreign_divergent_rollback_origin() -> None:
    manifest = _composite_fixture(transition="acceptance").old_manifest
    foreign_origin = _generation(
        "generation:composite-foreign-rollback-origin",
        "composite-foreign-rollback-origin",
        "e",
    )
    wrong_selected = ControlRecord.build(
        kind="rollback",
        record_id="rollback:composite:foreign-origin",
        payload={
            **_payload(manifest.selected_rollback_record),
            "generation_binding": {
                "generation_digest": foreign_origin.digest(),
                "mode": "required_generation",
            },
            "origin_generation_digest": foreign_origin.digest(),
            "rollback_id": "composite-foreign-origin",
        },
    )
    wrong_registry = ControlRecord.build(
        kind="rollback_registry",
        record_id="rollback-registry:composite:foreign-origin",
        payload={
            **_payload(manifest.rollback_registry_record),
            "registry_id": "composite-rollbacks-foreign-origin",
            "rollback_digests": [wrong_selected.digest()],
            "selected_rollback_digest": wrong_selected.digest(),
        },
    )
    wrong_manifest_record = ControlRecord.build(
        kind="composite_authority",
        record_id="composite-authority:foreign-rollback-origin",
        payload={
            **_payload(manifest.manifest_record),
            "manifest_id": "foreign-rollback-origin",
            "rollback_registry_digest": wrong_registry.digest(),
        },
    )
    arguments = {
        item.name: getattr(manifest, item.name)
        for item in fields(CompositeAuthorityManifest)
    }
    arguments.update(
        manifest_record=wrong_manifest_record,
        rollback_registry_record=wrong_registry,
        selected_rollback_record=wrong_selected,
    )

    with pytest.raises(ValueError, match="exact active generation"):
        CompositeAuthorityManifest.materialize(**arguments)


@pytest.mark.parametrize("joint", [False, True])
def test_composite_transition_derives_its_exact_diff_binding_and_quorum(joint):
    fixture = _composite_fixture(joint=joint)

    assert fixture.change_set.change_set_digest == (
        fixture.change_set.change_set_record.digest()
    )
    assert fixture.change_set.promotional is False
    assert fixture.old_manifest.promotional is False


def test_composite_acceptance_moves_only_the_accepted_pointer_to_active():
    fixture = _composite_fixture(transition="acceptance")

    assert fixture.change_set.change_set_record.payload["transition_mode"] == (
        "acceptance"
    )
    assert (
        fixture.candidate_manifest.accepted_generation_record.digest()
        == fixture.old_manifest.active_generation_record.digest()
    )


def test_composite_transition_rejects_f_or_inconsistent_generation_pointers():
    with pytest.raises(ValueError, match="exact C generations"):
        _composite_fixture(generation_class="f")

    with pytest.raises(ValueError, match="pointers are inconsistent"):
        _composite_fixture(
            transition="acceptance",
            inconsistent_old_pointers=True,
        )


def test_composite_transition_rejects_collapsed_or_standalone_pointer_changes():
    with pytest.raises(
        ValueError,
        match="activation .*preserv.* accepted",
    ):
        _composite_fixture(activation_acceptance_collapse=True)

    with pytest.raises(ValueError, match="control update cannot change"):
        _composite_fixture(
            transition="control_update",
            standalone_rollback_drift=True,
        )


def test_composite_transition_accepts_a_reconstructed_canonical_graph():
    fixture = _composite_fixture(joint=True)

    reconstructed = CompositeChangeSet(
        change_set_record=_reparse(fixture.change_set.change_set_record),
        old_manifest=_rebuild_composite_manifest(fixture.old_manifest),
        candidate_manifest=_rebuild_composite_manifest(
            fixture.candidate_manifest
        ),
        rollback_manifest=_rebuild_composite_manifest(fixture.old_manifest),
        authorization_record=_reparse(fixture.authorization_record),
        separation_policy_record=_reparse(fixture.separation_policy_record),
        coordinator_identity_record=_reparse(
            fixture.coordinator_identity_record
        ),
        quorum_receipt_records=tuple(
            _reparse(receipt) for receipt in fixture.receipts
        ),
        approval_records=tuple(
            _reparse(approval) for approval in fixture.approvals
        ),
    )

    assert reconstructed.change_set_digest == fixture.change_set.change_set_digest


def test_composite_change_set_rejects_a_manifest_subclass() -> None:
    fixture = _composite_fixture()
    unchecked = _copy_as_unchecked_composite_subclass(
        fixture.old_manifest,
        CompositeManifestWithoutValidation,
    )

    with pytest.raises(TypeError, match="old_manifest must be an exact"):
        replace(
            fixture.change_set,
            old_manifest=unchecked,
            rollback_manifest=unchecked,
        )


@pytest.mark.parametrize(
    ("field", "expected_kind"),
    [
        ("contract_record", "validation_contract"),
        ("inventory_record", "installed_inventory"),
        ("rollback_registry_record", "rollback_registry"),
        ("selected_rollback_record", "rollback"),
        ("recovery_policy_record", "recovery_policy"),
        ("fallback_record", "composite authority reference"),
    ],
)
def test_composite_manifest_rejects_untyped_projection_material(
    field,
    expected_kind,
):
    fixture = _composite_fixture()
    old = fixture.old_manifest
    wrong = _identity(
        f"identity:untyped-{field}",
        f"untyped-{field}",
        "subject",
        "f",
    )
    arguments = {
        item.name: getattr(old, item.name)
        for item in fields(CompositeAuthorityManifest)
    }
    arguments[field] = wrong

    with pytest.raises(ValueError, match=f"canonical {expected_kind}"):
        CompositeAuthorityManifest.materialize(**arguments)


def test_composite_manifest_rejects_a_same_root_record_with_a_changed_child_graph():
    fixture = _composite_fixture()
    old = fixture.old_manifest
    wrong_fallback = _identity(
        "identity:wrong-composite-fallback",
        "wrong-composite-fallback",
        "subject",
        "f",
    )

    with pytest.raises(ValueError, match="canonical composite authority reference"):
        CompositeAuthorityManifest.materialize(
            manifest_record=_reparse(old.manifest_record),
            requirements_record=old.requirements_record,
            contract_record=old.contract_record,
            inventory_record=old.inventory_record,
            accepted_generation_record=old.accepted_generation_record,
            active_generation_record=old.active_generation_record,
            rollback_generation_record=old.rollback_generation_record,
            rollback_registry_record=old.rollback_registry_record,
            selected_rollback_record=old.selected_rollback_record,
            recovery_policy_record=old.recovery_policy_record,
            recovery_authorization_record=old.recovery_authorization_record,
            recovery_separation_policy_record=(
                old.recovery_separation_policy_record
            ),
            recovery_root_identity_record=old.recovery_root_identity_record,
            authorization_policy_record=old.authorization_policy_record,
            fallback_record=wrong_fallback,
            witness_roster_record=old.witness_roster_record,
            quorum_policy_record=old.quorum_policy_record,
            witness_identity_records=old.witness_identity_records,
        )


@pytest.mark.parametrize(
    "change",
    [
        {
            "changed_fields": ["active_generation", "fallback"],
        },
        {
            "generation_binding": {
                "generation_digest": digest("f"),
                "mode": "required_generation",
            }
        },
    ],
)
def test_composite_transition_rejects_caller_selected_diff_or_generation_binding(
    change,
):
    fixture = _composite_fixture()
    record = ControlRecord.build(
        kind="composite_change_set",
        record_id="composite-change-set:caller-selected",
        payload={**_payload(fixture.change_set.change_set_record), **change},
    )

    with pytest.raises(ValueError, match="derived diff"):
        replace(fixture.change_set, change_set_record=record)


def test_composite_quorum_rejects_a_threshold_shortfall():
    fixture = _composite_fixture()
    one_approval = fixture.approvals[:1]
    receipt = ControlRecord.build(
        kind="quorum_receipt",
        record_id="quorum-receipt:threshold-shortfall",
        payload={
            **_payload(fixture.receipts[0]),
            "approval_digests": [one_approval[0].digest()],
        },
    )

    with pytest.raises(ValueError, match="threshold"):
        replace(
            fixture.change_set,
            quorum_receipt_records=(receipt,),
            approval_records=one_approval,
        )


def _committed_composite_checkpoint(
    fixture: CompositeFixture,
) -> CompositeAuthorityCheckpoint:
    manifest = fixture.candidate_manifest
    receipts = fixture.receipts
    register = ControlRecord.build(
        kind="authority_register",
        record_id="authority-register:composite-committed",
        payload={
            "observed_at": "2026-08-12T11:03:00Z",
            "quorum_receipt_digests": [
                receipt.digest() for receipt in receipts
            ],
            "register_head_digest": digest("3"),
            "register_id": "composite-register",
            "selected_manifest_digest": manifest.manifest_digest,
            "sequence": 7,
            "status": "valid",
            "witness_roster_digest": manifest.witness_roster_record.digest(),
        },
    )
    payload = {
        "authorization_digest": fixture.authorization_record.digest(),
        "change_set_digest": fixture.change_set.change_set_digest,
        "checkpoint_id": "composite-committed",
        "committed_at": "2026-08-12T11:04:00Z",
        "quorum_receipt_digests": [receipt.digest() for receipt in receipts],
        "register_head_digest": register.payload["register_head_digest"],
        "register_id": register.payload["register_id"],
        "register_observation_digest": register.digest(),
        "register_sequence": register.payload["sequence"],
        "selected_manifest_digest": manifest.manifest_digest,
        "signer_identity_digest": fixture.coordinator_identity_record.digest(),
    }
    record_id = "composite-authority-checkpoint:committed"
    record = ControlRecord.build(
        kind="composite_authority_checkpoint",
        record_id=record_id,
        payload=payload,
        signature={
            "algorithm": "ed25519",
            "signed_digest": ControlRecord.signing_digest(
                kind="composite_authority_checkpoint",
                record_id=record_id,
                payload=payload,
            ),
            "signer_identity_digest": fixture.coordinator_identity_record.digest(),
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        },
    )
    return CompositeAuthorityCheckpoint(
        checkpoint_record=_reparse(record),
        change_set=fixture.change_set,
        manifest=_rebuild_composite_manifest(manifest),
        register_observation_record=_reparse(register),
        quorum_receipt_records=tuple(_reparse(receipt) for receipt in receipts),
        signer_identity_record=_reparse(fixture.coordinator_identity_record),
        authorization_record=_reparse(fixture.authorization_record),
    )


def test_composite_checkpoint_rejects_subclassed_graph_wrappers() -> None:
    fixture = _composite_fixture()
    checkpoint = _committed_composite_checkpoint(fixture)
    unchecked_change_set = _copy_as_unchecked_composite_subclass(
        checkpoint.change_set,
        CompositeChangeSetWithoutValidation,
    )
    unchecked_manifest = _copy_as_unchecked_composite_subclass(
        checkpoint.manifest,
        CompositeManifestWithoutValidation,
    )

    with pytest.raises(TypeError, match="change_set must be an exact"):
        replace(checkpoint, change_set=unchecked_change_set)
    with pytest.raises(TypeError, match="manifest must be an exact"):
        replace(checkpoint, manifest=unchecked_manifest)


@pytest.mark.parametrize("status", ["absent", "corrupt"])
def test_composite_register_reinstatement_restores_only_the_exact_prior_manifest(
    status,
):
    fixture = _composite_fixture()
    checkpoint = _committed_composite_checkpoint(fixture)
    prior = checkpoint.manifest
    authorization = prior.recovery_authorization_record
    separation = prior.recovery_separation_policy_record
    coordinator = prior.recovery_root_identity_record
    register = ControlRecord.build(
        kind="authority_register",
        record_id=f"authority-register:{status}",
        payload={
            "observed_at": "2026-08-12T11:05:00Z",
            "quorum_receipt_digests": [],
            "register_head_digest": digest("4"),
            "register_id": "composite-register",
            "sequence": 1,
            "status": status,
            "witness_roster_digest": prior.witness_roster_record.digest(),
        },
    )
    record = ControlRecord.build(
        kind="composite_change_set",
        record_id=f"composite-register-reinstatement:{status}",
        payload={
            "authorization_action": "reinstate_composite_authority",
            "authorization_digest": authorization.digest(),
            "candidate_manifest_digest": prior.manifest_digest,
            "change_set_id": f"composite-reinstatement-{status}",
            "changed_fields": [],
            "coordinator_identity_digest": coordinator.digest(),
            "current_authority_register_observation_digest": register.digest(),
            "generation_binding": {"mode": "no_generation"},
            "old_manifest_digest": prior.manifest_digest,
            "prior_committed_checkpoint_digest": checkpoint.checkpoint_digest,
            "quorum_mode": "recovery_root",
            "rollback_manifest_digest": prior.manifest_digest,
            "terminal_rule": "conjunctive",
            "transition_mode": "register_reinstatement",
        },
    )
    reinstatement = CompositeRegisterReinstatement(
        change_set_record=_reparse(record),
        register_observation_record=_reparse(register),
        prior_committed_checkpoint=checkpoint,
        authorization_record=_reparse(authorization),
        separation_policy_record=_reparse(separation),
        coordinator_identity_record=_reparse(coordinator),
    )
    assert reinstatement.promotional is False
    assert checkpoint.promotional is False
    unchecked_checkpoint = _copy_as_unchecked_composite_subclass(
        checkpoint,
        CompositeCheckpointWithoutValidation,
    )
    with pytest.raises(TypeError, match="must be an exact"):
        replace(
            reinstatement,
            prior_committed_checkpoint=unchecked_checkpoint,
        )
    with pytest.raises(TypeError, match="prior_committed_checkpoint"):
        replace(reinstatement, prior_committed_checkpoint=prior)
    wrong_checkpoint_record = ControlRecord.build(
        kind="composite_change_set",
        record_id=f"composite-register-reinstatement:{status}:wrong-checkpoint",
        payload={
            **_payload(record),
            "prior_committed_checkpoint_digest": digest("f"),
        },
    )
    with pytest.raises(ValueError, match="exact prior whole manifest"):
        replace(reinstatement, change_set_record=wrong_checkpoint_record)
    wrong_current_register_record = ControlRecord.build(
        kind="composite_change_set",
        record_id=f"composite-register-reinstatement:{status}:wrong-register",
        payload={
            **_payload(record),
            "current_authority_register_observation_digest": digest("e"),
        },
    )
    with pytest.raises(ValueError, match="exact prior whole manifest"):
        replace(reinstatement, change_set_record=wrong_current_register_record)
