from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (  # noqa: E402
    ActiveContractContext,
    Attestation,
    AttestationOutcome,
    ControlRecord,
    DependencyBinding,
    DependencyKey,
    GateAssignment,
    GateImpact,
    InvalidationPolicy,
    NonPromotionalEvidence,
    SeparationPolicy,
    UnconditionalApplicability,
    ValidityPolicy,
    admit_promotion,
    evaluate_evidence,
)
from control_plane.testing import InMemoryAuthority  # noqa: E402


NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


def test_passing_record_backed_by_fake_authority_remains_nonpromotional():
    context = ActiveContractContext(
        context_id="w0-candidate",
        contract_digest="sha256:contract-v1",
        generation_id="generation-c",
    )
    source = DependencyBinding(
        key=DependencyKey(kind="source", identifier="control-plane"),
        digest="sha256:source-v1",
    )
    assignment = GateAssignment(
        assignment_id="assignment:control-plane",
        subject_id="generation-c",
        gate_id="gate:control-plane",
        context=context,
        impact=GateImpact.BLOCKING,
        applicability=UnconditionalApplicability(),
        dependency_projection=frozenset({source}),
        validity=ValidityPolicy(max_age=timedelta(minutes=5)),
        invalidation=InvalidationPolicy(invalidate_on=frozenset({source.key})),
        separation=SeparationPolicy(
            required_attestor_roles=frozenset({"validator"})
        ),
    )
    attestation = Attestation(
        attestation_id="attestation:control-plane:1",
        assignment_id=assignment.assignment_id,
        subject_id=assignment.subject_id,
        gate_id=assignment.gate_id,
        context=context,
        outcome=AttestationOutcome.PASS,
        observed_at=NOW - timedelta(minutes=1),
        dependency_projection=assignment.dependency_projection,
        actor_principal="validator:w0",
        actor_role="validator",
    )
    record = ControlRecord.build(
        kind="attestation",
        record_id=attestation.attestation_id,
        payload={
            "assignment_id": attestation.assignment_id,
            "gate_id": attestation.gate_id,
            "outcome": attestation.outcome.value,
            "subject_id": attestation.subject_id,
        },
    )
    authority = InMemoryAuthority()
    authority.append_record(record.digest(), kind="attestation")
    evaluation = evaluate_evidence(
        assignment,
        attestation=attestation,
        trusted_time=NOW,
    )

    with pytest.raises(NonPromotionalEvidence) as exc_info:
        admit_promotion(evaluation, authority.evidence_view())

    assert exc_info.value.code == "EVIDENCE_NONPROMOTIONAL"
    assert record.payload["outcome"] == "pass"
