from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
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
    Currency,
    ConditionalApplicability,
    DependencyBinding,
    DependencyKey,
    EvidenceEvaluation,
    EvaluationInputError,
    EvidenceNotCurrent,
    EvidenceSatisfaction,
    EvidenceUnknown,
    GateAssignment,
    GateImpact,
    InvalidationPolicy,
    InvalidationEvent,
    NotApplicable,
    NotDue,
    NonPromotionalContext,
    PredicateProof,
    PreassemblyContext,
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


def _active_context(*, contract_digest: str = CONTRACT_DIGEST) -> ActiveContractContext:
    return ActiveContractContext(
        context_id="w0-generation-c",
        contract_digest=contract_digest,
        generation_id="generation-c",
    )


def _preassembly_context() -> PreassemblyContext:
    return PreassemblyContext(
        context_id="preassembly:foundation",
        profile_digest=PROFILE_DIGEST,
        source_closure_digest=SOURCE_CLOSURE_DIGEST,
        artifact_digest=ARTIFACT_DIGEST,
    )


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
        "separation": SeparationPolicy(required_attestor_roles=frozenset({"validator"})),
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
    }
    values.update(changes)
    return PredicateProof(**values)  # type: ignore[arg-type]


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
            required_attestor_roles=roles,
            forbidden_attestor_principals=forbidden_principals,
        ),
    )
    projection.clear()
    invalidation_keys.clear()
    roles.clear()
    forbidden_principals.clear()

    assert assignment.dependency_projection == frozenset({source})
    assert assignment.invalidation.invalidate_on == frozenset({source.key})
    assert assignment.separation.required_attestor_roles == frozenset({"validator"})
    assert assignment.separation.forbidden_attestor_principals == frozenset(
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
                contract_digest=CONTRACT_DIGEST,
                generation_id="generation-c",
            ),
            id="empty-active-context-id",
        ),
        pytest.param(
            lambda: ActiveContractContext(
                context_id="w0-generation-c",
                contract_digest="sha256:not-canonical",
                generation_id="generation-c",
            ),
            id="malformed-contract-digest",
        ),
        pytest.param(
            lambda: ActiveContractContext(
                context_id="w0-generation-c",
                contract_digest=CONTRACT_DIGEST,
                generation_id="generation-c",
                kind=_preassembly_context().kind,
            ),
            id="wrong-active-context-tag",
        ),
        pytest.param(
            lambda: PreassemblyContext(
                context_id="preassembly:foundation",
                profile_digest=PROFILE_DIGEST,
                source_closure_digest="sha256:not-canonical",
                artifact_digest=ARTIFACT_DIGEST,
            ),
            id="malformed-preassembly-digest",
        ),
        pytest.param(
            lambda: PreassemblyContext(
                context_id="preassembly:foundation",
                profile_digest=PROFILE_DIGEST,
                source_closure_digest=SOURCE_CLOSURE_DIGEST,
                artifact_digest=ARTIFACT_DIGEST,
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
                required_attestor_roles=frozenset({"Validator"})
            ),
            id="invalid-attestor-role",
        ),
        pytest.param(
            lambda: SeparationPolicy(
                forbidden_attestor_principals=frozenset({"/private/principal"})
            ),
            id="invalid-attestor-principal",
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


def test_attestation_and_predicate_construction_detach_dependency_inputs() -> None:
    assignment = _assignment()
    attestation_projection = set(assignment.dependency_projection)
    proof_projection = set(assignment.dependency_projection)

    attestation = _attestation(
        assignment,
        dependency_projection=attestation_projection,
    )
    conditional = _assignment(
        applicability=ConditionalApplicability(predicate_id="optional-feature")
    )
    proof = _predicate_proof(
        conditional,
        is_applicable=False,
        dependency_projection=proof_projection,
    )
    attestation_projection.clear()
    proof_projection.clear()

    assert attestation.dependency_projection == assignment.dependency_projection
    assert proof.dependency_projection == conditional.dependency_projection


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
    ],
)
def test_attestation_and_predicate_construction_reject_invalid_boundaries(
    factory,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_evaluation_construction_detaches_invalidation_history() -> None:
    assignment = _assignment()
    original = evaluate_evidence(
        assignment,
        attestation=_attestation(assignment),
        trusted_time=NOW,
    )
    events = [
        InvalidationEvent(
            event_id="event:source-change",
            observed_at=NOW,
            changed_dependencies=frozenset(
                {DependencyKey(kind="source", identifier="control-plane")}
            ),
            reason="source changed",
        )
    ]

    evaluation = EvidenceEvaluation(
        assignment=original.assignment,
        state=original.state,
        currency=Currency.STALE,
        evaluated_at=NOW,
        observed_at=original.observed_at,
        invalidation_events=events,  # type: ignore[arg-type]
    )
    events.clear()

    assert isinstance(evaluation.invalidation_events, tuple)
    assert evaluation.invalidation_event_ids == ("event:source-change",)


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
            {"actor_role": "builder"},
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
