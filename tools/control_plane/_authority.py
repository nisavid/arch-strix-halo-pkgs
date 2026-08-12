from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z")


class AuthorityErrorCode(StrEnum):
    """Closed machine-readable failures across authority and promotion seams."""

    AUTHORITY_BINDING_MISMATCH = "AUTHORITY_BINDING_MISMATCH"
    AUTHORITY_CAPABILITY_CONSUMED = "AUTHORITY_CAPABILITY_CONSUMED"
    AUTHORITY_CAPABILITY_UNKNOWN = "AUTHORITY_CAPABILITY_UNKNOWN"
    AUTHORITY_EFFECT_ENFORCEMENT_MISSING = "AUTHORITY_EFFECT_ENFORCEMENT_MISSING"
    AUTHORITY_EFFECT_OBSERVATION_MISSING = "AUTHORITY_EFFECT_OBSERVATION_MISSING"
    AUTHORITY_FENCE_STALE = "AUTHORITY_FENCE_STALE"
    AUTHORITY_FORBIDDEN_EFFECT_OBSERVED = "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"
    AUTHORITY_INTENT_DUPLICATE = "AUTHORITY_INTENT_DUPLICATE"
    AUTHORITY_INTENT_MISSING = "AUTHORITY_INTENT_MISSING"
    AUTHORITY_OBSERVATION_MISSING = "AUTHORITY_OBSERVATION_MISSING"
    AUTHORITY_OPERATION_UNKNOWN = "AUTHORITY_OPERATION_UNKNOWN"
    AUTHORITY_PRESTATE_MISMATCH = "AUTHORITY_PRESTATE_MISMATCH"
    AUTHORITY_RECOVERY_BINDING_MISMATCH = "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    AUTHORITY_RECOVERY_FAILURE_MISMATCH = "AUTHORITY_RECOVERY_FAILURE_MISMATCH"
    AUTHORITY_RECOVERY_FENCE_MISSING = "AUTHORITY_RECOVERY_FENCE_MISSING"
    AUTHORITY_RECOVERY_OWNER_MISMATCH = "AUTHORITY_RECOVERY_OWNER_MISMATCH"
    AUTHORITY_RECOVERY_PHASE_INVALID = "AUTHORITY_RECOVERY_PHASE_INVALID"
    AUTHORITY_RECOVERY_PRESTATE_MISMATCH = "AUTHORITY_RECOVERY_PRESTATE_MISMATCH"
    AUTHORITY_RECOVERY_VALIDATION_FAILED = "AUTHORITY_RECOVERY_VALIDATION_FAILED"
    AUTHORITY_ROLLBACK_PHASE_INVALID = "AUTHORITY_ROLLBACK_PHASE_INVALID"
    AUTHORITY_ROLLBACK_PRESTATE_MISMATCH = "AUTHORITY_ROLLBACK_PRESTATE_MISMATCH"
    AUTHORITY_ROLLBACK_UNAVAILABLE = "AUTHORITY_ROLLBACK_UNAVAILABLE"
    AUTHORITY_ROLLBACK_VALIDATION_FAILED = "AUTHORITY_ROLLBACK_VALIDATION_FAILED"
    AUTHORITY_SUBSTRATE_FORBIDDEN = "AUTHORITY_SUBSTRATE_FORBIDDEN"
    AUTHORITY_SUBSTRATE_UNBOUND = "AUTHORITY_SUBSTRATE_UNBOUND"
    AUTHORITY_TARGET_GUARDED = "AUTHORITY_TARGET_GUARDED"
    AUTHORITY_TARGET_GUARD_MISMATCH = "AUTHORITY_TARGET_GUARD_MISMATCH"
    AUTHORITY_TERMINAL_NOT_PASS = "AUTHORITY_TERMINAL_NOT_PASS"
    AUTHORITY_TERMINAL_PHASE_INVALID = "AUTHORITY_TERMINAL_PHASE_INVALID"
    AUTHORITY_TERMINAL_STATE_MISMATCH = "AUTHORITY_TERMINAL_STATE_MISMATCH"
    AUTHORITY_TERMINAL_VALIDATOR_MISMATCH = "AUTHORITY_TERMINAL_VALIDATOR_MISMATCH"
    AUTHORITY_TOPOLOGY_INCOMPLETE = "AUTHORITY_TOPOLOGY_INCOMPLETE"
    AUTHORITY_TOPOLOGY_UNBOUND = "AUTHORITY_TOPOLOGY_UNBOUND"
    EVIDENCE_NONPROMOTIONAL = "EVIDENCE_NONPROMOTIONAL"
    PROMOTION_ATTEMPTS_INCOMPLETE = "PROMOTION_ATTEMPTS_INCOMPLETE"
    PROMOTION_ATTEMPT_DID_NOT_PASS = "PROMOTION_ATTEMPT_DID_NOT_PASS"
    PROMOTION_AUTHORITY_PROOF_MISMATCH = "PROMOTION_AUTHORITY_PROOF_MISMATCH"
    PROMOTION_CONTRACT_MISMATCH = "PROMOTION_CONTRACT_MISMATCH"
    PROMOTION_EVIDENCE_BINDING_MISMATCH = "PROMOTION_EVIDENCE_BINDING_MISMATCH"
    PROMOTION_EVIDENCE_DID_NOT_PASS = "PROMOTION_EVIDENCE_DID_NOT_PASS"
    PROMOTION_EVIDENCE_INCOMPLETE = "PROMOTION_EVIDENCE_INCOMPLETE"
    PROMOTION_EVIDENCE_NOT_CURRENT = "PROMOTION_EVIDENCE_NOT_CURRENT"
    PROMOTION_GENERATION_MISMATCH = "PROMOTION_GENERATION_MISMATCH"
    PROMOTION_INCLUSION_EDGE_MISMATCH = "PROMOTION_INCLUSION_EDGE_MISMATCH"
    PROMOTION_OPERATIONS_INCOMPLETE = "PROMOTION_OPERATIONS_INCOMPLETE"
    PROMOTION_OPERATION_BINDING_MISMATCH = "PROMOTION_OPERATION_BINDING_MISMATCH"
    PROMOTION_OPERATION_DID_NOT_PASS = "PROMOTION_OPERATION_DID_NOT_PASS"
    PROMOTION_PHASE_MISMATCH = "PROMOTION_PHASE_MISMATCH"
    PROMOTION_TARGET_MISMATCH = "PROMOTION_TARGET_MISMATCH"
    PROMOTION_TARGET_STATE_MISMATCH = "PROMOTION_TARGET_STATE_MISMATCH"


def _require_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field} must be a canonical sha256 digest")
    return value


def _require_identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase stable identifier")
    return value


class ControlAuthorityError(RuntimeError):
    """Base error with a stable machine-readable failure code."""

    def __init__(self, code: AuthorityErrorCode | str, message: str) -> None:
        self.code = AuthorityErrorCode(code)
        super().__init__(f"{self.code.value}: {message}")


class AuthorityUnavailable(ControlAuthorityError):
    """The requested authority observation or operation cannot be proven."""


class ForbiddenAuthoritySubstrate(ControlAuthorityError):
    """A mutable or target-local source was offered as production authority."""


class NonPromotionalEvidence(ControlAuthorityError):
    """Evidence is structurally useful but cannot authorize promotion."""


class AuthorityRole(StrEnum):
    SIGNER = "signer"
    EVIDENCE_STORE = "evidence_store"
    JOURNAL = "journal"
    COMPOSITE_REGISTER = "composite_register"
    WITNESS_QUORUM = "witness_quorum"
    FENCED_TARGET_LEASE = "fenced_target_lease"
    RECOVERY_ROOT = "recovery_root"
    TRUSTED_TIME = "trusted_time"


class GenerationBindingMode(StrEnum):
    """Closed generation-coordinate modes accepted by critical operations."""

    REQUIRED_GENERATION = "required_generation"
    B0_CAPTURE_SENTINEL = "b0_capture_sentinel"
    NO_GENERATION = "no_generation"


class GenerationClass(StrEnum):
    """Immutable artifact-state class bound into a critical operation."""

    B0 = "b0"
    F = "f"
    C = "c"


class LifecyclePhase(StrEnum):
    """Closed lifecycle coordinate for an operation's exact generation."""

    CAPTURED = "captured"
    FOUNDATION_VALIDATION = "foundation_validation"
    PUBLISHED = "published"
    PREVALIDATED = "prevalidated"
    ACTIVE = "active"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class GenerationBinding:
    """Bind an operation to an exact generation, or to an explicit absence."""

    mode: GenerationBindingMode
    generation_digest: str | None = None
    sentinel_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GenerationBindingMode):
            raise TypeError("mode must be a GenerationBindingMode")
        if self.mode is GenerationBindingMode.REQUIRED_GENERATION:
            if self.generation_digest is None:
                raise ValueError("required_generation requires generation_digest")
            _require_digest(self.generation_digest, field="generation_digest")
            if self.sentinel_digest is not None:
                raise ValueError("required_generation forbids sentinel_digest")
        elif self.mode is GenerationBindingMode.B0_CAPTURE_SENTINEL:
            if self.generation_digest is None or self.sentinel_digest is None:
                raise ValueError(
                    "b0_capture_sentinel requires generation_digest and sentinel_digest"
                )
            _require_digest(self.generation_digest, field="generation_digest")
            _require_digest(self.sentinel_digest, field="sentinel_digest")
        elif self.generation_digest is not None or self.sentinel_digest is not None:
            raise ValueError("no_generation forbids generation_digest and sentinel_digest")


class CriticalOperationKind(StrEnum):
    REPOSITORY_PUBLICATION = "repository_publication"
    PACKAGE_INSTALLATION = "package_installation"
    TRUST_POLICY_MUTATION = "trust_policy_mutation"
    BLOCKING_SCENARIO = "blocking_scenario"
    COMPOSITE_AUTHORITY_TRANSITION = "composite_authority_transition"
    ROLLBACK = "rollback"
    RECOVERY = "recovery"


class OperationSubjectKind(StrEnum):
    CONTROL_RECORD = "control_record"
    GENERATION = "generation"
    COMPOSITE_AUTHORITY = "composite_authority"
    GATE_OCCURRENCE = "gate_occurrence"


class OperationTargetKind(StrEnum):
    PACKAGE_REPOSITORY = "package_repository"
    ISOLATED_ROOT = "isolated_root"
    LIVE_ROOT = "live_root"
    SERVICE = "service"
    COMPOSITE_REGISTER = "composite_register"


class EffectClass(StrEnum):
    ADMISSIBLE = "admissible"
    FORBIDDEN_TRANSIENT = "forbidden_transient"
    POSTSTATE_OBSERVABLE = "poststate_observable"


class RecoveryMode(StrEnum):
    EXACT_ROLLBACK = "exact_rollback"
    RECOVERY_ONLY = "recovery_only"


class TerminalOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class OperationState(StrEnum):
    INTENT_REGISTERED = "intent_registered"
    CAPABILITY_ISSUED = "capability_issued"
    PRECHECK_FAILED = "precheck_failed"
    MUTATED_PENDING_VALIDATION = "mutated_pending_validation"
    SUCCEEDED = "succeeded"
    ROLLBACK_REQUIRED = "rollback_required"
    ROLLBACK_PENDING_VALIDATION = "rollback_pending_validation"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"
    RECOVERY_CAPABILITY_ISSUED = "recovery_capability_issued"
    RECOVERY_PENDING_VALIDATION = "recovery_pending_validation"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class OperationSubject:
    kind: OperationSubjectKind
    record_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationSubjectKind):
            raise TypeError("kind must be an OperationSubjectKind")
        _require_digest(self.record_digest, field="subject.record_digest")


@dataclass(frozen=True)
class OperationTarget:
    kind: OperationTargetKind
    target_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationTargetKind):
            raise TypeError("kind must be an OperationTargetKind")
        _require_identifier(self.target_id, field="target.target_id")


@dataclass(frozen=True)
class ProtectedStateSnapshot:
    """Content-addressed capture of one declared protected-state projection."""

    record_digest: str
    generation_digest: str
    projection_digest: str
    state_digest: str

    def __post_init__(self) -> None:
        _require_digest(self.record_digest, field="snapshot.record_digest")
        _require_digest(self.generation_digest, field="snapshot.generation_digest")
        _require_digest(self.projection_digest, field="snapshot.projection_digest")
        _require_digest(self.state_digest, field="snapshot.state_digest")


@dataclass(frozen=True)
class DeclaredEffect:
    effect_id: str
    classification: EffectClass
    projection_digest: str

    def __post_init__(self) -> None:
        _require_identifier(self.effect_id, field="effect.effect_id")
        if not isinstance(self.classification, EffectClass):
            raise TypeError("classification must be an EffectClass")
        _require_digest(self.projection_digest, field="effect.projection_digest")


@dataclass(frozen=True)
class RollbackRecoveryContract:
    """Exact rollback target or fail-closed recovery-only disposition."""

    mode: RecoveryMode
    recovery_plan_digest: str
    recovery_owner_role: str
    recovery_contract_digest: str | None = None
    recovery_target: ProtectedStateSnapshot | None = None
    recovery_destination_generation_digest: str | None = None
    recovery_origin_generation_digest: str | None = None
    rollback_target: ProtectedStateSnapshot | None = None
    rollback_plan_digest: str | None = None
    rollback_validator_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RecoveryMode):
            raise TypeError("mode must be a RecoveryMode")
        _require_digest(self.recovery_plan_digest, field="recovery_plan_digest")
        _require_identifier(self.recovery_owner_role, field="recovery_owner_role")
        if (
            self.recovery_contract_digest is None
            or self.recovery_target is None
            or self.recovery_destination_generation_digest is None
        ):
            raise ValueError(
                "recovery requires contract, target, and destination generation"
            )
        _require_digest(
            self.recovery_contract_digest,
            field="recovery_contract_digest",
        )
        if not isinstance(self.recovery_target, ProtectedStateSnapshot):
            raise TypeError("recovery_target must be a ProtectedStateSnapshot")
        _require_digest(
            self.recovery_destination_generation_digest,
            field="recovery_destination_generation_digest",
        )
        if (
            self.recovery_target.generation_digest
            != self.recovery_destination_generation_digest
        ):
            raise ValueError(
                "recovery target generation must equal recovery destination"
            )
        if self.recovery_origin_generation_digest is not None:
            _require_digest(
                self.recovery_origin_generation_digest,
                field="recovery_origin_generation_digest",
            )
        rollback_fields = (
            self.rollback_target,
            self.rollback_plan_digest,
            self.rollback_validator_digest,
        )
        if self.mode is RecoveryMode.EXACT_ROLLBACK:
            if any(value is None for value in rollback_fields):
                raise ValueError("exact_rollback requires target, plan, and validator")
            if not isinstance(self.rollback_target, ProtectedStateSnapshot):
                raise TypeError("rollback_target must be a ProtectedStateSnapshot")
            _require_digest(self.rollback_plan_digest, field="rollback_plan_digest")
            _require_digest(
                self.rollback_validator_digest,
                field="rollback_validator_digest",
            )
        elif any(value is not None for value in rollback_fields):
            raise ValueError("recovery_only forbids rollback target, plan, and validator")


_OPERATION_COORDINATES = {
    CriticalOperationKind.REPOSITORY_PUBLICATION: frozenset(
        {
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.PACKAGE_REPOSITORY,
                GenerationBindingMode.REQUIRED_GENERATION,
                generation_class,
                LifecyclePhase.PUBLISHED,
            )
            for generation_class in (GenerationClass.F, GenerationClass.C)
        }
    ),
    CriticalOperationKind.PACKAGE_INSTALLATION: frozenset(
        {
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.F,
                LifecyclePhase.FOUNDATION_VALIDATION,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.PREVALIDATED,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.LIVE_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.ACTIVE,
            ),
        }
    ),
    CriticalOperationKind.TRUST_POLICY_MUTATION: frozenset(
        {
            (
                OperationSubjectKind.CONTROL_RECORD,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.PREVALIDATED,
            ),
            (
                OperationSubjectKind.CONTROL_RECORD,
                OperationTargetKind.LIVE_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.ACTIVE,
            ),
        }
    ),
    CriticalOperationKind.BLOCKING_SCENARIO: frozenset(
        {
            (
                OperationSubjectKind.GATE_OCCURRENCE,
                target_kind,
                GenerationBindingMode.REQUIRED_GENERATION,
                generation_class,
                lifecycle_phase,
            )
            for generation_class, lifecycle_phase, target_kinds in (
                (
                    GenerationClass.F,
                    LifecyclePhase.FOUNDATION_VALIDATION,
                    (OperationTargetKind.ISOLATED_ROOT,),
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.PREVALIDATED,
                    (OperationTargetKind.ISOLATED_ROOT, OperationTargetKind.SERVICE),
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.ACTIVE,
                    (OperationTargetKind.LIVE_ROOT, OperationTargetKind.SERVICE),
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.ACCEPTED,
                    (OperationTargetKind.LIVE_ROOT, OperationTargetKind.SERVICE),
                ),
            )
            for target_kind in target_kinds
        }
    ),
    CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION: frozenset(
        {
            (
                OperationSubjectKind.COMPOSITE_AUTHORITY,
                OperationTargetKind.COMPOSITE_REGISTER,
                GenerationBindingMode.B0_CAPTURE_SENTINEL,
                GenerationClass.B0,
                LifecyclePhase.CAPTURED,
            ),
            *(
                (
                    OperationSubjectKind.COMPOSITE_AUTHORITY,
                    OperationTargetKind.COMPOSITE_REGISTER,
                    GenerationBindingMode.REQUIRED_GENERATION,
                    GenerationClass.C,
                    phase,
                )
                for phase in (
                    LifecyclePhase.PUBLISHED,
                    LifecyclePhase.PREVALIDATED,
                    LifecyclePhase.ACTIVE,
                    LifecyclePhase.ACCEPTED,
                )
            ),
        }
    ),
    CriticalOperationKind.ROLLBACK: frozenset(
        {
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.F,
                LifecyclePhase.FOUNDATION_VALIDATION,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.PREVALIDATED,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.LIVE_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.ACTIVE,
            ),
        }
    ),
    CriticalOperationKind.RECOVERY: frozenset(
        {
            (
                OperationSubjectKind.CONTROL_RECORD,
                target_kind,
                GenerationBindingMode.REQUIRED_GENERATION,
                generation_class,
                lifecycle_phase,
            )
            for generation_class, lifecycle_phase, target_kind in (
                (
                    GenerationClass.F,
                    LifecyclePhase.FOUNDATION_VALIDATION,
                    OperationTargetKind.ISOLATED_ROOT,
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.PREVALIDATED,
                    OperationTargetKind.ISOLATED_ROOT,
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.ACTIVE,
                    OperationTargetKind.LIVE_ROOT,
                ),
                (
                    GenerationClass.C,
                    LifecyclePhase.ACCEPTED,
                    OperationTargetKind.LIVE_ROOT,
                ),
            )
        }
    ),
}


def validate_operation_coordinates(
    operation_kind: CriticalOperationKind,
    subject_kind: OperationSubjectKind,
    target_kind: OperationTargetKind,
    generation_binding_mode: GenerationBindingMode,
    generation_class: GenerationClass,
    lifecycle_phase: LifecyclePhase,
) -> None:
    """Validate one exact typed critical-operation coordinate row."""

    typed_values = (
        (operation_kind, CriticalOperationKind, "operation_kind"),
        (subject_kind, OperationSubjectKind, "subject_kind"),
        (target_kind, OperationTargetKind, "target_kind"),
        (
            generation_binding_mode,
            GenerationBindingMode,
            "generation_binding_mode",
        ),
        (generation_class, GenerationClass, "generation_class"),
        (lifecycle_phase, LifecyclePhase, "lifecycle_phase"),
    )
    for value, expected_type, field_name in typed_values:
        if not isinstance(value, expected_type):
            raise TypeError(f"{field_name} must be a {expected_type.__name__}")
    actual = (
        subject_kind,
        target_kind,
        generation_binding_mode,
        generation_class,
        lifecycle_phase,
    )
    if actual not in _OPERATION_COORDINATES[operation_kind]:
        raise ValueError(
            "operation envelope coordinates are invalid for operation kind"
        )


@dataclass(frozen=True)
class SubstrateBinding:
    """A declared provider for one production authority role.

    This is configuration identity, not proof that the provider is approved or
    authoritative. ``production_authority`` remains unavailable until a
    concrete adapter verifies that proof independently.
    """

    role: AuthorityRole
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, AuthorityRole):
            raise TypeError("role must be an AuthorityRole")
        if not isinstance(self.provider, str) or not _IDENTIFIER_RE.fullmatch(
            self.provider
        ):
            raise ValueError(
                "provider must be a lowercase identifier using '-' or '_' separators"
            )


@dataclass(frozen=True)
class ProductionTopology:
    bindings: tuple[SubstrateBinding, ...]

    def __post_init__(self) -> None:
        bindings = tuple(self.bindings)
        object.__setattr__(self, "bindings", bindings)
        roles = [binding.role for binding in bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("production topology contains duplicate authority roles")


@dataclass(frozen=True)
class OperationBinding:
    """Exact typed contract for one guarded protected-state operation."""

    operation_id: str
    operation_kind: CriticalOperationKind
    generation_class: GenerationClass
    lifecycle_phase: LifecyclePhase
    intent_digest: str
    plan_digest: str
    authority_head_digest: str
    subject: OperationSubject
    target: OperationTarget
    expected_state: ProtectedStateSnapshot
    intended_state: ProtectedStateSnapshot
    generation: GenerationBinding
    effects: tuple[DeclaredEffect, ...]
    rollback: RollbackRecoveryContract
    terminal_validator_digest: str

    def __post_init__(self) -> None:
        _require_identifier(self.operation_id, field="operation_id")
        if not isinstance(self.operation_kind, CriticalOperationKind):
            raise TypeError("operation_kind must be a CriticalOperationKind")
        if not isinstance(self.generation_class, GenerationClass):
            raise TypeError("generation_class must be a GenerationClass")
        if not isinstance(self.lifecycle_phase, LifecyclePhase):
            raise TypeError("lifecycle_phase must be a LifecyclePhase")
        for field_name in (
            "intent_digest",
            "plan_digest",
            "authority_head_digest",
            "terminal_validator_digest",
        ):
            _require_digest(getattr(self, field_name), field=field_name)
        if not isinstance(self.subject, OperationSubject):
            raise TypeError("subject must be an OperationSubject")
        if not isinstance(self.target, OperationTarget):
            raise TypeError("target must be an OperationTarget")
        if not isinstance(self.expected_state, ProtectedStateSnapshot):
            raise TypeError("expected_state must be a ProtectedStateSnapshot")
        if not isinstance(self.intended_state, ProtectedStateSnapshot):
            raise TypeError("intended_state must be a ProtectedStateSnapshot")
        if not isinstance(self.generation, GenerationBinding):
            raise TypeError("generation must be a GenerationBinding")
        if not isinstance(self.rollback, RollbackRecoveryContract):
            raise TypeError("rollback must be a RollbackRecoveryContract")
        validate_operation_coordinates(
            self.operation_kind,
            self.subject.kind,
            self.target.kind,
            self.generation.mode,
            self.generation_class,
            self.lifecycle_phase,
        )
        if (
            self.subject.kind is OperationSubjectKind.GENERATION
            and self.subject.record_digest != self.generation.generation_digest
        ):
            raise ValueError("generation subject must equal the bound generation")
        effects = tuple(self.effects)
        object.__setattr__(self, "effects", effects)
        if not effects or any(not isinstance(effect, DeclaredEffect) for effect in effects):
            raise ValueError("effects must contain declared effects")
        effect_ids = [effect.effect_id for effect in effects]
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("effects contain duplicate effect_id values")
        projection = self.expected_state.projection_digest
        if self.intended_state.projection_digest != projection:
            raise ValueError("expected and intended states must use one projection")
        if self.expected_state.state_digest == self.intended_state.state_digest:
            raise ValueError("critical operation prestate and intended state must differ")
        if any(effect.projection_digest != projection for effect in effects):
            raise ValueError("every declared effect projection must match protected state")
        rollback_target = self.rollback.rollback_target
        if (
            rollback_target is not None
            and rollback_target.projection_digest != projection
        ):
            raise ValueError("rollback target must use the operation projection")
        if self.rollback.recovery_target.projection_digest != projection:
            raise ValueError("recovery target must use the operation projection")
        if (
            self.generation.generation_digest is not None
            and self.rollback.recovery_origin_generation_digest
            != self.generation.generation_digest
        ):
            raise ValueError(
                "recovery origin must equal the operation generation"
            )


@dataclass(frozen=True)
class FencedCapability:
    """Exclusive, single-use authority to perform one exact binding."""

    capability_id: str
    operation_id: str
    intent_digest: str
    plan_digest: str
    authority_head_digest: str
    subject_digest: str
    target: OperationTarget
    intended_state_digest: str
    fence_epoch: int

    def __post_init__(self) -> None:
        _require_digest(self.capability_id, field="capability_id")
        _require_identifier(self.operation_id, field="operation_id")
        for field_name in (
            "intent_digest",
            "plan_digest",
            "authority_head_digest",
            "subject_digest",
            "intended_state_digest",
        ):
            _require_digest(getattr(self, field_name), field=field_name)
        if not isinstance(self.target, OperationTarget):
            raise TypeError("target must be an OperationTarget")
        if (
            not isinstance(self.fence_epoch, int)
            or isinstance(self.fence_epoch, bool)
            or self.fence_epoch <= 0
        ):
            raise ValueError("fence_epoch must be a positive integer")


@dataclass(frozen=True)
class RecoveryCapability:
    """Fenced authority for one named successor of one proven failed operation."""

    fenced: FencedCapability
    predecessor_operation_id: str
    predecessor_failure_record_digest: str
    predecessor_fence_epoch: int
    recovery_contract_digest: str
    recovery_owner_role: str

    def __post_init__(self) -> None:
        if not isinstance(self.fenced, FencedCapability):
            raise TypeError("fenced must be a FencedCapability")
        _require_identifier(
            self.predecessor_operation_id,
            field="predecessor_operation_id",
        )
        _require_digest(
            self.predecessor_failure_record_digest,
            field="predecessor_failure_record_digest",
        )
        if (
            not isinstance(self.predecessor_fence_epoch, int)
            or isinstance(self.predecessor_fence_epoch, bool)
            or self.predecessor_fence_epoch <= 0
        ):
            raise ValueError("predecessor_fence_epoch must be a positive integer")
        _require_digest(
            self.recovery_contract_digest,
            field="recovery_contract_digest",
        )
        _require_identifier(
            self.recovery_owner_role,
            field="recovery_owner_role",
        )

    @property
    def capability_id(self) -> str:
        return self.fenced.capability_id


@dataclass(frozen=True)
class TerminalObservation:
    """Content-addressed terminal validator observation for an operation phase."""

    record_digest: str
    validator_digest: str
    observed_state: ProtectedStateSnapshot
    outcome: TerminalOutcome
    observed_effect_ids: frozenset[str] = frozenset()
    interval_enforced_effect_ids: frozenset[str] = frozenset()
    interval_violation_effect_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_digest(self.record_digest, field="terminal.record_digest")
        _require_digest(self.validator_digest, field="terminal.validator_digest")
        if not isinstance(self.observed_state, ProtectedStateSnapshot):
            raise TypeError("observed_state must be a ProtectedStateSnapshot")
        if not isinstance(self.outcome, TerminalOutcome):
            raise TypeError("outcome must be a TerminalOutcome")
        for collection_name in (
            "observed_effect_ids",
            "interval_enforced_effect_ids",
            "interval_violation_effect_ids",
        ):
            values = frozenset(getattr(self, collection_name))
            object.__setattr__(self, collection_name, values)
            for effect_id in values:
                _require_identifier(effect_id, field=collection_name)


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    state: OperationState
    record_digest: str
    failure_code: str | None = None
    failure_record_digest: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.operation_id, field="operation_id")
        if not isinstance(self.state, OperationState):
            raise TypeError("state must be an OperationState")
        _require_digest(self.record_digest, field="record_digest")
        if self.failure_record_digest is not None:
            _require_digest(
                self.failure_record_digest,
                field="failure_record_digest",
            )
        if (
            self.state is OperationState.RECOVERY_REQUIRED
            and self.failure_record_digest is None
        ):
            raise ValueError(
                "recovery-required result must bind the exact failure record"
            )


@dataclass(frozen=True)
class NonPromotionalReceipt:
    receipt_id: str
    sequence: int
    kind: str
    operation_id: str | None
    record_digest: str


@dataclass(frozen=True)
class NonPromotionalEvidenceView:
    """Evidence view produced by deterministic local or test adapters."""

    adapter_id: str
    receipts: tuple[NonPromotionalReceipt, ...]


@runtime_checkable
class AuthorityBackend(Protocol):
    """High-level seam implemented by fake and future production adapters."""

    def observe_active(self) -> ProtectedStateSnapshot: ...

    def append_intent(self, binding: OperationBinding) -> object: ...

    def acquire_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability: ...

    def guarded_compare_and_swap(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult: ...

    def terminalize_operation(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult: ...

    def acquire_rollback_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability: ...

    def execute_rollback(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult: ...

    def terminalize_rollback(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult: ...

    def acquire_recovery_capability(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        owner_role: str,
        fence_epoch: int,
    ) -> RecoveryCapability: ...

    def execute_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        capability: RecoveryCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult: ...

    def terminalize_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult: ...

    def evidence_view(self) -> object: ...


_FORBIDDEN_PROVIDERS = {
    "git",
    "mutable_local_file",
    "target_host_log",
}


def production_authority(
    topology: ProductionTopology | None = None,
) -> AuthorityBackend:
    """Bind production authority or fail before any side effect.

    Issue #104 deliberately lands the repository contract before choosing its
    independently operated substrate. Every configuration therefore remains
    unavailable in this version. Known non-authoritative providers receive a
    more specific refusal so future implementations cannot accidentally adopt
    them as a fallback.
    """

    if topology is None or not topology.bindings:
        raise AuthorityUnavailable(
            "AUTHORITY_TOPOLOGY_UNBOUND",
            "no operator-approved production authority topology is bound",
        )
    for binding in topology.bindings:
        if binding.provider in _FORBIDDEN_PROVIDERS:
            raise ForbiddenAuthoritySubstrate(
                "AUTHORITY_SUBSTRATE_FORBIDDEN",
                f"{binding.provider!r} cannot provide {binding.role.value} authority",
            )
    missing_roles = set(AuthorityRole) - {
        binding.role for binding in topology.bindings
    }
    if missing_roles:
        missing = ", ".join(sorted(role.value for role in missing_roles))
        raise AuthorityUnavailable(
            "AUTHORITY_TOPOLOGY_INCOMPLETE",
            f"production topology is missing required roles: {missing}",
        )
    raise AuthorityUnavailable(
        "AUTHORITY_SUBSTRATE_UNBOUND",
        "declared providers have no independently verified production adapter",
    )


def require_promotable(evidence_view: object) -> None:
    """Reject promotion until a verified production adapter owns this seam."""

    del evidence_view
    raise NonPromotionalEvidence(
        "EVIDENCE_NONPROMOTIONAL",
        "evidence was not produced by a verified production authority",
    )
