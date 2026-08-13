"""Immutable evidence evaluation for control-plane gate assignments.

This module deliberately has no storage or clock dependency.  Callers supply
the exact validation context and the trusted observation time used to derive an
evaluation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TypeAlias

from ._records import ControlRecord, _require_canonical_control_record


class ContextKind(StrEnum):
    ACTIVE_CONTRACT = "active_contract"
    PREASSEMBLY = "preassembly_profile"


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


def _record(value: object, *, field: str, kind: str) -> ControlRecord:
    return _require_canonical_control_record(value, field=field, kind=kind)


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
    requirements_digest: str
    assignments_digest: str
    contract_digest: str
    generation_digest: str
    kind: ContextKind = ContextKind.ACTIVE_CONTRACT

    def __post_init__(self) -> None:
        _require_stable_id(self.context_id, field="context_id")
        _require_digest(self.requirements_digest, field="requirements_digest")
        _require_digest(self.assignments_digest, field="assignments_digest")
        _require_digest(self.contract_digest, field="contract_digest")
        _require_digest(self.generation_digest, field="generation_digest")
        if self.kind is not ContextKind.ACTIVE_CONTRACT:
            raise ValueError("active contract context must use the active_contract tag")

    @classmethod
    def from_record(cls, record: ControlRecord) -> ActiveContractContext:
        payload = _record(
            record,
            field="record",
            kind="validation_context",
        ).payload
        if payload["context_type"] != ContextKind.ACTIVE_CONTRACT.value:
            raise ValueError("validation context is not active_contract")
        return cls(
            context_id=payload["context_id"],
            requirements_digest=payload["requirements_digest"],
            assignments_digest=payload["assignments_digest"],
            contract_digest=payload["contract_digest"],
            generation_digest=payload["generation_digest"],
        )

    def to_record(self, *, record_id: str) -> ControlRecord:
        return ControlRecord.build(
            kind="validation_context",
            record_id=record_id,
            payload={
                "assignments_digest": self.assignments_digest,
                "context_id": self.context_id,
                "context_type": self.kind.value,
                "contract_digest": self.contract_digest,
                "generation_digest": self.generation_digest,
                "requirements_digest": self.requirements_digest,
            },
        )


@dataclass(frozen=True, slots=True)
class PreassemblyContext:
    context_id: str
    requirements_digest: str
    assignments_digest: str
    profile_digest: str
    source_closure_digest: str
    artifact_digests: tuple[str, ...]
    kind: ContextKind = ContextKind.PREASSEMBLY

    def __post_init__(self) -> None:
        _require_stable_id(self.context_id, field="context_id")
        _require_digest(self.requirements_digest, field="requirements_digest")
        _require_digest(self.assignments_digest, field="assignments_digest")
        _require_digest(self.profile_digest, field="profile_digest")
        _require_digest(self.source_closure_digest, field="source_closure_digest")
        artifacts = tuple(self.artifact_digests)
        if not artifacts or len(artifacts) != len(set(artifacts)):
            raise ValueError("artifact_digests must be nonempty and unique")
        for artifact_digest in artifacts:
            _require_digest(artifact_digest, field="artifact_digests item")
        object.__setattr__(self, "artifact_digests", artifacts)
        if self.kind is not ContextKind.PREASSEMBLY:
            raise ValueError("preassembly context must use the preassembly tag")

    @classmethod
    def from_record(cls, record: ControlRecord) -> PreassemblyContext:
        payload = _record(
            record,
            field="record",
            kind="validation_context",
        ).payload
        if payload["context_type"] != ContextKind.PREASSEMBLY.value:
            raise ValueError("validation context is not preassembly_profile")
        return cls(
            context_id=payload["context_id"],
            requirements_digest=payload["requirements_digest"],
            assignments_digest=payload["assignments_digest"],
            profile_digest=payload["profile_digest"],
            source_closure_digest=payload["source_closure_digest"],
            artifact_digests=tuple(payload["artifact_digests"]),
        )

    def to_record(self, *, record_id: str) -> ControlRecord:
        return ControlRecord.build(
            kind="validation_context",
            record_id=record_id,
            payload={
                "artifact_digests": list(self.artifact_digests),
                "assignments_digest": self.assignments_digest,
                "context_id": self.context_id,
                "context_type": self.kind.value,
                "profile_digest": self.profile_digest,
                "requirements_digest": self.requirements_digest,
                "source_closure_digest": self.source_closure_digest,
            },
        )


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
    """Actor qualifications that are distinct from authorization grants.

    Every required role must belong to the actor identity, and the selected
    acting role must be one of those required roles when the set is nonempty.
    A separate authorization policy must allow the identity or selected role.
    """

    required_actor_roles: frozenset[str] = frozenset()
    forbidden_actor_principals: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        roles = _as_unique_frozenset(
            self.required_actor_roles,
            field="required_actor_roles",
            item_type=str,
        )
        principals = _as_unique_frozenset(
            self.forbidden_actor_principals,
            field="forbidden_actor_principals",
            item_type=str,
        )
        for role in roles:
            _require_stable_id(role, field="required_actor_roles item")
        for principal in principals:
            _require_stable_id(
                principal,
                field="forbidden_actor_principals item",
            )
        object.__setattr__(
            self,
            "required_actor_roles",
            roles,
        )
        object.__setattr__(
            self,
            "forbidden_actor_principals",
            principals,
        )


def _normalize_actor_identity_roles(
    actor_identity_roles: object,
    *,
    actor_role: str,
) -> frozenset[str]:
    roles = _as_unique_frozenset(
        actor_identity_roles,
        field="actor_identity_roles",
        item_type=str,
    )
    for role in roles:
        _require_stable_id(role, field="actor_identity_roles item")
    if actor_role not in roles:
        raise ValueError("actor_role must belong to actor_identity_roles")
    return roles


def _actor_satisfies_separation(
    policy: SeparationPolicy,
    *,
    actor_principal: str,
    actor_role: str,
    actor_identity_roles: frozenset[str],
) -> bool:
    required_roles = policy.required_actor_roles
    return (
        actor_principal not in policy.forbidden_actor_principals
        and actor_role in actor_identity_roles
        and required_roles <= actor_identity_roles
        and (not required_roles or actor_role in required_roles)
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
    """Historical outcome with roles resolved from the named actor identity."""

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
    actor_identity_roles: frozenset[str]

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
        object.__setattr__(
            self,
            "actor_identity_roles",
            _normalize_actor_identity_roles(
                self.actor_identity_roles,
                actor_role=self.actor_role,
            ),
        )


@dataclass(frozen=True, slots=True)
class PredicateProof:
    """Predicate result with roles resolved from the named actor identity."""

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
    actor_identity_roles: frozenset[str]

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
        object.__setattr__(
            self,
            "actor_identity_roles",
            _normalize_actor_identity_roles(
                self.actor_identity_roles,
                actor_role=self.actor_role,
            ),
        )


@dataclass(frozen=True, slots=True)
class Applicable:
    outcome: AttestationOutcome
    attestation: Attestation
    predicate_proof: PredicateProof | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AttestationOutcome):
            raise TypeError("outcome must be an AttestationOutcome")
        if not isinstance(self.attestation, Attestation):
            raise TypeError("attestation must be an Attestation")
        if self.outcome is AttestationOutcome.UNKNOWN:
            raise ValueError("unknown evidence must use ApplicableUnknown")
        if self.outcome is not self.attestation.outcome:
            raise ValueError("outcome must match the attestation outcome")
        if self.predicate_proof is not None:
            if not isinstance(self.predicate_proof, PredicateProof):
                raise TypeError("predicate_proof must be a PredicateProof or None")
            if not self.predicate_proof.is_applicable:
                raise ValueError("an applicable predicate proof must prove true")


@dataclass(frozen=True, slots=True)
class ApplicableUnknown:
    reason: UnknownReason
    attestation: Attestation | None = None
    predicate_proof: PredicateProof | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, UnknownReason):
            raise TypeError("reason must be an UnknownReason")
        if self.attestation is not None and not isinstance(
            self.attestation,
            Attestation,
        ):
            raise TypeError("attestation must be an Attestation or None")
        if self.predicate_proof is not None and not isinstance(
            self.predicate_proof,
            PredicateProof,
        ):
            raise TypeError("predicate_proof must be a PredicateProof or None")
        attestation_derived_reasons = {
            UnknownReason.ASSIGNMENT_MISMATCH,
            UnknownReason.CONTEXT_MISMATCH,
            UnknownReason.DEPENDENCY_MISMATCH,
            UnknownReason.GATE_MISMATCH,
            UnknownReason.REPORTED_UNKNOWN,
            UnknownReason.SEPARATION_VIOLATION,
            UnknownReason.SUBJECT_MISMATCH,
        }
        if (self.reason in attestation_derived_reasons) != (
            self.attestation is not None
        ):
            raise ValueError(
                "attestation-derived unknown reasons require exactly one attestation"
            )
        if (
            self.reason is UnknownReason.MISSING_APPLICABILITY_PROOF
            and self.predicate_proof is not None
        ):
            raise ValueError(
                "missing-applicability-proof state cannot bind a predicate proof"
            )
        if (
            self.reason is UnknownReason.APPLICABILITY_PROOF_MISMATCH
            and self.predicate_proof is None
        ):
            raise ValueError(
                "applicability-proof mismatch requires its exact predicate proof"
            )


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


@dataclass(frozen=True, slots=True, init=False)
class EvidenceEvaluation:
    """A factory-derived evidence verdict whose currency cannot be caller-selected."""

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
            applicability = self.assignment.applicability
            predicate_proof = self.state.predicate_proof
            if isinstance(applicability, ConditionalApplicability):
                if predicate_proof is None:
                    raise ValueError(
                        "conditional applicable evidence requires one true predicate proof"
                    )
                if (
                    predicate_proof.assignment_id
                    != self.assignment.assignment_id
                    or predicate_proof.subject_id != self.assignment.subject_id
                    or predicate_proof.gate_id != self.assignment.gate_id
                    or predicate_proof.context != self.assignment.context
                    or predicate_proof.predicate_id != applicability.predicate_id
                    or predicate_proof.dependency_projection
                    != self.assignment.dependency_projection
                    or not _actor_satisfies_separation(
                        self.assignment.separation,
                        actor_principal=predicate_proof.actor_principal,
                        actor_role=predicate_proof.actor_role,
                        actor_identity_roles=predicate_proof.actor_identity_roles,
                    )
                ):
                    raise ValueError(
                        "applicable predicate proof must match its conditional assignment"
                    )
            elif predicate_proof is not None:
                raise ValueError(
                    "unconditional applicable evidence cannot bind a predicate proof"
                )
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
        elif isinstance(self.state, ApplicableUnknown):
            reason = self.state.reason
            predicate_proof = self.state.predicate_proof
            applicability = self.assignment.applicability
            if isinstance(applicability, ConditionalApplicability):
                if reason is UnknownReason.MISSING_APPLICABILITY_PROOF:
                    if predicate_proof is not None:
                        raise ValueError(
                            "missing applicability proof cannot bind predicate evidence"
                        )
                elif predicate_proof is None:
                    raise ValueError(
                        "conditional post-proof unknown requires its exact predicate proof"
                    )
                else:
                    proof_matches = (
                        predicate_proof.assignment_id
                        == self.assignment.assignment_id
                        and predicate_proof.subject_id == self.assignment.subject_id
                        and predicate_proof.gate_id == self.assignment.gate_id
                        and predicate_proof.context == self.assignment.context
                        and predicate_proof.predicate_id == applicability.predicate_id
                        and predicate_proof.dependency_projection
                        == self.assignment.dependency_projection
                        and _actor_satisfies_separation(
                            self.assignment.separation,
                            actor_principal=predicate_proof.actor_principal,
                            actor_role=predicate_proof.actor_role,
                            actor_identity_roles=(
                                predicate_proof.actor_identity_roles
                            ),
                        )
                    )
                    if reason is UnknownReason.APPLICABILITY_PROOF_MISMATCH:
                        if proof_matches:
                            raise ValueError(
                                "applicability-proof mismatch must bind a mismatching proof"
                            )
                    elif not proof_matches or not predicate_proof.is_applicable:
                        raise ValueError(
                            "conditional post-proof unknown requires a matching true proof"
                        )
            elif predicate_proof is not None or reason in {
                UnknownReason.MISSING_APPLICABILITY_PROOF,
                UnknownReason.APPLICABILITY_PROOF_MISMATCH,
            }:
                raise ValueError(
                    "unconditional unknown evidence forbids applicability-proof provenance"
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
                or not _actor_satisfies_separation(
                    self.assignment.separation,
                    actor_principal=proof.actor_principal,
                    actor_role=proof.actor_role,
                    actor_identity_roles=proof.actor_identity_roles,
                )
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


def _derive_evaluation(
    *,
    assignment: GateAssignment,
    state: EvaluationState,
    currency: Currency,
    evaluated_at: datetime,
    observed_at: datetime,
    invalidation_events: Iterable[InvalidationEvent] = (),
) -> EvidenceEvaluation:
    evaluation = object.__new__(EvidenceEvaluation)
    object.__setattr__(evaluation, "assignment", assignment)
    object.__setattr__(evaluation, "state", state)
    object.__setattr__(evaluation, "currency", currency)
    object.__setattr__(evaluation, "evaluated_at", evaluated_at)
    object.__setattr__(evaluation, "observed_at", observed_at)
    object.__setattr__(
        evaluation,
        "invalidation_events",
        invalidation_events,
    )
    evaluation.__post_init__()
    return evaluation


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
        return _derive_evaluation(
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
            return _derive_evaluation(
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
        predicate_observed_at = applicability_proof.observed_at
        predicate_is_stale = (
            assignment.validity.max_age is not None
            and trusted_time
            > applicability_proof.observed_at + assignment.validity.max_age
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
            and _actor_satisfies_separation(
                assignment.separation,
                actor_principal=applicability_proof.actor_principal,
                actor_role=applicability_proof.actor_role,
                actor_identity_roles=applicability_proof.actor_identity_roles,
            )
        )
        if not proof_matches:
            return _derive_evaluation(
                assignment=assignment,
                state=ApplicableUnknown(
                    reason=UnknownReason.APPLICABILITY_PROOF_MISMATCH,
                    predicate_proof=applicability_proof,
                ),
                currency=(
                    Currency.STALE if predicate_is_stale else Currency.CURRENT
                ),
                evaluated_at=trusted_time,
                observed_at=applicability_proof.observed_at,
            )
        if not applicability_proof.is_applicable:
            return _derive_evaluation(
                assignment=assignment,
                state=NotApplicable(proof=applicability_proof),
                currency=(
                    Currency.STALE if predicate_is_stale else Currency.CURRENT
                ),
                evaluated_at=trusted_time,
                observed_at=applicability_proof.observed_at,
            )
    if attestation is None:
        return _derive_evaluation(
            assignment=assignment,
            state=ApplicableUnknown(
                reason=UnknownReason.MISSING_ATTESTATION,
                predicate_proof=(
                    applicability_proof
                    if isinstance(
                        assignment.applicability,
                        ConditionalApplicability,
                    )
                    else None
                ),
            ),
            currency=(
                Currency.STALE if predicate_is_stale else Currency.CURRENT
            ),
            evaluated_at=trusted_time,
            observed_at=predicate_observed_at or trusted_time,
        )
    _require_aware(attestation.observed_at, field="attestation.observed_at")
    if attestation.observed_at > trusted_time:
        raise EvaluationInputError("attestation observation is after trusted_time")
    attestation_is_stale = (
        assignment.validity.max_age is not None
        and trusted_time > attestation.observed_at + assignment.validity.max_age
    )
    retained_evidence_is_stale = predicate_is_stale or attestation_is_stale
    retained_observed_at = attestation.observed_at
    if predicate_observed_at is not None:
        retained_observed_at = min(
            retained_observed_at,
            predicate_observed_at,
        )
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
    elif not _actor_satisfies_separation(
        assignment.separation,
        actor_principal=attestation.actor_principal,
        actor_role=attestation.actor_role,
        actor_identity_roles=attestation.actor_identity_roles,
    ):
        mismatch_reason = UnknownReason.SEPARATION_VIOLATION
    elif attestation.outcome is AttestationOutcome.UNKNOWN:
        mismatch_reason = UnknownReason.REPORTED_UNKNOWN
    if mismatch_reason is not None:
        return _derive_evaluation(
            assignment=assignment,
            state=ApplicableUnknown(
                reason=mismatch_reason,
                attestation=attestation,
                predicate_proof=(
                    applicability_proof
                    if isinstance(
                        assignment.applicability,
                        ConditionalApplicability,
                    )
                    else None
                ),
            ),
            currency=(
                Currency.STALE
                if retained_evidence_is_stale
                else Currency.CURRENT
            ),
            evaluated_at=trusted_time,
            observed_at=retained_observed_at,
        )
    return _derive_evaluation(
        assignment=assignment,
        state=Applicable(
            outcome=attestation.outcome,
            attestation=attestation,
            predicate_proof=applicability_proof
            if isinstance(assignment.applicability, ConditionalApplicability)
            else None,
        ),
        currency=(
            Currency.STALE
            if retained_evidence_is_stale
            else Currency.CURRENT
        ),
        evaluated_at=trusted_time,
        observed_at=retained_observed_at,
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
    if trusted_time < evaluation.evaluated_at:
        raise EvaluationInputError(
            "trusted_time is before source evaluation evaluated_at"
        )
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
    return _derive_evaluation(
        assignment=evaluation.assignment,
        state=evaluation.state,
        currency=Currency.STALE,
        evaluated_at=trusted_time,
        observed_at=evaluation.observed_at,
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
