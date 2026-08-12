"""Deterministic nonpromotional adapters for repository behavioral tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ._authority import (
    AuthorityUnavailable,
    CriticalOperationKind,
    EffectClass,
    FencedCapability,
    NonPromotionalEvidenceView,
    NonPromotionalReceipt,
    OperationBinding,
    OperationResult,
    OperationState,
    ProtectedStateSnapshot,
    RecoveryCapability,
    RecoveryMode,
    TerminalObservation,
    TerminalOutcome,
)


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    kind: str
    operation_id: str | None
    record_digest: str
    active_digest: str | None


class InMemoryAuthority:
    """A strict in-memory adapter that can never produce promotional evidence."""

    adapter_id = "in_memory_nonpromotional_v1"

    def __init__(
        self,
        *,
        initial_active_state: ProtectedStateSnapshot | None = None,
    ) -> None:
        self._active_state = initial_active_state
        self._entries: list[JournalEntry] = []
        self._receipts: list[NonPromotionalReceipt] = []
        self._pending: dict[str, OperationBinding] = {}
        self._bindings: dict[str, OperationBinding] = {}
        self._states: dict[str, OperationState] = {}
        self._issued_capabilities: dict[str, FencedCapability] = {}
        self._issued_recovery_capabilities: dict[str, RecoveryCapability] = {}
        self._consumed_capabilities: set[str] = set()
        self._guarded_targets: dict[object, str] = {}
        self._last_fence_epochs: dict[object, int] = {}
        self._operation_fence_epochs: dict[str, int] = {}
        self._recovery_failures: dict[str, tuple[OperationResult, int]] = {}
        self._recovery_predecessors: dict[str, tuple[str, str]] = {}

    @property
    def journal_entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def observe_active(self) -> ProtectedStateSnapshot:
        if self._active_state is None:
            raise AuthorityUnavailable(
                "AUTHORITY_OBSERVATION_MISSING",
                "the fake has no configured active-state observation",
            )
        return self._active_state

    def operation_state(self, operation_id: str) -> OperationState:
        try:
            return self._states[operation_id]
        except KeyError as error:
            raise AuthorityUnavailable(
                "AUTHORITY_OPERATION_UNKNOWN",
                f"operation {operation_id!r} is not registered",
            ) from error

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

    def append_intent(self, binding: OperationBinding) -> NonPromotionalReceipt:
        if binding.operation_id in self._bindings:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_DUPLICATE",
                f"operation {binding.operation_id!r} is already registered",
            )
        self._pending[binding.operation_id] = binding
        self._bindings[binding.operation_id] = binding
        self._states[binding.operation_id] = OperationState.INTENT_REGISTERED
        return self._append(
            kind="operation_intent",
            operation_id=binding.operation_id,
            record_digest=binding.intent_digest,
        )

    def acquire_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability:
        registered = self._pending.get(binding.operation_id)
        if registered is None:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                f"operation {binding.operation_id!r} has no registered intent",
            )
        if registered != binding:
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "the transition binding differs from its registered intent",
            )
        guarded_by = self._guarded_targets.get(binding.target)
        if guarded_by is not None:
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARDED",
                f"target is already guarded by operation {guarded_by!r}",
            )
        if (
            not isinstance(fence_epoch, int)
            or isinstance(fence_epoch, bool)
            or fence_epoch <= self._last_fence_epochs.get(binding.target, 0)
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the capability fence does not advance the target epoch",
            )
        material = "\0".join(
            (
                binding.operation_id,
                binding.intent_digest,
                binding.plan_digest,
                binding.authority_head_digest,
                binding.subject.record_digest,
                binding.target.kind.value,
                binding.target.target_id,
                binding.intended_state.state_digest,
                str(fence_epoch),
            )
        ).encode("utf-8")
        capability = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            operation_id=binding.operation_id,
            intent_digest=binding.intent_digest,
            plan_digest=binding.plan_digest,
            authority_head_digest=binding.authority_head_digest,
            subject_digest=binding.subject.record_digest,
            target=binding.target,
            intended_state_digest=binding.intended_state.state_digest,
            fence_epoch=fence_epoch,
        )
        self._issued_capabilities[capability.capability_id] = capability
        self._guarded_targets[binding.target] = binding.operation_id
        self._last_fence_epochs[binding.target] = fence_epoch
        self._operation_fence_epochs[binding.operation_id] = fence_epoch
        self._states[binding.operation_id] = OperationState.CAPABILITY_ISSUED
        self._append(
            kind="fenced_capability",
            operation_id=binding.operation_id,
            record_digest=capability.capability_id,
        )
        return capability

    def guarded_compare_and_swap(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
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
        registered = self._pending.get(binding.operation_id)
        if registered is None:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                f"operation {binding.operation_id!r} has no registered intent",
            )
        if registered != binding or not self._capability_matches(binding, capability):
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "the capability does not bind the registered operation",
            )
        self._issued_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        active = self.observe_active()
        if observed_state != binding.expected_state or active != observed_state:
            receipt = self._append_precheck_failure(
                binding,
                "AUTHORITY_PRESTATE_MISMATCH",
            )
            self._states[binding.operation_id] = OperationState.PRECHECK_FAILED
            self._pending.pop(binding.operation_id)
            self._guarded_targets.pop(binding.target, None)
            raise AuthorityUnavailable(
                "AUTHORITY_PRESTATE_MISMATCH",
                "the observed state does not match the intent's expected state",
            )
        self._active_state = binding.intended_state
        self._pending.pop(binding.operation_id)
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

    def terminalize_operation(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        if self._bindings.get(binding.operation_id) != binding:
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "terminal observation does not bind the registered operation",
            )
        if self._states.get(binding.operation_id) is not OperationState.MUTATED_PENDING_VALIDATION:
            raise AuthorityUnavailable(
                "AUTHORITY_TERMINAL_PHASE_INVALID",
                "operation is not awaiting terminal validation",
            )
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
        failure_code: str | None = None
        if observation.validator_digest != binding.terminal_validator_digest:
            failure_code = "AUTHORITY_TERMINAL_VALIDATOR_MISMATCH"
        elif observation.outcome is not TerminalOutcome.PASS:
            failure_code = "AUTHORITY_TERMINAL_NOT_PASS"
        elif (
            observation.observed_state != binding.intended_state
            or self.observe_active() != observation.observed_state
        ):
            failure_code = "AUTHORITY_TERMINAL_STATE_MISMATCH"
        elif not required_effects <= observation.observed_effect_ids:
            failure_code = "AUTHORITY_EFFECT_OBSERVATION_MISSING"
        elif not forbidden_effects <= observation.interval_enforced_effect_ids:
            failure_code = "AUTHORITY_EFFECT_ENFORCEMENT_MISSING"
        elif forbidden_effects & observation.interval_violation_effect_ids:
            failure_code = "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"

        if failure_code is None:
            state = OperationState.SUCCEEDED
            kind = "operation_succeeded"
            self._guarded_targets.pop(binding.target, None)
        elif binding.rollback.mode is RecoveryMode.EXACT_ROLLBACK:
            state = OperationState.ROLLBACK_REQUIRED
            kind = "operation_terminal_failed"
        else:
            state = OperationState.RECOVERY_REQUIRED
            kind = "operation_recovery_required"
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
                observation.record_digest
                if state is OperationState.RECOVERY_REQUIRED
                else None
            ),
        )
        if state is OperationState.RECOVERY_REQUIRED:
            self._remember_recovery_failure(binding, result)
        return result

    def acquire_rollback_capability(
        self,
        binding: OperationBinding,
        *,
        fence_epoch: int,
    ) -> FencedCapability:
        if self._states.get(binding.operation_id) is not OperationState.ROLLBACK_REQUIRED:
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "operation does not require rollback",
            )
        if binding.rollback.mode is not RecoveryMode.EXACT_ROLLBACK:
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_UNAVAILABLE",
                "operation has no exact rollback contract",
            )
        last_epoch = self._last_fence_epochs.get(binding.target, 0)
        if (
            not isinstance(fence_epoch, int)
            or isinstance(fence_epoch, bool)
            or fence_epoch <= last_epoch
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the rollback fence does not advance the target epoch",
            )
        rollback_target = binding.rollback.rollback_target
        assert rollback_target is not None
        material = "\0".join(
            (
                binding.operation_id,
                binding.intent_digest,
                binding.rollback.rollback_plan_digest or "",
                binding.authority_head_digest,
                binding.subject.record_digest,
                binding.target.kind.value,
                binding.target.target_id,
                rollback_target.state_digest,
                str(fence_epoch),
            )
        ).encode("utf-8")
        capability = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            operation_id=binding.operation_id,
            intent_digest=binding.intent_digest,
            plan_digest=binding.rollback.rollback_plan_digest or "",
            authority_head_digest=binding.authority_head_digest,
            subject_digest=binding.subject.record_digest,
            target=binding.target,
            intended_state_digest=rollback_target.state_digest,
            fence_epoch=fence_epoch,
        )
        self._issued_capabilities[capability.capability_id] = capability
        self._last_fence_epochs[binding.target] = fence_epoch
        self._operation_fence_epochs[binding.operation_id] = fence_epoch
        return capability

    def execute_rollback(
        self,
        binding: OperationBinding,
        *,
        capability: FencedCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
        if self._states.get(binding.operation_id) is not OperationState.ROLLBACK_REQUIRED:
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "operation does not require rollback",
            )
        if capability.capability_id in self._consumed_capabilities:
            raise AuthorityUnavailable(
                "AUTHORITY_CAPABILITY_CONSUMED",
                "the rollback capability has already been consumed",
            )
        issued = self._issued_capabilities.get(capability.capability_id)
        rollback_target = binding.rollback.rollback_target
        rollback_plan = binding.rollback.rollback_plan_digest
        if (
            issued != capability
            or rollback_target is None
            or rollback_plan is None
            or capability.operation_id != binding.operation_id
            or capability.plan_digest != rollback_plan
            or capability.authority_head_digest != binding.authority_head_digest
            or capability.subject_digest != binding.subject.record_digest
            or capability.target != binding.target
            or capability.intended_state_digest != rollback_target.state_digest
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "rollback capability does not bind the exact rollback contract",
            )
        self._issued_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        if observed_state != binding.intended_state or self.observe_active() != observed_state:
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
            self._remember_recovery_failure(binding, result)
            return result
        self._active_state = rollback_target
        self._states[binding.operation_id] = OperationState.ROLLBACK_PENDING_VALIDATION
        receipt = self._append(
            kind="rollback_transition",
            operation_id=binding.operation_id,
            record_digest=rollback_target.record_digest,
        )
        return OperationResult(
            operation_id=binding.operation_id,
            state=OperationState.ROLLBACK_PENDING_VALIDATION,
            record_digest=receipt.receipt_id,
        )

    def terminalize_rollback(
        self,
        binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        if (
            self._states.get(binding.operation_id)
            is not OperationState.ROLLBACK_PENDING_VALIDATION
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_ROLLBACK_PHASE_INVALID",
                "rollback is not awaiting terminal validation",
            )
        target = binding.rollback.rollback_target
        validator = binding.rollback.rollback_validator_digest
        passed = (
            target is not None
            and validator is not None
            and observation.validator_digest == validator
            and observation.outcome is TerminalOutcome.PASS
            and observation.observed_state == target
            and self.observe_active() == target
        )
        state = OperationState.ROLLED_BACK if passed else OperationState.RECOVERY_REQUIRED
        self._states[binding.operation_id] = state
        if passed:
            self._guarded_targets.pop(binding.target, None)
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
            self._remember_recovery_failure(binding, result)
        return result

    def acquire_recovery_capability(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        owner_role: str,
        fence_epoch: int,
    ) -> RecoveryCapability:
        if self._bindings.get(failed_binding.operation_id) != failed_binding:
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "recovery predecessor does not bind the registered operation",
            )
        if self._states.get(failed_binding.operation_id) is not OperationState.RECOVERY_REQUIRED:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_PHASE_INVALID",
                "the predecessor does not require recovery",
            )
        remembered = self._recovery_failures.get(failed_binding.operation_id)
        if remembered is None or remembered[0] != failure:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_FAILURE_MISMATCH",
                "recovery does not bind the proven predecessor failure terminal",
            )
        predecessor_fence_epoch = remembered[1]
        failure_record_digest = failure.failure_record_digest
        assert failure_record_digest is not None
        contract = failed_binding.rollback
        if owner_role != contract.recovery_owner_role:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_OWNER_MISMATCH",
                "the acting role is not the named recovery owner",
            )
        registered = self._pending.get(recovery_binding.operation_id)
        if registered != recovery_binding:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                "the recovery successor has no matching registered intent",
            )
        if (
            recovery_binding.operation_kind is not CriticalOperationKind.RECOVERY
            or recovery_binding.target != failed_binding.target
            or recovery_binding.plan_digest != contract.recovery_plan_digest
            or recovery_binding.subject.record_digest
            != contract.recovery_contract_digest
            or recovery_binding.intended_state != contract.recovery_target
            or recovery_binding.generation.generation_digest
            != contract.recovery_destination_generation_digest
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "the successor does not bind the exact recovery contract",
            )
        if self._guarded_targets.get(failed_binding.target) != failed_binding.operation_id:
            raise AuthorityUnavailable(
                "AUTHORITY_TARGET_GUARD_MISMATCH",
                "the failed predecessor no longer exclusively guards the target",
            )
        last_epoch = self._last_fence_epochs.get(failed_binding.target, 0)
        if (
            not isinstance(fence_epoch, int)
            or isinstance(fence_epoch, bool)
            or fence_epoch <= max(last_epoch, predecessor_fence_epoch)
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the recovery fence does not advance the failed operation epoch",
            )
        recovery_contract_digest = contract.recovery_contract_digest
        assert recovery_contract_digest is not None
        material = "\0".join(
            (
                recovery_binding.operation_id,
                recovery_binding.intent_digest,
                recovery_binding.plan_digest,
                recovery_binding.authority_head_digest,
                recovery_binding.subject.record_digest,
                recovery_binding.target.kind.value,
                recovery_binding.target.target_id,
                recovery_binding.intended_state.state_digest,
                failed_binding.operation_id,
                failure_record_digest,
                str(predecessor_fence_epoch),
                recovery_contract_digest,
                owner_role,
                str(fence_epoch),
            )
        ).encode("utf-8")
        fenced = FencedCapability(
            capability_id="sha256:" + hashlib.sha256(material).hexdigest(),
            operation_id=recovery_binding.operation_id,
            intent_digest=recovery_binding.intent_digest,
            plan_digest=recovery_binding.plan_digest,
            authority_head_digest=recovery_binding.authority_head_digest,
            subject_digest=recovery_binding.subject.record_digest,
            target=recovery_binding.target,
            intended_state_digest=recovery_binding.intended_state.state_digest,
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
        self._issued_recovery_capabilities[capability.capability_id] = capability
        self._last_fence_epochs[recovery_binding.target] = fence_epoch
        self._operation_fence_epochs[recovery_binding.operation_id] = fence_epoch
        self._guarded_targets[recovery_binding.target] = recovery_binding.operation_id
        self._recovery_predecessors[recovery_binding.operation_id] = (
            failed_binding.operation_id,
            failure_record_digest,
        )
        self._states[recovery_binding.operation_id] = (
            OperationState.RECOVERY_CAPABILITY_ISSUED
        )
        self._append(
            kind="recovery_capability",
            operation_id=recovery_binding.operation_id,
            record_digest=capability.capability_id,
        )
        return capability

    def execute_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        *,
        failure: OperationResult,
        capability: RecoveryCapability,
        observed_state: ProtectedStateSnapshot,
    ) -> OperationResult:
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
            or remembered[0] != failure
            or failure_record_digest is None
            or capability.predecessor_operation_id != failed_binding.operation_id
            or capability.predecessor_failure_record_digest != failure_record_digest
            or capability.predecessor_fence_epoch != remembered[1]
            or link != (failed_binding.operation_id, failure_record_digest)
            or capability.fenced.operation_id != recovery_binding.operation_id
            or capability.fenced.intent_digest != recovery_binding.intent_digest
            or capability.fenced.plan_digest != recovery_binding.plan_digest
            or capability.fenced.authority_head_digest
            != recovery_binding.authority_head_digest
            or capability.fenced.subject_digest
            != recovery_binding.subject.record_digest
            or capability.fenced.target != recovery_binding.target
            or capability.fenced.intended_state_digest
            != recovery_binding.intended_state.state_digest
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "the capability does not bind the exact failed recovery chain",
            )
        self._issued_recovery_capabilities.pop(capability.capability_id)
        self._consumed_capabilities.add(capability.capability_id)
        if (
            observed_state != recovery_binding.expected_state
            or self.observe_active() != observed_state
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
            self._states[recovery_binding.operation_id] = OperationState.RECOVERY_REQUIRED
            self._remember_recovery_failure(recovery_binding, result)
            return result
        self._active_state = recovery_binding.intended_state
        self._pending.pop(recovery_binding.operation_id, None)
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

    def terminalize_recovery(
        self,
        failed_binding: OperationBinding,
        recovery_binding: OperationBinding,
        observation: TerminalObservation,
    ) -> OperationResult:
        if (
            self._states.get(recovery_binding.operation_id)
            is not OperationState.RECOVERY_PENDING_VALIDATION
        ):
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_PHASE_INVALID",
                "recovery is not awaiting terminal validation",
            )
        link = self._recovery_predecessors.get(recovery_binding.operation_id)
        if link is None or link[0] != failed_binding.operation_id:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_BINDING_MISMATCH",
                "recovery no longer binds the failed predecessor",
            )
        required_effects = {
            effect.effect_id
            for effect in recovery_binding.effects
            if effect.classification is EffectClass.POSTSTATE_OBSERVABLE
        }
        forbidden_effects = {
            effect.effect_id
            for effect in recovery_binding.effects
            if effect.classification is EffectClass.FORBIDDEN_TRANSIENT
        }
        passed = (
            observation.validator_digest
            == recovery_binding.terminal_validator_digest
            and observation.outcome is TerminalOutcome.PASS
            and observation.observed_state == recovery_binding.intended_state
            and self.observe_active() == recovery_binding.intended_state
            and required_effects <= observation.observed_effect_ids
            and forbidden_effects <= observation.interval_enforced_effect_ids
            and not forbidden_effects & observation.interval_violation_effect_ids
        )
        state = OperationState.RECOVERED if passed else OperationState.RECOVERY_REQUIRED
        self._states[recovery_binding.operation_id] = state
        if passed:
            self._states[failed_binding.operation_id] = OperationState.RECOVERED
            self._guarded_targets.pop(recovery_binding.target, None)
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
            self._remember_recovery_failure(recovery_binding, result)
        return result

    def evidence_view(self) -> NonPromotionalEvidenceView:
        return NonPromotionalEvidenceView(
            adapter_id=self.adapter_id,
            receipts=tuple(self._receipts),
        )

    def _append_precheck_failure(
        self,
        binding: OperationBinding,
        code: str,
    ) -> NonPromotionalReceipt:
        material = (
            f"{binding.intent_digest}\0{binding.operation_id}\0{code}"
        ).encode()
        failure_digest = "sha256:" + hashlib.sha256(material).hexdigest()
        return self._append(
            kind="precheck_failed",
            operation_id=binding.operation_id,
            record_digest=failure_digest,
        )

    def _remember_recovery_failure(
        self,
        binding: OperationBinding,
        result: OperationResult,
    ) -> None:
        fence_epoch = self._operation_fence_epochs.get(binding.operation_id)
        if fence_epoch is None:
            raise AuthorityUnavailable(
                "AUTHORITY_RECOVERY_FENCE_MISSING",
                "the recovery-required result has no proven operation fence",
            )
        self._recovery_failures[binding.operation_id] = (result, fence_epoch)

    @staticmethod
    def _capability_matches(
        binding: OperationBinding,
        capability: FencedCapability,
    ) -> bool:
        return (
            capability.operation_id == binding.operation_id
            and capability.intent_digest == binding.intent_digest
            and capability.plan_digest == binding.plan_digest
            and capability.authority_head_digest == binding.authority_head_digest
            and capability.subject_digest == binding.subject.record_digest
            and capability.target == binding.target
            and capability.intended_state_digest == binding.intended_state.state_digest
        )

    def _append(
        self,
        *,
        kind: str,
        operation_id: str | None,
        record_digest: str,
    ) -> NonPromotionalReceipt:
        sequence = len(self._entries) + 1
        receipt_material = "\0".join(
            (
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
            active_digest=(
                self._active_state.state_digest
                if self._active_state is not None
                else None
            ),
        )
        receipt = NonPromotionalReceipt(
            receipt_id=receipt_id,
            sequence=sequence,
            kind=kind,
            operation_id=operation_id,
            record_digest=record_digest,
        )
        self._entries.append(entry)
        self._receipts.append(receipt)
        return receipt


__all__ = ["InMemoryAuthority", "JournalEntry"]
