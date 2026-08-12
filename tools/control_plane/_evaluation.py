"""Immutable evidence evaluation for control-plane gate assignments.

This module deliberately has no storage or clock dependency.  Callers supply
the exact validation context and the trusted observation time used to derive an
evaluation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
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


_STABLE_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:[-_:][a-z0-9]+)*\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _require_stable_id(value: object, *, field: str) -> None:
    if type(value) is not str or not _STABLE_ID_RE.fullmatch(value):
        raise ValueError(
            f"{field} must be a lowercase stable identifier using '-', '_', or ':' separators"
        )


def _require_digest(value: object, *, field: str) -> None:
    if type(value) is not str or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field} must be a canonical sha256 digest")


def _require_nonempty_text(value: object, *, field: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _as_unique_frozenset(
    value: object,
    *,
    field: str,
    item_type: type,
) -> frozenset:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field} must be an iterable of {item_type.__name__}")
    items = tuple(value)
    if any(not isinstance(item, item_type) for item in items):
        raise TypeError(f"{field} must contain only {item_type.__name__} values")
    frozen = frozenset(items)
    if len(frozen) != len(items):
        raise ValueError(f"{field} must not contain duplicates")
    return frozen


@dataclass(frozen=True, slots=True, order=True)
class DependencyKey:
    kind: str
    identifier: str

    def __post_init__(self) -> None:
        _require_stable_id(self.kind, field="kind")
        _require_stable_id(self.identifier, field="identifier")


@dataclass(frozen=True, slots=True, order=True)
class DependencyBinding:
    key: DependencyKey
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, DependencyKey):
            raise TypeError("key must be a DependencyKey")
        _require_digest(self.digest, field="digest")


@dataclass(frozen=True, slots=True)
class ActiveContractContext:
    context_id: str
    contract_digest: str
    generation_id: str
    kind: ContextKind = ContextKind.ACTIVE_CONTRACT

    def __post_init__(self) -> None:
        _require_stable_id(self.context_id, field="context_id")
        _require_digest(self.contract_digest, field="contract_digest")
        _require_stable_id(self.generation_id, field="generation_id")
        if self.kind is not ContextKind.ACTIVE_CONTRACT:
            raise ValueError("active contract context must use the active_contract tag")


@dataclass(frozen=True, slots=True)
class PreassemblyContext:
    context_id: str
    profile_digest: str
    source_closure_digest: str
    artifact_digest: str
    kind: ContextKind = ContextKind.PREASSEMBLY

    def __post_init__(self) -> None:
        _require_stable_id(self.context_id, field="context_id")
        _require_digest(self.profile_digest, field="profile_digest")
        _require_digest(self.source_closure_digest, field="source_closure_digest")
        _require_digest(self.artifact_digest, field="artifact_digest")
        if self.kind is not ContextKind.PREASSEMBLY:
            raise ValueError("preassembly context must use the preassembly tag")


ValidationContext: TypeAlias = ActiveContractContext | PreassemblyContext


@dataclass(frozen=True, slots=True)
class UnconditionalApplicability:
    """The assignment always applies; non-applicability cannot waive it."""


@dataclass(frozen=True, slots=True)
class ConditionalApplicability:
    predicate_id: str

    def __post_init__(self) -> None:
        _require_stable_id(self.predicate_id, field="predicate_id")


ApplicabilityRule: TypeAlias = UnconditionalApplicability | ConditionalApplicability


@dataclass(frozen=True, slots=True)
class ValidityPolicy:
    max_age: timedelta | None = None

    def __post_init__(self) -> None:
        if self.max_age is None:
            return
        if not isinstance(self.max_age, timedelta):
            raise TypeError("max_age must be a timedelta or None")
        if self.max_age < timedelta(0):
            raise ValueError("max_age must not be negative")


@dataclass(frozen=True, slots=True)
class InvalidationPolicy:
    invalidate_on: frozenset[DependencyKey] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "invalidate_on",
            _as_unique_frozenset(
                self.invalidate_on,
                field="invalidate_on",
                item_type=DependencyKey,
            ),
        )


@dataclass(frozen=True, slots=True)
class InvalidationEvent:
    event_id: str
    observed_at: datetime
    changed_dependencies: frozenset[DependencyKey]
    reason: str

    def __post_init__(self) -> None:
        _require_stable_id(self.event_id, field="event_id")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        _require_aware(self.observed_at, field="observed_at")
        changed_dependencies = _as_unique_frozenset(
            self.changed_dependencies,
            field="changed_dependencies",
            item_type=DependencyKey,
        )
        if not changed_dependencies:
            raise ValueError("changed_dependencies must not be empty")
        object.__setattr__(self, "changed_dependencies", changed_dependencies)
        _require_nonempty_text(self.reason, field="reason")


@dataclass(frozen=True, slots=True)
class SeparationPolicy:
    required_attestor_roles: frozenset[str] = frozenset()
    forbidden_attestor_principals: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        roles = _as_unique_frozenset(
            self.required_attestor_roles,
            field="required_attestor_roles",
            item_type=str,
        )
        principals = _as_unique_frozenset(
            self.forbidden_attestor_principals,
            field="forbidden_attestor_principals",
            item_type=str,
        )
        for role in roles:
            _require_stable_id(role, field="required_attestor_roles item")
        for principal in principals:
            _require_stable_id(
                principal,
                field="forbidden_attestor_principals item",
            )
        object.__setattr__(
            self,
            "required_attestor_roles",
            roles,
        )
        object.__setattr__(
            self,
            "forbidden_attestor_principals",
            principals,
        )


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

    def __post_init__(self) -> None:
        _require_stable_id(self.assignment_id, field="assignment_id")
        _require_stable_id(self.subject_id, field="subject_id")
        _require_stable_id(self.gate_id, field="gate_id")
        if not isinstance(self.context, (ActiveContractContext, PreassemblyContext)):
            raise TypeError("context must be a validation context")
        if not isinstance(self.impact, GateImpact):
            raise TypeError("impact must be a GateImpact")
        if not isinstance(
            self.applicability,
            (UnconditionalApplicability, ConditionalApplicability),
        ):
            raise TypeError("applicability must be an applicability rule")
        if not isinstance(self.validity, ValidityPolicy):
            raise TypeError("validity must be a ValidityPolicy")
        if not isinstance(self.invalidation, InvalidationPolicy):
            raise TypeError("invalidation must be an InvalidationPolicy")
        if not isinstance(self.separation, SeparationPolicy):
            raise TypeError("separation must be a SeparationPolicy")
        dependency_projection = _as_unique_frozenset(
            self.dependency_projection,
            field="dependency_projection",
            item_type=DependencyBinding,
        )
        dependency_keys = tuple(
            binding.key for binding in dependency_projection
        )
        if len(dependency_keys) != len(set(dependency_keys)):
            raise ValueError(
                "dependency_projection must bind each dependency key exactly once"
            )
        unprojected_invalidation = (
            self.invalidation.invalidate_on - set(dependency_keys)
        )
        if unprojected_invalidation:
            raise ValueError(
                "invalidation keys must be present in dependency_projection"
            )
        object.__setattr__(
            self,
            "dependency_projection",
            dependency_projection,
        )


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

    def __post_init__(self) -> None:
        _require_stable_id(self.attestation_id, field="attestation_id")
        _require_stable_id(self.assignment_id, field="assignment_id")
        _require_stable_id(self.subject_id, field="subject_id")
        _require_stable_id(self.gate_id, field="gate_id")
        if not isinstance(self.context, (ActiveContractContext, PreassemblyContext)):
            raise TypeError("context must be a validation context")
        if not isinstance(self.outcome, AttestationOutcome):
            raise TypeError("outcome must be an AttestationOutcome")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        _require_aware(self.observed_at, field="observed_at")
        dependency_projection = _as_unique_frozenset(
            self.dependency_projection,
            field="dependency_projection",
            item_type=DependencyBinding,
        )
        dependency_keys = tuple(
            binding.key for binding in dependency_projection
        )
        if len(dependency_keys) != len(set(dependency_keys)):
            raise ValueError(
                "dependency_projection must bind each dependency key exactly once"
            )
        object.__setattr__(
            self,
            "dependency_projection",
            dependency_projection,
        )
        _require_stable_id(self.actor_principal, field="actor_principal")
        _require_stable_id(self.actor_role, field="actor_role")


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

    def __post_init__(self) -> None:
        _require_stable_id(self.proof_id, field="proof_id")
        _require_stable_id(self.assignment_id, field="assignment_id")
        _require_stable_id(self.subject_id, field="subject_id")
        _require_stable_id(self.gate_id, field="gate_id")
        if not isinstance(self.context, (ActiveContractContext, PreassemblyContext)):
            raise TypeError("context must be a validation context")
        _require_stable_id(self.predicate_id, field="predicate_id")
        if type(self.is_applicable) is not bool:
            raise TypeError("is_applicable must be a bool")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        _require_aware(self.observed_at, field="observed_at")
        dependency_projection = _as_unique_frozenset(
            self.dependency_projection,
            field="dependency_projection",
            item_type=DependencyBinding,
        )
        dependency_keys = tuple(
            binding.key for binding in dependency_projection
        )
        if len(dependency_keys) != len(set(dependency_keys)):
            raise ValueError(
                "dependency_projection must bind each dependency key exactly once"
            )
        object.__setattr__(
            self,
            "dependency_projection",
            dependency_projection,
        )
        _require_stable_id(self.actor_principal, field="actor_principal")
        _require_stable_id(self.actor_role, field="actor_role")


@dataclass(frozen=True, slots=True)
class Applicable:
    outcome: AttestationOutcome
    attestation: Attestation

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AttestationOutcome):
            raise TypeError("outcome must be an AttestationOutcome")
        if not isinstance(self.attestation, Attestation):
            raise TypeError("attestation must be an Attestation")
        if self.outcome is AttestationOutcome.UNKNOWN:
            raise ValueError("unknown evidence must use ApplicableUnknown")
        if self.outcome is not self.attestation.outcome:
            raise ValueError("outcome must match the attestation outcome")


@dataclass(frozen=True, slots=True)
class ApplicableUnknown:
    reason: UnknownReason
    attestation: Attestation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, UnknownReason):
            raise TypeError("reason must be an UnknownReason")
        if self.attestation is not None and not isinstance(
            self.attestation,
            Attestation,
        ):
            raise TypeError("attestation must be an Attestation or None")


@dataclass(frozen=True, slots=True)
class NotApplicable:
    proof: PredicateProof

    def __post_init__(self) -> None:
        if not isinstance(self.proof, PredicateProof):
            raise TypeError("proof must be a PredicateProof")
        if self.proof.is_applicable:
            raise ValueError("a not-applicable proof must prove false")


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

    def __post_init__(self) -> None:
        if not isinstance(self.assignment, GateAssignment):
            raise TypeError("assignment must be a GateAssignment")
        if not isinstance(
            self.state,
            (Applicable, ApplicableUnknown, NotApplicable, NotDue),
        ):
            raise TypeError("state must be an evaluation state")
        if not isinstance(self.currency, Currency):
            raise TypeError("currency must be a Currency")
        for field, moment in (
            ("evaluated_at", self.evaluated_at),
            ("observed_at", self.observed_at),
        ):
            if not isinstance(moment, datetime):
                raise TypeError(f"{field} must be a datetime")
            _require_aware(moment, field=field)
        if self.evaluated_at < self.observed_at:
            raise ValueError("evaluated_at must not precede observed_at")

        if isinstance(self.state, Applicable):
            attestation = self.state.attestation
            if (
                attestation.assignment_id != self.assignment.assignment_id
                or attestation.subject_id != self.assignment.subject_id
                or attestation.gate_id != self.assignment.gate_id
                or attestation.context != self.assignment.context
                or attestation.dependency_projection
                != self.assignment.dependency_projection
            ):
                raise ValueError(
                    "applicable evidence must match its assignment coordinates"
                )
        elif isinstance(self.state, NotApplicable):
            proof = self.state.proof
            if not isinstance(
                self.assignment.applicability,
                ConditionalApplicability,
            ) or (
                proof.assignment_id != self.assignment.assignment_id
                or proof.subject_id != self.assignment.subject_id
                or proof.gate_id != self.assignment.gate_id
                or proof.context != self.assignment.context
                or proof.predicate_id
                != self.assignment.applicability.predicate_id
                or proof.dependency_projection
                != self.assignment.dependency_projection
            ):
                raise ValueError(
                    "not-applicable proof must match its conditional assignment"
                )

        if isinstance(self.invalidation_events, (str, bytes)) or not isinstance(
            self.invalidation_events,
            Iterable,
        ):
            raise TypeError(
                "invalidation_events must be an iterable of InvalidationEvent"
            )
        invalidation_events = tuple(self.invalidation_events)
        if any(
            not isinstance(event, InvalidationEvent)
            for event in invalidation_events
        ):
            raise TypeError(
                "invalidation_events must contain only InvalidationEvent values"
            )
        event_ids = tuple(event.event_id for event in invalidation_events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("invalidation_events must have unique event IDs")
        if invalidation_events and self.currency is not Currency.STALE:
            raise ValueError("an invalidated evaluation must be stale")
        projected_keys = {
            binding.key for binding in self.assignment.dependency_projection
        }
        for event in invalidation_events:
            if not self.observed_at <= event.observed_at <= self.evaluated_at:
                raise ValueError(
                    "invalidation events must fall within the evaluation interval"
                )
            affected_keys = (
                event.changed_dependencies
                & self.assignment.invalidation.invalidate_on
                & projected_keys
            )
            if not affected_keys:
                raise ValueError(
                    "invalidation events must affect the assignment projection"
                )
        object.__setattr__(self, "invalidation_events", invalidation_events)

    @property
    def invalidation_event_ids(self) -> tuple[str, ...]:
        return tuple(event.event_id for event in self.invalidation_events)


@dataclass(frozen=True, slots=True)
class EvidenceSatisfaction:
    required: bool
    satisfied: bool

    def __post_init__(self) -> None:
        for field in ("required", "satisfied"):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f"{field} must be a bool")
        if self.satisfied and not self.required:
            raise ValueError("satisfied evidence must be required")


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


def assess_evidence_satisfaction(
    evaluation: EvidenceEvaluation,
) -> EvidenceSatisfaction:
    """Assess local gate semantics without asserting promotion authority."""

    if isinstance(evaluation.assignment.context, PreassemblyContext):
        raise NonPromotionalContext(
            "preassembly evidence requires a verified inclusion edge and cannot "
            "be relabeled as active-contract evidence"
        )
    if evaluation.assignment.impact is GateImpact.ADVISORY:
        return EvidenceSatisfaction(
            required=False,
            satisfied=False,
        )
    if isinstance(evaluation.state, NotApplicable):
        if evaluation.currency is not Currency.CURRENT:
            raise EvidenceNotCurrent("non-applicability proof is stale")
        return EvidenceSatisfaction(
            required=True,
            satisfied=True,
        )
    require_evaluation_pass(evaluation)
    return EvidenceSatisfaction(required=True, satisfied=True)
