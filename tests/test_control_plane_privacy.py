import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (
    ControlRecord,
    PrivacyEnvelopeError,
    RecordErrorCode,
)

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64
DIGEST_3 = "sha256:" + "3" * 64
DIGEST_4 = "sha256:" + "4" * 64
DIGEST_5 = "sha256:" + "5" * 64
DIGEST_6 = "sha256:" + "6" * 64
TIMESTAMP = "2026-08-12T10:00:00Z"


class DeceptiveControlRecord(ControlRecord):
    """Expose a safe-looking kind over a different stored record core."""

    def __getattribute__(self, name: str) -> object:
        if name == "kind":
            return "gate"
        return super().__getattribute__(name)


def _deceptive_restricted_record(record: ControlRecord) -> DeceptiveControlRecord:
    deceptive = object.__new__(DeceptiveControlRecord)
    for field_name in ("kind", "record_id", "payload", "_digest", "signature"):
        object.__setattr__(
            deceptive,
            field_name,
            object.__getattribute__(record, field_name),
        )
    return deceptive


def _gate_payload() -> dict[str, object]:
    return {
        "assertion_digest": DIGEST_1,
        "attestation_authorization_digest": DIGEST_5,
        "evidence_shape_digest": DIGEST_2,
        "fixture_role_digest": DIGEST_3,
        "gate_id": "gate_1",
        "validator_digest": DIGEST_4,
    }


@pytest.mark.parametrize(
    ("kind", "record_id", "payload"),
    [
        (
            "separation_policy",
            "separation_policy_1",
            {
                "forbidden_actor_identity_digests": [DIGEST_1],
                "policy_id": "separation_policy_1",
                "required_actor_roles": ["operator"],
            },
        ),
        (
            "acceptance_request",
            "acceptance_request_1",
            {
                "acceptance_authorization_digest": DIGEST_1,
                "atomic_evidence_cut_digest": DIGEST_2,
                "final_service_anchor_receipt_digest": DIGEST_2,
                "generation_digest": DIGEST_3,
                "predecessor_checkpoint_digest": DIGEST_4,
                "promotion_contract_digest": DIGEST_5,
                "requested_at": TIMESTAMP,
                "target_digest": DIGEST_6,
                "target_protected_state_digest": DIGEST_1,
            },
        ),
        (
            "lifecycle_checkpoint",
            "captured_checkpoint_1",
            {
                "checkpoint_id": "captured_checkpoint_1",
                "established_at": TIMESTAMP,
                "generation_class": "b0",
                "generation_digest": DIGEST_1,
                "phase": "captured",
                "root_authorization_digest": DIGEST_2,
                "target_digest": DIGEST_3,
                "target_protected_state_digest": DIGEST_4,
            },
        ),
        (
            "dependency_projection",
            "dependency_projection_1",
            {
                "dependency_digests": [DIGEST_1, DIGEST_2],
                "dependency_keys": ["driver/device", "generation"],
                "projection_id": "dependency_projection_1",
            },
        ),
        (
            "validity_policy",
            "validity_policy_1",
            {
                "attestation_max_age_seconds": 300,
                "evidence_cut_max_age_seconds": 300,
                "expiry_rule": "earliest_constituent_expiry",
                "inclusion_edge_max_age_seconds": 28_800,
                "policy_id": "validity_policy_1",
                "predicate_proof_max_age_seconds": 300,
            },
        ),
        (
            "invalidation_policy",
            "invalidation_policy_1",
            {
                "dependency_keys": ["driver/device", "generation"],
                "policy_id": "invalidation_policy_1",
            },
        ),
        (
            "trusted_time_observation",
            "trusted_time_observation_1",
            {
                "authority_head_digest": DIGEST_1,
                "observation_id": "trusted_time_observation_1",
                "observed_at": TIMESTAMP,
                "time_authority_digest": DIGEST_2,
                "time_proof_digest": DIGEST_3,
            },
        ),
        (
            "invalidation_stream_checkpoint",
            "invalidation_stream_checkpoint_1",
            {
                "authority_head_digest": DIGEST_1,
                "authority_manifest_digest": DIGEST_2,
                "authority_view_digest": DIGEST_3,
                "checkpoint_id": "invalidation_checkpoint_1",
                "checkpointed_at": TIMESTAMP,
                "complete_through_sequence": 42,
                "completeness_proof_digest": DIGEST_4,
                "current_dependency_projection_digest": DIGEST_5,
                "fork_proof_digest": DIGEST_6,
                "invalidation_policy_digest": DIGEST_1,
                "stream_head_digest": DIGEST_2,
                "stream_id": "invalidation_stream_1",
            },
        ),
        (
            "evidence_currency_proof",
            "evidence_currency_proof_1",
            {
                "evaluated_dependency_projection_digest": DIGEST_1,
                "evaluation_digest": DIGEST_2,
                "inclusion_edge_digests": [],
                "invalidation_policy_digest": DIGEST_3,
                "invalidation_stream_checkpoint_digest": DIGEST_4,
                "trusted_time_observation_digest": DIGEST_5,
                "validity_policy_digest": DIGEST_6,
            },
        ),
        (
            "baseline_restoration_receipt",
            "baseline_restoration_receipt_1",
            {
                "candidate_live_protected_state_digest": DIGEST_1,
                "captured_checkpoint_digest": DIGEST_2,
                "captured_generation_digest": DIGEST_3,
                "captured_protected_state_digest": DIGEST_4,
                "isolated_install_operation_digest": DIGEST_5,
                "isolated_install_operation_terminal_digest": DIGEST_6,
                "live_prestate_protected_state_digest": DIGEST_1,
                "post_restoration_gate_terminal_digest": DIGEST_2,
                "post_restoration_smoke_attempt_digest": DIGEST_3,
                "post_restoration_smoke_contract_digest": DIGEST_5,
                "post_restoration_smoke_evaluation_digest": DIGEST_4,
                "phase_establishing_operation_obligation_digest": DIGEST_6,
                "prevalidated_promotion_contract_digest": DIGEST_1,
                "receipt_id": "baseline_restoration_receipt_1",
                "rehearsal_install_operation_digest": DIGEST_5,
                "rehearsal_install_operation_terminal_digest": DIGEST_6,
                "restoration_evidence_cut_digest": DIGEST_1,
                "restoration_operation_digest": DIGEST_2,
                "restoration_operation_terminal_digest": DIGEST_3,
                "restored_generation_digest": DIGEST_4,
                "restored_fence_epoch": 3,
                "restored_projection_digest": DIGEST_2,
                "restored_protected_state_digest": DIGEST_5,
                "rollback_digest": DIGEST_6,
                "target_digest": DIGEST_1,
            },
        ),
        (
            "final_service_anchor_receipt",
            "final_service_anchor_receipt_1",
            {
                "anchor_id": "private_final_service_anchor",
                "backend_provenance_digest": DIGEST_1,
                "evidence_cut_digest": DIGEST_2,
                "expires_at": "2026-08-12T10:05:00Z",
                "final_restart_operation_digest": DIGEST_3,
                "final_restart_operation_terminal_digest": DIGEST_4,
                "generation_digest": DIGEST_5,
                "issued_at": TIMESTAMP,
                "predecessor_service_anchor_receipt_digest": DIGEST_6,
                "process_epoch": "private_process_epoch_2",
                "promotion_contract_digest": DIGEST_1,
                "readiness_digest": DIGEST_2,
                "service_protected_state_digest": DIGEST_3,
                "target_digest": DIGEST_4,
            },
        ),
        (
            "composite_authority",
            "composite_authority_1",
            {
                "accepted_generation_digest": DIGEST_1,
                "active_generation_digest": DIGEST_2,
                "authorization_policy_digest": DIGEST_3,
                "contract_digest": DIGEST_4,
                "fallback_digest": DIGEST_5,
                "inventory_digest": DIGEST_6,
                "manifest_id": "private_composite_authority",
                "quorum_policy_digest": DIGEST_1,
                "recovery_policy_digest": DIGEST_2,
                "requirements_digest": DIGEST_3,
                "rollback_generation_digest": DIGEST_4,
                "rollback_registry_digest": DIGEST_5,
                "witness_roster_digest": DIGEST_6,
            },
        ),
        (
            "composite_change_set",
            "composite_change_set_1",
            {
                "authorization_action": "transition_composite_authority",
                "authorization_digest": DIGEST_1,
                "candidate_manifest_digest": DIGEST_2,
                "change_set_id": "private_composite_change_set",
                "changed_fields": ["active_generation", "fallback"],
                "coordinator_identity_digest": DIGEST_3,
                "generation_binding": {
                    "generation_digest": DIGEST_4,
                    "mode": "required_generation",
                },
                "old_manifest_digest": DIGEST_5,
                "quorum_mode": "existing",
                "rollback_manifest_digest": DIGEST_5,
                "terminal_rule": "conjunctive",
                "transition_mode": "activation",
            },
        ),
        (
            "installed_inventory",
            "installed_inventory_1",
            {
                "authorization_digest": DIGEST_1,
                "configuration_digest": DIGEST_2,
                "driver_device_digest": DIGEST_3,
                "generation_digest": DIGEST_4,
                "inventory_id": "private_installed_inventory",
                "model_identity_digests": [DIGEST_5, DIGEST_6],
                "observed_at": TIMESTAMP,
                "observer_identity_digest": DIGEST_1,
                "package_manifest_digest": DIGEST_2,
            },
        ),
        (
            "rollback_registry",
            "rollback_registry_1",
            {
                "authorization_digest": DIGEST_1,
                "established_at": TIMESTAMP,
                "registry_head_digest": DIGEST_2,
                "registry_id": "private_rollback_registry",
                "rollback_digests": [DIGEST_3, DIGEST_4],
                "selected_rollback_digest": DIGEST_4,
            },
        ),
        (
            "recovery_policy",
            "recovery_policy_1",
            {
                "authorization_digest": DIGEST_1,
                "policy_id": "private_recovery_policy",
                "recovery_contract_digests": [DIGEST_2, DIGEST_3],
                "recovery_owner_roles": ["operator", "recovery_owner"],
                "recovery_root_digest": DIGEST_4,
                "separation_policy_digest": DIGEST_5,
                "validity_policy_digest": DIGEST_6,
            },
        ),
        (
            "composite_fallback_reference",
            "composite_fallback_reference_1",
            {
                "authorization_digest": DIGEST_1,
                "committed_checkpoint_digest": DIGEST_2,
                "reference_id": "private_composite_fallback",
                "referenced_manifest_digest": DIGEST_3,
            },
        ),
        (
            "witness_roster",
            "witness_roster_1",
            {
                "roster_id": "private_witness_roster",
                "witness_identity_digests": [DIGEST_1, DIGEST_2],
            },
        ),
        (
            "quorum_policy",
            "quorum_policy_1",
            {
                "policy_id": "private_quorum_policy",
                "threshold": 2,
                "witness_roster_digest": DIGEST_1,
            },
        ),
        (
            "quorum_receipt",
            "quorum_receipt_1",
            {
                "approval_digests": [DIGEST_1, DIGEST_2],
                "approved_at": TIMESTAMP,
                "authorization_digest": DIGEST_3,
                "change_set_digest": DIGEST_4,
                "quorum_policy_digest": DIGEST_5,
                "receipt_id": "private_quorum_receipt",
                "side": "existing",
                "witness_roster_digest": DIGEST_6,
            },
        ),
        (
            "operation_requirement",
            "operation_requirement_1",
            {
                "declared_effects": [
                    {
                        "classification": "poststate_observable",
                        "effect_id": "package_database",
                        "projection_digest": DIGEST_1,
                    }
                ],
                "generation_binding_mode": "required_generation",
                "generation_binding_role": "candidate_generation",
                "generation_class": "c",
                "lifecycle_phase": "active",
                "operation_kind": "package_installation",
                "plan_digest": DIGEST_2,
                "purpose": "phase_transition",
                "realization_condition": "always",
                "recovery_contract_digest": DIGEST_3,
                "recovery_target_role": "predecessor_state",
                "requirement_id": "active_install",
                "subject_binding_role": "candidate_generation",
                "subject_kind": "generation",
                "target_digest": DIGEST_4,
                "target_id": "reference_host",
                "target_kind": "live_root",
                "terminal_validator_digest": DIGEST_5,
            },
        ),
        (
            "operation_requirement_set",
            "operation_requirement_set_1",
            {
                "operation_requirement_digests": [DIGEST_1],
                "requirements_digest": DIGEST_2,
            },
        ),
        (
            "operation_realization",
            "operation_realization_1",
            {
                "observed_prestate_digest": DIGEST_1,
                "operation_digest": DIGEST_2,
                "operation_obligation_digest": DIGEST_3,
                "operation_requirement_digest": DIGEST_4,
                "realization_id": "operation_realization_1",
                "resolved_generation_binding": {
                    "generation_digest": DIGEST_5,
                    "mode": "required_generation",
                },
                "resolved_subject_digest": DIGEST_6,
            },
        ),
        (
            "operation_realization_set",
            "operation_realization_set_1",
            {
                "operation_obligation_set_digest": DIGEST_1,
                "operation_realization_digests": [DIGEST_2],
            },
        ),
        (
            "restored_baseline_smoke_contract",
            "restored_baseline_smoke_contract_1",
            {
                "assignment_digest": DIGEST_1,
                "attestation_authorization_digest": DIGEST_2,
                "expected_outcome": "pass",
                "gate_digest": DIGEST_3,
                "restored_protected_state_digest": DIGEST_4,
                "smoke_contract_id": "restored_baseline_smoke_1",
                "target_digest": DIGEST_5,
                "validation_contract_digest": DIGEST_6,
                "validator_digest": DIGEST_1,
            },
        ),
        (
            "backend_provenance",
            "backend_provenance_1",
            {
                "authorization_digest": DIGEST_1,
                "backend_id": "lemonade_hip",
                "backend_manifest_digest": DIGEST_2,
                "configuration_digest": DIGEST_3,
                "driver_device_digest": DIGEST_4,
                "generation_digest": DIGEST_5,
                "model_identity_digest": DIGEST_6,
                "observed_at": "2026-08-12T09:56:00Z",
                "observer_identity_digest": DIGEST_1,
                "package_manifest_digest": DIGEST_2,
                "process_epoch": "process_epoch_1",
                "provenance_id": "service_epoch_1_provenance",
                "service_protected_state_digest": DIGEST_3,
                "target_digest": DIGEST_4,
            },
        ),
        (
            "service_health_observation",
            "service_health_observation_1",
            {
                "authorization_digest": DIGEST_1,
                "backend_provenance_digest": DIGEST_2,
                "generation_digest": DIGEST_3,
                "observation_id": "service_epoch_1_health",
                "observed_at": "2026-08-12T09:57:00Z",
                "observer_identity_digest": DIGEST_4,
                "process_epoch": "process_epoch_1",
                "service_protected_state_digest": DIGEST_5,
                "status": "ready",
                "target_digest": DIGEST_6,
            },
        ),
        (
            "service_anchor_receipt",
            "service_anchor_receipt_1",
            {
                "active_evidence_cut_digest": DIGEST_1,
                "active_phase_operation_terminal_digest": DIGEST_6,
                "active_promotion_contract_digest": DIGEST_2,
                "anchor_id": "active_service_anchor",
                "backend_provenance_digest": DIGEST_1,
                "establishing_operation_digest": DIGEST_3,
                "expires_at": "2026-08-12T10:05:00Z",
                "generation_digest": DIGEST_4,
                "issued_at": TIMESTAMP,
                "operation_terminal_digest": DIGEST_5,
                "process_epoch": "process_epoch_1",
                "readiness_digest": DIGEST_2,
                "service_protected_state_digest": DIGEST_6,
                "target_digest": DIGEST_1,
            },
        ),
    ],
)
def test_new_authority_records_export_no_restricted_policy_or_chain_material(
    kind: str,
    record_id: str,
    payload: dict[str, object],
) -> None:
    envelope = ControlRecord.build(
        kind=kind,
        record_id=record_id,
        payload=payload,
    ).public_envelope(opaque_reference_key=b"r" * 32)

    assert envelope.payload["public"] == {}
    wire = envelope.canonical_bytes()
    for digest in (DIGEST_1, DIGEST_2, DIGEST_3, DIGEST_4, DIGEST_5, DIGEST_6):
        assert digest.encode() not in wire


def test_signed_composite_checkpoint_exports_no_register_or_signer_material() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "change_set_digest": DIGEST_2,
        "checkpoint_id": "private_composite_checkpoint",
        "committed_at": TIMESTAMP,
        "quorum_receipt_digests": [DIGEST_2, DIGEST_3],
        "register_head_digest": DIGEST_4,
        "register_id": "private_composite_register",
        "register_observation_digest": DIGEST_5,
        "register_sequence": 7,
        "selected_manifest_digest": DIGEST_6,
        "signer_identity_digest": DIGEST_1,
    }
    record_id = "composite_authority_checkpoint_1"
    checkpoint = ControlRecord.build(
        kind="composite_authority_checkpoint",
        record_id=record_id,
        payload=payload,
        signature={
            "algorithm": "ed25519",
            "signed_digest": ControlRecord.signing_digest(
                kind="composite_authority_checkpoint",
                record_id=record_id,
                payload=payload,
            ),
            "signer_identity_digest": DIGEST_1,
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        },
    )

    wire = checkpoint.public_envelope(
        opaque_reference_key=b"r" * 32
    ).canonical_bytes()
    assert b"private_composite_register" not in wire
    assert b"private_composite_checkpoint" not in wire
    for digest in (DIGEST_1, DIGEST_2, DIGEST_3, DIGEST_4, DIGEST_5, DIGEST_6):
        assert digest.encode() not in wire


def test_operation_requirements_and_service_anchors_do_not_leak_target_roles() -> None:
    requirement = ControlRecord.build(
        kind="operation_requirement",
        record_id="operation_requirement_private_target",
        payload={
            "declared_effects": [
                {
                    "classification": "poststate_observable",
                    "effect_id": "package_database",
                    "projection_digest": DIGEST_1,
                }
            ],
            "generation_binding_mode": "required_generation",
            "generation_binding_role": "candidate_generation",
            "generation_class": "c",
            "lifecycle_phase": "active",
            "operation_kind": "package_installation",
            "plan_digest": DIGEST_2,
            "purpose": "phase_transition",
            "realization_condition": "always",
            "recovery_contract_digest": DIGEST_3,
            "recovery_target_role": "predecessor_state",
            "requirement_id": "active_install",
            "subject_binding_role": "candidate_generation",
            "subject_kind": "generation",
            "target_digest": DIGEST_4,
            "target_id": "private_reference_host",
            "target_kind": "live_root",
            "terminal_validator_digest": DIGEST_5,
        },
    )
    anchor = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service_anchor_receipt_private_target",
        payload={
            "active_evidence_cut_digest": DIGEST_1,
            "active_phase_operation_terminal_digest": DIGEST_6,
            "active_promotion_contract_digest": DIGEST_2,
            "anchor_id": "private_service_anchor",
            "backend_provenance_digest": DIGEST_1,
            "establishing_operation_digest": DIGEST_3,
            "expires_at": "2026-08-12T10:05:00Z",
            "generation_digest": DIGEST_4,
            "issued_at": TIMESTAMP,
            "operation_terminal_digest": DIGEST_5,
            "process_epoch": "private_process_epoch",
            "readiness_digest": DIGEST_2,
            "service_protected_state_digest": DIGEST_6,
            "target_digest": DIGEST_1,
        },
    )

    requirement_wire = requirement.public_envelope(
        opaque_reference_key=b"r" * 32
    ).canonical_bytes()
    anchor_wire = anchor.public_envelope(
        opaque_reference_key=b"r" * 32
    ).canonical_bytes()

    assert b"private_reference_host" not in requirement_wire
    assert b"candidate_generation" not in requirement_wire
    assert b"private_service_anchor" not in anchor_wire


def test_actor_role_and_protected_target_kind_remain_restricted() -> None:
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval_1",
        payload={
            "action": "activate_generation",
            "actor_identity_digest": DIGEST_1,
            "actor_role": "release_operator",
            "authorization_digest": DIGEST_2,
            "decided_at": TIMESTAMP,
            "decision": "approved",
            "subject_digest": DIGEST_3,
        },
    )
    protected_state = ControlRecord.build(
        kind="protected_state",
        record_id="protected_state_1",
        payload={
            "fence_epoch": 1,
            "generation_digest": DIGEST_1,
            "lifecycle_phase": "active",
            "observed_at": TIMESTAMP,
            "projection_id": "active_generation_pointer",
            "state_digest": DIGEST_2,
            "target_digest": DIGEST_3,
            "target_kind": "live_root",
        },
    )

    approval_wire = approval.public_envelope(
        opaque_reference_key=b"r" * 32
    ).canonical_bytes()
    state_wire = protected_state.public_envelope(
        opaque_reference_key=b"r" * 32
    ).canonical_bytes()

    assert b"release_operator" not in approval_wire
    assert b"live_root" not in state_wire
    assert approval.payload["actor_role"] == "release_operator"
    assert protected_state.payload["target_kind"] == "live_root"


def _attestation_payload(**changes: object) -> dict[str, object]:
    payload = {
        "actor_identity_digest": DIGEST_1,
        "actor_role": "validator",
        "assignment_digest": DIGEST_2,
        "context_digest": DIGEST_3,
        "dependency_projection_digest": DIGEST_4,
        "gate_digest": DIGEST_5,
        "observed_at": TIMESTAMP,
        "outcome": "pass",
        "raw_payload_reference_digest": DIGEST_6,
        "subject_digest": DIGEST_6,
    }
    payload.update(changes)
    return payload


def _evaluation_payload() -> dict[str, object]:
    return {
        "applicability": "applicable",
        "assignment_digest": DIGEST_1,
        "attestation_digests": [DIGEST_2],
        "context_digest": DIGEST_3,
        "dependency_projection_digest": DIGEST_4,
        "evaluated_at": TIMESTAMP,
        "outcome": "blocked",
    }


def test_opaque_reference_is_derived_instead_of_caller_selected() -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )

    envelope = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
    )

    assert envelope.payload["binding"]["opaque_ref"] == (
        "opaque_hmac_sha256:v1:"
        "8ACefUGk5QSwMHwH7yPhptItXrqiqXUMPsscwT_TmNs"
    )
    assert "private-host" not in envelope.payload["binding"]["opaque_ref"]
    assert envelope.record_id.startswith("public_envelope_sha256:v1:")
    assert len(envelope.record_id) == len("public_envelope_sha256:v1:") + 64

    with pytest.raises(TypeError):
        restricted.public_envelope(  # type: ignore[call-arg]
            envelope_id="private-host:/restricted/path",
            opaque_reference_key=b"r" * 32,
        )
    with pytest.raises(TypeError):
        restricted.public_envelope(  # type: ignore[call-arg]
            opaque_ref="opaque:v1:private-host-identity",
            opaque_reference_key=b"r" * 32,
        )


def test_public_envelope_exports_only_schema_owned_metadata_and_safe_bindings() -> None:
    restricted = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload=_attestation_payload(),
    )

    envelope = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
        commitment_key=b"k" * 32,
    )

    assert envelope.kind == "public_envelope"
    assert envelope.payload["source_kind"] == "attestation"
    assert envelope.payload["public"] == {"outcome": "pass"}
    assert envelope.payload["binding"] == {
        "keyed_commitment": (
            "hmac_sha256:"
            "90ba835600e3079298449973b6f8be4719acc3f7a0465868bdda7b8ce2b3cd54"
        ),
        "opaque_ref": (
            "opaque_hmac_sha256:v1:"
            "SRhmDFI5_A9394t8pDqRALas0zEfCt1yMvVthXHQTjU"
        ),
    }
    wire = envelope.canonical_bytes()
    assert DIGEST_1.encode() not in wire
    assert DIGEST_6.encode() not in wire
    assert restricted.digest().encode() not in wire
    assert ControlRecord.parse(wire).canonical_bytes() == wire


def test_public_envelope_accepts_each_safe_binding_independently() -> None:
    restricted = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_1",
        payload=_evaluation_payload(),
    )

    by_reference = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
    )
    by_commitment = restricted.public_envelope(
        commitment_key=b"c" * 32,
    )

    assert set(by_reference.payload["binding"]) == {"opaque_ref"}
    assert set(by_commitment.payload["binding"]) == {"keyed_commitment"}


def test_public_envelope_rejects_a_deceptive_control_record_subclass() -> None:
    restricted = ControlRecord.build(
        kind="identity",
        record_id="identity_deceptive_envelope_source",
        payload={
            "authority_digest": DIGEST_2,
            "identity_id": "deceptive-envelope-source",
            "identity_type": "principal",
            "roles": ["validator"],
        },
    )

    with pytest.raises(PrivacyEnvelopeError) as caught:
        _deceptive_restricted_record(restricted).public_envelope(
            opaque_reference_key=b"r" * 32,
        )

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_public_envelope_rejects_a_forged_exact_base_record() -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_forged_envelope_source",
        payload=_gate_payload(),
    )
    object.__setattr__(restricted, "_digest", DIGEST_6)

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(opaque_reference_key=b"r" * 32)

    assert caught.value.code is RecordErrorCode.DIGEST_MISMATCH


def test_unknown_evaluation_envelope_hides_reason_and_evidence_provenance() -> None:
    restricted = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_with_restricted_unknown_provenance",
        payload={
            **_evaluation_payload(),
            "applicability": "applicable_unknown",
            "attestation_digests": [DIGEST_2],
            "outcome": "unknown",
            "unknown_reason": "reported_unknown",
        },
    )

    envelope = restricted.public_envelope(opaque_reference_key=b"r" * 32)
    wire = envelope.canonical_bytes()

    assert envelope.payload["public"] == {
        "applicability": "applicable_unknown",
        "outcome": "unknown",
    }
    assert b"unknown_reason" not in wire
    assert b"reported_unknown" not in wire
    assert DIGEST_2.encode() not in wire


def test_retention_metadata_envelopes_do_not_expose_the_raw_record_or_lease_link(
) -> None:
    lease = ControlRecord.build(
        kind="retention_lease",
        record_id="retention_lease_1",
        payload={
            "expires_at": TIMESTAMP,
            "issued_at": "2026-08-12T09:00:00Z",
            "key_version": "evidence_key_v1",
            "lease_id": "retention_lease_1",
            "status": "active",
        },
    )
    reference = ControlRecord.build(
        kind="restricted_reference",
        record_id="restricted_reference_1",
        payload={
            "created_at": TIMESTAMP,
            "key_version": "evidence_key_v1",
            "reference_id": "restricted_reference_1",
            "restricted_record_digest": DIGEST_1,
            "retention_lease_digest": lease.digest(),
            "storage_authority_digest": DIGEST_2,
        },
    )

    lease_envelope = lease.public_envelope(opaque_reference_key=b"r" * 32)
    reference_envelope = reference.public_envelope(
        opaque_reference_key=b"r" * 32
    )

    assert lease_envelope.payload["public"] == {"status": "active"}
    assert reference_envelope.payload["public"] == {}
    for wire in (
        lease_envelope.canonical_bytes(),
        reference_envelope.canonical_bytes(),
    ):
        assert DIGEST_1.encode() not in wire
        assert lease.digest().encode() not in wire
        assert reference.digest().encode() not in wire


@pytest.mark.parametrize(
    ("opaque_reference_key", "commitment_key", "code"),
    [
        (None, None, RecordErrorCode.PRIVACY_BINDING_REQUIRED),
        (b"weak", None, RecordErrorCode.INVALID_OPAQUE_REFERENCE_KEY),
        (None, b"weak", RecordErrorCode.INVALID_COMMITMENT_KEY),
    ],
)
def test_public_envelope_fails_closed_without_a_safe_binding(
    opaque_reference_key: bytes | None,
    commitment_key: bytes | None,
    code: RecordErrorCode,
) -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(
            opaque_reference_key=opaque_reference_key,
            commitment_key=commitment_key,
        )

    assert caught.value.code is code


def test_public_envelope_kind_cannot_bypass_the_schema_owned_projection() -> None:
    with pytest.raises(PrivacyEnvelopeError) as caught:
        ControlRecord.build(
            kind="public_envelope",
            record_id="envelope_1",
            payload={"secret": "token_should_never_be_public"},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PUBLIC_ENVELOPE


def test_direct_constructor_cannot_bypass_public_envelope_validation() -> None:
    with pytest.raises(TypeError):
        ControlRecord(  # type: ignore[call-arg]
            kind="public_envelope",
            record_id="/private/host",
            payload={"secret": "token"},
            _digest="sha256:" + "0" * 64,
        )


def test_public_envelope_rejects_a_detached_signature_privacy_channel() -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )
    envelope = restricted.public_envelope(opaque_reference_key=b"r" * 32)
    document = json.loads(envelope.canonical_bytes())
    document["signature"] = {
        "private_host": "private-host",
        "private_path": "/restricted/path",
    }
    wire = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    with pytest.raises(PrivacyEnvelopeError) as caught:
        ControlRecord.parse(wire)

    assert caught.value.code is RecordErrorCode.INVALID_PUBLIC_ENVELOPE


def test_restricted_signature_is_never_copied_into_a_public_envelope() -> None:
    unsigned = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
        signature={
            "algorithm": "ed25519",
            "signed_digest": unsigned.digest(),
            "signer_identity_digest": DIGEST_6,
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        },
    )

    envelope = restricted.public_envelope(opaque_reference_key=b"r" * 32)

    assert envelope.signature is None
    assert b"signer_identity_digest" not in envelope.canonical_bytes()
