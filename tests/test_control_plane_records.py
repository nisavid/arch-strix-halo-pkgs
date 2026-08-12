from pathlib import Path
from copy import deepcopy
import json
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from control_plane import (
    MAX_NESTING_DEPTH,
    MAX_RECORD_BYTES,
    RECORD_KINDS,
    RECORD_SCHEMAS,
    CanonicalizationError,
    ControlRecord,
    ControlRecordError,
    RecordValidationError,
    RecordErrorCode,
)


EXPECTED_RECORD_KINDS = {
    "approval",
    "assignment",
    "attempt",
    "attestation",
    "atomic_evidence_cut",
    "authority_register",
    "authorization",
    "capability",
    "composite_authority",
    "composite_change_set",
    "evaluation",
    "exception",
    "fixture_role",
    "fixture_selector",
    "gate",
    "generation",
    "identity",
    "inclusion_edge",
    "intent",
    "invalidation",
    "operation",
    "predicate_proof",
    "promotion_contract",
    "promotion_obligation",
    "protected_state",
    "public_envelope",
    "readiness",
    "recovery",
    "restricted_reference",
    "retention_lease",
    "rollback",
    "requirements",
    "terminal_record",
    "validation_context",
}

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64
DIGEST_3 = "sha256:" + "3" * 64
DIGEST_4 = "sha256:" + "4" * 64
DIGEST_5 = "sha256:" + "5" * 64
DIGEST_6 = "sha256:" + "6" * 64
DIGEST_7 = "sha256:" + "7" * 64
DIGEST_8 = "sha256:" + "8" * 64
DIGEST_9 = "sha256:" + "9" * 64
TIMESTAMP = "2026-08-12T10:00:00Z"

VALID_PAYLOADS = {
    "approval": {
        "action": "activate_generation",
        "actor_identity_digest": DIGEST_1,
        "authorization_digest": DIGEST_2,
        "decided_at": TIMESTAMP,
        "decision": "approved",
        "subject_digest": DIGEST_3,
    },
    "assignment": {
        "applicability": "unconditional",
        "assignment_id": "assignment_1",
        "authorization_policy_digest": DIGEST_1,
        "context_digest": DIGEST_2,
        "dependency_projection_digest": DIGEST_3,
        "gate_digest": DIGEST_4,
        "impact": "blocking",
        "invalidation_policy_digest": DIGEST_5,
        "separation_policy_digest": DIGEST_6,
        "subject_digest": DIGEST_7,
        "validity_policy_digest": DIGEST_8,
    },
    "attempt": {
        "actor_identity_digest": DIGEST_1,
        "assignment_digest": DIGEST_2,
        "attempt_id": "attempt_1",
        "context_digest": DIGEST_3,
        "decision": "admitted",
        "intent_digest": DIGEST_4,
        "journal_sequence": 1,
        "started_at": TIMESTAMP,
    },
    "attestation": {
        "actor_identity_digest": DIGEST_1,
        "actor_role": "validator",
        "assignment_digest": DIGEST_2,
        "context_digest": DIGEST_3,
        "dependency_projection_digest": DIGEST_4,
        "gate_digest": DIGEST_5,
        "observed_at": TIMESTAMP,
        "outcome": "pass",
        "subject_digest": DIGEST_6,
    },
    "atomic_evidence_cut": {
        "accepted_generation_digest": DIGEST_1,
        "active_generation_digest": DIGEST_2,
        "attempt_digests": [DIGEST_3],
        "authority_head_digest": DIGEST_4,
        "authority_manifest_digest": DIGEST_5,
        "complete_through_sequence": 42,
        "completeness_proof_digest": DIGEST_6,
        "contract_digest": DIGEST_7,
        "evaluation_digests": [DIGEST_8],
        "fork_proof_digest": DIGEST_9,
        "generation_digest": DIGEST_3,
        "inclusion_edge_digests": [],
        "journal_head_digest": DIGEST_4,
        "phase": "prevalidated",
        "registration_set_digest": DIGEST_5,
        "target_digest": DIGEST_6,
        "target_kind": "live_root",
        "target_protected_state_digest": DIGEST_7,
    },
    "authority_register": {
        "observed_at": TIMESTAMP,
        "quorum_receipt_digests": [DIGEST_1, DIGEST_2],
        "register_id": "authority_register_1",
        "selected_manifest_digest": DIGEST_3,
        "sequence": 1,
        "status": "valid",
        "witness_roster_digest": DIGEST_4,
    },
    "authorization": {
        "action": "activate_generation",
        "approver_roles": ["operator", "witness"],
        "policy_id": "authorization_policy_1",
        "recovery_root_digest": DIGEST_1,
        "separation_policy_digest": DIGEST_2,
        "subject_kind": "generation",
        "validity_policy_digest": DIGEST_3,
    },
    "capability": {
        "authority_head_digest": DIGEST_1,
        "authorizer_digest": DIGEST_1,
        "capability_id": DIGEST_2,
        "capability_type": "operation",
        "expires_at": TIMESTAMP,
        "fence_epoch": 1,
        "intended_protected_state_digest": DIGEST_3,
        "intent_digest": DIGEST_4,
        "issued_at": "2026-08-12T09:00:00Z",
        "operation_digest": DIGEST_5,
        "operation_id": "activation_1",
        "plan_digest": DIGEST_6,
        "single_use_scope_digest": DIGEST_7,
        "status": "active",
        "subject_digest": DIGEST_8,
        "target_id": "reference_host",
        "target_kind": "live_root",
        "target_lease_digest": DIGEST_9,
    },
    "composite_authority": {
        "active_generation_digest": DIGEST_1,
        "authorization_policy_digest": DIGEST_2,
        "contract_digest": DIGEST_3,
        "fallback_digest": DIGEST_4,
        "inventory_digest": DIGEST_5,
        "manifest_id": "composite_authority_1",
        "recovery_policy_digest": DIGEST_6,
        "requirements_digest": DIGEST_7,
        "rollback_registry_digest": DIGEST_8,
        "witness_roster_digest": DIGEST_9,
    },
    "composite_change_set": {
        "authorization_digest": DIGEST_1,
        "binding_mode": "required_generation",
        "candidate_manifest_digest": DIGEST_2,
        "change_set_id": "change_set_1",
        "changed_fields": ["active_generation"],
        "coordinator_identity_digest": DIGEST_3,
        "old_manifest_digest": DIGEST_4,
        "quorum_mode": "existing",
        "rollback_manifest_digest": DIGEST_5,
        "terminal_rule": "conjunctive",
    },
    "evaluation": {
        "admissible": True,
        "applicability": "applicable",
        "assignment_digest": DIGEST_1,
        "attestation_digests": [DIGEST_2],
        "context_digest": DIGEST_3,
        "currency": "current",
        "dependency_projection_digest": DIGEST_4,
        "evaluated_at": TIMESTAMP,
        "outcome": "pass",
    },
    "exception": {
        "authorization_digest": DIGEST_1,
        "exception_id": "exception_1",
        "expires_at": TIMESTAMP,
        "owner_identity_digest": DIGEST_2,
        "reason_code": "controlled_kokoro_realization",
        "scope_digest": DIGEST_3,
        "status": "active",
    },
    "fixture_role": {
        "api_path": "vllm.offline",
        "assertion_digest": DIGEST_1,
        "backend_attribution": "vllm_rocm",
        "capability_id": "offline_text",
        "corpus_digest": DIGEST_2,
        "fixture_format": "safetensors",
        "input_digest": DIGEST_3,
        "license_class": "public",
        "modality": "text",
        "offline": True,
        "resource_envelope_digest": DIGEST_4,
        "role_id": "vllm_offline_text",
        "tolerance_digest": DIGEST_5,
    },
    "fixture_selector": {
        "access_class": "public",
        "artifact_digests": [DIGEST_1, DIGEST_2],
        "closure_digest": DIGEST_3,
        "fixture_format": "safetensors",
        "license_digest": DIGEST_4,
        "provider": "huggingface",
        "revision": "0123456789abcdef",
        "role_digest": DIGEST_5,
        "selector_id": "qwen_text_fixture",
    },
    "gate": {
        "assertion_digest": DIGEST_1,
        "evidence_shape_digest": DIGEST_2,
        "fixture_role_digest": DIGEST_3,
        "gate_id": "gate_1",
        "label": "Control schema validation",
        "validator_digest": DIGEST_4,
    },
    "generation": {
        "artifact_digests": [DIGEST_1, DIGEST_2],
        "generation_id": "generation_c",
        "input_closure_digest": DIGEST_3,
        "manifest_digest": DIGEST_4,
        "generation_class": "c",
    },
    "identity": {
        "authority_digest": DIGEST_1,
        "identity_id": "validator_1",
        "identity_type": "principal",
    },
    "inclusion_edge": {
        "active_contract_digest": DIGEST_1,
        "approval_digest": DIGEST_2,
        "artifact_digests": [DIGEST_3, DIGEST_4],
        "assignment_digests": [DIGEST_5],
        "generation_digest": DIGEST_6,
        "inclusion_edge_id": "preassembly_to_generation_c",
        "preassembly_context_digest": DIGEST_7,
        "preassembly_evaluation_digests": [DIGEST_8],
        "preassembly_profile_digest": DIGEST_9,
        "source_closure_digest": DIGEST_4,
        "verified_at": TIMESTAMP,
        "verifier_identity_digest": DIGEST_3,
    },
    "intent": {
        "actor_identity_digest": DIGEST_1,
        "assignment_digest": DIGEST_2,
        "context_digest": DIGEST_3,
        "intent_id": "gate_intent_1",
        "intent_type": "gate_occurrence",
        "journal_sequence": 1,
        "registered_at": TIMESTAMP,
        "subject_digest": DIGEST_4,
    },
    "invalidation": {
        "affected_evaluation_digests": [DIGEST_1],
        "dependency_key": "source:control_plane",
        "episode_id": "invalidation_1",
        "event_digest": DIGEST_2,
        "opened_at": TIMESTAMP,
        "status": "open",
    },
    "operation": {
        "authority_head_digest": DIGEST_1,
        "declared_effects": [
            {
                "classification": "poststate_observable",
                "effect_id": "package_database",
                "projection_digest": DIGEST_9,
            },
            {
                "classification": "forbidden_transient",
                "effect_id": "mixed_endpoint",
                "projection_digest": DIGEST_8,
            },
        ],
        "expected_protected_state_digest": DIGEST_2,
        "generation_class": "c",
        "generation_binding": {
            "generation_digest": DIGEST_9,
            "mode": "required_generation",
        },
        "intended_protected_state_digest": DIGEST_3,
        "intent_digest": DIGEST_3,
        "lifecycle_phase": "active",
        "operation_id": "activation_1",
        "operation_kind": "package_installation",
        "plan_digest": DIGEST_4,
        "recovery_contract_digest": DIGEST_5,
        "recovery_target_digest": DIGEST_6,
        "rollback_contract_digest": DIGEST_7,
        "subject_digest": DIGEST_9,
        "subject_kind": "generation",
        "target_id": "reference_host",
        "target_kind": "live_root",
        "terminal_validator_digest": DIGEST_8,
    },
    "predicate_proof": {
        "actor_identity_digest": DIGEST_1,
        "actor_role": "validator",
        "assignment_digest": DIGEST_2,
        "context_digest": DIGEST_3,
        "dependency_projection_digest": DIGEST_4,
        "gate_digest": DIGEST_5,
        "is_applicable": False,
        "observed_at": TIMESTAMP,
        "predicate_digest": DIGEST_6,
        "subject_digest": DIGEST_7,
    },
    "promotion_contract": {
        "contract_id": "w0_prevalidated_contract",
        "expected_accepted_generation_digest": DIGEST_1,
        "expected_active_generation_digest": DIGEST_2,
        "generation_digest": DIGEST_3,
        "obligation_digests": [DIGEST_4, DIGEST_5],
        "phase": "prevalidated",
        "requirements_digest": DIGEST_6,
        "target_digest": DIGEST_7,
        "target_kind": "live_root",
        "target_protected_state_digest": DIGEST_8,
    },
    "promotion_obligation": {
        "assignment_digest": DIGEST_1,
        "impact": "blocking",
        "obligation_id": "w0_control_plane",
        "occurrence_digest": DIGEST_2,
    },
    "protected_state": {
        "fence_epoch": 1,
        "generation_digest": DIGEST_1,
        "observed_at": TIMESTAMP,
        "projection_id": "active_generation_pointer",
        "state_digest": DIGEST_2,
        "target_digest": DIGEST_3,
    },
    "readiness": {
        "generation_digest": DIGEST_1,
        "manifest_digest": DIGEST_2,
        "observation_digests": [DIGEST_3, DIGEST_4],
        "observed_at": TIMESTAMP,
        "status": "ready",
        "target_digest": DIGEST_5,
    },
    "recovery": {
        "authorization_digest": DIGEST_1,
        "destination_generation_digest": DIGEST_2,
        "exact_state_snapshot_digest": DIGEST_3,
        "generation_binding": {
            "generation_digest": DIGEST_7,
            "mode": "required_generation",
        },
        "incident_digest": DIGEST_4,
        "origin_generation_digest": DIGEST_7,
        "recovery_id": "recovery_1",
        "target_digest": DIGEST_5,
        "terminal_gate_digest": DIGEST_6,
    },
    "restricted_reference": {
        "created_at": TIMESTAMP,
        "key_version": "evidence_key_v1",
        "reference_id": "restricted_reference_1",
        "restricted_record_digest": DIGEST_1,
        "retention_lease_digest": DIGEST_2,
        "storage_authority_digest": DIGEST_3,
    },
    "retention_lease": {
        "expires_at": TIMESTAMP,
        "issued_at": "2026-08-12T09:00:00Z",
        "key_version": "evidence_key_v1",
        "lease_id": "retention_lease_1",
        "restricted_reference_digest": DIGEST_1,
        "status": "active",
    },
    "rollback": {
        "destination_generation_digest": DIGEST_1,
        "generation_binding": {
            "generation_digest": DIGEST_3,
            "mode": "required_generation",
        },
        "operation_digest": DIGEST_2,
        "origin_generation_digest": DIGEST_3,
        "rollback_id": "rollback_1",
        "target_digest": DIGEST_4,
        "terminal_gate_digest": DIGEST_5,
    },
    "requirements": {
        "approval_digest": DIGEST_1,
        "effective_at": TIMESTAMP,
        "requirements_definition_digest": DIGEST_2,
        "requirement_digests": [DIGEST_3, DIGEST_4],
        "requirements_id": "w0_convergence_requirements",
        "requirements_version": 1,
    },
    "terminal_record": {
        "assignment_digest": DIGEST_1,
        "attempt_digest": DIGEST_2,
        "completed_at": TIMESTAMP,
        "journal_sequence": 3,
        "outcome": "succeeded",
        "poststate_digest": DIGEST_4,
        "terminal_type": "gate_attempt",
        "validator_attestation_digests": [DIGEST_5],
    },
    "validation_context": {
        "assignments_digest": DIGEST_1,
        "context_id": "active_contract_context_1",
        "context_type": "active_contract",
        "contract_digest": DIGEST_2,
        "generation_digest": DIGEST_3,
        "requirements_digest": DIGEST_4,
    },
}


def test_identity_family_has_a_closed_semantic_payload_schema() -> None:
    valid = {
        "authority_digest": DIGEST_1,
        "identity_id": "validator_1",
        "identity_type": "principal",
    }

    assert ControlRecord.build(
        kind="identity",
        record_id="identity_record_1",
        payload=valid,
    ).payload["identity_id"] == "validator_1"

    invalid_payloads = [
        {"identity_id": "validator_1", "identity_type": "principal"},
        {**valid, "hostname": "private-host"},
        {**valid, "authority_digest": "sha256:not-a-digest"},
    ]
    for payload in invalid_payloads:
        with pytest.raises(RecordValidationError):
            ControlRecord.build(
                kind="identity",
                record_id="identity_record_1",
                payload=payload,
            )

    schema = RECORD_SCHEMAS["identity"]
    assert set(schema.required_fields) == {
        "authority_digest",
        "identity_id",
        "identity_type",
    }
    assert set(schema.optional_fields) == {"roles"}


@pytest.mark.parametrize("kind", sorted(EXPECTED_RECORD_KINDS - {"public_envelope"}))
def test_each_restricted_record_family_has_a_closed_typed_payload(kind: str) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    schema = RECORD_SCHEMAS[kind]

    record = ControlRecord.build(
        kind=kind,
        record_id=f"{kind}_record_1",
        payload=payload,
    )

    assert record.kind == kind
    assert schema.required_fields

    missing = deepcopy(payload)
    del missing[next(iter(schema.required_fields))]
    with pytest.raises(RecordValidationError) as caught_missing:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload=missing,
        )
    assert caught_missing.value.code is RecordErrorCode.MISSING_PAYLOAD_FIELD

    with pytest.raises(RecordValidationError) as caught_unknown:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload={**payload, "unregistered_field": "value"},
        )
    assert caught_unknown.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


@pytest.mark.parametrize("kind", sorted(EXPECTED_RECORD_KINDS - {"public_envelope"}))
def test_each_restricted_record_family_rejects_malformed_typed_digests(
    kind: str,
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    schema = RECORD_SCHEMAS[kind]
    digest_field = next(
        field
        for field, field_schema in schema.required_fields.items()
        if field_schema.kind.value in {"digest", "digest_list"}
    )
    payload[digest_field] = (
        ["sha256:not-a-digest"]
        if schema.required_fields[digest_field].kind.value == "digest_list"
        else "sha256:not-a-digest"
    )

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_DIGEST


@pytest.mark.parametrize(
    ("kind", "changes"),
    [
        ("assignment", {"predicate_digest": DIGEST_9}),
        (
            "assignment",
            {"applicability": "conditional", "predicate_digest": None},
        ),
        ("attempt", {"journal_sequence": 0}),
        ("intent", {"assignment_digest": None}),
        ("intent", {"journal_sequence": 0}),
        (
            "intent",
            {
                "assignment_digest": None,
                "intent_type": "critical_operation",
                "operation_plan_digest": None,
            },
        ),
        ("invalidation", {"closed_at": TIMESTAMP}),
        ("invalidation", {"status": "closed", "closed_at": None}),
        ("evaluation", {"currency": "stale", "admissible": True}),
        (
            "evaluation",
            {"applicability": "applicable_unknown", "outcome": "pass"},
        ),
        (
            "evaluation",
            {
                "applicability": "not_applicable",
                "attestation_digests": [],
                "outcome": "not_applicable",
            },
        ),
        (
            "evaluation",
            {"predicate_proof_digest": DIGEST_9},
        ),
        (
            "evaluation",
            {
                "applicability": "applicable_unknown",
                "attestation_digests": [],
                "outcome": "unknown",
                "predicate_proof_digest": DIGEST_9,
            },
        ),
        (
            "validation_context",
            {"profile_digest": DIGEST_9},
        ),
        (
            "validation_context",
            {
                "artifact_digests": [DIGEST_8],
                "context_type": "preassembly_profile",
                "contract_digest": None,
                "generation_digest": None,
                "profile_digest": DIGEST_9,
                "source_closure_digest": None,
            },
        ),
        (
            "authority_register",
            {"selected_manifest_digest": None},
        ),
        (
            "authority_register",
            {"status": "absent"},
        ),
        (
            "composite_change_set",
            {"changed_fields": ["recovery_policy"], "quorum_mode": "existing"},
        ),
        (
            "retention_lease",
            {"expires_at": "2026-08-12T08:00:00Z"},
        ),
        ("requirements", {"requirements_version": 0}),
        ("requirements", {"supersedes_requirements_digest": DIGEST_9}),
        (
            "requirements",
            {"requirements_version": 2},
        ),
        (
            "inclusion_edge",
            {"active_contract_digest": DIGEST_7},
        ),
        ("atomic_evidence_cut", {"complete_through_sequence": 0}),
        ("terminal_record", {"journal_sequence": 0}),
        ("terminal_record", {"operation_digest": DIGEST_3}),
        (
            "terminal_record",
            {
                "assignment_digest": None,
                "attempt_digest": None,
                "terminal_type": "critical_operation",
            },
        ),
        (
            "recovery",
            {
                "generation_binding": {
                    "generation_digest": DIGEST_6,
                    "mode": "required_generation",
                }
            },
        ),
        (
            "rollback",
            {
                "generation_binding": {
                    "generation_digest": DIGEST_6,
                    "mode": "required_generation",
                }
            },
        ),
        (
            "rollback",
            {"generation_binding": {"mode": "no_generation"}},
        ),
        (
            "operation",
            {"intended_protected_state_digest": DIGEST_2},
        ),
        (
            "operation",
            {
                "generation_binding": {
                    "mode": "required_generation",
                }
            },
        ),
        (
            "operation",
            {
                "generation_binding": {
                    "generation_digest": DIGEST_9,
                    "mode": "no_generation",
                }
            },
        ),
        (
            "operation",
            {
                "declared_effects": [
                    {
                        "classification": "poststate_observable",
                        "effect_id": "package_database",
                        "projection_digest": DIGEST_9,
                    },
                    {
                        "classification": "admissible",
                        "effect_id": "package_database",
                        "projection_digest": DIGEST_8,
                    },
                ]
            },
        ),
        (
            "operation",
            {
                "generation_class": "b0",
                "lifecycle_phase": "published",
                "operation_kind": "repository_publication",
                "target_kind": "package_repository",
            },
        ),
        (
            "operation",
            {
                "generation_binding": {"mode": "no_generation"},
                "generation_class": "b0",
                "lifecycle_phase": "captured",
                "operation_kind": "composite_authority_transition",
                "subject_kind": "composite_authority",
                "target_kind": "composite_register",
            },
        ),
        ("operation", {"lifecycle_phase": "published"}),
        ("capability", {"fence_epoch": 0}),
        (
            "capability",
            {"expires_at": "2026-08-12T09:00:00Z"},
        ),
    ],
)
def test_variant_records_reject_semantically_incoherent_payloads(
    kind: str,
    changes: dict[str, object],
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    for field, value in changes.items():
        if value is None:
            payload.pop(field, None)
        else:
            payload[field] = value

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_operation_and_capability_bind_the_complete_authority_coordinates() -> None:
    operation_schema = RECORD_SCHEMAS["operation"]
    capability_schema = RECORD_SCHEMAS["capability"]

    assert set(operation_schema.required_fields) == {
        "authority_head_digest",
        "declared_effects",
        "expected_protected_state_digest",
        "generation_class",
        "generation_binding",
        "intended_protected_state_digest",
        "intent_digest",
        "lifecycle_phase",
        "operation_id",
        "operation_kind",
        "plan_digest",
        "recovery_contract_digest",
        "recovery_target_digest",
        "subject_digest",
        "subject_kind",
        "target_id",
        "target_kind",
        "terminal_validator_digest",
    }
    assert set(operation_schema.optional_fields) == {
        "rollback_contract_digest",
    }
    assert set(capability_schema.required_fields) == {
        "authority_head_digest",
        "authorizer_digest",
        "capability_id",
        "capability_type",
        "expires_at",
        "fence_epoch",
        "intended_protected_state_digest",
        "intent_digest",
        "issued_at",
        "operation_digest",
        "operation_id",
        "plan_digest",
        "single_use_scope_digest",
        "status",
        "subject_digest",
        "target_id",
        "target_kind",
        "target_lease_digest",
    }
    assert set(capability_schema.optional_fields) == {
        "predecessor_failure_record_digest",
        "predecessor_fence_epoch",
        "predecessor_operation_id",
        "recovery_contract_digest",
        "recovery_owner_role",
    }

    operation = ControlRecord.build(
        kind="operation",
        record_id="operation_record_1",
        payload=VALID_PAYLOADS["operation"],
    )
    capability = ControlRecord.build(
        kind="capability",
        record_id="capability_record_1",
        payload=VALID_PAYLOADS["capability"],
    )

    assert operation.payload["operation_kind"] == "package_installation"
    assert operation.payload["generation_binding"] == {
        "generation_digest": DIGEST_9,
        "mode": "required_generation",
    }
    assert operation.payload["declared_effects"][0]["classification"] == (
        "poststate_observable"
    )
    assert capability.payload["single_use_scope_digest"] == DIGEST_7


def test_recovery_capability_binds_the_failed_terminal_and_predecessor_fence() -> None:
    recovery_payload = {
        **VALID_PAYLOADS["capability"],
        "capability_type": "recovery",
        "fence_epoch": 2,
        "predecessor_failure_record_digest": DIGEST_1,
        "predecessor_fence_epoch": 1,
        "predecessor_operation_id": "activation_0",
        "recovery_contract_digest": DIGEST_2,
        "recovery_owner_role": "recovery_owner",
    }

    recovery = ControlRecord.build(
        kind="capability",
        record_id="recovery_capability_record_1",
        payload=recovery_payload,
    )

    assert recovery.payload["predecessor_fence_epoch"] == 1
    with pytest.raises(RecordValidationError) as missing_failure:
        ControlRecord.build(
            kind="capability",
            record_id="recovery_capability_record_2",
            payload={
                key: value
                for key, value in recovery_payload.items()
                if key != "predecessor_failure_record_digest"
            },
        )
    with pytest.raises(RecordValidationError) as stale_fence:
        ControlRecord.build(
            kind="capability",
            record_id="recovery_capability_record_3",
            payload={**recovery_payload, "predecessor_fence_epoch": 2},
        )

    assert missing_failure.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS
    assert stale_fence.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_attempt_and_terminal_records_form_a_one_way_content_addressed_dag() -> None:
    attempt_schema = RECORD_SCHEMAS["attempt"]

    assert set(attempt_schema.optional_fields) == set()
    with pytest.raises(RecordValidationError) as terminal_decision:
        ControlRecord.build(
            kind="attempt",
            record_id="attempt_record_1",
            payload={**VALID_PAYLOADS["attempt"], "decision": "terminal"},
        )
    with pytest.raises(RecordValidationError) as reverse_reference:
        ControlRecord.build(
            kind="attempt",
            record_id="attempt_record_1",
            payload={**VALID_PAYLOADS["attempt"], "terminal_digest": DIGEST_9},
        )

    assert terminal_decision.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD
    assert reverse_reference.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_requirements_and_inclusion_edge_bind_the_accepted_evidence_model() -> None:
    requirements_schema = RECORD_SCHEMAS["requirements"]
    edge_schema = RECORD_SCHEMAS["inclusion_edge"]

    assert set(requirements_schema.required_fields) == {
        "approval_digest",
        "effective_at",
        "requirement_digests",
        "requirements_definition_digest",
        "requirements_id",
        "requirements_version",
    }
    assert set(requirements_schema.optional_fields) == {
        "supersedes_requirements_digest"
    }
    assert set(edge_schema.required_fields) == {
        "active_contract_digest",
        "approval_digest",
        "artifact_digests",
        "assignment_digests",
        "generation_digest",
        "inclusion_edge_id",
        "preassembly_context_digest",
        "preassembly_evaluation_digests",
        "preassembly_profile_digest",
        "source_closure_digest",
        "verified_at",
        "verifier_identity_digest",
    }

    requirements = ControlRecord.build(
        kind="requirements",
        record_id="requirements_record_1",
        payload=VALID_PAYLOADS["requirements"],
    )
    edge = ControlRecord.build(
        kind="inclusion_edge",
        record_id="inclusion_edge_record_1",
        payload=VALID_PAYLOADS["inclusion_edge"],
    )

    assert requirements.payload["requirements_version"] == 1
    assert edge.payload["preassembly_evaluation_digests"] == (DIGEST_8,)


def test_promotion_records_bind_total_obligations_and_an_atomic_evidence_cut() -> None:
    obligation_schema = RECORD_SCHEMAS["promotion_obligation"]
    contract_schema = RECORD_SCHEMAS["promotion_contract"]
    cut_schema = RECORD_SCHEMAS["atomic_evidence_cut"]

    assert set(obligation_schema.required_fields) == {
        "assignment_digest",
        "impact",
        "obligation_id",
        "occurrence_digest",
    }
    assert set(contract_schema.required_fields) == {
        "contract_id",
        "expected_accepted_generation_digest",
        "expected_active_generation_digest",
        "generation_digest",
        "obligation_digests",
        "phase",
        "requirements_digest",
        "target_digest",
        "target_kind",
        "target_protected_state_digest",
    }
    assert set(cut_schema.required_fields) == set(
        VALID_PAYLOADS["atomic_evidence_cut"]
    )

    obligation = ControlRecord.build(
        kind="promotion_obligation",
        record_id="promotion_obligation_record_1",
        payload=VALID_PAYLOADS["promotion_obligation"],
    )
    contract = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion_contract_record_1",
        payload=VALID_PAYLOADS["promotion_contract"],
    )
    cut = ControlRecord.build(
        kind="atomic_evidence_cut",
        record_id="atomic_evidence_cut_record_1",
        payload=VALID_PAYLOADS["atomic_evidence_cut"],
    )

    assert obligation.payload["impact"] == "blocking"
    assert contract.payload["obligation_digests"] == (DIGEST_4, DIGEST_5)
    assert cut.payload["inclusion_edge_digests"] == ()


def test_terminal_records_use_closed_gate_and_operation_variants() -> None:
    gate_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="gate_terminal_record_1",
        payload=VALID_PAYLOADS["terminal_record"],
    )
    operation_payload = deepcopy(VALID_PAYLOADS["terminal_record"])
    operation_payload.pop("assignment_digest")
    operation_payload.pop("attempt_digest")
    operation_payload["operation_digest"] = DIGEST_3
    operation_payload["terminal_type"] = "critical_operation"
    operation_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="operation_terminal_record_1",
        payload=operation_payload,
    )

    assert gate_terminal.payload["terminal_type"] == "gate_attempt"
    assert "operation_digest" not in gate_terminal.payload
    assert operation_terminal.payload["terminal_type"] == "critical_operation"
    assert "assignment_digest" not in operation_terminal.payload


def test_not_applicable_evaluation_binds_one_canonical_predicate_proof() -> None:
    proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="predicate_proof_record_1",
        payload=VALID_PAYLOADS["predicate_proof"],
    )
    payload = deepcopy(VALID_PAYLOADS["evaluation"])
    payload.update(
        {
            "admissible": True,
            "applicability": "not_applicable",
            "attestation_digests": [],
            "outcome": "not_applicable",
            "predicate_proof_digest": proof.digest(),
        }
    )

    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_record_1",
        payload=payload,
    )

    assert evaluation.payload["predicate_proof_digest"] == proof.digest()

    payload["attestation_digests"] = [DIGEST_2]
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="evaluation",
            record_id="evaluation_record_2",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_current_failure_can_remain_admissible_for_advisory_assignment_policy() -> None:
    payload = deepcopy(VALID_PAYLOADS["evaluation"])
    payload["outcome"] = "fail"

    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_record_1",
        payload=payload,
    )

    assert evaluation.payload["admissible"] is True
    assert evaluation.payload["outcome"] == "fail"


def test_record_builds_a_known_canonical_v1_vector() -> None:
    record = ControlRecord.build(
        kind="identity",
        record_id="record_1",
        payload={
            "authority_digest": DIGEST_1,
            "identity_id": "validator_1",
            "identity_type": "principal",
        },
    )
    assert record.digest() == (
        "sha256:763780be1fe20d7b27cde338dd154f5804f891903fae148f74c726fe148e7064"
    )
    assert record.canonical_bytes() == (
        b'{"digest":"sha256:763780be1fe20d7b27cde338dd154f5804f891903fae148f74c726fe148e7064",'
        b'"kind":"identity","payload":{"authority_digest":"sha256:'
        b'1111111111111111111111111111111111111111111111111111111111111111",'
        b'"identity_id":"validator_1","identity_type":"principal"},'
        b'"record_id":"record_1",'
        b'"schema":"arch_strix_halo.control_record","schema_version":1}'
    )


def test_record_kind_registry_is_closed_and_covers_the_w0_model() -> None:
    assert RECORD_KINDS == EXPECTED_RECORD_KINDS
    for kind in EXPECTED_RECORD_KINDS - {"public_envelope"}:
        assert ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_1",
            payload=VALID_PAYLOADS[kind],
        ).kind == kind

    with pytest.raises(ControlRecordError) as caught:
        ControlRecord.build(kind="chat_message", record_id="message_1", payload={})

    assert caught.value.code is RecordErrorCode.UNSUPPORTED_KIND


def _nested_payload(depth: int) -> dict[str, object]:
    value: object = "leaf"
    for _ in range(depth):
        value = {"level": value}
    return {"root": value}


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"badKey": "value"}, RecordErrorCode.INVALID_KEY),
        ({1: "value"}, RecordErrorCode.INVALID_KEY),
        ({"bad_value": 1.5}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"bad_value": float("nan")}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"bad_value": 2**63}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"bad_value": (1, 2)}, RecordErrorCode.INVALID_TYPE),
        ({"bad_value": "unsafe\ud800"}, RecordErrorCode.UNSAFE_UNICODE),
        ({"bad_value": "right-to-left\u202e"}, RecordErrorCode.UNSAFE_UNICODE),
        (
            _nested_payload(MAX_NESTING_DEPTH + 1),
            RecordErrorCode.EXCESSIVE_DEPTH,
        ),
    ],
)
def test_build_rejects_values_without_a_safe_canonical_v1_form(
    payload: dict[object, object],
    code: RecordErrorCode,
) -> None:
    with pytest.raises(CanonicalizationError) as caught:
        ControlRecord.build(
            kind="gate",
            record_id="record_1",
            payload={**deepcopy(VALID_PAYLOADS["gate"]), **payload},
        )

    assert caught.value.code is code


def test_build_rejects_a_cyclic_payload_and_boolean_record_id() -> None:
    cyclic = deepcopy(VALID_PAYLOADS["gate"])
    cyclic["cycle"] = cyclic

    with pytest.raises(CanonicalizationError) as caught_cycle:
        ControlRecord.build(kind="gate", record_id="record_1", payload=cyclic)
    with pytest.raises(CanonicalizationError) as caught_id:
        ControlRecord.build(  # type: ignore[arg-type]
            kind="gate",
            record_id=True,
            payload=VALID_PAYLOADS["gate"],
        )

    assert caught_cycle.value.code is RecordErrorCode.CYCLIC_VALUE
    assert caught_id.value.code is RecordErrorCode.INVALID_TYPE


def test_built_record_is_detached_from_caller_mutation() -> None:
    payload = deepcopy(VALID_PAYLOADS["gate"])
    payload["dependency_keys"] = ["source:first"]
    record = ControlRecord.build(kind="gate", record_id="record_1", payload=payload)
    before = record.canonical_bytes()

    payload["dependency_keys"].append("source:second")  # type: ignore[union-attr]

    assert record.canonical_bytes() == before


def test_parse_round_trips_canonical_bytes_and_signature_is_not_hashed() -> None:
    unsigned = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload=VALID_PAYLOADS["attestation"],
    )
    signed = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload=VALID_PAYLOADS["attestation"],
        signature={
            "algorithm": "ed25519",
            "signed_digest": unsigned.digest(),
            "signer_identity_digest": DIGEST_9,
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        },
    )

    parsed = ControlRecord.parse(signed.canonical_bytes())

    assert signed.digest() == unsigned.digest()
    assert parsed.canonical_bytes() == signed.canonical_bytes()
    assert parsed.signature == signed.signature


@pytest.mark.parametrize(
    "signature",
    [
        {
            "algorithm": "ed25519",
            "private_path": "/restricted/path",
            "signed_digest": DIGEST_1,
            "signer_identity_digest": DIGEST_9,
            "value": "not_a_signature",
        },
        {
            "algorithm": "rsa",
            "signed_digest": DIGEST_1,
            "signer_identity_digest": DIGEST_9,
            "value": "not_a_signature",
        },
        {
            "algorithm": "ed25519",
            "signed_digest": DIGEST_1,
            "signer_identity_digest": DIGEST_9,
            "value": "not_a_signature",
        },
    ],
)
def test_detached_signature_has_a_closed_core_binding(
    signature: dict[str, str],
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="attestation",
            record_id="attestation_1",
            payload=VALID_PAYLOADS["attestation"],
            signature=signature,
        )

    assert caught.value.code is RecordErrorCode.INVALID_SIGNATURE


def _valid_wire(**overrides: object) -> bytes:
    record = ControlRecord.build(
        kind="gate",
        record_id="record_1",
        payload=VALID_PAYLOADS["gate"],
    )
    document = json.loads(record.canonical_bytes())
    document.update(overrides)
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("wire", "code"),
    [
        (_valid_wire(schema="wrong.schema"), RecordErrorCode.UNSUPPORTED_SCHEMA),
        (_valid_wire(schema_version=2), RecordErrorCode.UNSUPPORTED_VERSION),
        (_valid_wire(schema_version=True), RecordErrorCode.UNSUPPORTED_VERSION),
        (_valid_wire(kind="chat_message"), RecordErrorCode.UNSUPPORTED_KIND),
        (_valid_wire(extra="value"), RecordErrorCode.UNKNOWN_FIELD),
        (
            _valid_wire(digest="sha256:" + "0" * 64),
            RecordErrorCode.DIGEST_MISMATCH,
        ),
        (b"{\"schema\":\"x\",\"schema\":\"y\"}", RecordErrorCode.DUPLICATE_KEY),
        (b"{\"payload\":{\"value\":1.5}}", RecordErrorCode.UNSUPPORTED_NUMBER),
        (b"{\"payload\":{\"value\":NaN}}", RecordErrorCode.UNSUPPORTED_NUMBER),
        (
            b'{"payload":{"value":9999999999999999999999999999999999999999}}',
            RecordErrorCode.UNSUPPORTED_NUMBER,
        ),
        (b"\xff", RecordErrorCode.INVALID_JSON),
    ],
)
def test_parse_rejects_invalid_or_unsupported_wire_records(
    wire: bytes,
    code: RecordErrorCode,
) -> None:
    with pytest.raises(ControlRecordError) as caught:
        ControlRecord.parse(wire)

    assert caught.value.code is code


def test_parse_rejects_missing_fields_and_noncanonical_json() -> None:
    valid = ControlRecord.build(
        kind="gate",
        record_id="record_1",
        payload={**VALID_PAYLOADS["gate"], "label": "Café"},
    ).canonical_bytes()
    missing = json.loads(valid)
    del missing["record_id"]
    decomposed = valid.replace("Café".encode(), "Cafe\u0301".encode())

    cases = [
        (
            json.dumps(missing, separators=(",", ":"), sort_keys=True).encode(),
            RecordErrorCode.MISSING_FIELD,
        ),
        (b" " + valid, RecordErrorCode.NON_CANONICAL_JSON),
        (decomposed, RecordErrorCode.NON_CANONICAL_JSON),
    ]
    for wire, code in cases:
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.parse(wire)
        assert caught.value.code is code


def test_parse_rejects_oversized_input_before_decoding() -> None:
    with pytest.raises(CanonicalizationError) as caught:
        ControlRecord.parse(b" " * (MAX_RECORD_BYTES + 1))

    assert caught.value.code is RecordErrorCode.EXCESSIVE_SIZE
