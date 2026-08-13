"""Canonical records and privacy-safe public envelopes for the control plane."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from ._authority import (
    CriticalOperationKind,
    EffectClass,
    GenerationBindingMode,
    GenerationClass,
    LifecyclePhase,
    OperationSubjectKind,
    OperationTargetKind,
    validate_operation_coordinates,
)

SCHEMA_NAME = "arch_strix_halo.control_record"
SCHEMA_VERSION = 1
MAX_NESTING_DEPTH = 32
MAX_RECORD_BYTES = 1024 * 1024
MIN_CANONICAL_INTEGER = -(2**63)
MAX_CANONICAL_INTEGER = 2**63 - 1
_DIGEST_DOMAIN = b"arch-strix-halo/control-record/v1\x00"
_PUBLIC_COMMITMENT_DOMAIN = b"arch-strix-halo/public-envelope-commitment/v1\x00"
_PUBLIC_ENVELOPE_ID_DOMAIN = b"arch-strix-halo/public-envelope-id/v1\x00"
_OPAQUE_REFERENCE_DOMAIN = b"arch-strix-halo/opaque-reference/v1\x00"
_SNAKE_CASE_KEY = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE_REF_PATTERN = re.compile(
    r"^opaque_hmac_sha256:v1:[A-Za-z0-9_-]{43}$"
)
_KEYED_COMMITMENT_PATTERN = re.compile(r"^hmac_sha256:[0-9a-f]{64}$")
_ED25519_SIGNATURE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{86}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,255}$")
_STABLE_IDENTIFIER_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"
)
_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_EVALUATION_MISSING_UNKNOWN_REASONS = frozenset(
    {"missing_applicability_proof", "missing_attestation"}
)
_EVALUATION_PROOF_UNKNOWN_REASONS = frozenset({"applicability_proof_mismatch"})
_EVALUATION_ATTESTATION_UNKNOWN_REASONS = frozenset(
    {
        "assignment_mismatch",
        "context_mismatch",
        "dependency_mismatch",
        "gate_mismatch",
        "reported_unknown",
        "separation_violation",
        "subject_mismatch",
    }
)
_EVALUATION_UNKNOWN_REASONS = (
    _EVALUATION_MISSING_UNKNOWN_REASONS
    | _EVALUATION_PROOF_UNKNOWN_REASONS
    | _EVALUATION_ATTESTATION_UNKNOWN_REASONS
)


class FieldKind(str, Enum):
    """Closed value types used by record-family payload schemas."""

    BOOL = "bool"
    DECLARED_EFFECT_LIST = "declared_effect_list"
    DIGEST = "digest"
    DIGEST_LIST = "digest_list"
    DIGEST_SEQUENCE = "digest_sequence"
    ENUM = "enum"
    ENUM_LIST = "enum_list"
    GENERATION_BINDING = "generation_binding"
    IDENTIFIER = "identifier"
    IDENTIFIER_LIST = "identifier_list"
    NONNEGATIVE_INTEGER = "nonnegative_integer"
    OBJECT = "object"
    STABLE_IDENTIFIER = "stable_identifier"
    TEXT = "text"
    TIMESTAMP = "timestamp"


def parse_canonical_timestamp(value: str) -> datetime:
    """Parse one schema-valid RFC 3339 timestamp as an aware instant."""

    if type(value) is not str or not _TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("timestamp is not canonical RFC 3339")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must identify an aware instant")
    return parsed


@dataclass(frozen=True, slots=True)
class FieldSchema:
    """The semantic type and finite choices for one payload field."""

    kind: FieldKind
    choices: frozenset[str] = frozenset()
    allow_empty: bool = False


@dataclass(frozen=True, slots=True)
class RecordSchema:
    """The closed metadata policy for one canonical record kind."""

    kind: str
    required_fields: Mapping[str, FieldSchema]
    optional_fields: Mapping[str, FieldSchema]
    public_fields: frozenset[str] = frozenset()


def _field(
    kind: FieldKind,
    *choices: str,
    allow_empty: bool = False,
) -> FieldSchema:
    return FieldSchema(
        kind=kind,
        choices=frozenset(choices),
        allow_empty=allow_empty,
    )


def _record_schema(
    kind: str,
    *public_fields: str,
    required: Mapping[str, FieldSchema] | None = None,
    optional: Mapping[str, FieldSchema] | None = None,
) -> RecordSchema:
    return RecordSchema(
        kind=kind,
        required_fields=MappingProxyType(dict(required or {})),
        optional_fields=MappingProxyType(dict(optional or {})),
        public_fields=frozenset(public_fields),
    )


RECORD_SCHEMAS: Mapping[str, RecordSchema] = MappingProxyType(
    {
        "acceptance_request": _record_schema(
            "acceptance_request",
            required={
                "acceptance_authorization_digest": _field(FieldKind.DIGEST),
                "atomic_evidence_cut_digest": _field(FieldKind.DIGEST),
                "final_service_anchor_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
                "generation_digest": _field(FieldKind.DIGEST),
                "predecessor_checkpoint_digest": _field(FieldKind.DIGEST),
                "promotion_contract_digest": _field(FieldKind.DIGEST),
                "requested_at": _field(FieldKind.TIMESTAMP),
                "target_digest": _field(FieldKind.DIGEST),
                "target_protected_state_digest": _field(FieldKind.DIGEST),
            },
        ),
        "approval": _record_schema(
            "approval",
            "decision",
            required={
                "action": _field(FieldKind.IDENTIFIER),
                "actor_identity_digest": _field(FieldKind.DIGEST),
                "actor_role": _field(FieldKind.IDENTIFIER),
                "authorization_digest": _field(FieldKind.DIGEST),
                "decided_at": _field(FieldKind.TIMESTAMP),
                "decision": _field(FieldKind.ENUM, "approved", "rejected"),
                "subject_digest": _field(FieldKind.DIGEST),
            },
        ),
        "assignment": _record_schema(
            "assignment",
            "applicability",
            required={
                "applicability": _field(
                    FieldKind.ENUM,
                    "conditional",
                    "unconditional",
                ),
                "assignment_id": _field(FieldKind.IDENTIFIER),
                "authorization_policy_digest": _field(FieldKind.DIGEST),
                "dependency_projection_digest": _field(FieldKind.DIGEST),
                "execution_requirement": _field(
                    FieldKind.ENUM,
                    "blocking_scenario",
                    "evidence_only",
                ),
                "gate_digest": _field(FieldKind.DIGEST),
                "impact": _field(FieldKind.ENUM, "advisory", "blocking"),
                "invalidation_policy_digest": _field(FieldKind.DIGEST),
                "separation_policy_digest": _field(FieldKind.DIGEST),
                "subject_digest": _field(FieldKind.DIGEST),
                "validity_policy_digest": _field(FieldKind.DIGEST),
            },
            optional={"predicate_digest": _field(FieldKind.DIGEST)},
        ),
        "assignment_set": _record_schema(
            "assignment_set",
            required={
                "assignment_digests": _field(FieldKind.DIGEST_LIST),
                "requirements_digest": _field(FieldKind.DIGEST),
            },
        ),
        "attempt": _record_schema(
            "attempt",
            required={
                "actor_identity_digest": _field(FieldKind.DIGEST),
                "assignment_digest": _field(FieldKind.DIGEST),
                "attempt_id": _field(FieldKind.IDENTIFIER),
                "context_digest": _field(FieldKind.DIGEST),
                "decision": _field(
                    FieldKind.ENUM,
                    "admitted",
                    "blocked",
                    "running",
                ),
                "intent_digest": _field(FieldKind.DIGEST),
                "journal_sequence": _field(FieldKind.NONNEGATIVE_INTEGER),
                "started_at": _field(FieldKind.TIMESTAMP),
            },
        ),
        "attestation": _record_schema(
            "attestation",
            "outcome",
            required={
                "actor_identity_digest": _field(FieldKind.DIGEST),
                "actor_role": _field(FieldKind.IDENTIFIER),
                "assignment_digest": _field(FieldKind.DIGEST),
                "context_digest": _field(FieldKind.DIGEST),
                "dependency_projection_digest": _field(FieldKind.DIGEST),
                "gate_digest": _field(FieldKind.DIGEST),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "outcome": _field(
                    FieldKind.ENUM,
                    "blocked",
                    "fail",
                    "pass",
                    "unknown",
                ),
                "subject_digest": _field(FieldKind.DIGEST),
            },
            optional={"raw_payload_reference_digest": _field(FieldKind.DIGEST)},
        ),
        "atomic_evidence_cut": _record_schema(
            "atomic_evidence_cut",
            required={
                "accepted_generation_digest": _field(FieldKind.DIGEST),
                "active_generation_digest": _field(FieldKind.DIGEST),
                "attempt_digests": _field(FieldKind.DIGEST_LIST),
                "capability_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "authority_head_digest": _field(FieldKind.DIGEST),
                "authority_manifest_digest": _field(FieldKind.DIGEST),
                "complete_through_sequence": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "completeness_proof_digest": _field(FieldKind.DIGEST),
                "contract_digest": _field(FieldKind.DIGEST),
                "currency_proof_digests": _field(FieldKind.DIGEST_LIST),
                "evaluation_digests": _field(FieldKind.DIGEST_LIST),
                "fork_proof_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "inclusion_edge_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "journal_head_digest": _field(FieldKind.DIGEST),
                "operation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "operation_terminal_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "observation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "phase": _field(
                    FieldKind.ENUM,
                    "accepted",
                    "active",
                    "prevalidated",
                    "published",
                ),
                "registration_set_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
                "target_protected_state_digest": _field(FieldKind.DIGEST),
            },
        ),
        "authority_register": _record_schema(
            "authority_register",
            "status",
            required={
                "observed_at": _field(FieldKind.TIMESTAMP),
                "quorum_receipt_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "register_head_digest": _field(FieldKind.DIGEST),
                "register_id": _field(FieldKind.IDENTIFIER),
                "sequence": _field(FieldKind.NONNEGATIVE_INTEGER),
                "status": _field(FieldKind.ENUM, "absent", "corrupt", "valid"),
                "witness_roster_digest": _field(FieldKind.DIGEST),
            },
            optional={"selected_manifest_digest": _field(FieldKind.DIGEST)},
        ),
        "authorization": _record_schema(
            "authorization",
            required={
                "action": _field(FieldKind.IDENTIFIER),
                "approver_roles": _field(FieldKind.IDENTIFIER_LIST),
                "policy_id": _field(FieldKind.IDENTIFIER),
                "recovery_root_digest": _field(FieldKind.DIGEST),
                "separation_policy_digest": _field(FieldKind.DIGEST),
                "subject_kind": _field(FieldKind.IDENTIFIER),
                "validity_policy_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "allowed_actor_identity_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "allowed_actor_roles": _field(
                    FieldKind.IDENTIFIER_LIST,
                    allow_empty=True,
                ),
            },
        ),
        "baseline_restoration_receipt": _record_schema(
            "baseline_restoration_receipt",
            required={
                "candidate_live_protected_state_digest": _field(
                    FieldKind.DIGEST
                ),
                "captured_checkpoint_digest": _field(FieldKind.DIGEST),
                "captured_generation_digest": _field(FieldKind.DIGEST),
                "captured_protected_state_digest": _field(FieldKind.DIGEST),
                "isolated_install_operation_digest": _field(FieldKind.DIGEST),
                "isolated_install_operation_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "live_prestate_protected_state_digest": _field(
                    FieldKind.DIGEST
                ),
                "post_restoration_gate_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "post_restoration_smoke_attempt_digest": _field(
                    FieldKind.DIGEST
                ),
                "post_restoration_smoke_evaluation_digest": _field(
                    FieldKind.DIGEST
                ),
                "phase_establishing_operation_obligation_digest": _field(
                    FieldKind.DIGEST
                ),
                "post_restoration_smoke_contract_digest": _field(
                    FieldKind.DIGEST
                ),
                "prevalidated_promotion_contract_digest": _field(
                    FieldKind.DIGEST
                ),
                "receipt_id": _field(FieldKind.STABLE_IDENTIFIER),
                "rehearsal_install_operation_digest": _field(FieldKind.DIGEST),
                "rehearsal_install_operation_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "restoration_evidence_cut_digest": _field(FieldKind.DIGEST),
                "restoration_operation_digest": _field(FieldKind.DIGEST),
                "restoration_operation_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "restored_generation_digest": _field(FieldKind.DIGEST),
                "restored_fence_epoch": _field(FieldKind.NONNEGATIVE_INTEGER),
                "restored_projection_digest": _field(FieldKind.DIGEST),
                "restored_protected_state_digest": _field(FieldKind.DIGEST),
                "rollback_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "backend_provenance": _record_schema(
            "backend_provenance",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "backend_id": _field(FieldKind.STABLE_IDENTIFIER),
                "backend_manifest_digest": _field(FieldKind.DIGEST),
                "configuration_digest": _field(FieldKind.DIGEST),
                "driver_device_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "model_identity_digest": _field(FieldKind.DIGEST),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "observer_identity_digest": _field(FieldKind.DIGEST),
                "package_manifest_digest": _field(FieldKind.DIGEST),
                "process_epoch": _field(FieldKind.IDENTIFIER),
                "provenance_id": _field(FieldKind.STABLE_IDENTIFIER),
                "service_protected_state_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "capability": _record_schema(
            "capability",
            "status",
            required={
                "authority_head_digest": _field(FieldKind.DIGEST),
                "authorizer_digest": _field(FieldKind.DIGEST),
                "capability_id": _field(FieldKind.DIGEST),
                "capability_type": _field(
                    FieldKind.ENUM,
                    "operation",
                    "recovery",
                    "rollback",
                ),
                "expires_at": _field(FieldKind.TIMESTAMP),
                "fence_epoch": _field(FieldKind.NONNEGATIVE_INTEGER),
                "intended_protected_state_digest": _field(FieldKind.DIGEST),
                "intent_digest": _field(FieldKind.DIGEST),
                "issued_at": _field(FieldKind.TIMESTAMP),
                "operation_digest": _field(FieldKind.DIGEST),
                "operation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "plan_digest": _field(FieldKind.DIGEST),
                "single_use_scope_digest": _field(FieldKind.DIGEST),
                "status": _field(
                    FieldKind.ENUM,
                    "active",
                    "consumed",
                    "revoked",
                ),
                "subject_digest": _field(FieldKind.DIGEST),
                "target_id": _field(FieldKind.STABLE_IDENTIFIER),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
                "target_lease_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "predecessor_failure_record_digest": _field(FieldKind.DIGEST),
                "predecessor_fence_epoch": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "predecessor_operation_id": _field(
                    FieldKind.STABLE_IDENTIFIER
                ),
                "recovery_contract_digest": _field(FieldKind.DIGEST),
                "recovery_owner_role": _field(FieldKind.STABLE_IDENTIFIER),
            },
        ),
        "composite_authority": _record_schema(
            "composite_authority",
            required={
                "accepted_generation_digest": _field(FieldKind.DIGEST),
                "active_generation_digest": _field(FieldKind.DIGEST),
                "authorization_policy_digest": _field(FieldKind.DIGEST),
                "contract_digest": _field(FieldKind.DIGEST),
                "fallback_digest": _field(FieldKind.DIGEST),
                "inventory_digest": _field(FieldKind.DIGEST),
                "manifest_id": _field(FieldKind.IDENTIFIER),
                "quorum_policy_digest": _field(FieldKind.DIGEST),
                "recovery_policy_digest": _field(FieldKind.DIGEST),
                "requirements_digest": _field(FieldKind.DIGEST),
                "rollback_generation_digest": _field(FieldKind.DIGEST),
                "rollback_registry_digest": _field(FieldKind.DIGEST),
                "witness_roster_digest": _field(FieldKind.DIGEST),
            },
        ),
        "composite_authority_checkpoint": _record_schema(
            "composite_authority_checkpoint",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "change_set_digest": _field(FieldKind.DIGEST),
                "checkpoint_id": _field(FieldKind.STABLE_IDENTIFIER),
                "committed_at": _field(FieldKind.TIMESTAMP),
                "quorum_receipt_digests": _field(FieldKind.DIGEST_LIST),
                "register_head_digest": _field(FieldKind.DIGEST),
                "register_id": _field(FieldKind.STABLE_IDENTIFIER),
                "register_observation_digest": _field(FieldKind.DIGEST),
                "register_sequence": _field(FieldKind.NONNEGATIVE_INTEGER),
                "selected_manifest_digest": _field(FieldKind.DIGEST),
                "signer_identity_digest": _field(FieldKind.DIGEST),
            },
        ),
        "composite_change_set": _record_schema(
            "composite_change_set",
            required={
                "authorization_action": _field(
                    FieldKind.ENUM,
                    "reinstate_composite_authority",
                    "transition_composite_authority",
                ),
                "authorization_digest": _field(FieldKind.DIGEST),
                "candidate_manifest_digest": _field(FieldKind.DIGEST),
                "change_set_id": _field(FieldKind.IDENTIFIER),
                "changed_fields": _field(
                    FieldKind.ENUM_LIST,
                    "accepted_generation",
                    "active_generation",
                    "authorization_policy",
                    "contract",
                    "fallback",
                    "inventory",
                    "quorum_policy",
                    "recovery_policy",
                    "requirements",
                    "rollback_generation",
                    "rollback_registry",
                    "witness_roster",
                    allow_empty=True,
                ),
                "coordinator_identity_digest": _field(FieldKind.DIGEST),
                "generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    GenerationBindingMode.REQUIRED_GENERATION.value,
                    GenerationBindingMode.B0_CAPTURE_SENTINEL.value,
                    GenerationBindingMode.NO_GENERATION.value,
                ),
                "old_manifest_digest": _field(FieldKind.DIGEST),
                "quorum_mode": _field(
                    FieldKind.ENUM,
                    "existing",
                    "joint_consensus",
                    "recovery_root",
                ),
                "rollback_manifest_digest": _field(FieldKind.DIGEST),
                "terminal_rule": _field(FieldKind.ENUM, "conjunctive"),
                "transition_mode": _field(
                    FieldKind.ENUM,
                    "acceptance",
                    "activation",
                    "control_update",
                    "register_reinstatement",
                ),
            },
            optional={
                "current_authority_register_observation_digest": _field(
                    FieldKind.DIGEST
                ),
                "prior_committed_checkpoint_digest": _field(FieldKind.DIGEST),
            },
        ),
        "composite_fallback_reference": _record_schema(
            "composite_fallback_reference",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "committed_checkpoint_digest": _field(FieldKind.DIGEST),
                "reference_id": _field(FieldKind.STABLE_IDENTIFIER),
                "referenced_manifest_digest": _field(FieldKind.DIGEST),
            },
        ),
        "dependency_projection": _record_schema(
            "dependency_projection",
            required={
                "dependency_digests": _field(
                    FieldKind.DIGEST_SEQUENCE,
                    allow_empty=True,
                ),
                "dependency_keys": _field(
                    FieldKind.IDENTIFIER_LIST,
                    allow_empty=True,
                ),
                "projection_id": _field(FieldKind.STABLE_IDENTIFIER),
            },
        ),
        "evidence_currency_proof": _record_schema(
            "evidence_currency_proof",
            required={
                "evaluated_dependency_projection_digest": _field(
                    FieldKind.DIGEST
                ),
                "evaluation_digest": _field(FieldKind.DIGEST),
                "inclusion_edge_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "invalidation_policy_digest": _field(FieldKind.DIGEST),
                "invalidation_stream_checkpoint_digest": _field(
                    FieldKind.DIGEST
                ),
                "trusted_time_observation_digest": _field(FieldKind.DIGEST),
                "validity_policy_digest": _field(FieldKind.DIGEST),
            },
        ),
        "evaluation": _record_schema(
            "evaluation",
            "applicability",
            "outcome",
            required={
                "applicability": _field(
                    FieldKind.ENUM,
                    "applicable",
                    "applicable_unknown",
                    "not_applicable",
                    "not_due",
                ),
                "assignment_digest": _field(FieldKind.DIGEST),
                "attestation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "context_digest": _field(FieldKind.DIGEST),
                "dependency_projection_digest": _field(FieldKind.DIGEST),
                "evaluated_at": _field(FieldKind.TIMESTAMP),
                "outcome": _field(
                    FieldKind.ENUM,
                    "blocked",
                    "fail",
                    "not_applicable",
                    "pass",
                    "unknown",
                ),
            },
            optional={
                "predicate_proof_digest": _field(FieldKind.DIGEST),
                "unknown_reason": _field(
                    FieldKind.ENUM,
                    *_EVALUATION_UNKNOWN_REASONS,
                ),
            },
        ),
        "exception": _record_schema(
            "exception",
            "status",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "exception_id": _field(FieldKind.IDENTIFIER),
                "expires_at": _field(FieldKind.TIMESTAMP),
                "owner_identity_digest": _field(FieldKind.DIGEST),
                "reason_code": _field(FieldKind.IDENTIFIER),
                "scope_digest": _field(FieldKind.DIGEST),
                "status": _field(FieldKind.ENUM, "active", "expired", "revoked"),
            },
            optional={"recovery_artifact_digest": _field(FieldKind.DIGEST)},
        ),
        "fixture_role": _record_schema(
            "fixture_role",
            required={
                "api_path": _field(FieldKind.IDENTIFIER),
                "assertion_digest": _field(FieldKind.DIGEST),
                "backend_attribution": _field(FieldKind.IDENTIFIER),
                "capability_id": _field(FieldKind.IDENTIFIER),
                "corpus_digest": _field(FieldKind.DIGEST),
                "fixture_format": _field(FieldKind.IDENTIFIER),
                "input_digest": _field(FieldKind.DIGEST),
                "license_class": _field(
                    FieldKind.ENUM,
                    "gated",
                    "proprietary",
                    "public",
                ),
                "modality": _field(
                    FieldKind.ENUM,
                    "audio",
                    "embedding",
                    "image",
                    "multimodal",
                    "reranking",
                    "text",
                    "tts",
                    "video",
                ),
                "offline": _field(FieldKind.BOOL),
                "resource_envelope_digest": _field(FieldKind.DIGEST),
                "role_id": _field(FieldKind.IDENTIFIER),
                "tolerance_digest": _field(FieldKind.DIGEST),
            },
        ),
        "fixture_selector": _record_schema(
            "fixture_selector",
            required={
                "access_class": _field(
                    FieldKind.ENUM,
                    "gated",
                    "proprietary",
                    "public",
                ),
                "artifact_digests": _field(FieldKind.DIGEST_LIST),
                "closure_digest": _field(FieldKind.DIGEST),
                "fixture_format": _field(FieldKind.IDENTIFIER),
                "license_digest": _field(FieldKind.DIGEST),
                "provider": _field(FieldKind.IDENTIFIER),
                "revision": _field(FieldKind.IDENTIFIER),
                "role_digest": _field(FieldKind.DIGEST),
                "selector_id": _field(FieldKind.IDENTIFIER),
            },
            optional={"base_model_digest": _field(FieldKind.DIGEST)},
        ),
        "final_service_anchor_receipt": _record_schema(
            "final_service_anchor_receipt",
            required={
                "anchor_id": _field(FieldKind.STABLE_IDENTIFIER),
                "backend_provenance_digest": _field(FieldKind.DIGEST),
                "evidence_cut_digest": _field(FieldKind.DIGEST),
                "expires_at": _field(FieldKind.TIMESTAMP),
                "final_restart_operation_digest": _field(FieldKind.DIGEST),
                "final_restart_operation_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "generation_digest": _field(FieldKind.DIGEST),
                "issued_at": _field(FieldKind.TIMESTAMP),
                "predecessor_service_anchor_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
                "process_epoch": _field(FieldKind.IDENTIFIER),
                "promotion_contract_digest": _field(FieldKind.DIGEST),
                "readiness_digest": _field(FieldKind.DIGEST),
                "service_protected_state_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "gate": _record_schema(
            "gate",
            required={
                "assertion_digest": _field(FieldKind.DIGEST),
                "attestation_authorization_digest": _field(FieldKind.DIGEST),
                "evidence_shape_digest": _field(FieldKind.DIGEST),
                "fixture_role_digest": _field(FieldKind.DIGEST),
                "gate_id": _field(FieldKind.IDENTIFIER),
                "validator_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "dependency_keys": _field(FieldKind.IDENTIFIER_LIST),
                "label": _field(FieldKind.TEXT),
                "predicate_authorization_digest": _field(FieldKind.DIGEST),
            },
        ),
        "generation": _record_schema(
            "generation",
            required={
                "artifact_digests": _field(FieldKind.DIGEST_LIST),
                "generation_class": _field(FieldKind.ENUM, "b0", "c", "f"),
                "generation_id": _field(FieldKind.IDENTIFIER),
                "input_closure_digest": _field(FieldKind.DIGEST),
                "manifest_digest": _field(FieldKind.DIGEST),
            },
            optional={"parent_generation_digest": _field(FieldKind.DIGEST)},
        ),
        "identity": _record_schema(
            "identity",
            required={
                "authority_digest": _field(FieldKind.DIGEST),
                "identity_id": _field(FieldKind.IDENTIFIER),
                "identity_type": _field(
                    FieldKind.ENUM,
                    "artifact",
                    "input_closure",
                    "principal",
                    "scenario",
                    "subject",
                    "target",
                    "validator",
                ),
            },
            optional={"roles": _field(FieldKind.IDENTIFIER_LIST)},
        ),
        "intent": _record_schema(
            "intent",
            required={
                "actor_identity_digest": _field(FieldKind.DIGEST),
                "context_digest": _field(FieldKind.DIGEST),
                "intent_id": _field(FieldKind.IDENTIFIER),
                "intent_type": _field(
                    FieldKind.ENUM,
                    "critical_operation",
                    "gate_occurrence",
                ),
                "journal_sequence": _field(FieldKind.NONNEGATIVE_INTEGER),
                "registered_at": _field(FieldKind.TIMESTAMP),
                "subject_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "assignment_digest": _field(FieldKind.DIGEST),
                "operation_plan_digest": _field(FieldKind.DIGEST),
            },
        ),
        "inclusion_edge": _record_schema(
            "inclusion_edge",
            required={
                "active_contract_digest": _field(FieldKind.DIGEST),
                "approval_digest": _field(FieldKind.DIGEST),
                "artifact_digests": _field(FieldKind.DIGEST_LIST),
                "assignment_digests": _field(FieldKind.DIGEST_LIST),
                "generation_digest": _field(FieldKind.DIGEST),
                "inclusion_edge_id": _field(FieldKind.STABLE_IDENTIFIER),
                "preassembly_context_digest": _field(FieldKind.DIGEST),
                "preassembly_evaluation_digests": _field(
                    FieldKind.DIGEST_LIST
                ),
                "preassembly_profile_digest": _field(FieldKind.DIGEST),
                "source_closure_digest": _field(FieldKind.DIGEST),
                "verified_at": _field(FieldKind.TIMESTAMP),
                "verifier_identity_digest": _field(FieldKind.DIGEST),
            },
        ),
        "invalidation": _record_schema(
            "invalidation",
            "status",
            required={
                "affected_evaluation_digests": _field(FieldKind.DIGEST_LIST),
                "dependency_key": _field(FieldKind.IDENTIFIER),
                "episode_id": _field(FieldKind.IDENTIFIER),
                "event_digest": _field(FieldKind.DIGEST),
                "opened_at": _field(FieldKind.TIMESTAMP),
                "status": _field(FieldKind.ENUM, "closed", "open"),
            },
            optional={"closed_at": _field(FieldKind.TIMESTAMP)},
        ),
        "invalidation_policy": _record_schema(
            "invalidation_policy",
            required={
                "dependency_keys": _field(
                    FieldKind.IDENTIFIER_LIST,
                    allow_empty=True,
                ),
                "policy_id": _field(FieldKind.STABLE_IDENTIFIER),
            },
        ),
        "invalidation_stream_checkpoint": _record_schema(
            "invalidation_stream_checkpoint",
            required={
                "authority_head_digest": _field(FieldKind.DIGEST),
                "authority_manifest_digest": _field(FieldKind.DIGEST),
                "authority_view_digest": _field(FieldKind.DIGEST),
                "checkpoint_id": _field(FieldKind.STABLE_IDENTIFIER),
                "checkpointed_at": _field(FieldKind.TIMESTAMP),
                "complete_through_sequence": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "completeness_proof_digest": _field(FieldKind.DIGEST),
                "current_dependency_projection_digest": _field(
                    FieldKind.DIGEST
                ),
                "fork_proof_digest": _field(FieldKind.DIGEST),
                "invalidation_policy_digest": _field(FieldKind.DIGEST),
                "stream_head_digest": _field(FieldKind.DIGEST),
                "stream_id": _field(FieldKind.STABLE_IDENTIFIER),
            },
        ),
        "installed_inventory": _record_schema(
            "installed_inventory",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "configuration_digest": _field(FieldKind.DIGEST),
                "driver_device_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "inventory_id": _field(FieldKind.STABLE_IDENTIFIER),
                "model_identity_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "observer_identity_digest": _field(FieldKind.DIGEST),
                "package_manifest_digest": _field(FieldKind.DIGEST),
            },
        ),
        "lifecycle_checkpoint": _record_schema(
            "lifecycle_checkpoint",
            required={
                "checkpoint_id": _field(FieldKind.STABLE_IDENTIFIER),
                "established_at": _field(FieldKind.TIMESTAMP),
                "generation_class": _field(
                    FieldKind.ENUM,
                    *(generation_class.value for generation_class in GenerationClass),
                ),
                "generation_digest": _field(FieldKind.DIGEST),
                "phase": _field(
                    FieldKind.ENUM,
                    *(phase.value for phase in LifecyclePhase),
                ),
                "target_digest": _field(FieldKind.DIGEST),
                "target_protected_state_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "acceptance_request_digest": _field(FieldKind.DIGEST),
                "approval_digest": _field(FieldKind.DIGEST),
                "authority_proof_digest": _field(FieldKind.DIGEST),
                "baseline_restoration_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
                "contract_digest": _field(FieldKind.DIGEST),
                "evidence_cut_digest": _field(FieldKind.DIGEST),
                "final_service_anchor_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
                "predecessor_checkpoint_digest": _field(FieldKind.DIGEST),
                "root_authorization_digest": _field(FieldKind.DIGEST),
                "service_anchor_receipt_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation": _record_schema(
            "operation",
            required={
                "authority_head_digest": _field(FieldKind.DIGEST),
                "declared_effects": _field(FieldKind.DECLARED_EFFECT_LIST),
                "expected_protected_state_digest": _field(FieldKind.DIGEST),
                "generation_class": _field(
                    FieldKind.ENUM,
                    *(generation_class.value for generation_class in GenerationClass),
                ),
                "generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    *(mode.value for mode in GenerationBindingMode),
                ),
                "intended_protected_state_digest": _field(FieldKind.DIGEST),
                "intent_digest": _field(FieldKind.DIGEST),
                "lifecycle_phase": _field(
                    FieldKind.ENUM,
                    *(phase.value for phase in LifecyclePhase),
                ),
                "operation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "operation_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in CriticalOperationKind),
                ),
                "plan_digest": _field(FieldKind.DIGEST),
                "recovery_contract_digest": _field(FieldKind.DIGEST),
                "recovery_target_digest": _field(FieldKind.DIGEST),
                "subject_digest": _field(FieldKind.DIGEST),
                "subject_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationSubjectKind),
                ),
                "target_id": _field(FieldKind.STABLE_IDENTIFIER),
                "target_digest": _field(FieldKind.DIGEST),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
                "terminal_validator_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "rollback_contract_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_attestation": _record_schema(
            "operation_attestation",
            required={
                "observed_at": _field(FieldKind.TIMESTAMP),
                "operation_digest": _field(FieldKind.DIGEST),
                "outcome": _field(
                    FieldKind.ENUM,
                    "failed",
                    "succeeded",
                    "unknown",
                ),
                "poststate_digest": _field(FieldKind.DIGEST),
                "subject_digest": _field(FieldKind.DIGEST),
                "validator_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_obligation": _record_schema(
            "operation_obligation",
            required={
                "generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    *(mode.value for mode in GenerationBindingMode),
                ),
                "generation_class": _field(
                    FieldKind.ENUM,
                    *(generation_class.value for generation_class in GenerationClass),
                ),
                "intent_digest": _field(FieldKind.DIGEST),
                "lifecycle_phase": _field(
                    FieldKind.ENUM,
                    *(phase.value for phase in LifecyclePhase),
                ),
                "obligation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "operation_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in CriticalOperationKind),
                ),
                "operation_digest": _field(FieldKind.DIGEST),
                "operation_requirement_digest": _field(FieldKind.DIGEST),
                "subject_digest": _field(FieldKind.DIGEST),
                "subject_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationSubjectKind),
                ),
                "target_id": _field(FieldKind.STABLE_IDENTIFIER),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
            },
        ),
        "operation_obligation_set": _record_schema(
            "operation_obligation_set",
            required={
                "obligation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "operation_requirement_set_digest": _field(FieldKind.DIGEST),
                "requirements_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_requirement": _record_schema(
            "operation_requirement",
            required={
                "declared_effects": _field(FieldKind.DECLARED_EFFECT_LIST),
                "generation_binding_mode": _field(
                    FieldKind.ENUM,
                    *(mode.value for mode in GenerationBindingMode),
                ),
                "generation_binding_role": _field(
                    FieldKind.ENUM,
                    "b0_capture_sentinel",
                    "candidate_generation",
                    "captured_baseline_generation",
                    "no_generation",
                    "predecessor_generation",
                ),
                "generation_class": _field(
                    FieldKind.ENUM,
                    *(generation_class.value for generation_class in GenerationClass),
                ),
                "lifecycle_phase": _field(
                    FieldKind.ENUM,
                    *(phase.value for phase in LifecyclePhase),
                ),
                "operation_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in CriticalOperationKind),
                ),
                "plan_digest": _field(FieldKind.DIGEST),
                "purpose": _field(
                    FieldKind.ENUM,
                    "baseline_rehearsal_install",
                    "baseline_restoration",
                    "blocking_scenario",
                    "final_service_restart",
                    "phase_transition",
                    "service_anchor",
                    "service_restart",
                ),
                "realization_condition": _field(
                    FieldKind.ENUM,
                    "always",
                    "when_assignment_applicable",
                ),
                "recovery_contract_digest": _field(FieldKind.DIGEST),
                "recovery_target_role": _field(
                    FieldKind.ENUM,
                    "captured_baseline",
                    "expected_prestate",
                    "predecessor_state",
                ),
                "requirement_id": _field(FieldKind.STABLE_IDENTIFIER),
                "subject_binding_role": _field(
                    FieldKind.ENUM,
                    "candidate_generation",
                    "captured_baseline",
                    "composite_authority",
                    "control_record",
                    "gate_occurrence",
                ),
                "subject_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationSubjectKind),
                ),
                "target_digest": _field(FieldKind.DIGEST),
                "target_id": _field(FieldKind.STABLE_IDENTIFIER),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
                "terminal_validator_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "assignment_digest": _field(FieldKind.DIGEST),
                "rollback_contract_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_requirement_set": _record_schema(
            "operation_requirement_set",
            required={
                "operation_requirement_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "requirements_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_realization": _record_schema(
            "operation_realization",
            required={
                "observed_prestate_digest": _field(FieldKind.DIGEST),
                "operation_digest": _field(FieldKind.DIGEST),
                "operation_obligation_digest": _field(FieldKind.DIGEST),
                "operation_requirement_digest": _field(FieldKind.DIGEST),
                "realization_id": _field(FieldKind.STABLE_IDENTIFIER),
                "resolved_generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    *(mode.value for mode in GenerationBindingMode),
                ),
                "resolved_subject_digest": _field(FieldKind.DIGEST),
            },
        ),
        "operation_realization_set": _record_schema(
            "operation_realization_set",
            required={
                "operation_obligation_set_digest": _field(FieldKind.DIGEST),
                "operation_realization_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
            },
        ),
        "predicate_proof": _record_schema(
            "predicate_proof",
            required={
                "actor_identity_digest": _field(FieldKind.DIGEST),
                "actor_role": _field(FieldKind.STABLE_IDENTIFIER),
                "assignment_digest": _field(FieldKind.DIGEST),
                "context_digest": _field(FieldKind.DIGEST),
                "dependency_projection_digest": _field(FieldKind.DIGEST),
                "gate_digest": _field(FieldKind.DIGEST),
                "is_applicable": _field(FieldKind.BOOL),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "predicate_digest": _field(FieldKind.DIGEST),
                "subject_digest": _field(FieldKind.DIGEST),
            },
        ),
        "promotion_authority_proof": _record_schema(
            "promotion_authority_proof",
            required={
                "atomic_evidence_cut_digest": _field(FieldKind.DIGEST),
                "attempt_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "authority_adapter_identity_digest": _field(FieldKind.DIGEST),
                "authority_head_digest": _field(FieldKind.DIGEST),
                "authority_manifest_digest": _field(FieldKind.DIGEST),
                "authority_view_digest": _field(FieldKind.DIGEST),
                "capability_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "complete_through_sequence": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "completeness_proof_digest": _field(FieldKind.DIGEST),
                "currency_proof_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "evaluation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "fork_proof_digest": _field(FieldKind.DIGEST),
                "inclusion_edge_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "journal_head_digest": _field(FieldKind.DIGEST),
                "operation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "operation_terminal_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "observation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "phase": _field(
                    FieldKind.ENUM,
                    "accepted",
                    "active",
                    "prevalidated",
                    "published",
                ),
                "predecessor_checkpoint_digest": _field(FieldKind.DIGEST),
                "promotion_contract_digest": _field(FieldKind.DIGEST),
                "proof_id": _field(FieldKind.STABLE_IDENTIFIER),
                "validation_contract_digest": _field(FieldKind.DIGEST),
                "verified_at": _field(FieldKind.TIMESTAMP),
                "verifier_identity_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "acceptance_request_digest": _field(FieldKind.DIGEST),
                "approval_digest": _field(FieldKind.DIGEST),
                "final_service_anchor_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
            },
        ),
        "promotion_contract": _record_schema(
            "promotion_contract",
            required={
                "contract_id": _field(FieldKind.STABLE_IDENTIFIER),
                "expected_accepted_generation_digest": _field(
                    FieldKind.DIGEST
                ),
                "expected_active_generation_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "obligation_digests": _field(FieldKind.DIGEST_LIST),
                "operation_obligation_set_digest": _field(FieldKind.DIGEST),
                "operation_realization_set_digest": _field(FieldKind.DIGEST),
                "predecessor_checkpoint_digest": _field(FieldKind.DIGEST),
                "phase": _field(
                    FieldKind.ENUM,
                    "accepted",
                    "active",
                    "prevalidated",
                    "published",
                ),
                "requirements_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
                "target_protected_state_digest": _field(FieldKind.DIGEST),
                "validation_contract_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "acceptance_authorization_digest": _field(FieldKind.DIGEST),
                "baseline_restoration_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
                "phase_establishing_operation_obligation_digest": _field(
                    FieldKind.DIGEST
                ),
                "predecessor_service_anchor_receipt_digest": _field(
                    FieldKind.DIGEST
                ),
            },
        ),
        "promotion_obligation": _record_schema(
            "promotion_obligation",
            required={
                "assignment_digest": _field(FieldKind.DIGEST),
                "impact": _field(FieldKind.ENUM, "advisory", "blocking"),
                "obligation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "occurrence_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "scenario_operation_obligation_digest": _field(FieldKind.DIGEST),
            },
        ),
        "protected_state": _record_schema(
            "protected_state",
            required={
                "fence_epoch": _field(FieldKind.NONNEGATIVE_INTEGER),
                "generation_digest": _field(FieldKind.DIGEST),
                "lifecycle_phase": _field(
                    FieldKind.ENUM,
                    *(phase.value for phase in LifecyclePhase),
                ),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "projection_id": _field(FieldKind.IDENTIFIER),
                "state_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
                "target_kind": _field(
                    FieldKind.ENUM,
                    *(kind.value for kind in OperationTargetKind),
                ),
            },
            optional={"process_epoch": _field(FieldKind.IDENTIFIER)},
        ),
        "public_envelope": _record_schema(
            "public_envelope",
            required={
                "binding": _field(FieldKind.OBJECT),
                "public": _field(FieldKind.OBJECT),
                "source_kind": _field(FieldKind.IDENTIFIER),
            },
        ),
        "quorum_policy": _record_schema(
            "quorum_policy",
            required={
                "policy_id": _field(FieldKind.STABLE_IDENTIFIER),
                "threshold": _field(FieldKind.NONNEGATIVE_INTEGER),
                "witness_roster_digest": _field(FieldKind.DIGEST),
            },
        ),
        "quorum_receipt": _record_schema(
            "quorum_receipt",
            required={
                "approval_digests": _field(FieldKind.DIGEST_LIST),
                "approved_at": _field(FieldKind.TIMESTAMP),
                "authorization_digest": _field(FieldKind.DIGEST),
                "change_set_digest": _field(FieldKind.DIGEST),
                "quorum_policy_digest": _field(FieldKind.DIGEST),
                "receipt_id": _field(FieldKind.STABLE_IDENTIFIER),
                "side": _field(FieldKind.ENUM, "candidate", "existing"),
                "witness_roster_digest": _field(FieldKind.DIGEST),
            },
        ),
        "readiness": _record_schema(
            "readiness",
            "status",
            required={
                "backend_manifest_digest": _field(FieldKind.DIGEST),
                "backend_provenance_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "process_epoch": _field(FieldKind.IDENTIFIER),
                "service_health_observation_digests": _field(
                    FieldKind.DIGEST_LIST
                ),
                "service_protected_state_digest": _field(FieldKind.DIGEST),
                "status": _field(FieldKind.ENUM, "not_ready", "ready"),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "recovery": _record_schema(
            "recovery",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "destination_generation_digest": _field(FieldKind.DIGEST),
                "exact_state_generation_digest": _field(FieldKind.DIGEST),
                "exact_state_snapshot_digest": _field(FieldKind.DIGEST),
                "generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    GenerationBindingMode.REQUIRED_GENERATION.value,
                    GenerationBindingMode.B0_CAPTURE_SENTINEL.value,
                ),
                "incident_digest": _field(FieldKind.DIGEST),
                "origin_generation_digest": _field(FieldKind.DIGEST),
                "recovery_id": _field(FieldKind.IDENTIFIER),
                "target_digest": _field(FieldKind.DIGEST),
                "terminal_gate_digest": _field(FieldKind.DIGEST),
            },
        ),
        "recovery_policy": _record_schema(
            "recovery_policy",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "policy_id": _field(FieldKind.STABLE_IDENTIFIER),
                "recovery_contract_digests": _field(FieldKind.DIGEST_LIST),
                "recovery_owner_roles": _field(FieldKind.IDENTIFIER_LIST),
                "recovery_root_digest": _field(FieldKind.DIGEST),
                "separation_policy_digest": _field(FieldKind.DIGEST),
                "validity_policy_digest": _field(FieldKind.DIGEST),
            },
        ),
        "restricted_reference": _record_schema(
            "restricted_reference",
            required={
                "created_at": _field(FieldKind.TIMESTAMP),
                "key_version": _field(FieldKind.IDENTIFIER),
                "reference_id": _field(FieldKind.IDENTIFIER),
                "restricted_record_digest": _field(FieldKind.DIGEST),
                "retention_lease_digest": _field(FieldKind.DIGEST),
                "storage_authority_digest": _field(FieldKind.DIGEST),
            },
            optional={"rotation_history_digest": _field(FieldKind.DIGEST)},
        ),
        "retention_lease": _record_schema(
            "retention_lease",
            "status",
            required={
                "expires_at": _field(FieldKind.TIMESTAMP),
                "issued_at": _field(FieldKind.TIMESTAMP),
                "key_version": _field(FieldKind.IDENTIFIER),
                "lease_id": _field(FieldKind.IDENTIFIER),
                "status": _field(FieldKind.ENUM, "active", "expired", "revoked"),
            },
            optional={"rotation_history_digest": _field(FieldKind.DIGEST)},
        ),
        "restored_baseline_smoke_contract": _record_schema(
            "restored_baseline_smoke_contract",
            required={
                "assignment_digest": _field(FieldKind.DIGEST),
                "attestation_authorization_digest": _field(FieldKind.DIGEST),
                "expected_outcome": _field(FieldKind.ENUM, "pass"),
                "gate_digest": _field(FieldKind.DIGEST),
                "restored_protected_state_digest": _field(FieldKind.DIGEST),
                "smoke_contract_id": _field(FieldKind.STABLE_IDENTIFIER),
                "target_digest": _field(FieldKind.DIGEST),
                "validation_contract_digest": _field(FieldKind.DIGEST),
                "validator_digest": _field(FieldKind.DIGEST),
            },
        ),
        "rollback": _record_schema(
            "rollback",
            required={
                "destination_generation_digest": _field(FieldKind.DIGEST),
                "generation_binding": _field(
                    FieldKind.GENERATION_BINDING,
                    GenerationBindingMode.REQUIRED_GENERATION.value,
                ),
                "operation_digest": _field(FieldKind.DIGEST),
                "origin_generation_digest": _field(FieldKind.DIGEST),
                "rollback_id": _field(FieldKind.IDENTIFIER),
                "target_digest": _field(FieldKind.DIGEST),
                "target_generation_digest": _field(FieldKind.DIGEST),
                "target_projection_digest": _field(FieldKind.DIGEST),
                "target_protected_state_digest": _field(FieldKind.DIGEST),
                "target_state_digest": _field(FieldKind.DIGEST),
                "terminal_gate_digest": _field(FieldKind.DIGEST),
            },
        ),
        "rollback_registry": _record_schema(
            "rollback_registry",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "established_at": _field(FieldKind.TIMESTAMP),
                "registry_head_digest": _field(FieldKind.DIGEST),
                "registry_id": _field(FieldKind.STABLE_IDENTIFIER),
                "rollback_digests": _field(FieldKind.DIGEST_LIST),
                "selected_rollback_digest": _field(FieldKind.DIGEST),
            },
        ),
        "separation_policy": _record_schema(
            "separation_policy",
            required={
                "forbidden_actor_identity_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
                "policy_id": _field(FieldKind.STABLE_IDENTIFIER),
                "required_actor_roles": _field(
                    FieldKind.IDENTIFIER_LIST,
                    allow_empty=True,
                ),
            },
        ),
        "service_anchor_receipt": _record_schema(
            "service_anchor_receipt",
            required={
                "active_evidence_cut_digest": _field(FieldKind.DIGEST),
                "active_phase_operation_terminal_digest": _field(
                    FieldKind.DIGEST
                ),
                "active_promotion_contract_digest": _field(FieldKind.DIGEST),
                "anchor_id": _field(FieldKind.STABLE_IDENTIFIER),
                "backend_provenance_digest": _field(FieldKind.DIGEST),
                "establishing_operation_digest": _field(FieldKind.DIGEST),
                "expires_at": _field(FieldKind.TIMESTAMP),
                "generation_digest": _field(FieldKind.DIGEST),
                "issued_at": _field(FieldKind.TIMESTAMP),
                "operation_terminal_digest": _field(FieldKind.DIGEST),
                "process_epoch": _field(FieldKind.IDENTIFIER),
                "readiness_digest": _field(FieldKind.DIGEST),
                "service_protected_state_digest": _field(FieldKind.DIGEST),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "service_health_observation": _record_schema(
            "service_health_observation",
            required={
                "authorization_digest": _field(FieldKind.DIGEST),
                "backend_provenance_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "observation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "observer_identity_digest": _field(FieldKind.DIGEST),
                "process_epoch": _field(FieldKind.IDENTIFIER),
                "service_protected_state_digest": _field(FieldKind.DIGEST),
                "status": _field(
                    FieldKind.ENUM,
                    "not_ready",
                    "ready",
                    "unknown",
                ),
                "target_digest": _field(FieldKind.DIGEST),
            },
        ),
        "requirements": _record_schema(
            "requirements",
            required={
                "approval_digest": _field(FieldKind.DIGEST),
                "effective_at": _field(FieldKind.TIMESTAMP),
                "requirement_digests": _field(FieldKind.DIGEST_LIST),
                "requirements_definition_digest": _field(FieldKind.DIGEST),
                "requirements_id": _field(FieldKind.STABLE_IDENTIFIER),
                "requirements_version": _field(FieldKind.NONNEGATIVE_INTEGER),
            },
            optional={
                "supersedes_requirements_digest": _field(FieldKind.DIGEST)
            },
        ),
        "terminal_record": _record_schema(
            "terminal_record",
            "outcome",
            required={
                "completed_at": _field(FieldKind.TIMESTAMP),
                "journal_sequence": _field(FieldKind.NONNEGATIVE_INTEGER),
                "outcome": _field(
                    FieldKind.ENUM,
                    "failed",
                    "succeeded",
                    "unknown",
                ),
                "poststate_digest": _field(FieldKind.DIGEST),
                "terminal_type": _field(
                    FieldKind.ENUM,
                    "critical_operation",
                    "gate_attempt",
                ),
                "validator_attestation_digests": _field(
                    FieldKind.DIGEST_LIST,
                    allow_empty=True,
                ),
            },
            optional={
                "assignment_digest": _field(FieldKind.DIGEST),
                "attempt_digest": _field(FieldKind.DIGEST),
                "capability_digest": _field(FieldKind.DIGEST),
                "operation_digest": _field(FieldKind.DIGEST),
                "predicate_proof_digest": _field(FieldKind.DIGEST),
            },
        ),
        "trusted_time_observation": _record_schema(
            "trusted_time_observation",
            required={
                "authority_head_digest": _field(FieldKind.DIGEST),
                "observation_id": _field(FieldKind.STABLE_IDENTIFIER),
                "observed_at": _field(FieldKind.TIMESTAMP),
                "time_authority_digest": _field(FieldKind.DIGEST),
                "time_proof_digest": _field(FieldKind.DIGEST),
            },
        ),
        "validation_contract": _record_schema(
            "validation_contract",
            required={
                "approval_digest": _field(FieldKind.DIGEST),
                "assignments_digest": _field(FieldKind.DIGEST),
                "authorization_policy_digest": _field(FieldKind.DIGEST),
                "contract_id": _field(FieldKind.STABLE_IDENTIFIER),
                "max_live_attempt_seconds": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "max_suite_seconds": _field(FieldKind.NONNEGATIVE_INTEGER),
                "operation_requirement_set_digest": _field(FieldKind.DIGEST),
                "requirements_digest": _field(FieldKind.DIGEST),
            },
        ),
        "validation_context": _record_schema(
            "validation_context",
            required={
                "assignments_digest": _field(FieldKind.DIGEST),
                "context_id": _field(FieldKind.IDENTIFIER),
                "context_type": _field(
                    FieldKind.ENUM,
                    "active_contract",
                    "preassembly_profile",
                ),
                "requirements_digest": _field(FieldKind.DIGEST),
            },
            optional={
                "artifact_digests": _field(FieldKind.DIGEST_LIST),
                "contract_digest": _field(FieldKind.DIGEST),
                "generation_digest": _field(FieldKind.DIGEST),
                "profile_digest": _field(FieldKind.DIGEST),
                "source_closure_digest": _field(FieldKind.DIGEST),
            },
        ),
        "validity_policy": _record_schema(
            "validity_policy",
            required={
                "expiry_rule": _field(
                    FieldKind.ENUM,
                    "earliest_constituent_expiry",
                ),
                "policy_id": _field(FieldKind.STABLE_IDENTIFIER),
            },
            optional={
                "attestation_max_age_seconds": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "evidence_cut_max_age_seconds": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "inclusion_edge_max_age_seconds": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
                "predicate_proof_max_age_seconds": _field(
                    FieldKind.NONNEGATIVE_INTEGER
                ),
            },
        ),
        "witness_roster": _record_schema(
            "witness_roster",
            required={
                "roster_id": _field(FieldKind.STABLE_IDENTIFIER),
                "witness_identity_digests": _field(FieldKind.DIGEST_LIST),
            },
        ),
    }
)
RECORD_KINDS = frozenset(RECORD_SCHEMAS)

class RecordErrorCode(str, Enum):
    """Stable failure codes for record producers and consumers."""

    UNSUPPORTED_KIND = "unsupported_kind"
    INVALID_TYPE = "invalid_type"
    INVALID_KEY = "invalid_key"
    UNSUPPORTED_NUMBER = "unsupported_number"
    UNSAFE_UNICODE = "unsafe_unicode"
    EXCESSIVE_DEPTH = "excessive_depth"
    EXCESSIVE_SIZE = "excessive_size"
    CYCLIC_VALUE = "cyclic_value"
    INVALID_JSON = "invalid_json"
    DUPLICATE_KEY = "duplicate_key"
    NON_CANONICAL_JSON = "non_canonical_json"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    UNSUPPORTED_VERSION = "unsupported_version"
    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_DIGEST = "invalid_digest"
    INVALID_SIGNATURE = "invalid_signature"
    DIGEST_MISMATCH = "digest_mismatch"
    PRIVACY_BINDING_REQUIRED = "privacy_binding_required"
    INVALID_OPAQUE_REF = "invalid_opaque_ref"
    INVALID_OPAQUE_REFERENCE_KEY = "invalid_opaque_reference_key"
    INVALID_COMMITMENT_KEY = "invalid_commitment_key"
    UNSAFE_PUBLIC_VALUE = "unsafe_public_value"
    INVALID_PUBLIC_ENVELOPE = "invalid_public_envelope"
    MISSING_PAYLOAD_FIELD = "missing_payload_field"
    UNKNOWN_PAYLOAD_FIELD = "unknown_payload_field"
    INVALID_PAYLOAD_FIELD = "invalid_payload_field"
    INVALID_PAYLOAD_SEMANTICS = "invalid_payload_semantics"


class ControlRecordError(ValueError):
    """Base class for rejected control records."""

    def __init__(self, code: RecordErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


class CanonicalizationError(ControlRecordError):
    """A value has no safe canonical JSON v1 representation."""


class RecordValidationError(ControlRecordError):
    """A wire record is malformed, unsupported, or not canonical."""


class PrivacyEnvelopeError(ControlRecordError):
    """A public projection would lack a safe binding or disclose unsafe data."""


def _require_exact_record_kind(value: object) -> str:
    if type(value) is not str:
        raise CanonicalizationError(
            RecordErrorCode.INVALID_TYPE,
            "record kind must be an exact string",
        )
    return value


def _require_base_record_factory(cls: type[object]) -> None:
    if cls is not ControlRecord:
        raise CanonicalizationError(
            RecordErrorCode.INVALID_TYPE,
            "control record factories require the exact ControlRecord class",
        )


def _is_unicode_noncharacter(codepoint: int) -> bool:
    return 0xFDD0 <= codepoint <= 0xFDEF or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}


def _normalize_string(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    for character in normalized:
        codepoint = ord(character)
        if unicodedata.category(character) in {"Cc", "Cf", "Cs"}:
            raise CanonicalizationError(
                RecordErrorCode.UNSAFE_UNICODE,
                f"control, format, and surrogate characters are forbidden: U+{codepoint:04X}",
            )
        if _is_unicode_noncharacter(codepoint):
            raise CanonicalizationError(
                RecordErrorCode.UNSAFE_UNICODE,
                f"Unicode noncharacters are forbidden: U+{codepoint:04X}",
            )
    return normalized


def _normalize(
    value: Any,
    *,
    depth: int = 0,
    ancestors: set[int] | None = None,
) -> Any:
    if depth > MAX_NESTING_DEPTH:
        raise CanonicalizationError(
            RecordErrorCode.EXCESSIVE_DEPTH,
            f"canonical value exceeds nesting depth {MAX_NESTING_DEPTH}",
        )
    if isinstance(value, str):
        return _normalize_string(value)
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not MIN_CANONICAL_INTEGER <= value <= MAX_CANONICAL_INTEGER:
            raise CanonicalizationError(
                RecordErrorCode.UNSUPPORTED_NUMBER,
                "canonical JSON v1 integers must fit in a signed 64-bit value",
            )
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            RecordErrorCode.UNSUPPORTED_NUMBER,
            "canonical JSON v1 forbids floating-point numbers",
        )
    ancestors = ancestors if ancestors is not None else set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in ancestors:
            raise CanonicalizationError(
                RecordErrorCode.CYCLIC_VALUE,
                "canonical values must be acyclic",
            )
        ancestors.add(identity)
        normalized: dict[str, Any] = {}
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CanonicalizationError(
                        RecordErrorCode.INVALID_KEY,
                        "canonical object keys must be strings",
                    )
                normalized_key = _normalize_string(key)
                if not _SNAKE_CASE_KEY.fullmatch(normalized_key):
                    raise CanonicalizationError(
                        RecordErrorCode.INVALID_KEY,
                        f"canonical object key is not snake_case: {key!r}",
                    )
                if normalized_key in normalized:
                    raise CanonicalizationError(
                        RecordErrorCode.INVALID_KEY,
                        f"object keys collide after NFC normalization: {key!r}",
                    )
                normalized[normalized_key] = _normalize(
                    item,
                    depth=depth + 1,
                    ancestors=ancestors,
                )
        finally:
            ancestors.remove(identity)
        return normalized
    if isinstance(value, list):
        identity = id(value)
        if identity in ancestors:
            raise CanonicalizationError(
                RecordErrorCode.CYCLIC_VALUE,
                "canonical values must be acyclic",
            )
        ancestors.add(identity)
        try:
            return [
                _normalize(item, depth=depth + 1, ancestors=ancestors)
                for item in value
            ]
        finally:
            ancestors.remove(identity)
    raise CanonicalizationError(
        RecordErrorCode.INVALID_TYPE,
        f"canonical JSON v1 cannot represent {type(value).__name__}",
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _invalid_payload_field(record_kind: str, field: str, detail: str) -> None:
    raise RecordValidationError(
        RecordErrorCode.INVALID_PAYLOAD_FIELD,
        f"{record_kind}.{field}: {detail}",
    )


def _validate_nested_digest(record_kind: str, field: str, value: Any) -> None:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise RecordValidationError(
            RecordErrorCode.INVALID_DIGEST,
            f"{record_kind}.{field} must be a canonical sha256 digest",
        )


def _validate_generation_binding(
    record_kind: str,
    field: str,
    schema: FieldSchema,
    value: Any,
) -> None:
    if not isinstance(value, Mapping):
        _invalid_payload_field(record_kind, field, "must be an object")
    allowed = {"generation_digest", "mode", "sentinel_digest"}
    if set(value) - allowed:
        _invalid_payload_semantics(
            record_kind,
            "generation binding contains fields outside its closed schema",
        )
    mode = value.get("mode")
    if type(mode) is not str or mode not in schema.choices:
        _invalid_payload_semantics(
            record_kind,
            "generation binding mode is not supported",
        )
    expected_fields = {
        GenerationBindingMode.REQUIRED_GENERATION.value: {
            "generation_digest",
            "mode",
        },
        GenerationBindingMode.B0_CAPTURE_SENTINEL.value: {
            "generation_digest",
            "mode",
            "sentinel_digest",
        },
        GenerationBindingMode.NO_GENERATION.value: {"mode"},
    }[mode]
    if set(value) != expected_fields:
        _invalid_payload_semantics(
            record_kind,
            f"{mode} generation binding requires exactly {sorted(expected_fields)!r}",
        )
    for digest_field in expected_fields - {"mode"}:
        _validate_nested_digest(
            record_kind,
            f"{field}.{digest_field}",
            value[digest_field],
        )


def _validate_declared_effects(
    record_kind: str,
    field: str,
    value: Any,
) -> None:
    if not isinstance(value, list) or not value:
        _invalid_payload_field(
            record_kind,
            field,
            "must be a nonempty declared-effect array",
        )
    effect_ids: list[str] = []
    expected_fields = {"classification", "effect_id", "projection_digest"}
    allowed_classifications = {classification.value for classification in EffectClass}
    for index, effect in enumerate(value):
        nested_field = f"{field}[{index}]"
        if not isinstance(effect, Mapping) or set(effect) != expected_fields:
            _invalid_payload_semantics(
                record_kind,
                "each declared effect must use the closed effect schema",
            )
        effect_id = effect["effect_id"]
        if (
            type(effect_id) is not str
            or not _STABLE_IDENTIFIER_PATTERN.fullmatch(effect_id)
        ):
            _invalid_payload_field(
                record_kind,
                f"{nested_field}.effect_id",
                "must be a lowercase stable identifier",
            )
        classification = effect["classification"]
        if (
            type(classification) is not str
            or classification not in allowed_classifications
        ):
            _invalid_payload_field(
                record_kind,
                f"{nested_field}.classification",
                f"must be one of {sorted(allowed_classifications)!r}",
            )
        _validate_nested_digest(
            record_kind,
            f"{nested_field}.projection_digest",
            effect["projection_digest"],
        )
        effect_ids.append(effect_id)
    if len(effect_ids) != len(set(effect_ids)):
        _invalid_payload_semantics(
            record_kind,
            "declared effects must not repeat an effect_id",
        )


def _validate_field_value(
    record_kind: str,
    field: str,
    schema: FieldSchema,
    value: Any,
) -> None:
    if schema.kind is FieldKind.BOOL:
        if type(value) is not bool:
            _invalid_payload_field(record_kind, field, "must be a boolean")
        return
    if schema.kind is FieldKind.DECLARED_EFFECT_LIST:
        _validate_declared_effects(record_kind, field, value)
        return
    if schema.kind is FieldKind.DIGEST:
        if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
            raise RecordValidationError(
                RecordErrorCode.INVALID_DIGEST,
                f"{record_kind}.{field} must be a canonical sha256 digest",
            )
        return
    if schema.kind is FieldKind.DIGEST_LIST:
        if not isinstance(value, list) or (not value and not schema.allow_empty):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a nonempty digest array",
            )
        for item in value:
            if not isinstance(item, str) or not _DIGEST_PATTERN.fullmatch(item):
                raise RecordValidationError(
                    RecordErrorCode.INVALID_DIGEST,
                    f"{record_kind}.{field} contains a malformed sha256 digest",
                )
        if len(value) != len(set(value)):
            _invalid_payload_field(record_kind, field, "must not contain duplicates")
        return
    if schema.kind is FieldKind.DIGEST_SEQUENCE:
        if not isinstance(value, list) or (not value and not schema.allow_empty):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a nonempty digest array",
            )
        for item in value:
            if not isinstance(item, str) or not _DIGEST_PATTERN.fullmatch(item):
                raise RecordValidationError(
                    RecordErrorCode.INVALID_DIGEST,
                    f"{record_kind}.{field} contains a malformed sha256 digest",
                )
        return
    if schema.kind is FieldKind.ENUM:
        if type(value) is not str or value not in schema.choices:
            _invalid_payload_field(
                record_kind,
                field,
                f"must be one of {sorted(schema.choices)!r}",
            )
        return
    if schema.kind is FieldKind.ENUM_LIST:
        if not isinstance(value, list) or (not value and not schema.allow_empty):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a nonempty enum array",
            )
        for item in value:
            if type(item) is not str or item not in schema.choices:
                _invalid_payload_field(
                    record_kind,
                    field,
                    f"contains a value outside {sorted(schema.choices)!r}",
                )
        if len(value) != len(set(value)):
            _invalid_payload_field(record_kind, field, "must not contain duplicates")
        return
    if schema.kind is FieldKind.GENERATION_BINDING:
        _validate_generation_binding(record_kind, field, schema, value)
        return
    if schema.kind is FieldKind.IDENTIFIER:
        if type(value) is not str or not _IDENTIFIER_PATTERN.fullmatch(value):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a lowercase canonical identifier",
            )
        return
    if schema.kind is FieldKind.IDENTIFIER_LIST:
        if not isinstance(value, list) or (not value and not schema.allow_empty):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a nonempty identifier array",
            )
        for item in value:
            if type(item) is not str or not _IDENTIFIER_PATTERN.fullmatch(item):
                _invalid_payload_field(
                    record_kind,
                    field,
                    "contains a noncanonical identifier",
                )
        if len(value) != len(set(value)):
            _invalid_payload_field(record_kind, field, "must not contain duplicates")
        return
    if schema.kind is FieldKind.NONNEGATIVE_INTEGER:
        if type(value) is not int or value < 0:
            _invalid_payload_field(
                record_kind,
                field,
                "must be a nonnegative integer",
            )
        return
    if schema.kind is FieldKind.OBJECT:
        if not isinstance(value, Mapping):
            _invalid_payload_field(record_kind, field, "must be an object")
        return
    if schema.kind is FieldKind.STABLE_IDENTIFIER:
        if (
            type(value) is not str
            or not _STABLE_IDENTIFIER_PATTERN.fullmatch(value)
        ):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a lowercase stable identifier",
            )
        return
    if schema.kind is FieldKind.TEXT:
        if type(value) is not str or not value or len(value) > 4096:
            _invalid_payload_field(
                record_kind,
                field,
                "must be nonempty text no longer than 4096 characters",
            )
        return
    if schema.kind is FieldKind.TIMESTAMP:
        try:
            parse_canonical_timestamp(value)
        except (TypeError, ValueError):
            _invalid_payload_field(
                record_kind,
                field,
                "must be a canonical RFC 3339 timestamp with an explicit offset",
            )
        return
    raise AssertionError(f"unhandled field kind: {schema.kind}")


def _validate_record_payload(record_kind: str, payload: Mapping[str, Any]) -> None:
    schema = RECORD_SCHEMAS[record_kind]
    if not schema.required_fields and not schema.optional_fields:
        return
    missing = set(schema.required_fields) - set(payload)
    if missing:
        raise RecordValidationError(
            RecordErrorCode.MISSING_PAYLOAD_FIELD,
            f"{record_kind} is missing payload fields: {sorted(missing)!r}",
        )
    allowed = set(schema.required_fields) | set(schema.optional_fields)
    unknown = set(payload) - allowed
    if unknown:
        raise RecordValidationError(
            RecordErrorCode.UNKNOWN_PAYLOAD_FIELD,
            f"{record_kind} has unknown payload fields: {sorted(unknown)!r}",
        )
    for field, field_schema in schema.required_fields.items():
        _validate_field_value(record_kind, field, field_schema, payload[field])
    for field, field_schema in schema.optional_fields.items():
        if field in payload:
            _validate_field_value(record_kind, field, field_schema, payload[field])
    _validate_record_semantics(record_kind, payload)


def _invalid_payload_semantics(record_kind: str, detail: str) -> None:
    raise RecordValidationError(
        RecordErrorCode.INVALID_PAYLOAD_SEMANTICS,
        f"{record_kind}: {detail}",
    )


def _validate_record_semantics(record_kind: str, payload: Mapping[str, Any]) -> None:
    if record_kind == "assignment":
        conditional = payload["applicability"] == "conditional"
        has_predicate = "predicate_digest" in payload
        if conditional != has_predicate:
            _invalid_payload_semantics(
                record_kind,
                "conditional applicability requires exactly one predicate digest",
            )
        if (
            payload["execution_requirement"] == "blocking_scenario"
            and payload["impact"] != "blocking"
        ):
            _invalid_payload_semantics(
                record_kind,
                "a blocking scenario requires blocking impact",
            )
    elif record_kind == "dependency_projection":
        dependency_keys = payload["dependency_keys"]
        if len(dependency_keys) != len(payload["dependency_digests"]):
            _invalid_payload_semantics(
                record_kind,
                "dependency keys and digests must have equal lengths",
            )
        if tuple(dependency_keys) != tuple(sorted(dependency_keys)):
            _invalid_payload_semantics(
                record_kind,
                "dependency bindings must be ordered by dependency key",
            )
    elif record_kind == "invalidation_policy":
        dependency_keys = payload["dependency_keys"]
        if tuple(dependency_keys) != tuple(sorted(dependency_keys)):
            _invalid_payload_semantics(
                record_kind,
                "invalidation dependency keys must be in canonical order",
            )
    elif record_kind == "invalidation_stream_checkpoint":
        if payload["complete_through_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "complete_through_sequence must be positive",
            )
    elif record_kind == "attempt":
        if payload["journal_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "journal_sequence must be positive",
            )
    elif record_kind == "intent":
        if payload["journal_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "journal_sequence must be positive",
            )
        gate_occurrence = payload["intent_type"] == "gate_occurrence"
        has_assignment = "assignment_digest" in payload
        has_operation_plan = "operation_plan_digest" in payload
        if gate_occurrence and (not has_assignment or has_operation_plan):
            _invalid_payload_semantics(
                record_kind,
                "a gate occurrence binds one assignment and no operation plan",
            )
        if not gate_occurrence and (has_assignment or not has_operation_plan):
            _invalid_payload_semantics(
                record_kind,
                "a critical operation binds one operation plan and no assignment",
            )
    elif record_kind == "invalidation":
        closed = payload["status"] == "closed"
        has_closed_at = "closed_at" in payload
        if closed != has_closed_at:
            _invalid_payload_semantics(
                record_kind,
                "closed_at is present exactly when the episode is closed",
            )
        if closed and parse_canonical_timestamp(
            payload["closed_at"]
        ) < parse_canonical_timestamp(payload["opened_at"]):
            _invalid_payload_semantics(
                record_kind,
                "closed_at cannot precede opened_at",
            )
    elif record_kind == "evaluation":
        applicability = payload["applicability"]
        outcome = payload["outcome"]
        attestation_count = len(payload["attestation_digests"])
        has_attestations = attestation_count > 0
        has_predicate_proof = "predicate_proof_digest" in payload
        unknown_reason = payload.get("unknown_reason")
        allowed_outcomes = {
            "applicable": {"blocked", "fail", "pass"},
            "applicable_unknown": {"unknown"},
            "not_applicable": {"not_applicable"},
            "not_due": {"unknown"},
        }
        if outcome not in allowed_outcomes[applicability]:
            _invalid_payload_semantics(
                record_kind,
                "outcome does not match the applicability state",
            )
        if applicability == "not_applicable":
            if has_attestations or not has_predicate_proof:
                _invalid_payload_semantics(
                    record_kind,
                    "not-applicable evaluation requires one predicate proof and no attestations",
                )
        elif applicability == "applicable":
            if not has_attestations:
                _invalid_payload_semantics(
                    record_kind,
                    "applicable evaluation requires attestations",
                )
        elif applicability == "applicable_unknown":
            if unknown_reason is None:
                _invalid_payload_semantics(
                    record_kind,
                    "applicable-unknown evaluation requires one unknown reason",
                )
            if unknown_reason == "missing_applicability_proof":
                coherent_provenance = not has_attestations and not has_predicate_proof
            elif unknown_reason == "missing_attestation":
                coherent_provenance = not has_attestations
            elif unknown_reason in _EVALUATION_PROOF_UNKNOWN_REASONS:
                coherent_provenance = not has_attestations and has_predicate_proof
            else:
                coherent_provenance = attestation_count == 1
            if not coherent_provenance:
                _invalid_payload_semantics(
                    record_kind,
                    "applicable-unknown reason does not bind its exact evidence provenance",
                )
        elif has_attestations or has_predicate_proof:
            _invalid_payload_semantics(
                record_kind,
                "not-due evaluation cannot claim terminal evidence",
            )
        if applicability != "applicable_unknown" and unknown_reason is not None:
            _invalid_payload_semantics(
                record_kind,
                "unknown_reason is present exactly for applicable-unknown evaluations",
            )
    elif record_kind == "validation_context":
        active = payload["context_type"] == "active_contract"
        active_fields = {"contract_digest", "generation_digest"}
        preassembly_fields = {
            "artifact_digests",
            "profile_digest",
            "source_closure_digest",
        }
        present = set(payload)
        if active and (
            not active_fields <= present or bool(preassembly_fields & present)
        ):
            _invalid_payload_semantics(
                record_kind,
                "active context requires contract/generation and forbids preassembly bindings",
            )
        if not active and (
            not preassembly_fields <= present or bool(active_fields & present)
        ):
            _invalid_payload_semantics(
                record_kind,
                "preassembly context requires profile/source/artifacts and "
                "forbids active bindings",
            )
    elif record_kind == "authority_register":
        valid = payload["status"] == "valid"
        selected = "selected_manifest_digest" in payload
        has_receipts = bool(payload["quorum_receipt_digests"])
        if valid and (not selected or not has_receipts):
            _invalid_payload_semantics(
                record_kind,
                "a valid register observation requires a selected manifest and receipts",
            )
        if not valid and (selected or has_receipts):
            _invalid_payload_semantics(
                record_kind,
                "absent or corrupt observations cannot assert a manifest or quorum",
            )
    elif record_kind == "authorization":
        if payload["subject_kind"] not in RECORD_KINDS:
            _invalid_payload_semantics(
                record_kind,
                "subject_kind must name a registered control-record family",
            )
        allowed_identities = payload.get("allowed_actor_identity_digests", ())
        allowed_roles = payload.get("allowed_actor_roles", ())
        if not allowed_identities and not allowed_roles:
            _invalid_payload_semantics(
                record_kind,
                "authorization requires at least one allowed actor identity or role",
            )
    elif record_kind == "composite_change_set":
        changed_fields = tuple(payload["changed_fields"])
        if changed_fields != tuple(sorted(changed_fields)):
            _invalid_payload_semantics(
                record_kind,
                "changed fields must be in canonical order",
            )
        transition_mode = payload["transition_mode"]
        old_manifest = payload["old_manifest_digest"]
        candidate_manifest = payload["candidate_manifest_digest"]
        rollback_manifest = payload["rollback_manifest_digest"]
        reinstatement = transition_mode == "register_reinstatement"
        has_prior_checkpoint = "prior_committed_checkpoint_digest" in payload
        has_current_register_observation = (
            "current_authority_register_observation_digest" in payload
        )
        expected_action = (
            "reinstate_composite_authority"
            if reinstatement
            else "transition_composite_authority"
        )
        if payload["authorization_action"] != expected_action:
            _invalid_payload_semantics(
                record_kind,
                "authorization action must match the transition mode",
            )
        if reinstatement != has_prior_checkpoint:
            _invalid_payload_semantics(
                record_kind,
                "only register reinstatement binds a prior committed checkpoint",
            )
        if reinstatement != has_current_register_observation:
            _invalid_payload_semantics(
                record_kind,
                "only register reinstatement binds the current authority-register observation",
            )
        if not reinstatement:
            if old_manifest == candidate_manifest:
                _invalid_payload_semantics(
                    record_kind,
                    "a composite transition requires distinct old and candidate manifests",
                )
            if rollback_manifest != old_manifest:
                _invalid_payload_semantics(
                    record_kind,
                    "a composite transition must roll back to the exact old manifest",
                )
            if not changed_fields:
                _invalid_payload_semantics(
                    record_kind,
                    "a composite transition requires a nonempty projection change set",
                )
            if "fallback" not in changed_fields:
                _invalid_payload_semantics(
                    record_kind,
                    "a composite transition must bind the old manifest as fallback",
                )
            generation_fields = {
                "accepted_generation",
                "active_generation",
                "rollback_generation",
            }
            changed_generations = generation_fields & set(changed_fields)
            binding_mode = payload["generation_binding"]["mode"]
            if transition_mode == "control_update" and (
                changed_generations
                or binding_mode != GenerationBindingMode.NO_GENERATION.value
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "control update cannot change generation pointers",
                )
            if transition_mode == "activation" and (
                "active_generation" not in changed_generations
                or "accepted_generation" in changed_generations
                or binding_mode
                != GenerationBindingMode.REQUIRED_GENERATION.value
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "activation changes the active pointer and preserves accepted",
                )
            if transition_mode == "acceptance" and (
                changed_generations != {"accepted_generation"}
                or binding_mode
                != GenerationBindingMode.REQUIRED_GENERATION.value
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "acceptance changes only the accepted generation pointer",
                )
            joint_fields = {
                "quorum_policy",
                "recovery_policy",
                "witness_roster",
            }
            expected_quorum_mode = (
                "joint_consensus"
                if joint_fields & set(changed_fields)
                else "existing"
            )
            if payload["quorum_mode"] != expected_quorum_mode:
                _invalid_payload_semantics(
                    record_kind,
                    "quorum mode must be derived from the changed authority projections",
                )
        else:
            if not old_manifest == candidate_manifest == rollback_manifest:
                _invalid_payload_semantics(
                    record_kind,
                    "register reinstatement must select the exact prior whole manifest",
                )
            if changed_fields:
                _invalid_payload_semantics(
                    record_kind,
                    "register reinstatement cannot change manifest projections",
                )
            if payload["quorum_mode"] != "recovery_root":
                _invalid_payload_semantics(
                    record_kind,
                    "register reinstatement requires recovery-root authority",
                )
            if (
                payload["generation_binding"]["mode"]
                != GenerationBindingMode.NO_GENERATION.value
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "register reinstatement has no generation projection change",
                )
    elif record_kind == "composite_authority_checkpoint":
        if payload["register_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "committed checkpoint register sequence must be positive",
            )
    elif record_kind == "quorum_policy":
        if payload["threshold"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "quorum threshold must be positive",
            )
    elif record_kind == "witness_roster":
        witnesses = tuple(payload["witness_identity_digests"])
        if witnesses != tuple(sorted(witnesses)):
            _invalid_payload_semantics(
                record_kind,
                "witness identities must be in canonical order",
            )
    elif record_kind == "capability":
        if payload["fence_epoch"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "fence_epoch must be positive",
            )
        issued_at = parse_canonical_timestamp(payload["issued_at"])
        expires_at = parse_canonical_timestamp(payload["expires_at"])
        if issued_at >= expires_at:
            _invalid_payload_semantics(
                record_kind,
                "capability expiry must follow issuance",
            )
        recovery_fields = {
            "predecessor_failure_record_digest",
            "predecessor_fence_epoch",
            "predecessor_operation_id",
            "recovery_contract_digest",
            "recovery_owner_role",
        }
        present_recovery_fields = recovery_fields & set(payload)
        if payload["capability_type"] == "recovery":
            if present_recovery_fields != recovery_fields:
                _invalid_payload_semantics(
                    record_kind,
                    "recovery capability requires complete predecessor and owner binding",
                )
            if payload["predecessor_operation_id"] == payload["operation_id"]:
                _invalid_payload_semantics(
                    record_kind,
                    "recovery capability predecessor and successor must differ",
                )
            if payload["predecessor_fence_epoch"] >= payload["fence_epoch"]:
                _invalid_payload_semantics(
                    record_kind,
                    "recovery fence must advance the predecessor fence",
                )
        elif present_recovery_fields:
            _invalid_payload_semantics(
                record_kind,
                "non-recovery capability forbids predecessor recovery fields",
            )
    elif record_kind == "operation":
        if (
            payload["expected_protected_state_digest"]
            == payload["intended_protected_state_digest"]
        ):
            _invalid_payload_semantics(
                record_kind,
                "critical operation prestate and intended state must differ",
            )
        operation_kind = CriticalOperationKind(payload["operation_kind"])
        try:
            validate_operation_coordinates(
                operation_kind,
                OperationSubjectKind(payload["subject_kind"]),
                OperationTargetKind(payload["target_kind"]),
                GenerationBindingMode(payload["generation_binding"]["mode"]),
                GenerationClass(payload["generation_class"]),
                LifecyclePhase(payload["lifecycle_phase"]),
            )
        except ValueError:
            _invalid_payload_semantics(
                record_kind,
                "operation envelope coordinates are invalid for operation kind",
            )
        generation_binding = payload["generation_binding"]
        if (
            payload["subject_kind"] == "generation"
            and payload["subject_digest"]
            != generation_binding.get("generation_digest")
        ):
            _invalid_payload_semantics(
                record_kind,
                "generation subject must equal the bound generation",
            )
    elif record_kind == "operation_obligation":
        try:
            validate_operation_coordinates(
                CriticalOperationKind(payload["operation_kind"]),
                OperationSubjectKind(payload["subject_kind"]),
                OperationTargetKind(payload["target_kind"]),
                GenerationBindingMode(payload["generation_binding"]["mode"]),
                GenerationClass(payload["generation_class"]),
                LifecyclePhase(payload["lifecycle_phase"]),
            )
        except ValueError:
            _invalid_payload_semantics(
                record_kind,
                "operation envelope coordinates are invalid for operation kind",
            )
        generation_binding = payload["generation_binding"]
        if (
            payload["subject_kind"] == "generation"
            and payload["subject_digest"]
            != generation_binding.get("generation_digest")
        ):
            _invalid_payload_semantics(
                record_kind,
                "generation subject must equal the bound generation",
            )
    elif record_kind == "operation_requirement":
        try:
            validate_operation_coordinates(
                CriticalOperationKind(payload["operation_kind"]),
                OperationSubjectKind(payload["subject_kind"]),
                OperationTargetKind(payload["target_kind"]),
                GenerationBindingMode(payload["generation_binding_mode"]),
                GenerationClass(payload["generation_class"]),
                LifecyclePhase(payload["lifecycle_phase"]),
            )
        except ValueError:
            _invalid_payload_semantics(
                record_kind,
                "operation requirement coordinates are invalid for operation kind",
            )
        subject_kind_by_role = {
            "candidate_generation": "generation",
            "captured_baseline": "generation",
            "composite_authority": "composite_authority",
            "control_record": "control_record",
            "gate_occurrence": "gate_occurrence",
        }
        if (
            payload["subject_kind"]
            != subject_kind_by_role[payload["subject_binding_role"]]
        ):
            _invalid_payload_semantics(
                record_kind,
                "subject binding role contradicts the operation subject kind",
            )
        generation_mode_by_role = {
            "b0_capture_sentinel": "b0_capture_sentinel",
            "candidate_generation": "required_generation",
            "captured_baseline_generation": "required_generation",
            "no_generation": "no_generation",
            "predecessor_generation": "required_generation",
        }
        if (
            payload["generation_binding_mode"]
            != generation_mode_by_role[payload["generation_binding_role"]]
        ):
            _invalid_payload_semantics(
                record_kind,
                "generation binding role contradicts the generation binding mode",
            )
        gate_occurrence = payload["subject_binding_role"] == "gate_occurrence"
        has_assignment = "assignment_digest" in payload
        if gate_occurrence != has_assignment:
            _invalid_payload_semantics(
                record_kind,
                "gate-occurrence requirements bind one assignment and other requirements forbid it",
            )
        if gate_occurrence:
            purpose = payload["purpose"]
            realization_condition = payload["realization_condition"]
            final_restart = purpose == "final_service_restart"
            conditional_scenario = purpose in {
                "blocking_scenario",
                "service_anchor",
                "service_restart",
            }
            if (
                final_restart
                and realization_condition != "always"
            ) or (
                not final_restart
                and (
                    not conditional_scenario
                    or realization_condition != "when_assignment_applicable"
                )
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "gate-occurrence requirements realize conditional scenarios or one always-realized final restart",
                )
        elif payload["realization_condition"] != "always":
            _invalid_payload_semantics(
                record_kind,
                "nongate operation requirements are always realized",
            )
        purpose_coordinates = {
            "baseline_rehearsal_install": (
                "package_installation",
                "live_root",
                "c",
                "active",
            ),
            "baseline_restoration": (
                "rollback",
                "live_root",
                "c",
                "active",
            ),
            "service_anchor": (
                "blocking_scenario",
                "service",
                "c",
                "active",
            ),
            "service_restart": (
                "blocking_scenario",
                "service",
                "c",
                "active",
            ),
            "final_service_restart": (
                "blocking_scenario",
                "service",
                "c",
                "active",
            ),
        }
        required_coordinates = purpose_coordinates.get(payload["purpose"])
        actual_coordinates = (
            payload["operation_kind"],
            payload["target_kind"],
            payload["generation_class"],
            payload["lifecycle_phase"],
        )
        if (
            required_coordinates is not None
            and actual_coordinates != required_coordinates
        ):
            _invalid_payload_semantics(
                record_kind,
                "operation requirement purpose has invalid authority coordinates",
            )
    elif record_kind == "retention_lease":
        issued_at = parse_canonical_timestamp(payload["issued_at"])
        expires_at = parse_canonical_timestamp(payload["expires_at"])
        if issued_at >= expires_at:
            _invalid_payload_semantics(
                record_kind,
                "retention lease expiry must follow issuance",
            )
    elif record_kind == "recovery_policy":
        contract_digests = tuple(payload["recovery_contract_digests"])
        owner_roles = tuple(payload["recovery_owner_roles"])
        if contract_digests != tuple(sorted(contract_digests)):
            _invalid_payload_semantics(
                record_kind,
                "recovery contracts must be in canonical order",
            )
        if owner_roles != tuple(sorted(owner_roles)):
            _invalid_payload_semantics(
                record_kind,
                "recovery owner roles must be in canonical order",
            )
    elif record_kind in {
        "final_service_anchor_receipt",
        "service_anchor_receipt",
    }:
        issued_at = parse_canonical_timestamp(payload["issued_at"])
        expires_at = parse_canonical_timestamp(payload["expires_at"])
        if (expires_at - issued_at).total_seconds() != 300:
            _invalid_payload_semantics(
                record_kind,
                "service anchor health lease must last exactly five minutes",
            )
    elif record_kind == "validation_contract":
        max_live_attempt_seconds = payload["max_live_attempt_seconds"]
        max_suite_seconds = payload["max_suite_seconds"]
        if not 0 < max_live_attempt_seconds <= 3600:
            _invalid_payload_semantics(
                record_kind,
                "live-attempt budget must be positive and no more than 60 minutes",
            )
        if not 0 < max_suite_seconds <= 28800:
            _invalid_payload_semantics(
                record_kind,
                "suite budget must be positive and no more than eight hours",
            )
    elif record_kind == "requirements":
        version = payload["requirements_version"]
        has_predecessor = "supersedes_requirements_digest" in payload
        if version <= 0:
            _invalid_payload_semantics(
                record_kind,
                "requirements_version must be positive",
            )
        if (version > 1) != has_predecessor:
            _invalid_payload_semantics(
                record_kind,
                "requirements versions after v1 must bind exactly one predecessor",
            )
    elif record_kind in {"recovery", "rollback"}:
        origin = payload["origin_generation_digest"]
        destination = payload["destination_generation_digest"]
        binding_generation = payload["generation_binding"]["generation_digest"]
        if origin == destination:
            _invalid_payload_semantics(
                record_kind,
                "origin and destination generations must differ",
            )
        if binding_generation != origin:
            _invalid_payload_semantics(
                record_kind,
                "generation binding must name the exact origin generation",
            )
        target_generation_field = (
            "exact_state_generation_digest"
            if record_kind == "recovery"
            else "target_generation_digest"
        )
        if payload[target_generation_field] != destination:
            _invalid_payload_semantics(
                record_kind,
                "target protected-state generation must equal destination generation",
            )
    elif record_kind == "rollback_registry":
        if payload["selected_rollback_digest"] not in payload["rollback_digests"]:
            _invalid_payload_semantics(
                record_kind,
                "selected rollback must be an exact member of the registry",
            )
    elif record_kind == "inclusion_edge":
        if payload["active_contract_digest"] == payload["preassembly_context_digest"]:
            _invalid_payload_semantics(
                record_kind,
                "inclusion edge must cross from preassembly into an active contract",
            )
    elif record_kind == "lifecycle_checkpoint":
        coordinate = (payload["generation_class"], payload["phase"])
        legal_coordinates = {
            ("b0", "captured"),
            ("f", "foundation_validation"),
            ("c", "published"),
            ("c", "prevalidated"),
            ("c", "active"),
            ("c", "accepted"),
        }
        if coordinate not in legal_coordinates:
            _invalid_payload_semantics(
                record_kind,
                "generation class and lifecycle phase are not a legal checkpoint",
            )
        nonroot_fields = {
            "authority_proof_digest",
            "contract_digest",
            "evidence_cut_digest",
            "predecessor_checkpoint_digest",
        }
        present_nonroot_fields = nonroot_fields & set(payload)
        root = coordinate == ("b0", "captured")
        foundation = coordinate == ("f", "foundation_validation")
        has_root_authorization = "root_authorization_digest" in payload
        if root:
            if present_nonroot_fields or not has_root_authorization:
                _invalid_payload_semantics(
                    record_kind,
                    "captured B0 root requires root authorization and forbids nonroot material",
                )
        elif foundation:
            if present_nonroot_fields != {"predecessor_checkpoint_digest"} or has_root_authorization:
                _invalid_payload_semantics(
                    record_kind,
                    "foundation checkpoint requires only its structural predecessor",
                )
        elif present_nonroot_fields != nonroot_fields or has_root_authorization:
            _invalid_payload_semantics(
                record_kind,
                "C checkpoint requires contract, cut, proof, and predecessor",
            )
        acceptance_fields = {
            "acceptance_request_digest",
            "approval_digest",
            "final_service_anchor_receipt_digest",
        }
        present_acceptance_fields = acceptance_fields & set(payload)
        accepted = coordinate == ("c", "accepted")
        if accepted and present_acceptance_fields != acceptance_fields:
            _invalid_payload_semantics(
                record_kind,
                "accepted checkpoint requires request and approval",
            )
        if not accepted and present_acceptance_fields:
            _invalid_payload_semantics(
                record_kind,
                "nonaccepted checkpoint forbids request and approval",
            )
        if (
            "baseline_restoration_receipt_digest" in payload
            and coordinate != ("c", "prevalidated")
        ):
            _invalid_payload_semantics(
                record_kind,
                "only a prevalidated C checkpoint may bind baseline restoration",
            )
        if (
            "service_anchor_receipt_digest" in payload
            and coordinate != ("c", "active")
        ):
            _invalid_payload_semantics(
                record_kind,
                "only an active C checkpoint may authorize a service anchor",
            )
    elif record_kind == "atomic_evidence_cut" or record_kind == "promotion_authority_proof":
        if payload["complete_through_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "complete_through_sequence must be positive",
            )
        operation_count = len(payload["operation_digests"])
        if (
            operation_count != len(payload["operation_terminal_digests"])
            or operation_count != len(payload["capability_digests"])
        ):
            _invalid_payload_semantics(
                record_kind,
                "every critical operation requires one capability and terminal record",
            )
        if len(payload["evaluation_digests"]) != len(
            payload["currency_proof_digests"]
        ):
            _invalid_payload_semantics(
                record_kind,
                "every evaluation requires one exact currency proof",
            )
        if record_kind == "promotion_authority_proof":
            acceptance_fields = {
                "acceptance_request_digest",
                "approval_digest",
                "final_service_anchor_receipt_digest",
            }
            present_acceptance_fields = acceptance_fields & set(payload)
            if payload["phase"] == "accepted":
                if present_acceptance_fields != acceptance_fields:
                    _invalid_payload_semantics(
                        record_kind,
                        "accepted proof requires request and approval",
                    )
            elif present_acceptance_fields:
                _invalid_payload_semantics(
                    record_kind,
                    "nonaccepted proof forbids request and approval",
                )
    elif record_kind == "promotion_contract":
        phase_operation_field = "phase_establishing_operation_obligation_digest"
        acceptance_field = "acceptance_authorization_digest"
        restoration_field = "baseline_restoration_receipt_digest"
        service_anchor_field = "predecessor_service_anchor_receipt_digest"
        phase = payload["phase"]
        accepted = payload["phase"] == "accepted"
        if accepted:
            if (
                acceptance_field not in payload
                or service_anchor_field not in payload
                or phase_operation_field in payload
            ):
                _invalid_payload_semantics(
                    record_kind,
                    "accepted contract requires acceptance authorization and its predecessor service anchor and forbids a phase operation",
                )
        elif phase_operation_field not in payload or acceptance_field in payload:
            _invalid_payload_semantics(
                record_kind,
                "nonaccepted contract requires a phase operation and forbids acceptance authorization",
            )
        active = phase == "active"
        if active != (restoration_field in payload):
            _invalid_payload_semantics(
                record_kind,
                "active contract requires one baseline restoration receipt and other phases forbid it",
            )
        if service_anchor_field in payload and not accepted:
            _invalid_payload_semantics(
                record_kind,
                "only an accepted contract may consume a service anchor receipt",
            )
    elif record_kind == "terminal_record":
        if payload["journal_sequence"] <= 0:
            _invalid_payload_semantics(
                record_kind,
                "journal_sequence must be positive",
            )
        gate_fields = {"assignment_digest", "attempt_digest"}
        has_gate_fields = gate_fields & set(payload)
        has_operation = "operation_digest" in payload
        has_capability = "capability_digest" in payload
        has_predicate_proof = "predicate_proof_digest" in payload
        if payload["terminal_type"] == "gate_attempt":
            if has_gate_fields != gate_fields or has_operation or has_capability:
                _invalid_payload_semantics(
                    record_kind,
                    "gate-attempt terminal requires assignment/attempt and forbids operation capability",
                )
        elif (
            has_gate_fields
            or not has_operation
            or not has_capability
            or has_predicate_proof
        ):
            _invalid_payload_semantics(
                record_kind,
                "critical-operation terminal requires operation/capability and forbids gate coordinates",
            )
        elif (
            payload["outcome"] == "succeeded"
            and not payload["validator_attestation_digests"]
        ):
            _invalid_payload_semantics(
                record_kind,
                "successful critical-operation terminal requires validator evidence",
            )


def _is_safe_public_value(
    record_kind: str,
    field: str,
    value: Any,
) -> bool:
    schema = RECORD_SCHEMAS[record_kind]
    field_schema = schema.required_fields.get(field)
    if field_schema is None:
        field_schema = schema.optional_fields.get(field)
    if field_schema is None:
        return False
    try:
        _validate_field_value(record_kind, field, field_schema, value)
    except RecordValidationError:
        return False
    return True


def _validate_opaque_ref(
    opaque_ref: Any,
) -> str:
    if not isinstance(opaque_ref, str) or not _OPAQUE_REF_PATTERN.fullmatch(
        opaque_ref
    ):
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_OPAQUE_REF,
            "opaque reference must be a key-derived opaque_hmac_sha256:v1 token",
        )
    return opaque_ref


def _validate_privacy_key(
    value: Any,
    *,
    field: str,
    code: RecordErrorCode,
) -> bytes:
    if type(value) is not bytes or not 32 <= len(value) <= 4096:
        raise PrivacyEnvelopeError(
            code,
            f"{field} must contain between 32 and 4096 bytes",
        )
    return value


def _validate_public_envelope_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != {"binding", "public", "source_kind"}:
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
            "public envelope payload has fields outside its closed schema",
        )
    source_kind = payload["source_kind"]
    if (
        not isinstance(source_kind, str)
        or source_kind not in RECORD_SCHEMAS
        or source_kind == "public_envelope"
    ):
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
            "public envelope source_kind is not a restricted record kind",
        )

    binding = payload["binding"]
    if not isinstance(binding, Mapping) or not binding:
        raise PrivacyEnvelopeError(
            RecordErrorCode.PRIVACY_BINDING_REQUIRED,
            "public envelope has no restricted-record binding",
        )
    if not set(binding) <= {"keyed_commitment", "opaque_ref"}:
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
            "public envelope binding has fields outside its closed schema",
        )
    if "opaque_ref" in binding:
        _validate_opaque_ref(binding["opaque_ref"])
    if "keyed_commitment" in binding:
        commitment = binding["keyed_commitment"]
        if not isinstance(commitment, str) or not _KEYED_COMMITMENT_PATTERN.fullmatch(
            commitment
        ):
            raise PrivacyEnvelopeError(
                RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                "public envelope keyed commitment is malformed",
            )

    public = payload["public"]
    schema = RECORD_SCHEMAS[source_kind]
    if not isinstance(public, Mapping) or not set(public) <= schema.public_fields:
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
            "public envelope metadata exceeds the source schema allowlist",
        )
    for field, value in public.items():
        if not _is_safe_public_value(source_kind, field, value):
            raise PrivacyEnvelopeError(
                RecordErrorCode.UNSAFE_PUBLIC_VALUE,
                f"allowlisted public field has an unrecognized value: {field!r}",
            )


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_detached_signature(
    signature: Mapping[str, Any],
    *,
    record_digest: str,
) -> None:
    required = {
        "algorithm",
        "signed_digest",
        "signer_identity_digest",
        "value",
    }
    if set(signature) != required:
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached signature contains fields outside its closed schema",
        )
    if signature["algorithm"] != "ed25519":
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached signature algorithm must be ed25519",
        )
    signer_digest = signature["signer_identity_digest"]
    if not isinstance(signer_digest, str) or not _DIGEST_PATTERN.fullmatch(
        signer_digest
    ):
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached signature signer identity must be a canonical digest",
        )
    signed_digest = signature["signed_digest"]
    if (
        not isinstance(signed_digest, str)
        or not _DIGEST_PATTERN.fullmatch(signed_digest)
        or not hmac.compare_digest(signed_digest, record_digest)
    ):
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached signature must bind the canonical record digest",
        )
    value = signature["value"]
    if not isinstance(value, str) or not _ED25519_SIGNATURE_PATTERN.fullmatch(value):
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached ed25519 signature must be unpadded base64url",
        )
    try:
        decoded = base64.b64decode(value + "==", altchars=b"-_", validate=True)
    except (ValueError, TypeError) as error:
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached ed25519 signature is malformed",
        ) from error
    if len(decoded) != 64:
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached ed25519 signature must contain 64 bytes",
        )
    canonical_value = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(value, canonical_value):
        raise RecordValidationError(
            RecordErrorCode.INVALID_SIGNATURE,
            "detached ed25519 signature must use canonical base64url pad bits",
        )


def _public_envelope_record_id(payload: Mapping[str, Any]) -> str:
    envelope_hash = hashlib.sha256(
        _PUBLIC_ENVELOPE_ID_DOMAIN + _canonical_json(payload)
    ).hexdigest()
    return f"public_envelope_sha256:v1:{envelope_hash}"


@dataclass(frozen=True, slots=True, init=False)
class ControlRecord:
    """A schema-versioned control record with deterministic wire bytes."""

    kind: str
    record_id: str
    payload: Mapping[str, Any]
    _digest: str
    signature: Mapping[str, Any] | None = None

    @classmethod
    def signing_digest(
        cls,
        *,
        kind: str,
        record_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        """Return the validated canonical core digest for detached signing."""

        _require_base_record_factory(cls)
        kind = _require_exact_record_kind(kind)
        if kind == "public_envelope":
            raise PrivacyEnvelopeError(
                RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                "public envelopes must be derived from a restricted record",
            )
        return cls._build(
            kind=kind,
            record_id=record_id,
            payload=payload,
            allow_public_envelope=False,
            allow_unsigned_required_signature=True,
        ).digest()

    @classmethod
    def build(
        cls,
        *,
        kind: str,
        record_id: str,
        payload: Mapping[str, Any],
        signature: Mapping[str, Any] | None = None,
    ) -> ControlRecord:
        _require_base_record_factory(cls)
        kind = _require_exact_record_kind(kind)
        if kind == "public_envelope":
            raise PrivacyEnvelopeError(
                RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                "public envelopes must be derived from a restricted record",
            )
        return cls._build(
            kind=kind,
            record_id=record_id,
            payload=payload,
            signature=signature,
            allow_public_envelope=False,
        )

    @classmethod
    def _build(
        cls,
        *,
        kind: str,
        record_id: str,
        payload: Mapping[str, Any],
        signature: Mapping[str, Any] | None = None,
        allow_public_envelope: bool,
        allow_unsigned_required_signature: bool = False,
    ) -> ControlRecord:
        _require_base_record_factory(cls)
        kind = _require_exact_record_kind(kind)
        if kind == "public_envelope" and not allow_public_envelope:
            raise PrivacyEnvelopeError(
                RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                "public envelopes must be derived from a restricted record",
            )
        if kind not in RECORD_KINDS:
            raise ControlRecordError(
                RecordErrorCode.UNSUPPORTED_KIND,
                f"record kind is not registered: {kind!r}",
            )
        if not isinstance(record_id, str):
            raise CanonicalizationError(
                RecordErrorCode.INVALID_TYPE,
                "record_id must be a string",
            )
        normalized_record_id = _normalize_string(record_id)
        if not normalized_record_id:
            raise CanonicalizationError(
                RecordErrorCode.INVALID_TYPE,
                "record_id must not be empty",
            )
        if not isinstance(payload, Mapping):
            raise CanonicalizationError(
                RecordErrorCode.INVALID_TYPE,
                "record payload must be an object",
            )
        normalized_payload = _normalize(payload)
        _validate_record_payload(kind, normalized_payload)
        if kind == "public_envelope":
            _validate_public_envelope_payload(normalized_payload)
            expected_record_id = _public_envelope_record_id(normalized_payload)
            if normalized_record_id != expected_record_id:
                raise PrivacyEnvelopeError(
                    RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                    "public envelope record_id must be derived from its safe payload",
                )
            if signature is not None:
                raise PrivacyEnvelopeError(
                    RecordErrorCode.INVALID_PUBLIC_ENVELOPE,
                    "public envelopes forbid detached signatures",
                )
        if signature is not None and not isinstance(signature, Mapping):
            raise CanonicalizationError(
                RecordErrorCode.INVALID_TYPE,
                "record signature must be an object",
            )
        normalized_signature = (
            _normalize(signature) if signature is not None else None
        )
        core = {
            "kind": kind,
            "payload": normalized_payload,
            "record_id": normalized_record_id,
            "schema": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
        }
        digest = "sha256:" + hashlib.sha256(
            _DIGEST_DOMAIN + _canonical_json(core)
        ).hexdigest()
        if normalized_signature is not None:
            _validate_detached_signature(
                normalized_signature,
                record_digest=digest,
            )
        signature_required = kind == "composite_authority_checkpoint"
        if (
            signature_required
            and normalized_signature is None
            and not allow_unsigned_required_signature
        ):
            raise RecordValidationError(
                RecordErrorCode.INVALID_SIGNATURE,
                "composite authority checkpoint requires a detached signature",
            )
        if (
            signature_required
            and normalized_signature is not None
            and normalized_signature["signer_identity_digest"]
            != normalized_payload["signer_identity_digest"]
        ):
            raise RecordValidationError(
                RecordErrorCode.INVALID_SIGNATURE,
                "checkpoint signature must use the bound signer identity",
            )
        record = object.__new__(cls)
        object.__setattr__(record, "kind", kind)
        object.__setattr__(record, "record_id", normalized_record_id)
        object.__setattr__(record, "payload", _freeze(normalized_payload))
        object.__setattr__(record, "_digest", digest)
        object.__setattr__(
            record,
            "signature",
            (
                _freeze(normalized_signature)
                if normalized_signature is not None
                else None
            ),
        )
        if len(record.canonical_bytes()) > MAX_RECORD_BYTES:
            raise CanonicalizationError(
                RecordErrorCode.EXCESSIVE_SIZE,
                f"canonical record exceeds {MAX_RECORD_BYTES} bytes",
            )
        return record

    @classmethod
    def parse(cls, wire: bytes | str) -> ControlRecord:
        _require_base_record_factory(cls)
        if type(wire) is bytes:
            raw = wire
        elif type(wire) is str:
            try:
                raw = wire.encode("utf-8")
            except UnicodeEncodeError as error:
                raise RecordValidationError(
                    RecordErrorCode.INVALID_JSON,
                    "wire record is not valid UTF-8",
                ) from error
        else:
            raise RecordValidationError(
                RecordErrorCode.INVALID_TYPE,
                "wire record must be bytes or text",
            )
        if len(raw) > MAX_RECORD_BYTES:
            raise CanonicalizationError(
                RecordErrorCode.EXCESSIVE_SIZE,
                f"wire record exceeds {MAX_RECORD_BYTES} bytes",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RecordValidationError(
                RecordErrorCode.INVALID_JSON,
                "wire record is not valid UTF-8",
            ) from error
        try:
            document = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_float=_reject_json_number,
                parse_constant=_reject_json_number,
                parse_int=_parse_json_integer,
            )
        except ControlRecordError:
            raise
        except (json.JSONDecodeError, RecursionError) as error:
            raise RecordValidationError(
                RecordErrorCode.INVALID_JSON,
                "wire record is not valid JSON",
            ) from error

        if not isinstance(document, Mapping):
            raise RecordValidationError(
                RecordErrorCode.INVALID_TYPE,
                "wire record must be a JSON object",
            )
        required = {
            "digest",
            "kind",
            "payload",
            "record_id",
            "schema",
            "schema_version",
        }
        allowed = required | {"signature"}
        unknown = set(document) - allowed
        if unknown:
            raise RecordValidationError(
                RecordErrorCode.UNKNOWN_FIELD,
                f"unknown top-level record fields: {sorted(unknown)!r}",
            )
        missing = required - set(document)
        if missing:
            raise RecordValidationError(
                RecordErrorCode.MISSING_FIELD,
                f"missing top-level record fields: {sorted(missing)!r}",
            )
        if document["schema"] != SCHEMA_NAME:
            raise RecordValidationError(
                RecordErrorCode.UNSUPPORTED_SCHEMA,
                f"unsupported record schema: {document['schema']!r}",
            )
        if type(document["schema_version"]) is not int or document[
            "schema_version"
        ] != SCHEMA_VERSION:
            raise RecordValidationError(
                RecordErrorCode.UNSUPPORTED_VERSION,
                f"unsupported schema version: {document['schema_version']!r}",
            )
        kind = document["kind"]
        if type(kind) is not str:
            raise RecordValidationError(
                RecordErrorCode.INVALID_TYPE,
                "record kind must be an exact string",
            )
        if kind not in RECORD_KINDS:
            raise RecordValidationError(
                RecordErrorCode.UNSUPPORTED_KIND,
                f"record kind is not registered: {kind!r}",
            )
        supplied_digest = document["digest"]
        if not isinstance(supplied_digest, str) or not _DIGEST_PATTERN.fullmatch(
            supplied_digest
        ):
            raise RecordValidationError(
                RecordErrorCode.INVALID_DIGEST,
                "record digest must be a lowercase sha256 value",
            )
        record = cls._build(
            kind=kind,
            record_id=document["record_id"],
            payload=document["payload"],
            signature=document.get("signature"),
            allow_public_envelope=kind == "public_envelope",
        )
        if not hmac.compare_digest(record.digest(), supplied_digest):
            raise RecordValidationError(
                RecordErrorCode.DIGEST_MISMATCH,
                "record digest does not bind the canonical record core",
            )
        if record.canonical_bytes() != raw:
            raise RecordValidationError(
                RecordErrorCode.NON_CANONICAL_JSON,
                "wire record is valid JSON but not canonical JSON v1",
            )
        return record

    def digest(self) -> str:
        return self._digest

    def public_envelope(
        self,
        *,
        opaque_reference_key: bytes | None = None,
        commitment_key: bytes | None = None,
    ) -> ControlRecord:
        """Project schema-owned metadata with a non-guessable restricted binding."""

        try:
            source = _require_canonical_control_record(
                self,
                field="public envelope source",
            )
        except TypeError as error:
            raise PrivacyEnvelopeError(
                RecordErrorCode.INVALID_TYPE,
                "public envelope source must be an exact ControlRecord",
            ) from error
        except ValueError as error:
            raise PrivacyEnvelopeError(
                RecordErrorCode.DIGEST_MISMATCH,
                "public envelope source does not match its canonical record identity",
            ) from error
        if opaque_reference_key is None and commitment_key is None:
            raise PrivacyEnvelopeError(
                RecordErrorCode.PRIVACY_BINDING_REQUIRED,
                "a public envelope requires an opaque reference or keyed commitment",
            )

        binding: dict[str, str] = {}
        if opaque_reference_key is not None:
            reference_key = _validate_privacy_key(
                opaque_reference_key,
                field="opaque reference key",
                code=RecordErrorCode.INVALID_OPAQUE_REFERENCE_KEY,
            )
            opaque_token = hmac.new(
                reference_key,
                _OPAQUE_REFERENCE_DOMAIN + source._digest.encode("ascii"),
                hashlib.sha256,
            ).digest()
            encoded_token = base64.urlsafe_b64encode(opaque_token).rstrip(b"=")
            binding["opaque_ref"] = (
                "opaque_hmac_sha256:v1:" + encoded_token.decode("ascii")
            )

        if commitment_key is not None:
            validated_commitment_key = _validate_privacy_key(
                commitment_key,
                field="commitment key",
                code=RecordErrorCode.INVALID_COMMITMENT_KEY,
            )
            commitment = hmac.new(
                validated_commitment_key,
                _PUBLIC_COMMITMENT_DOMAIN + source._digest.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            binding["keyed_commitment"] = f"hmac_sha256:{commitment}"

        public: dict[str, bool | str] = {}
        for field in sorted(RECORD_SCHEMAS[source.kind].public_fields):
            if field not in source.payload:
                continue
            value = source.payload[field]
            if not _is_safe_public_value(source.kind, field, value):
                raise PrivacyEnvelopeError(
                    RecordErrorCode.UNSAFE_PUBLIC_VALUE,
                    f"allowlisted public field has an unrecognized value: {field!r}",
                )
            public[field] = value

        envelope_payload = {
            "binding": binding,
            "public": public,
            "source_kind": source.kind,
        }
        return ControlRecord._build(
            kind="public_envelope",
            record_id=_public_envelope_record_id(envelope_payload),
            payload=envelope_payload,
            allow_public_envelope=True,
        )

    def canonical_bytes(self) -> bytes:
        document = {
            "digest": self._digest,
            "kind": self.kind,
            "payload": _plain(self.payload),
            "record_id": self.record_id,
            "schema": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
        }
        if self.signature is not None:
            document["signature"] = _plain(self.signature)
        return _canonical_json(document)


def _require_canonical_control_record(
    value: object,
    *,
    field: str,
    kind: str | None = None,
) -> ControlRecord:
    """Admit one exact, internally consistent base control record."""

    if type(value) is not ControlRecord:
        raise TypeError(f"{field} must be an exact ControlRecord")
    record_kind = object.__getattribute__(value, "kind")
    if type(record_kind) is not str:
        raise TypeError(f"{field}.kind must be an exact string")
    if kind is not None:
        if type(kind) is not str:
            raise TypeError("expected record kind must be an exact string")
        if record_kind != kind:
            raise ValueError(f"{field} must be a canonical {kind} record")
    try:
        rebuilt = ControlRecord._build(
            kind=record_kind,
            record_id=object.__getattribute__(value, "record_id"),
            payload=_plain(object.__getattribute__(value, "payload")),
            signature=_plain(object.__getattribute__(value, "signature")),
            allow_public_envelope=record_kind == "public_envelope",
        )
        stored_digest = object.__getattribute__(value, "_digest")
        integrity_matches = (
            type(stored_digest) is str
            and hmac.compare_digest(stored_digest, rebuilt.digest())
            and value.canonical_bytes() == rebuilt.canonical_bytes()
        )
    except (ControlRecordError, AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{field} fails canonical integrity") from error
    if not integrity_matches:
        raise ValueError(f"{field} fails canonical integrity")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise RecordValidationError(
                RecordErrorCode.DUPLICATE_KEY,
                f"duplicate JSON object key: {key!r}",
            )
        document[key] = value
    return document


def _reject_json_number(value: str) -> Any:
    raise CanonicalizationError(
        RecordErrorCode.UNSUPPORTED_NUMBER,
        f"canonical JSON v1 forbids floating-point number {value!r}",
    )


def _parse_json_integer(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise CanonicalizationError(
            RecordErrorCode.UNSUPPORTED_NUMBER,
            "canonical JSON v1 integers must fit in a signed 64-bit value",
        )
    parsed = int(value)
    if not MIN_CANONICAL_INTEGER <= parsed <= MAX_CANONICAL_INTEGER:
        raise CanonicalizationError(
            RecordErrorCode.UNSUPPORTED_NUMBER,
            "canonical JSON v1 integers must fit in a signed 64-bit value",
        )
    return parsed
