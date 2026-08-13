"""Instance-scoped nonpromotional adapters for repository behavioral tests.

Content and canonical derivations are deterministic within one authority
instance, but capability and receipt identities intentionally differ across
instances.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

if TYPE_CHECKING:
    from ._promotion import LifecycleCheckpoint

from ._authority import (
    AuthorityUnavailable,
    CapabilityType,
    CriticalOperationKind,
    DeclaredEffect,
    EffectClass,
    FencedCapability,
    GenerationBinding,
    GenerationBindingMode,
    LifecyclePhase,
    NonPromotionalEvidenceView,
    NonPromotionalReceipt,
    OperationBinding,
    OperationResult,
    OperationState,
    OperationSubject,
    OperationTarget,
    ProtectedStateSnapshot,
    RecoveryCapability,
    RecoveryMode,
    RollbackRecoveryContract,
    RollbackTarget,
    TerminalObservation,
    TerminalOutcome,
    _require_digest,
    _require_identifier,
    _require_positive_integer,
)

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _synchronized(
    method: Callable[Concatenate[InMemoryAuthority, _P], _R],
) -> Callable[Concatenate[InMemoryAuthority, _P], _R]:
    @wraps(method)
    def locked(
        self: InMemoryAuthority,
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        with self._lock:
            return method(self, *args, **kwargs)

    return locked


@dataclass(frozen=True, slots=True)
class JournalEntry:
    sequence: int
    kind: str
    operation_id: str | None
    record_digest: str
    active_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence",
            _require_positive_integer(self.sequence, field="sequence"),
        )
        object.__setattr__(
            self,
            "kind",
            _require_identifier(self.kind, field="kind"),
        )
        if self.operation_id is not None:
            object.__setattr__(
                self,
                "operation_id",
                _require_identifier(self.operation_id, field="operation_id"),
            )
        object.__setattr__(
            self,
            "record_digest",
            _require_digest(self.record_digest, field="record_digest"),
        )
        if self.active_digest is not None:
            object.__setattr__(
                self,
                "active_digest",
                _require_digest(self.active_digest, field="active_digest"),
            )


@dataclass(frozen=True, slots=True)
class _RecoveryFailureProvenance:
    result: OperationResult
    fence_epoch: int
    active_state: ProtectedStateSnapshot


@dataclass(frozen=True, slots=True)
class _RecoveryIncidentLink:
    predecessor_operation_id: str
    predecessor_failure_record_digest: str
    predecessor_fence_epoch: int
    predecessor_active_state: ProtectedStateSnapshot


def _canonical_fence_epoch(fence_epoch: object) -> int:
    try:
        return _require_positive_integer(fence_epoch, field="fence_epoch")
    except (TypeError, ValueError) as error:
        raise AuthorityUnavailable(
            "AUTHORITY_FENCE_STALE",
            "the fence epoch must be a positive integer",
        ) from error


def _snapshot_entry(entry: JournalEntry) -> JournalEntry:
    if not isinstance(entry, JournalEntry):
        raise TypeError("entry must be a JournalEntry")
    return JournalEntry(
        sequence=entry.sequence,
        kind=entry.kind,
        operation_id=entry.operation_id,
        record_digest=entry.record_digest,
        active_digest=entry.active_digest,
    )


def _snapshot_identity(snapshot: ProtectedStateSnapshot) -> tuple[str, ...]:
    return (
        snapshot.record_digest,
        snapshot.generation_digest,
        snapshot.lifecycle_phase.value,
        snapshot.projection_digest,
        snapshot.state_digest,
        snapshot.process_epoch or "",
    )


def _snapshot_state(snapshot: ProtectedStateSnapshot) -> ProtectedStateSnapshot:
    if not isinstance(snapshot, ProtectedStateSnapshot):
        raise TypeError("snapshot must be a ProtectedStateSnapshot")
    return ProtectedStateSnapshot(
        record_digest=snapshot.record_digest,
        generation_digest=snapshot.generation_digest,
        lifecycle_phase=snapshot.lifecycle_phase,
        projection_digest=snapshot.projection_digest,
        state_digest=snapshot.state_digest,
        process_epoch=snapshot.process_epoch,
    )


def _snapshot_terminal(observation: TerminalObservation) -> TerminalObservation:
    if not isinstance(observation, TerminalObservation):
        raise TypeError("observation must be a TerminalObservation")
    return TerminalObservation(
        record_digest=observation.record_digest,
        operation_digest=observation.operation_digest,
        capability_digest=observation.capability_digest,
        validator_digest=observation.validator_digest,
        observed_state=_snapshot_state(observation.observed_state),
        outcome=observation.outcome,
        observed_effect_ids=frozenset(observation.observed_effect_ids),
        interval_enforced_effect_ids=frozenset(
            observation.interval_enforced_effect_ids
        ),
        interval_violation_effect_ids=frozenset(
            observation.interval_violation_effect_ids
        ),
    )


def _snapshot_target(target: OperationTarget) -> OperationTarget:
    if not isinstance(target, OperationTarget):
        raise TypeError("target must be an OperationTarget")
    return OperationTarget(kind=target.kind, target_id=target.target_id)


def _snapshot_capability(capability: FencedCapability) -> FencedCapability:
    if not isinstance(capability, FencedCapability):
        raise TypeError("capability must be a FencedCapability")
    return FencedCapability(
        capability_id=capability.capability_id,
        capability_type=capability.capability_type,
        operation_digest=capability.operation_digest,
        operation_id=capability.operation_id,
        intent_digest=capability.intent_digest,
        plan_digest=capability.plan_digest,
        authority_head_digest=capability.authority_head_digest,
        subject_digest=capability.subject_digest,
        target=_snapshot_target(capability.target),
        intended_state=_snapshot_state(capability.intended_state),
        fence_epoch=capability.fence_epoch,
    )


def _snapshot_result(result: OperationResult) -> OperationResult:
    if not isinstance(result, OperationResult):
        raise TypeError("result must be an OperationResult")
    return OperationResult(
        operation_id=result.operation_id,
        state=result.state,
        record_digest=result.record_digest,
        failure_code=result.failure_code,
        failure_record_digest=result.failure_record_digest,
    )


def _snapshot_recovery_capability(
    capability: RecoveryCapability,
) -> RecoveryCapability:
    if not isinstance(capability, RecoveryCapability):
        raise TypeError("capability must be a RecoveryCapability")
    return RecoveryCapability(
        fenced=_snapshot_capability(capability.fenced),
        predecessor_operation_id=capability.predecessor_operation_id,
        predecessor_failure_record_digest=(
            capability.predecessor_failure_record_digest
        ),
        predecessor_fence_epoch=capability.predecessor_fence_epoch,
        recovery_contract_digest=capability.recovery_contract_digest,
        recovery_owner_role=capability.recovery_owner_role,
    )


def seal_authority_issued_checkpoint_for_testing(
    checkpoint: LifecycleCheckpoint,
) -> LifecycleCheckpoint:
    """Seal a validated checkpoint for repository tests only."""

    from ._promotion import _seal_authority_issued_checkpoint

    return _seal_authority_issued_checkpoint(checkpoint)


def issue_lifecycle_checkpoint_for_testing(
    **kwargs: Any,
) -> LifecycleCheckpoint:
    """Issue a lifecycle checkpoint through the private test allocator only."""

    from ._promotion import _issue_lifecycle_checkpoint

    return _issue_lifecycle_checkpoint(**kwargs)


def _snapshot_receipt(receipt: NonPromotionalReceipt) -> NonPromotionalReceipt:
    if not isinstance(receipt, NonPromotionalReceipt):
        raise TypeError("receipt must be a NonPromotionalReceipt")
    return NonPromotionalReceipt(
        receipt_id=receipt.receipt_id,
        sequence=receipt.sequence,
        kind=receipt.kind,
        operation_id=receipt.operation_id,
        record_digest=receipt.record_digest,
    )


def _snapshot_rollback(contract: RollbackRecoveryContract) -> RollbackRecoveryContract:
    if not isinstance(contract, RollbackRecoveryContract):
        raise TypeError("rollback must be a RollbackRecoveryContract")
    rollback_target = contract.rollback_target
    recovery_target = contract.recovery_target
    return RollbackRecoveryContract(
        mode=contract.mode,
        recovery_plan_digest=contract.recovery_plan_digest,
        recovery_owner_role=contract.recovery_owner_role,
        recovery_contract_digest=contract.recovery_contract_digest,
        recovery_target=(
            _snapshot_state(recovery_target) if recovery_target is not None else None
        ),
        recovery_destination_generation_digest=(
            contract.recovery_destination_generation_digest
        ),
        recovery_origin_generation_digest=contract.recovery_origin_generation_digest,
        rollback_target=(
            RollbackTarget(
                protected_state=_snapshot_state(rollback_target.protected_state),
                destination_generation_digest=(
                    rollback_target.destination_generation_digest
                ),
            )
            if rollback_target is not None
            else None
        ),
        rollback_plan_digest=contract.rollback_plan_digest,
        rollback_validator_digest=contract.rollback_validator_digest,
    )


def _snapshot_binding(binding: OperationBinding) -> OperationBinding:
    if not isinstance(binding, OperationBinding):
        raise TypeError("binding must be an OperationBinding")
    subject = binding.subject
    generation = binding.generation
    if not isinstance(subject, OperationSubject):
        raise TypeError("subject must be an OperationSubject")
    if not isinstance(generation, GenerationBinding):
        raise TypeError("generation must be a GenerationBinding")
    return OperationBinding(
        operation_id=binding.operation_id,
        operation_kind=binding.operation_kind,
        generation_class=binding.generation_class,
        lifecycle_phase=binding.lifecycle_phase,
        intent_digest=binding.intent_digest,
        plan_digest=binding.plan_digest,
        authority_head_digest=binding.authority_head_digest,
        subject=OperationSubject(
            kind=subject.kind,
            record_digest=subject.record_digest,
        ),
        target=_snapshot_target(binding.target),
        expected_state=_snapshot_state(binding.expected_state),
        intended_state=_snapshot_state(binding.intended_state),
        generation=GenerationBinding(
            mode=generation.mode,
            generation_digest=generation.generation_digest,
            sentinel_digest=generation.sentinel_digest,
        ),
        effects=tuple(
            DeclaredEffect(
                effect_id=effect.effect_id,
                classification=effect.classification,
                projection_digest=effect.projection_digest,
            )
            for effect in binding.effects
        ),
        rollback=_snapshot_rollback(binding.rollback),
        terminal_validator_digest=binding.terminal_validator_digest,
    )


class InMemoryAuthority:
    """Strict instance-scoped nonpromotional authority for behavioral tests.

    Content and canonical derivations are deterministic within one authority
    instance, but capability and receipt identities intentionally differ across
    instances.
    """

    adapter_id = "in_memory_nonpromotional_v1"

    def __init__(
        self,
        *,
        initial_active_state: ProtectedStateSnapshot | None = None,
        initial_target: OperationTarget | None = None,
    ) -> None:
        self._lock = RLock()
        self._authority_instance_digest = (
            "sha256:" + hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        )
        self._state_record_claims: dict[
            str,
            tuple[
                str,
                LifecyclePhase,
                str,
                str,
                str | None,
                OperationTarget | None,
            ],
        ] = {}
        self._active_states: dict[OperationTarget, ProtectedStateSnapshot] = {}
        self._unbound_initial_active_state: ProtectedStateSnapshot | None = None
        if initial_active_state is not None:
            initial_state = _snapshot_state(initial_active_state)
            if initial_target is None:
                self._unbound_initial_active_state = initial_state
            else:
                target = _snapshot_target(initial_target)
                self._claim_state_records(initial_state, target=target)
                self._active_states[target] = initial_state
        elif initial_target is not None:
            target = _snapshot_target(initial_target)
            raise ValueError(
                f"initial_target {target.target_id!r} requires initial_active_state"
            )
        self._entries: list[JournalEntry] = []
        self._receipts: list[NonPromotionalReceipt] = []
        self._pending: dict[str, OperationBinding] = {}
        self._bindings: dict[str, OperationBinding] = {}
        self._states: dict[str, OperationState] = {}
        self._issued_capabilities: dict[str, FencedCapability] = {}
        self._issued_recovery_capabilities: dict[str, RecoveryCapability] = {}
        self._consumed_capabilities: set[str] = set()
        self._terminal_capabilities: dict[str, FencedCapability] = {}
        self._terminal_records: dict[str, tuple[object, ...]] = {}
        self._guarded_targets: dict[OperationTarget, tuple[str, str, int]] = {}
        self._last_fence_epochs: dict[OperationTarget, int] = {}
        self._operation_fence_epochs: dict[str, int] = {}
        self._recovery_failures: dict[str, _RecoveryFailureProvenance] = {}
        self._recovery_predecessors: dict[str, _RecoveryIncidentLink] = {}

    @property
    @_synchronized
    def journal_entries(self) -> tuple[JournalEntry, ...]:
        return tuple(_snapshot_entry(item) for item in self._entries)

    @_synchronized
    def observe_active(
        self,
        target: OperationTarget | None = None,
    ) -> ProtectedStateSnapshot:
        if target is None:
            if len(self._active_states) == 1:
                return _snapshot_state(next(iter(self._active_states.values())))
            if (
                not self._active_states
                and self._unbound_initial_active_state is not None
            ):
                return _snapshot_state(self._unbound_initial_active_state)
            raise AuthorityUnavailable(
                "AUTHORITY_OBSERVATION_MISSING",
                "an exact target is required unless one observation is unambiguous",
            )
        target = _snapshot_target(target)
        snapshot = self._active_states.get(target)
        if snapshot is None and self._unbound_initial_active_state is not None:
            if self._active_states:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the legacy initial active state is ambiguous across targets",
                )
            self._claim_state_records(
                self._unbound_initial_active_state,
                target=target,
            )
            snapshot = self._unbound_initial_active_state
            self._active_states[target] = snapshot
            self._unbound_initial_active_state = None
        if snapshot is None:
            raise AuthorityUnavailable(
                "AUTHORITY_OBSERVATION_MISSING",
                "the fake has no configured active-state observation for the target",
            )
        return _snapshot_state(snapshot)

    @_synchronized
    def configure_active(
        self,
        target: OperationTarget,
        snapshot: ProtectedStateSnapshot | None,
    ) -> None:
        target = _snapshot_target(target)
        if snapshot is None:
            self._active_states.pop(target, None)
            return
        retained = _snapshot_state(snapshot)
        self._claim_state_records(retained, target=target)
        self._active_states[target] = retained

    def _observe_active_snapshot(
        self,
        target: OperationTarget,
    ) -> ProtectedStateSnapshot:
        snapshot = self._read_active_snapshot(target)
        self._claim_state_records(snapshot, target=target)
        return snapshot

    def _read_active_snapshot(
        self,
        target: OperationTarget,
    ) -> ProtectedStateSnapshot:
        return _snapshot_state(self.observe_active(target))

    def _claim_state_records(
        self,
        *snapshots: ProtectedStateSnapshot,
        target: OperationTarget | None = None,
    ) -> None:
        self._state_record_claims = self._proposed_state_record_claims(
            *snapshots,
            target=target,
        )

    def _proposed_state_record_claims(
        self,
        *snapshots: ProtectedStateSnapshot,
        target: OperationTarget | None = None,
    ) -> dict[
        str,
        tuple[
            str,
            LifecyclePhase,
            str,
            str,
            str | None,
            OperationTarget | None,
        ],
    ]:
        claimed_target = _snapshot_target(target) if target is not None else None
        proposed = dict(self._state_record_claims)
        for supplied in snapshots:
            snapshot = _snapshot_state(supplied)
            content = (
                snapshot.generation_digest,
                snapshot.lifecycle_phase,
                snapshot.projection_digest,
                snapshot.state_digest,
                snapshot.process_epoch,
            )
            existing = proposed.get(snapshot.record_digest)
            if existing is not None and (
                existing[:5] != content
                or (
                    claimed_target is not None
                    and existing[5] is not None
                    and existing[5] != claimed_target
                )
            ):
                raise AuthorityUnavailable(
                    "AUTHORITY_STATE_RECORD_REBOUND",
                    "protected-state record digest cannot bind distinct content or target",
                )
            retained_target = (
                existing[5]
                if existing is not None and existing[5] is not None
                else claimed_target
            )
            proposed[snapshot.record_digest] = (*content, retained_target)
        return proposed

    @_synchronized
    def operation_state(self, operation_id: str) -> OperationState:
        operation_id = _require_identifier(operation_id, field="operation_id")
        try:
            return self._states[operation_id]
        except KeyError as error:
            raise AuthorityUnavailable(
                "AUTHORITY_OPERATION_UNKNOWN",
                f"operation {operation_id!r} is not registered",
            ) from error

    @_synchronized
    def append_record(
        self,
        record_digest: str,
        *,
        kind: str = "evidence_record",
    ) -> NonPromotionalReceipt:
        return self._append(
            kind=kind,
            operation_id=None,
            record_digest=record_digest,
        )

    @_synchronized
    def append_intent(self, binding: OperationBinding) -> NonPromotionalReceipt:
        binding = _snapshot_binding(binding)
        if binding.operation_id in self._bindings:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_DUPLICATE",
                f"operation {binding.operation_id!r} is already registered",
            )
        state_records = [
            binding.expected_state,
            binding.intended_state,
            binding.rollback.recovery_target,
        ]
        if binding.rollback.rollback_target is not None:
            state_records.append(binding.rollback.rollback_target.protected_state)
        assert all(state is not None for state in state_records)
        unbound_initial_state = self._unbound_initial_active_state
        if unbound_initial_state is not None and self._active_states:
            raise AuthorityUnavailable(
                "AUTHORITY_OBSERVATION_MISSING",
                "the legacy initial active state is ambiguous across targets",
            )
        if unbound_initial_state is not None:
            state_records.append(unbound_initial_state)
        self._claim_state_records(
            *(state for state in state_records if state is not None),
            target=binding.target,
        )
        if unbound_initial_state is not None:
            self._active_states[binding.target] = unbound_initial_state
            self._unbound_initial_active_state = None
        self._pending[binding.operation_id] = binding
        self._bindings[binding.operation_id] = binding
        self._states[binding.operation_id] = OperationState.INTENT_REGISTERED
        return self._append(
            kind="operation_intent",
            operation_id=binding.operation_id,
            record_digest=binding.intent_digest,
        )

    @_synchronized
    def acquire_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability:
        binding = self._pending_binding(binding)
        self._require_forward_operation(binding)
        fence_epoch = _canonical_fence_epoch(fence_epoch)
        guarded_by = self._guarded_targets.get(binding.target)
        if guarded_by is not None and guarded_by[0] == binding.operation_id:
            retained_capability = self._issued_capabilities.get(guarded_by[1])
            if (
                retained_capability is None
                or self._states.get(binding.operation_id)
                is not OperationState.CAPABILITY_ISSUED
                or guarded_by != self._guard_owner(retained_capability)
            ):
                raise AuthorityUnavailable(
                    "AUTHORITY_TARGET_GUARD_MISMATCH",
                    "the existing operation guard has no exact issued capability",
                )
            if fence_epoch != retained_capability.fence_epoch:
                raise AuthorityUnavailable(
                    "AUTHORITY_FENCE_STALE",
                    "the requested fence differs from the issued capability",
                )
            return _snapshot_capability(retained_capability)
        elif guarded_by is not None:
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARDED",
                f"target is already guarded by operation {guarded_by[0]!r}",
            )
        if fence_epoch <= self._last_fence_epochs.get(binding.target, 0):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the capability fence does not advance the target epoch",
            )
        self._observe_active_snapshot(binding.target)
        material = "\0".join(
            (
                self._authority_instance_digest,
                CapabilityType.OPERATION.value,
                binding.digest(),
                binding.operation_id,
                binding.intent_digest,
                binding.plan_digest,
                binding.authority_head_digest,
                binding.subject.record_digest,
                binding.target.kind.value,
                binding.target.target_id,
                *_snapshot_identity(binding.intended_state),
                str(fence_epoch),
            )
        ).encode("utf-8")
        capability = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            capability_type=CapabilityType.OPERATION,
            operation_digest=binding.digest(),
            operation_id=binding.operation_id,
            intent_digest=binding.intent_digest,
            plan_digest=binding.plan_digest,
            authority_head_digest=binding.authority_head_digest,
            subject_digest=binding.subject.record_digest,
            target=binding.target,
            intended_state=binding.intended_state,
            fence_epoch=fence_epoch,
        )
        retained_capability = _snapshot_capability(capability)
        self._issued_capabilities[capability.capability_id] = retained_capability
        self._guarded_targets[binding.target] = self._guard_owner(retained_capability)
        self._last_fence_epochs[binding.target] = fence_epoch
        self._operation_fence_epochs[binding.operation_id] = fence_epoch
        self._states[binding.operation_id] = OperationState.CAPABILITY_ISSUED
        self._append(
            kind="fenced_capability",
            operation_id=binding.operation_id,
            record_digest=capability.capability_id,
        )
        return _snapshot_capability(retained_capability)

    @_synchronized
    def guarded_compare_and_swap(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
        binding = _snapshot_binding(binding)
        self._require_forward_operation(binding)
        observed_state = _snapshot_state(observed_state)
        capability = _snapshot_capability(capability)
        if capability.capability_id in self._consumed_capabilities:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_CONSUMED",
                "the fenced capability has already been consumed",
            )
        issued = self._issued_capabilities.get(capability.capability_id)
        if issued is None or issued != capability:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_UNKNOWN",
                "the fenced capability was not issued by this authority",
            )
        binding = self._pending_binding(binding)
        if not self._capability_matches(binding, capability):
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "the capability does not bind the registered operation",
            )
        self._require_guard_owner(binding, capability)
        active = self._read_active_snapshot(binding.target)
        self._claim_state_records(observed_state, active, target=binding.target)
        self._issued_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        if observed_state != binding.expected_state or active != observed_state:
            receipt = self._append_precheck_failure(
                binding,
                "AUTHORITY_PRESTATE_MISMATCH",
            )
            self._states[binding.operation_id] = OperationState.PRECHECK_FAILED
            self._pending.pop(binding.operation_id)
            self._release_guard(binding, capability)
            raise AuthorityUnavailable(
                "AUTHORITY_PRESTATE_MISMATCH",
                "the observed state does not match the intent's expected state",
            )
        self._active_states[binding.target] = _snapshot_state(binding.intended_state)
        self._pending.pop(binding.operation_id)
        self._terminal_capabilities[binding.operation_id] = _snapshot_capability(issued)
        self._states[binding.operation_id] = OperationState.MUTATED_PENDING_VALIDATION
        receipt = self._append(
            kind="guarded_transition",
            operation_id=binding.operation_id,
            record_digest=binding.intended_state.record_digest,
        )
        return OperationResult(
            operation_id=binding.operation_id,
            state=OperationState.MUTATED_PENDING_VALIDATION,
            record_digest=receipt.receipt_id,
        )

    @_synchronized
    def terminalize_operation(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        observation = _snapshot_terminal(observation)
        binding = self._registered_binding(
            binding,
            code="AUTHORITY_BINDING_MISMATCH",
            message="terminal observation does not bind the registered operation",
        )
        self._require_forward_operation(binding)
        if (
            self._states.get(binding.operation_id)
            is not OperationState.MUTATED_PENDING_VALIDATION
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_TERMINAL_PHASE_INVALID",
                "operation is not awaiting terminal validation",
            )
        terminal_capability = self._require_terminal_binding(
            binding,
            observation,
            capability_type=CapabilityType.OPERATION,
            code="AUTHORITY_BINDING_MISMATCH",
            message="terminal observation does not bind the consumed capability",
        )
        self._require_guard_owner(binding, terminal_capability)
        required_effects = {
            effect.effect_id
            for effect in binding.effects
            if effect.classification is EffectClass.POSTSTATE_OBSERVABLE
        }
        declared_effects = {effect.effect_id for effect in binding.effects}
        forbidden_effects = {
            effect.effect_id
            for effect in binding.effects
            if effect.classification is EffectClass.FORBIDDEN_TRANSIENT
        }
        active = self._read_active_snapshot(binding.target)
        failure_code: str | None = None
        if observation.validator_digest != binding.terminal_validator_digest:
            failure_code = "AUTHORITY_TERMINAL_VALIDATOR_MISMATCH"
        elif observation.outcome is not TerminalOutcome.PASS:
            failure_code = "AUTHORITY_TERMINAL_NOT_PASS"
        elif (
            observation.observed_state != binding.intended_state
            or active != observation.observed_state
        ):
            failure_code = "AUTHORITY_TERMINAL_STATE_MISMATCH"
        elif not required_effects <= observation.observed_effect_ids:
            failure_code = "AUTHORITY_EFFECT_OBSERVATION_MISSING"
        elif not forbidden_effects <= observation.interval_enforced_effect_ids:
            failure_code = "AUTHORITY_EFFECT_ENFORCEMENT_MISSING"
        elif (
            not observation.observed_effect_ids <= declared_effects
            or not observation.interval_enforced_effect_ids <= declared_effects
            or not observation.interval_violation_effect_ids <= declared_effects
            or forbidden_effects & observation.observed_effect_ids
            or forbidden_effects & observation.interval_violation_effect_ids
        ):
            failure_code = "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"

        if failure_code is None:
            state = OperationState.SUCCEEDED
            kind = "operation_succeeded"
        elif binding.rollback.mode is RecoveryMode.EXACT_ROLLBACK:
            state = OperationState.ROLLBACK_REQUIRED
            kind = "operation_terminal_failed"
        else:
            state = OperationState.RECOVERY_REQUIRED
            kind = "operation_recovery_required"
        self._commit_terminal_claims(
            observation,
            observation.observed_state,
            active,
            target=binding.target,
        )
        if failure_code is None:
            self._release_guard(binding, terminal_capability)
        self._terminal_capabilities.pop(binding.operation_id, None)
        self._states[binding.operation_id] = state
        receipt = self._append(
            kind=kind,
            operation_id=binding.operation_id,
            record_digest=observation.record_digest,
        )
        result = OperationResult(
            operation_id=binding.operation_id,
            state=state,
            record_digest=receipt.receipt_id,
            failure_code=failure_code,
            failure_record_digest=(
                observation.record_digest if failure_code is not None else None
            ),
        )
        if state is OperationState.RECOVERY_REQUIRED:
            self._remember_recovery_failure(binding, result, active)
        return result

    @_synchronized
    def acquire_rollback_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability:
        binding = self._registered_binding(
            binding,
            code="AUTHORITY_BINDING_MISMATCH",
            message="rollback does not bind the registered operation",
        )
        if (
            self._states.get(binding.operation_id)
            is not OperationState.ROLLBACK_REQUIRED
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "operation does not require rollback",
            )
        if binding.rollback.mode is not RecoveryMode.EXACT_ROLLBACK:
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_UNAVAILABLE",
                "operation has no exact rollback contract",
            )
        guarded_by = self._require_operation_guard(binding)
        fence_epoch = _canonical_fence_epoch(fence_epoch)
        retained_capability = self._issued_capabilities.get(guarded_by[1])
        if (
            retained_capability is not None
            and retained_capability.capability_type is CapabilityType.ROLLBACK
        ):
            if guarded_by != self._guard_owner(retained_capability):
                raise AuthorityUnavailable(
                    "AUTHORITY_TARGET_GUARD_MISMATCH",
                    "the rollback guard has no exact issued capability",
                )
            if fence_epoch == retained_capability.fence_epoch:
                return _snapshot_capability(retained_capability)
        last_epoch = self._last_fence_epochs.get(binding.target, 0)
        if fence_epoch <= last_epoch:
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the rollback fence does not advance the target epoch",
            )
        rollback_target = binding.rollback.rollback_target
        assert rollback_target is not None
        protected_state = rollback_target.protected_state
        material = "\0".join(
            (
                self._authority_instance_digest,
                CapabilityType.ROLLBACK.value,
                binding.digest(),
                binding.operation_id,
                binding.intent_digest,
                binding.rollback.rollback_plan_digest or "",
                binding.authority_head_digest,
                binding.subject.record_digest,
                binding.target.kind.value,
                binding.target.target_id,
                *_snapshot_identity(protected_state),
                str(fence_epoch),
            )
        ).encode("utf-8")
        capability = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            capability_type=CapabilityType.ROLLBACK,
            operation_digest=binding.digest(),
            operation_id=binding.operation_id,
            intent_digest=binding.intent_digest,
            plan_digest=binding.rollback.rollback_plan_digest or "",
            authority_head_digest=binding.authority_head_digest,
            subject_digest=binding.subject.record_digest,
            target=binding.target,
            intended_state=protected_state,
            fence_epoch=fence_epoch,
        )
        superseded_ids = (
            capability_id
            for capability_id, issued in self._issued_capabilities.items()
            if issued.capability_type is CapabilityType.ROLLBACK
            and (
                issued.target == binding.target
                or issued.operation_id == binding.operation_id
            )
        )
        for capability_id in tuple(superseded_ids):
            self._issued_capabilities.pop(capability_id)
        retained_capability = _snapshot_capability(capability)
        self._issued_capabilities[capability.capability_id] = retained_capability
        self._last_fence_epochs[binding.target] = fence_epoch
        self._operation_fence_epochs[binding.operation_id] = fence_epoch
        self._guarded_targets[binding.target] = self._guard_owner(retained_capability)
        self._append(
            kind="rollback_capability",
            operation_id=binding.operation_id,
            record_digest=capability.capability_id,
        )
        return _snapshot_capability(retained_capability)

    @_synchronized
    def execute_rollback(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
        observed_state = _snapshot_state(observed_state)
        capability = _snapshot_capability(capability)
        binding = self._registered_binding(
            binding,
            code="AUTHORITY_BINDING_MISMATCH",
            message="rollback does not bind the registered operation",
        )
        if (
            self._states.get(binding.operation_id)
            is not OperationState.ROLLBACK_REQUIRED
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "operation does not require rollback",
            )
        if capability.capability_id in self._consumed_capabilities:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_CONSUMED",
                "the rollback capability has already been consumed",
            )
        if capability.fence_epoch != self._last_fence_epochs.get(
            binding.target
        ) or capability.fence_epoch != self._operation_fence_epochs.get(
            binding.operation_id
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the rollback capability does not hold the current fence epoch",
            )
        issued = self._issued_capabilities.get(capability.capability_id)
        rollback_target = binding.rollback.rollback_target
        rollback_plan = binding.rollback.rollback_plan_digest
        protected_state = (
            rollback_target.protected_state if rollback_target is not None else None
        )
        if (
            issued != capability
            or protected_state is None
            or rollback_plan is None
            or capability.capability_type is not CapabilityType.ROLLBACK
            or capability.operation_digest != binding.digest()
            or capability.operation_id != binding.operation_id
            or capability.plan_digest != rollback_plan
            or capability.authority_head_digest != binding.authority_head_digest
            or capability.subject_digest != binding.subject.record_digest
            or capability.target != binding.target
            or capability.intended_state != protected_state
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "rollback capability does not bind the exact rollback contract",
            )
        self._require_guard_owner(binding, capability)
        active = self._read_active_snapshot(binding.target)
        self._claim_state_records(observed_state, active, target=binding.target)
        self._issued_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        if observed_state != binding.intended_state or active != observed_state:
            self._states[binding.operation_id] = OperationState.RECOVERY_REQUIRED
            receipt = self._append_precheck_failure(
                binding,
                "AUTHORITY_ROLLBACK_PRESTATE_MISMATCH",
            )
            result = OperationResult(
                operation_id=binding.operation_id,
                state=OperationState.RECOVERY_REQUIRED,
                record_digest=receipt.receipt_id,
                failure_code="AUTHORITY_ROLLBACK_PRESTATE_MISMATCH",
                failure_record_digest=receipt.record_digest,
            )
            self._remember_recovery_failure(binding, result, active)
            return result
        self._active_states[binding.target] = _snapshot_state(protected_state)
        self._terminal_capabilities[binding.operation_id] = _snapshot_capability(issued)
        self._states[binding.operation_id] = OperationState.ROLLBACK_PENDING_VALIDATION
        receipt = self._append(
            kind="rollback_transition",
            operation_id=binding.operation_id,
            record_digest=protected_state.record_digest,
        )
        return OperationResult(
            operation_id=binding.operation_id,
            state=OperationState.ROLLBACK_PENDING_VALIDATION,
            record_digest=receipt.receipt_id,
        )

    @_synchronized
    def terminalize_rollback(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        observation = _snapshot_terminal(observation)
        binding = self._registered_binding(
            binding,
            code="AUTHORITY_BINDING_MISMATCH",
            message="rollback does not bind the registered operation",
        )
        if (
            self._states.get(binding.operation_id)
            is not OperationState.ROLLBACK_PENDING_VALIDATION
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "rollback is not awaiting terminal validation",
            )
        terminal_capability = self._require_terminal_binding(
            binding,
            observation,
            capability_type=CapabilityType.ROLLBACK,
            code="AUTHORITY_BINDING_MISMATCH",
            message="rollback observation does not bind the consumed capability",
        )
        self._require_guard_owner(binding, terminal_capability)
        rollback_target = binding.rollback.rollback_target
        target = (
            rollback_target.protected_state if rollback_target is not None else None
        )
        validator = binding.rollback.rollback_validator_digest
        declared_effects = {effect.effect_id for effect in binding.effects}
        required_effects = {
            effect.effect_id
            for effect in binding.effects
            if effect.classification is EffectClass.POSTSTATE_OBSERVABLE
        }
        forbidden_effects = {
            effect.effect_id
            for effect in binding.effects
            if effect.classification is EffectClass.FORBIDDEN_TRANSIENT
        }
        active = self._read_active_snapshot(binding.target)
        passed = (
            target is not None
            and validator is not None
            and observation.validator_digest == validator
            and observation.outcome is TerminalOutcome.PASS
            and observation.observed_state == target
            and active == target
            and observation.observed_effect_ids <= declared_effects
            and observation.interval_enforced_effect_ids <= declared_effects
            and observation.interval_violation_effect_ids <= declared_effects
            and required_effects <= observation.observed_effect_ids
            and forbidden_effects <= observation.interval_enforced_effect_ids
            and not forbidden_effects & observation.observed_effect_ids
            and not forbidden_effects & observation.interval_violation_effect_ids
        )
        state = (
            OperationState.ROLLED_BACK if passed else OperationState.RECOVERY_REQUIRED
        )
        self._commit_terminal_claims(
            observation,
            observation.observed_state,
            active,
            target=binding.target,
        )
        self._terminal_capabilities.pop(binding.operation_id, None)
        self._states[binding.operation_id] = state
        if passed:
            self._release_guard(binding, terminal_capability)
        receipt = self._append(
            kind=("rollback_succeeded" if passed else "rollback_recovery_required"),
            operation_id=binding.operation_id,
            record_digest=observation.record_digest,
        )
        result = OperationResult(
            operation_id=binding.operation_id,
            state=state,
            record_digest=receipt.receipt_id,
            failure_code=(None if passed else "AUTHORITY_ROLLBACK_VALIDATION_FAILED"),
            failure_record_digest=(None if passed else observation.record_digest),
        )
        if state is OperationState.RECOVERY_REQUIRED:
            self._remember_recovery_failure(binding, result, active)
        return result

    @_synchronized
    def acquire_recovery_capability(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        owner_role: str,
        fence_epoch: int,
    ) -> RecoveryCapability:
        failure = _snapshot_result(failure)
        owner_role = _require_identifier(owner_role, field="owner_role")
        fence_epoch = _canonical_fence_epoch(fence_epoch)
        failed_binding = self._registered_binding(
            failed_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery predecessor does not bind the registered operation",
        )
        recovery_binding = self._registered_binding(
            recovery_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery successor does not bind the registered operation",
        )
        if (
            self._states.get(failed_binding.operation_id)
            is not OperationState.RECOVERY_REQUIRED
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_PHASE_INVALID",
                "the predecessor does not require recovery",
            )
        remembered = self._recovery_failures.get(failed_binding.operation_id)
        if remembered is None or remembered.result != failure:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_FAILURE_MISMATCH",
                "recovery does not bind the proven predecessor failure terminal",
            )
        predecessor_fence_epoch = remembered.fence_epoch
        failure_record_digest = failure.failure_record_digest
        assert failure_record_digest is not None
        requested_link = _RecoveryIncidentLink(
            predecessor_operation_id=failed_binding.operation_id,
            predecessor_failure_record_digest=failure_record_digest,
            predecessor_fence_epoch=predecessor_fence_epoch,
            predecessor_active_state=_snapshot_state(remembered.active_state),
        )
        contract = failed_binding.rollback
        if owner_role != contract.recovery_owner_role:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_OWNER_MISMATCH",
                "the acting role is not the named recovery owner",
            )
        if self._pending.get(recovery_binding.operation_id) != recovery_binding:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                "the recovery successor has no matching registered intent",
            )
        if (
            recovery_binding.operation_kind is not CriticalOperationKind.RECOVERY
            or recovery_binding.target != failed_binding.target
            or recovery_binding.generation_class is not failed_binding.generation_class
            or recovery_binding.plan_digest != contract.recovery_plan_digest
            or recovery_binding.subject.record_digest
            != contract.recovery_contract_digest
            or recovery_binding.expected_state != remembered.active_state
            or recovery_binding.intended_state != contract.recovery_target
            or recovery_binding.generation.mode is not failed_binding.generation.mode
            or (
                failed_binding.generation.mode
                is GenerationBindingMode.B0_CAPTURE_SENTINEL
                and recovery_binding.generation.sentinel_digest
                != failed_binding.generation.sentinel_digest
            )
            or recovery_binding.generation.generation_digest
            != contract.recovery_destination_generation_digest
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "the successor does not bind the exact recovery contract",
            )
        guarded_by = self._guarded_targets.get(failed_binding.target)
        if guarded_by is not None and guarded_by[0] == recovery_binding.operation_id:
            retained_capability = self._issued_recovery_capabilities.get(guarded_by[1])
            if (
                retained_capability is None
                or self._states.get(recovery_binding.operation_id)
                is not OperationState.RECOVERY_CAPABILITY_ISSUED
                or guarded_by != self._guard_owner(retained_capability.fenced)
            ):
                raise AuthorityUnavailable(
                    "AUTHORITY_TARGET_GUARD_MISMATCH",
                    "the recovery guard has no exact issued capability",
                )
            if (
                self._recovery_predecessors.get(recovery_binding.operation_id)
                != requested_link
            ):
                raise AuthorityUnavailable(
                    "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                    "recovery reissuance cannot change the incident predecessor",
                )
            if fence_epoch != retained_capability.fenced.fence_epoch:
                raise AuthorityUnavailable(
                    "AUTHORITY_FENCE_STALE",
                    "the requested fence differs from the issued recovery capability",
                )
            return _snapshot_recovery_capability(retained_capability)
        else:
            self._require_operation_guard(failed_binding)
        last_epoch = self._last_fence_epochs.get(failed_binding.target, 0)
        if fence_epoch <= max(last_epoch, predecessor_fence_epoch):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the recovery fence does not advance the failed operation epoch",
            )
        recovery_contract_digest = contract.recovery_contract_digest
        assert recovery_contract_digest is not None
        material = "\0".join(
            (
                self._authority_instance_digest,
                CapabilityType.RECOVERY.value,
                recovery_binding.digest(),
                recovery_binding.operation_id,
                recovery_binding.intent_digest,
                recovery_binding.plan_digest,
                recovery_binding.authority_head_digest,
                recovery_binding.subject.record_digest,
                recovery_binding.target.kind.value,
                recovery_binding.target.target_id,
                *_snapshot_identity(recovery_binding.intended_state),
                failed_binding.operation_id,
                failure_record_digest,
                str(predecessor_fence_epoch),
                *_snapshot_identity(remembered.active_state),
                recovery_contract_digest,
                owner_role,
                str(fence_epoch),
            )
        ).encode("utf-8")
        fenced = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            capability_type=CapabilityType.RECOVERY,
            operation_digest=recovery_binding.digest(),
            operation_id=recovery_binding.operation_id,
            intent_digest=recovery_binding.intent_digest,
            plan_digest=recovery_binding.plan_digest,
            authority_head_digest=recovery_binding.authority_head_digest,
            subject_digest=recovery_binding.subject.record_digest,
            target=recovery_binding.target,
            intended_state=recovery_binding.intended_state,
            fence_epoch=fence_epoch,
        )
        capability = RecoveryCapability(
            fenced=fenced,
            predecessor_operation_id=failed_binding.operation_id,
            predecessor_failure_record_digest=failure_record_digest,
            predecessor_fence_epoch=predecessor_fence_epoch,
            recovery_contract_digest=recovery_contract_digest,
            recovery_owner_role=owner_role,
        )
        retained_capability = _snapshot_recovery_capability(capability)
        self._issued_recovery_capabilities[capability.capability_id] = (
            retained_capability
        )
        self._last_fence_epochs[recovery_binding.target] = fence_epoch
        self._operation_fence_epochs[recovery_binding.operation_id] = fence_epoch
        self._guarded_targets[recovery_binding.target] = self._guard_owner(
            retained_capability.fenced
        )
        self._recovery_predecessors[recovery_binding.operation_id] = requested_link
        self._states[recovery_binding.operation_id] = (
            OperationState.RECOVERY_CAPABILITY_ISSUED
        )
        self._append(
            kind="recovery_capability",
            operation_id=recovery_binding.operation_id,
            record_digest=capability.capability_id,
        )
        return _snapshot_recovery_capability(retained_capability)

    @_synchronized
    def execute_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        capability: RecoveryCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
        observed_state = _snapshot_state(observed_state)
        failure = _snapshot_result(failure)
        capability = _snapshot_recovery_capability(capability)
        failed_binding = self._registered_binding(
            failed_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery predecessor does not bind the registered operation",
        )
        recovery_binding = self._registered_binding(
            recovery_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery successor does not bind the registered operation",
        )
        issued = self._issued_recovery_capabilities.get(capability.capability_id)
        if capability.capability_id in self._consumed_capabilities:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_CONSUMED",
                "the recovery capability has already been consumed",
            )
        if issued != capability:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_UNKNOWN",
                "the recovery capability was not issued by this authority",
            )
        remembered = self._recovery_failures.get(failed_binding.operation_id)
        failure_record_digest = failure.failure_record_digest
        link = self._recovery_predecessors.get(recovery_binding.operation_id)
        if (
            remembered is None
            or remembered.result != failure
            or failure_record_digest is None
            or capability.predecessor_operation_id != failed_binding.operation_id
            or capability.predecessor_failure_record_digest != failure_record_digest
            or capability.predecessor_fence_epoch != remembered.fence_epoch
            or link
            != _RecoveryIncidentLink(
                predecessor_operation_id=failed_binding.operation_id,
                predecessor_failure_record_digest=failure_record_digest,
                predecessor_fence_epoch=remembered.fence_epoch,
                predecessor_active_state=remembered.active_state,
            )
            or recovery_binding.expected_state != remembered.active_state
            or capability.fenced.capability_type is not CapabilityType.RECOVERY
            or capability.fenced.operation_digest != recovery_binding.digest()
            or capability.fenced.operation_id != recovery_binding.operation_id
            or capability.fenced.intent_digest != recovery_binding.intent_digest
            or capability.fenced.plan_digest != recovery_binding.plan_digest
            or capability.fenced.authority_head_digest
            != recovery_binding.authority_head_digest
            or capability.fenced.subject_digest
            != recovery_binding.subject.record_digest
            or capability.fenced.target != recovery_binding.target
            or capability.fenced.intended_state != recovery_binding.intended_state
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "the capability does not bind the exact failed recovery chain",
            )
        self._require_guard_owner(recovery_binding, capability.fenced)
        active = self._read_active_snapshot(recovery_binding.target)
        self._claim_state_records(
            observed_state,
            active,
            target=recovery_binding.target,
        )
        self._issued_recovery_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        if (
            observed_state != recovery_binding.expected_state
            or active != observed_state
        ):
            receipt = self._append_precheck_failure(
                recovery_binding,
                "AUTHORITY_RECOVERY_PRESTATE_MISMATCH",
            )
            result = OperationResult(
                operation_id=recovery_binding.operation_id,
                state=OperationState.RECOVERY_REQUIRED,
                record_digest=receipt.receipt_id,
                failure_code="AUTHORITY_RECOVERY_PRESTATE_MISMATCH",
                failure_record_digest=receipt.record_digest,
            )
            self._pending.pop(recovery_binding.operation_id, None)
            self._states[recovery_binding.operation_id] = (
                OperationState.RECOVERY_REQUIRED
            )
            self._remember_recovery_failure(recovery_binding, result, active)
            return result
        if active != recovery_binding.intended_state:
            self._active_states[recovery_binding.target] = _snapshot_state(
                recovery_binding.intended_state
            )
        self._pending.pop(recovery_binding.operation_id, None)
        self._terminal_capabilities[recovery_binding.operation_id] = capability.fenced
        self._states[recovery_binding.operation_id] = (
            OperationState.RECOVERY_PENDING_VALIDATION
        )
        receipt = self._append(
            kind="recovery_transition",
            operation_id=recovery_binding.operation_id,
            record_digest=recovery_binding.intended_state.record_digest,
        )
        return OperationResult(
            operation_id=recovery_binding.operation_id,
            state=OperationState.RECOVERY_PENDING_VALIDATION,
            record_digest=receipt.receipt_id,
        )

    @_synchronized
    def terminalize_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        observation = _snapshot_terminal(observation)
        failed_binding = self._registered_binding(
            failed_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery predecessor does not bind the registered operation",
        )
        recovery_binding = self._registered_binding(
            recovery_binding,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery successor does not bind the registered operation",
        )
        if (
            self._states.get(recovery_binding.operation_id)
            is not OperationState.RECOVERY_PENDING_VALIDATION
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_PHASE_INVALID",
                "recovery is not awaiting terminal validation",
            )
        link = self._recovery_predecessors.get(recovery_binding.operation_id)
        remembered = self._recovery_failures.get(failed_binding.operation_id)
        failure_record_digest = (
            remembered.result.failure_record_digest if remembered is not None else None
        )
        expected_link = (
            _RecoveryIncidentLink(
                predecessor_operation_id=failed_binding.operation_id,
                predecessor_failure_record_digest=failure_record_digest,
                predecessor_fence_epoch=remembered.fence_epoch,
                predecessor_active_state=remembered.active_state,
            )
            if failure_record_digest is not None and remembered is not None
            else None
        )
        if link != expected_link:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "recovery no longer binds the exact failed predecessor",
            )
        terminal_capability = self._require_terminal_binding(
            recovery_binding,
            observation,
            capability_type=CapabilityType.RECOVERY,
            code="AUTHORITY_RECOVERY_BINDING_MISMATCH",
            message="recovery observation does not bind the consumed capability",
        )
        self._require_guard_owner(recovery_binding, terminal_capability)
        required_effects = {
            effect.effect_id
            for effect in recovery_binding.effects
            if effect.classification is EffectClass.POSTSTATE_OBSERVABLE
        }
        declared_effects = {effect.effect_id for effect in recovery_binding.effects}
        forbidden_effects = {
            effect.effect_id
            for effect in recovery_binding.effects
            if effect.classification is EffectClass.FORBIDDEN_TRANSIENT
        }
        active = self._read_active_snapshot(recovery_binding.target)
        passed = (
            observation.validator_digest == recovery_binding.terminal_validator_digest
            and observation.outcome is TerminalOutcome.PASS
            and observation.observed_state == recovery_binding.intended_state
            and active == recovery_binding.intended_state
            and observation.observed_effect_ids <= declared_effects
            and observation.interval_enforced_effect_ids <= declared_effects
            and observation.interval_violation_effect_ids <= declared_effects
            and required_effects <= observation.observed_effect_ids
            and forbidden_effects <= observation.interval_enforced_effect_ids
            and not forbidden_effects & observation.observed_effect_ids
            and not forbidden_effects & observation.interval_violation_effect_ids
        )
        state = OperationState.RECOVERED if passed else OperationState.RECOVERY_REQUIRED
        incident_operation_ids = (
            self._recovery_incident_operation_ids(recovery_binding) if passed else ()
        )
        self._commit_terminal_claims(
            observation,
            observation.observed_state,
            active,
            target=recovery_binding.target,
        )
        self._terminal_capabilities.pop(recovery_binding.operation_id, None)
        if passed:
            for operation_id in incident_operation_ids:
                self._states[operation_id] = OperationState.RECOVERED
            self._release_guard(recovery_binding, terminal_capability)
        else:
            self._states[recovery_binding.operation_id] = state
        receipt = self._append(
            kind=("recovery_succeeded" if passed else "recovery_still_required"),
            operation_id=recovery_binding.operation_id,
            record_digest=observation.record_digest,
        )
        result = OperationResult(
            operation_id=recovery_binding.operation_id,
            state=state,
            record_digest=receipt.receipt_id,
            failure_code=(None if passed else "AUTHORITY_RECOVERY_VALIDATION_FAILED"),
            failure_record_digest=(None if passed else observation.record_digest),
        )
        if not passed:
            self._remember_recovery_failure(recovery_binding, result, active)
        return result

    @_synchronized
    def evidence_view(self) -> NonPromotionalEvidenceView:
        return NonPromotionalEvidenceView(
            adapter_id=self.adapter_id,
            receipts=tuple(_snapshot_receipt(item) for item in self._receipts),
        )

    def _append_precheck_failure(
        self,
        binding: OperationBinding,
        code: str,
    ) -> NonPromotionalReceipt:
        material = (f"{binding.intent_digest}\0{binding.operation_id}\0{code}").encode()
        failure_digest = "sha256:" + hashlib.sha256(material).hexdigest()
        return self._append(
            kind="precheck_failed",
            operation_id=binding.operation_id,
            record_digest=failure_digest,
        )

    def _registered_binding(
        self,
        binding: OperationBinding,
        *,
        code: str,
        message: str,
    ) -> OperationBinding:
        candidate = _snapshot_binding(binding)
        registered = self._bindings.get(candidate.operation_id)
        if registered != candidate:
            raise AuthorityUnavailable(code, message)
        return registered

    def _pending_binding(self, binding: OperationBinding) -> OperationBinding:
        candidate = _snapshot_binding(binding)
        registered = self._pending.get(candidate.operation_id)
        if registered is None:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                f"operation {candidate.operation_id!r} has no registered intent",
            )
        if registered != candidate:
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "the transition binding differs from its registered intent",
            )
        return registered

    @staticmethod
    def _require_forward_operation(binding: OperationBinding) -> None:
        if binding.operation_kind is CriticalOperationKind.RECOVERY:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_PHASE_INVALID",
                "recovery operations require the dedicated recovery authority path",
            )

    def _require_terminal_binding(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
        *,
        capability_type: CapabilityType,
        code: str,
        message: str,
    ) -> FencedCapability:
        capability = self._terminal_capabilities.get(binding.operation_id)
        if (
            capability is None
            or capability.capability_type is not capability_type
            or observation.operation_digest != binding.digest()
            or observation.capability_digest != capability.capability_id
        ):
            raise AuthorityUnavailable(code, message)
        return capability

    @staticmethod
    def _guard_owner(capability: FencedCapability) -> tuple[str, str, int]:
        return (
            capability.operation_id,
            capability.capability_id,
            capability.fence_epoch,
        )

    def _require_operation_guard(
        self,
        binding: OperationBinding,
    ) -> tuple[str, str, int]:
        guarded_by = self._guarded_targets.get(binding.target)
        operation_fence = self._operation_fence_epochs.get(binding.operation_id)
        if (
            guarded_by is None
            or guarded_by[0] != binding.operation_id
            or guarded_by[2] != operation_fence
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARD_MISMATCH",
                "the operation no longer exclusively guards the target",
            )
        return guarded_by

    def _require_guard_owner(
        self,
        binding: OperationBinding,
        capability: FencedCapability,
    ) -> None:
        if self._guarded_targets.get(binding.target) != self._guard_owner(capability):
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARD_MISMATCH",
                "the capability does not own the exact target guard",
            )
        if (
            self._last_fence_epochs.get(binding.target) != capability.fence_epoch
            or self._operation_fence_epochs.get(binding.operation_id)
            != capability.fence_epoch
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the capability does not hold the current target fence",
            )

    def _release_guard(
        self,
        binding: OperationBinding,
        capability: FencedCapability,
    ) -> None:
        self._require_guard_owner(binding, capability)
        self._guarded_targets.pop(binding.target)

    def _commit_terminal_claims(
        self,
        observation: TerminalObservation,
        *snapshots: ProtectedStateSnapshot,
        target: OperationTarget,
    ) -> None:
        proposed_state_records = self._proposed_state_record_claims(
            *snapshots,
            target=target,
        )
        proposed_terminal_records = self._proposed_terminal_records(observation)
        self._state_record_claims = proposed_state_records
        self._terminal_records = proposed_terminal_records

    def _proposed_terminal_records(
        self,
        observation: TerminalObservation,
    ) -> dict[str, tuple[object, ...]]:
        canonical = (
            observation.operation_digest,
            observation.capability_digest,
            observation.validator_digest,
            *_snapshot_identity(observation.observed_state),
            observation.outcome.value,
            tuple(sorted(observation.observed_effect_ids)),
            tuple(sorted(observation.interval_enforced_effect_ids)),
            tuple(sorted(observation.interval_violation_effect_ids)),
        )
        proposed = dict(self._terminal_records)
        existing = proposed.get(observation.record_digest)
        if existing is not None:
            disposition = "reused" if existing == canonical else "rebound"
            raise AuthorityUnavailable(
                "AUTHORITY_TERMINAL_RECORD_REUSED",
                f"terminal record digest was already {disposition}",
            )
        proposed[observation.record_digest] = canonical
        return proposed

    def _remember_recovery_failure(
        self,
        binding: OperationBinding,
        result: OperationResult,
        active_state: ProtectedStateSnapshot,
    ) -> None:
        fence_epoch = self._operation_fence_epochs.get(binding.operation_id)
        if fence_epoch is None:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_FENCE_MISSING",
                "the recovery-required result has no proven operation fence",
            )
        self._recovery_failures[binding.operation_id] = _RecoveryFailureProvenance(
            result=_snapshot_result(result),
            fence_epoch=fence_epoch,
            active_state=_snapshot_state(active_state),
        )

    def _recovery_incident_operation_ids(
        self,
        terminal_binding: OperationBinding,
    ) -> tuple[str, ...]:
        guarded_by = self._guarded_targets.get(terminal_binding.target)
        if guarded_by is None or guarded_by[0] != terminal_binding.operation_id:
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARD_MISMATCH",
                "the terminal recovery no longer exclusively guards the target",
            )
        operation_ids: list[str] = []
        seen: set[str] = set()
        current_id = terminal_binding.operation_id
        while True:
            if current_id in seen:
                raise AuthorityUnavailable(
                    "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                    "the recovery incident ancestry contains a cycle",
                )
            seen.add(current_id)
            operation_ids.append(current_id)
            current = self._bindings.get(current_id)
            if current is None or current.target != terminal_binding.target:
                raise AuthorityUnavailable(
                    "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                    "the recovery incident ancestry is incomplete or changes target",
                )
            link = self._recovery_predecessors.get(current_id)
            if link is None:
                if current.operation_kind is CriticalOperationKind.RECOVERY:
                    raise AuthorityUnavailable(
                        "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                        "the recovery incident ancestry has no original operation",
                    )
                break
            predecessor_id = link.predecessor_operation_id
            predecessor = self._bindings.get(predecessor_id)
            remembered = self._recovery_failures.get(predecessor_id)
            if (
                predecessor is None
                or predecessor.target != terminal_binding.target
                or self._states.get(predecessor_id)
                is not OperationState.RECOVERY_REQUIRED
                or remembered is None
                or remembered.result.failure_record_digest
                != link.predecessor_failure_record_digest
                or remembered.fence_epoch != link.predecessor_fence_epoch
                or remembered.active_state != link.predecessor_active_state
                or current.expected_state != link.predecessor_active_state
            ):
                raise AuthorityUnavailable(
                    "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                    "the recovery incident ancestry is corrupt",
                )
            current_id = predecessor_id
        return tuple(operation_ids)

    @staticmethod
    def _capability_matches(
        binding: OperationBinding,
        capability: FencedCapability,
    ) -> bool:
        return (
            capability.capability_type is CapabilityType.OPERATION
            and capability.operation_digest == binding.digest()
            and capability.operation_id == binding.operation_id
            and capability.intent_digest == binding.intent_digest
            and capability.plan_digest == binding.plan_digest
            and capability.authority_head_digest == binding.authority_head_digest
            and capability.subject_digest == binding.subject.record_digest
            and capability.target == binding.target
            and capability.intended_state == binding.intended_state
        )

    def _append(
        self,
        *,
        kind: str,
        operation_id: str | None,
        record_digest: str,
    ) -> NonPromotionalReceipt:
        kind = _require_identifier(kind, field="kind")
        if operation_id is not None:
            operation_id = _require_identifier(operation_id, field="operation_id")
        record_digest = _require_digest(record_digest, field="record_digest")
        sequence = len(self._entries) + 1
        receipt_material = "\0".join(
            (
                self._authority_instance_digest,
                self.adapter_id,
                str(sequence),
                kind,
                operation_id or "",
                record_digest,
            )
        ).encode("utf-8")
        receipt_id = "sha256:" + hashlib.sha256(receipt_material).hexdigest()
        entry = JournalEntry(
            sequence=sequence,
            kind=kind,
            operation_id=operation_id,
            record_digest=record_digest,
            active_digest=self._journal_active_digest(operation_id),
        )
        receipt = NonPromotionalReceipt(
            receipt_id=receipt_id,
            sequence=sequence,
            kind=kind,
            operation_id=operation_id,
            record_digest=record_digest,
        )
        self._entries.append(_snapshot_entry(entry))
        retained_receipt = _snapshot_receipt(receipt)
        self._receipts.append(retained_receipt)
        return _snapshot_receipt(retained_receipt)

    def _journal_active_digest(self, operation_id: str | None) -> str | None:
        if operation_id is None:
            return None
        binding = self._bindings.get(operation_id)
        if binding is None:
            return None
        active = self._active_states.get(binding.target)
        return active.state_digest if active is not None else None


__all__ = [
    "InMemoryAuthority",
    "JournalEntry",
    "issue_lifecycle_checkpoint_for_testing",
    "seal_authority_issued_checkpoint_for_testing",
]
