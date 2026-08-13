from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from pathlib import Path
from threading import Barrier
from time import sleep

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import control_plane
import control_plane.testing as control_plane_testing
from control_plane import (
    AuthorityErrorCode,
    AuthorityRole,
    AuthorityUnavailable,
    CapabilityType,
    ControlAuthorityError,
    CriticalOperationKind,
    DeclaredEffect,
    EffectClass,
    FencedCapability,
    ForbiddenAuthoritySubstrate,
    GenerationBinding,
    GenerationBindingMode,
    GenerationClass,
    LifecyclePhase,
    NonPromotionalEvidence,
    OperationBinding,
    OperationResult,
    OperationState,
    OperationSubject,
    OperationSubjectKind,
    OperationTarget,
    OperationTargetKind,
    ProductionTopology,
    ProtectedStateSnapshot,
    RecoveryCapability,
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


class _LyingString(str):
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash("package-database")

    def __str__(self):
        return "package-database"


class _LyingInt(int):
    def __eq__(self, other):
        return True

    def __le__(self, other):
        return False

    def __hash__(self):
        return int.__hash__(self)

    def __int__(self):
        return 999

    def __str__(self):
        return "999"


class _LyingSnapshot(ProtectedStateSnapshot):
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False


class _SwitchableObservationAuthority(InMemoryAuthority):
    observation_override: ProtectedStateSnapshot | None = None

    def observe_active(self, target=None):
        if self.observation_override is not None:
            return self.observation_override
        return super().observe_active(target)


def _deceptive_snapshot(
    state: ProtectedStateSnapshot,
) -> ProtectedStateSnapshot:
    return _LyingSnapshot(
        record_digest="sha256:" + "e" * 64,
        generation_digest=state.generation_digest,
        lifecycle_phase=state.lifecycle_phase,
        projection_digest=state.projection_digest,
        state_digest="sha256:" + "d" * 64,
    )


def test_authority_failures_export_a_closed_typed_error_code():
    error = ControlAuthorityError(
        AuthorityErrorCode.AUTHORITY_TOPOLOGY_UNBOUND,
        "unbound",
    )

    assert error.code is AuthorityErrorCode.AUTHORITY_TOPOLOGY_UNBOUND


def test_operation_result_rejects_an_undeclared_failure_code():
    with pytest.raises(ValueError, match="declared AuthorityErrorCode"):
        OperationResult(
            operation_id="op-failed-001",
            state=OperationState.RECOVERY_REQUIRED,
            record_digest="sha256:" + "1" * 64,
            failure_code="invented_failure",
            failure_record_digest="sha256:" + "2" * 64,
        )


@pytest.mark.parametrize(
    ("failure_code", "failure_record_digest"),
    [
        (None, "sha256:" + "2" * 64),
        ("AUTHORITY_TERMINAL_NOT_PASS", None),
    ],
)
def test_operation_result_failure_state_requires_code_and_exact_failure_record(
    failure_code,
    failure_record_digest,
):
    with pytest.raises(ValueError, match="failure state requires"):
        OperationResult(
            operation_id="op-failed-001",
            state=OperationState.ROLLBACK_REQUIRED,
            record_digest="sha256:" + "1" * 64,
            failure_code=failure_code,
            failure_record_digest=failure_record_digest,
        )


@pytest.mark.parametrize(
    ("state", "failure_code"),
    [
        (OperationState.PRECHECK_FAILED, "AUTHORITY_TERMINAL_NOT_PASS"),
        (OperationState.ROLLBACK_REQUIRED, "AUTHORITY_ROLLBACK_VALIDATION_FAILED"),
        (OperationState.RECOVERY_REQUIRED, "AUTHORITY_TOPOLOGY_UNBOUND"),
    ],
)
def test_operation_result_failure_state_rejects_an_inappropriate_failure_code(
    state,
    failure_code,
):
    with pytest.raises(ValueError, match="not valid for operation state"):
        OperationResult(
            operation_id="op-failed-001",
            state=state,
            record_digest="sha256:" + "1" * 64,
            failure_code=failure_code,
            failure_record_digest="sha256:" + "2" * 64,
        )


@pytest.mark.parametrize(
    ("failure_code", "failure_record_digest"),
    [
        ("AUTHORITY_TERMINAL_NOT_PASS", None),
        (None, "sha256:" + "2" * 64),
        ("AUTHORITY_TERMINAL_NOT_PASS", "sha256:" + "2" * 64),
    ],
)
def test_operation_result_nonfailure_state_forbids_failure_metadata(
    failure_code,
    failure_record_digest,
):
    with pytest.raises(ValueError, match="nonfailure state forbids"):
        OperationResult(
            operation_id="op-succeeded-001",
            state=OperationState.SUCCEEDED,
            record_digest="sha256:" + "1" * 64,
            failure_code=failure_code,
            failure_record_digest=failure_record_digest,
        )


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
    base = typed_operation_binding()
    source = _binding_with_lifecycle_phase(
        base,
        rollback=replace(
            base.rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
            recovery_target=replace(
                base.rollback.recovery_target,
                record_digest="sha256:" + "5" * 64,
                lifecycle_phase=source_changes["lifecycle_phase"],
            ),
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
        _terminal_observation(
            source,
            capability,
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=source.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    successor_base = typed_operation_binding()
    successor = _binding_with_lifecycle_phase(
        successor_base,
        source.rollback.recovery_target.lifecycle_phase,
        operation_id=f"recovery-{source.target.kind.value}",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=source.generation_class,
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
            successor_base.rollback,
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
    with pytest.raises(
        ValueError, match="requires generation_digest and sentinel_digest"
    ):
        GenerationBinding(mode=GenerationBindingMode.B0_CAPTURE_SENTINEL)


def test_b0_capture_sentinel_has_one_exact_composite_register_coordinate():
    base = typed_operation_binding()
    binding = _binding_with_lifecycle_phase(
        base,
        LifecyclePhase.CAPTURED,
        operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
        generation_class=GenerationClass.B0,
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
        _binding_with_lifecycle_phase(
            base,
            LifecyclePhase.CAPTURED,
            operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
            generation_class=GenerationClass.B0,
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


def _binding_with_lifecycle_phase(
    binding: OperationBinding,
    lifecycle_phase: LifecyclePhase,
    **changes,
) -> OperationBinding:
    expected_source = changes.pop("expected_state", binding.expected_state)
    intended_source = changes.pop("intended_state", binding.intended_state)
    rollback_source = changes.pop("rollback", binding.rollback)
    expected_state = expected_source
    intended_state = replace(
        intended_source,
        lifecycle_phase=lifecycle_phase,
    )
    rollback_target = rollback_source.rollback_target
    return replace(
        binding,
        lifecycle_phase=lifecycle_phase,
        expected_state=expected_state,
        intended_state=intended_state,
        rollback=replace(
            rollback_source,
            rollback_target=rollback_target,
        ),
        **changes,
    )


def typed_operation_binding() -> OperationBinding:
    expected = ProtectedStateSnapshot(
        record_digest="sha256:" + "f" * 64,
        generation_digest=RECOVERY_DESTINATION,
        lifecycle_phase=LifecyclePhase.ACTIVE,
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
            lifecycle_phase=LifecyclePhase.ACTIVE,
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


def test_protected_state_snapshot_requires_a_closed_lifecycle_phase():
    snapshot_fields = {
        "record_digest": "sha256:" + "1" * 64,
        "generation_digest": "sha256:" + "2" * 64,
        "projection_digest": "sha256:" + "3" * 64,
        "state_digest": "sha256:" + "4" * 64,
    }

    with pytest.raises(TypeError, match="lifecycle_phase"):
        ProtectedStateSnapshot(**snapshot_fields)

    with pytest.raises(TypeError, match="lifecycle_phase"):
        ProtectedStateSnapshot(
            **snapshot_fields,
            lifecycle_phase=LifecyclePhase.ACTIVE.value,
        )

    snapshot = ProtectedStateSnapshot(
        **snapshot_fields,
        lifecycle_phase=LifecyclePhase.ACTIVE,
    )

    assert snapshot.lifecycle_phase is LifecyclePhase.ACTIVE


def test_protected_state_snapshot_normalizes_and_freezes_an_optional_process_epoch():
    process_epoch = _LyingString("service-process-001")
    snapshot = ProtectedStateSnapshot(
        record_digest="sha256:" + "1" * 64,
        generation_digest="sha256:" + "2" * 64,
        lifecycle_phase=LifecyclePhase.ACTIVE,
        projection_digest="sha256:" + "3" * 64,
        state_digest="sha256:" + "4" * 64,
        process_epoch=process_epoch,
    )

    assert snapshot.process_epoch == "service-process-001"
    assert type(snapshot.process_epoch) is str
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(AttributeError):
        snapshot.process_epoch = "service-process-002"


def test_authority_clones_and_rejects_cross_target_process_epoch_rebinding():
    binding = typed_operation_binding()
    target = binding.target
    snapshot = replace(binding.expected_state, process_epoch="service-process-001")
    authority = InMemoryAuthority(
        initial_active_state=snapshot,
        initial_target=target,
    )

    observed = authority.observe_active(target)

    assert observed == snapshot
    assert observed is not snapshot
    assert observed.process_epoch == "service-process-001"
    with pytest.raises(AuthorityUnavailable) as caught:
        authority.configure_active(
            replace(target, target_id="other-host"),
            replace(snapshot, process_epoch="service-process-002"),
        )
    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert authority.observe_active(target) == snapshot


def test_authority_value_constructors_normalize_scalar_subclasses():
    snapshot = ProtectedStateSnapshot(
        record_digest=_LyingString("sha256:" + "1" * 64),
        generation_digest=_LyingString("sha256:" + "2" * 64),
        lifecycle_phase=LifecyclePhase.ACTIVE,
        projection_digest=_LyingString("sha256:" + "3" * 64),
        state_digest=_LyingString("sha256:" + "4" * 64),
        process_epoch=_LyingString("service-process-001"),
    )
    target = OperationTarget(
        kind=OperationTargetKind.LIVE_ROOT,
        target_id=_LyingString("reference-host"),
    )
    effect = DeclaredEffect(
        effect_id=_LyingString("package-database"),
        classification=EffectClass.POSTSTATE_OBSERVABLE,
        projection_digest=_LyingString("sha256:" + "3" * 64),
    )
    capability = FencedCapability(
        capability_id=_LyingString("sha256:" + "5" * 64),
        capability_type=CapabilityType.OPERATION,
        operation_digest=_LyingString("sha256:" + "6" * 64),
        operation_id=_LyingString("op-activation-001"),
        intent_digest=_LyingString("sha256:" + "7" * 64),
        plan_digest=_LyingString("sha256:" + "8" * 64),
        authority_head_digest=_LyingString("sha256:" + "9" * 64),
        subject_digest=_LyingString("sha256:" + "a" * 64),
        target=target,
        intended_state=snapshot,
        fence_epoch=_LyingInt(1),
    )
    observation = TerminalObservation(
        record_digest=_LyingString("sha256:" + "b" * 64),
        operation_digest=_LyingString("sha256:" + "c" * 64),
        capability_digest=_LyingString("sha256:" + "d" * 64),
        validator_digest=_LyingString("sha256:" + "e" * 64),
        observed_state=snapshot,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={_LyingString("package-database")},
    )
    result = OperationResult(
        operation_id=_LyingString("op-activation-001"),
        state=OperationState.RECOVERY_REQUIRED,
        record_digest=_LyingString("sha256:" + "f" * 64),
        failure_code=_LyingString("AUTHORITY_RECOVERY_VALIDATION_FAILED"),
        failure_record_digest=_LyingString("sha256:" + "0" * 64),
    )

    assert snapshot.lifecycle_phase is LifecyclePhase.ACTIVE
    assert all(
        type(getattr(snapshot, item.name)) is str
        for item in fields(snapshot)
        if item.name != "lifecycle_phase"
    )
    assert type(target.target_id) is str
    assert type(effect.effect_id) is str
    assert type(effect.projection_digest) is str
    assert type(capability.capability_id) is str
    assert type(capability.operation_id) is str
    assert type(capability.fence_epoch) is int
    assert all(type(value) is str for value in observation.observed_effect_ids)
    assert type(result.operation_id) is str
    assert type(result.record_digest) is str
    assert type(result.failure_code) is str
    assert type(result.failure_record_digest) is str


def test_checkpoint_allocation_helpers_are_explicitly_test_only():
    helper_names = {
        "issue_lifecycle_checkpoint_for_testing",
        "seal_authority_issued_checkpoint_for_testing",
    }

    assert helper_names <= set(control_plane_testing.__all__)
    assert helper_names.isdisjoint(control_plane.__all__)
    assert all(callable(getattr(control_plane_testing, name)) for name in helper_names)
    assert all(
        "test" in (getattr(control_plane_testing, name).__doc__ or "").lower()
        for name in helper_names
    )


def test_append_record_normalizes_scalars_before_hashing_and_retention():
    authority = InMemoryAuthority()
    record_digest = _LyingString("sha256:" + "1" * 64)
    kind = _LyingString("evidence_record")

    receipt = authority.append_record(record_digest, kind=kind)
    entry = authority.journal_entries[0]

    assert type(receipt.record_digest) is str
    assert type(receipt.kind) is str
    assert type(receipt.sequence) is int
    assert type(entry.record_digest) is str
    assert type(entry.kind) is str
    assert type(entry.sequence) is int
    assert receipt.record_digest == str.__str__(record_digest)
    assert entry.record_digest == str.__str__(record_digest)


def test_receipts_and_evidence_are_bound_to_their_authority_instance():
    first = InMemoryAuthority()
    second = InMemoryAuthority()
    record_digest = "sha256:" + "1" * 64

    first_receipt = first.append_record(record_digest)
    second_receipt = second.append_record(record_digest)
    first_evidence = first.evidence_view()
    second_evidence = second.evidence_view()

    assert first_receipt.receipt_id != second_receipt.receipt_id
    assert first_evidence != second_evidence
    assert first_evidence.receipts == (first_receipt,)
    assert second_evidence.receipts == (second_receipt,)

    next_receipt = first.append_record(record_digest)
    assert first.evidence_view().receipts == (first_receipt, next_receipt)
    assert (first_receipt.sequence, next_receipt.sequence) == (1, 2)
    assert first_receipt.receipt_id != next_receipt.receipt_id


def test_authority_docs_describe_instance_scoped_nonpromotional_identity():
    authority = InMemoryAuthority()
    receipt = authority.append_record("sha256:" + "1" * 64)
    evidence = authority.evidence_view()
    public_docs = tuple(
        " ".join((doc or "").split())
        for doc in (
            control_plane_testing.__doc__,
            InMemoryAuthority.__doc__,
            type(receipt).__doc__,
            type(evidence).__doc__,
        )
    )

    assert all(
        "instance-scoped nonpromotional" in doc.lower()
        for doc in public_docs
    )
    assert "deterministic within one authority instance" in (
        public_docs[0].lower()
    )
    assert "capability and receipt identities intentionally differ" in (
        public_docs[1].lower()
    )


def test_forward_acquisition_rejects_a_lying_nonpositive_fence_subclass():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(binding, fence_epoch=_LyingInt(0))

    assert caught.value.code == "AUTHORITY_FENCE_STALE"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def test_rollback_acquisition_rejects_a_lying_stale_fence_subclass():
    authority, binding = _rollback_required_authority()

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_rollback_capability(binding, fence_epoch=_LyingInt(1))

    assert caught.value.code == "AUTHORITY_FENCE_STALE"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )


def test_recovery_acquisition_rejects_a_lying_stale_fence_subclass():
    authority, failed, recovery, failure = _registered_recovery_successor()

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=_LyingInt(1),
        )

    assert caught.value.code == "AUTHORITY_FENCE_STALE"
    assert (
        authority.operation_state(failed.operation_id)
        is OperationState.RECOVERY_REQUIRED
    )
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def test_guarded_transition_rejects_lying_scalar_subclasses_in_wrong_prestate():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    forged = replace(
        binding.expected_state,
        record_digest="sha256:" + "1" * 64,
        state_digest="sha256:" + "2" * 64,
    )
    object.__setattr__(
        forged,
        "record_digest",
        _LyingString(forged.record_digest),
    )
    object.__setattr__(forged, "state_digest", _LyingString(forged.state_digest))

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=forged,
        )

    assert caught.value.code == "AUTHORITY_PRESTATE_MISMATCH"
    assert authority.observe_active() == binding.expected_state
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.PRECHECK_FAILED
    )


def test_forward_execution_normalizes_a_deceptive_adapter_observation():
    binding = typed_operation_binding()
    deceptive = _LyingSnapshot(
        record_digest="sha256:" + "1" * 64,
        generation_digest=binding.expected_state.generation_digest,
        lifecycle_phase=binding.expected_state.lifecycle_phase,
        projection_digest=binding.expected_state.projection_digest,
        state_digest="sha256:" + "2" * 64,
    )

    class DeceptiveObservationAuthority(InMemoryAuthority):
        def observe_active(self, target=None):
            return deceptive

    authority = DeceptiveObservationAuthority(
        initial_active_state=binding.expected_state
    )
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=binding.expected_state,
        )

    assert caught.value.code == "AUTHORITY_PRESTATE_MISMATCH"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.PRECHECK_FAILED
    )


def test_forward_terminal_normalizes_a_deceptive_adapter_observation():
    binding = typed_operation_binding()
    authority = _SwitchableObservationAuthority(
        initial_active_state=binding.expected_state
    )
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    authority.observation_override = _deceptive_snapshot(binding.intended_state)

    result = authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_TERMINAL_STATE_MISMATCH"


def test_forward_terminal_rejects_lying_scalar_subclasses_in_wrong_state():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    forged = replace(
        binding.intended_state,
        record_digest="sha256:" + "1" * 64,
        state_digest="sha256:" + "2" * 64,
    )
    object.__setattr__(
        forged,
        "record_digest",
        _LyingString(forged.record_digest),
    )
    object.__setattr__(forged, "state_digest", _LyingString(forged.state_digest))

    result = authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=forged,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_TERMINAL_STATE_MISMATCH"


def test_forward_terminal_rejects_a_lying_wrong_effect_id_scalar_subclass():
    binding = typed_operation_binding()
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={_LyingString("wrong-effect")},
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_EFFECT_OBSERVATION_MISSING"


def test_recovery_acquisition_rejects_lying_scalars_in_failure_identity():
    authority, failed, recovery, failure = _registered_recovery_successor()
    forged = replace(failure, record_digest="sha256:" + "1" * 64)
    object.__setattr__(
        forged,
        "record_digest",
        _LyingString(forged.record_digest),
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=forged,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_FAILURE_MISMATCH"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def test_recovery_acquisition_rejects_a_lying_wrong_owner_scalar_subclass():
    authority, failed, recovery, failure = _registered_recovery_successor()

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=failure,
            owner_role=_LyingString("attacker"),
            fence_epoch=2,
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_OWNER_MISMATCH"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def _terminal_observation(
    binding: OperationBinding,
    capability,
    *,
    record_digest: str,
    validator_digest: str,
    observed_state: ProtectedStateSnapshot,
    outcome: TerminalOutcome,
    observed_effect_ids=(),
    interval_enforced_effect_ids=(),
    interval_violation_effect_ids=(),
) -> TerminalObservation:
    return TerminalObservation(
        record_digest=record_digest,
        operation_digest=binding.digest(),
        capability_digest=capability.capability_id,
        validator_digest=validator_digest,
        observed_state=observed_state,
        outcome=outcome,
        observed_effect_ids=observed_effect_ids,
        interval_enforced_effect_ids=interval_enforced_effect_ids,
        interval_violation_effect_ids=interval_violation_effect_ids,
    )


def _recovery_only_contract(
    *,
    origin_generation: str,
    lifecycle_phase: LifecyclePhase,
    projection_digest: str,
    ordinal: int,
) -> RollbackRecoveryContract:
    target = ProtectedStateSnapshot(
        record_digest="sha256:" + f"{ordinal + 1:x}" * 64,
        generation_digest="sha256:" + f"{ordinal + 2:x}" * 64,
        lifecycle_phase=lifecycle_phase,
        projection_digest=projection_digest,
        state_digest="sha256:" + f"{ordinal + 3:x}" * 64,
    )
    return RollbackRecoveryContract(
        mode=RecoveryMode.RECOVERY_ONLY,
        recovery_plan_digest="sha256:" + f"{ordinal + 5:x}" * 64,
        recovery_owner_role="recovery-owner",
        recovery_contract_digest="sha256:" + f"{ordinal + 4:x}" * 64,
        recovery_target=target,
        recovery_destination_generation_digest=target.generation_digest,
        recovery_origin_generation_digest=origin_generation,
    )


def _registered_recovery_successor(
    *,
    source: OperationBinding | None = None,
    recovery_target: ProtectedStateSnapshot | None = None,
    recovery_expected_state: ProtectedStateSnapshot | None = None,
    recovery_generation_class: GenerationClass | None = None,
    recovery_lifecycle_phase: LifecyclePhase | None = None,
    recovery_terminal_validator_digest: str = TERMINAL_VALIDATOR,
    recovery_effects: tuple[DeclaredEffect, ...] | None = None,
    recovery_successor_rollback: RollbackRecoveryContract | None = None,
    next_recovery_ordinal: int | None = None,
    authority_type=InMemoryAuthority,
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
            recovery_destination_generation_digest=(
                recovery_target.generation_digest
                if recovery_target is not None
                else source.rollback.recovery_destination_generation_digest
            ),
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
        ),
    )
    authority = authority_type(initial_active_state=failed_binding.expected_state)
    authority.append_intent(failed_binding)
    capability = authority.acquire_capability(failed_binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        failed_binding,
        capability=capability,
        observed_state=failed_binding.expected_state,
    )
    failure = authority.terminalize_operation(
        failed_binding,
        _terminal_observation(
            failed_binding,
            capability,
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    successor_phase = (
        recovery_lifecycle_phase
        if recovery_lifecycle_phase is not None
        else failed_binding.rollback.recovery_target.lifecycle_phase
    )
    expected_state = (
        recovery_expected_state
        if recovery_expected_state is not None
        else failed_binding.intended_state
    )
    intended_state = failed_binding.rollback.recovery_target
    recovery_destination = intended_state.generation_digest
    recovery_base = typed_operation_binding()
    recovery_rollback = replace(
        recovery_base.rollback,
        rollback_target=_rollback_target(expected_state),
        recovery_origin_generation_digest=recovery_destination,
    )
    recovery_binding = _binding_with_lifecycle_phase(
        recovery_base,
        successor_phase,
        operation_id="op-recovery-001",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=(
            recovery_generation_class
            if recovery_generation_class is not None
            else failed_binding.generation_class
        ),
        intent_digest="sha256:" + "e" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        target=failed_binding.target,
        expected_state=expected_state,
        intended_state=intended_state,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=recovery_destination,
        ),
        effects=(
            recovery_effects
            if recovery_effects is not None
            else typed_operation_binding().effects
        ),
        rollback=(
            recovery_successor_rollback
            if recovery_successor_rollback is not None
            else (
                _recovery_only_contract(
                    origin_generation=recovery_destination,
                    lifecycle_phase=successor_phase,
                    projection_digest=failed_binding.intended_state.projection_digest,
                    ordinal=next_recovery_ordinal,
                )
                if next_recovery_ordinal is not None
                else recovery_rollback
            )
        ),
        terminal_validator_digest=recovery_terminal_validator_digest,
    )
    authority.append_intent(recovery_binding)
    return authority, failed_binding, recovery_binding, failure


def _next_recovery_successor(
    authority: InMemoryAuthority,
    failed_binding: OperationBinding,
    failure: OperationResult,
    *,
    ordinal: int,
    expected_state: ProtectedStateSnapshot | None = None,
):
    predecessor_contract = failed_binding.rollback
    predecessor_target = predecessor_contract.recovery_target
    predecessor_destination = (
        predecessor_contract.recovery_destination_generation_digest
    )
    predecessor_record = predecessor_contract.recovery_contract_digest
    assert predecessor_target is not None
    assert predecessor_destination is not None
    assert predecessor_record is not None
    recovery_base = typed_operation_binding()
    recovery = _binding_with_lifecycle_phase(
        recovery_base,
        failed_binding.lifecycle_phase,
        operation_id=f"op-recovery-00{ordinal}",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=failed_binding.generation_class,
        intent_digest="sha256:" + f"{ordinal + 6:x}" * 64,
        plan_digest=predecessor_contract.recovery_plan_digest,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=predecessor_record,
        ),
        target=failed_binding.target,
        expected_state=(
            failed_binding.intended_state if expected_state is None else expected_state
        ),
        intended_state=predecessor_target,
        generation=GenerationBinding(
            mode=failed_binding.generation.mode,
            generation_digest=predecessor_destination,
            sentinel_digest=failed_binding.generation.sentinel_digest,
        ),
        rollback=_recovery_only_contract(
            origin_generation=predecessor_destination,
            lifecycle_phase=failed_binding.lifecycle_phase,
            projection_digest=failed_binding.intended_state.projection_digest,
            ordinal=ordinal + 1,
        ),
    )
    authority.append_intent(recovery)
    capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=ordinal + 1,
    )
    authority.execute_recovery(
        failed_binding,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=(
            failed_binding.intended_state if expected_state is None else expected_state
        ),
    )
    return recovery, capability


def _registered_b0_recovery_successor(*, sentinel_digest: str):
    source_base = typed_operation_binding()
    source = _binding_with_lifecycle_phase(
        source_base,
        LifecyclePhase.CAPTURED,
        operation_kind=CriticalOperationKind.COMPOSITE_AUTHORITY_TRANSITION,
        generation_class=GenerationClass.B0,
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
            source_base.rollback,
            mode=RecoveryMode.RECOVERY_ONLY,
            rollback_target=None,
            rollback_plan_digest=None,
            rollback_validator_digest=None,
            recovery_target=replace(
                source_base.rollback.recovery_target,
                record_digest="sha256:" + "4" * 64,
                lifecycle_phase=LifecyclePhase.CAPTURED,
            ),
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
        _terminal_observation(
            source,
            capability,
            record_digest="sha256:" + "d" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=source.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    successor_base = typed_operation_binding()
    successor = _binding_with_lifecycle_phase(
        successor_base,
        LifecyclePhase.CAPTURED,
        operation_id="recovery-composite-register",
        operation_kind=CriticalOperationKind.RECOVERY,
        generation_class=GenerationClass.B0,
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
            successor_base.rollback,
            rollback_target=_rollback_target(source.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    authority.append_intent(successor)
    return authority, source, successor, failure


def _rollback_required_authority(
    binding: OperationBinding | None = None,
    *,
    authority_type=InMemoryAuthority,
):
    binding = binding if binding is not None else typed_operation_binding()
    authority = authority_type(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            capability,
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
        binding.rollback.recovery_destination_generation_digest == RECOVERY_DESTINATION
    )
    assert binding.terminal_validator_digest == TERMINAL_VALIDATOR


def test_ordinary_operation_rejects_a_generation_other_than_its_intended_state():
    binding = typed_operation_binding()
    wrong_generation = "sha256:" + "5" * 64

    with pytest.raises(ValueError, match="operation generation"):
        replace(
            binding,
            subject=replace(binding.subject, record_digest=wrong_generation),
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=wrong_generation,
            ),
            rollback=replace(
                binding.rollback,
                recovery_origin_generation_digest=wrong_generation,
            ),
        )


def test_planned_rollback_binds_its_generation_to_the_expected_state_origin():
    binding = typed_operation_binding()
    planned_rollback = replace(
        binding,
        operation_kind=CriticalOperationKind.ROLLBACK,
        subject=replace(
            binding.subject,
            record_digest=binding.expected_state.generation_digest,
        ),
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=binding.expected_state.generation_digest,
        ),
        rollback=replace(
            binding.rollback,
            recovery_origin_generation_digest=(
                binding.expected_state.generation_digest
            ),
        ),
    )

    assert (
        planned_rollback.generation.generation_digest
        == planned_rollback.expected_state.generation_digest
    )
    with pytest.raises(ValueError, match="prestate and intended state must differ"):
        replace(planned_rollback, intended_state=planned_rollback.expected_state)

    with pytest.raises(ValueError, match="recovery origin"):
        replace(
            planned_rollback,
            rollback=replace(
                planned_rollback.rollback,
                recovery_origin_generation_digest=(
                    planned_rollback.intended_state.generation_digest
                ),
            ),
        )

    with pytest.raises(ValueError, match="operation generation"):
        replace(
            planned_rollback,
            subject=replace(
                planned_rollback.subject,
                record_digest=planned_rollback.intended_state.generation_digest,
            ),
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=planned_rollback.intended_state.generation_digest,
            ),
            rollback=replace(
                planned_rollback.rollback,
                recovery_origin_generation_digest=(
                    planned_rollback.intended_state.generation_digest
                ),
            ),
        )


def test_operation_binding_rejects_one_state_record_digest_for_distinct_content():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="state record digest"):
        replace(
            binding,
            intended_state=replace(
                binding.intended_state,
                record_digest=binding.expected_state.record_digest,
            ),
        )


def test_operation_binding_rejects_one_state_record_digest_across_phases():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="state record digest"):
        replace(
            binding,
            rollback=replace(
                binding.rollback,
                recovery_target=replace(
                    binding.expected_state,
                    lifecycle_phase=LifecyclePhase.PREVALIDATED,
                ),
            ),
        )


def test_operation_binding_accepts_an_exact_target_specific_source_phase():
    binding = typed_operation_binding()
    source = replace(
        binding.expected_state,
        lifecycle_phase=LifecyclePhase.PREVALIDATED,
    )

    transitioned = replace(
        binding,
        expected_state=source,
        rollback=replace(
            binding.rollback,
            rollback_target=_rollback_target(source),
            recovery_target=replace(
                binding.rollback.recovery_target,
                record_digest="sha256:" + "5" * 64,
            ),
        ),
    )

    assert transitioned.expected_state.lifecycle_phase is LifecyclePhase.PREVALIDATED
    assert transitioned.intended_state.lifecycle_phase is LifecyclePhase.ACTIVE


def test_operation_binding_rejects_an_intended_state_from_another_lifecycle_phase():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="intended protected-state lifecycle phase"):
        replace(
            binding,
            intended_state=replace(
                binding.intended_state,
                lifecycle_phase=LifecyclePhase.PREVALIDATED,
            ),
        )


def test_operation_binding_rejects_a_rollback_target_from_another_source_phase():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="rollback target lifecycle phase"):
        replace(
            binding,
            rollback=replace(
                binding.rollback,
                rollback_target=_rollback_target(
                    replace(
                        binding.expected_state,
                        record_digest="sha256:" + "5" * 64,
                        lifecycle_phase=LifecyclePhase.PREVALIDATED,
                    )
                ),
            ),
        )


def test_operation_binding_accepts_an_independently_phased_recovery_target():
    binding = typed_operation_binding()
    recovery_target = replace(
        binding.rollback.recovery_target,
        record_digest="sha256:" + "5" * 64,
        lifecycle_phase=LifecyclePhase.PREVALIDATED,
    )

    bound = replace(
        binding,
        rollback=replace(
            binding.rollback,
            recovery_target=recovery_target,
        ),
    )

    assert bound.rollback.recovery_target == recovery_target


def test_registered_operation_binding_has_no_public_mutation_storage():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    registered_digest = binding.digest()

    authority.append_intent(binding)

    assert not hasattr(binding, "__dict__")
    with pytest.raises(TypeError):
        vars(binding)
    with pytest.raises(AttributeError):
        binding.plan_digest = "sha256:" + "e" * 64

    capability = authority.acquire_capability(binding, fence_epoch=1)
    assert binding.digest() == registered_digest
    assert capability.operation_digest == registered_digest


def test_authority_rejects_cross_operation_state_record_rebinding_before_append():
    first = typed_operation_binding()
    rebound_expected = replace(
        first.expected_state,
        state_digest="sha256:" + "e" * 64,
    )
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
        expected_state=rebound_expected,
        rollback=replace(
            first.rollback,
            rollback_target=_rollback_target(rebound_expected),
            recovery_target=rebound_expected,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.append_intent(second)

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert [entry.kind for entry in authority.journal_entries] == ["operation_intent"]
    with pytest.raises(AuthorityUnavailable) as unknown:
        authority.operation_state(second.operation_id)
    assert unknown.value.code == "AUTHORITY_OPERATION_UNKNOWN"


def test_rejected_intent_cannot_poison_an_unbound_initial_state_claim():
    binding = typed_operation_binding()
    initial_state = replace(
        binding.expected_state,
        state_digest="sha256:" + "5" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=initial_state)

    with pytest.raises(AuthorityUnavailable) as rejected:
        authority.append_intent(binding)

    assert rejected.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert authority.journal_entries == ()
    assert authority.evidence_view().receipts == ()
    with pytest.raises(AuthorityUnavailable) as unknown:
        authority.operation_state(binding.operation_id)
    assert unknown.value.code == "AUTHORITY_OPERATION_UNKNOWN"

    corrected = replace(
        binding,
        expected_state=initial_state,
        rollback=replace(
            binding.rollback,
            rollback_target=_rollback_target(initial_state),
            recovery_target=initial_state,
        ),
    )
    receipt = authority.append_intent(corrected)

    assert receipt.sequence == 1
    assert authority.observe_active(binding.target) == initial_state
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    capability = authority.acquire_capability(corrected, fence_epoch=1)
    assert capability.fence_epoch == 1
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )


def test_authority_rejects_state_record_rebinding_across_lifecycle_phases():
    base = typed_operation_binding()
    first = replace(
        base,
        operation_kind=CriticalOperationKind.BLOCKING_SCENARIO,
        subject=OperationSubject(
            kind=OperationSubjectKind.GATE_OCCURRENCE,
            record_digest=SUBJECT,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.SERVICE,
            target_id="inference-service",
        ),
    )
    second = _binding_with_lifecycle_phase(
        first,
        LifecyclePhase.PREVALIDATED,
        operation_id="op-blocking-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.append_intent(second)

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert [entry.kind for entry in authority.journal_entries] == ["operation_intent"]
    with pytest.raises(AuthorityUnavailable) as unknown:
        authority.operation_state(second.operation_id)
    assert unknown.value.code == "AUTHORITY_OPERATION_UNKNOWN"


def test_authority_allows_exact_state_record_reuse_on_the_same_target():
    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
        intended_state=replace(
            first.intended_state,
            record_digest="sha256:" + "c" * 64,
            state_digest="sha256:" + "b" * 64,
        ),
    )
    authority = InMemoryAuthority(initial_active_state=first.expected_state)

    first_receipt = authority.append_intent(first)
    second_receipt = authority.append_intent(second)

    assert first_receipt.sequence == 1
    assert second_receipt.sequence == 2
    assert (
        authority.operation_state(first.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert (
        authority.operation_state(second.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def test_authority_rejects_state_record_reuse_for_a_distinct_target():
    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
        target=replace(first.target, target_id="other-host"),
    )
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.append_intent(second)

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert [entry.kind for entry in authority.journal_entries] == ["operation_intent"]


def _mutable_authority_value(value, *, field_name: str):
    missing = object()
    value_type = type(value)

    def getattribute(instance, name):
        if name == field_name:
            replacement = object.__getattribute__(instance, "__dict__").get(
                "replacement",
                missing,
            )
            if replacement is not missing:
                return replacement
        return value_type.__getattribute__(instance, name)

    mutable_type = type(
        f"Mutable{value_type.__name__}",
        (value_type,),
        {"__getattribute__": getattribute},
    )
    return mutable_type(
        **{field.name: getattr(value, field.name) for field in fields(value)}
    )


def test_append_intent_snapshots_a_mutable_operation_binding_subclass():
    base = typed_operation_binding()

    class MutableOperationBinding(OperationBinding):
        def digest(self):
            return self.mutable_digest

    binding = MutableOperationBinding(
        **{field.name: getattr(base, field.name) for field in fields(base)}
    )
    binding.mutable_digest = base.digest()
    authority = InMemoryAuthority(initial_active_state=base.expected_state)
    authority.append_intent(binding)

    binding.mutable_digest = "sha256:" + "e" * 64
    capability = authority.acquire_capability(binding, fence_epoch=1)
    mutation = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=base.expected_state,
    )
    terminal = authority.terminalize_operation(
        binding,
        _terminal_observation(
            base,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=base.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert capability.operation_digest == base.digest()
    assert capability.operation_digest != binding.digest()
    assert mutation.state is OperationState.MUTATED_PENDING_VALIDATION
    assert terminal.state is OperationState.SUCCEEDED


@pytest.mark.parametrize(
    ("nested_name", "field_name", "replacement"),
    [
        ("effect", "effect_id", "substituted-effect"),
        ("target", "target_id", "substituted-host"),
        ("expected_state", "record_digest", "sha256:" + "e" * 64),
        ("rollback", "recovery_plan_digest", "sha256:" + "e" * 64),
    ],
)
def test_registered_binding_rejects_nested_subclass_drift(
    nested_name,
    field_name,
    replacement,
):
    base = typed_operation_binding()
    if nested_name == "effect":
        nested = _mutable_authority_value(base.effects[0], field_name=field_name)
        binding = replace(base, effects=[nested])
    else:
        nested = _mutable_authority_value(
            getattr(base, nested_name),
            field_name=field_name,
        )
        binding = replace(base, **{nested_name: nested})
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)

    nested.replacement = replacement

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(binding, fence_epoch=1)
    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"


@pytest.mark.parametrize("phase", ["execute", "terminal"])
@pytest.mark.parametrize(
    ("nested_name", "field_name", "replacement"),
    [
        ("effect", "effect_id", "substituted-effect"),
        ("target", "target_id", "substituted-host"),
        ("expected_state", "record_digest", "sha256:" + "e" * 64),
        ("rollback", "recovery_plan_digest", "sha256:" + "e" * 64),
    ],
)
def test_registered_binding_rejects_nested_drift_during_transition_or_terminal(
    phase,
    nested_name,
    field_name,
    replacement,
):
    base = typed_operation_binding()
    if nested_name == "effect":
        nested = _mutable_authority_value(base.effects[0], field_name=field_name)
        binding = replace(base, effects=[nested])
    else:
        nested = _mutable_authority_value(
            getattr(base, nested_name),
            field_name=field_name,
        )
        binding = replace(base, **{nested_name: nested})
    authority = InMemoryAuthority(initial_active_state=base.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    if phase == "terminal":
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=base.expected_state,
        )

    nested.replacement = replacement

    with pytest.raises(AuthorityUnavailable) as caught:
        if phase == "execute":
            authority.guarded_compare_and_swap(
                binding,
                capability=capability,
                observed_state=base.expected_state,
            )
        else:
            authority.terminalize_operation(
                binding,
                _terminal_observation(
                    base,
                    capability,
                    record_digest="sha256:" + "f" * 64,
                    validator_digest=TERMINAL_VALIDATOR,
                    observed_state=base.intended_state,
                    outcome=TerminalOutcome.PASS,
                    observed_effect_ids={"package-database"},
                ),
            )
    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"


def test_authority_binding_normalizes_and_freezes_nested_value_objects():
    effects = list(typed_operation_binding().effects)
    binding = replace(typed_operation_binding(), effects=effects)
    binding_digest = binding.digest()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    substrate_bindings = [
        SubstrateBinding(role=AuthorityRole.SIGNER, provider="remote-signer"),
        SubstrateBinding(role=AuthorityRole.JOURNAL, provider="remote-journal"),
    ]
    topology = ProductionTopology(bindings=substrate_bindings)

    effects.clear()
    substrate_bindings.clear()
    capability = authority.acquire_capability(binding, fence_epoch=1)

    assert len(binding.effects) == 1
    assert binding.digest() == binding_digest
    assert capability.operation_digest == binding_digest
    assert [item.role for item in topology.bindings] == [
        AuthorityRole.SIGNER,
        AuthorityRole.JOURNAL,
    ]
    nested_values = (
        binding.generation,
        binding.subject,
        binding.target,
        binding.expected_state,
        binding.intended_state,
        binding.effects[0],
        binding.rollback,
        binding.rollback.rollback_target,
        binding.rollback.recovery_target,
        *topology.bindings,
        topology,
    )
    assert all(not hasattr(value, "__dict__") for value in nested_values)
    with pytest.raises(AttributeError):
        binding.effects[0].effect_id = "substituted-effect"
    with pytest.raises(AttributeError):
        topology.bindings[0].provider = "substituted-signer"


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
    binding = _binding_with_lifecycle_phase(
        typed_operation_binding(),
        LifecyclePhase.PUBLISHED,
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.C,
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
    binding = _binding_with_lifecycle_phase(
        typed_operation_binding(),
        LifecyclePhase.PUBLISHED,
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.F,
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
        _binding_with_lifecycle_phase(
            typed_operation_binding(),
            lifecycle_phase,
            generation_class=generation_class,
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
    assert successor.generation.mode is GenerationBindingMode.B0_CAPTURE_SENTINEL
    assert (
        successor.generation.generation_digest
        == source.rollback.recovery_destination_generation_digest
    )
    assert (
        successor.generation.generation_digest
        == source.rollback.recovery_target.generation_digest
    )
    assert successor.generation.generation_digest != source.generation.generation_digest
    assert capability.fenced.target == source.target
    assert capability.predecessor_fence_epoch == 1
    assert capability.fenced.fence_epoch == 2


def test_b0_recovery_successor_cannot_drop_the_sentinel_binding_mode():
    sentinel = "sha256:" + "5" * 64
    _, _, successor, _ = _registered_b0_recovery_successor(
        sentinel_digest=sentinel,
    )

    with pytest.raises(ValueError, match="operation envelope coordinates"):
        replace(
            successor,
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=successor.generation.generation_digest,
            ),
        )


def test_b0_recovery_successor_cannot_bind_the_failed_generation_as_destination():
    sentinel = "sha256:" + "5" * 64
    _, source, successor, _ = _registered_b0_recovery_successor(
        sentinel_digest=sentinel,
    )

    with pytest.raises(ValueError, match="operation generation"):
        replace(
            successor,
            generation=GenerationBinding(
                mode=GenerationBindingMode.B0_CAPTURE_SENTINEL,
                generation_digest=source.generation.generation_digest,
                sentinel_digest=sentinel,
            ),
        )


def test_rollback_target_binds_an_exact_snapshot_and_destination_generation():
    snapshot = ProtectedStateSnapshot(
        record_digest="sha256:" + "f" * 64,
        generation_digest=RECOVERY_DESTINATION,
        lifecycle_phase=LifecyclePhase.ACTIVE,
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
        _terminal_observation(
            binding,
            capability,
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


def test_forward_capability_redelivery_retains_the_exact_fence_and_receipt():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    issued = authority.acquire_capability(binding, fence_epoch=1)
    journal_before_redelivery = authority.journal_entries
    evidence_before_redelivery = authority.evidence_view()

    redelivered = authority.acquire_capability(binding, fence_epoch=1)

    assert redelivered == issued
    assert redelivered is not issued
    assert redelivered.intended_state is not issued.intended_state
    assert redelivered.fence_epoch == issued.fence_epoch == 1
    assert redelivered.intended_state == binding.intended_state
    assert authority.journal_entries == journal_before_redelivery
    assert authority.evidence_view() == evidence_before_redelivery
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )
    assert authority.observe_active(binding.target) == binding.expected_state
    assert (
        authority.guarded_compare_and_swap(
            binding,
            capability=redelivered,
            observed_state=binding.expected_state,
        ).state
        is OperationState.MUTATED_PENDING_VALIDATION
    )


@pytest.mark.parametrize("requested_fence", [1, 3], ids=("older", "newer"))
def test_forward_redelivery_rejects_a_different_fence_without_rotation(
    requested_fence,
):
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    issued = authority.acquire_capability(binding, fence_epoch=2)
    journal_before_retry = authority.journal_entries
    evidence_before_retry = authority.evidence_view()

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(binding, fence_epoch=requested_fence)

    assert caught.value.code == "AUTHORITY_FENCE_STALE"
    assert authority.journal_entries == journal_before_retry
    assert authority.evidence_view() == evidence_before_retry
    assert authority.observe_active(binding.target) == binding.expected_state
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )
    assert (
        authority.guarded_compare_and_swap(
            binding,
            capability=issued,
            observed_state=binding.expected_state,
        ).state
        is OperationState.MUTATED_PENDING_VALIDATION
    )


def test_forward_acquisition_never_displaces_another_operation_guard():
    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)
    authority.append_intent(second)
    first_capability = authority.acquire_capability(first, fence_epoch=1)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(second, fence_epoch=2)

    assert caught.value.code == "AUTHORITY_TARGET_GUARDED"
    assert (
        authority.guarded_compare_and_swap(
            first,
            capability=first_capability,
            observed_state=first.expected_state,
        ).state
        is OperationState.MUTATED_PENDING_VALIDATION
    )


def test_forward_terminal_observation_loss_does_not_claim_the_terminal_record():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    binding = typed_operation_binding()
    authority = ToggleObservationAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    observation = _terminal_observation(
        binding,
        capability,
        record_digest="sha256:" + "1" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=binding.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_operation(binding, observation)

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.MUTATED_PENDING_VALIDATION
    )
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        expected_state=binding.intended_state,
        intended_state=replace(
            binding.intended_state,
            record_digest="sha256:" + "4" * 64,
            state_digest="sha256:" + "5" * 64,
        ),
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=2)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"

    authority.observation_available = True
    terminal = authority.terminalize_operation(binding, observation)

    assert terminal.state is OperationState.SUCCEEDED
    assert authority.acquire_capability(successor, fence_epoch=2).fence_epoch == 2


def test_forward_terminal_rejects_replay_from_a_distinct_capability():
    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        plan_digest="sha256:" + "f" * 64,
    )
    first_authority = InMemoryAuthority(initial_active_state=first.expected_state)
    second_authority = InMemoryAuthority(initial_active_state=second.expected_state)
    first_authority.append_intent(first)
    second_authority.append_intent(second)
    first_capability = first_authority.acquire_capability(first, fence_epoch=1)
    second_capability = second_authority.acquire_capability(second, fence_epoch=1)
    first_authority.guarded_compare_and_swap(
        first,
        capability=first_capability,
        observed_state=first.expected_state,
    )
    second_authority.guarded_compare_and_swap(
        second,
        capability=second_capability,
        observed_state=second.expected_state,
    )
    observation = _terminal_observation(
        first,
        first_capability,
        record_digest="sha256:" + "1" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=first.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    assert (
        first_authority.terminalize_operation(first, observation).state
        is OperationState.SUCCEEDED
    )
    with pytest.raises(AuthorityUnavailable) as caught:
        second_authority.terminalize_operation(second, observation)
    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert (
        second_authority.terminalize_operation(
            second,
            _terminal_observation(
                second,
                second_capability,
                record_digest="sha256:" + "2" * 64,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=second.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.SUCCEEDED
    )


def test_concurrent_forward_acquisitions_have_one_exact_target_guard_owner():
    class SlowObservationAuthority(InMemoryAuthority):
        def observe_active(self, target=None):
            sleep(0.05)
            return super().observe_active(target)

    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        plan_digest="sha256:" + "f" * 64,
    )
    authority = SlowObservationAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)
    authority.append_intent(second)
    start = Barrier(3)

    def acquire(binding):
        start.wait()
        try:
            return authority.acquire_capability(binding, fence_epoch=1)
        except AuthorityUnavailable as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(acquire, first)
        second_future = executor.submit(acquire, second)
        start.wait()
        outcomes = (first_future.result(), second_future.result())

    capabilities = [item for item in outcomes if isinstance(item, FencedCapability)]
    failures = [item for item in outcomes if isinstance(item, AuthorityUnavailable)]
    assert len(capabilities) == 1
    assert len(failures) == 1
    assert failures[0].code == "AUTHORITY_TARGET_GUARDED"
    capability = capabilities[0]
    holder = first if capability.operation_id == first.operation_id else second
    nonholder = second if holder is first else first

    with pytest.raises(AuthorityUnavailable) as nonholder_execution:
        authority.guarded_compare_and_swap(
            nonholder,
            capability=capability,
            observed_state=nonholder.expected_state,
        )
    assert nonholder_execution.value.code == "AUTHORITY_BINDING_MISMATCH"

    authority.guarded_compare_and_swap(
        holder,
        capability=capability,
        observed_state=holder.expected_state,
    )
    third = replace(
        first,
        operation_id="op-activation-003",
        intent_digest="sha256:" + "3" * 64,
        plan_digest="sha256:" + "4" * 64,
        expected_state=holder.intended_state,
        intended_state=replace(
            holder.intended_state,
            record_digest="sha256:" + "5" * 64,
            state_digest="sha256:" + "6" * 64,
        ),
    )
    authority.append_intent(third)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(third, fence_epoch=2)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"

    terminal = authority.terminalize_operation(
        holder,
        _terminal_observation(
            holder,
            capability,
            record_digest="sha256:" + "7" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=holder.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert terminal.state is OperationState.SUCCEEDED
    assert authority.acquire_capability(third, fence_epoch=2).fence_epoch == 2


def test_forward_authority_outputs_and_journal_are_publicly_immutable():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    intent_receipt = authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    mutation = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    observed_effect_ids = {"package-database"}
    observation = _terminal_observation(
        binding,
        capability,
        record_digest="sha256:" + "1" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=binding.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids=observed_effect_ids,
    )
    terminal = authority.terminalize_operation(binding, observation)
    journal_entries = authority.journal_entries
    evidence_view = authority.evidence_view()

    observed_effect_ids.clear()

    assert observation.observed_effect_ids == frozenset({"package-database"})
    public_values = (
        intent_receipt,
        capability,
        mutation,
        observation,
        terminal,
        *journal_entries,
        evidence_view,
        *evidence_view.receipts,
    )
    assert all(not hasattr(value, "__dict__") for value in public_values)
    first_entry = journal_entries[0]
    with pytest.raises(AttributeError):
        first_entry.record_digest = "sha256:" + "e" * 64
    assert authority.journal_entries[0] == first_entry


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
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )


def test_forward_capability_is_bound_to_its_issuing_authority_instance():
    binding = typed_operation_binding()
    first = InMemoryAuthority(initial_active_state=binding.expected_state)
    second = InMemoryAuthority(initial_active_state=binding.expected_state)
    first.append_intent(binding)
    second.append_intent(binding)
    first_capability = first.acquire_capability(binding, fence_epoch=1)
    second_capability = second.acquire_capability(binding, fence_epoch=1)

    assert first_capability.capability_id != second_capability.capability_id
    with pytest.raises(AuthorityUnavailable) as caught:
        second.guarded_compare_and_swap(
            binding,
            capability=first_capability,
            observed_state=binding.expected_state,
        )

    assert caught.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert (
        second.guarded_compare_and_swap(
            binding,
            capability=second_capability,
            observed_state=binding.expected_state,
        ).state
        is OperationState.MUTATED_PENDING_VALIDATION
    )


def test_forward_terminal_rejects_an_observation_from_another_authority_instance():
    binding = typed_operation_binding()
    first = InMemoryAuthority(initial_active_state=binding.expected_state)
    second = InMemoryAuthority(initial_active_state=binding.expected_state)
    first.append_intent(binding)
    second.append_intent(binding)
    first_capability = first.acquire_capability(binding, fence_epoch=1)
    second_capability = second.acquire_capability(binding, fence_epoch=1)
    first.guarded_compare_and_swap(
        binding,
        capability=first_capability,
        observed_state=binding.expected_state,
    )
    second.guarded_compare_and_swap(
        binding,
        capability=second_capability,
        observed_state=binding.expected_state,
    )
    foreign = _terminal_observation(
        binding,
        first_capability,
        record_digest="sha256:" + "4" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=binding.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        second.terminalize_operation(binding, foreign)

    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert (
        second.terminalize_operation(
            binding,
            _terminal_observation(
                binding,
                second_capability,
                record_digest="sha256:" + "5" * 64,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=binding.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.SUCCEEDED
    )


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
        _terminal_observation(
            binding,
            capability,
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
        _terminal_observation(
            binding,
            rollback_capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    assert rolled_back.state is OperationState.ROLLED_BACK
    assert all(
        not hasattr(value, "__dict__")
        for value in (failed, rollback_capability, pending, rolled_back)
    )


def test_rollback_terminal_rejects_cross_phase_and_distinct_operation_replay():
    first = typed_operation_binding()
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        plan_digest="sha256:" + "f" * 64,
    )

    def ready_for_rollback(binding):
        authority = InMemoryAuthority(initial_active_state=binding.expected_state)
        authority.append_intent(binding)
        forward_capability = authority.acquire_capability(binding, fence_epoch=1)
        authority.guarded_compare_and_swap(
            binding,
            capability=forward_capability,
            observed_state=binding.expected_state,
        )
        forward_observation = _terminal_observation(
            binding,
            forward_capability,
            record_digest="sha256:" + "4" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.FAIL,
        )
        authority.terminalize_operation(binding, forward_observation)
        rollback_capability = authority.acquire_rollback_capability(
            binding,
            fence_epoch=2,
        )
        authority.execute_rollback(
            binding,
            capability=rollback_capability,
            observed_state=binding.intended_state,
        )
        return authority, forward_observation, rollback_capability

    first_authority, forward_observation, first_capability = ready_for_rollback(first)
    second_authority, _, second_capability = ready_for_rollback(second)

    with pytest.raises(AuthorityUnavailable) as cross_phase:
        first_authority.terminalize_rollback(first, forward_observation)
    assert cross_phase.value.code == "AUTHORITY_BINDING_MISMATCH"

    rollback_observation = _terminal_observation(
        first,
        first_capability,
        record_digest="sha256:" + "5" * 64,
        validator_digest=ROLLBACK_VALIDATOR,
        observed_state=first.expected_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )
    assert (
        first_authority.terminalize_rollback(first, rollback_observation).state
        is OperationState.ROLLED_BACK
    )
    with pytest.raises(AuthorityUnavailable) as distinct_operation:
        second_authority.terminalize_rollback(second, rollback_observation)
    assert distinct_operation.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert (
        second_authority.terminalize_rollback(
            second,
            _terminal_observation(
                second,
                second_capability,
                record_digest="sha256:" + "6" * 64,
                validator_digest=ROLLBACK_VALIDATOR,
                observed_state=second.expected_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.ROLLED_BACK
    )


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
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )
    rollback_capability = authority.acquire_rollback_capability(
        binding,
        fence_epoch=2,
    )
    assert rollback_capability.fence_epoch == 2


def test_missing_observation_during_rollback_does_not_consume_the_capability():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    binding = typed_operation_binding()
    authority = ToggleObservationAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    forward_capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=forward_capability,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            forward_capability,
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
    fresh_caller_state = replace(
        binding.intended_state,
        record_digest="sha256:" + "4" * 64,
    )
    unrelated_target = replace(binding.target, target_id="unrelated-host")
    journal_before_rejection = authority.journal_entries
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.execute_rollback(
            binding,
            capability=rollback_capability,
            observed_state=fresh_caller_state,
        )

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )
    assert authority.journal_entries == journal_before_rejection

    authority.configure_active(unrelated_target, fresh_caller_state)

    authority.observation_available = True
    assert authority.observe_active(unrelated_target) == fresh_caller_state
    pending = authority.execute_rollback(
        binding,
        capability=rollback_capability,
        observed_state=binding.intended_state,
    )

    assert pending.state is OperationState.ROLLBACK_PENDING_VALIDATION


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
    foreign_authority, foreign_binding = _rollback_required_authority(foreign_binding)
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


def test_rollback_capability_is_bound_to_its_issuing_authority_instance():
    first, binding = _rollback_required_authority()
    second, _ = _rollback_required_authority(binding)
    first_capability = first.acquire_rollback_capability(binding, fence_epoch=2)
    second_capability = second.acquire_rollback_capability(binding, fence_epoch=2)

    assert first_capability.capability_id != second_capability.capability_id
    with pytest.raises(AuthorityUnavailable) as caught:
        second.execute_rollback(
            binding,
            capability=first_capability,
            observed_state=binding.intended_state,
        )

    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert (
        second.execute_rollback(
            binding,
            capability=second_capability,
            observed_state=binding.intended_state,
        ).state
        is OperationState.ROLLBACK_PENDING_VALIDATION
    )


def test_rollback_terminal_rejects_an_observation_from_another_authority_instance():
    first, binding = _rollback_required_authority()
    second, _ = _rollback_required_authority(binding)
    first_capability = first.acquire_rollback_capability(binding, fence_epoch=2)
    second_capability = second.acquire_rollback_capability(binding, fence_epoch=2)
    first.execute_rollback(
        binding,
        capability=first_capability,
        observed_state=binding.intended_state,
    )
    second.execute_rollback(
        binding,
        capability=second_capability,
        observed_state=binding.intended_state,
    )
    foreign = _terminal_observation(
        binding,
        first_capability,
        record_digest="sha256:" + "7" * 64,
        validator_digest=ROLLBACK_VALIDATOR,
        observed_state=binding.expected_state,
        outcome=TerminalOutcome.PASS,
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        second.terminalize_rollback(binding, foreign)

    assert caught.value.code == "AUTHORITY_BINDING_MISMATCH"
    assert (
        second.terminalize_rollback(
            binding,
            _terminal_observation(
                binding,
                second_capability,
                record_digest="sha256:" + "8" * 64,
                validator_digest=ROLLBACK_VALIDATOR,
                observed_state=binding.expected_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.ROLLED_BACK
    )


def test_rollback_terminal_observation_loss_does_not_claim_the_terminal_record():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    binding = typed_operation_binding()
    authority = ToggleObservationAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    forward_capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=forward_capability,
        observed_state=binding.expected_state,
    )
    authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            forward_capability,
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
    observation = _terminal_observation(
        binding,
        rollback_capability,
        record_digest="sha256:" + "3" * 64,
        validator_digest=ROLLBACK_VALIDATOR,
        observed_state=binding.expected_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_rollback(binding, observation)

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_PENDING_VALIDATION
    )
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        expected_state=binding.expected_state,
        intended_state=replace(
            binding.intended_state,
            record_digest="sha256:" + "4" * 64,
            state_digest="sha256:" + "5" * 64,
        ),
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"

    authority.observation_available = True
    terminal = authority.terminalize_rollback(binding, observation)

    assert terminal.state is OperationState.ROLLED_BACK
    assert authority.acquire_capability(successor, fence_epoch=3).fence_epoch == 3


def test_rollback_terminal_rejects_an_undeclared_interval_violation_effect():
    authority, binding = _rollback_required_authority()
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )

    result = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
            interval_violation_effect_ids={"undeclared-effect"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"


@pytest.mark.parametrize(
    ("effect_mode", "effect_claim"),
    [
        ("observable", {}),
        (
            "observable",
            {"observed_effect_ids": {"package-database", "undeclared-effect"}},
        ),
        (
            "observable",
            {
                "observed_effect_ids": {"package-database"},
                "interval_enforced_effect_ids": {"undeclared-effect"},
            },
        ),
        ("forbidden", {}),
    ],
)
def test_rollback_terminal_closes_effect_claims_and_retains_the_guard(
    effect_mode,
    effect_claim,
):
    binding = typed_operation_binding()
    if effect_mode == "forbidden":
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
    authority, binding = _rollback_required_authority(binding)
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )
    observation = _terminal_observation(
        binding,
        capability,
        record_digest="sha256:" + "3" * 64,
        validator_digest=ROLLBACK_VALIDATOR,
        observed_state=binding.expected_state,
        outcome=TerminalOutcome.PASS,
        **effect_claim,
    )

    result = authority.terminalize_rollback(binding, observation)

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"
    assert result.failure_record_digest == observation.record_digest
    assert authority.operation_state(binding.operation_id) is result.state
    assert authority.journal_entries[-1].record_digest == observation.record_digest
    assert authority.evidence_view().receipts[-1].receipt_id == result.record_digest
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        plan_digest="sha256:" + "f" * 64,
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"


def test_rollback_execution_normalizes_a_deceptive_adapter_observation():
    authority, binding = _rollback_required_authority(
        authority_type=_SwitchableObservationAuthority
    )
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.observation_override = _deceptive_snapshot(binding.intended_state)

    result = authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_PRESTATE_MISMATCH"


def test_rollback_prestate_drift_recovers_from_the_exact_retained_active_state():
    authority, failed = _rollback_required_authority()
    capability = authority.acquire_rollback_capability(failed, fence_epoch=2)
    drifted = replace(
        failed.intended_state,
        record_digest="sha256:" + "4" * 64,
        state_digest="sha256:" + "5" * 64,
    )
    authority.configure_active(failed.target, drifted)

    failure = authority.execute_rollback(
        failed,
        capability=capability,
        observed_state=drifted,
    )
    wrong_successor = replace(
        failed,
        operation_id="op-recovery-wrong",
        operation_kind=CriticalOperationKind.RECOVERY,
        intent_digest="sha256:" + "6" * 64,
        plan_digest=RECOVERY_PLAN,
        subject=OperationSubject(
            kind=OperationSubjectKind.CONTROL_RECORD,
            record_digest=RECOVERY_CONTRACT,
        ),
        expected_state=failed.intended_state,
        intended_state=failed.rollback.recovery_target,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=RECOVERY_DESTINATION,
        ),
        rollback=replace(
            failed.rollback,
            rollback_target=_rollback_target(failed.intended_state),
            recovery_origin_generation_digest=RECOVERY_DESTINATION,
        ),
    )
    successor = replace(
        wrong_successor,
        operation_id="op-recovery-actual",
        intent_digest="sha256:" + "7" * 64,
        expected_state=drifted,
        rollback=replace(
            wrong_successor.rollback,
            rollback_target=_rollback_target(drifted),
        ),
    )
    authority.append_intent(wrong_successor)
    authority.append_intent(successor)

    with pytest.raises(AuthorityUnavailable) as rejected:
        authority.acquire_recovery_capability(
            failed,
            wrong_successor,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=3,
        )
    assert rejected.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"

    recovery_capability = authority.acquire_recovery_capability(
        failed,
        successor,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=3,
    )
    authority.execute_recovery(
        failed,
        successor,
        failure=failure,
        capability=recovery_capability,
        observed_state=drifted,
    )
    result = authority.terminalize_recovery(
        failed,
        successor,
        _terminal_observation(
            successor,
            recovery_capability,
            record_digest="sha256:" + "8" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=successor.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.RECOVERED
    assert authority.operation_state(failed.operation_id) is OperationState.RECOVERED
    assert authority.observe_active(failed.target) == successor.intended_state


def test_rollback_execution_rejects_state_record_rebinding_before_consumption():
    authority, binding = _rollback_required_authority()
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    rebound = replace(
        binding.intended_state,
        state_digest="sha256:" + "e" * 64,
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.execute_rollback(
            binding,
            capability=capability,
            observed_state=rebound,
        )

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )

    result = authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )

    assert result.state is OperationState.ROLLBACK_PENDING_VALIDATION


def test_rollback_terminal_normalizes_a_deceptive_adapter_observation():
    authority, binding = _rollback_required_authority(
        authority_type=_SwitchableObservationAuthority
    )
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )
    authority.observation_override = _deceptive_snapshot(binding.expected_state)

    result = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"


def test_rollback_terminal_rejects_a_declared_forbidden_interval_violation():
    binding = replace(
        typed_operation_binding(),
        effects=(
            DeclaredEffect(
                effect_id="mixed-endpoint",
                classification=EffectClass.FORBIDDEN_TRANSIENT,
                projection_digest=EFFECT_PROJECTION,
            ),
        ),
    )
    authority, binding = _rollback_required_authority(binding)
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )

    result = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
            interval_violation_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"


def test_rollback_terminal_rejects_an_observed_declared_forbidden_effect():
    binding = replace(
        typed_operation_binding(),
        effects=(
            DeclaredEffect(
                effect_id="mixed-endpoint",
                classification=EffectClass.FORBIDDEN_TRANSIENT,
                projection_digest=EFFECT_PROJECTION,
            ),
        ),
    )
    authority, binding = _rollback_required_authority(binding)
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )
    observation = _terminal_observation(
        binding,
        capability,
        record_digest="sha256:" + "3" * 64,
        validator_digest=ROLLBACK_VALIDATOR,
        observed_state=binding.expected_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"mixed-endpoint"},
        interval_enforced_effect_ids={"mixed-endpoint"},
    )

    result = authority.terminalize_rollback(binding, observation)

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"
    assert result.failure_record_digest == observation.record_digest
    assert authority.operation_state(binding.operation_id) is result.state
    assert authority.journal_entries[-1].kind == "rollback_recovery_required"
    assert authority.journal_entries[-1].record_digest == observation.record_digest
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "e" * 64,
        plan_digest="sha256:" + "f" * 64,
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"


def test_rollback_terminal_allows_an_enforced_unobserved_forbidden_effect():
    binding = replace(
        typed_operation_binding(),
        effects=(
            DeclaredEffect(
                effect_id="mixed-endpoint",
                classification=EffectClass.FORBIDDEN_TRANSIENT,
                projection_digest=EFFECT_PROJECTION,
            ),
        ),
    )
    authority, binding = _rollback_required_authority(binding)
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )

    result = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.ROLLED_BACK
    assert result.failure_code is None
    assert authority.journal_entries[-1].kind == "rollback_succeeded"


def test_rollback_capability_redelivery_retains_the_exact_attempt_and_receipt():
    authority, binding = _rollback_required_authority()
    issued = authority.acquire_rollback_capability(binding, fence_epoch=2)
    journal_before_redelivery = authority.journal_entries
    evidence_before_redelivery = authority.evidence_view()

    redelivered = authority.acquire_rollback_capability(binding, fence_epoch=2)

    rollback_target = binding.rollback.rollback_target
    assert rollback_target is not None
    assert redelivered == issued
    assert redelivered is not issued
    assert redelivered.intended_state is not issued.intended_state
    assert redelivered.fence_epoch == issued.fence_epoch == 2
    assert redelivered.intended_state == rollback_target.protected_state
    assert authority.journal_entries == journal_before_redelivery
    assert authority.evidence_view() == evidence_before_redelivery
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )
    assert authority.observe_active(binding.target) == binding.intended_state
    assert (
        authority.execute_rollback(
            binding,
            capability=redelivered,
            observed_state=binding.intended_state,
        ).state
        is OperationState.ROLLBACK_PENDING_VALIDATION
    )


def test_newer_rollback_fence_supersedes_an_unconsumed_capability():
    authority, binding = _rollback_required_authority()
    superseded = authority.acquire_rollback_capability(binding, fence_epoch=2)
    current = authority.acquire_rollback_capability(binding, fence_epoch=3)

    with pytest.raises(AuthorityUnavailable) as exc_info:
        authority.execute_rollback(
            binding,
            capability=superseded,
            observed_state=binding.intended_state,
        )

    assert exc_info.value.code == "AUTHORITY_FENCE_STALE"
    assert authority.observe_active() == binding.intended_state
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )

    pending = authority.execute_rollback(
        binding,
        capability=current,
        observed_state=binding.intended_state,
    )
    assert pending.state is OperationState.ROLLBACK_PENDING_VALIDATION


def test_rollback_capability_receipts_bind_each_superseding_issuance_before_transition():
    authority, binding = _rollback_required_authority()
    other, other_binding = _rollback_required_authority()

    superseded = authority.acquire_rollback_capability(binding, fence_epoch=2)
    current = authority.acquire_rollback_capability(binding, fence_epoch=3)
    other_capability = other.acquire_rollback_capability(
        other_binding,
        fence_epoch=2,
    )

    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "fenced_capability",
        "guarded_transition",
        "operation_terminal_failed",
        "rollback_capability",
        "rollback_capability",
    ]
    entries = authority.journal_entries[-2:]
    receipts = authority.evidence_view().receipts[-2:]
    for entry, receipt, capability in zip(
        entries,
        receipts,
        (superseded, current),
        strict=True,
    ):
        assert entry.record_digest == capability.capability_id
        assert receipt.kind == "rollback_capability"
        assert receipt.sequence == entry.sequence
        assert receipt.operation_id == binding.operation_id
        assert receipt.record_digest == capability.capability_id
    assert receipts[0].receipt_id != other.evidence_view().receipts[-1].receipt_id
    assert (
        other.evidence_view().receipts[-1].record_digest
        == other_capability.capability_id
    )
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )

    with pytest.raises(AuthorityUnavailable) as stale:
        authority.execute_rollback(
            binding,
            capability=superseded,
            observed_state=binding.intended_state,
        )
    assert stale.value.code == "AUTHORITY_FENCE_STALE"

    result = authority.execute_rollback(
        binding,
        capability=current,
        observed_state=binding.intended_state,
    )

    assert result.state is OperationState.ROLLBACK_PENDING_VALIDATION
    assert authority.journal_entries[-1].kind == "rollback_transition"


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
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_REQUIRED
    )
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
            _terminal_observation(
                binding,
                rollback_capability,
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
        _terminal_observation(
            binding,
            rollback_capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
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
        _terminal_observation(
            binding,
            capability,
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
        _terminal_observation(
            binding,
            rollback_capability,
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
        _terminal_observation(
            failed_binding,
            capability,
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
        recovery_capability.predecessor_failure_record_digest == failure_terminal_digest
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
        _terminal_observation(
            recovery_binding,
            recovery_capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=failed_binding.rollback.recovery_target,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids=frozenset({"package-database"}),
        ),
    )

    assert recovered.state is OperationState.RECOVERED
    assert (
        authority.operation_state(failed_binding.operation_id)
        is OperationState.RECOVERED
    )
    assert (
        authority.operation_state(recovery_binding.operation_id)
        is OperationState.RECOVERED
    )
    assert all(
        not hasattr(value, "__dict__")
        for value in (failure, recovery_capability, pending, recovered)
    )


def test_validation_only_recovery_installs_occurrence_for_already_active_state():
    active_state = typed_operation_binding().intended_state
    declared_target = replace(
        active_state,
        record_digest="sha256:" + "7" * 64,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_target=declared_target,
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    pending = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=active_state,
    )

    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION
    assert recovery.expected_state == active_state
    assert recovery.intended_state == declared_target
    assert (
        recovery.expected_state.record_digest != recovery.intended_state.record_digest
    )
    assert authority.observe_active(failed.target) == declared_target
    with pytest.raises(AuthorityUnavailable) as consumed:
        authority.execute_recovery(
            failed,
            recovery,
            failure=failure,
            capability=capability,
            observed_state=active_state,
        )
    assert consumed.value.code == "AUTHORITY_CAPABILITY_CONSUMED"
    recovered = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "6" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=declared_target,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    assert recovered.state is OperationState.RECOVERED
    assert authority.operation_state(failed.operation_id) is OperationState.RECOVERED
    assert authority.operation_state(recovery.operation_id) is OperationState.RECOVERED


def test_validation_only_service_recovery_retains_process_epoch_at_runtime():
    base = typed_operation_binding()
    active_state = replace(
        base.intended_state,
        process_epoch="service-process-001",
    )
    validation_occurrence = replace(
        active_state,
        record_digest="sha256:" + "7" * 64,
    )
    source = replace(
        base,
        intended_state=active_state,
        rollback=replace(
            base.rollback,
            recovery_target=validation_occurrence,
            recovery_destination_generation_digest=(
                validation_occurrence.generation_digest
            ),
        ),
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        source=source,
        recovery_target=validation_occurrence,
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    pending = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=active_state,
    )
    recovered = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "6" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=validation_occurrence,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION
    assert recovered.state is OperationState.RECOVERED
    assert recovery.expected_state.process_epoch == "service-process-001"
    assert recovery.intended_state.process_epoch == "service-process-001"
    assert capability.fenced.intended_state.process_epoch == "service-process-001"
    assert authority.observe_active(failed.target) == validation_occurrence


@pytest.mark.parametrize(
    ("expected_process_epoch", "intended_process_epoch"),
    [
        ("service-process-001", "service-process-002"),
        ("service-process-001", None),
        (None, "service-process-001"),
    ],
    ids=("changed", "removed", "added"),
)
def test_validation_only_recovery_rejects_a_process_epoch_mismatch(
    expected_process_epoch,
    intended_process_epoch,
):
    _, _, recovery, _ = _registered_recovery_successor()
    expected = replace(
        recovery.expected_state,
        record_digest="sha256:" + "6" * 64,
        process_epoch=expected_process_epoch,
    )
    intended = replace(
        expected,
        record_digest="sha256:" + "7" * 64,
        process_epoch=intended_process_epoch,
    )

    with pytest.raises(ValueError, match="prestate and intended state must differ"):
        replace(
            recovery,
            expected_state=expected,
            intended_state=intended,
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=intended.generation_digest,
            ),
            rollback=replace(
                recovery.rollback,
                rollback_target=_rollback_target(expected),
                recovery_origin_generation_digest=intended.generation_digest,
            ),
        )


def test_validation_only_recovery_terminal_failure_keeps_the_incident_guarded():
    active_state = typed_operation_binding().intended_state
    declared_target = replace(
        active_state,
        record_digest="sha256:" + "7" * 64,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_target=declared_target,
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=active_state,
    )

    terminal = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "6" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=declared_target,
            outcome=TerminalOutcome.FAIL,
            observed_effect_ids={"package-database"},
        ),
    )

    assert terminal.state is OperationState.RECOVERY_REQUIRED
    assert terminal.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"
    assert (
        authority.operation_state(failed.operation_id)
        is OperationState.RECOVERY_REQUIRED
    )
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_REQUIRED
    )
    assert authority.observe_active(failed.target) == declared_target
    ordinary = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "7" * 64,
        expected_state=declared_target,
        intended_state=replace(
            declared_target,
            record_digest="sha256:" + "8" * 64,
            state_digest="sha256:" + "a" * 64,
        ),
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(declared_target),
        ),
    )
    authority.append_intent(ordinary)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(ordinary, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"


def test_validation_only_recovery_must_equal_the_predecessor_declared_target():
    authority, failed, recovery, failure = _registered_recovery_successor()
    active = failed.intended_state
    undeclared_occurrence = replace(
        active,
        record_digest="sha256:" + "6" * 64,
    )
    wrong_noop = replace(
        recovery,
        operation_id="op-recovery-wrong",
        intent_digest="sha256:" + "6" * 64,
        expected_state=active,
        intended_state=undeclared_occurrence,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=active.generation_digest,
        ),
        rollback=replace(
            recovery.rollback,
            rollback_target=_rollback_target(active),
            recovery_origin_generation_digest=active.generation_digest,
        ),
    )
    authority.append_intent(wrong_noop)

    with pytest.raises(AuthorityUnavailable) as mismatch:
        authority.acquire_recovery_capability(
            failed,
            wrong_noop,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert mismatch.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert (
        authority.operation_state(wrong_noop.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert authority.observe_active(failed.target) == active
    valid = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    assert valid.fenced.intended_state == failed.rollback.recovery_target


def test_validation_only_recovery_requires_a_distinct_state_record_occurrence():
    _, _, recovery, _ = _registered_recovery_successor()
    validation_occurrence = replace(
        recovery.expected_state,
        record_digest="sha256:" + "6" * 64,
    )

    binding = replace(
        recovery,
        intended_state=validation_occurrence,
        generation=GenerationBinding(
            mode=GenerationBindingMode.REQUIRED_GENERATION,
            generation_digest=validation_occurrence.generation_digest,
        ),
        rollback=replace(
            recovery.rollback,
            rollback_target=_rollback_target(recovery.expected_state),
            recovery_origin_generation_digest=validation_occurrence.generation_digest,
        ),
    )

    assert binding.expected_state.record_digest != binding.intended_state.record_digest
    assert binding.expected_state.state_digest == binding.intended_state.state_digest


def test_validation_only_recovery_rejects_a_reused_state_record_occurrence():
    _, _, recovery, _ = _registered_recovery_successor()
    expected = recovery.expected_state

    with pytest.raises(ValueError, match="prestate and intended state must differ"):
        replace(
            recovery,
            intended_state=expected,
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=expected.generation_digest,
            ),
            rollback=replace(
                recovery.rollback,
                rollback_target=_rollback_target(expected),
                recovery_origin_generation_digest=expected.generation_digest,
            ),
        )


@pytest.mark.parametrize(
    ("coordinate", "error"),
    [
        ("generation", "prestate and intended state must differ"),
        ("lifecycle", "prestate and intended state must differ"),
        ("projection", "one projection"),
    ],
)
def test_validation_only_recovery_rejects_mismatched_state_coordinates(
    coordinate,
    error,
):
    _, _, recovery, _ = _registered_recovery_successor()
    expected = recovery.expected_state
    intended = replace(expected, record_digest="sha256:" + "6" * 64)
    if coordinate == "generation":
        intended = replace(intended, generation_digest="sha256:" + "5" * 64)
    elif coordinate == "lifecycle":
        expected = replace(
            expected,
            record_digest="sha256:" + "7" * 64,
            lifecycle_phase=LifecyclePhase.PREVALIDATED,
        )
    else:
        intended = replace(intended, projection_digest="sha256:" + "5" * 64)

    with pytest.raises(ValueError, match=error):
        replace(
            recovery,
            expected_state=expected,
            intended_state=intended,
            generation=GenerationBinding(
                mode=GenerationBindingMode.REQUIRED_GENERATION,
                generation_digest=intended.generation_digest,
            ),
            rollback=replace(
                recovery.rollback,
                rollback_target=_rollback_target(expected),
                recovery_origin_generation_digest=intended.generation_digest,
            ),
        )


def test_recovery_terminal_rejects_replay_from_a_distinct_capability():
    first_authority, first_failed, first_recovery, first_failure = (
        _registered_recovery_successor()
    )
    second_source = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "1" * 64,
        plan_digest="sha256:" + "2" * 64,
        target=OperationTarget(
            kind=OperationTargetKind.LIVE_ROOT,
            target_id="test-root-2",
        ),
    )
    second_authority, second_failed, second_recovery, second_failure = (
        _registered_recovery_successor(source=second_source)
    )
    first_capability = first_authority.acquire_recovery_capability(
        first_failed,
        first_recovery,
        failure=first_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    second_capability = second_authority.acquire_recovery_capability(
        second_failed,
        second_recovery,
        failure=second_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    first_authority.execute_recovery(
        first_failed,
        first_recovery,
        failure=first_failure,
        capability=first_capability,
        observed_state=first_failed.intended_state,
    )
    second_authority.execute_recovery(
        second_failed,
        second_recovery,
        failure=second_failure,
        capability=second_capability,
        observed_state=second_failed.intended_state,
    )
    observation = _terminal_observation(
        first_recovery,
        first_capability,
        record_digest="sha256:" + "3" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=first_recovery.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    assert (
        first_authority.terminalize_recovery(
            first_failed,
            first_recovery,
            observation,
        ).state
        is OperationState.RECOVERED
    )
    with pytest.raises(AuthorityUnavailable) as caught:
        second_authority.terminalize_recovery(
            second_failed,
            second_recovery,
            observation,
        )
    assert caught.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert (
        second_authority.terminalize_recovery(
            second_failed,
            second_recovery,
            _terminal_observation(
                second_recovery,
                second_capability,
                record_digest="sha256:" + "4" * 64,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=second_recovery.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.RECOVERED
    )


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


def test_recovery_capability_requires_the_exact_failed_poststate_as_its_source():
    failed_poststate = typed_operation_binding().intended_state
    wrong_source = replace(
        failed_poststate,
        record_digest="sha256:" + "4" * 64,
        state_digest="sha256:" + "5" * 64,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_expected_state=wrong_source,
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )


def test_missing_observation_during_recovery_does_not_consume_the_capability():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    authority, failed, recovery, failure = _registered_recovery_successor(
        authority_type=ToggleObservationAuthority
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    fresh_caller_state = replace(
        failed.intended_state,
        record_digest="sha256:" + "4" * 64,
    )
    unrelated_target = replace(failed.target, target_id="unrelated-host")
    journal_before_rejection = authority.journal_entries
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.execute_recovery(
            failed,
            recovery,
            failure=failure,
            capability=capability,
            observed_state=fresh_caller_state,
        )

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_CAPABILITY_ISSUED
    )
    assert authority.journal_entries == journal_before_rejection

    authority.configure_active(unrelated_target, fresh_caller_state)

    authority.observation_available = True
    assert authority.observe_active(unrelated_target) == fresh_caller_state
    pending = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
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


def test_recovery_capability_is_bound_to_its_issuing_authority_instance():
    first, failed, recovery, first_failure = _registered_recovery_successor()
    second, _, _, second_failure = _registered_recovery_successor()
    first_capability = first.acquire_recovery_capability(
        failed,
        recovery,
        failure=first_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    second_capability = second.acquire_recovery_capability(
        failed,
        recovery,
        failure=second_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert first_capability.capability_id != second_capability.capability_id
    with pytest.raises(AuthorityUnavailable) as caught:
        second.execute_recovery(
            failed,
            recovery,
            failure=second_failure,
            capability=first_capability,
            observed_state=failed.intended_state,
        )

    assert caught.value.code == "AUTHORITY_CAPABILITY_UNKNOWN"
    assert (
        second.execute_recovery(
            failed,
            recovery,
            failure=second_failure,
            capability=second_capability,
            observed_state=failed.intended_state,
        ).state
        is OperationState.RECOVERY_PENDING_VALIDATION
    )


def test_recovery_capability_redelivery_retains_the_exact_incident_and_receipt():
    authority, failed, recovery, failure = _registered_recovery_successor()
    issued = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    journal_before_redelivery = authority.journal_entries
    evidence_before_redelivery = authority.evidence_view()

    redelivered = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert redelivered == issued
    assert redelivered is not issued
    assert redelivered.fenced is not issued.fenced
    assert redelivered.fenced.intended_state is not issued.fenced.intended_state
    assert redelivered.fenced.fence_epoch == issued.fenced.fence_epoch == 2
    assert redelivered.fenced.intended_state == recovery.intended_state
    assert redelivered.predecessor_operation_id == failed.operation_id
    assert redelivered.predecessor_fence_epoch == 1
    assert authority.journal_entries == journal_before_redelivery
    assert authority.evidence_view() == evidence_before_redelivery
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_CAPABILITY_ISSUED
    )
    assert authority.observe_active(failed.target) == failed.intended_state
    assert (
        authority.execute_recovery(
            failed,
            recovery,
            failure=failure,
            capability=redelivered,
            observed_state=failed.intended_state,
        ).state
        is OperationState.RECOVERY_PENDING_VALIDATION
    )


def test_recovery_redelivery_cannot_rebind_a_validation_only_successor_to_root():
    source = typed_operation_binding()
    active = source.intended_state
    first_occurrence = replace(active, record_digest="sha256:" + "5" * 64)
    second_occurrence = replace(active, record_digest="sha256:" + "a" * 64)
    root_contract = replace(
        source.rollback,
        mode=RecoveryMode.RECOVERY_ONLY,
        recovery_target=first_occurrence,
        recovery_destination_generation_digest=active.generation_digest,
        rollback_target=None,
        rollback_plan_digest=None,
        rollback_validator_digest=None,
    )
    first_contract = replace(root_contract, recovery_target=second_occurrence)
    authority, root, first, root_failure = _registered_recovery_successor(
        source=replace(source, rollback=root_contract),
        recovery_target=first_occurrence,
        recovery_successor_rollback=first_contract,
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=active,
    )
    first_failure = authority.terminalize_recovery(
        root,
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest="sha256:" + "6" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first_occurrence,
            outcome=TerminalOutcome.FAIL,
            observed_effect_ids={"package-database"},
        ),
    )
    second = replace(
        first,
        operation_id="op-recovery-002",
        intent_digest="sha256:" + "7" * 64,
        expected_state=first_occurrence,
        intended_state=second_occurrence,
    )
    authority.append_intent(second)
    issued = authority.acquire_recovery_capability(
        first,
        second,
        failure=first_failure,
        owner_role="recovery-owner",
        fence_epoch=3,
    )
    journal_before_rebind = authority.journal_entries

    with pytest.raises(AuthorityUnavailable) as mismatch:
        authority.acquire_recovery_capability(
            root,
            second,
            failure=root_failure,
            owner_role="recovery-owner",
            fence_epoch=4,
        )

    assert mismatch.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert authority.journal_entries == journal_before_rebind
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [
        OperationState.RECOVERY_REQUIRED,
        OperationState.RECOVERY_REQUIRED,
        OperationState.RECOVERY_CAPABILITY_ISSUED,
    ]
    assert authority.observe_active(root.target) == first_occurrence

    redelivered = authority.acquire_recovery_capability(
        first,
        second,
        failure=first_failure,
        owner_role="recovery-owner",
        fence_epoch=3,
    )
    assert redelivered == issued
    assert authority.journal_entries == journal_before_rebind
    pending = authority.execute_recovery(
        first,
        second,
        failure=first_failure,
        capability=redelivered,
        observed_state=first_occurrence,
    )
    assert pending.state is OperationState.RECOVERY_PENDING_VALIDATION
    recovered = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            redelivered,
            record_digest="sha256:" + "8" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second_occurrence,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    assert recovered.state is OperationState.RECOVERED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [OperationState.RECOVERED] * 3

    ordinary = replace(
        source,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "9" * 64,
        expected_state=second_occurrence,
        intended_state=replace(
            second_occurrence,
            record_digest="sha256:" + "c" * 64,
            state_digest="sha256:" + "b" * 64,
        ),
        rollback=replace(
            source.rollback,
            rollback_target=_rollback_target(second_occurrence),
        ),
    )
    authority.append_intent(ordinary)
    assert authority.acquire_capability(ordinary, fence_epoch=5).fence_epoch == 5


@pytest.mark.parametrize("requested_fence", [1, 3], ids=("older", "newer"))
def test_recovery_redelivery_rejects_a_different_fence_without_rotation(
    requested_fence,
):
    authority, failed, recovery, failure = _registered_recovery_successor()
    issued = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    journal_before_retry = authority.journal_entries

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=requested_fence,
        )

    assert caught.value.code == "AUTHORITY_FENCE_STALE"
    assert authority.journal_entries == journal_before_retry
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_CAPABILITY_ISSUED
    )
    assert authority.observe_active(failed.target) == failed.intended_state
    assert (
        authority.execute_recovery(
            failed,
            recovery,
            failure=failure,
            capability=issued,
            observed_state=failed.intended_state,
        ).state
        is OperationState.RECOVERY_PENDING_VALIDATION
    )


def test_recovery_capability_rejects_a_foreign_authority_failure_result():
    authority, failed, recovery, failure = _registered_recovery_successor()
    foreign, _, _, foreign_failure = _registered_recovery_successor()

    assert failure != foreign_failure
    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=foreign_failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_FAILURE_MISMATCH"
    assert (
        authority.acquire_recovery_capability(
            failed,
            recovery,
            failure=failure,
            owner_role="recovery-owner",
            fence_epoch=2,
        ).predecessor_failure_record_digest
        == failure.failure_record_digest
    )
    assert (
        foreign.operation_state(failed.operation_id) is OperationState.RECOVERY_REQUIRED
    )


def test_recovery_terminal_rejects_an_observation_from_another_authority_instance():
    first, failed, recovery, first_failure = _registered_recovery_successor()
    second, _, _, second_failure = _registered_recovery_successor()
    first_capability = first.acquire_recovery_capability(
        failed,
        recovery,
        failure=first_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    second_capability = second.acquire_recovery_capability(
        failed,
        recovery,
        failure=second_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    first.execute_recovery(
        failed,
        recovery,
        failure=first_failure,
        capability=first_capability,
        observed_state=failed.intended_state,
    )
    second.execute_recovery(
        failed,
        recovery,
        failure=second_failure,
        capability=second_capability,
        observed_state=failed.intended_state,
    )
    foreign = _terminal_observation(
        recovery,
        first_capability,
        record_digest="sha256:" + "6" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=recovery.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        second.terminalize_recovery(failed, recovery, foreign)

    assert caught.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert (
        second.terminalize_recovery(
            failed,
            recovery,
            _terminal_observation(
                recovery,
                second_capability,
                record_digest="sha256:" + "7" * 64,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=recovery.intended_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        ).state
        is OperationState.RECOVERED
    )


def test_recovery_terminal_observation_loss_does_not_claim_the_terminal_record():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    authority, failed, recovery, failure = _registered_recovery_successor(
        authority_type=ToggleObservationAuthority
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )
    observation = _terminal_observation(
        recovery,
        capability,
        record_digest="sha256:" + "f" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=recovery.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_recovery(failed, recovery, observation)

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "3" * 64,
        expected_state=recovery.intended_state,
        intended_state=replace(
            recovery.intended_state,
            record_digest="sha256:" + "4" * 64,
            generation_digest=GENERATION,
            state_digest="sha256:" + "5" * 64,
        ),
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"

    authority.observation_available = True
    terminal = authority.terminalize_recovery(failed, recovery, observation)

    assert terminal.state is OperationState.RECOVERED
    assert authority.acquire_capability(successor, fence_epoch=3).fence_epoch == 3


def test_recovery_terminal_rejects_an_undeclared_interval_violation_effect():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
            interval_violation_effect_ids={"undeclared-effect"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


@pytest.mark.parametrize(
    "effect_claim",
    [
        {"observed_effect_ids": {"package-database", "undeclared-effect"}},
        {
            "observed_effect_ids": {"package-database"},
            "interval_enforced_effect_ids": {"undeclared-effect"},
        },
    ],
)
def test_recovery_terminal_rejects_undeclared_effect_claims(effect_claim):
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            **effect_claim,
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


def test_recovery_terminal_rejects_a_declared_forbidden_interval_violation():
    forbidden_effect = DeclaredEffect(
        effect_id="mixed-endpoint",
        classification=EffectClass.FORBIDDEN_TRANSIENT,
        projection_digest=EFFECT_PROJECTION,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_effects=(forbidden_effect,)
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
            interval_violation_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


def test_recovery_terminal_rejects_an_observed_declared_forbidden_effect():
    forbidden_effect = DeclaredEffect(
        effect_id="mixed-endpoint",
        classification=EffectClass.FORBIDDEN_TRANSIENT,
        projection_digest=EFFECT_PROJECTION,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_effects=(forbidden_effect,)
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )
    observation = _terminal_observation(
        recovery,
        capability,
        record_digest="sha256:" + "f" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=recovery.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"mixed-endpoint"},
        interval_enforced_effect_ids={"mixed-endpoint"},
    )

    result = authority.terminalize_recovery(failed, recovery, observation)

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"
    assert result.failure_record_digest == observation.record_digest
    assert authority.operation_state(failed.operation_id) is result.state
    assert authority.operation_state(recovery.operation_id) is result.state
    assert authority.journal_entries[-1].kind == "recovery_still_required"
    assert authority.journal_entries[-1].record_digest == observation.record_digest
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "3" * 64,
        expected_state=recovery.intended_state,
        intended_state=replace(
            recovery.intended_state,
            record_digest="sha256:" + "4" * 64,
            generation_digest=GENERATION,
            state_digest="sha256:" + "5" * 64,
        ),
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=3)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"


def test_recovery_terminal_allows_an_enforced_unobserved_forbidden_effect():
    forbidden_effect = DeclaredEffect(
        effect_id="mixed-endpoint",
        classification=EffectClass.FORBIDDEN_TRANSIENT,
        projection_digest=EFFECT_PROJECTION,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_effects=(forbidden_effect,)
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.RECOVERED
    assert result.failure_code is None
    assert authority.operation_state(failed.operation_id) is OperationState.RECOVERED
    assert authority.journal_entries[-1].kind == "recovery_succeeded"


def test_recovery_terminal_requires_declared_forbidden_interval_enforcement():
    forbidden_effect = DeclaredEffect(
        effect_id="mixed-endpoint",
        classification=EffectClass.FORBIDDEN_TRANSIENT,
        projection_digest=EFFECT_PROJECTION,
    )
    authority, failed, recovery, failure = _registered_recovery_successor(
        recovery_effects=(forbidden_effect,)
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


def test_recovery_execution_normalizes_a_deceptive_adapter_observation():
    authority, failed, recovery, failure = _registered_recovery_successor(
        authority_type=_SwitchableObservationAuthority
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.observation_override = _deceptive_snapshot(failed.intended_state)

    result = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_PRESTATE_MISMATCH"


def test_recovery_prestate_drift_chains_from_retained_state_and_closes_incident():
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    drifted = replace(
        first.expected_state,
        record_digest="sha256:" + "8" * 64,
        state_digest="sha256:" + "9" * 64,
    )
    authority.configure_active(first.target, drifted)

    first_failure = authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=drifted,
    )

    with pytest.raises(AuthorityUnavailable) as wrong_source:
        _next_recovery_successor(
            authority,
            first,
            first_failure,
            ordinal=2,
        )
    assert wrong_source.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"

    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=3,
        expected_state=drifted,
    )
    recovered = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "a" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert first_failure.state is OperationState.RECOVERY_REQUIRED
    assert recovered.state is OperationState.RECOVERED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [OperationState.RECOVERED] * 3
    assert authority.observe_active(first.target) == second.intended_state
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "b" * 64,
        plan_digest="sha256:" + "c" * 64,
        expected_state=second.intended_state,
    )
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=5).fence_epoch == 5


def test_recovery_prestate_drift_can_close_after_target_state_is_already_realized():
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    declared_target = first.rollback.recovery_target
    assert declared_target is not None
    already_realized = replace(
        declared_target,
        record_digest="sha256:" + "6" * 64,
    )
    authority.configure_active(first.target, already_realized)
    first_failure = authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=already_realized,
    )

    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=2,
        expected_state=already_realized,
    )

    assert second.expected_state == already_realized
    assert second.intended_state == declared_target
    assert second.expected_state.record_digest != second.intended_state.record_digest
    assert authority.observe_active(first.target) == declared_target
    recovered = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "8" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=declared_target,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert first_failure.state is OperationState.RECOVERY_REQUIRED
    assert recovered.state is OperationState.RECOVERED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [OperationState.RECOVERED] * 3
    assert authority.observe_active(first.target) == declared_target
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "9" * 64,
        expected_state=declared_target,
        rollback=replace(
            typed_operation_binding().rollback,
            rollback_target=_rollback_target(declared_target),
        ),
    )
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=4).fence_epoch == 4


def test_recovery_terminal_normalizes_a_deceptive_adapter_observation():
    authority, failed, recovery, failure = _registered_recovery_successor(
        authority_type=_SwitchableObservationAuthority
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )
    authority.observation_override = _deceptive_snapshot(recovery.intended_state)

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "f" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


def test_recovery_terminal_rejects_state_record_rebinding_before_claiming():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )
    terminal_record = "sha256:" + "6" * 64
    rebound = replace(
        recovery.intended_state,
        state_digest="sha256:" + "5" * 64,
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_recovery(
            failed,
            recovery,
            _terminal_observation(
                recovery,
                capability,
                record_digest=terminal_record,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=rebound,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        )

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest=terminal_record,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.RECOVERED


def test_two_hop_recovery_success_closes_the_complete_incident_before_guard_release():
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=root.intended_state,
    )
    first_failure = authority.terminalize_recovery(
        root,
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=2,
    )

    recovered = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert recovered.state is OperationState.RECOVERED
    assert authority.operation_state(root.operation_id) is OperationState.RECOVERED
    assert authority.operation_state(first.operation_id) is OperationState.RECOVERED
    assert authority.operation_state(second.operation_id) is OperationState.RECOVERED
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "3" * 64,
        expected_state=second.intended_state,
    )
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=4).fence_epoch == 4


def test_three_hop_recovery_success_closes_every_ancestor_and_releases_the_guard():
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=root.intended_state,
    )
    first_failure = authority.terminalize_recovery(
        root,
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=2,
    )
    second_failure = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    third, third_capability = _next_recovery_successor(
        authority,
        second,
        second_failure,
        ordinal=3,
    )

    recovered = authority.terminalize_recovery(
        second,
        third,
        _terminal_observation(
            third,
            third_capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=third.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert recovered.state is OperationState.RECOVERED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second, third)
    ] == [OperationState.RECOVERED] * 4
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "4" * 64,
        expected_state=third.intended_state,
    )
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=5).fence_epoch == 5


def test_failed_intermediate_recovery_keeps_every_ancestor_open_and_target_guarded():
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=root.intended_state,
    )
    first_failure = authority.terminalize_recovery(
        root,
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=2,
    )

    second_failure = authority.terminalize_recovery(
        first,
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "2" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )

    assert second_failure.state is OperationState.RECOVERY_REQUIRED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [OperationState.RECOVERY_REQUIRED] * 3
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "3" * 64,
        expected_state=second.intended_state,
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(successor, fence_epoch=4)
    assert caught.value.code == "AUTHORITY_TARGET_GUARDED"


@pytest.mark.parametrize("corruption", ["cycle", "missing-ancestor"])
def test_corrupt_recovery_ancestry_fails_closed_before_state_or_guard_release(
    corruption,
):
    authority, root, first, root_failure = _registered_recovery_successor(
        next_recovery_ordinal=2
    )
    first_capability = authority.acquire_recovery_capability(
        root,
        first,
        failure=root_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        root,
        first,
        failure=root_failure,
        capability=first_capability,
        observed_state=root.intended_state,
    )
    first_failure = authority.terminalize_recovery(
        root,
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.FAIL,
        ),
    )
    second, second_capability = _next_recovery_successor(
        authority,
        first,
        first_failure,
        ordinal=2,
    )
    predecessor_id = (
        first.operation_id if corruption == "cycle" else "missing-operation"
    )
    original_link = authority._recovery_predecessors[first.operation_id]
    authority._recovery_predecessors[first.operation_id] = replace(
        original_link,
        predecessor_operation_id=predecessor_id,
    )
    observation = _terminal_observation(
        second,
        second_capability,
        record_digest="sha256:" + "2" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=second.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_recovery(first, second, observation)

    assert caught.value.code == "AUTHORITY_RECOVERY_BINDING_MISMATCH"
    assert (
        authority.operation_state(root.operation_id) is OperationState.RECOVERY_REQUIRED
    )
    assert (
        authority.operation_state(first.operation_id)
        is OperationState.RECOVERY_REQUIRED
    )
    assert (
        authority.operation_state(second.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "3" * 64,
        expected_state=second.intended_state,
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=4)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"

    authority._recovery_predecessors[first.operation_id] = original_link
    recovered = authority.terminalize_recovery(first, second, observation)

    assert recovered.state is OperationState.RECOVERED
    assert [
        authority.operation_state(binding.operation_id)
        for binding in (root, first, second)
    ] == [OperationState.RECOVERED] * 3


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


def test_recovery_capability_constructor_rejects_its_successor_as_predecessor():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    with pytest.raises(
        ValueError,
        match="predecessor operation must differ from successor operation",
    ):
        RecoveryCapability(
            fenced=capability.fenced,
            predecessor_operation_id=capability.fenced.operation_id,
            predecessor_failure_record_digest=(
                capability.predecessor_failure_record_digest
            ),
            predecessor_fence_epoch=capability.predecessor_fence_epoch,
            recovery_contract_digest=capability.recovery_contract_digest,
            recovery_owner_role=capability.recovery_owner_role,
        )


def test_recovery_capability_constructor_rejects_a_nonadvancing_fence():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    with pytest.raises(
        ValueError,
        match="predecessor fence must precede successor fence",
    ):
        RecoveryCapability(
            fenced=capability.fenced,
            predecessor_operation_id=capability.predecessor_operation_id,
            predecessor_failure_record_digest=(
                capability.predecessor_failure_record_digest
            ),
            predecessor_fence_epoch=capability.fenced.fence_epoch,
            recovery_contract_digest=capability.recovery_contract_digest,
            recovery_owner_role=capability.recovery_owner_role,
        )


def test_recovery_capability_constructor_rejects_a_noncanonical_contract():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    with pytest.raises(
        ValueError,
        match="recovery contract must equal fenced subject",
    ):
        RecoveryCapability(
            fenced=capability.fenced,
            predecessor_operation_id=capability.predecessor_operation_id,
            predecessor_failure_record_digest=(
                capability.predecessor_failure_record_digest
            ),
            predecessor_fence_epoch=capability.predecessor_fence_epoch,
            recovery_contract_digest="sha256:" + "5" * 64,
            recovery_owner_role=capability.recovery_owner_role,
        )


@pytest.mark.parametrize(
    ("contradiction", "message"),
    [
        (
            "operation",
            "predecessor operation must differ from successor operation",
        ),
        ("equal-fence", "predecessor fence must precede successor fence"),
        ("later-fence", "predecessor fence must precede successor fence"),
        ("contract", "recovery contract must equal fenced subject"),
    ],
)
def test_recovery_capability_replace_rejects_canonical_identity_contradictions(
    contradiction,
    message,
):
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    changes = {
        "operation": {
            "predecessor_operation_id": capability.fenced.operation_id,
        },
        "equal-fence": {
            "predecessor_fence_epoch": capability.fenced.fence_epoch,
        },
        "later-fence": {
            "predecessor_fence_epoch": capability.fenced.fence_epoch + 1,
        },
        "contract": {
            "recovery_contract_digest": "sha256:" + "5" * 64,
        },
    }

    with pytest.raises(ValueError, match=message):
        replace(capability, **changes[contradiction])


def test_recovery_capability_round_trip_preserves_canonical_issued_record():
    authority, failed, recovery, failure = _registered_recovery_successor()
    issued = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    reconstructed = RecoveryCapability(
        fenced=replace(issued.fenced),
        predecessor_operation_id=_LyingString(issued.predecessor_operation_id),
        predecessor_failure_record_digest=_LyingString(
            issued.predecessor_failure_record_digest
        ),
        predecessor_fence_epoch=issued.predecessor_fence_epoch,
        recovery_contract_digest=_LyingString(issued.recovery_contract_digest),
        recovery_owner_role=_LyingString(issued.recovery_owner_role),
    )

    assert reconstructed == issued
    assert replace(reconstructed) == issued
    assert type(reconstructed.predecessor_operation_id) is str
    assert type(reconstructed.predecessor_failure_record_digest) is str
    assert type(reconstructed.predecessor_fence_epoch) is int
    assert type(reconstructed.recovery_contract_digest) is str
    assert type(reconstructed.recovery_owner_role) is str
    assert not hasattr(reconstructed, "__dict__")
    with pytest.raises(AttributeError):
        reconstructed.recovery_owner_role = "substituted-owner"


def test_recovery_binding_cannot_acquire_an_ordinary_forward_capability():
    _, _, recovery, _ = _registered_recovery_successor()
    authority = InMemoryAuthority(initial_active_state=recovery.expected_state)
    authority.append_intent(recovery)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(recovery, fence_epoch=1)

    assert caught.value.code == "AUTHORITY_RECOVERY_PHASE_INVALID"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert authority.observe_active() == recovery.expected_state


def test_guarded_forward_transition_defensively_rejects_a_recovery_binding():
    _, _, recovery, _ = _registered_recovery_successor()
    ordinary = typed_operation_binding()
    foreign = InMemoryAuthority(initial_active_state=ordinary.expected_state)
    foreign.append_intent(ordinary)
    foreign_capability = foreign.acquire_capability(ordinary, fence_epoch=1)
    authority = InMemoryAuthority(initial_active_state=recovery.expected_state)
    authority.append_intent(recovery)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            recovery,
            capability=foreign_capability,
            observed_state=recovery.expected_state,
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_PHASE_INVALID"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert authority.observe_active() == recovery.expected_state


def test_forward_terminal_defensively_rejects_a_recovery_binding():
    _, _, recovery, _ = _registered_recovery_successor()
    ordinary = typed_operation_binding()
    foreign = InMemoryAuthority(initial_active_state=ordinary.expected_state)
    foreign.append_intent(ordinary)
    foreign_capability = foreign.acquire_capability(ordinary, fence_epoch=1)
    authority = InMemoryAuthority(initial_active_state=recovery.expected_state)
    authority.append_intent(recovery)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_operation(
            recovery,
            _terminal_observation(
                recovery,
                foreign_capability,
                record_digest="sha256:" + "1" * 64,
                validator_digest=recovery.terminal_validator_digest,
                observed_state=recovery.expected_state,
                outcome=TerminalOutcome.PASS,
            ),
        )

    assert caught.value.code == "AUTHORITY_RECOVERY_PHASE_INVALID"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.INTENT_REGISTERED
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


def test_recovery_successor_moves_from_failed_phase_to_declared_recovery_phase():
    base = typed_operation_binding()
    recovery_target = replace(
        base.rollback.recovery_target,
        record_digest="sha256:" + "5" * 64,
        lifecycle_phase=LifecyclePhase.PREVALIDATED,
    )
    source = replace(
        base,
        operation_kind=CriticalOperationKind.BLOCKING_SCENARIO,
        subject=OperationSubject(
            kind=OperationSubjectKind.GATE_OCCURRENCE,
            record_digest=SUBJECT,
        ),
        target=OperationTarget(
            kind=OperationTargetKind.SERVICE,
            target_id="inference-service",
        ),
        rollback=replace(
            base.rollback,
            recovery_target=recovery_target,
        ),
    )
    authority, failed_binding, recovery_binding, failure = (
        _registered_recovery_successor(
            source=source,
            recovery_target=recovery_target,
        )
    )

    capability = authority.acquire_recovery_capability(
        failed_binding,
        recovery_binding,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert recovery_binding.expected_state.lifecycle_phase is LifecyclePhase.ACTIVE
    assert (
        recovery_binding.intended_state.lifecycle_phase is LifecyclePhase.PREVALIDATED
    )
    assert capability.fenced.intended_state == recovery_target


def test_recovery_successor_cannot_reclassify_the_failed_generation_class():
    base = typed_operation_binding()
    source = _binding_with_lifecycle_phase(
        base,
        LifecyclePhase.PUBLISHED,
        operation_kind=CriticalOperationKind.REPOSITORY_PUBLICATION,
        generation_class=GenerationClass.F,
        target=OperationTarget(
            kind=OperationTargetKind.PACKAGE_REPOSITORY,
            target_id="foundation-repository",
        ),
        rollback=replace(
            base.rollback,
            recovery_target=replace(
                base.rollback.recovery_target,
                record_digest="sha256:" + "4" * 64,
                lifecycle_phase=LifecyclePhase.PUBLISHED,
            ),
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
            _terminal_observation(
                recovery_binding,
                recovery_capability,
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
        _terminal_observation(
            recovery_binding,
            recovery_capability,
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
            _terminal_observation(
                recovery_binding,
                recovery_capability,
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
        _terminal_observation(
            failed_binding,
            capability,
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_EFFECT_ENFORCEMENT_MISSING"


def test_forward_terminal_rejects_an_observed_declared_forbidden_effect():
    binding = replace(
        typed_operation_binding(),
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
    observation = _terminal_observation(
        binding,
        capability,
        record_digest="sha256:" + "5" * 64,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=binding.intended_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"mixed-endpoint"},
        interval_enforced_effect_ids={"mixed-endpoint"},
    )

    result = authority.terminalize_operation(binding, observation)

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"
    assert result.failure_record_digest == observation.record_digest
    assert authority.operation_state(binding.operation_id) is result.state
    assert authority.journal_entries[-1].kind == "operation_terminal_failed"
    assert authority.journal_entries[-1].record_digest == observation.record_digest
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "6" * 64,
        expected_state=binding.intended_state,
        intended_state=replace(
            binding.intended_state,
            record_digest="sha256:" + "7" * 64,
            state_digest="sha256:" + "8" * 64,
        ),
    )
    authority.append_intent(successor)
    with pytest.raises(AuthorityUnavailable) as guarded:
        authority.acquire_capability(successor, fence_epoch=2)
    assert guarded.value.code == "AUTHORITY_TARGET_GUARDED"


def test_forward_terminal_allows_an_enforced_unobserved_forbidden_effect():
    binding = replace(
        typed_operation_binding(),
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.SUCCEEDED
    assert result.failure_code is None
    assert authority.journal_entries[-1].kind == "operation_succeeded"


def test_forward_terminal_rejects_an_undeclared_interval_violation_effect():
    binding = typed_operation_binding()
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
            interval_violation_effect_ids={"undeclared-effect"},
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"


@pytest.mark.parametrize(
    "effect_claim",
    [
        {"observed_effect_ids": {"package-database", "undeclared-effect"}},
        {
            "observed_effect_ids": {"package-database"},
            "interval_enforced_effect_ids": {"undeclared-effect"},
        },
    ],
)
def test_forward_terminal_rejects_undeclared_effect_claims(effect_claim):
    binding = typed_operation_binding()
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            **effect_claim,
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"


def test_forward_terminal_rejects_a_declared_forbidden_interval_violation():
    binding = replace(
        typed_operation_binding(),
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
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "5" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=binding.intended_state,
            outcome=TerminalOutcome.PASS,
            interval_enforced_effect_ids={"mixed-endpoint"},
            interval_violation_effect_ids={"mixed-endpoint"},
        ),
    )

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_FORBIDDEN_EFFECT_OBSERVED"


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


def test_active_observations_and_transitions_are_isolated_by_exact_target():
    first = typed_operation_binding()
    second_expected = replace(
        first.expected_state,
        record_digest="sha256:" + "4" * 64,
        state_digest="sha256:" + "5" * 64,
    )
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "d" * 64,
        plan_digest="sha256:" + "e" * 64,
        target=replace(first.target, target_id="other-host"),
        expected_state=second_expected,
        intended_state=replace(
            first.intended_state,
            record_digest="sha256:" + "c" * 64,
            state_digest="sha256:" + "b" * 64,
        ),
        rollback=replace(
            first.rollback,
            rollback_target=_rollback_target(second_expected),
            recovery_target=second_expected,
        ),
    )
    authority = InMemoryAuthority()
    authority.configure_active(first.target, first.expected_state)
    authority.configure_active(second.target, second.expected_state)
    authority.append_intent(first)
    authority.append_intent(second)
    first_capability = authority.acquire_capability(first, fence_epoch=1)
    second_capability = authority.acquire_capability(second, fence_epoch=1)

    authority.guarded_compare_and_swap(
        first,
        capability=first_capability,
        observed_state=first.expected_state,
    )
    authority.guarded_compare_and_swap(
        second,
        capability=second_capability,
        observed_state=second.expected_state,
    )

    assert authority.observe_active(first.target) == first.intended_state
    assert authority.observe_active(second.target) == second.intended_state


def test_initial_target_and_state_must_be_configured_as_one_exact_pair():
    binding = typed_operation_binding()

    with pytest.raises(ValueError, match="requires initial_active_state"):
        InMemoryAuthority(initial_target=binding.target)

    authority = InMemoryAuthority(
        initial_target=binding.target,
        initial_active_state=binding.expected_state,
    )

    assert authority.observe_active(binding.target) == binding.expected_state


def test_observe_active_requires_an_exact_target_when_multiple_are_configured():
    binding = typed_operation_binding()
    second_target = replace(binding.target, target_id="other-host")
    second_state = replace(
        binding.expected_state,
        record_digest="sha256:" + "4" * 64,
        state_digest="sha256:" + "5" * 64,
    )
    authority = InMemoryAuthority(
        initial_target=binding.target,
        initial_active_state=binding.expected_state,
    )
    authority.configure_active(second_target, second_state)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.observe_active()

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert authority.observe_active(binding.target) == binding.expected_state
    assert authority.observe_active(second_target) == second_state


def test_forward_acquisition_requires_observation_before_issuing_or_guarding():
    class LateObservationAuthority(InMemoryAuthority):
        configured_observation = None

        def observe_active(self, target=None):
            if self.configured_observation is None:
                return super().observe_active(target)
            return replace(self.configured_observation)

    binding = typed_operation_binding()
    authority = LateObservationAuthority()
    authority.append_intent(binding)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.acquire_capability(binding, fence_epoch=1)

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert [entry.kind for entry in authority.journal_entries] == ["operation_intent"]

    authority.configured_observation = binding.expected_state
    capability = authority.acquire_capability(binding, fence_epoch=1)

    assert capability.operation_id == binding.operation_id
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )


def test_forward_acquisition_normalizes_the_adapter_observation_before_issuance():
    binding = typed_operation_binding()
    malformed = _deceptive_snapshot(binding.expected_state)
    object.__setattr__(malformed, "record_digest", _LyingString("not-a-digest"))
    authority = _SwitchableObservationAuthority(
        initial_active_state=binding.expected_state
    )
    authority.observation_override = malformed
    authority.append_intent(binding)

    with pytest.raises(ValueError, match="canonical sha256 digest"):
        authority.acquire_capability(binding, fence_epoch=1)

    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.INTENT_REGISTERED
    )
    assert [entry.kind for entry in authority.journal_entries] == ["operation_intent"]

    authority.observation_override = binding.expected_state
    assert authority.acquire_capability(binding, fence_epoch=1).fence_epoch == 1


def test_missing_observation_during_forward_transition_does_not_wedge_capability():
    class ToggleObservationAuthority(InMemoryAuthority):
        observation_available = True

        def observe_active(self, target=None):
            if not self.observation_available:
                raise AuthorityUnavailable(
                    "AUTHORITY_OBSERVATION_MISSING",
                    "the active-state observation is temporarily unavailable",
                )
            return super().observe_active(target)

    binding = typed_operation_binding()
    authority = ToggleObservationAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    fresh_caller_state = replace(
        binding.expected_state,
        record_digest="sha256:" + "5" * 64,
    )
    unrelated_target = replace(binding.target, target_id="unrelated-host")
    journal_before_rejection = authority.journal_entries
    authority.observation_available = False

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=fresh_caller_state,
        )

    assert caught.value.code == "AUTHORITY_OBSERVATION_MISSING"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "fenced_capability",
    ]
    assert authority.journal_entries == journal_before_rejection

    authority.configure_active(unrelated_target, fresh_caller_state)

    authority.observation_available = True
    assert authority.observe_active(unrelated_target) == fresh_caller_state
    pending = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    assert pending.state is OperationState.MUTATED_PENDING_VALIDATION
    assert authority.observe_active(binding.target) == binding.intended_state


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


def test_guarded_transition_normalizes_a_lying_observed_state_subclass():
    binding = typed_operation_binding()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    forged = LyingSnapshot(
        record_digest="sha256:" + "e" * 64,
        generation_digest=binding.expected_state.generation_digest,
        lifecycle_phase=binding.expected_state.lifecycle_phase,
        projection_digest=binding.expected_state.projection_digest,
        state_digest="sha256:" + "f" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=forged,
        )

    assert caught.value.code == "AUTHORITY_PRESTATE_MISMATCH"
    assert authority.observe_active() == binding.expected_state


def test_forward_terminal_normalizes_a_lying_observation_and_nested_state():
    binding = typed_operation_binding()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    class LyingTerminalObservation(TerminalObservation):
        pass

    forged_state = LyingSnapshot(
        record_digest="sha256:" + "e" * 64,
        generation_digest=binding.intended_state.generation_digest,
        lifecycle_phase=binding.intended_state.lifecycle_phase,
        projection_digest=binding.intended_state.projection_digest,
        state_digest="sha256:" + "f" * 64,
    )
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )
    observation = LyingTerminalObservation(
        record_digest="sha256:" + "1" * 64,
        operation_digest=binding.digest(),
        capability_digest=capability.capability_id,
        validator_digest=TERMINAL_VALIDATOR,
        observed_state=forged_state,
        outcome=TerminalOutcome.PASS,
        observed_effect_ids={"package-database"},
    )

    result = authority.terminalize_operation(binding, observation)

    assert result.state is OperationState.ROLLBACK_REQUIRED
    assert result.failure_code == "AUTHORITY_TERMINAL_STATE_MISMATCH"


def test_rollback_execution_normalizes_a_lying_observed_state_subclass():
    authority, binding = _rollback_required_authority()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    forged = LyingSnapshot(
        record_digest="sha256:" + "e" * 64,
        generation_digest=binding.intended_state.generation_digest,
        lifecycle_phase=binding.intended_state.lifecycle_phase,
        projection_digest=binding.intended_state.projection_digest,
        state_digest="sha256:" + "f" * 64,
    )
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)

    result = authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=forged,
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_PRESTATE_MISMATCH"
    assert authority.observe_active() == binding.intended_state


def test_rollback_terminal_normalizes_a_lying_nested_state_subclass():
    authority, binding = _rollback_required_authority()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    authority.execute_rollback(
        binding,
        capability=capability,
        observed_state=binding.intended_state,
    )
    forged = LyingSnapshot(
        record_digest="sha256:" + "e" * 64,
        generation_digest=binding.expected_state.generation_digest,
        lifecycle_phase=binding.expected_state.lifecycle_phase,
        projection_digest=binding.expected_state.projection_digest,
        state_digest="sha256:" + "f" * 64,
    )

    result = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            capability,
            record_digest="sha256:" + "1" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=forged,
            outcome=TerminalOutcome.PASS,
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_ROLLBACK_VALIDATION_FAILED"


def test_recovery_execution_normalizes_a_lying_observed_state_subclass():
    authority, failed, recovery, failure = _registered_recovery_successor()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    forged = LyingSnapshot(
        record_digest="sha256:" + "1" * 64,
        generation_digest=failed.intended_state.generation_digest,
        lifecycle_phase=failed.intended_state.lifecycle_phase,
        projection_digest=failed.intended_state.projection_digest,
        state_digest="sha256:" + "2" * 64,
    )
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    result = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=forged,
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_PRESTATE_MISMATCH"
    assert authority.observe_active() == failed.intended_state


def test_recovery_terminal_normalizes_a_lying_nested_state_subclass():
    authority, failed, recovery, failure = _registered_recovery_successor()

    class LyingSnapshot(ProtectedStateSnapshot):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=capability,
        observed_state=failed.intended_state,
    )
    forged = LyingSnapshot(
        record_digest="sha256:" + "1" * 64,
        generation_digest=recovery.intended_state.generation_digest,
        lifecycle_phase=recovery.intended_state.lifecycle_phase,
        projection_digest=recovery.intended_state.projection_digest,
        state_digest="sha256:" + "2" * 64,
    )

    result = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=forged,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )

    assert result.state is OperationState.RECOVERY_REQUIRED
    assert result.failure_code == "AUTHORITY_RECOVERY_VALIDATION_FAILED"


def test_terminal_record_digest_cannot_be_rebound_to_a_distinct_operation():
    first = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=first.expected_state)
    authority.append_intent(first)
    first_capability = authority.acquire_capability(first, fence_epoch=1)
    authority.guarded_compare_and_swap(
        first,
        capability=first_capability,
        observed_state=first.expected_state,
    )
    record_digest = "sha256:" + "5" * 64
    first_result = authority.terminalize_operation(
        first,
        _terminal_observation(
            first,
            first_capability,
            record_digest=record_digest,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=first.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    second = replace(
        first,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "6" * 64,
        expected_state=first.intended_state,
        intended_state=replace(
            first.intended_state,
            record_digest="sha256:" + "7" * 64,
            state_digest="sha256:" + "8" * 64,
        ),
    )
    authority.append_intent(second)
    second_capability = authority.acquire_capability(second, fence_epoch=2)
    authority.guarded_compare_and_swap(
        second,
        capability=second_capability,
        observed_state=second.expected_state,
    )
    poisoned_state_record = "sha256:" + "9" * 64
    rebound_observed_state = replace(
        second.intended_state,
        record_digest=poisoned_state_record,
        state_digest="sha256:" + "b" * 64,
    )
    journal_before_rejection = authority.journal_entries

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_operation(
            second,
            _terminal_observation(
                second,
                second_capability,
                record_digest=record_digest,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=rebound_observed_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        )

    assert first_result.state is OperationState.SUCCEEDED
    assert caught.value.code == "AUTHORITY_TERMINAL_RECORD_REUSED"
    assert (
        authority.operation_state(second.operation_id)
        is OperationState.MUTATED_PENDING_VALIDATION
    )
    assert authority.journal_entries == journal_before_rejection

    retry = authority.terminalize_operation(
        second,
        _terminal_observation(
            second,
            second_capability,
            record_digest="sha256:" + "a" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=second.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    successor = replace(
        second,
        operation_id="op-activation-003",
        intent_digest="sha256:" + "c" * 64,
        plan_digest="sha256:" + "d" * 64,
        expected_state=second.intended_state,
        intended_state=replace(
            second.intended_state,
            record_digest=poisoned_state_record,
            state_digest="sha256:" + "e" * 64,
        ),
    )

    assert retry.state is OperationState.SUCCEEDED
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=3).fence_epoch == 3


def test_terminal_record_digest_cannot_be_rebound_from_forward_to_rollback():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    forward_capability = authority.acquire_capability(binding, fence_epoch=1)
    authority.guarded_compare_and_swap(
        binding,
        capability=forward_capability,
        observed_state=binding.expected_state,
    )
    record_digest = "sha256:" + "5" * 64
    authority.terminalize_operation(
        binding,
        _terminal_observation(
            binding,
            forward_capability,
            record_digest=record_digest,
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
    poisoned_state_record = "sha256:" + "4" * 64
    rebound_observed_state = replace(
        binding.expected_state,
        record_digest=poisoned_state_record,
        state_digest="sha256:" + "5" * 64,
    )
    journal_before_rejection = authority.journal_entries

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_rollback(
            binding,
            _terminal_observation(
                binding,
                rollback_capability,
                record_digest=record_digest,
                validator_digest=ROLLBACK_VALIDATOR,
                observed_state=rebound_observed_state,
                outcome=TerminalOutcome.PASS,
            ),
        )

    assert caught.value.code == "AUTHORITY_TERMINAL_RECORD_REUSED"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.ROLLBACK_PENDING_VALIDATION
    )
    assert authority.journal_entries == journal_before_rejection

    retry = authority.terminalize_rollback(
        binding,
        _terminal_observation(
            binding,
            rollback_capability,
            record_digest="sha256:" + "6" * 64,
            validator_digest=ROLLBACK_VALIDATOR,
            observed_state=binding.expected_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    successor = replace(
        binding,
        operation_id="op-activation-002",
        intent_digest="sha256:" + "7" * 64,
        plan_digest="sha256:" + "8" * 64,
        expected_state=binding.expected_state,
        intended_state=replace(
            binding.intended_state,
            record_digest=poisoned_state_record,
            state_digest="sha256:" + "9" * 64,
        ),
    )

    assert retry.state is OperationState.ROLLED_BACK
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=3).fence_epoch == 3


def test_terminal_record_digest_cannot_be_rebound_from_forward_to_recovery():
    authority, failed, recovery, failure = _registered_recovery_successor()
    recovery_capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=recovery_capability,
        observed_state=failed.intended_state,
    )
    poisoned_state_record = "sha256:" + "1" * 64
    rebound_observed_state = replace(
        recovery.intended_state,
        record_digest=poisoned_state_record,
        state_digest="sha256:" + "2" * 64,
    )
    journal_before_rejection = authority.journal_entries

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.terminalize_recovery(
            failed,
            recovery,
            _terminal_observation(
                recovery,
                recovery_capability,
                record_digest=failure.failure_record_digest,
                validator_digest=TERMINAL_VALIDATOR,
                observed_state=rebound_observed_state,
                outcome=TerminalOutcome.PASS,
                observed_effect_ids={"package-database"},
            ),
        )

    assert caught.value.code == "AUTHORITY_TERMINAL_RECORD_REUSED"
    assert (
        authority.operation_state(recovery.operation_id)
        is OperationState.RECOVERY_PENDING_VALIDATION
    )
    assert (
        authority.operation_state(failed.operation_id)
        is OperationState.RECOVERY_REQUIRED
    )
    assert authority.journal_entries == journal_before_rejection

    retry = authority.terminalize_recovery(
        failed,
        recovery,
        _terminal_observation(
            recovery,
            recovery_capability,
            record_digest="sha256:" + "3" * 64,
            validator_digest=TERMINAL_VALIDATOR,
            observed_state=recovery.intended_state,
            outcome=TerminalOutcome.PASS,
            observed_effect_ids={"package-database"},
        ),
    )
    successor = replace(
        typed_operation_binding(),
        operation_id="op-activation-002",
        intent_digest="sha256:" + "4" * 64,
        expected_state=recovery.intended_state,
        intended_state=replace(
            recovery.intended_state,
            record_digest=poisoned_state_record,
            generation_digest=GENERATION,
            state_digest="sha256:" + "5" * 64,
        ),
    )

    assert retry.state is OperationState.RECOVERED
    assert authority.operation_state(failed.operation_id) is OperationState.RECOVERED
    authority.append_intent(successor)
    assert authority.acquire_capability(successor, fence_epoch=3).fence_epoch == 3


def test_observe_active_returns_a_detached_exact_snapshot():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)

    observed = authority.observe_active()
    object.__setattr__(observed, "state_digest", "sha256:" + "e" * 64)
    current = authority.observe_active()

    assert type(observed) is ProtectedStateSnapshot
    assert type(current) is ProtectedStateSnapshot
    assert current is not observed
    assert current == binding.expected_state


def test_mutated_returned_observation_cannot_rebind_its_state_record():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)
    capability = authority.acquire_capability(binding, fence_epoch=1)
    observed = authority.observe_active()
    object.__setattr__(observed, "state_digest", "sha256:" + "e" * 64)

    with pytest.raises(AuthorityUnavailable) as caught:
        authority.guarded_compare_and_swap(
            binding,
            capability=capability,
            observed_state=observed,
        )

    assert caught.value.code == "AUTHORITY_STATE_RECORD_REBOUND"
    assert (
        authority.operation_state(binding.operation_id)
        is OperationState.CAPABILITY_ISSUED
    )
    assert [entry.kind for entry in authority.journal_entries] == [
        "operation_intent",
        "fenced_capability",
    ]

    result = authority.guarded_compare_and_swap(
        binding,
        capability=capability,
        observed_state=binding.expected_state,
    )

    assert result.state is OperationState.MUTATED_PENDING_VALIDATION


def test_acquire_returns_a_detached_capability_tree():
    binding = typed_operation_binding()
    authority = InMemoryAuthority(initial_active_state=binding.expected_state)
    authority.append_intent(binding)

    capability = authority.acquire_capability(binding, fence_epoch=1)
    pristine = replace(
        capability,
        target=replace(capability.target),
        intended_state=replace(capability.intended_state),
    )
    object.__setattr__(capability, "plan_digest", "sha256:" + "e" * 64)
    object.__setattr__(capability.target, "target_id", "substituted-host")
    object.__setattr__(capability.intended_state, "state_digest", "sha256:" + "f" * 64)

    result = authority.guarded_compare_and_swap(
        binding,
        capability=pristine,
        observed_state=binding.expected_state,
    )

    assert type(capability) is FencedCapability
    assert type(capability.target) is OperationTarget
    assert type(capability.intended_state) is ProtectedStateSnapshot
    assert result.state is OperationState.MUTATED_PENDING_VALIDATION
    assert authority.observe_active() == binding.intended_state


def test_returned_failure_mutation_cannot_rewrite_recovery_provenance():
    authority, failed, recovery, failure = _registered_recovery_successor()
    pristine_failure = replace(failure)
    original_failure_digest = failure.failure_record_digest

    object.__setattr__(failure, "record_digest", "sha256:" + "1" * 64)
    object.__setattr__(failure, "failure_record_digest", "sha256:" + "2" * 64)
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=pristine_failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )

    assert type(failure) is OperationResult
    assert capability.predecessor_failure_record_digest == original_failure_digest


def test_acquire_returns_a_detached_recovery_capability_tree():
    authority, failed, recovery, failure = _registered_recovery_successor()
    capability = authority.acquire_recovery_capability(
        failed,
        recovery,
        failure=failure,
        owner_role="recovery-owner",
        fence_epoch=2,
    )
    pristine = replace(
        capability,
        fenced=replace(
            capability.fenced,
            target=replace(capability.fenced.target),
            intended_state=replace(capability.fenced.intended_state),
        ),
    )

    object.__setattr__(
        capability,
        "predecessor_failure_record_digest",
        "sha256:" + "1" * 64,
    )
    object.__setattr__(capability.fenced, "plan_digest", "sha256:" + "2" * 64)
    object.__setattr__(capability.fenced.target, "target_id", "substituted-host")
    object.__setattr__(
        capability.fenced.intended_state,
        "state_digest",
        "sha256:" + "3" * 64,
    )

    result = authority.execute_recovery(
        failed,
        recovery,
        failure=failure,
        capability=pristine,
        observed_state=failed.intended_state,
    )

    assert type(capability) is RecoveryCapability
    assert type(capability.fenced) is FencedCapability
    assert result.state is OperationState.RECOVERY_PENDING_VALIDATION


def test_acquire_returns_a_detached_rollback_capability_tree():
    authority, binding = _rollback_required_authority()
    capability = authority.acquire_rollback_capability(binding, fence_epoch=2)
    pristine = replace(
        capability,
        target=replace(capability.target),
        intended_state=replace(capability.intended_state),
    )

    object.__setattr__(capability, "plan_digest", "sha256:" + "1" * 64)
    object.__setattr__(capability.target, "target_id", "substituted-host")
    object.__setattr__(
        capability.intended_state,
        "state_digest",
        "sha256:" + "2" * 64,
    )

    result = authority.execute_rollback(
        binding,
        capability=pristine,
        observed_state=binding.intended_state,
    )

    assert type(capability) is FencedCapability
    assert result.state is OperationState.ROLLBACK_PENDING_VALIDATION


def test_returned_receipt_mutation_cannot_rewrite_retained_evidence():
    authority = InMemoryAuthority(
        initial_active_state=typed_operation_binding().expected_state
    )
    record_digest = "sha256:" + "5" * 64
    receipt = authority.append_record(record_digest)

    object.__setattr__(receipt, "record_digest", "sha256:" + "6" * 64)
    view = authority.evidence_view()

    assert view.receipts[0].record_digest == record_digest
    assert view.receipts[0] is not receipt


def test_returned_journal_mutation_cannot_rewrite_retained_entry():
    authority = InMemoryAuthority(
        initial_active_state=typed_operation_binding().expected_state
    )
    record_digest = "sha256:" + "5" * 64
    authority.append_record(record_digest)
    entry = authority.journal_entries[0]

    object.__setattr__(entry, "record_digest", "sha256:" + "6" * 64)
    current = authority.journal_entries[0]

    assert current.record_digest == record_digest
    assert current is not entry


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
        _terminal_observation(
            first,
            capability,
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
