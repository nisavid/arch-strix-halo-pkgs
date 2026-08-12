"""Immutable evidence evaluation for control-plane gate assignments.

This module deliberately has no storage or clock dependency.  Callers supply
the exact validation context and the trusted observation time used to derive an
evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TypeAlias


class ContextKind(StrEnum):
    ACTIVE_CONTRACT = "active_contract"
    PREASSEMBLY = "preassembly"


class GateImpact(StrEnum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"


class AttestationOutcome(StrEnum):
    BLOCKED = "blocked"
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Currency(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class UnknownReason(StrEnum):
    MISSING_ATTESTATION = "missing_attestation"
    MISSING_APPLICABILITY_PROOF = "missing_applicability_proof"
    APPLICABILITY_PROOF_MISMATCH = "applicability_proof_mismatch"
    ASSIGNMENT_MISMATCH = "assignment_mismatch"
    SUBJECT_MISMATCH = "subject_mismatch"
    GATE_MISMATCH = "gate_mismatch"
    CONTEXT_MISMATCH = "context_mismatch"
    DEPENDENCY_MISMATCH = "dependency_mismatch"
    SEPARATION_VIOLATION = "separation_violation"
    REPORTED_UNKNOWN = "reported_unknown"


@dataclass(frozen=True, slots=True, order=True)
class DependencyKey:
    kind: str
    identifier: str


@dataclass(frozen=True, slots=True, order=True)
class DependencyBinding:
    key: DependencyKey
    digest: str


@dataclass(frozen=True, slots=True)
class ActiveContractContext:
    context_id: str
    contract_digest: str
    generation_id: str
    kind: ContextKind = ContextKind.ACTIVE_CONTRACT


@dataclass(frozen=True, slots=True)
class PreassemblyContext:
    context_id: str
    profile_digest: str
    source_closure_digest: str
    artifact_digest: str
    kind: ContextKind = ContextKind.PREASSEMBLY


ValidationContext: TypeAlias = ActiveContractContext | PreassemblyContext


@dataclass(frozen=True, slots=True)
class UnconditionalApplicability:
    """The assignment always applies; non-applicability cannot waive it."""


@dataclass(frozen=True, slots=True)
class ConditionalApplicability:
    predicate_id: str


ApplicabilityRule: TypeAlias = UnconditionalApplicability | ConditionalApplicability


@dataclass(frozen=True, slots=True)
class ValidityPolicy:
    max_age: timedelta | None = None


@dataclass(frozen=True, slots=True)
class InvalidationPolicy:
    invalidate_on: frozenset[DependencyKey] = frozenset()


@dataclass(frozen=True, slots=True)
class InvalidationEvent:
    event_id: str
    observed_at: datetime
    changed_dependencies: frozenset[DependencyKey]
    reason: str


@dataclass(frozen=True, slots=True)
class SeparationPolicy:
    required_attestor_roles: frozenset[str] = frozenset()
    forbidden_attestor_principals: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class GateAssignment:
    assignment_id: str
    subject_id: str
    gate_id: str
    context: ValidationContext
    impact: GateImpact
    applicability: ApplicabilityRule
    dependency_projection: frozenset[DependencyBinding]
    validity: ValidityPolicy
    invalidation: InvalidationPolicy
    separation: SeparationPolicy


@dataclass(frozen=True, slots=True)
class Attestation:
    attestation_id: str
    assignment_id: str
    subject_id: str
    gate_id: str
    context: ValidationContext
    outcome: AttestationOutcome
    observed_at: datetime
    dependency_projection: frozenset[DependencyBinding]
    actor_principal: str
    actor_role: str


@dataclass(frozen=True, slots=True)
class PredicateProof:
    proof_id: str
    assignment_id: str
    subject_id: str
    gate_id: str
    context: ValidationContext
    predicate_id: str
    is_applicable: bool
    observed_at: datetime
    dependency_projection: frozenset[DependencyBinding]
    actor_principal: str
    actor_role: str


@dataclass(frozen=True, slots=True)
class Applicable:
    outcome: AttestationOutcome
    attestation: Attestation


@dataclass(frozen=True, slots=True)
class ApplicableUnknown:
    reason: UnknownReason
    attestation: Attestation | None = None


@dataclass(frozen=True, slots=True)
class NotApplicable:
    proof: PredicateProof


@dataclass(frozen=True, slots=True)
class NotDue:
    pass


EvaluationState: TypeAlias = Applicable | ApplicableUnknown | NotApplicable | NotDue


@dataclass(frozen=True, slots=True)
class EvidenceEvaluation:
    assignment: GateAssignment
    state: EvaluationState
    currency: Currency
    evaluated_at: datetime
    observed_at: datetime
    invalidation_events: tuple[InvalidationEvent, ...] = ()

    @property
    def invalidation_event_ids(self) -> tuple[str, ...]:
        return tuple(event.event_id for event in self.invalidation_events)


@dataclass(frozen=True, slots=True)
class PromotionAssessment:
    required: bool
    satisfied: bool
    promotional: bool


class EvaluationFailure(RuntimeError):
    """Base class for a typed evidence-evaluation failure."""


class EvaluationInputError(EvaluationFailure):
    pass


class EvidenceNotCurrent(EvaluationFailure):
    pass


class EvidenceDidNotPass(EvaluationFailure):
    pass


class EvidenceUnknown(EvaluationFailure):
    pass


class NonPromotionalContext(EvaluationFailure):
    pass


def _require_aware(moment: datetime, *, field: str) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def evaluate_evidence(
    assignment: GateAssignment,
    *,
    attestation: Attestation | None,
    applicability_proof: PredicateProof | None = None,
    due: bool = True,
    trusted_time: datetime,
) -> EvidenceEvaluation:
    """Derive an immutable evaluation using the caller's trusted time."""

    _require_aware(trusted_time, field="trusted_time")
    if not due:
        return EvidenceEvaluation(
            assignment=assignment,
            state=NotDue(),
            currency=Currency.CURRENT,
            evaluated_at=trusted_time,
            observed_at=trusted_time,
        )
    predicate_observed_at: datetime | None = None
    predicate_is_stale = False
    if isinstance(assignment.applicability, ConditionalApplicability):
        if applicability_proof is None:
            return EvidenceEvaluation(
                assignment=assignment,
                state=ApplicableUnknown(
                    reason=UnknownReason.MISSING_APPLICABILITY_PROOF
                ),
                currency=Currency.CURRENT,
                evaluated_at=trusted_time,
                observed_at=trusted_time,
            )
        _require_aware(
            applicability_proof.observed_at,
            field="applicability_proof.observed_at",
        )
        if applicability_proof.observed_at > trusted_time:
            raise EvaluationInputError(
                "applicability proof observation is after trusted_time"
            )
        proof_matches = (
            applicability_proof.assignment_id == assignment.assignment_id
            and applicability_proof.subject_id == assignment.subject_id
            and applicability_proof.gate_id == assignment.gate_id
            and applicability_proof.context == assignment.context
            and applicability_proof.predicate_id
            == assignment.applicability.predicate_id
            and applicability_proof.dependency_projection
            == assignment.dependency_projection
            and (
                not assignment.separation.required_attestor_roles
                or applicability_proof.actor_role
                in assignment.separation.required_attestor_roles
            )
            and applicability_proof.actor_principal
            not in assignment.separation.forbidden_attestor_principals
        )
        if not proof_matches:
            return EvidenceEvaluation(
                assignment=assignment,
                state=ApplicableUnknown(
                    reason=UnknownReason.APPLICABILITY_PROOF_MISMATCH
                ),
                currency=Currency.CURRENT,
                evaluated_at=trusted_time,
                observed_at=applicability_proof.observed_at,
            )
        predicate_observed_at = applicability_proof.observed_at
        predicate_is_stale = (
            assignment.validity.max_age is not None
            and trusted_time
            > applicability_proof.observed_at + assignment.validity.max_age
        )
        if not applicability_proof.is_applicable:
            return EvidenceEvaluation(
                assignment=assignment,
                state=NotApplicable(proof=applicability_proof),
                currency=(
                    Currency.STALE if predicate_is_stale else Currency.CURRENT
                ),
                evaluated_at=trusted_time,
                observed_at=applicability_proof.observed_at,
            )
    if attestation is None:
        return EvidenceEvaluation(
            assignment=assignment,
            state=ApplicableUnknown(reason=UnknownReason.MISSING_ATTESTATION),
            currency=Currency.CURRENT,
            evaluated_at=trusted_time,
            observed_at=trusted_time,
        )
    _require_aware(attestation.observed_at, field="attestation.observed_at")
    if attestation.observed_at > trusted_time:
        raise EvaluationInputError("attestation observation is after trusted_time")
    mismatch_reason: UnknownReason | None = None
    if attestation.assignment_id != assignment.assignment_id:
        mismatch_reason = UnknownReason.ASSIGNMENT_MISMATCH
    elif attestation.subject_id != assignment.subject_id:
        mismatch_reason = UnknownReason.SUBJECT_MISMATCH
    elif attestation.gate_id != assignment.gate_id:
        mismatch_reason = UnknownReason.GATE_MISMATCH
    elif attestation.context != assignment.context:
        mismatch_reason = UnknownReason.CONTEXT_MISMATCH
    elif attestation.dependency_projection != assignment.dependency_projection:
        mismatch_reason = UnknownReason.DEPENDENCY_MISMATCH
    elif (
        assignment.separation.required_attestor_roles
        and attestation.actor_role
        not in assignment.separation.required_attestor_roles
    ) or (
        attestation.actor_principal
        in assignment.separation.forbidden_attestor_principals
    ):
        mismatch_reason = UnknownReason.SEPARATION_VIOLATION
    elif attestation.outcome is AttestationOutcome.UNKNOWN:
        mismatch_reason = UnknownReason.REPORTED_UNKNOWN
    if mismatch_reason is not None:
        return EvidenceEvaluation(
            assignment=assignment,
            state=ApplicableUnknown(
                reason=mismatch_reason,
                attestation=attestation,
            ),
            currency=Currency.CURRENT,
            evaluated_at=trusted_time,
            observed_at=attestation.observed_at,
        )
    currency = Currency.STALE if predicate_is_stale else Currency.CURRENT
    if (
        assignment.validity.max_age is not None
        and trusted_time > attestation.observed_at + assignment.validity.max_age
    ):
        currency = Currency.STALE
    observed_at = attestation.observed_at
    if predicate_observed_at is not None:
        observed_at = min(observed_at, predicate_observed_at)
    return EvidenceEvaluation(
        assignment=assignment,
        state=Applicable(outcome=attestation.outcome, attestation=attestation),
        currency=currency,
        evaluated_at=trusted_time,
        observed_at=observed_at,
    )


def require_evaluation_pass(evaluation: EvidenceEvaluation) -> EvidenceEvaluation:
    """Return a current pass or raise a typed failure."""

    if evaluation.currency is not Currency.CURRENT:
        raise EvidenceNotCurrent("evidence evaluation is stale")
    if isinstance(evaluation.state, ApplicableUnknown):
        raise EvidenceUnknown(
            f"evidence evaluation is unknown: {evaluation.state.reason.value}"
        )
    if not isinstance(evaluation.state, Applicable):
        raise EvidenceDidNotPass("evidence evaluation is not an applicable pass")
    if evaluation.state.outcome is not AttestationOutcome.PASS:
        raise EvidenceDidNotPass(
            f"evidence outcome is {evaluation.state.outcome.value}, not pass"
        )
    return evaluation


def apply_invalidation(
    evaluation: EvidenceEvaluation,
    event: InvalidationEvent,
    *,
    trusted_time: datetime,
) -> EvidenceEvaluation:
    """Return a stale derived evaluation when ``event`` touches its projection."""

    _require_aware(trusted_time, field="trusted_time")
    _require_aware(event.observed_at, field="event.observed_at")
    if event.observed_at > trusted_time:
        raise EvaluationInputError("invalidation event is after trusted_time")
    if event.event_id in evaluation.invalidation_event_ids:
        return evaluation
    projected_keys = {
        binding.key for binding in evaluation.assignment.dependency_projection
    }
    affected_keys = (
        event.changed_dependencies
        & evaluation.assignment.invalidation.invalidate_on
        & projected_keys
    )
    if not affected_keys or event.observed_at < evaluation.observed_at:
        return evaluation
    return replace(
        evaluation,
        currency=Currency.STALE,
        evaluated_at=trusted_time,
        invalidation_events=(*evaluation.invalidation_events, event),
    )


def require_promotable_evidence(
    evaluation: EvidenceEvaluation,
) -> PromotionAssessment:
    """Enforce blocking promotion evidence while recording advisory results."""

    if isinstance(evaluation.assignment.context, PreassemblyContext):
        raise NonPromotionalContext(
            "preassembly evidence requires a verified inclusion edge and cannot "
            "be relabeled as active-contract evidence"
        )
    if evaluation.assignment.impact is GateImpact.ADVISORY:
        return PromotionAssessment(
            required=False,
            satisfied=False,
            promotional=False,
        )
    if isinstance(evaluation.state, NotApplicable):
        if evaluation.currency is not Currency.CURRENT:
            raise EvidenceNotCurrent("non-applicability proof is stale")
        return PromotionAssessment(
            required=True,
            satisfied=True,
            promotional=True,
        )
    require_evaluation_pass(evaluation)
    return PromotionAssessment(required=True, satisfied=True, promotional=True)
