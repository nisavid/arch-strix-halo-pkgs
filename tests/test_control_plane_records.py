import json
import sys
from copy import deepcopy
from pathlib import Path

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
    RecordErrorCode,
    RecordValidationError,
)

EXPECTED_RECORD_KINDS = {
    "acceptance_request",
    "approval",
    "assignment",
    "assignment_set",
    "attempt",
    "attestation",
    "atomic_evidence_cut",
    "authority_register",
    "authorization",
    "baseline_restoration_receipt",
    "backend_provenance",
    "capability",
    "composite_authority",
    "composite_authority_checkpoint",
    "composite_change_set",
    "composite_fallback_reference",
    "dependency_projection",
    "evidence_currency_proof",
    "evaluation",
    "exception",
    "fixture_role",
    "fixture_selector",
    "final_service_anchor_receipt",
    "gate",
    "generation",
    "identity",
    "inclusion_edge",
    "intent",
    "invalidation",
    "invalidation_policy",
    "invalidation_stream_checkpoint",
    "installed_inventory",
    "operation",
    "operation_attestation",
    "operation_obligation",
    "operation_obligation_set",
    "operation_requirement",
    "operation_requirement_set",
    "operation_realization",
    "operation_realization_set",
    "predicate_proof",
    "promotion_authority_proof",
    "lifecycle_checkpoint",
    "promotion_contract",
    "promotion_obligation",
    "protected_state",
    "public_envelope",
    "quorum_policy",
    "quorum_receipt",
    "readiness",
    "recovery",
    "recovery_policy",
    "restricted_reference",
    "retention_lease",
    "restored_baseline_smoke_contract",
    "rollback",
    "rollback_registry",
    "separation_policy",
    "service_anchor_receipt",
    "service_health_observation",
    "requirements",
    "terminal_record",
    "trusted_time_observation",
    "validation_contract",
    "validation_context",
    "validity_policy",
    "witness_roster",
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


class RegisteredKindImpostor(str):
    """Compare as a registered kind while retaining hostile wire text."""

    def __hash__(self) -> int:
        return hash("identity")

    def __eq__(self, other: object) -> bool:
        return other == "identity"


class PublicEnvelopeKindImpostor(str):
    """Compare as the internal-only kind while retaining hostile wire text."""

    def __hash__(self) -> int:
        return hash("public_envelope")

    def __eq__(self, other: object) -> bool:
        return other == "public_envelope"


class EncodeOverridingWire(str):
    """Raise if record parsing dispatches through subclass string behavior."""

    def encode(self, *args: object, **kwargs: object) -> bytes:
        del args, kwargs
        raise AssertionError("parse must not invoke a string subclass encode")


class DecodeOverridingWire(bytes):
    """Raise if record parsing dispatches through subclass bytes behavior."""

    def decode(self, *args: object, **kwargs: object) -> str:
        del args, kwargs
        raise AssertionError("parse must not invoke a bytes subclass decode")


class DeceptiveControlRecord(ControlRecord):
    """Expose a kind other than the canonical core stored by the base class."""

    def __getattribute__(self, name: str) -> object:
        if name == "kind":
            return "validation_context"
        return super().__getattribute__(name)


VALID_PAYLOADS = {
    "acceptance_request": {
        "acceptance_authorization_digest": DIGEST_1,
        "atomic_evidence_cut_digest": DIGEST_2,
        "final_service_anchor_receipt_digest": DIGEST_8,
        "generation_digest": DIGEST_3,
        "predecessor_checkpoint_digest": DIGEST_4,
        "promotion_contract_digest": DIGEST_5,
        "requested_at": TIMESTAMP,
        "target_digest": DIGEST_6,
        "target_protected_state_digest": DIGEST_7,
    },
    "approval": {
        "action": "activate_generation",
        "actor_identity_digest": DIGEST_1,
        "actor_role": "operator",
        "authorization_digest": DIGEST_2,
        "decided_at": TIMESTAMP,
        "decision": "approved",
        "subject_digest": DIGEST_3,
    },
    "assignment": {
        "applicability": "unconditional",
        "assignment_id": "assignment_1",
        "authorization_policy_digest": DIGEST_1,
        "dependency_projection_digest": DIGEST_3,
        "execution_requirement": "blocking_scenario",
        "gate_digest": DIGEST_4,
        "impact": "blocking",
        "invalidation_policy_digest": DIGEST_5,
        "separation_policy_digest": DIGEST_6,
        "subject_digest": DIGEST_7,
        "validity_policy_digest": DIGEST_8,
    },
    "assignment_set": {
        "assignment_digests": [DIGEST_1, DIGEST_2],
        "requirements_digest": DIGEST_3,
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
        "capability_digests": [],
        "authority_head_digest": DIGEST_4,
        "authority_manifest_digest": DIGEST_5,
        "complete_through_sequence": 42,
        "completeness_proof_digest": DIGEST_6,
        "contract_digest": DIGEST_7,
        "currency_proof_digests": [DIGEST_9],
        "evaluation_digests": [DIGEST_8],
        "fork_proof_digest": DIGEST_9,
        "generation_digest": DIGEST_3,
        "inclusion_edge_digests": [],
        "journal_head_digest": DIGEST_4,
        "operation_digests": [],
        "operation_terminal_digests": [],
        "observation_digests": [],
        "observed_at": TIMESTAMP,
        "phase": "prevalidated",
        "registration_set_digest": DIGEST_5,
        "target_digest": DIGEST_6,
        "target_kind": "live_root",
        "target_protected_state_digest": DIGEST_7,
    },
    "authority_register": {
        "observed_at": TIMESTAMP,
        "quorum_receipt_digests": [DIGEST_1, DIGEST_2],
        "register_head_digest": DIGEST_5,
        "register_id": "authority_register_1",
        "selected_manifest_digest": DIGEST_3,
        "sequence": 1,
        "status": "valid",
        "witness_roster_digest": DIGEST_4,
    },
    "authorization": {
        "action": "activate_generation",
        "allowed_actor_roles": ["operator"],
        "approver_roles": ["operator", "witness"],
        "policy_id": "authorization_policy_1",
        "recovery_root_digest": DIGEST_1,
        "separation_policy_digest": DIGEST_2,
        "subject_kind": "generation",
        "validity_policy_digest": DIGEST_3,
    },
    "baseline_restoration_receipt": {
        "candidate_live_protected_state_digest": DIGEST_1,
        "captured_checkpoint_digest": DIGEST_2,
        "captured_generation_digest": DIGEST_3,
        "captured_protected_state_digest": DIGEST_4,
        "isolated_install_operation_digest": DIGEST_5,
        "isolated_install_operation_terminal_digest": DIGEST_6,
        "live_prestate_protected_state_digest": DIGEST_7,
        "post_restoration_gate_terminal_digest": DIGEST_8,
        "post_restoration_smoke_attempt_digest": DIGEST_9,
        "post_restoration_smoke_contract_digest": DIGEST_2,
        "post_restoration_smoke_evaluation_digest": DIGEST_1,
        "phase_establishing_operation_obligation_digest": DIGEST_3,
        "prevalidated_promotion_contract_digest": DIGEST_4,
        "receipt_id": "baseline_restoration_receipt_1",
        "rehearsal_install_operation_digest": DIGEST_2,
        "rehearsal_install_operation_terminal_digest": DIGEST_3,
        "restoration_evidence_cut_digest": DIGEST_4,
        "restoration_operation_digest": DIGEST_5,
        "restoration_operation_terminal_digest": DIGEST_6,
        "restored_generation_digest": DIGEST_7,
        "restored_fence_epoch": 3,
        "restored_projection_digest": DIGEST_9,
        "restored_protected_state_digest": DIGEST_8,
        "rollback_digest": DIGEST_9,
        "target_digest": DIGEST_1,
    },
    "backend_provenance": {
        "authorization_digest": DIGEST_1,
        "backend_id": "lemonade_hip",
        "backend_manifest_digest": DIGEST_2,
        "configuration_digest": DIGEST_3,
        "driver_device_digest": DIGEST_4,
        "generation_digest": DIGEST_5,
        "model_identity_digest": DIGEST_6,
        "observed_at": "2026-08-12T09:56:00Z",
        "observer_identity_digest": DIGEST_7,
        "package_manifest_digest": DIGEST_8,
        "process_epoch": "process_epoch_1",
        "provenance_id": "service_epoch_1_provenance",
        "service_protected_state_digest": DIGEST_9,
        "target_digest": DIGEST_1,
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
        "accepted_generation_digest": DIGEST_2,
        "active_generation_digest": DIGEST_1,
        "authorization_policy_digest": DIGEST_2,
        "contract_digest": DIGEST_3,
        "fallback_digest": DIGEST_4,
        "inventory_digest": DIGEST_5,
        "manifest_id": "composite_authority_1",
        "quorum_policy_digest": DIGEST_5,
        "recovery_policy_digest": DIGEST_6,
        "requirements_digest": DIGEST_7,
        "rollback_generation_digest": DIGEST_7,
        "rollback_registry_digest": DIGEST_8,
        "witness_roster_digest": DIGEST_9,
    },
    "composite_authority_checkpoint": {
        "authorization_digest": DIGEST_1,
        "change_set_digest": DIGEST_8,
        "checkpoint_id": "composite_checkpoint_1",
        "committed_at": TIMESTAMP,
        "quorum_receipt_digests": [DIGEST_2, DIGEST_3],
        "register_head_digest": DIGEST_4,
        "register_id": "composite_register",
        "register_observation_digest": DIGEST_5,
        "register_sequence": 7,
        "selected_manifest_digest": DIGEST_6,
        "signer_identity_digest": DIGEST_7,
    },
    "composite_change_set": {
        "authorization_action": "transition_composite_authority",
        "authorization_digest": DIGEST_1,
        "candidate_manifest_digest": DIGEST_2,
        "change_set_id": "change_set_1",
        "changed_fields": ["active_generation", "fallback"],
        "coordinator_identity_digest": DIGEST_3,
        "generation_binding": {
            "generation_digest": DIGEST_1,
            "mode": "required_generation",
        },
        "old_manifest_digest": DIGEST_4,
        "quorum_mode": "existing",
        "rollback_manifest_digest": DIGEST_4,
        "terminal_rule": "conjunctive",
        "transition_mode": "activation",
    },
    "composite_fallback_reference": {
        "authorization_digest": DIGEST_1,
        "committed_checkpoint_digest": DIGEST_2,
        "reference_id": "composite_fallback_1",
        "referenced_manifest_digest": DIGEST_3,
    },
    "dependency_projection": {
        "dependency_digests": [DIGEST_1, DIGEST_2],
        "dependency_keys": ["driver/device", "generation"],
        "projection_id": "dependency_projection_1",
    },
    "evidence_currency_proof": {
        "evaluated_dependency_projection_digest": DIGEST_1,
        "evaluation_digest": DIGEST_2,
        "inclusion_edge_digests": [],
        "invalidation_policy_digest": DIGEST_3,
        "invalidation_stream_checkpoint_digest": DIGEST_4,
        "trusted_time_observation_digest": DIGEST_5,
        "validity_policy_digest": DIGEST_6,
    },
    "evaluation": {
        "applicability": "applicable",
        "assignment_digest": DIGEST_1,
        "attestation_digests": [DIGEST_2],
        "context_digest": DIGEST_3,
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
    "final_service_anchor_receipt": {
        "anchor_id": "accepted_service_anchor",
        "backend_provenance_digest": DIGEST_1,
        "evidence_cut_digest": DIGEST_2,
        "expires_at": "2026-08-12T10:05:00Z",
        "final_restart_operation_digest": DIGEST_3,
        "final_restart_operation_terminal_digest": DIGEST_4,
        "generation_digest": DIGEST_5,
        "issued_at": TIMESTAMP,
        "predecessor_service_anchor_receipt_digest": DIGEST_6,
        "process_epoch": "process_epoch_2",
        "promotion_contract_digest": DIGEST_7,
        "readiness_digest": DIGEST_8,
        "service_protected_state_digest": DIGEST_9,
        "target_digest": DIGEST_1,
    },
    "gate": {
        "assertion_digest": DIGEST_1,
        "attestation_authorization_digest": DIGEST_5,
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
    "invalidation_policy": {
        "dependency_keys": ["driver/device", "generation"],
        "policy_id": "invalidation_policy_1",
    },
    "invalidation_stream_checkpoint": {
        "authority_head_digest": DIGEST_1,
        "authority_manifest_digest": DIGEST_2,
        "authority_view_digest": DIGEST_3,
        "checkpoint_id": "invalidation_checkpoint_1",
        "checkpointed_at": TIMESTAMP,
        "complete_through_sequence": 42,
        "completeness_proof_digest": DIGEST_4,
        "current_dependency_projection_digest": DIGEST_5,
        "fork_proof_digest": DIGEST_6,
        "invalidation_policy_digest": DIGEST_7,
        "stream_head_digest": DIGEST_8,
        "stream_id": "invalidation_stream_1",
    },
    "installed_inventory": {
        "authorization_digest": DIGEST_1,
        "configuration_digest": DIGEST_2,
        "driver_device_digest": DIGEST_3,
        "generation_digest": DIGEST_4,
        "inventory_id": "installed_inventory_1",
        "model_identity_digests": [DIGEST_5, DIGEST_6],
        "observed_at": TIMESTAMP,
        "observer_identity_digest": DIGEST_7,
        "package_manifest_digest": DIGEST_8,
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
        "target_digest": DIGEST_7,
        "target_kind": "live_root",
        "terminal_validator_digest": DIGEST_8,
    },
    "operation_attestation": {
        "observed_at": TIMESTAMP,
        "operation_digest": DIGEST_1,
        "outcome": "succeeded",
        "poststate_digest": DIGEST_2,
        "subject_digest": DIGEST_3,
        "validator_digest": DIGEST_4,
    },
    "operation_obligation": {
        "generation_binding": {
            "generation_digest": DIGEST_1,
            "mode": "required_generation",
        },
        "generation_class": "c",
        "intent_digest": DIGEST_2,
        "lifecycle_phase": "active",
        "obligation_id": "activation_1",
        "operation_kind": "package_installation",
        "operation_digest": DIGEST_3,
        "operation_requirement_digest": DIGEST_4,
        "subject_digest": DIGEST_1,
        "subject_kind": "generation",
        "target_id": "reference_host",
        "target_kind": "live_root",
    },
    "operation_obligation_set": {
        "obligation_digests": [DIGEST_1, DIGEST_2],
        "operation_requirement_set_digest": DIGEST_4,
        "requirements_digest": DIGEST_3,
    },
    "operation_requirement": {
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
    "operation_requirement_set": {
        "operation_requirement_digests": [DIGEST_1, DIGEST_2],
        "requirements_digest": DIGEST_3,
    },
    "operation_realization": {
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
    "operation_realization_set": {
        "operation_obligation_set_digest": DIGEST_1,
        "operation_realization_digests": [DIGEST_2],
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
    "promotion_authority_proof": {
        "atomic_evidence_cut_digest": DIGEST_1,
        "attempt_digests": [DIGEST_2],
        "authority_adapter_identity_digest": DIGEST_3,
        "authority_head_digest": DIGEST_4,
        "authority_manifest_digest": DIGEST_5,
        "authority_view_digest": DIGEST_6,
        "capability_digests": [],
        "complete_through_sequence": 42,
        "completeness_proof_digest": DIGEST_7,
        "currency_proof_digests": [DIGEST_9],
        "evaluation_digests": [DIGEST_8],
        "fork_proof_digest": DIGEST_9,
        "inclusion_edge_digests": [],
        "journal_head_digest": DIGEST_1,
        "operation_digests": [],
        "operation_terminal_digests": [],
        "observation_digests": [],
        "phase": "prevalidated",
        "predecessor_checkpoint_digest": DIGEST_5,
        "promotion_contract_digest": DIGEST_2,
        "proof_id": "promotion_authority_proof_1",
        "validation_contract_digest": DIGEST_3,
        "verified_at": TIMESTAMP,
        "verifier_identity_digest": DIGEST_4,
    },
    "promotion_contract": {
        "contract_id": "w0_prevalidated_contract",
        "expected_accepted_generation_digest": DIGEST_1,
        "expected_active_generation_digest": DIGEST_2,
        "generation_digest": DIGEST_3,
        "obligation_digests": [DIGEST_4, DIGEST_5],
        "operation_obligation_set_digest": DIGEST_8,
        "operation_realization_set_digest": DIGEST_7,
        "phase": "prevalidated",
        "phase_establishing_operation_obligation_digest": DIGEST_4,
        "predecessor_checkpoint_digest": DIGEST_5,
        "requirements_digest": DIGEST_6,
        "target_digest": DIGEST_7,
        "target_kind": "live_root",
        "target_protected_state_digest": DIGEST_8,
        "validation_contract_digest": DIGEST_9,
    },
    "lifecycle_checkpoint": {
        "authority_proof_digest": DIGEST_4,
        "checkpoint_id": "prevalidated_checkpoint_1",
        "contract_digest": DIGEST_5,
        "evidence_cut_digest": DIGEST_1,
        "established_at": TIMESTAMP,
        "generation_class": "c",
        "generation_digest": DIGEST_2,
        "phase": "prevalidated",
        "predecessor_checkpoint_digest": DIGEST_3,
        "target_digest": DIGEST_6,
        "target_protected_state_digest": DIGEST_7,
    },
    "promotion_obligation": {
        "assignment_digest": DIGEST_1,
        "impact": "blocking",
        "obligation_id": "w0_control_plane",
        "occurrence_digest": DIGEST_2,
        "scenario_operation_obligation_digest": DIGEST_3,
    },
    "protected_state": {
        "fence_epoch": 1,
        "generation_digest": DIGEST_1,
        "lifecycle_phase": "active",
        "observed_at": TIMESTAMP,
        "projection_id": "active_generation_pointer",
        "state_digest": DIGEST_2,
        "target_digest": DIGEST_3,
        "target_kind": "live_root",
    },
    "quorum_policy": {
        "policy_id": "quorum_policy_1",
        "threshold": 2,
        "witness_roster_digest": DIGEST_1,
    },
    "quorum_receipt": {
        "approval_digests": [DIGEST_1, DIGEST_2],
        "approved_at": TIMESTAMP,
        "authorization_digest": DIGEST_3,
        "change_set_digest": DIGEST_4,
        "quorum_policy_digest": DIGEST_5,
        "receipt_id": "quorum_receipt_1",
        "side": "existing",
        "witness_roster_digest": DIGEST_6,
    },
    "readiness": {
        "backend_manifest_digest": DIGEST_2,
        "backend_provenance_digest": DIGEST_6,
        "generation_digest": DIGEST_1,
        "observed_at": TIMESTAMP,
        "process_epoch": "process_epoch_1",
        "service_health_observation_digests": [DIGEST_3, DIGEST_4],
        "service_protected_state_digest": DIGEST_7,
        "status": "ready",
        "target_digest": DIGEST_5,
    },
    "recovery": {
        "authorization_digest": DIGEST_1,
        "destination_generation_digest": DIGEST_2,
        "exact_state_generation_digest": DIGEST_2,
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
    "recovery_policy": {
        "authorization_digest": DIGEST_1,
        "policy_id": "recovery_policy_1",
        "recovery_contract_digests": [DIGEST_2, DIGEST_3],
        "recovery_owner_roles": ["operator", "recovery_owner"],
        "recovery_root_digest": DIGEST_4,
        "separation_policy_digest": DIGEST_5,
        "validity_policy_digest": DIGEST_6,
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
        "status": "active",
    },
    "restored_baseline_smoke_contract": {
        "assignment_digest": DIGEST_1,
        "attestation_authorization_digest": DIGEST_2,
        "expected_outcome": "pass",
        "gate_digest": DIGEST_3,
        "restored_protected_state_digest": DIGEST_4,
        "smoke_contract_id": "restored_baseline_smoke_1",
        "target_digest": DIGEST_5,
        "validation_contract_digest": DIGEST_6,
        "validator_digest": DIGEST_7,
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
        "target_generation_digest": DIGEST_1,
        "target_projection_digest": DIGEST_6,
        "target_protected_state_digest": DIGEST_7,
        "target_state_digest": DIGEST_8,
        "terminal_gate_digest": DIGEST_5,
    },
    "rollback_registry": {
        "authorization_digest": DIGEST_1,
        "established_at": TIMESTAMP,
        "registry_head_digest": DIGEST_2,
        "registry_id": "rollback_registry_1",
        "rollback_digests": [DIGEST_3, DIGEST_4],
        "selected_rollback_digest": DIGEST_4,
    },
    "separation_policy": {
        "forbidden_actor_identity_digests": [],
        "policy_id": "separation_policy_1",
        "required_actor_roles": [],
    },
    "service_anchor_receipt": {
        "active_evidence_cut_digest": DIGEST_1,
        "active_phase_operation_terminal_digest": DIGEST_8,
        "active_promotion_contract_digest": DIGEST_2,
        "anchor_id": "active_service_anchor",
        "backend_provenance_digest": DIGEST_9,
        "establishing_operation_digest": DIGEST_3,
        "expires_at": "2026-08-12T10:05:00Z",
        "generation_digest": DIGEST_4,
        "issued_at": TIMESTAMP,
        "operation_terminal_digest": DIGEST_5,
        "process_epoch": "process_epoch_1",
        "readiness_digest": DIGEST_8,
        "service_protected_state_digest": DIGEST_6,
        "target_digest": DIGEST_7,
    },
    "service_health_observation": {
        "authorization_digest": DIGEST_1,
        "backend_provenance_digest": DIGEST_2,
        "generation_digest": DIGEST_3,
        "observation_id": "service_epoch_1_health",
        "observed_at": TIMESTAMP,
        "observer_identity_digest": DIGEST_4,
        "process_epoch": "process_epoch_1",
        "service_protected_state_digest": DIGEST_5,
        "status": "ready",
        "target_digest": DIGEST_6,
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
    "trusted_time_observation": {
        "authority_head_digest": DIGEST_1,
        "observation_id": "trusted_time_observation_1",
        "observed_at": TIMESTAMP,
        "time_authority_digest": DIGEST_2,
        "time_proof_digest": DIGEST_3,
    },
    "validation_contract": {
        "approval_digest": DIGEST_1,
        "assignments_digest": DIGEST_2,
        "authorization_policy_digest": DIGEST_3,
        "contract_id": "active_validation_contract",
        "max_live_attempt_seconds": 3600,
        "max_suite_seconds": 28800,
        "operation_requirement_set_digest": DIGEST_5,
        "requirements_digest": DIGEST_4,
    },
    "validation_context": {
        "assignments_digest": DIGEST_1,
        "context_id": "active_contract_context_1",
        "context_type": "active_contract",
        "contract_digest": DIGEST_2,
        "generation_digest": DIGEST_3,
        "requirements_digest": DIGEST_4,
    },
    "validity_policy": {
        "attestation_max_age_seconds": 300,
        "evidence_cut_max_age_seconds": 300,
        "expiry_rule": "earliest_constituent_expiry",
        "inclusion_edge_max_age_seconds": 28_800,
        "policy_id": "validity_policy_1",
        "predicate_proof_max_age_seconds": 300,
    },
    "witness_roster": {
        "roster_id": "witness_roster_1",
        "witness_identity_digests": [DIGEST_1, DIGEST_2],
    },
}


PUBLIC_PROJECTION_VARIANTS = (
    ("approval", {"decision": "approved"}, {}, ()),
    ("approval", {"decision": "rejected"}, {"decision": "rejected"}, ()),
    ("assignment", {"applicability": "unconditional"}, {}, ()),
    (
        "assignment",
        {"applicability": "conditional"},
        {"applicability": "conditional", "predicate_digest": DIGEST_9},
        (),
    ),
    ("attestation", {"outcome": "blocked"}, {"outcome": "blocked"}, ()),
    ("attestation", {"outcome": "fail"}, {"outcome": "fail"}, ()),
    ("attestation", {"outcome": "pass"}, {}, ()),
    ("attestation", {"outcome": "unknown"}, {"outcome": "unknown"}, ()),
    (
        "authority_register",
        {"status": "absent"},
        {"quorum_receipt_digests": [], "status": "absent"},
        ("selected_manifest_digest",),
    ),
    (
        "authority_register",
        {"status": "corrupt"},
        {"quorum_receipt_digests": [], "status": "corrupt"},
        ("selected_manifest_digest",),
    ),
    ("authority_register", {"status": "valid"}, {}, ()),
    ("capability", {"status": "active"}, {}, ()),
    ("capability", {"status": "consumed"}, {"status": "consumed"}, ()),
    ("capability", {"status": "revoked"}, {"status": "revoked"}, ()),
    (
        "evaluation",
        {"applicability": "applicable", "outcome": "blocked"},
        {"outcome": "blocked"},
        (),
    ),
    (
        "evaluation",
        {"applicability": "applicable", "outcome": "fail"},
        {"outcome": "fail"},
        (),
    ),
    (
        "evaluation",
        {"applicability": "applicable", "outcome": "pass"},
        {},
        (),
    ),
    (
        "evaluation",
        {"applicability": "applicable_unknown", "outcome": "unknown"},
        {
            "applicability": "applicable_unknown",
            "attestation_digests": [],
            "outcome": "unknown",
            "unknown_reason": "missing_attestation",
        },
        (),
    ),
    (
        "evaluation",
        {"applicability": "not_applicable", "outcome": "not_applicable"},
        {
            "applicability": "not_applicable",
            "attestation_digests": [],
            "outcome": "not_applicable",
            "predicate_proof_digest": DIGEST_9,
        },
        (),
    ),
    (
        "evaluation",
        {"applicability": "not_due", "outcome": "unknown"},
        {
            "applicability": "not_due",
            "attestation_digests": [],
            "outcome": "unknown",
        },
        (),
    ),
    ("exception", {"status": "active"}, {}, ()),
    ("exception", {"status": "expired"}, {"status": "expired"}, ()),
    ("exception", {"status": "revoked"}, {"status": "revoked"}, ()),
    (
        "invalidation",
        {"status": "closed"},
        {"closed_at": TIMESTAMP, "status": "closed"},
        (),
    ),
    ("invalidation", {"status": "open"}, {}, ()),
    ("readiness", {"status": "not_ready"}, {"status": "not_ready"}, ()),
    ("readiness", {"status": "ready"}, {}, ()),
    ("retention_lease", {"status": "active"}, {}, ()),
    (
        "retention_lease",
        {"status": "expired"},
        {"status": "expired"},
        (),
    ),
    (
        "retention_lease",
        {"status": "revoked"},
        {"status": "revoked"},
        (),
    ),
    ("terminal_record", {"outcome": "failed"}, {"outcome": "failed"}, ()),
    ("terminal_record", {"outcome": "succeeded"}, {}, ()),
    ("terminal_record", {"outcome": "unknown"}, {"outcome": "unknown"}, ()),
)


@pytest.mark.parametrize(
    ("kind", "expected_public", "changes", "removed_fields"),
    PUBLIC_PROJECTION_VARIANTS,
)
def test_public_envelope_projects_every_schema_declared_public_variant(
    kind: str,
    expected_public: dict[str, object],
    changes: dict[str, object],
    removed_fields: tuple[str, ...],
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    payload.update(changes)
    for field in removed_fields:
        payload.pop(field)

    envelope = ControlRecord.build(
        kind=kind,
        record_id=f"{kind}_record_1",
        payload=payload,
    ).public_envelope(opaque_reference_key=b"r" * 32)

    assert envelope.payload["public"] == expected_public


def test_public_projection_variants_cover_the_declared_field_schemas() -> None:
    expected = {
        (kind, field, choice)
        for kind, schema in RECORD_SCHEMAS.items()
        for field in schema.public_fields
        for choice in (
            schema.required_fields.get(field) or schema.optional_fields[field]
        ).choices
    }
    covered = {
        (kind, field, value)
        for kind, public, _changes, _removed in PUBLIC_PROJECTION_VARIANTS
        for field, value in public.items()
    }

    assert covered == expected


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
    signature = None
    if kind == "composite_authority_checkpoint":
        signature = {
            "algorithm": "ed25519",
            "signed_digest": ControlRecord.signing_digest(
                kind=kind,
                record_id=f"{kind}_record_1",
                payload=payload,
            ),
            "signer_identity_digest": payload["signer_identity_digest"],
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        }

    record = ControlRecord.build(
        kind=kind,
        record_id=f"{kind}_record_1",
        payload=payload,
        signature=signature,
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
    typed_fields = {**schema.required_fields, **schema.optional_fields}
    digest_field = next(
        (
            field
            for field, field_schema in typed_fields.items()
            if field_schema.kind.value
            in {"digest", "digest_list", "digest_sequence"}
        ),
        None,
    )
    if digest_field is None:
        return
    payload[digest_field] = (
        ["sha256:not-a-digest"]
        if typed_fields[digest_field].kind.value
        in {"digest_list", "digest_sequence"}
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
    ("kind", "field", "expected_code"),
    [
        ("assignment_set", "assignment_digests", RecordErrorCode.INVALID_DIGEST),
        ("composite_change_set", "changed_fields", RecordErrorCode.INVALID_PAYLOAD_FIELD),
        ("dependency_projection", "dependency_keys", RecordErrorCode.INVALID_PAYLOAD_FIELD),
    ],
)
def test_typed_set_arrays_reject_unhashable_members_with_stable_record_errors(
    kind: str,
    field: str,
    expected_code: RecordErrorCode,
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    payload[field] = [{"malformed": "member"}]

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_with_malformed_{field}",
            payload=payload,
        )

    assert caught.value.code is expected_code


def test_separation_and_authorization_policies_are_closed_and_nonvacuous() -> None:
    separation = ControlRecord.build(
        kind="separation_policy",
        record_id="separation_policy_record_1",
        payload=VALID_PAYLOADS["separation_policy"],
    )
    authorization = ControlRecord.build(
        kind="authorization",
        record_id="authorization_record_1",
        payload=VALID_PAYLOADS["authorization"],
    )

    assert separation.payload["required_actor_roles"] == ()
    assert separation.payload["forbidden_actor_identity_digests"] == ()
    assert authorization.payload["allowed_actor_roles"] == ("operator",)

    invalid_policies = (
        {**VALID_PAYLOADS["separation_policy"], "policy_id": ""},
        {
            **VALID_PAYLOADS["separation_policy"],
            "required_actor_roles": ["operator", "operator"],
        },
        {
            **VALID_PAYLOADS["separation_policy"],
            "forbidden_actor_identity_digests": ["sha256:bad"],
        },
    )
    for payload in invalid_policies:
        with pytest.raises(RecordValidationError):
            ControlRecord.build(
                kind="separation_policy",
                record_id="separation_policy_record_invalid",
                payload=payload,
            )

    vacuous_authorization = deepcopy(VALID_PAYLOADS["authorization"])
    vacuous_authorization.pop("allowed_actor_roles")
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="authorization",
            record_id="authorization_record_invalid",
            payload=vacuous_authorization,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    empty_authorization = {
        **vacuous_authorization,
        "allowed_actor_identity_digests": [],
        "allowed_actor_roles": [],
    }
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="authorization",
            record_id="authorization_record_empty",
            payload=empty_authorization,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    identity_authorization = {
        **vacuous_authorization,
        "allowed_actor_identity_digests": [DIGEST_9],
    }
    assert ControlRecord.build(
        kind="authorization",
        record_id="authorization_record_identity",
        payload=identity_authorization,
    ).payload["allowed_actor_identity_digests"] == (DIGEST_9,)


def test_approval_binds_the_actor_role_used_for_authorization() -> None:
    approval = ControlRecord.build(
        kind="approval",
        record_id="approval_record_with_role",
        payload=VALID_PAYLOADS["approval"],
    )
    assert approval.payload["actor_role"] == "operator"

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="approval",
            record_id="approval_record_with_invalid_role",
            payload={**VALID_PAYLOADS["approval"], "actor_role": "Operator Admin"},
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


def test_assignment_declares_its_execution_requirement() -> None:
    blocking_scenario = ControlRecord.build(
        kind="assignment",
        record_id="blocking_scenario_assignment",
        payload=VALID_PAYLOADS["assignment"],
    )
    evidence_only = ControlRecord.build(
        kind="assignment",
        record_id="advisory_evidence_assignment",
        payload={
            **VALID_PAYLOADS["assignment"],
            "execution_requirement": "evidence_only",
            "impact": "advisory",
        },
    )

    assert blocking_scenario.payload["execution_requirement"] == "blocking_scenario"
    assert evidence_only.payload["execution_requirement"] == "evidence_only"

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="assignment",
            record_id="advisory_blocking_scenario_assignment",
            payload={**VALID_PAYLOADS["assignment"], "impact": "advisory"},
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="assignment",
            record_id="open_ended_execution_requirement_assignment",
            payload={
                **VALID_PAYLOADS["assignment"],
                "execution_requirement": "operator_decides",
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


def test_gate_authorization_fields_are_closed_and_predicate_specific() -> None:
    gate = ControlRecord.build(
        kind="gate",
        record_id="gate_record_1",
        payload={
            **VALID_PAYLOADS["gate"],
            "predicate_authorization_digest": DIGEST_6,
        },
    )

    assert gate.payload["attestation_authorization_digest"] == DIGEST_5
    assert gate.payload["predicate_authorization_digest"] == DIGEST_6


def test_operation_records_bind_target_phase_and_exact_obligation() -> None:
    assert ControlRecord.build(
        kind="operation",
        record_id="operation_record_exact",
        payload=VALID_PAYLOADS["operation"],
    ).payload["target_digest"] == DIGEST_7
    assert ControlRecord.build(
        kind="operation_obligation",
        record_id="operation_obligation_record_exact",
        payload=VALID_PAYLOADS["operation_obligation"],
    ).payload["operation_digest"] == DIGEST_3
    assert ControlRecord.build(
        kind="protected_state",
        record_id="protected_state_record_exact",
        payload=VALID_PAYLOADS["protected_state"],
    ).payload["target_kind"] == "live_root"


def test_operation_requirement_is_an_occurrence_free_exact_operation_template() -> None:
    requirement = ControlRecord.build(
        kind="operation_requirement",
        record_id="operation_requirement_active_install",
        payload=VALID_PAYLOADS["operation_requirement"],
    )

    assert requirement.payload["purpose"] == "phase_transition"
    assert requirement.payload["target_digest"] == DIGEST_4
    assert requirement.payload["declared_effects"][0]["effect_id"] == (
        "package_database"
    )
    for forbidden_field in (
        "context_digest",
        "generation_digest",
        "intent_digest",
        "operation_digest",
        "protected_state_digest",
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="operation_requirement",
                record_id=f"operation_requirement_with_{forbidden_field}",
                payload={
                    **VALID_PAYLOADS["operation_requirement"],
                    forbidden_field: DIGEST_9,
                },
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_operation_requirement_rejects_declared_target_as_a_recovery_role() -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation_requirement_declared_target_recovery",
            payload={
                **VALID_PAYLOADS["operation_requirement"],
                "recovery_target_role": "declared_target",
            },
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


def test_operation_requirement_assignment_is_exactly_for_applicable_gate_work() -> None:
    gate_requirement = {
        **VALID_PAYLOADS["operation_requirement"],
        "assignment_digest": DIGEST_6,
        "operation_kind": "blocking_scenario",
        "purpose": "blocking_scenario",
        "realization_condition": "when_assignment_applicable",
        "subject_binding_role": "gate_occurrence",
        "subject_kind": "gate_occurrence",
        "target_kind": "service",
    }
    assert ControlRecord.build(
        kind="operation_requirement",
        record_id="operation_requirement_blocking_scenario",
        payload=gate_requirement,
    ).payload["assignment_digest"] == DIGEST_6

    invalid_payloads = (
        {key: value for key, value in gate_requirement.items() if key != "assignment_digest"},
        {**gate_requirement, "purpose": "phase_transition"},
        {**gate_requirement, "realization_condition": "always"},
        {
            **VALID_PAYLOADS["operation_requirement"],
            "assignment_digest": DIGEST_6,
        },
        {
            **VALID_PAYLOADS["operation_requirement"],
            "realization_condition": "when_assignment_applicable",
        },
    )
    for index, payload in enumerate(invalid_payloads):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="operation_requirement",
                record_id=f"operation_requirement_invalid_assignment_{index}",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_service_restart_requirement_is_assignment_bound_scenario_work() -> None:
    requirement = {
        **VALID_PAYLOADS["operation_requirement"],
        "assignment_digest": DIGEST_6,
        "operation_kind": "blocking_scenario",
        "purpose": "service_restart",
        "realization_condition": "when_assignment_applicable",
        "subject_binding_role": "gate_occurrence",
        "subject_kind": "gate_occurrence",
        "target_kind": "service",
    }

    assert ControlRecord.build(
        kind="operation_requirement",
        record_id="service_restart_requirement",
        payload=requirement,
    ).payload["assignment_digest"] == DIGEST_6


def test_final_service_restart_is_always_realized_unconditional_gate_work() -> None:
    requirement = {
        **VALID_PAYLOADS["operation_requirement"],
        "assignment_digest": DIGEST_6,
        "operation_kind": "blocking_scenario",
        "purpose": "final_service_restart",
        "subject_binding_role": "gate_occurrence",
        "subject_kind": "gate_occurrence",
        "target_kind": "service",
    }

    assert ControlRecord.build(
        kind="operation_requirement",
        record_id="final_service_restart_requirement",
        payload=requirement,
    ).payload["realization_condition"] == "always"

    for removed, changes in (
        ("assignment_digest", {}),
        (None, {"realization_condition": "when_assignment_applicable"}),
    ):
        invalid = {**requirement, **changes}
        if removed is not None:
            invalid.pop(removed)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="operation_requirement",
                record_id="invalid_final_service_restart_requirement",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    "changes",
    [
        {"purpose": "baseline_rehearsal_install"},
        {
            "operation_kind": "rollback",
            "purpose": "baseline_restoration",
            "recovery_target_role": "captured_baseline",
        },
        {
            "assignment_digest": DIGEST_6,
            "operation_kind": "blocking_scenario",
            "purpose": "service_anchor",
            "realization_condition": "when_assignment_applicable",
            "subject_binding_role": "gate_occurrence",
            "subject_kind": "gate_occurrence",
            "target_kind": "service",
        },
    ],
)
def test_operation_requirement_purpose_has_one_legal_authority_shape(changes) -> None:
    requirement = ControlRecord.build(
        kind="operation_requirement",
        record_id=f"operation_requirement_{changes['purpose']}",
        payload={**VALID_PAYLOADS["operation_requirement"], **changes},
    )

    assert requirement.payload["purpose"] == changes["purpose"]


@pytest.mark.parametrize(
    "changes",
    [
        {"target_kind": "service"},
        {
            "operation_kind": "rollback",
            "purpose": "baseline_rehearsal_install",
        },
        {"purpose": "baseline_restoration"},
        {
            "assignment_digest": DIGEST_6,
            "operation_kind": "blocking_scenario",
            "purpose": "service_anchor",
            "realization_condition": "when_assignment_applicable",
            "subject_binding_role": "gate_occurrence",
            "subject_kind": "gate_occurrence",
            "target_kind": "live_root",
        },
    ],
)
def test_operation_requirement_rejects_wrong_coordinates_for_its_purpose(
    changes,
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation_requirement_wrong_purpose_coordinates",
            payload={**VALID_PAYLOADS["operation_requirement"], **changes},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    "changes",
    [
        {
            "lifecycle_phase": "published",
            "operation_kind": "repository_publication",
            "target_kind": "package_repository",
        },
        {
            "lifecycle_phase": "prevalidated",
            "target_kind": "isolated_root",
        },
        {},
        {
            "generation_class": "f",
            "lifecycle_phase": "foundation_validation",
            "target_kind": "isolated_root",
        },
        {
            "generation_binding_mode": "b0_capture_sentinel",
            "generation_binding_role": "b0_capture_sentinel",
            "generation_class": "b0",
            "lifecycle_phase": "captured",
            "operation_kind": "composite_authority_transition",
            "subject_binding_role": "composite_authority",
            "subject_kind": "composite_authority",
            "target_kind": "composite_register",
        },
    ],
)
def test_phase_transition_requirement_uses_the_shared_authority_coordinate_table(
    changes,
) -> None:
    requirement = ControlRecord.build(
        kind="operation_requirement",
        record_id="operation_requirement_shared_coordinate",
        payload={**VALID_PAYLOADS["operation_requirement"], **changes},
    )

    assert requirement.payload["purpose"] == "phase_transition"


@pytest.mark.parametrize(
    "changes",
    [
        {"generation_class": "c", "lifecycle_phase": "foundation_validation"},
        {"generation_class": "f", "lifecycle_phase": "active"},
        {
            "generation_binding_mode": "required_generation",
            "generation_binding_role": "b0_capture_sentinel",
            "generation_class": "b0",
            "lifecycle_phase": "captured",
            "operation_kind": "composite_authority_transition",
            "subject_binding_role": "composite_authority",
            "subject_kind": "composite_authority",
            "target_kind": "composite_register",
        },
    ],
)
def test_phase_transition_requirement_rejects_adjacent_invalid_coordinates(
    changes,
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation_requirement_invalid_shared_coordinate",
            payload={**VALID_PAYLOADS["operation_requirement"], **changes},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    "changes",
    [
        {"subject_binding_role": "control_record"},
        {"generation_binding_role": "b0_capture_sentinel"},
        {"generation_binding_role": "no_generation"},
    ],
)
def test_operation_requirement_roles_cannot_contradict_their_coordinate_types(
    changes,
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="operation_requirement",
            record_id="operation_requirement_contradictory_role",
            payload={**VALID_PAYLOADS["operation_requirement"], **changes},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_validation_contract_approves_requirements_before_occurrences_exist() -> None:
    requirement_set = ControlRecord.build(
        kind="operation_requirement_set",
        record_id="operation_requirement_set_approved",
        payload=VALID_PAYLOADS["operation_requirement_set"],
    )
    empty_requirement_set = ControlRecord.build(
        kind="operation_requirement_set",
        record_id="operation_requirement_set_empty",
        payload={
            **VALID_PAYLOADS["operation_requirement_set"],
            "operation_requirement_digests": [],
        },
    )
    validation_contract = ControlRecord.build(
        kind="validation_contract",
        record_id="validation_contract_with_operation_requirements",
        payload=VALID_PAYLOADS["validation_contract"],
    )
    obligation = ControlRecord.build(
        kind="operation_obligation",
        record_id="operation_obligation_realization",
        payload=VALID_PAYLOADS["operation_obligation"],
    )
    obligation_set = ControlRecord.build(
        kind="operation_obligation_set",
        record_id="operation_obligation_set_realization",
        payload=VALID_PAYLOADS["operation_obligation_set"],
    )

    assert requirement_set.payload["operation_requirement_digests"] == (
        DIGEST_1,
        DIGEST_2,
    )
    assert empty_requirement_set.payload["operation_requirement_digests"] == ()
    assert validation_contract.payload["operation_requirement_set_digest"] == (
        DIGEST_5
    )
    assert obligation.payload["operation_requirement_digest"] == DIGEST_4
    assert obligation_set.payload["operation_requirement_set_digest"] == DIGEST_4


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_live_attempt_seconds", 0),
        ("max_live_attempt_seconds", 3601),
        ("max_suite_seconds", 0),
        ("max_suite_seconds", 28801),
    ),
)
def test_validation_contract_rejects_invalid_execution_time_budgets(
    field: str,
    value: int,
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="validation_contract",
            record_id=f"validation_contract_invalid_{field}",
            payload={**VALID_PAYLOADS["validation_contract"], field: value},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_validation_contract_allows_tighter_execution_time_budgets() -> None:
    contract = ControlRecord.build(
        kind="validation_contract",
        record_id="validation_contract_tighter_time_budgets",
        payload={
            **VALID_PAYLOADS["validation_contract"],
            "max_live_attempt_seconds": 900,
            "max_suite_seconds": 7200,
        },
    )

    assert contract.payload["max_live_attempt_seconds"] == 900
    assert contract.payload["max_suite_seconds"] == 7200


@pytest.mark.parametrize(
    "field",
    ("max_live_attempt_seconds", "max_suite_seconds"),
)
def test_validation_contract_requires_integer_execution_time_budgets(
    field: str,
) -> None:
    payload = deepcopy(VALID_PAYLOADS["validation_contract"])
    payload[field] = True
    with pytest.raises(RecordValidationError) as malformed:
        ControlRecord.build(
            kind="validation_contract",
            record_id=f"validation_contract_boolean_{field}",
            payload=payload,
        )
    assert malformed.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD

    payload.pop(field)
    with pytest.raises(RecordValidationError) as missing:
        ControlRecord.build(
            kind="validation_contract",
            record_id=f"validation_contract_missing_{field}",
            payload=payload,
        )
    assert missing.value.code is RecordErrorCode.MISSING_PAYLOAD_FIELD


def test_operation_realization_materializes_exact_roles_prestate_and_set_ownership() -> None:
    realization = ControlRecord.build(
        kind="operation_realization",
        record_id="operation_realization_active_install",
        payload={
            "observed_prestate_digest": DIGEST_1,
            "operation_digest": DIGEST_2,
            "operation_obligation_digest": DIGEST_3,
            "operation_requirement_digest": DIGEST_4,
            "realization_id": "active_install_realization",
            "resolved_generation_binding": {
                "generation_digest": DIGEST_5,
                "mode": "required_generation",
            },
            "resolved_subject_digest": DIGEST_6,
        },
    )
    realization_set = ControlRecord.build(
        kind="operation_realization_set",
        record_id="operation_realization_set_active",
        payload={
            "operation_obligation_set_digest": DIGEST_7,
            "operation_realization_digests": [realization.digest()],
        },
    )
    contract = ControlRecord.build(
        kind="promotion_contract",
        record_id="promotion_contract_with_realizations",
        payload={
            **VALID_PAYLOADS["promotion_contract"],
            "operation_realization_set_digest": realization_set.digest(),
        },
    )

    assert realization.payload["observed_prestate_digest"] == DIGEST_1
    assert realization.payload["resolved_generation_binding"] == {
        "generation_digest": DIGEST_5,
        "mode": "required_generation",
    }
    assert realization_set.payload["operation_realization_digests"] == (
        realization.digest(),
    )
    assert contract.payload["operation_realization_set_digest"] == (
        realization_set.digest()
    )


def test_protected_state_target_kind_is_exact_and_content_addressed() -> None:
    states = {
        target_kind: ControlRecord.build(
            kind="protected_state",
            record_id=f"protected_state_{target_kind}",
            payload={
                **VALID_PAYLOADS["protected_state"],
                "target_kind": target_kind,
            },
        )
        for target_kind in (
            "package_repository",
            "isolated_root",
            "live_root",
            "service",
            "composite_register",
        )
    }

    assert {state.payload["target_kind"] for state in states.values()} == set(states)
    assert len({state.digest() for state in states.values()}) == len(states)

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="protected_state",
            record_id="protected_state_ambiguous_repository",
            payload={
                **VALID_PAYLOADS["protected_state"],
                "target_kind": "repository",
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


@pytest.mark.parametrize(
    ("phase", "changes", "removed"),
    [
        ("published", {}, ()),
        ("prevalidated", {}, ()),
        (
            "active",
            {"baseline_restoration_receipt_digest": DIGEST_7},
            (),
        ),
        (
            "accepted",
            {
                "acceptance_authorization_digest": DIGEST_6,
                "predecessor_service_anchor_receipt_digest": DIGEST_7,
            },
            ("phase_establishing_operation_obligation_digest",),
        ),
    ],
)
def test_promotion_contract_phase_fields_are_required_iff_applicable(
    phase: str,
    changes: dict[str, object],
    removed: tuple[str, ...],
) -> None:
    payload = {**VALID_PAYLOADS["promotion_contract"], "phase": phase, **changes}
    for field in removed:
        payload.pop(field)

    assert ControlRecord.build(
        kind="promotion_contract",
        record_id=f"promotion_contract_{phase}",
        payload=payload,
    ).payload["phase"] == phase

    if phase == "accepted":
        payload.pop("acceptance_authorization_digest")
    else:
        payload.pop("phase_establishing_operation_obligation_digest")
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="promotion_contract",
            record_id=f"promotion_contract_{phase}_invalid",
            payload=payload,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    forbidden = deepcopy(VALID_PAYLOADS["promotion_contract"])
    if phase == "accepted":
        forbidden.update(
            {
                "acceptance_authorization_digest": DIGEST_6,
                "phase": phase,
            }
        )
    else:
        forbidden["acceptance_authorization_digest"] = DIGEST_6
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="promotion_contract",
            record_id=f"promotion_contract_{phase}_forbidden",
            payload=forbidden,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_baseline_restoration_receipt_is_a_closed_acyclic_exact_binding() -> None:
    receipt = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline_restoration_receipt_record_1",
        payload=VALID_PAYLOADS["baseline_restoration_receipt"],
    )

    assert set(receipt.payload) == {
        "candidate_live_protected_state_digest",
        "captured_checkpoint_digest",
        "captured_generation_digest",
        "captured_protected_state_digest",
        "isolated_install_operation_digest",
        "isolated_install_operation_terminal_digest",
        "live_prestate_protected_state_digest",
        "post_restoration_gate_terminal_digest",
        "post_restoration_smoke_attempt_digest",
        "post_restoration_smoke_contract_digest",
        "post_restoration_smoke_evaluation_digest",
        "phase_establishing_operation_obligation_digest",
        "prevalidated_promotion_contract_digest",
        "receipt_id",
        "rehearsal_install_operation_digest",
        "rehearsal_install_operation_terminal_digest",
        "restoration_evidence_cut_digest",
        "restoration_operation_digest",
        "restoration_operation_terminal_digest",
        "restored_generation_digest",
        "restored_fence_epoch",
        "restored_projection_digest",
        "restored_protected_state_digest",
        "rollback_digest",
        "target_digest",
    }
    assert receipt.payload["restoration_operation_terminal_digest"] == DIGEST_6

    for forbidden_field, value in (
        ("operation_digest", DIGEST_8),
        ("operation_terminal_digest", DIGEST_8),
        ("terminal_digest", DIGEST_8),
        ("restored_at", TIMESTAMP),
        ("promotion_contract_digest", DIGEST_9),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="baseline_restoration_receipt",
                record_id=f"receipt_with_{forbidden_field}",
                payload={
                    **VALID_PAYLOADS["baseline_restoration_receipt"],
                    forbidden_field: value,
                },
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_restored_baseline_smoke_contract_and_receipt_bind_exact_w4_evidence() -> None:
    smoke_contract = ControlRecord.build(
        kind="restored_baseline_smoke_contract",
        record_id="restored_baseline_smoke_contract_1",
        payload={
            "assignment_digest": DIGEST_1,
            "attestation_authorization_digest": DIGEST_2,
            "expected_outcome": "pass",
            "gate_digest": DIGEST_3,
            "restored_protected_state_digest": DIGEST_4,
            "smoke_contract_id": "restored_baseline_smoke_1",
            "target_digest": DIGEST_5,
            "validation_contract_digest": DIGEST_6,
            "validator_digest": DIGEST_7,
        },
    )
    receipt = ControlRecord.build(
        kind="baseline_restoration_receipt",
        record_id="baseline_restoration_receipt_with_smoke_contract",
        payload={
            **VALID_PAYLOADS["baseline_restoration_receipt"],
            "phase_establishing_operation_obligation_digest": DIGEST_1,
            "post_restoration_smoke_contract_digest": smoke_contract.digest(),
            "prevalidated_promotion_contract_digest": DIGEST_2,
            "restored_fence_epoch": 7,
            "restored_projection_digest": DIGEST_3,
        },
    )

    assert smoke_contract.payload["expected_outcome"] == "pass"
    assert receipt.payload["post_restoration_smoke_contract_digest"] == (
        smoke_contract.digest()
    )
    assert receipt.payload["restored_fence_epoch"] == 7


def test_service_anchor_receipt_identifies_the_exact_w5_transition() -> None:
    receipt = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service_anchor_receipt_record_1",
        payload=VALID_PAYLOADS["service_anchor_receipt"],
    )

    assert set(receipt.payload) == {
        "active_evidence_cut_digest",
        "active_phase_operation_terminal_digest",
        "active_promotion_contract_digest",
        "anchor_id",
        "backend_provenance_digest",
        "establishing_operation_digest",
        "expires_at",
        "generation_digest",
        "issued_at",
        "operation_terminal_digest",
        "process_epoch",
        "readiness_digest",
        "service_protected_state_digest",
        "target_digest",
    }
    for forbidden_field, value in (
        ("active_authority_proof_digest", DIGEST_8),
        ("fence_epoch", 2),
        ("projection_id", "active_service"),
        ("state_digest", DIGEST_9),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="service_anchor_receipt",
                record_id=f"service_anchor_receipt_with_{forbidden_field}",
                payload={
                    **VALID_PAYLOADS["service_anchor_receipt"],
                    forbidden_field: value,
                },
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_service_anchor_binds_process_epoch_provenance_health_and_five_minute_lease() -> None:
    provenance = ControlRecord.build(
        kind="backend_provenance",
        record_id="backend_provenance_service_epoch_1",
        payload={
            "authorization_digest": DIGEST_1,
            "backend_id": "lemonade_hip",
            "backend_manifest_digest": DIGEST_2,
            "configuration_digest": DIGEST_3,
            "driver_device_digest": DIGEST_4,
            "generation_digest": DIGEST_5,
            "model_identity_digest": DIGEST_6,
            "observed_at": "2026-08-12T09:56:00Z",
            "observer_identity_digest": DIGEST_7,
            "package_manifest_digest": DIGEST_8,
            "process_epoch": "process_epoch_1",
            "provenance_id": "service_epoch_1_provenance",
            "service_protected_state_digest": DIGEST_9,
            "target_digest": DIGEST_1,
        },
    )
    health = ControlRecord.build(
        kind="service_health_observation",
        record_id="service_health_observation_epoch_1",
        payload={
            "authorization_digest": DIGEST_1,
            "backend_provenance_digest": provenance.digest(),
            "generation_digest": DIGEST_5,
            "observation_id": "service_epoch_1_health",
            "observed_at": "2026-08-12T09:57:00Z",
            "observer_identity_digest": DIGEST_7,
            "process_epoch": "process_epoch_1",
            "service_protected_state_digest": DIGEST_9,
            "status": "ready",
            "target_digest": DIGEST_1,
        },
    )
    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness_service_epoch_1",
        payload={
            "backend_provenance_digest": provenance.digest(),
            "generation_digest": DIGEST_5,
                "backend_manifest_digest": DIGEST_2,
            "observed_at": "2026-08-12T09:58:00Z",
            "process_epoch": "process_epoch_1",
            "service_health_observation_digests": [health.digest()],
            "service_protected_state_digest": DIGEST_9,
            "status": "ready",
            "target_digest": DIGEST_1,
        },
    )
    receipt = ControlRecord.build(
        kind="service_anchor_receipt",
        record_id="service_anchor_receipt_epoch_1",
        payload={
            **VALID_PAYLOADS["service_anchor_receipt"],
            "active_phase_operation_terminal_digest": DIGEST_8,
            "backend_provenance_digest": provenance.digest(),
            "expires_at": "2026-08-12T10:05:00Z",
            "issued_at": "2026-08-12T10:00:00Z",
            "process_epoch": "process_epoch_1",
            "readiness_digest": readiness.digest(),
        },
    )

    assert readiness.payload["service_health_observation_digests"] == (
        health.digest(),
    )
    assert receipt.payload["expires_at"] == "2026-08-12T10:05:00Z"


@pytest.mark.parametrize(
    "expires_at",
    (
        "2026-08-12T10:04:59Z",
        "2026-08-12T10:05:01Z",
        "2026-08-12T09:59:59Z",
    ),
)
def test_service_anchor_health_lease_is_exactly_five_minutes(expires_at: str) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="service_anchor_receipt",
            record_id="service_anchor_receipt_with_invalid_lease",
            payload={
                **VALID_PAYLOADS["service_anchor_receipt"],
                "expires_at": expires_at,
            },
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_final_service_anchor_is_a_closed_post_restart_five_minute_lease() -> None:
    receipt = ControlRecord.build(
        kind="final_service_anchor_receipt",
        record_id="final_service_anchor_receipt_1",
        payload=VALID_PAYLOADS["final_service_anchor_receipt"],
    )

    assert receipt.payload["predecessor_service_anchor_receipt_digest"] == DIGEST_6
    assert receipt.payload["final_restart_operation_terminal_digest"] == DIGEST_4
    assert "acceptance_request_digest" not in receipt.payload

    for expires_at in (
        "2026-08-12T10:04:59Z",
        "2026-08-12T10:05:01Z",
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="final_service_anchor_receipt",
                record_id="final_service_anchor_invalid_lease",
                payload={
                    **VALID_PAYLOADS["final_service_anchor_receipt"],
                    "expires_at": expires_at,
                },
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_promotion_contract_restoration_and_service_anchors_are_phase_specific() -> None:
    active = {
        **VALID_PAYLOADS["promotion_contract"],
        "baseline_restoration_receipt_digest": DIGEST_7,
        "phase": "active",
    }
    assert ControlRecord.build(
        kind="promotion_contract",
        record_id="active_contract_with_restoration_receipt",
        payload=active,
    ).payload["baseline_restoration_receipt_digest"] == DIGEST_7

    for missing_field in (
        "baseline_restoration_receipt_digest",
        "phase_establishing_operation_obligation_digest",
    ):
        invalid = deepcopy(active)
        invalid.pop(missing_field)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="promotion_contract",
                record_id=f"active_contract_missing_{missing_field}",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    accepted = {
        **VALID_PAYLOADS["promotion_contract"],
        "acceptance_authorization_digest": DIGEST_6,
        "phase": "accepted",
        "predecessor_service_anchor_receipt_digest": DIGEST_7,
    }
    accepted.pop("phase_establishing_operation_obligation_digest")
    assert ControlRecord.build(
        kind="promotion_contract",
        record_id="accepted_contract_with_service_anchor",
        payload=accepted,
    ).payload["predecessor_service_anchor_receipt_digest"] == DIGEST_7

    missing_predecessor_anchor = deepcopy(accepted)
    missing_predecessor_anchor.pop("predecessor_service_anchor_receipt_digest")
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="promotion_contract",
            record_id="accepted_contract_without_predecessor_service_anchor",
            payload=missing_predecessor_anchor,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    legacy_service_state = deepcopy(accepted)
    legacy_service_state.pop("predecessor_service_anchor_receipt_digest")
    legacy_service_state["active_service_protected_state_digest"] = DIGEST_7
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="promotion_contract",
            record_id="accepted_contract_with_legacy_service_state",
            payload=legacy_service_state,
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD

    for phase, forbidden_field in (
        ("published", "baseline_restoration_receipt_digest"),
        ("prevalidated", "baseline_restoration_receipt_digest"),
        ("accepted", "baseline_restoration_receipt_digest"),
        ("published", "predecessor_service_anchor_receipt_digest"),
        ("prevalidated", "predecessor_service_anchor_receipt_digest"),
        ("active", "predecessor_service_anchor_receipt_digest"),
    ):
        payload = {
            **VALID_PAYLOADS["promotion_contract"],
            forbidden_field: DIGEST_7,
            "phase": phase,
        }
        if phase == "active":
            payload["baseline_restoration_receipt_digest"] = DIGEST_8
        if phase == "accepted":
            payload["acceptance_authorization_digest"] = DIGEST_6
            payload.pop("phase_establishing_operation_obligation_digest")
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="promotion_contract",
                record_id=f"{phase}_contract_with_{forbidden_field}",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_evidence_cut_and_proof_bind_one_capability_per_operation_terminal() -> None:
    for kind in ("atomic_evidence_cut", "promotion_authority_proof"):
        valid = {
            **VALID_PAYLOADS[kind],
            "capability_digests": [DIGEST_1],
            "operation_digests": [DIGEST_2],
            "operation_terminal_digests": [DIGEST_3],
        }
        assert ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_with_operation",
            payload=valid,
        ).payload["capability_digests"] == (DIGEST_1,)

        for field in (
            "capability_digests",
            "operation_digests",
            "operation_terminal_digests",
        ):
            invalid = deepcopy(valid)
            invalid[field] = []
            with pytest.raises(RecordValidationError) as caught:
                ControlRecord.build(
                    kind=kind,
                    record_id=f"{kind}_{field}_invalid",
                    payload=invalid,
                )
            assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

        duplicate = deepcopy(valid)
        duplicate["capability_digests"] = [DIGEST_1, DIGEST_1]
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind=kind,
                record_id=f"{kind}_duplicate_capability",
                payload=duplicate,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


def test_promotion_authority_proof_acceptance_fields_are_accepted_only() -> None:
    accepted = {
        **VALID_PAYLOADS["promotion_authority_proof"],
        "acceptance_request_digest": DIGEST_6,
        "approval_digest": DIGEST_7,
        "final_service_anchor_receipt_digest": DIGEST_8,
        "phase": "accepted",
    }
    assert ControlRecord.build(
        kind="promotion_authority_proof",
        record_id="promotion_authority_proof_accepted",
        payload=accepted,
    ).payload["approval_digest"] == DIGEST_7

    for field in (
        "acceptance_request_digest",
        "approval_digest",
        "final_service_anchor_receipt_digest",
    ):
        invalid = deepcopy(accepted)
        invalid.pop(field)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="promotion_authority_proof",
                record_id=f"promotion_authority_proof_missing_{field}",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    forbidden = {
        **VALID_PAYLOADS["promotion_authority_proof"],
        "acceptance_request_digest": DIGEST_6,
        "approval_digest": DIGEST_7,
        "final_service_anchor_receipt_digest": DIGEST_8,
    }
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="promotion_authority_proof",
            record_id="promotion_authority_proof_nonaccepted",
            payload=forbidden,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    ("generation_class", "phase"),
    [
        ("c", "published"),
        ("c", "prevalidated"),
        ("c", "active"),
    ],
)
def test_c_lifecycle_checkpoints_bind_exact_promotion_material(
    generation_class: str,
    phase: str,
) -> None:
    payload = {
        **VALID_PAYLOADS["lifecycle_checkpoint"],
        "generation_class": generation_class,
        "phase": phase,
    }
    assert ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"{generation_class}_{phase}_checkpoint",
        payload=payload,
    ).payload["authority_proof_digest"] == DIGEST_4

    for field in (
        "authority_proof_digest",
        "contract_digest",
        "evidence_cut_digest",
        "predecessor_checkpoint_digest",
    ):
        invalid = deepcopy(payload)
        invalid.pop(field)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id=f"{generation_class}_{phase}_missing_{field}",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="lifecycle_checkpoint",
            record_id=f"{generation_class}_{phase}_with_root_authorization",
            payload={**payload, "root_authorization_digest": DIGEST_8},
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_prevalidated_checkpoint_alone_may_bind_baseline_restoration() -> None:
    prevalidated = {
        **VALID_PAYLOADS["lifecycle_checkpoint"],
        "baseline_restoration_receipt_digest": DIGEST_8,
    }
    assert ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="prevalidated_checkpoint_with_baseline_restoration",
        payload=prevalidated,
    ).payload["baseline_restoration_receipt_digest"] == DIGEST_8

    for phase in ("published", "active", "accepted", "foundation_validation"):
        payload = {**prevalidated, "phase": phase}
        if phase == "accepted":
            payload.update(
                {
                    "acceptance_request_digest": DIGEST_8,
                    "approval_digest": DIGEST_9,
                }
            )
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id=f"{phase}_checkpoint_with_baseline_restoration",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_active_checkpoint_alone_may_authorize_a_service_anchor() -> None:
    active = {
        **VALID_PAYLOADS["lifecycle_checkpoint"],
        "phase": "active",
        "service_anchor_receipt_digest": DIGEST_9,
    }
    assert ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="active_checkpoint_with_service_anchor",
        payload=active,
    ).payload["service_anchor_receipt_digest"] == DIGEST_9

    for phase in (
        "published",
        "prevalidated",
        "accepted",
        "foundation_validation",
    ):
        payload = {**active, "phase": phase}
        if phase == "accepted":
            payload.update(
                {
                    "acceptance_request_digest": DIGEST_8,
                    "approval_digest": DIGEST_9,
                }
            )
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id=f"{phase}_checkpoint_with_service_anchor",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_captured_checkpoint_is_an_authorized_material_free_root() -> None:
    root = {
        "checkpoint_id": "b0_root_checkpoint",
        "established_at": TIMESTAMP,
        "generation_class": "b0",
        "generation_digest": DIGEST_1,
        "phase": "captured",
        "root_authorization_digest": DIGEST_2,
        "target_digest": DIGEST_3,
        "target_protected_state_digest": DIGEST_4,
    }
    assert ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="b0_root_checkpoint_record",
        payload=root,
    ).payload["root_authorization_digest"] == DIGEST_2

    for changes in (
        {"root_authorization_digest": None},
        {"authority_proof_digest": DIGEST_5},
        {"contract_digest": DIGEST_5},
        {"evidence_cut_digest": DIGEST_5},
        {"predecessor_checkpoint_digest": DIGEST_5},
    ):
        invalid = deepcopy(root)
        for field, value in changes.items():
            if value is None:
                invalid.pop(field)
            else:
                invalid[field] = value
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id="b0_root_checkpoint_invalid",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_foundation_checkpoint_is_structural_and_forbids_promotion_material() -> None:
    foundation = {
        "checkpoint_id": "foundation_checkpoint",
        "established_at": TIMESTAMP,
        "generation_class": "f",
        "generation_digest": DIGEST_1,
        "phase": "foundation_validation",
        "predecessor_checkpoint_digest": DIGEST_2,
        "target_digest": DIGEST_3,
        "target_protected_state_digest": DIGEST_4,
    }

    record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="foundation_checkpoint_record",
        payload=foundation,
    )

    assert record.payload["predecessor_checkpoint_digest"] == DIGEST_2
    for forbidden_field in (
        "authority_proof_digest",
        "contract_digest",
        "evidence_cut_digest",
        "acceptance_request_digest",
        "approval_digest",
        "baseline_restoration_receipt_digest",
        "final_service_anchor_receipt_digest",
        "root_authorization_digest",
        "service_anchor_receipt_digest",
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id=f"foundation_checkpoint_with_{forbidden_field}",
                payload={**foundation, forbidden_field: DIGEST_5},
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_accepted_checkpoint_requires_request_approval_and_final_anchor() -> None:
    accepted = {
        **VALID_PAYLOADS["lifecycle_checkpoint"],
        "acceptance_request_digest": DIGEST_8,
        "approval_digest": DIGEST_9,
        "final_service_anchor_receipt_digest": DIGEST_6,
        "phase": "accepted",
    }
    assert ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id="accepted_checkpoint",
        payload=accepted,
    ).payload["acceptance_request_digest"] == DIGEST_8

    for field in (
        "acceptance_request_digest",
        "approval_digest",
        "final_service_anchor_receipt_digest",
    ):
        invalid = deepcopy(accepted)
        invalid.pop(field)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="lifecycle_checkpoint",
                record_id=f"accepted_checkpoint_missing_{field}",
                payload=invalid,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    forbidden = {
        **VALID_PAYLOADS["lifecycle_checkpoint"],
        "acceptance_request_digest": DIGEST_8,
        "approval_digest": DIGEST_9,
        "final_service_anchor_receipt_digest": DIGEST_6,
    }
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="lifecycle_checkpoint",
            record_id="prevalidated_checkpoint_with_acceptance",
            payload=forbidden,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    ("generation_class", "phase"),
    [
        ("b0", "published"),
        ("f", "active"),
        ("c", "captured"),
        ("c", "foundation_validation"),
    ],
)
def test_lifecycle_checkpoint_rejects_invalid_class_phase_pairs(
    generation_class: str,
    phase: str,
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="lifecycle_checkpoint",
            record_id="invalid_lifecycle_checkpoint",
            payload={
                **VALID_PAYLOADS["lifecycle_checkpoint"],
                "generation_class": generation_class,
                "phase": phase,
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_evidence_cut_forbids_acceptance_and_final_anchor_backedges() -> None:
    for field in (
        "acceptance_request_digest",
        "approval_digest",
        "final_service_anchor_receipt_digest",
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="atomic_evidence_cut",
                record_id=f"atomic_cut_with_{field}",
                payload={
                    **VALID_PAYLOADS["atomic_evidence_cut"],
                    field: DIGEST_9,
                },
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_acceptance_request_is_closed_and_does_not_point_to_authority_proof() -> None:
    request = ControlRecord.build(
        kind="acceptance_request",
        record_id="acceptance_request_record_1",
        payload=VALID_PAYLOADS["acceptance_request"],
    )
    assert request.payload["predecessor_checkpoint_digest"] == DIGEST_4
    assert request.payload["final_service_anchor_receipt_digest"] == DIGEST_8

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="acceptance_request",
            record_id="acceptance_request_record_cycle",
            payload={
                **VALID_PAYLOADS["acceptance_request"],
                "authority_proof_digest": DIGEST_8,
            },
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_composite_authority_manifest_binds_generation_and_quorum_projections() -> None:
    payload = {
        **VALID_PAYLOADS["composite_authority"],
        "accepted_generation_digest": DIGEST_2,
        "quorum_policy_digest": DIGEST_3,
        "rollback_generation_digest": DIGEST_4,
    }
    manifest = ControlRecord.build(
        kind="composite_authority",
        record_id="complete_composite_authority",
        payload=payload,
    )
    assert manifest.payload["accepted_generation_digest"] == DIGEST_2
    assert manifest.payload["rollback_generation_digest"] == DIGEST_4
    assert manifest.payload["quorum_policy_digest"] == DIGEST_3

    for field in (
        "accepted_generation_digest",
        "rollback_generation_digest",
        "quorum_policy_digest",
    ):
        incomplete = deepcopy(payload)
        incomplete.pop(field)
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="composite_authority",
                record_id=f"composite_authority_missing_{field}",
                payload=incomplete,
            )
        assert caught.value.code is RecordErrorCode.MISSING_PAYLOAD_FIELD


def test_installed_inventory_is_a_closed_composite_projection() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "configuration_digest": DIGEST_2,
        "driver_device_digest": DIGEST_3,
        "generation_digest": DIGEST_4,
        "inventory_id": "installed_inventory_1",
        "model_identity_digests": [DIGEST_5, DIGEST_6],
        "observed_at": TIMESTAMP,
        "observer_identity_digest": DIGEST_7,
        "package_manifest_digest": DIGEST_8,
    }
    inventory = ControlRecord.build(
        kind="installed_inventory",
        record_id="installed_inventory_1",
        payload=payload,
    )
    assert inventory.payload["model_identity_digests"] == (
        DIGEST_5,
        DIGEST_6,
    )

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
                kind="installed_inventory",
                record_id="installed_inventory_with_opaque_payload",
                payload={**payload, "inventory_payload": {}},
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_rollback_registry_selects_one_exact_registered_rollback() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "established_at": TIMESTAMP,
        "registry_head_digest": DIGEST_2,
        "registry_id": "rollback_registry_1",
        "rollback_digests": [DIGEST_3, DIGEST_4],
        "selected_rollback_digest": DIGEST_4,
    }
    registry = ControlRecord.build(
        kind="rollback_registry",
        record_id="rollback_registry_1",
        payload=payload,
    )
    assert registry.payload["selected_rollback_digest"] == DIGEST_4

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="rollback_registry",
            record_id="rollback_registry_unregistered_selection",
            payload={**payload, "selected_rollback_digest": DIGEST_5},
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_recovery_policy_binds_closed_roots_contracts_and_owner_roles() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "policy_id": "recovery_policy_1",
        "recovery_contract_digests": [DIGEST_2, DIGEST_3],
        "recovery_owner_roles": ["operator", "recovery_owner"],
        "recovery_root_digest": DIGEST_4,
        "separation_policy_digest": DIGEST_5,
        "validity_policy_digest": DIGEST_6,
    }
    policy = ControlRecord.build(
        kind="recovery_policy",
        record_id="recovery_policy_1",
        payload=payload,
    )
    assert policy.payload["recovery_owner_roles"] == (
        "operator",
        "recovery_owner",
    )

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="recovery_policy",
            record_id="unordered_recovery_policy",
            payload={
                **payload,
                "recovery_owner_roles": ["recovery_owner", "operator"],
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_composite_fallback_reference_binds_one_prior_committed_manifest() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "committed_checkpoint_digest": DIGEST_2,
        "reference_id": "composite_fallback_1",
        "referenced_manifest_digest": DIGEST_3,
    }
    fallback = ControlRecord.build(
        kind="composite_fallback_reference",
        record_id="composite_fallback_reference_1",
        payload=payload,
    )
    assert fallback.payload["committed_checkpoint_digest"] == DIGEST_2

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="composite_fallback_reference",
            record_id="composite_fallback_with_unbound_head",
            payload={**payload, "register_head_digest": DIGEST_4},
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_composite_checkpoint_requires_a_closed_signature_over_the_exact_register() -> None:
    payload = {
        "authorization_digest": DIGEST_1,
        "change_set_digest": DIGEST_8,
        "checkpoint_id": "composite_checkpoint_1",
        "committed_at": TIMESTAMP,
        "quorum_receipt_digests": [DIGEST_2, DIGEST_3],
        "register_head_digest": DIGEST_4,
        "register_id": "composite_register",
        "register_observation_digest": DIGEST_5,
        "register_sequence": 7,
        "selected_manifest_digest": DIGEST_6,
        "signer_identity_digest": DIGEST_7,
    }
    signing_digest = ControlRecord.signing_digest(
        kind="composite_authority_checkpoint",
        record_id="composite_authority_checkpoint_1",
        payload=payload,
    )
    signature = {
        "algorithm": "ed25519",
        "signed_digest": signing_digest,
        "signer_identity_digest": DIGEST_7,
        "value": (
            "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
            "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
        ),
    }
    checkpoint = ControlRecord.build(
        kind="composite_authority_checkpoint",
        record_id="composite_authority_checkpoint_1",
        payload=payload,
        signature=signature,
    )
    assert checkpoint.digest() == signing_digest

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="composite_authority_checkpoint",
            record_id="unsigned_composite_authority_checkpoint",
            payload=payload,
        )
    assert caught.value.code is RecordErrorCode.INVALID_SIGNATURE

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="composite_authority_checkpoint",
            record_id="wrong_signer_composite_authority_checkpoint",
            payload=payload,
            signature={**signature, "signer_identity_digest": DIGEST_8},
        )
    assert caught.value.code is RecordErrorCode.INVALID_SIGNATURE


def test_composite_change_set_separates_normal_transition_from_reinstatement() -> None:
    normal = {
        "authorization_action": "transition_composite_authority",
        "authorization_digest": DIGEST_1,
        "candidate_manifest_digest": DIGEST_2,
        "change_set_id": "normal_change_set",
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
    }
    transition = ControlRecord.build(
        kind="composite_change_set",
        record_id="normal_change_set",
        payload=normal,
    )
    assert transition.payload["generation_binding"]["mode"] == (
        "required_generation"
    )

    reinstatement = {
        **normal,
        "candidate_manifest_digest": DIGEST_5,
        "changed_fields": [],
        "change_set_id": "register_reinstatement",
        "current_authority_register_observation_digest": DIGEST_7,
        "generation_binding": {"mode": "no_generation"},
        "quorum_mode": "recovery_root",
        "authorization_action": "reinstate_composite_authority",
        "prior_committed_checkpoint_digest": DIGEST_6,
        "transition_mode": "register_reinstatement",
    }
    restored = ControlRecord.build(
        kind="composite_change_set",
        record_id="register_reinstatement",
        payload=reinstatement,
    )
    assert restored.payload["changed_fields"] == ()

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="composite_change_set",
            record_id="legacy_caller_selected_binding_mode",
            payload={**normal, "binding_mode": "required_generation"},
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD

    invalid_variants = (
        {**normal, "rollback_manifest_digest": DIGEST_6},
        {**normal, "changed_fields": []},
        {**normal, "changed_fields": ["fallback", "active_generation"]},
        {
            **normal,
            "changed_fields": ["fallback", "quorum_policy"],
            "quorum_mode": "existing",
        },
        {**normal, "quorum_mode": "joint_consensus"},
        {**normal, "current_authority_register_observation_digest": DIGEST_7},
        {**reinstatement, "candidate_manifest_digest": DIGEST_6},
        {**reinstatement, "changed_fields": ["fallback"]},
        {**reinstatement, "quorum_mode": "existing"},
        {**reinstatement, "prior_committed_checkpoint_digest": None},
        {
            **reinstatement,
            "current_authority_register_observation_digest": None,
        },
        {**reinstatement, "authorization_action": "transition_composite_authority"},
        {
            **reinstatement,
            "generation_binding": {
                "generation_digest": DIGEST_4,
                "mode": "required_generation",
            },
        },
    )
    for index, payload in enumerate(invalid_variants):
        payload = {key: value for key, value in payload.items() if value is not None}
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="composite_change_set",
                record_id=f"invalid_composite_change_set_{index}",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    ("transition_mode", "changed_fields", "generation_binding"),
    [
        (
            "control_update",
            ["fallback", "inventory"],
            {"mode": "no_generation"},
        ),
        (
            "activation",
            ["active_generation", "fallback"],
            {"generation_digest": DIGEST_4, "mode": "required_generation"},
        ),
        (
            "acceptance",
            ["accepted_generation", "fallback"],
            {"generation_digest": DIGEST_4, "mode": "required_generation"},
        ),
    ],
)
def test_composite_transition_modes_constrain_generation_pointer_changes(
    transition_mode: str,
    changed_fields: list[str],
    generation_binding: dict[str, str],
) -> None:
    payload = {
        "authorization_action": "transition_composite_authority",
        "authorization_digest": DIGEST_1,
        "candidate_manifest_digest": DIGEST_2,
        "change_set_id": f"{transition_mode}_change_set",
        "changed_fields": changed_fields,
        "coordinator_identity_digest": DIGEST_3,
        "generation_binding": generation_binding,
        "old_manifest_digest": DIGEST_5,
        "quorum_mode": "existing",
        "rollback_manifest_digest": DIGEST_5,
        "terminal_rule": "conjunctive",
        "transition_mode": transition_mode,
    }
    assert ControlRecord.build(
        kind="composite_change_set",
        record_id=f"{transition_mode}_change_set",
        payload=payload,
    ).payload["transition_mode"] == transition_mode

    invalid = deepcopy(payload)
    invalid["changed_fields"] = (
        ["active_generation", "fallback"]
        if transition_mode != "activation"
        else ["accepted_generation", "fallback"]
    )
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="composite_change_set",
            record_id=f"invalid_{transition_mode}_change_set",
            payload=invalid,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_composite_quorum_material_is_closed_ordered_and_content_addressed() -> None:
    roster = ControlRecord.build(
        kind="witness_roster",
        record_id="witness_roster_1",
        payload={
            "roster_id": "witness_roster_1",
            "witness_identity_digests": [DIGEST_1, DIGEST_2],
        },
    )
    policy = ControlRecord.build(
        kind="quorum_policy",
        record_id="quorum_policy_1",
        payload={
            "policy_id": "quorum_policy_1",
            "threshold": 2,
            "witness_roster_digest": roster.digest(),
        },
    )
    receipt = ControlRecord.build(
        kind="quorum_receipt",
        record_id="quorum_receipt_1",
        payload={
            "approval_digests": [DIGEST_3, DIGEST_4],
            "approved_at": TIMESTAMP,
            "authorization_digest": DIGEST_5,
            "change_set_digest": DIGEST_6,
            "quorum_policy_digest": policy.digest(),
            "receipt_id": "quorum_receipt_1",
            "side": "existing",
            "witness_roster_digest": roster.digest(),
        },
    )
    assert receipt.payload["approval_digests"] == (DIGEST_3, DIGEST_4)

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="witness_roster",
            record_id="unordered_witness_roster",
            payload={
                "roster_id": "unordered_witness_roster",
                "witness_identity_digests": [DIGEST_2, DIGEST_1],
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="witness_roster",
            record_id="duplicate_witness_roster",
            payload={
                "roster_id": "duplicate_witness_roster",
                "witness_identity_digests": [DIGEST_1, DIGEST_1],
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="quorum_policy",
            record_id="zero_threshold_policy",
            payload={
                "policy_id": "zero_threshold_policy",
                "threshold": 0,
                "witness_roster_digest": roster.digest(),
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="quorum_receipt",
            record_id="duplicate_quorum_receipt",
            payload={
                **dict(receipt.payload),
                "approval_digests": [DIGEST_3, DIGEST_3],
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


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
        ("recovery", {"exact_state_generation_digest": DIGEST_9}),
        (
            "rollback",
            {
                "generation_binding": {
                    "generation_digest": DIGEST_6,
                    "mode": "required_generation",
                }
            },
        ),
        ("rollback", {"target_generation_digest": DIGEST_9}),
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


@pytest.mark.parametrize(
    ("kind", "earlier_field", "later_field"),
    [
        ("capability", "issued_at", "expires_at"),
        ("retention_lease", "issued_at", "expires_at"),
    ],
)
def test_strict_timestamp_ordering_rejects_equivalent_fractional_instants(
    kind: str,
    earlier_field: str,
    later_field: str,
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    payload[earlier_field] = "2026-08-12T10:00:00.10Z"
    payload[later_field] = "2026-08-12T10:00:00.1Z"

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_non_strict_timestamp_ordering_accepts_equivalent_fractional_instants(
) -> None:
    payload = deepcopy(VALID_PAYLOADS["invalidation"])
    payload.update(
        {
            "closed_at": "2026-08-12T10:00:00.10Z",
            "opened_at": "2026-08-12T10:00:00.1Z",
            "status": "closed",
        }
    )

    record = ControlRecord.build(
        kind="invalidation",
        record_id="invalidation_record_1",
        payload=payload,
    )

    assert record.payload["closed_at"] == "2026-08-12T10:00:00.10Z"


@pytest.mark.parametrize(
    ("kind", "earlier_field", "later_field"),
    [
        ("capability", "issued_at", "expires_at"),
        ("retention_lease", "issued_at", "expires_at"),
    ],
)
def test_strict_timestamp_ordering_rejects_equivalent_rfc3339_offsets(
    kind: str,
    earlier_field: str,
    later_field: str,
) -> None:
    payload = deepcopy(VALID_PAYLOADS[kind])
    payload[earlier_field] = "2026-08-12T10:00:00Z"
    payload[later_field] = "2026-08-12T11:00:00+01:00"

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_record_1",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_non_strict_timestamp_ordering_accepts_equivalent_rfc3339_offsets() -> None:
    payload = deepcopy(VALID_PAYLOADS["invalidation"])
    payload.update(
        {
            "closed_at": "2026-08-12T11:00:00+01:00",
            "opened_at": "2026-08-12T10:00:00Z",
            "status": "closed",
        }
    )

    record = ControlRecord.build(
        kind="invalidation",
        record_id="invalidation_record_1",
        payload=payload,
    )

    assert record.payload["closed_at"] == "2026-08-12T11:00:00+01:00"


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
        "target_digest",
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


def test_operation_attestation_binds_the_exact_terminal_validator_observation() -> None:
    schema = RECORD_SCHEMAS["operation_attestation"]

    assert set(schema.required_fields) == {
        "observed_at",
        "operation_digest",
        "outcome",
        "poststate_digest",
        "subject_digest",
        "validator_digest",
    }
    assert not schema.optional_fields

    attestation = ControlRecord.build(
        kind="operation_attestation",
        record_id="operation_attestation_record_1",
        payload=VALID_PAYLOADS["operation_attestation"],
    )

    assert attestation.payload["validator_digest"] == DIGEST_4


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


def test_recovery_record_preserves_a_failed_b0_capture_sentinel() -> None:
    recovery = ControlRecord.build(
        kind="recovery",
        record_id="b0_recovery_record_1",
        payload={
            **VALID_PAYLOADS["recovery"],
            "generation_binding": {
                "generation_digest": DIGEST_7,
                "mode": "b0_capture_sentinel",
                "sentinel_digest": DIGEST_9,
            },
        },
    )

    assert recovery.payload["generation_binding"] == {
        "generation_digest": DIGEST_7,
        "mode": "b0_capture_sentinel",
        "sentinel_digest": DIGEST_9,
    }
    assert recovery.payload["origin_generation_digest"] == DIGEST_7
    assert recovery.payload["destination_generation_digest"] == DIGEST_2


def test_rollback_record_binds_the_exact_destination_snapshot_without_a_reverse_edge(
) -> None:
    protected_state = ControlRecord.build(
        kind="protected_state",
        record_id="rollback_protected_state_record_1",
        payload=VALID_PAYLOADS["protected_state"],
    )
    rollback = ControlRecord.build(
        kind="rollback",
        record_id="rollback_record_1",
        payload={
            **VALID_PAYLOADS["rollback"],
            "destination_generation_digest": protected_state.payload[
                "generation_digest"
            ],
            "target_generation_digest": protected_state.payload[
                "generation_digest"
            ],
            "target_protected_state_digest": protected_state.digest(),
            "target_state_digest": protected_state.payload["state_digest"],
        },
    )

    assert rollback.payload["target_protected_state_digest"] == protected_state.digest()
    assert rollback.payload["target_projection_digest"] == DIGEST_6
    assert rollback.payload["target_state_digest"] == DIGEST_2
    with pytest.raises(RecordValidationError) as reverse_edge:
        ControlRecord.build(
            kind="protected_state",
            record_id="rollback_protected_state_record_2",
            payload={
                **VALID_PAYLOADS["protected_state"],
                "rollback_digest": rollback.digest(),
            },
        )

    assert reverse_edge.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


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


def test_restricted_reference_and_retention_lease_form_a_realizable_one_way_dag(
) -> None:
    lease = ControlRecord.build(
        kind="retention_lease",
        record_id="retention_lease_record_1",
        payload=VALID_PAYLOADS["retention_lease"],
    )
    reference = ControlRecord.build(
        kind="restricted_reference",
        record_id="restricted_reference_record_1",
        payload={
            **VALID_PAYLOADS["restricted_reference"],
            "retention_lease_digest": lease.digest(),
        },
    )

    assert reference.payload["retention_lease_digest"] == lease.digest()
    assert "restricted_reference_digest" not in lease.payload
    with pytest.raises(RecordValidationError) as reverse_reference:
        ControlRecord.build(
            kind="retention_lease",
            record_id="retention_lease_record_2",
            payload={
                **VALID_PAYLOADS["retention_lease"],
                "restricted_reference_digest": reference.digest(),
            },
        )

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
    validation_contract_schema = RECORD_SCHEMAS["validation_contract"]

    assert set(obligation_schema.required_fields) == {
        "assignment_digest",
        "impact",
        "obligation_id",
        "occurrence_digest",
    }
    assert set(obligation_schema.optional_fields) == {
        "scenario_operation_obligation_digest"
    }
    assert set(contract_schema.required_fields) == {
        "contract_id",
        "expected_accepted_generation_digest",
        "expected_active_generation_digest",
        "generation_digest",
        "obligation_digests",
        "operation_obligation_set_digest",
        "operation_realization_set_digest",
        "phase",
        "predecessor_checkpoint_digest",
        "requirements_digest",
        "target_digest",
        "target_kind",
        "target_protected_state_digest",
        "validation_contract_digest",
    }
    assert set(contract_schema.optional_fields) == {
            "acceptance_authorization_digest",
            "baseline_restoration_receipt_digest",
            "phase_establishing_operation_obligation_digest",
            "predecessor_service_anchor_receipt_digest",
        }
    assert set(cut_schema.required_fields) == set(
        VALID_PAYLOADS["atomic_evidence_cut"]
    )
    assert set(validation_contract_schema.required_fields) == {
        "approval_digest",
        "assignments_digest",
        "authorization_policy_digest",
        "contract_id",
        "max_live_attempt_seconds",
        "max_suite_seconds",
        "operation_requirement_set_digest",
        "requirements_digest",
    }

    operation_obligation_schema = RECORD_SCHEMAS["operation_obligation"]
    assert set(operation_obligation_schema.required_fields) == {
        "generation_binding",
        "generation_class",
        "intent_digest",
        "lifecycle_phase",
        "obligation_id",
        "operation_kind",
        "operation_digest",
        "operation_requirement_digest",
        "subject_digest",
        "subject_kind",
        "target_id",
        "target_kind",
    }

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
    validation_contract = ControlRecord.build(
        kind="validation_contract",
        record_id="validation_contract_record_1",
        payload=VALID_PAYLOADS["validation_contract"],
    )

    assert obligation.payload["impact"] == "blocking"
    assert contract.payload["obligation_digests"] == (DIGEST_4, DIGEST_5)
    assert contract.payload["validation_contract_digest"] == DIGEST_9
    assert cut.payload["inclusion_edge_digests"] == ()
    assert cut.payload["operation_digests"] == ()
    assert cut.payload["operation_terminal_digests"] == ()
    assert validation_contract.payload["assignments_digest"] == DIGEST_2
    assert "operation_obligation_set_digest" not in validation_contract.payload

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="validation_contract",
            record_id="occurrence_bound_validation_contract",
            payload={
                **VALID_PAYLOADS["validation_contract"],
                "operation_obligation_set_digest": DIGEST_5,
            },
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD

    with pytest.raises(RecordValidationError) as mismatched_operation_terminals:
        ControlRecord.build(
            kind="atomic_evidence_cut",
            record_id="atomic_evidence_cut_record_2",
            payload={
                **VALID_PAYLOADS["atomic_evidence_cut"],
                "operation_digests": [DIGEST_1],
            },
        )

    assert mismatched_operation_terminals.value.code is (
        RecordErrorCode.INVALID_PAYLOAD_SEMANTICS
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            **VALID_PAYLOADS["operation_obligation"],
            "generation_binding": {
                "generation_digest": DIGEST_1,
                "mode": "required_generation",
            },
            "generation_class": "f",
            "lifecycle_phase": "foundation_validation",
            "operation_kind": "package_installation",
            "subject_digest": DIGEST_1,
            "subject_kind": "generation",
            "target_kind": "isolated_root",
        },
        {
            **VALID_PAYLOADS["operation_obligation"],
            "generation_binding": {
                "generation_digest": DIGEST_1,
                "mode": "b0_capture_sentinel",
                "sentinel_digest": DIGEST_9,
            },
            "generation_class": "b0",
            "lifecycle_phase": "captured",
            "operation_kind": "composite_authority_transition",
            "subject_digest": DIGEST_8,
            "subject_kind": "composite_authority",
            "target_id": "authority_register",
            "target_kind": "composite_register",
        },
    ],
)
def test_operation_obligations_represent_foundation_and_b0_coordinates(payload):
    obligation = ControlRecord.build(
        kind="operation_obligation",
        record_id=f"operation_obligation:{payload['generation_class']}",
        payload=payload,
    )

    assert obligation.payload["lifecycle_phase"] == payload["lifecycle_phase"]


@pytest.mark.parametrize(
    "changes",
    [
        {"generation_class": "c", "lifecycle_phase": "foundation_validation"},
        {"target_kind": "service"},
        {
            "generation_binding": {
                "generation_digest": DIGEST_1,
                "mode": "required_generation",
            },
            "generation_class": "b0",
            "lifecycle_phase": "captured",
            "operation_kind": "composite_authority_transition",
            "subject_digest": DIGEST_8,
            "subject_kind": "composite_authority",
            "target_kind": "composite_register",
        },
    ],
)
def test_operation_obligations_reject_impossible_authority_coordinates(changes):
    with pytest.raises(RecordValidationError) as exc_info:
        ControlRecord.build(
            kind="operation_obligation",
            record_id="operation_obligation:invalid",
            payload={**VALID_PAYLOADS["operation_obligation"], **changes},
        )

    assert exc_info.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_promotion_authority_proof_binds_the_exact_authority_view_and_cut() -> None:
    schema = RECORD_SCHEMAS["promotion_authority_proof"]

    assert set(schema.required_fields) == set(
        VALID_PAYLOADS["promotion_authority_proof"]
    )
    assert all(
        schema.required_fields[field].allow_empty
        for field in (
            "attempt_digests",
            "evaluation_digests",
            "inclusion_edge_digests",
            "operation_digests",
            "operation_terminal_digests",
        )
    )

    proof = ControlRecord.build(
        kind="promotion_authority_proof",
        record_id="promotion_authority_proof_record_1",
        payload=VALID_PAYLOADS["promotion_authority_proof"],
    )

    assert proof.payload["authority_adapter_identity_digest"] == DIGEST_3
    assert proof.payload["authority_view_digest"] == DIGEST_6

    invalid_payloads = [
        {
            **VALID_PAYLOADS["promotion_authority_proof"],
            "complete_through_sequence": 0,
        },
        {
            **VALID_PAYLOADS["promotion_authority_proof"],
            "operation_digests": [DIGEST_1],
        },
    ]
    for payload in invalid_payloads:
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="promotion_authority_proof",
                record_id="promotion_authority_proof_record_2",
                payload=payload,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_terminal_records_use_closed_gate_and_operation_variants() -> None:
    gate_terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="gate_terminal_record_1",
        payload=VALID_PAYLOADS["terminal_record"],
    )
    operation_payload = deepcopy(VALID_PAYLOADS["terminal_record"])
    operation_payload.pop("assignment_digest")
    operation_payload.pop("attempt_digest")
    operation_payload["capability_digest"] = DIGEST_2
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
    assert operation_terminal.payload["capability_digest"] == DIGEST_2
    assert "assignment_digest" not in operation_terminal.payload

    missing_capability = deepcopy(operation_payload)
    missing_capability.pop("capability_digest")
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="terminal_record",
            record_id="operation_terminal_without_capability",
            payload=missing_capability,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    gate_with_capability = {
        **VALID_PAYLOADS["terminal_record"],
        "capability_digest": DIGEST_3,
    }
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="terminal_record",
            record_id="gate_terminal_with_capability",
            payload=gate_with_capability,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_successful_critical_operation_terminal_requires_validator_evidence() -> None:
    operation_payload = deepcopy(VALID_PAYLOADS["terminal_record"])
    operation_payload.pop("assignment_digest")
    operation_payload.pop("attempt_digest")
    operation_payload.update(
        {
            "capability_digest": DIGEST_2,
            "operation_digest": DIGEST_3,
            "terminal_type": "critical_operation",
            "validator_attestation_digests": [],
        }
    )

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="terminal_record",
            record_id="successful_operation_without_validator_evidence",
            payload=operation_payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_false_predicate_gate_terminal_needs_no_validator_attestation() -> None:
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="false_predicate_gate_terminal",
        payload={
            **VALID_PAYLOADS["terminal_record"],
            "predicate_proof_digest": DIGEST_6,
            "validator_attestation_digests": [],
        },
    )

    assert terminal.payload["validator_attestation_digests"] == ()


def test_not_applicable_evaluation_binds_one_canonical_predicate_proof() -> None:
    proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="predicate_proof_record_1",
        payload=VALID_PAYLOADS["predicate_proof"],
    )
    payload = deepcopy(VALID_PAYLOADS["evaluation"])
    payload.update(
        {
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


def test_applicable_evaluation_may_bind_a_true_conditional_predicate_proof() -> None:
    proof_payload = {
        **VALID_PAYLOADS["predicate_proof"],
        "is_applicable": True,
    }
    proof = ControlRecord.build(
        kind="predicate_proof",
        record_id="true_predicate_proof",
        payload=proof_payload,
    )
    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="conditional_applicable_evaluation",
        payload={
            **VALID_PAYLOADS["evaluation"],
            "predicate_proof_digest": proof.digest(),
        },
    )
    terminal = ControlRecord.build(
        kind="terminal_record",
        record_id="conditional_applicable_terminal",
        payload={
            **VALID_PAYLOADS["terminal_record"],
            "predicate_proof_digest": proof.digest(),
        },
    )

    assert proof.payload["is_applicable"] is True
    assert evaluation.payload["predicate_proof_digest"] == proof.digest()
    assert terminal.payload["predicate_proof_digest"] == proof.digest()

    operation_terminal = {
        **VALID_PAYLOADS["terminal_record"],
        "capability_digest": DIGEST_1,
        "operation_digest": DIGEST_2,
        "predicate_proof_digest": proof.digest(),
        "terminal_type": "critical_operation",
    }
    operation_terminal.pop("assignment_digest")
    operation_terminal.pop("attempt_digest")
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="terminal_record",
            record_id="operation_terminal_with_predicate_proof",
            payload=operation_terminal,
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_readiness_names_the_exact_backend_manifest_projection() -> None:
    payload = deepcopy(VALID_PAYLOADS["readiness"])

    readiness = ControlRecord.build(
        kind="readiness",
        record_id="readiness_with_exact_backend_manifest",
        payload=payload,
    )
    assert readiness.payload["backend_manifest_digest"] == DIGEST_2

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="readiness",
            record_id="readiness_with_ambiguous_manifest",
            payload={**payload, "manifest_digest": DIGEST_2},
        )
    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_evaluation_preserves_historical_failure_without_claiming_admissibility() -> None:
    payload = deepcopy(VALID_PAYLOADS["evaluation"])
    payload["outcome"] = "fail"

    evaluation = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_record_1",
        payload=payload,
    )

    assert evaluation.payload["outcome"] == "fail"
    assert "admissible" not in evaluation.payload
    assert "currency" not in evaluation.payload


@pytest.mark.parametrize(
    ("reason", "attestation_digests", "predicate_proof_digest"),
    [
        ("missing_attestation", [], None),
        ("missing_attestation", [], DIGEST_3),
        ("missing_applicability_proof", [], None),
        ("applicability_proof_mismatch", [], DIGEST_3),
        ("assignment_mismatch", [DIGEST_2], None),
        ("assignment_mismatch", [DIGEST_2], DIGEST_3),
        ("subject_mismatch", [DIGEST_2], None),
        ("subject_mismatch", [DIGEST_2], DIGEST_3),
        ("gate_mismatch", [DIGEST_2], None),
        ("gate_mismatch", [DIGEST_2], DIGEST_3),
        ("context_mismatch", [DIGEST_2], None),
        ("context_mismatch", [DIGEST_2], DIGEST_3),
        ("dependency_mismatch", [DIGEST_2], None),
        ("dependency_mismatch", [DIGEST_2], DIGEST_3),
        ("separation_violation", [DIGEST_2], None),
        ("separation_violation", [DIGEST_2], DIGEST_3),
        ("reported_unknown", [DIGEST_2], None),
        ("reported_unknown", [DIGEST_2], DIGEST_3),
    ],
)
def test_applicable_unknown_evaluation_round_trips_exact_reason_and_provenance(
    reason: str,
    attestation_digests: list[str],
    predicate_proof_digest: str | None,
) -> None:
    payload = {
        **VALID_PAYLOADS["evaluation"],
        "applicability": "applicable_unknown",
        "attestation_digests": attestation_digests,
        "outcome": "unknown",
        "unknown_reason": reason,
    }
    if predicate_proof_digest is not None:
        payload["predicate_proof_digest"] = predicate_proof_digest

    record = ControlRecord.build(
        kind="evaluation",
        record_id=f"applicable_unknown_{reason}",
        payload=payload,
    )
    restored = ControlRecord.parse(record.canonical_bytes())

    assert restored.payload["unknown_reason"] == reason
    assert restored.payload["attestation_digests"] == tuple(attestation_digests)
    assert restored.payload.get("predicate_proof_digest") == predicate_proof_digest
    assert restored.canonical_bytes() == record.canonical_bytes()


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"attestation_digests": [DIGEST_2], "unknown_reason": "missing_attestation"},
        {"unknown_reason": "assignment_mismatch"},
        {
            "attestation_digests": [DIGEST_2, DIGEST_3],
            "unknown_reason": "assignment_mismatch",
        },
        {
            "predicate_proof_digest": DIGEST_3,
            "unknown_reason": "assignment_mismatch",
        },
        {"unknown_reason": "applicability_proof_mismatch"},
        {
            "attestation_digests": [DIGEST_2],
            "predicate_proof_digest": DIGEST_3,
            "unknown_reason": "applicability_proof_mismatch",
        },
        {
            "predicate_proof_digest": DIGEST_3,
            "unknown_reason": "missing_applicability_proof",
        },
    ],
)
def test_applicable_unknown_evaluation_rejects_incoherent_provenance(
    changes: dict[str, object],
) -> None:
    payload = {
        **VALID_PAYLOADS["evaluation"],
        "applicability": "applicable_unknown",
        "attestation_digests": [],
        "outcome": "unknown",
        **changes,
    }

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="evaluation",
            record_id="applicable_unknown_with_incoherent_provenance",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_PAYLOADS["evaluation"], "unknown_reason": "reported_unknown"},
        {
            **VALID_PAYLOADS["evaluation"],
            "applicability": "not_due",
            "attestation_digests": [],
            "outcome": "unknown",
            "unknown_reason": "missing_attestation",
        },
    ],
)
def test_non_unknown_evaluation_states_forbid_an_unknown_reason(
    payload: dict[str, object],
) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="evaluation",
            record_id="non_unknown_with_unknown_reason",
            payload=payload,
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_evaluation_rejects_an_unregistered_unknown_reason() -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="evaluation",
            record_id="evaluation_with_unregistered_unknown_reason",
            payload={
                **VALID_PAYLOADS["evaluation"],
                "applicability": "applicable_unknown",
                "attestation_digests": [],
                "outcome": "unknown",
                "unknown_reason": "ambiguous",
            },
        )

    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD


@pytest.mark.parametrize("field", ["admissible", "currency"])
def test_evaluation_rejects_self_asserted_admission_and_currency(field: str) -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="evaluation",
            record_id=f"evaluation_with_{field}",
            payload={
                **VALID_PAYLOADS["evaluation"],
                field: True if field == "admissible" else "current",
            },
        )

    assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_validity_policy_uses_one_closed_earliest_constituent_expiry_rule() -> None:
    policy = ControlRecord.build(
        kind="validity_policy",
        record_id="validity_policy_record_1",
        payload=VALID_PAYLOADS["validity_policy"],
    )

    assert policy.payload["expiry_rule"] == "earliest_constituent_expiry"
    assert policy.payload["attestation_max_age_seconds"] == 300
    assert policy.payload["predicate_proof_max_age_seconds"] == 300
    assert policy.payload["inclusion_edge_max_age_seconds"] == 28_800
    assert policy.payload["evidence_cut_max_age_seconds"] == 300

    event_valid = ControlRecord.build(
        kind="validity_policy",
        record_id="event_validity_policy_record_1",
        payload={
            "expiry_rule": "earliest_constituent_expiry",
            "policy_id": "event_validity_policy_1",
        },
    )
    assert set(event_valid.payload) == {"expiry_rule", "policy_id"}

    for changes, code in (
        ({"expiry_rule": "latest_constituent_expiry"}, RecordErrorCode.INVALID_PAYLOAD_FIELD),
        ({"attestation_max_age_seconds": -1}, RecordErrorCode.INVALID_PAYLOAD_FIELD),
        ({"max_age_seconds": 300}, RecordErrorCode.UNKNOWN_PAYLOAD_FIELD),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="validity_policy",
                record_id="invalid_validity_policy",
                payload={**VALID_PAYLOADS["validity_policy"], **changes},
            )
        assert caught.value.code is code


def test_dependency_projection_is_one_canonical_exact_mapping() -> None:
    projection = ControlRecord.build(
        kind="dependency_projection",
        record_id="dependency_projection_record_1",
        payload=VALID_PAYLOADS["dependency_projection"],
    )
    assert tuple(
        zip(
            projection.payload["dependency_keys"],
            projection.payload["dependency_digests"],
            strict=True,
        )
    ) == (
        ("driver/device", DIGEST_1),
        ("generation", DIGEST_2),
    )

    empty = ControlRecord.build(
        kind="dependency_projection",
        record_id="empty_dependency_projection_record_1",
        payload={
            "dependency_digests": [],
            "dependency_keys": [],
            "projection_id": "empty_dependency_projection_1",
        },
    )
    assert empty.payload["dependency_keys"] == ()

    shared_value = ControlRecord.build(
        kind="dependency_projection",
        record_id="shared_dependency_projection_record_1",
        payload={
            **VALID_PAYLOADS["dependency_projection"],
            "dependency_digests": [DIGEST_1, DIGEST_1],
        },
    )
    assert shared_value.payload["dependency_digests"] == (DIGEST_1, DIGEST_1)

    for changes in (
        {"dependency_digests": [DIGEST_1]},
        {"dependency_keys": ["generation", "driver/device"]},
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="dependency_projection",
                record_id="invalid_dependency_projection",
                payload={**VALID_PAYLOADS["dependency_projection"], **changes},
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


def test_invalidation_policy_is_a_canonical_dependency_key_set() -> None:
    empty = ControlRecord.build(
        kind="invalidation_policy",
        record_id="event_valid_invalidation_policy_record_1",
        payload={
            "dependency_keys": [],
            "policy_id": "event_valid_invalidation_policy_1",
        },
    )
    assert empty.payload["dependency_keys"] == ()

    for dependency_keys, code in (
        (["generation", "driver/device"], RecordErrorCode.INVALID_PAYLOAD_SEMANTICS),
        (["generation", "generation"], RecordErrorCode.INVALID_PAYLOAD_FIELD),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="invalidation_policy",
                record_id="invalid_invalidation_policy_record_1",
                payload={
                    "dependency_keys": dependency_keys,
                    "policy_id": "invalidation_policy_1",
                },
            )
        assert caught.value.code is code


def test_currency_proof_binds_authoritative_inputs_without_asserting_currentness() -> None:
    checkpoint = ControlRecord.build(
        kind="invalidation_stream_checkpoint",
        record_id="invalidation_stream_checkpoint_record_1",
        payload=VALID_PAYLOADS["invalidation_stream_checkpoint"],
    )
    observation = ControlRecord.build(
        kind="trusted_time_observation",
        record_id="trusted_time_observation_record_1",
        payload=VALID_PAYLOADS["trusted_time_observation"],
    )
    proof = ControlRecord.build(
        kind="evidence_currency_proof",
        record_id="evidence_currency_proof_record_1",
        payload={
            **VALID_PAYLOADS["evidence_currency_proof"],
            "invalidation_stream_checkpoint_digest": checkpoint.digest(),
            "trusted_time_observation_digest": observation.digest(),
        },
    )

    assert proof.payload["evaluation_digest"] == DIGEST_2
    assert "currency" not in proof.payload
    assert "admissible" not in proof.payload
    assert "atomic_evidence_cut_digest" not in proof.payload

    for forbidden_field, value in (
        ("currency", "current"),
        ("admissible", True),
        ("atomic_evidence_cut_digest", DIGEST_7),
        ("currency_proof_digest", DIGEST_8),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind="evidence_currency_proof",
                record_id=f"currency_proof_with_{forbidden_field}",
                payload={
                    **VALID_PAYLOADS["evidence_currency_proof"],
                    forbidden_field: value,
                },
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD


def test_invalidation_checkpoint_binds_authority_and_completeness_coordinates() -> None:
    checkpoint = ControlRecord.build(
        kind="invalidation_stream_checkpoint",
        record_id="invalidation_stream_checkpoint_record_1",
        payload=VALID_PAYLOADS["invalidation_stream_checkpoint"],
    )

    assert checkpoint.payload["complete_through_sequence"] == 42
    assert checkpoint.payload["stream_head_digest"] == DIGEST_8
    assert checkpoint.payload["authority_head_digest"] == DIGEST_1
    assert checkpoint.payload["authority_manifest_digest"] == DIGEST_2
    assert checkpoint.payload["authority_view_digest"] == DIGEST_3
    assert checkpoint.payload["completeness_proof_digest"] == DIGEST_4
    assert checkpoint.payload["fork_proof_digest"] == DIGEST_6

    for kind, payload in (
        ("invalidation_stream_checkpoint", VALID_PAYLOADS["invalidation_stream_checkpoint"]),
        ("trusted_time_observation", VALID_PAYLOADS["trusted_time_observation"]),
    ):
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind=kind,
                record_id=f"{kind}_with_self_asserted_currentness",
                payload={**payload, "current": True},
            )
        assert caught.value.code is RecordErrorCode.UNKNOWN_PAYLOAD_FIELD

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="invalidation_stream_checkpoint",
            record_id="empty_invalidation_stream_checkpoint",
            payload={
                **VALID_PAYLOADS["invalidation_stream_checkpoint"],
                "complete_through_sequence": 0,
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS


@pytest.mark.parametrize(
    "kind",
    ["atomic_evidence_cut", "promotion_authority_proof"],
)
def test_currency_provenance_is_one_to_one_with_evaluations(kind: str) -> None:
    valid = VALID_PAYLOADS[kind]
    assert ControlRecord.build(
        kind=kind,
        record_id=f"{kind}_with_currency_provenance",
        payload=valid,
    ).payload["currency_proof_digests"] == (DIGEST_9,)

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_missing_currency_provenance",
            payload={
                **valid,
                "currency_proof_digests": [DIGEST_7, DIGEST_9],
            },
        )
    assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_SEMANTICS

    empty = {
        **valid,
        "currency_proof_digests": [],
        "evaluation_digests": [],
    }
    if kind == "atomic_evidence_cut":
        with pytest.raises(RecordValidationError) as caught:
            ControlRecord.build(
                kind=kind,
                record_id="atomic_cut_without_evaluations",
                payload=empty,
            )
        assert caught.value.code is RecordErrorCode.INVALID_PAYLOAD_FIELD
    else:
        assert ControlRecord.build(
            kind=kind,
            record_id="authority_proof_without_evaluations",
            payload=empty,
        ).payload["currency_proof_digests"] == ()


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


@pytest.mark.parametrize("entrypoint", ["build", "signing_digest"])
def test_record_kind_entrypoints_reject_a_subclass_before_registry_lookup(
    entrypoint: str,
) -> None:
    hostile_kind = RegisteredKindImpostor("hostile_kind")

    with pytest.raises(ControlRecordError) as caught:
        getattr(ControlRecord, entrypoint)(
            kind=hostile_kind,
            record_id="identity_record_1",
            payload=VALID_PAYLOADS["identity"],
        )

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_ordinary_record_kind_round_trips_as_an_exact_string() -> None:
    record = ControlRecord.build(
        kind="identity",
        record_id="identity_round_trip",
        payload=VALID_PAYLOADS["identity"],
    )

    restored = ControlRecord.parse(record.canonical_bytes())

    assert type(record.kind) is str
    assert type(restored.kind) is str
    assert restored.digest() == record.digest()
    assert restored.canonical_bytes() == record.canonical_bytes()


@pytest.mark.parametrize("entrypoint", ["build", "signing_digest"])
def test_public_kind_entrypoints_reject_subclasses_before_semantic_checks(
    entrypoint: str,
) -> None:
    hostile_kind = PublicEnvelopeKindImpostor("hostile_kind")

    with pytest.raises(ControlRecordError) as caught:
        getattr(ControlRecord, entrypoint)(
            kind=hostile_kind,
            record_id="identity_record_1",
            payload=VALID_PAYLOADS["identity"],
        )

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


@pytest.mark.parametrize("entrypoint", ["build", "signing_digest"])
def test_record_factories_reject_a_control_record_subclass(
    entrypoint: str,
) -> None:
    with pytest.raises(ControlRecordError) as caught:
        getattr(DeceptiveControlRecord, entrypoint)(
            kind="identity",
            record_id="identity_deceptive_factory",
            payload=VALID_PAYLOADS["identity"],
        )

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_record_kind_registry_is_closed_and_covers_the_w0_model() -> None:
    assert RECORD_KINDS == EXPECTED_RECORD_KINDS
    for kind in EXPECTED_RECORD_KINDS - {"public_envelope"}:
        signature = None
        if kind == "composite_authority_checkpoint":
            signature = {
                "algorithm": "ed25519",
                "signed_digest": ControlRecord.signing_digest(
                    kind=kind,
                    record_id=f"{kind}_1",
                    payload=VALID_PAYLOADS[kind],
                ),
                "signer_identity_digest": VALID_PAYLOADS[kind][
                    "signer_identity_digest"
                ],
                "value": (
                    "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                    "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
                ),
            }
        assert ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_1",
            payload=VALID_PAYLOADS[kind],
            signature=signature,
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


def test_detached_signature_rejects_noncanonical_base64url_pad_bits() -> None:
    unsigned = ControlRecord.build(
        kind="attestation",
        record_id="attestation_with_noncanonical_signature",
        payload=VALID_PAYLOADS["attestation"],
    )
    canonical_value = (
        "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
        "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
    )
    noncanonical_value = canonical_value[:-1] + "x"

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.build(
            kind="attestation",
            record_id="attestation_with_noncanonical_signature",
            payload=VALID_PAYLOADS["attestation"],
            signature={
                "algorithm": "ed25519",
                "signed_digest": unsigned.digest(),
                "signer_identity_digest": DIGEST_9,
                "value": noncanonical_value,
            },
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


def test_parse_rejects_a_nonstring_kind_with_the_stable_type_code() -> None:
    with pytest.raises(ControlRecordError) as caught:
        ControlRecord.parse(_valid_wire(kind=7))

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_parse_rejects_a_string_subclass_without_invoking_its_encode() -> None:
    record = ControlRecord.build(
        kind="identity",
        record_id="identity_string_subclass",
        payload=VALID_PAYLOADS["identity"],
    )
    wire = EncodeOverridingWire(record.canonical_bytes().decode("utf-8"))

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.parse(wire)

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_parse_rejects_a_bytes_subclass_without_invoking_its_decode() -> None:
    record = ControlRecord.build(
        kind="identity",
        record_id="identity_bytes_subclass",
        payload=VALID_PAYLOADS["identity"],
    )
    wire = DecodeOverridingWire(record.canonical_bytes())

    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.parse(wire)

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


def test_parse_round_trips_exact_canonical_text() -> None:
    record = ControlRecord.build(
        kind="identity",
        record_id="identity_text_round_trip",
        payload=VALID_PAYLOADS["identity"],
    )
    wire = record.canonical_bytes().decode("utf-8")

    restored = ControlRecord.parse(wire)

    assert restored.canonical_bytes() == record.canonical_bytes()


def test_parse_preserves_invalid_json_code_for_exact_text() -> None:
    with pytest.raises(RecordValidationError) as caught:
        ControlRecord.parse("{")

    assert caught.value.code is RecordErrorCode.INVALID_JSON


def test_parse_rejects_a_control_record_subclass_factory() -> None:
    wire = ControlRecord.build(
        kind="identity",
        record_id="identity_deceptive_parse",
        payload=VALID_PAYLOADS["identity"],
    ).canonical_bytes()

    with pytest.raises(ControlRecordError) as caught:
        DeceptiveControlRecord.parse(wire)

    assert caught.value.code is RecordErrorCode.INVALID_TYPE


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
