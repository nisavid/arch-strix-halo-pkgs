from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (
    ActiveContractContext,
    Applicable,
    ApplicableUnknown,
    Attestation,
    AttestationOutcome,
    ConditionalApplicability,
    ControlRecord,
    Currency,
    DependencyBinding,
    DependencyKey,
    EvaluationInputError,
    EvidenceEvaluation,
    EvidenceNotCurrent,
    EvidenceSatisfaction,
    EvidenceUnknown,
    GateAssignment,
    GateImpact,
    InvalidationEvent,
    InvalidationPolicy,
    NonPromotionalContext,
    NotApplicable,
    NotDue,
    PreassemblyContext,
    PredicateProof,
    SeparationPolicy,
    UnconditionalApplicability,
    UnknownReason,
    ValidityPolicy,
    apply_invalidation,
    assess_evidence_satisfaction,
    evaluate_evidence,
    require_evaluation_pass,
)

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
CONTRACT_DIGEST = "sha256:" + "1" * 64
OTHER_CONTRACT_DIGEST = "sha256:" + "2" * 64
PROFILE_DIGEST = "sha256:" + "3" * 64
SOURCE_CLOSURE_DIGEST = "sha256:" + "4" * 64
ARTIFACT_DIGEST = "sha256:" + "5" * 64
SOURCE_DIGEST = "sha256:" + "6" * 64
REQUIREMENTS_DIGEST = "sha256:" + "7" * 64
ASSIGNMENTS_DIGEST = "sha256:" + "8" * 64
GENERATION_DIGEST = "sha256:" + "9" * 64


class DeceptiveControlRecord(ControlRecord):
    """Expose a validation-context kind over a different stored core."""

    def __getattribute__(self, name: str) -> object:
        if name == "kind":
            return "validation_context"
        return super().__getattribute__(name)


def _deceptive_context_record(record: ControlRecord) -> DeceptiveControlRecord:
    deceptive = object.__new__(DeceptiveControlRecord)
    for field_name in ("record_id", "payload", "_digest", "signature"):
        object.__setattr__(
            deceptive,
            field_name,
            object.__getattribute__(record, field_name),
        )
    object.__setattr__(deceptive, "kind", "identity")
    return deceptive


def _active_context(*, contract_digest: str = CONTRACT_DIGEST) -> ActiveContractContext:
    return ActiveContractContext(
        context_id="w0-generation-c",
        requirements_digest=REQUIREMENTS_DIGEST,
        assignments_digest=ASSIGNMENTS_DIGEST,
        contract_digest=contract_digest,
        generation_digest=GENERATION_DIGEST,
    )


def _preassembly_context() -> PreassemblyContext:
    return PreassemblyContext(
        context_id="preassembly:foundation",
        requirements_digest=REQUIREMENTS_DIGEST,
        assignments_digest=ASSIGNMENTS_DIGEST,
        profile_digest=PROFILE_DIGEST,
        source_closure_digest=SOURCE_CLOSURE_DIGEST,
        artifact_digests=(ARTIFACT_DIGEST,),
    )


@pytest.mark.parametrize("context", [_active_context(), _preassembly_context()])
def test_validation_context_value_objects_round_trip_canonical_records(context):
    record = context.to_record(record_id=f"validation-context:{context.context_id}")
    restored = type(context).from_record(record)

    assert restored == context
    assert record.payload["context_type"] == context.kind.value


def test_context_from_record_rejects_a_deceptive_control_record_subclass():
    record = _active_context().to_record(record_id="validation-context:deceptive")

    with pytest.raises(TypeError, match="exact ControlRecord"):
        ActiveContractContext.from_record(_deceptive_context_record(record))


def test_context_from_record_rejects_a_record_with_an_inconsistent_core():
    record = _active_context().to_record(record_id="validation-context:forged")
    object.__setattr__(record, "_digest", OTHER_CONTRACT_DIGEST)

    with pytest.raises(ValueError, match="canonical integrity"):
        ActiveContractContext.from_record(record)


def test_preassembly_context_preserves_the_exact_artifact_plurality():
    context = _preassembly_context()
    second = "sha256:" + "a" * 64
    record = ControlRecord.build(
        kind="validation_context",
        record_id="validation-context:preassembly-many",
        payload={
            **dict(context.to_record(record_id="validation-context:one").payload),
            "artifact_digests": [ARTIFACT_DIGEST, second],
        },
    )

    restored = PreassemblyContext.from_record(record)

    assert restored.artifact_digests == (ARTIFACT_DIGEST, second)


def _assignment(**changes: object) -> GateAssignment:
    source = DependencyBinding(
        key=DependencyKey(kind="source", identifier="control-plane"),
        digest=SOURCE_DIGEST,
    )
    values: dict[str, object] = {
        "assignment_id": "assignment:control-schema",
        "subject_id": "generation-c",
        "gate_id": "gate:control-schema",
        "context": _active_context(),
        "impact": GateImpact.BLOCKING,
        "applicability": UnconditionalApplicability(),
        "dependency_projection": frozenset({source}),
        "validity": ValidityPolicy(max_age=timedelta(minutes=5)),
        "invalidation": InvalidationPolicy(invalidate_on=frozenset({source.key})),
        "separation": SeparationPolicy(required_actor_roles=frozenset({"validator"})),
    }
    values.update(changes)
    return GateAssignment(**values)  # type: ignore[arg-type]


def _attestation(assignment: GateAssignment, **changes: object) -> Attestation:
    values: dict[str, object] = {
        "attestation_id": "attestation:control-schema:1",
        "assignment_id": assignment.assignment_id,
        "subject_id": assignment.subject_id,
        "gate_id": assignment.gate_id,
        "context": assignment.context,
        "outcome": AttestationOutcome.PASS,
        "observed_at": NOW - timedelta(minutes=1),
        "dependency_projection": assignment.dependency_projection,
        "actor_principal": "validator:w0",
        "actor_role": "validator",
        "actor_identity_roles": frozenset({"validator"}),
    }
    values.update(changes)
    return Attestation(**values)  # type: ignore[arg-type]


def _predicate_proof(
    assignment: GateAssignment,
    *,
    is_applicable: bool,
    **changes: object,
) -> PredicateProof:
    assert isinstance(assignment.applicability, ConditionalApplicability)
    values: dict[str, object] = {
        "proof_id": "predicate-proof:1",
        "assignment_id": assignment.assignment_id,
        "subject_id": assignment.subject_id,
        "gate_id": assignment.gate_id,
        "context": assignment.context,
        "predicate_id": assignment.applicability.predicate_id,
        "is_applicable": is_applicable,
        "observed_at": NOW - timedelta(minutes=1),
        "dependency_projection": assignment.dependency_projection,
        "actor_principal": "validator:w0",
        "actor_role": "validator",
        "actor_identity_roles": frozenset({"validator"}),
    }
    values.update(changes)
    return PredicateProof(**values)  # type: ignore[arg-type]


def _source_invalidation_event(
    *,
    event_id: str,
    observed_at: datetime,
    reason: str,
) -> InvalidationEvent:
    return InvalidationEvent(
        event_id=event_id,
        observed_at=observed_at,
        changed_dependencies=frozenset(
            {DependencyKey(kind="source", identifier="control-plane")}
        ),
        reason=reason,
    )


def test_current_pass_satisfies_a_blocking_active_contract_assignment() -> None:
    assignment = _assignment()

    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )

    assert evaluation.currency is Currency.CURRENT
    assert isinstance(evaluation.state, Applicable)
    assert evaluation.state.outcome is AttestationOutcome.PASS
    assert require_evaluation_pass(evaluation) is evaluation


@pytest.mark.parametrize("evidence_kind", ["attestation", "predicate_proof"])
@pytest.mark.parametrize(
    (
        "required_roles",
        "forbidden_principals",
        "actor_principal",
        "actor_role",
        "actor_identity_roles",
        "admitted",
    ),
    [
        pytest.param(
            frozenset({"operator", "validator"}),
            frozenset(),
            "validator:w0",
            "validator",
            frozenset({"operator", "validator"}),
            True,
            id="multi-role-identity-has-every-required-role",
        ),
        pytest.param(
            frozenset({"operator", "validator"}),
            frozenset(),
            "validator:w0",
            "validator",
            frozenset({"validator"}),
            False,
            id="identity-is-missing-a-required-role",
        ),
        pytest.param(
            frozenset({"operator", "validator"}),
            frozenset(),
            "validator:w0",
            "auditor",
            frozenset({"auditor", "operator", "validator"}),
            False,
            id="selected-role-is-not-a-required-role",
        ),
        pytest.param(
            frozenset({"validator"}),
            frozenset({"validator:w0"}),
            "validator:w0",
            "validator",
            frozenset({"validator"}),
            False,
            id="identity-is-forbidden",
        ),
    ],
)
def test_actor_separation_policy_has_attestation_and_predicate_parity(
    evidence_kind: str,
    required_roles: frozenset[str],
    forbidden_principals: frozenset[str],
    actor_principal: str,
    actor_role: str,
    actor_identity_roles: frozenset[str],
    admitted: bool,
) -> None:
    applicability = (
        ConditionalApplicability(predicate_id="has-managed-runtime")
        if evidence_kind == "predicate_proof"
        else UnconditionalApplicability()
    )
    assignment = _assignment(
        applicability=applicability,
        separation=SeparationPolicy(
            required_actor_roles=required_roles,
            forbidden_actor_principals=forbidden_principals,
        ),
    )
    evidence_changes = {
        "actor_principal": actor_principal,
        "actor_role": actor_role,
        "actor_identity_roles": actor_identity_roles,
    }

    if evidence_kind == "predicate_proof":
        evaluation = evaluate_evidence(
            assignment,
            attestation=None,
            applicability_proof=_predicate_proof(
                assignment,
                is_applicable=False,
                **evidence_changes,
            ),
            trusted_time=NOW,
        )
        accepted_state = NotApplicable
        rejected_reason = UnknownReason.APPLICABILITY_PROOF_MISMATCH
    else:
        evaluation = evaluate_evidence(
            assignment,
            attestation=_attestation(assignment, **evidence_changes),
            trusted_time=NOW,
        )
        accepted_state = Applicable
        rejected_reason = UnknownReason.SEPARATION_VIOLATION

    if admitted:
        assert isinstance(evaluation.state, accepted_state)
    else:
        assert isinstance(evaluation.state, ApplicableUnknown)
        assert evaluation.state.reason is rejected_reason


def test_assignment_construction_detaches_mutable_dependency_and_separation_inputs() -> None:
    source = DependencyBinding(
        key=DependencyKey(kind="source", identifier="control-plane"),
        digest=SOURCE_DIGEST,
    )
    projection = {source}
    invalidation_keys = {source.key}
    roles = {"validator"}
    forbidden_principals = {"builder:w0"}

    assignment = GateAssignment(
        assignment_id="assignment:control-schema",
        subject_id="generation-c",
        gate_id="gate:control-schema",
        context=_active_context(),
        impact=GateImpact.BLOCKING,
        applicability=UnconditionalApplicability(),
        dependency_projection=projection,  # type: ignore[arg-type]
        validity=ValidityPolicy(),
        invalidation=InvalidationPolicy(  # type: ignore[arg-type]
            invalidate_on=invalidation_keys
        ),
        separation=SeparationPolicy(  # type: ignore[arg-type]
            required_actor_roles=roles,
            forbidden_actor_principals=forbidden_principals,
        ),
    )
    projection.clear()
    invalidation_keys.clear()
    roles.clear()
    forbidden_principals.clear()

    assert assignment.dependency_projection == frozenset({source})
    assert assignment.invalidation.invalidate_on == frozenset({source.key})
    assert assignment.separation.required_actor_roles == frozenset({"validator"})
    assert assignment.separation.forbidden_actor_principals == frozenset(
        {"builder:w0"}
    )


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: DependencyKey(kind="", identifier="control-plane"),
            id="empty-dependency-kind",
        ),
        pytest.param(
            lambda: DependencyKey(kind="source", identifier="/private/path"),
            id="unstable-dependency-identifier",
        ),
        pytest.param(
            lambda: DependencyBinding(
                key=DependencyKey(kind="source", identifier="control-plane"),
                digest="sha256:not-canonical",
            ),
            id="malformed-dependency-digest",
        ),
        pytest.param(
            lambda: ActiveContractContext(
                context_id="",
                requirements_digest=REQUIREMENTS_DIGEST,
                assignments_digest=ASSIGNMENTS_DIGEST,
                contract_digest=CONTRACT_DIGEST,
                generation_digest=GENERATION_DIGEST,
            ),
            id="empty-active-context-id",
        ),
        pytest.param(
            lambda: ActiveContractContext(
                context_id="w0-generation-c",
                requirements_digest=REQUIREMENTS_DIGEST,
                assignments_digest=ASSIGNMENTS_DIGEST,
                contract_digest="sha256:not-canonical",
                generation_digest=GENERATION_DIGEST,
            ),
            id="malformed-contract-digest",
        ),
        pytest.param(
            lambda: ActiveContractContext(
                context_id="w0-generation-c",
                requirements_digest=REQUIREMENTS_DIGEST,
                assignments_digest=ASSIGNMENTS_DIGEST,
                contract_digest=CONTRACT_DIGEST,
                generation_digest=GENERATION_DIGEST,
                kind=_preassembly_context().kind,
            ),
            id="wrong-active-context-tag",
        ),
        pytest.param(
            lambda: PreassemblyContext(
                context_id="preassembly:foundation",
                requirements_digest=REQUIREMENTS_DIGEST,
                assignments_digest=ASSIGNMENTS_DIGEST,
                profile_digest=PROFILE_DIGEST,
                source_closure_digest="sha256:not-canonical",
                artifact_digests=(ARTIFACT_DIGEST,),
            ),
            id="malformed-preassembly-digest",
        ),
        pytest.param(
            lambda: PreassemblyContext(
                context_id="preassembly:foundation",
                requirements_digest=REQUIREMENTS_DIGEST,
                assignments_digest=ASSIGNMENTS_DIGEST,
                profile_digest=PROFILE_DIGEST,
                source_closure_digest=SOURCE_CLOSURE_DIGEST,
                artifact_digests=(ARTIFACT_DIGEST,),
                kind=_active_context().kind,
            ),
            id="wrong-preassembly-context-tag",
        ),
        pytest.param(
            lambda: ConditionalApplicability(predicate_id=""),
            id="empty-predicate-id",
        ),
    ],
)
def test_value_object_construction_rejects_malformed_domain_primitives(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_invalidation_event_construction_detaches_changed_dependencies() -> None:
    source_key = DependencyKey(kind="source", identifier="control-plane")
    changed_dependencies = {source_key}

    event = InvalidationEvent(
        event_id="event:source-change",
        observed_at=NOW,
        changed_dependencies=changed_dependencies,  # type: ignore[arg-type]
        reason="source changed",
    )
    changed_dependencies.clear()

    assert event.changed_dependencies == frozenset({source_key})


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: ValidityPolicy(max_age=-timedelta(seconds=1)),
            id="negative-validity",
        ),
        pytest.param(
            lambda: ValidityPolicy(max_age="five minutes"),  # type: ignore[arg-type]
            id="invalid-validity-type",
        ),
        pytest.param(
            lambda: InvalidationPolicy(
                invalidate_on=frozenset({"source"})  # type: ignore[arg-type]
            ),
            id="invalid-invalidation-key",
        ),
        pytest.param(
            lambda: InvalidationEvent(
                event_id="event:source-change",
                observed_at=NOW.replace(tzinfo=None),
                changed_dependencies=frozenset(
                    {DependencyKey(kind="source", identifier="control-plane")}
                ),
                reason="source changed",
            ),
            id="naive-invalidation-time",
        ),
        pytest.param(
            lambda: InvalidationEvent(
                event_id="event:source-change",
                observed_at=NOW,
                changed_dependencies=frozenset(),
                reason="source changed",
            ),
            id="empty-invalidation-change",
        ),
        pytest.param(
            lambda: InvalidationEvent(
                event_id="event:source-change",
                observed_at=NOW,
                changed_dependencies=frozenset(
                    {DependencyKey(kind="source", identifier="control-plane")}
                ),
                reason=" ",
            ),
            id="empty-invalidation-reason",
        ),
        pytest.param(
            lambda: SeparationPolicy(
                required_actor_roles=frozenset({"Validator"})
            ),
            id="invalid-actor-role",
        ),
        pytest.param(
            lambda: SeparationPolicy(
                forbidden_actor_principals=frozenset({"/private/principal"})
            ),
            id="invalid-actor-principal",
        ),
    ],
)
def test_policy_construction_rejects_invalid_boundary_values(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: _assignment(assignment_id=""),
            id="empty-assignment-id",
        ),
        pytest.param(
            lambda: _assignment(context=object()),
            id="invalid-context-type",
        ),
        pytest.param(
            lambda: _assignment(impact="blocking"),
            id="invalid-impact-type",
        ),
        pytest.param(
            lambda: _assignment(applicability="unconditional"),
            id="invalid-applicability-type",
        ),
        pytest.param(
            lambda: _assignment(validity=object()),
            id="invalid-validity-policy",
        ),
        pytest.param(
            lambda: _assignment(invalidation=object()),
            id="invalid-invalidation-policy",
        ),
        pytest.param(
            lambda: _assignment(separation=object()),
            id="invalid-separation-policy",
        ),
        pytest.param(
            lambda: _assignment(
                dependency_projection=(
                    DependencyBinding(
                        key=DependencyKey(
                            kind="source",
                            identifier="control-plane",
                        ),
                        digest=SOURCE_DIGEST,
                    ),
                    DependencyBinding(
                        key=DependencyKey(
                            kind="source",
                            identifier="control-plane",
                        ),
                        digest="sha256:" + "7" * 64,
                    ),
                )
            ),
            id="conflicting-dependency-binding",
        ),
        pytest.param(
            lambda: _assignment(
                invalidation=InvalidationPolicy(
                    invalidate_on=frozenset(
                        {DependencyKey(kind="driver", identifier="amdgpu")}
                    )
                )
            ),
            id="unprojected-invalidation-key",
        ),
    ],
)
def test_assignment_construction_rejects_invalid_or_inconsistent_boundaries(
    factory,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_attestation_and_predicate_construction_detach_mutable_inputs() -> None:
    assignment = _assignment()
    attestation_projection = set(assignment.dependency_projection)
    proof_projection = set(assignment.dependency_projection)
    attestation_roles = {"operator", "validator"}
    proof_roles = {"operator", "validator"}

    attestation = _attestation(
        assignment,
        dependency_projection=attestation_projection,
        actor_identity_roles=attestation_roles,
    )
    conditional = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature")
    )
    proof = _predicate_proof(
        conditional,
        is_applicable=False,
        dependency_projection=proof_projection,
        actor_identity_roles=proof_roles,
    )
    attestation_projection.clear()
    proof_projection.clear()
    attestation_roles.clear()
    proof_roles.clear()

    assert attestation.dependency_projection == assignment.dependency_projection
    assert proof.dependency_projection == conditional.dependency_projection
    assert attestation.actor_identity_roles == frozenset({"operator", "validator"})
    assert proof.actor_identity_roles == frozenset({"operator", "validator"})


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: _attestation(_assignment(), attestation_id=""),
            id="empty-attestation-id",
        ),
        pytest.param(
            lambda: _attestation(_assignment(), context=object()),
            id="invalid-attestation-context",
        ),
        pytest.param(
            lambda: _attestation(_assignment(), outcome="pass"),
            id="invalid-attestation-outcome",
        ),
        pytest.param(
            lambda: _attestation(
                _assignment(),
                observed_at=NOW.replace(tzinfo=None),
            ),
            id="naive-attestation-time",
        ),
        pytest.param(
            lambda: _attestation(
                _assignment(),
                actor_principal="/private/principal",
            ),
            id="invalid-attestation-principal",
        ),
        pytest.param(
            lambda: _predicate_proof(
                _assignment(
                    applicability=ConditionalApplicability(
                        predicate_id="optional-feature"
                    )
                ),
                is_applicable=1,  # type: ignore[arg-type]
            ),
            id="non-boolean-applicability",
        ),
        pytest.param(
            lambda: _predicate_proof(
                _assignment(
                    applicability=ConditionalApplicability(
                        predicate_id="optional-feature"
                    )
                ),
                is_applicable=False,
                actor_role="Validator",
            ),
            id="invalid-proof-role",
        ),
        pytest.param(
            lambda: _attestation(
                _assignment(),
                actor_role="operator",
                actor_identity_roles=frozenset({"validator"}),
            ),
            id="attestation-acting-role-not-held-by-identity",
        ),
        pytest.param(
            lambda: _predicate_proof(
                _assignment(
                    applicability=ConditionalApplicability(
                        predicate_id="optional-feature"
                    )
                ),
                is_applicable=False,
                actor_role="operator",
                actor_identity_roles=frozenset({"validator"}),
            ),
            id="predicate-acting-role-not-held-by-identity",
        ),
        pytest.param(
            lambda: _predicate_proof(
                _assignment(
                    applicability=ConditionalApplicability(
                        predicate_id="optional-feature"
                    )
                ),
                is_applicable=False,
                actor_identity_roles=frozenset({"Validator"}),
            ),
            id="invalid-identity-role",
        ),
    ],
)
def test_attestation_and_predicate_construction_reject_invalid_boundaries(
    factory,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_invalidation_derivation_keeps_immutable_history() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    evaluation = apply_invalidation(
        original,
        InvalidationEvent(
            event_id="event:source-change",
            observed_at=NOW,
            changed_dependencies=frozenset(
                {DependencyKey(kind="source", identifier="control-plane")}
            ),
            reason="source changed",
        ),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.invalidation_events, tuple)
    assert evaluation.invalidation_event_ids == ("event:source-change",)


def test_invalidation_rejects_trusted_time_before_source_evaluation() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(
            assignment,
            observed_at=NOW - timedelta(minutes=2),
        ),
        trusted_time=NOW,
    )
    event = _source_invalidation_event(
        event_id="event:source-change:early-clock",
        observed_at=NOW - timedelta(minutes=1),
        reason="source changed before the evaluation completed",
    )

    with pytest.raises(
        EvaluationInputError,
        match="trusted_time is before source evaluation evaluated_at",
    ):
        apply_invalidation(
            original,
            event,
            trusted_time=event.observed_at,
        )


def test_invalidation_accepts_the_source_evaluation_time_boundary() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    event = _source_invalidation_event(
        event_id="event:source-change:equal-clock",
        observed_at=NOW,
        reason="source changed at the evaluation boundary",
    )

    invalidated = apply_invalidation(
        original,
        event,
        trusted_time=original.evaluated_at,
    )

    assert invalidated.evaluated_at == original.evaluated_at
    assert invalidated.currency is Currency.STALE
    assert invalidated.invalidation_events == (event,)


def test_invalidation_accepts_later_trusted_time_with_exact_provenance() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    event = _source_invalidation_event(
        event_id="event:source-change:later-clock",
        observed_at=NOW + timedelta(minutes=1),
        reason="source changed after evaluation",
    )
    trusted_time = NOW + timedelta(minutes=2)

    invalidated = apply_invalidation(
        original,
        event,
        trusted_time=trusted_time,
    )

    assert invalidated.evaluated_at == trusted_time
    assert invalidated.state is original.state
    assert invalidated.currency is Currency.STALE
    assert invalidated.invalidation_events == (event,)


def test_repeated_invalidation_preserves_monotonic_time_and_exact_history() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    first_event = _source_invalidation_event(
        event_id="event:source-change:first",
        observed_at=NOW + timedelta(minutes=1),
        reason="first source change",
    )
    first = apply_invalidation(
        original,
        first_event,
        trusted_time=NOW + timedelta(minutes=2),
    )
    second_event = _source_invalidation_event(
        event_id="event:source-change:second",
        observed_at=NOW + timedelta(minutes=1, seconds=30),
        reason="second source change",
    )

    with pytest.raises(
        EvaluationInputError,
        match="trusted_time is before source evaluation evaluated_at",
    ):
        apply_invalidation(
            first,
            second_event,
            trusted_time=second_event.observed_at,
        )

    repeated = apply_invalidation(
        first,
        second_event,
        trusted_time=NOW + timedelta(minutes=3),
    )

    assert repeated.evaluated_at > first.evaluated_at
    assert repeated.state is first.state
    assert repeated.currency is Currency.STALE
    assert repeated.invalidation_events == (first_event, second_event)
    assert tuple(event.reason for event in repeated.invalidation_events) == (
        "first source change",
        "second source change",
    )


def test_direct_evaluation_construction_cannot_forge_currentness() -> None:
    assignment = _assignment()
    stale_attestation = _attestation(
        assignment,
        observed_at=NOW - timedelta(minutes=10),
    )

    with pytest.raises(TypeError):
        EvidenceEvaluation(
            assignment=assignment,
            state=Applicable(
                outcome=AttestationOutcome.PASS,
                attestation=stale_attestation,
            ),
            currency=Currency.CURRENT,
            evaluated_at=NOW,
            observed_at=stale_attestation.observed_at,
        )


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: Applicable(
                outcome="pass",  # type: ignore[arg-type]
                attestation=_attestation(_assignment()),
            ),
            id="invalid-applicable-outcome-type",
        ),
        pytest.param(
            lambda: Applicable(
                outcome=AttestationOutcome.FAIL,
                attestation=_attestation(_assignment()),
            ),
            id="applicable-outcome-mismatch",
        ),
        pytest.param(
            lambda: Applicable(
                outcome=AttestationOutcome.UNKNOWN,
                attestation=_attestation(
                    _assignment(),
                    outcome=AttestationOutcome.UNKNOWN,
                ),
            ),
            id="unknown-as-applicable",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason="missing_attestation",  # type: ignore[arg-type]
            ),
            id="invalid-unknown-reason-type",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason=UnknownReason.MISSING_ATTESTATION,
                predicate_proof=object(),  # type: ignore[arg-type]
            ),
            id="invalid-unknown-predicate-proof-type",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason=UnknownReason.MISSING_APPLICABILITY_PROOF,
                predicate_proof=_predicate_proof(
                    _assignment(
                        applicability=ConditionalApplicability(
                            predicate_id="optional-feature"
                        )
                    ),
                    is_applicable=True,
                ),
            ),
            id="missing-applicability-proof-with-proof",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason=UnknownReason.APPLICABILITY_PROOF_MISMATCH,
            ),
            id="applicability-proof-mismatch-without-proof",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason=UnknownReason.MISSING_ATTESTATION,
                attestation=_attestation(_assignment()),
            ),
            id="missing-attestation-with-attestation",
        ),
        pytest.param(
            lambda: ApplicableUnknown(
                reason=UnknownReason.REPORTED_UNKNOWN,
            ),
            id="attestation-derived-unknown-without-attestation",
        ),
        pytest.param(
            lambda: NotApplicable(
                proof=_predicate_proof(
                    _assignment(
                        applicability=ConditionalApplicability(
                            predicate_id="optional-feature"
                        )
                    ),
                    is_applicable=True,
                )
            ),
            id="applicable-proof-as-not-applicable",
        ),
        pytest.param(
            lambda: EvidenceEvaluation(
                assignment=_assignment(),
                state=NotDue(),
                currency="current",  # type: ignore[arg-type]
                evaluated_at=NOW,
                observed_at=NOW,
            ),
            id="invalid-currency-type",
        ),
        pytest.param(
            lambda: EvidenceEvaluation(
                assignment=_assignment(),
                state=NotDue(),
                currency=Currency.CURRENT,
                evaluated_at=NOW.replace(tzinfo=None),
                observed_at=NOW,
            ),
            id="naive-evaluation-time",
        ),
        pytest.param(
            lambda: EvidenceEvaluation(
                assignment=_assignment(),
                state=NotDue(),
                currency=Currency.CURRENT,
                evaluated_at=NOW - timedelta(seconds=1),
                observed_at=NOW,
            ),
            id="evaluation-before-observation",
        ),
        pytest.param(
            lambda: EvidenceEvaluation(
                assignment=_assignment(),
                state=NotDue(),
                currency=Currency.STALE,
                evaluated_at=NOW,
                observed_at=NOW,
                invalidation_events=(
                    InvalidationEvent(
                        event_id="event:driver-change",
                        observed_at=NOW,
                        changed_dependencies=frozenset(
                            {
                                DependencyKey(
                                    kind="driver",
                                    identifier="amdgpu",
                                )
                            }
                        ),
                        reason="driver changed",
                    ),
                ),
            ),
            id="unrelated-invalidation-history",
        ),
        pytest.param(
            lambda: EvidenceSatisfaction(
                required=False,
                satisfied=True,
            ),
            id="satisfied-nonrequired-assessment",
        ),
        pytest.param(
            lambda: EvidenceSatisfaction(
                required=1,  # type: ignore[arg-type]
                satisfied=True,
            ),
            id="non-boolean-assessment-field",
        ),
    ],
)
def test_derived_evaluation_construction_rejects_invalid_boundaries(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_expired_pass_remains_historical_but_is_explicitly_stale() -> None:
    assignment = _assignment()

    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(
            assignment,
            observed_at=NOW - timedelta(minutes=6),
        ),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, Applicable)
    assert evaluation.state.outcome is AttestationOutcome.PASS
    assert evaluation.currency is Currency.STALE
    with pytest.raises(EvidenceNotCurrent):
        require_evaluation_pass(evaluation)


def test_evaluation_rejects_observations_after_the_supplied_trusted_time() -> None:
    assignment = _assignment()

    with pytest.raises(EvaluationInputError, match="after trusted_time"):
        evaluate_evidence(
            assignment,
            attestation=_attestation(
                assignment,
                observed_at=NOW + timedelta(seconds=1),
            ),
            trusted_time=NOW,
        )


@pytest.mark.parametrize(
    ("attestation_changes", "reason"),
    [
        ({"assignment_id": "assignment:other"}, UnknownReason.ASSIGNMENT_MISMATCH),
        ({"subject_id": "generation-b"}, UnknownReason.SUBJECT_MISMATCH),
        ({"gate_id": "gate:other"}, UnknownReason.GATE_MISMATCH),
        (
            {"context": _active_context(contract_digest=OTHER_CONTRACT_DIGEST)},
            UnknownReason.CONTEXT_MISMATCH,
        ),
    ],
)
def test_mismatched_evidence_is_unknown_and_cannot_pass(
    attestation_changes: dict[str, object],
    reason: UnknownReason,
) -> None:
    assignment = _assignment()

    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment, **attestation_changes),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is reason
    with pytest.raises(EvidenceUnknown):
        require_evaluation_pass(evaluation)


def test_missing_attestation_derives_unknown_instead_of_inventing_a_result() -> None:
    evaluation = evaluate_evidence(
        _assignment(),
        attestation=None,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.MISSING_ATTESTATION
    with pytest.raises(EvidenceUnknown):
        require_evaluation_pass(evaluation)


@pytest.mark.parametrize(
    ("attestation_changes", "reason"),
    [
        (
            {"outcome": AttestationOutcome.UNKNOWN},
            UnknownReason.REPORTED_UNKNOWN,
        ),
        (
            {"dependency_projection": frozenset()},
            UnknownReason.DEPENDENCY_MISMATCH,
        ),
        (
            {
                "actor_role": "builder",
                "actor_identity_roles": frozenset({"builder"}),
            },
            UnknownReason.SEPARATION_VIOLATION,
        ),
    ],
)
def test_unverifiable_attestations_derive_an_explicit_unknown(
    attestation_changes: dict[str, object],
    reason: UnknownReason,
) -> None:
    assignment = _assignment()

    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment, **attestation_changes),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is reason


def test_current_false_predicate_proves_a_conditional_assignment_not_applicable() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=_predicate_proof(
            assignment,
            is_applicable=False,
        ),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, NotApplicable)
    assert evaluation.state.proof.is_applicable is False
    assert evaluation.currency is Currency.CURRENT


def test_current_true_predicate_proves_a_conditional_assignment_applicable() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(assignment, is_applicable=True)

    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, Applicable)
    assert evaluation.state.predicate_proof is proof
    assert evaluation.state.predicate_proof.is_applicable is True


def test_conditional_applicable_evaluation_requires_a_true_predicate_proof() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.MISSING_APPLICABILITY_PROOF
    assert evaluation.state.predicate_proof is None
    assert evaluation.observed_at == NOW


def test_conditional_true_predicate_is_retained_when_attestation_is_missing() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(assignment, is_applicable=True)

    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.MISSING_ATTESTATION
    assert evaluation.state.predicate_proof is proof
    assert evaluation.observed_at == proof.observed_at
    assert evaluation.currency is Currency.CURRENT


def test_stale_true_predicate_remains_stale_when_attestation_is_missing() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(
        assignment,
        is_applicable=True,
        observed_at=NOW - timedelta(minutes=5, seconds=1),
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.MISSING_ATTESTATION
    assert evaluation.state.predicate_proof is proof
    assert evaluation.observed_at == proof.observed_at
    assert evaluation.currency is Currency.STALE


@pytest.mark.parametrize(
    ("proof_age", "attestation_age", "expected_currency"),
    [
        pytest.param(
            timedelta(minutes=5),
            timedelta(minutes=1),
            Currency.CURRENT,
            id="proof-at-freshness-boundary",
        ),
        pytest.param(
            timedelta(minutes=5, seconds=1),
            timedelta(minutes=1),
            Currency.STALE,
            id="stale-proof",
        ),
        pytest.param(
            timedelta(minutes=1),
            timedelta(minutes=5, seconds=1),
            Currency.STALE,
            id="stale-attestation",
        ),
    ],
)
def test_conditional_unknown_uses_oldest_retained_evidence_currency(
    proof_age: timedelta,
    attestation_age: timedelta,
    expected_currency: Currency,
) -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(
        assignment,
        is_applicable=True,
        observed_at=NOW - proof_age,
    )
    attestation = _attestation(
        assignment,
        assignment_id="assignment:other",
        observed_at=NOW - attestation_age,
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=attestation,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.ASSIGNMENT_MISMATCH
    assert evaluation.state.attestation is attestation
    assert evaluation.state.predicate_proof is proof
    assert evaluation.observed_at == min(
        proof.observed_at,
        attestation.observed_at,
    )
    assert evaluation.currency is expected_currency


def test_stale_mismatching_predicate_preserves_its_own_currency() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(
        assignment,
        is_applicable=True,
        assignment_id="assignment:other",
        observed_at=NOW - timedelta(minutes=5, seconds=1),
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.APPLICABILITY_PROOF_MISMATCH
    assert evaluation.state.predicate_proof is proof
    assert evaluation.observed_at == proof.observed_at
    assert evaluation.currency is Currency.STALE


@pytest.mark.parametrize(
    ("attestation_changes", "reason"),
    [
        ({"assignment_id": "assignment:other"}, UnknownReason.ASSIGNMENT_MISMATCH),
        ({"subject_id": "generation-b"}, UnknownReason.SUBJECT_MISMATCH),
        ({"gate_id": "gate:other"}, UnknownReason.GATE_MISMATCH),
        (
            {"context": _active_context(contract_digest=OTHER_CONTRACT_DIGEST)},
            UnknownReason.CONTEXT_MISMATCH,
        ),
        ({"dependency_projection": frozenset()}, UnknownReason.DEPENDENCY_MISMATCH),
        (
            {
                "actor_role": "builder",
                "actor_identity_roles": frozenset({"builder"}),
            },
            UnknownReason.SEPARATION_VIOLATION,
        ),
        ({"outcome": AttestationOutcome.UNKNOWN}, UnknownReason.REPORTED_UNKNOWN),
    ],
)
def test_conditional_true_predicate_is_retained_with_unknown_attestation(
    attestation_changes: dict[str, object],
    reason: UnknownReason,
) -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    proof = _predicate_proof(assignment, is_applicable=True)
    attestation = _attestation(assignment, **attestation_changes)

    evaluation = evaluate_evidence(
        assignment,
        attestation=attestation,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is reason
    assert evaluation.state.attestation is attestation
    assert evaluation.state.predicate_proof is proof


@pytest.mark.parametrize(
    "proof_changes",
    [
        pytest.param(
            {"assignment_id": "assignment:other"},
            id="assignment",
        ),
        pytest.param(
            {"subject_id": "generation-b"},
            id="subject",
        ),
        pytest.param(
            {"gate_id": "gate:other"},
            id="gate",
        ),
        pytest.param(
            {"context": _active_context(contract_digest=OTHER_CONTRACT_DIGEST)},
            id="context",
        ),
        pytest.param(
            {"predicate_id": "other-predicate"},
            id="predicate",
        ),
        pytest.param(
            {"dependency_projection": frozenset()},
            id="dependency-projection",
        ),
        pytest.param(
            {
                "actor_role": "builder",
                "actor_identity_roles": frozenset({"builder"}),
            },
            id="separation-policy",
        ),
    ],
)
def test_conditional_applicable_evaluation_requires_its_exact_true_predicate_proof(
    proof_changes: dict[str, object],
) -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    attestation = _attestation(assignment)
    proof = _predicate_proof(
        assignment,
        is_applicable=True,
        **proof_changes,
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=attestation,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.APPLICABILITY_PROOF_MISMATCH
    assert evaluation.state.predicate_proof is proof


def test_false_predicate_proof_cannot_waive_an_unconditional_assignment() -> None:
    conditional = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature"),
    )
    unconditional = _assignment()

    evaluation = evaluate_evidence(
        unconditional,
        attestation=None,
        applicability_proof=_predicate_proof(
            conditional,
            is_applicable=False,
        ),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.MISSING_ATTESTATION
    assert evaluation.state.predicate_proof is None


def test_unconditional_unknown_attestation_does_not_bind_a_predicate_proof() -> None:
    conditional = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature"),
    )
    unconditional = _assignment()
    proof = _predicate_proof(conditional, is_applicable=True)

    evaluation = evaluate_evidence(
        unconditional,
        attestation=_attestation(
            unconditional,
            outcome=AttestationOutcome.UNKNOWN,
        ),
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.REPORTED_UNKNOWN
    assert evaluation.state.predicate_proof is None


def test_unconditional_applicable_evaluation_does_not_bind_a_predicate_proof() -> None:
    conditional = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature"),
    )
    unconditional = _assignment()
    attestation = _attestation(unconditional)

    evaluation = evaluate_evidence(
        unconditional,
        attestation=attestation,
        applicability_proof=_predicate_proof(
            conditional,
            is_applicable=True,
        ),
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, Applicable)
    assert evaluation.state.predicate_proof is None


def test_not_applicable_evaluation_requires_a_separated_false_predicate_proof() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature"),
    )
    proof = _predicate_proof(
        assignment,
        is_applicable=False,
        actor_role="builder",
        actor_identity_roles=frozenset({"builder"}),
    )

    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=proof,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, ApplicableUnknown)
    assert evaluation.state.reason is UnknownReason.APPLICABILITY_PROOF_MISMATCH


def test_not_due_is_an_explicit_state_and_needs_no_attestation() -> None:
    evaluation = evaluate_evidence(
        _assignment(),
        attestation=None,
        due=False,
        trusted_time=NOW,
    )

    assert isinstance(evaluation.state, NotDue)
    assert evaluation.currency is Currency.CURRENT


def test_invalidation_stales_only_the_matching_dependency_slice() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    unrelated = InvalidationEvent(
        event_id="event:driver-change",
        observed_at=NOW,
        changed_dependencies=frozenset(
            {DependencyKey(kind="driver", identifier="amdgpu")}
        ),
        reason="driver changed",
    )

    unaffected = apply_invalidation(
        original,
        unrelated,
        trusted_time=NOW,
    )
    invalidated = apply_invalidation(
        original,
        InvalidationEvent(
            event_id="event:source-change",
            observed_at=NOW,
            changed_dependencies=frozenset(
                {DependencyKey(kind="source", identifier="control-plane")}
            ),
            reason="source changed",
        ),
        trusted_time=NOW,
    )

    assert unaffected is original
    assert original.currency is Currency.CURRENT
    assert invalidated is not original
    assert invalidated.currency is Currency.STALE
    assert invalidated.invalidation_event_ids == ("event:source-change",)


def test_promotion_requires_blocking_proof_but_only_records_advisory_results() -> None:
    blocking = _assignment()
    blocking_evaluation = evaluate_evidence(
        blocking,
        attestation=_attestation(blocking),
        trusted_time=NOW,
    )
    advisory = _assignment(impact=GateImpact.ADVISORY)
    advisory_evaluation = evaluate_evidence(
        advisory,
        attestation=_attestation(advisory, outcome=AttestationOutcome.FAIL),
        trusted_time=NOW,
    )

    blocking_result = assess_evidence_satisfaction(blocking_evaluation)
    advisory_result = assess_evidence_satisfaction(advisory_evaluation)

    assert blocking_result == EvidenceSatisfaction(
        required=True,
        satisfied=True,
    )
    assert advisory_result == EvidenceSatisfaction(
        required=False,
        satisfied=False,
    )


def test_current_conditional_non_applicability_satisfies_promotion_obligation() -> None:
    assignment = _assignment(
        applicability=ConditionalApplicability(predicate_id="has-managed-runtime"),
    )
    evaluation = evaluate_evidence(
        assignment,
        attestation=None,
        applicability_proof=_predicate_proof(
            assignment,
            is_applicable=False,
        ),
        trusted_time=NOW,
    )

    assert assess_evidence_satisfaction(evaluation) == EvidenceSatisfaction(
        required=True,
        satisfied=True,
    )


def test_preassembly_pass_stays_bound_to_its_profile_and_is_never_promotional() -> None:
    context = _preassembly_context()
    assignment = _assignment(context=context)
    evaluation = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )

    assert evaluation.assignment.context is context
    assert evaluation.state.attestation.context is context
    assert require_evaluation_pass(evaluation) is evaluation
    with pytest.raises(NonPromotionalContext):
        assess_evidence_satisfaction(evaluation)
