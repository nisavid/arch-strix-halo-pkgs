from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (
    AuthorityErrorCode,
    AuthorityRole,
    AuthorityUnavailable,
    ControlAuthorityError,
    CriticalOperationKind,
    DeclaredEffect,
    EffectClass,
    ForbiddenAuthoritySubstrate,
    GenerationBinding,
    GenerationBindingMode,
    GenerationClass,
    LifecyclePhase,
    NonPromotionalEvidence,
    OperationBinding,
    OperationState,
    OperationSubject,
    OperationSubjectKind,
    OperationTarget,
    OperationTargetKind,
    ProductionTopology,
    ProtectedStateSnapshot,
    RecoveryMode,
    RollbackRecoveryContract,
    RollbackTarget,
    SubstrateBinding,
    TerminalObservation,
    TerminalOutcome,
    production_authority,
    require_promotable,
    validate_operation_coordinates,
)
from control_plane.testing import InMemoryAuthority

OLD_STATE = "sha256:" + "1" * 64
NEW_STATE = "sha256:" + "2" * 64
INTENT = "sha256:" + "3" * 64
PLAN = "sha256:" + "4" * 64
ROLLBACK = "sha256:" + "6" * 64
GENERATION = "sha256:" + "7" * 64
SUBJECT = GENERATION
PROJECTION = "sha256:" + "8" * 64
INTENDED = "sha256:" + "9" * 64
HEAD = "sha256:" + "a" * 64
TERMINAL_VALIDATOR = "sha256:" + "b" * 64
ROLLBACK_VALIDATOR = "sha256:" + "c" * 64
RECOVERY_PLAN = "sha256:" + "d" * 64
EFFECT_PROJECTION = PROJECTION
RECOVERY_CONTRACT = "sha256:" + "f" * 64
RECOVERY_DESTINATION = "sha256:" + "0" * 64


def test_authority_failures_export_a_closed_typed_error_code():
    error = ControlAuthorityError(
        AuthorityErrorCode.AUTHORITY_TOPOLOGY_UNBOUND,
        "unbound",
    )

    assert error.code is AuthorityErrorCode.AUTHORITY_TOPOLOGY_UNBOUND


def test_generation_binding_modes_are_closed_and_bind_required_generations():
    binding = GenerationBinding(
        mode=GenerationBindingMode.REQUIRED_GENERATION,
        generation_digest=GENERATION,
    )

    assert binding.generation_digest == GENERATION
    with pytest.raises(ValueError, match="requires generation_digest"):
        GenerationBinding(mode=GenerationBindingMode.REQUIRED_GENERATION)
    with pytest.raises(ValueError, match="forbids generation_digest"):
        GenerationBinding(
            mode=GenerationBindingMode.NO_GENERATION,
            generation_digest=GENERATION,
        )
    with pytest.raises(TypeError, match="GenerationBindingMode"):
        GenerationBinding(mode="emergency_root")  # type: ignore[arg-type]


def test_shared_operation_coordinate_validator_accepts_every_legal_row():
    required = GenerationBindingMode.REQUIRED_GENERATION
    legal_rows = {
        CriticalOperationKind.REPOSITORY_PUBLICATION: {
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.PACKAGE_REPOSITORY,
                required,
                generation_class,
                LifecyclePhase.PUBLISHED,
            )
            for generation_class in (GenerationClass.F, GenerationClass.C)
        },
        CriticalOperationKind.PACKAGE_INSTALLATION: {
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                required,
                GenerationClass.F,
                LifecyclePhase.FOUNDATION_VALIDATION,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                required,
                GenerationClass.C,
                LifecyclePhase.PREVALIDATED,
            ),
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.LIVE_ROOT,
                required,
                GenerationClass.C,
                LifecyclePhase.ACTIVE,
            ),
        },
        CriticalOperationKind.TRUST_POLICY_MUTATION: {
            (
                OperationSubjectKind.CONTROL_RECORD,
                target_kind,
                required,
                GenerationClass.C,
                lifecycle_phase,
            )
            for target_kind, lifecycle_phase in (
                (OperationTargetKind.ISOLATED_ROOT, LifecyclePhase.PREVALIDATED),
                (OperationTargetKind.LIVE_ROOT, LifecyclePhase.ACTIVE),
            )
        },
        CriticalOperationKind.BLOCKING_SCENARIO: {
            (
                OperationSubjectKind.GATE_OCCURRENCE,
                target_kind,
                required,
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
        },
        CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION: {
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
                    required,
                    GenerationClass.C,
                    lifecycle_phase,
                )
                for lifecycle_phase in (
                    LifecyclePhase.PUBLISHED,
                    LifecyclePhase.PREVALIDATED,
                    LifecyclePhase.ACTIVE,
                    LifecyclePhase.ACCEPTED,
                )
            ),
        },
        CriticalOperationKind.ROLLBACK: {
            (
                OperationSubjectKind.GENERATION,
                target_kind,
                required,
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
            )
        },
        CriticalOperationKind.RECOVERY: {
            (
                OperationSubjectKind.CONTROL_RECORD,
                target_kind,
                required,
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
        },
    }

    assert sum(map(len, legal_rows.values())) == 26
    for operation_kind, rows in legal_rows.items():
        for row in rows:
            validate_operation_coordinates(operation_kind, *row)


@pytest.mark.parametrize(
    ("target_kind", "generation_class", "lifecycle_phase"),
    [
        (
            OperationTargetKind.PACKAGE_REPOSITORY,
            GenerationClass.F,
            LifecyclePhase.PUBLISHED,
        ),
        (
            OperationTargetKind.PACKAGE_REPOSITORY,
            GenerationClass.C,
            LifecyclePhase.PUBLISHED,
        ),
        (
            OperationTargetKind.ISOLATED_ROOT,
            GenerationClass.F,
            LifecyclePhase.FOUNDATION_VALIDATION,
        ),
        (
            OperationTargetKind.ISOLATED_ROOT,
            GenerationClass.C,
            LifecyclePhase.PREVALIDATED,
        ),
        (
            OperationTargetKind.LIVE_ROOT,
            GenerationClass.C,
            LifecyclePhase.ACTIVE,
        ),
        (
            OperationTargetKind.LIVE_ROOT,
            GenerationClass.C,
            LifecyclePhase.ACCEPTED,
        ),
        (
            OperationTargetKind.SERVICE,
            GenerationClass.C,
            LifecyclePhase.PREVALIDATED,
        ),
        (
            OperationTargetKind.SERVICE,
            GenerationClass.C,
            LifecyclePhase.ACTIVE,
        ),
        (
            OperationTargetKind.SERVICE,
            GenerationClass.C,
            LifecyclePhase.ACCEPTED,
        ),
        (
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationClass.B0,
            LifecyclePhase.CAPTURED,
        ),
        (
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationClass.C,
            LifecyclePhase.PUBLISHED,
        ),
        (
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationClass.C,
            LifecyclePhase.PREVALIDATED,
        ),
        (
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationClass.C,
            LifecyclePhase.ACTIVE,
        ),
        (
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationClass.C,
            LifecyclePhase.ACCEPTED,
        ),
    ],
)
def test_recovery_coordinates_cover_every_mutating_target_and_phase(
    target_kind,
    generation_class,
    lifecycle_phase,
):
    validate_operation_coordinates(
        CriticalOperationKind.RECOVERY,
        OperationSubjectKind.CONTROL_RECORD,
        target_kind,
        (
            GenerationBindingMode.B0_CAPTURE_SENTINEL
            if generation_class is GenerationClass.B0
            else GenerationBindingMode.REQUIRED_GENERATION
        ),
        generation_class,
        lifecycle_phase,
    )


def test_b0_capture_recovery_rejects_required_generation_reclassification():
    with pytest.raises(ValueError, match="operation envelope coordinates"):
        validate_operation_coordinates(
            CriticalOperationKind.RECOVERY,
            OperationSubjectKind.CONTROL_RECORD,
            OperationTargetKind.COMPOSITE_REGISTER,
            GenerationBindingMode.REQUIRED_GENERATION,
            GenerationClass.B0,
            LifecyclePhase.CAPTURED,
        )


@pytest.mark.parametrize(
    "source_changes",
    [
        {
            "operation_kind": CriticalOperationKind.REPOSITORY_PUBLICATION,
            "generation_class": GenerationClass.C,
            "lifecycle_phase": LifecyclePhase.PUBLISHED,
            "target": OperationTarget(
                kind=OperationTargetKind.PACKAGE_REPOSITORY,
                target_id="candidate-repository",
            ),
        },
        {
            "operation_kind": CriticalOperationKind.BLOCKING_SCENARIO,
            "generation_class": GenerationClass.C,
            "lifecycle_phase": LifecyclePhase.ACTIVE,
            "subject": OperationSubject(
                kind=OperationSubjectKind.GATE_OCCURRENCE,
                record_digest=SUBJECT,
            ),
            "target": OperationTarget(
                kind=OperationTargetKind.SERVICE,
                target_id="inference-service",
            ),
        },
        {
            "operation_kind": CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
            "generation_class": GenerationClass.C,
            "lifecycle_phase": LifecyclePhase.ACTIVE,
            "subject": OperationSubject(
                kind=OperationSubjectKind.COMPOSITE_AUTHORITY,
                record_digest=SUBJECT,
            ),
            "target": OperationTarget(
                kind=OperationTargetKind.COMPOSITE_REGISTER,
                target_id="authority-register",
            ),
        },
    ],
)
def test_recovery_successor_preserves_the_failed_target_and_advances_its_fence(
    source_changes,
):
    source = replace(
        typed_operation_binding(),
        rollback=replace(
            typed_operation_binding().rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
        **source_changes,
    )
    authority = InMemoryAuthority(initial_active_state=source.expected_state)
    authority.append_intent(source)
    capability = authority.acquire_capability(source, fence_epoch=1)
    authority.guarded_compare_and_swap(
        source,
        capability=capability,
        observed_state=source.expected_state,
    )
    failure = authority.terminalize_operation(
        source,
        TerminalObservation(
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=source.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    successor = replace(
        typed_operation_binding(),
        operation_id=f"recovery-{source.target.kind.value}",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=source.generation_class,
        lifecycle_phase=source.lifecycle_phase,
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        target=source.target,
        expected_state=source.intended_state,
        intended_state=source.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=RECOVERY_DESTINATION,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(source.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    authority.append_intent(successor)

    recovery_capability = authority.acquire_recovery_capability(
        source,
        successor,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert recovery_capability.fenced.target == source.target
    assert recovery_capability.predecessor_fence_epoch == 1
    assert recovery_capability.fenced.fence_epoch == 2


@pytest.mark.parametrize(
    ("operation_kind", "coordinates"),
    [
        (
            CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
            (
                OperationSubjectKind.COMPOSITE_AUTHORITY,
                OperationTargetKind.COMPOSITE_REGISTER,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.B0,
                LifecyclePhase.CAPTURED,
            ),
        ),
        (
            CriticalOperationKind.PACKAGE_INSTALLATION,
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.C,
                LifecyclePhase.FOUNDATION_VALIDATION,
            ),
        ),
        (
            CriticalOperationKind.REPOSITORY_PUBLICATION,
            (
                OperationSubjectKind.GENERATION,
                OperationTargetKind.ISOLATED_ROOT,
                GenerationBindingMode.REQUIRED_GENERATION,
                GenerationClass.F,
                LifecyclePhase.PUBLISHED,
            ),
        ),
    ],
)
def test_shared_operation_coordinate_validator_rejects_adjacent_invalid_rows(
    operation_kind,
    coordinates,
):
    with pytest.raises(ValueError, match="operation envelope coordinates"):
        validate_operation_coordinates(operation_kind, *coordinates)


def test_b0_capture_binds_an_exact_pre_generation_sentinel_and_output():
    sentinel = "sha256:" + "5" * 64

    binding = GenerationBinding(
        mode=GenerationBindingMode.B0_CAPTURE_SENTINEL,
        generation_digest=GENERATION,
        sentinel_digest=sentinel,
    )

    assert binding.generation_digest == GENERATION
    assert binding.sentinel_digest == sentinel
    with pytest.raises(ValueError, match="requires generation_digest and sentinel_digest"):
        GenerationBinding(mode=GenerationBindingMode.B0_CAPTURE_SENTINEL)


def test_b0_capture_sentinel_has_one_exact_composite_register_coordinate():
    base = typed_operation_binding()
    binding = replace(
        base,
        operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
        generation_class=GenerationClass.B0,
        lifecycle_phase=LifecyclePhase.CAPTURED,
        subject=OperationSubject(
            kind=OperationSubjectKind.COMPOSITE_AUTHORITY,
            record_digest=GENERATION,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.COMPOSITE_REGISTER,
            target_id="authority-register",
        ),
        generation=GenerationBinding(
            mode=GenerationBindingMode.B0_CAPTURE_SENTINEL,
            generation_digest=GENERATION,
            sentinel_digest="sha256:" + "f" * 64,
        ),
    )

    assert binding.generation.mode is GenerationBindingMode.B0_CAPTURE_SENTINEL


def test_b0_capture_rejects_a_sentinel_free_generation_exemption():
    base = typed_operation_binding()

    with pytest.raises(ValueError, match="operation envelope coordinates"):
        replace(
            base,
            operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
            generation_class=GenerationClass.B0,
            lifecycle_phase=LifecyclePhase.CAPTURED,
            subject=OperationSubject(
                kind=OperationSubjectKind.COMPOSITE_AUTHORITY,
                record_digest=GENERATION,
            ),
            target=OperationTarget(
                kind=OperationTargetKind.COMPOSITE_REGISTER,
                target_id="authority-register",
            ),
            generation=GenerationBinding(
                mode=GenerationBindingMode.NO_GENERATION,
            ),
        )


def _rollback_target(snapshot: ProtectedStateSnapshot) -> RollbackTarget:
    return RollbackTarget(
        protected_state=snapshot,
        destination_generation_digest=snapshot.generation_digest,
    )


def typed_operation_binding() -> OperationBinding:
    expected = ProtectedStateSnapshot(
        record_digest="sha256:" + "f" * 64,
        generation_digest=RECOVERY_DESTINATION,
        projection_digest=PROJECTION,
        state_digest=OLD_STATE,
    )
    return OperationBinding(
        operation_id="op-activation-001",
        operation_kind=CriticalOperationKind.PACKAGE_INSTALLATION,
        generation_class=GenerationClass.C,
        lifecycle_phase=LifecyclePhase.ACTIVE,
        intent_digest=INTENT,
        plan_digest=PLAN,
        authority_head_digest=HEAD,
        subject=OperationSubject(
            kind=OperationSubjectKind.GENERATION,
            record_digest=SUBJECT,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.LIVE_ROOT,
            target_id="reference-host",
        ),
        expected_state=expected,
        intended_state=ProtectedStateSnapshot(
            record_digest="sha256:" + "0" * 64,
            generation_digest=GENERATION,
            projection_digest=PROJECTION,
            state_digest=INTENDED,
        ),
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=GENERATION,
        ),
        effects=(
            DeclaredEffect(
                effect_id="package-database",
                classification=EffectClass.POSTSTATE_OBSERVABLE,
                projection_digest=EFFECT_PROJECTION,
            ),
        ),
        rollback=RollbackRecoveryContract(
            mode=RecoveryMode.EXACT_ROLLBACK,
            rollback_target=_rollback_target(expected),
            rollback_plan_digest=ROLLBACK,
            rollback_validator_digest=ROLLBACK_VALIDATOR,
            recovery_plan_digest=RECOVERY_PLAN,
            recovery_owner_role="recovery-owner",
            recovery_contract_digest=RECOVERY_CONTRACT,
            recovery_target=expected,
            recovery_destination_generation_digest=RECOVERY_DESTINATION,
            recovery_origin_generation_digest=GENERATION,
        ),
        terminal_validator_digest=TERMINAL_VALIDATOR,
    )


def _registered_recovery_successor(
    *,
    source: OperationBinding | None = None,
    recovery_target: ProtectedStateSnapshot | None = None,
    recovery_generation_class: GenerationClass | None = None,
    recovery_lifecycle_phase: LifecyclePhase | None = None,
    recovery_terminal_validator_digest: str = TERMINAL_VALIDATOR,
):
    source = source if source is not None else typed_operation_binding()
    failed_binding = replace(
        source,
        rollback=replace(
            source.rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            recovery_target=(
                recovery_target
                if recovery_target is not None
                else source.rollback.recovery_target
            ),
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=failed_binding.expected_state)
    authority.append_intent(failed_binding)
    capability = authority.acquire_capability(failed_binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        failed_binding,
        capability=capability,
        observed_state=failed_binding.expected_state,
    )
    failure = authority.terminalize_operation(
        failed_binding,
        TerminalObservation(
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    recovery_binding = replace(
        typed_operation_binding(),
        operation_id="op-recovery-001",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=(
            recovery_generation_class
            if recovery_generation_class is not None
            else failed_binding.generation_class
        ),
        lifecycle_phase=(
            recovery_lifecycle_phase
            if recovery_lifecycle_phase is not None
            else failed_binding.lifecycle_phase
        ),
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        target=failed_binding.target,
        expected_state=failed_binding.intended_state,
        intended_state=failed_binding.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=RECOVERY_DESTINATION,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(failed_binding.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
        terminal_validator_digest=recovery_terminal_validator_digest,
    )
    authority.append_intent(recovery_binding)
    return authority, failed_binding, recovery_binding, failure


def _registered_b0_recovery_successor(*, sentinel_digest: str):
    source = replace(
        typed_operation_binding(),
        operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
        generation_class=GenerationClass.B0,
        lifecycle_phase=LifecyclePhase.CAPTURED,
        subject=OperationSubject(
            kind=OperationSubjectKind.COMPOSITE_AUTHORITY,
            record_digest=SUBJECT,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.COMPOSITE_REGISTER,
            target_id="authority-register",
        ),
        generation=GenerationBinding(
            mode=GenerationBindingMode.B0_CAPTURE_SENTINEL,
            generation_digest=GENERATION,
            sentinel_digest="sha256:" + "5" * 64,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=source.expected_state)
    authority.append_intent(source)
    capability = authority.acquire_capability(source, fence_epoch=1)
    authority.guarded_compare_and_swap(
        source,
        capability=capability,
        observed_state=source.expected_state,
    )
    failure = authority.terminalize_operation(
        source,
        TerminalObservation(
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=source.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    successor = replace(
        typed_operation_binding(),
        operation_id="recovery-composite-register",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=GenerationClass.B0,
        lifecycle_phase=LifecyclePhase.CAPTURED,
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        target=source.target,
        expected_state=source.intended_state,
        intended_state=source.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.B0_CAPTURE_SENTINEL,
            generation_digest=RECOVERY_DESTINATION,
            sentinel_digest=sentinel_digest,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(source.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    authority.append_intent(successor)
    return authority, source, successor, failure


def _rollback_required_authority(
    binding: OperationBinding | None = None,
):
    binding = binding if binding is not None else typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    return authority, binding


def test_operation_binding_is_typed_and_binds_the_complete_protected_state_contract():
    binding = typed_operation_binding()

    assert binding.operation_kind is CriticalOperationKind.PACKAGE_INSTALLATION
    assert binding.generation_class is GenerationClass.C
    assert binding.lifecycle_phase is LifecyclePhase.ACTIVE
    assert binding.subject.kind is OperationSubjectKind.GENERATION
    assert binding.target.kind is OperationTargetKind.LIVE_ROOT
    assert binding.expected_state.projection_digest == PROJECTION
    assert binding.intended_state.state_digest == INTENDED
    assert binding.generation.mode is GenerationBindingMode.REQUIRED_GENERATION
    assert binding.effects[0].classification is EffectClass.POSTSTATE_OBSERVABLE
    assert binding.rollback.rollback_target is not None
    assert binding.rollback.rollback_target.protected_state == binding.expected_state
    assert (
        binding.rollback.recovery_destination_generation_digest
        == RECOVERY_DESTINATION
    )
    assert binding.terminal_validator_digest == TERMINAL_VALIDATOR


def test_operation_binding_rejects_a_noop_or_effect_outside_its_projection():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="prestate and intended state must differ"):
        replace(binding, intended_state=binding.expected_state)
    with pytest.raises(ValueError, match="effect projection"):
        replace(
            binding,
            effects=(
                replace(
                    binding.effects[0],
                    projection_digest="sha256:" + "f" * 64,
                ),
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {
            "generation": GenerationBinding(
                mode=GenerationBindingMode.NO_GENERATION,
            )
        },
        {
            "subject": OperationSubject(
                kind=OperationSubjectKind.GATE_OCCURRENCE,
                record_digest=SUBJECT,
            )
        },
        {
            "target": OperationTarget(
                kind=OperationTargetKind.LIVE_ROOT,
                target_id="reference-host",
            )
        },
    ],
)
def test_repository_publication_rejects_invalid_envelope_coordinates(change):
    binding = replace(
        typed_operation_binding(),
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.C,
        lifecycle_phase=LifecyclePhase.PUBLISHED,
        subject=OperationSubject(
            kind=OperationSubjectKind.GENERATION,
            record_digest=SUBJECT,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.PACKAGE_REPOSITORY,
            target_id="candidate-repository",
        ),
    )

    with pytest.raises(ValueError, match="operation envelope coordinates"):
        replace(binding, **change)


def test_foundation_publication_is_bound_to_published_phase():
    binding = replace(
        typed_operation_binding(),
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.F,
        lifecycle_phase=LifecyclePhase.PUBLISHED,
        target=OperationTarget(
            kind=OperationTargetKind.PACKAGE_REPOSITORY,
            target_id="foundation-repository",
        ),
    )

    assert binding.generation_class is GenerationClass.F
    assert binding.lifecycle_phase is LifecyclePhase.PUBLISHED


@pytest.mark.parametrize(
    ("generation_class", "lifecycle_phase"),
    [
        (GenerationClass.B0, LifecyclePhase.ACTIVE),
        (GenerationClass.F, LifecyclePhase.PREVALIDATED),
        (GenerationClass.C, LifecyclePhase.FOUNDATION_VALIDATION),
    ],
)
def test_package_installation_rejects_incoherent_generation_phase_pairs(
    generation_class,
    lifecycle_phase,
):
    with pytest.raises(ValueError, match="operation envelope coordinates"):
        replace(
            typed_operation_binding(),
            generation_class=generation_class,
            lifecycle_phase=lifecycle_phase,
        )


def test_generation_subject_must_equal_the_bound_generation():
    with pytest.raises(ValueError, match="generation subject"):
        replace(
            typed_operation_binding(),
            subject=OperationSubject(
                kind=OperationSubjectKind.GENERATION,
                record_digest="sha256:" + "f" * 64,
            ),
        )


def test_recovery_only_contract_requires_an_exact_recovery_target():
    with pytest.raises(ValueError, match="requires contract, target, and destination"):
        RollbackRecoveryContract(
            mode=RecoveryMode.RECOVERY_ONLY,
            recovery_plan_digest=RECOVERY_PLAN,
            recovery_owner_role="recovery-owner",
        )


def test_recovery_target_generation_must_equal_the_recovery_destination():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="recovery target generation"):
        replace(
            binding.rollback,
            recovery_destination_generation_digest="sha256:" + "e" * 64,
        )


def test_b0_recovery_successor_must_inherit_the_failed_capture_sentinel():
    authority, source, successor, failure = _registered_b0_recovery_successor(
        sentinel_digest="sha256:" + "6" * 64,
    )

    with pytest.raises(AuthorityUnavailable) as mismatch:
        authority.acquire_recovery_capability(
            source,
            successor,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert mismatch.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"


def test_b0_recovery_successor_can_advance_the_same_sentinel_bound_target():
    sentinel = "sha256:" + "5" * 64
    authority, source, successor, failure = _registered_b0_recovery_successor(
        sentinel_digest=sentinel,
    )

    capability = authority.acquire_recovery_capability(
        source,
        successor,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert successor.generation.sentinel_digest == sentinel
    assert capability.fenced.target == source.target
    assert capability.predecessor_fence_epoch == 1
    assert capability.fenced.fence_epoch == 2


def test_rollback_target_binds_an_exact_snapshot_and_destination_generation():
    snapshot = ProtectedStateSnapshot(
        record_digest="sha256:" + "f" * 64,
        generation_digest=RECOVERY_DESTINATION,
        projection_digest=PROJECTION,
        state_digest=OLD_STATE,
    )

    target = RollbackTarget(
        protected_state=snapshot,
        destination_generation_digest=RECOVERY_DESTINATION,
    )

    assert target.protected_state.record_digest == "sha256:" + "f" * 64
    assert target.protected_state.projection_digest == PROJECTION
    assert target.protected_state.state_digest == OLD_STATE
    with pytest.raises(ValueError, match="snapshot generation"):
        replace(
            target,
            destination_generation_digest="sha256:" + "e" * 64,
        )


def test_fake_operation_needs_a_fenced_capability_and_terminal_validation_to_succeed():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)

    mutation = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    assert mutation.state is OperationState.MUTATED_PENDING_VALIDATION
    assert authority.operation_state(binding.operation_id) is mutation.state
    assert authority.observe_active() == binding.intended_state

    terminal = authority.terminalize_operation(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids=frozenset({"package-database"}),
        ),
    )

    assert terminal.state is OperationState.SUCCEEDED
    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=binding.expected_state,
        )
    assert exc_info.value.code == "AUTHORITY_CAPABILITY_CONSUMED"


def test_forward_capability_rejects_a_foreign_snapshot_with_the_same_state_digest():
    binding = typed_operation_binding()
    foreign_binding = replace(
        binding,
        intended_state=replace(
            binding.intended_state,
            record_digest="sha256:" + "4" * 64,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    foreign_authority = InMemoryAuthority(
        initial_active_state=foreign_binding.expected_state
    )
    authority.append_intent(binding)
    foreign_authority.append_intent(foreign_binding)
    authority.acquire_capability(binding, fence_epoch=1)
    foreign_capability = foreign_authority.acquire_capability(
        foreign_binding,
        fence_epoch=1,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(
            binding,
            capability=foreign_capability,
            observed_state=binding.expected_state,
        )

    assert exc_info.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert authority.observe_active() == binding.expected_state
    assert authority.operation_state(binding.operation_id) is OperationState.CAPABILITY_ISSUED


def test_forward_capability_rejects_a_foreign_binding_with_another_validator():
    binding = typed_operation_binding()
    foreign_binding = replace(
        binding,
        terminal_validator_digest="sha256:" + "4" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    foreign_authority = InMemoryAuthority(
        initial_active_state=foreign_binding.expected_state
    )
    authority.append_intent(binding)
    foreign_authority.append_intent(foreign_binding)
    authority.acquire_capability(binding, fence_epoch=1)
    foreign_capability = foreign_authority.acquire_capability(
        foreign_binding,
        fence_epoch=1,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(
            binding,
            capability=foreign_capability,
            observed_state=binding.expected_state,
        )

    assert exc_info.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert authority.observe_active() == binding.expected_state


def _cross_domain_capabilities():
    base = typed_operation_binding()
    binding = replace(
        base,
        plan_digest=ROLLBACK,
        rollback=replace(
            base.rollback,
            rollback_target=_rollback_target(base.intended_state),
        ),
    )
    forward_authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    forward_authority.append_intent(binding)
    forward_capability = forward_authority.acquire_capability(
        binding,
        fence_epoch=2,
    )
    rollback_authority, binding = _rollback_required_authority(binding)
    rollback_capability = rollback_authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    return (
        binding,
        forward_authority,
        forward_capability,
        rollback_authority,
        rollback_capability,
    )


def test_rollback_rejects_a_replayed_forward_capability():
    (
        binding,
        _forward_authority,
        forward_capability,
        rollback_authority,
        rollback_capability,
    ) = _cross_domain_capabilities()

    assert forward_capability.capability_type.value == "operation"
    assert rollback_capability.capability_type.value == "rollback"
    assert forward_capability.operation_digest == binding.digest()
    assert rollback_capability.operation_digest == binding.digest()
    assert forward_capability.capability_id != rollback_capability.capability_id

    with pytest.raises(AuthorityUnavailable) as exc_info:
        rollback_authority.execute_rollback(
            binding,
            capability=forward_capability,
            observed_state=binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_BINDING_MISMATCH"


def test_forward_operation_rejects_a_replayed_rollback_capability():
    (
        binding,
        forward_authority,
        _forward_capability,
        _rollback_authority,
        rollback_capability,
    ) = _cross_domain_capabilities()

    with pytest.raises(AuthorityUnavailable) as exc_info:
        forward_authority.guarded_compare_and_swap(
            binding,
            capability=rollback_capability,
            observed_state=binding.expected_state,
        )

    assert exc_info.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"


def test_terminal_failure_requires_exact_rollback_and_successful_validation():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    failed = authority.terminalize_operation(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )

    assert failed.state is OperationState.ROLLBACK_REQUIRED
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    pending = authority.execute_rollback(
        binding,
        capability=rollback_capability,
        observed_state=binding.intended_state,
    )
    assert pending.state is OperationState.ROLLBACK_PENDING_VALIDATION
    assert authority.observe_active() == binding.expected_state

    rolled_back = authority.terminalize_rollback(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
        ),
    )
    assert rolled_back.state is OperationState.ROLLED_BACK


def test_rollback_rejects_a_substituted_registered_target():
    authority, binding = _rollback_required_authority()
    forged_target = replace(
        binding.expected_state,
        record_digest="sha256:" + "4" * 64,
    )
    forged_binding = replace(
        binding,
        rollback=replace(
            binding.rollback,
            rollback_target=_rollback_target(forged_target),
        ),
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        rollback_capability = authority.acquire_rollback_capability(
            forged_binding,
            fence_epoch=2,
        )
        authority.execute_rollback(
            forged_binding,
            capability=rollback_capability,
            observed_state=binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert authority.observe_active() == binding.intended_state
    assert authority.operation_state(binding.operation_id) is OperationState.ROLLBACK_REQUIRED
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    assert rollback_capability.fence_epoch == 2


def test_rollback_capability_rejects_a_foreign_snapshot_with_the_same_state_digest():
    binding = typed_operation_binding()
    foreign_target = replace(
        binding.rollback.rollback_target,
        protected_state=replace(
            binding.expected_state,
            record_digest="sha256:" + "4" * 64,
        ),
    )
    foreign_binding = replace(
        binding,
        rollback=replace(binding.rollback, rollback_target=foreign_target),
    )
    authority, binding = _rollback_required_authority(binding)
    foreign_authority, foreign_binding = _rollback_required_authority(
        foreign_binding
    )
    local_capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    foreign_capability = foreign_authority.acquire_rollback_capability(
        foreign_binding,
        fence_epoch=2,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.execute_rollback(
            binding,
            capability=foreign_capability,
            observed_state=binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert authority.observe_active() == binding.intended_state
    pending = authority.execute_rollback(
        binding,
        capability=local_capability,
        observed_state=binding.intended_state,
    )
    assert pending.state is OperationState.ROLLBACK_PENDING_VALIDATION


def test_rollback_execution_rechecks_the_registered_target():
    authority, binding = _rollback_required_authority()
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    forged_binding = replace(
        binding,
        rollback=replace(
            binding.rollback,
            rollback_target=replace(
                binding.rollback.rollback_target,
                protected_state=replace(
                    binding.expected_state,
                    record_digest="sha256:" + "4" * 64,
                ),
            ),
        ),
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.execute_rollback(
            forged_binding,
            capability=rollback_capability,
            observed_state=binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert authority.observe_active() == binding.intended_state
    assert authority.operation_state(binding.operation_id) is OperationState.ROLLBACK_REQUIRED
    pending = authority.execute_rollback(
        binding,
        capability=rollback_capability,
        observed_state=binding.intended_state,
    )
    assert pending.state is OperationState.ROLLBACK_PENDING_VALIDATION


def test_rollback_terminal_rechecks_the_registered_validator():
    authority, binding = _rollback_required_authority()
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    authority.execute_rollback(
        binding,
        capability=rollback_capability,
        observed_state=binding.intended_state,
    )
    forged_validator = "sha256:" + "4" * 64
    forged_binding = replace(
        binding,
        rollback=replace(
            binding.rollback,
            rollback_validator_digest=forged_validator,
        ),
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.terminalize_rollback(
            forged_binding,
            TerminalObservation(
                record_digest="sha256:" + "3" * 64,
                validator_digest=forged_validator,
                observed_state=binding.expected_state,
                outcome=TerminalOutcome.PASS,
            ),
        )

    assert exc_info.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert authority.observe_active() == binding.expected_state
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_PENDING_VALIDATION
    )
    rolled_back = authority.terminalize_rollback(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "5" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
        ),
    )
    assert rolled_back.state is OperationState.ROLLED_BACK


def test_failed_rollback_enters_guarded_recovery_and_keeps_the_target_exclusive():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    authority.execute_rollback(
        binding,
        capability=rollback_capability,
        observed_state=binding.intended_state,
    )

    recovery = authority.terminalize_rollback(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "4" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.UNKNOWN,
        ),
    )

    assert recovery.state is OperationState.RECOVERY_REQUIRED
    successor = typed_operation_binding()
    successor = replace(successor, operation_id="op-activation-002")
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.acquire_capability(successor, fence_epoch=3)
    assert exc_info.value.code == "AUTHORITY_TARGET_GUARDED"


def test_named_recovery_successor_restores_the_target_under_the_failed_fence():
    failed_binding = replace(
        typed_operation_binding(),
        rollback=replace(
            typed_operation_binding().rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=failed_binding.expected_state)
    authority.append_intent(failed_binding)
    capability = authority.acquire_capability(failed_binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        failed_binding,
        capability=capability,
        observed_state=failed_binding.expected_state,
    )
    failure_terminal_digest = "sha256:" + "d" * 64
    failure = authority.terminalize_operation(
        failed_binding,
        TerminalObservation(
            record_digest=failure_terminal_digest,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    recovery_binding = replace(
        typed_operation_binding(),
        operation_id="op-recovery-001",
        operation_kind=CriticalOperationKind.RECOVERY,
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        expected_state=failed_binding.intended_state,
        intended_state=failed_binding.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=RECOVERY_DESTINATION,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(failed_binding.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    authority.append_intent(recovery_binding)

    recovery_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert failure.failure_record_digest == failure_terminal_digest
    assert (
        recovery_capability.predecessor_failure_record_digest
        == failure_terminal_digest
    )
    assert recovery_capability.predecessor_fence_epoch == 1
    pending = authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=recovery_capability,
        observed_state=failed_binding.intended_state,
    )
    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION
    assert authority.observe_active() == failed_binding.rollback.recovery_target

    recovered = authority.terminalize_recovery(
        failed_binding,
        recovery_binding,
        TerminalObservation(
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.rollback.recovery_target,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids=frozenset({"package-database"}),
        ),
    )

    assert recovered.state is OperationState.RECOVERED
    assert authority.operation_state(failed_binding.operation_id) is OperationState.RECOVERED
    assert authority.operation_state(recovery_binding.operation_id) is OperationState.RECOVERED


def test_recovery_execution_rechecks_the_registered_target():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    recovery_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    forged_binding = replace(
        recovery_binding,
        intended_state=replace(
            recovery_binding.intended_state,
            record_digest="sha256:" + "4" * 64,
        ),
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.execute_recovery(
            failed_binding,
            forged_binding,
            failure=failure,
            capability=recovery_capability,
            observed_state=failed_binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert authority.observe_active() == failed_binding.intended_state
    assert (
        authority.operation_state(recovery_binding.operation_id)
        is OperationState.RECOVERY_CAPABILITY_ISSUED
    )
    pending = authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=recovery_capability,
        observed_state=failed_binding.intended_state,
    )
    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION


def test_recovery_capability_rejects_a_foreign_snapshot_with_the_same_state_digest():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    foreign_target = replace(
        recovery_binding.intended_state,
        record_digest="sha256:" + "4" * 64,
    )
    (
        foreign_authority,
        foreign_failed_binding,
        foreign_recovery_binding,
        foreign_failure,
    ) = _registered_recovery_successor(recovery_target=foreign_target)
    local_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    foreign_capability = foreign_authority.acquire_recovery_capability(
        foreign_failed_binding,
        foreign_recovery_binding,
        failure=foreign_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.execute_recovery(
            failed_binding,
            recovery_binding,
            failure=failure,
            capability=foreign_capability,
            observed_state=failed_binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert authority.observe_active() == failed_binding.intended_state
    pending = authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=local_capability,
        observed_state=failed_binding.intended_state,
    )
    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION


def test_recovery_capability_requires_a_recovery_domain_fence():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    capability_type = type(capability.fenced.capability_type)

    with pytest.raises(ValueError, match="requires a recovery fence"):
        replace(
            capability,
            fenced=replace(
                capability.fenced,
                capability_type=capability_type.OPERATION,
            ),
        )


def test_recovery_acquisition_rechecks_the_registered_successor():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    forged_binding = replace(
        recovery_binding,
        intended_state=replace(
            recovery_binding.intended_state,
            record_digest="sha256:" + "4" * 64,
        ),
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.acquire_recovery_capability(
            failed_binding,
            forged_binding,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert authority.observe_active() == failed_binding.intended_state
    assert (
        authority.operation_state(recovery_binding.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    recovery_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    assert recovery_capability.fenced.fence_epoch == 2


def test_recovery_successor_cannot_reclassify_the_failed_lifecycle_phase():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor(
            recovery_lifecycle_phase=LifecyclePhase.ACCEPTED,
        )
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.acquire_recovery_capability(
            failed_binding,
            recovery_binding,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"


def test_recovery_successor_cannot_reclassify_the_failed_generation_class():
    source = replace(
        typed_operation_binding(),
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.F,
        lifecycle_phase=LifecyclePhase.PUBLISHED,
        target=OperationTarget(
            kind=OperationTargetKind.PACKAGE_REPOSITORY,
            target_id="foundation-repository",
        ),
    )
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor(
            source=source,
            recovery_generation_class=GenerationClass.C,
        )
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.acquire_recovery_capability(
            failed_binding,
            recovery_binding,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"


def test_recovery_terminal_rechecks_the_registered_validator():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    recovery_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=recovery_capability,
        observed_state=failed_binding.intended_state,
    )
    forged_validator = "sha256:" + "4" * 64
    forged_binding = replace(
        recovery_binding,
        terminal_validator_digest=forged_validator,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.terminalize_recovery(
            failed_binding,
            forged_binding,
            TerminalObservation(
                record_digest="sha256:" + "f" * 64,
                validator_digest=forged_validator,
                observed_state=recovery_binding.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids=frozenset({"package-database"}),
            ),
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert authority.observe_active() == recovery_binding.intended_state
    assert (
        authority.operation_state(recovery_binding.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )
    recovered = authority.terminalize_recovery(
        failed_binding,
        recovery_binding,
        TerminalObservation(
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery_binding.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids=frozenset({"package-database"}),
        ),
    )
    assert recovered.state is OperationState.RECOVERED


def test_recovery_terminal_rechecks_the_registered_failure_predecessor():
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor()
    )
    recovery_capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed_binding,
        recovery_binding,
        failure=failure,
        capability=recovery_capability,
        observed_state=failed_binding.intended_state,
    )
    forged_failed_binding = replace(
        failed_binding,
        terminal_validator_digest="sha256:" + "4" * 64,
    )

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.terminalize_recovery(
            forged_failed_binding,
            recovery_binding,
            TerminalObservation(
                record_digest="sha256:" + "f" * 64,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=recovery_binding.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids=frozenset({"package-database"}),
            ),
        )

    assert exc_info.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert authority.observe_active() == recovery_binding.intended_state
    assert (
        authority.operation_state(recovery_binding.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )


def test_recovery_rejects_the_wrong_owner_or_failure_terminal():
    failed_binding = replace(
        typed_operation_binding(),
        rollback=replace(
            typed_operation_binding().rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=failed_binding.expected_state)
    authority.append_intent(failed_binding)
    capability = authority.acquire_capability(failed_binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        failed_binding,
        capability=capability,
        observed_state=failed_binding.expected_state,
    )
    failure = authority.terminalize_operation(
        failed_binding,
        TerminalObservation(
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    recovery_binding = replace(
        typed_operation_binding(),
        operation_id="op-recovery-001",
        operation_kind=CriticalOperationKind.RECOVERY,
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        expected_state=failed_binding.intended_state,
        intended_state=failed_binding.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=RECOVERY_DESTINATION,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(failed_binding.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    authority.append_intent(recovery_binding)

    with pytest.raises(AuthorityUnavailable) as wrong_owner:
        authority.acquire_recovery_capability(
            failed_binding,
            recovery_binding,
            failure=failure,
            owner_role="package-operator",
            fence_epoch=2,
        )
    assert wrong_owner.value.code == "AUTHORITY_RECOVERY_OWNER_MISMATCH"

    forged_failure = replace(
        failure,
        record_digest="sha256:" + "0" * 64,
    )
    with pytest.raises(AuthorityUnavailable) as wrong_failure:
        authority.acquire_recovery_capability(
            failed_binding,
            recovery_binding,
            failure=forged_failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )
    assert wrong_failure.value.code == "AUTHORITY_RECOVERY_FAILURE_MISMATCH"


def test_forbidden_transient_effect_requires_interval_enforcement():
    binding = typed_operation_binding()
    binding = replace(
        binding,
        effects=(
            DeclaredEffect(
                effect_id="mixed-endpoint",
                classification=EffectClass.FORBIDDEN_TRANSIENT,
                projection_digest=EFFECT_PROJECTION,
            ),
        ),
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    result = authority.terminalize_operation(
        binding,
        TerminalObservation(
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_EFFECT_ENFORCEMENT_MISSING"


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
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)

    intent_receipt = authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    transition = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    assert intent_receipt.sequence == 1
    assert transition.state is OperationState.MUTATED_PENDING_VALIDATION
    assert authority.observe_active() == binding.intended_state
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "fenced_capability",
        "guarded_transition",
    ]


def test_fake_refuses_unregistered_transition_without_mutation():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    foreign = InMemoryAuthority(initial_active_state=binding.expected_state)
    foreign.append_intent(binding)
    capability = foreign.acquire_capability(binding, fence_epoch=1)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=binding.expected_state,
        )

    assert exc_info.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert authority.observe_active() == binding.expected_state
    assert authority.journal_entries == ()


def test_fake_refuses_expected_state_mismatch_without_mutation():
    binding = typed_operation_binding()
    actual = replace(
        binding.expected_state,
        record_digest="sha256:" + "4" * 64,
        state_digest="sha256:" + "5" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=actual)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=actual,
        )

    assert exc_info.value.code == "AUTHORITY_PRESTATE_MISMATCH"
    assert authority.observe_active() == actual
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "fenced_capability",
        "precheck_failed",
    ]


def test_fake_evidence_cannot_be_promoted_even_after_success():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        require_promotable(authority.evidence_view())

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"


def test_fake_rejects_a_stale_fence_without_mutation():
    first = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)
    capability = authority.acquire_capability(first, fence_epoch=1)
    authority.guarded_compare_and_swap(
        first,
        capability=capability,
        observed_state=first.expected_state,
    )
    authority.terminalize_operation(
        first,
        TerminalObservation(
            record_digest="sha256:" + "6" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids=frozenset({"package-database"}),
        ),
    )
    stale = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "7" * 64,
        expected_state=first.intended_state,
        intended_state=replace(
            first.intended_state,
            record_digest="sha256:" + "8" * 64,
            state_digest="sha256:" + "a" * 64,
        ),
    )
    authority.append_intent(stale)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.acquire_capability(stale, fence_epoch=1)

    assert exc_info.value.code == "AUTHORITY_FENCE_STALE"
    assert authority.observe_active() == first.intended_state
