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
    EvaluationInputError,
    EvidenceNotCurrent,
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
    PromotionAssessment,
    SeparationPolicy,
    UnconditionalApplicability,
    UnknownReason,
    ValidityPolicy,
    apply_invalidation,
    evaluate_evidence,
    require_evaluation_pass,
    require_promotable_evidence,
)


NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)


def _active_context(*, contract_digest: str = "sha256:contract") -> ActiveContractContext:
    return ActiveContractContext(
        context_id="w0-generation-c",
        contract_digest=contract_digest,
        generation_id="generation-c",
    )


def _preassembly_context() -> PreassemblyContext:
    return PreassemblyContext(
        context_id="preassembly:foundation",
        profile_digest="sha256:profile",
        source_closure_digest="sha256:source-closure",
        artifact_digest="sha256:foundation-artifacts",
    )


def _assignment(**changes: object) -> GateAssignment:
    source = DependencyBinding(
        key=DependencyKey(kind="source", identifier="control-plane"),
        digest="sha256:source-v1",
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
            {"context": _active_context(contract_digest="sha256:other-contract")},
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

    blocking_result = require_promotable_evidence(blocking_evaluation)
    advisory_result = require_promotable_evidence(advisory_evaluation)

    assert blocking_result == PromotionAssessment(
        required=True,
        satisfied=True,
        promotional=True,
    )
    assert advisory_result == PromotionAssessment(
        required=False,
        satisfied=False,
        promotional=False,
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

    assert require_promotable_evidence(evaluation) == PromotionAssessment(
        required=True,
        satisfied=True,
        promotional=True,
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
        require_promotable_evidence(evaluation)
