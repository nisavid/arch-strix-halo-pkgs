"""Canonical, non-authoritative promotion assessment at one evidence cut."""

from __future__ import annotations

import hashlib
import weakref
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ._authority import (
    ControlAuthorityError,
    CriticalOperationKind,
    GenerationBindingMode,
    GenerationClass,
    LifecyclePhase,
    NonPromotionalEvidence,
    OperationSubjectKind,
    OperationTarget,
    OperationTargetKind,
    require_promotable,
    validate_operation_coordinates,
)
from ._evaluation import GateImpact
from ._records import (
    ControlRecord,
    _require_canonical_control_record,
    parse_canonical_timestamp,
)


def _record(value: object, *, field: str, kind: str) -> ControlRecord:
    return _require_canonical_control_record(value, field=field, kind=kind)


def _any_record(value: object, *, field: str) -> ControlRecord:
    return _require_canonical_control_record(value, field=field)


def _canonical_graph_key(
    value: object,
    *,
    normalize_lifecycle: bool = False,
) -> object:
    """Return a canonical identity for a fully materialized wrapper graph."""

    if normalize_lifecycle:
        if type(value) is StructuralBaselineCapture:
            return _canonical_lifecycle_root_key(value)
        if type(value) is LifecycleCheckpoint and (
            value.predecessor_checkpoint is None
        ):
            return _canonical_lifecycle_root_key(value)
        if type(value) in (LifecycleCheckpoint, StructuralLifecycleCandidate):
            return _canonical_lifecycle_candidate_key(value)
    if type(value) is ControlRecord:
        record = _any_record(value, field="canonical graph record")
        return ("record", record.kind, record.digest())
    if isinstance(value, ControlRecord):
        raise TypeError("canonical graph record must be an exact ControlRecord")
    if isinstance(value, tuple | list):
        return tuple(
            _canonical_graph_key(
                item,
                normalize_lifecycle=normalize_lifecycle,
            )
            for item in value
        )
    if isinstance(value, dict):
        return tuple(
            (
                key,
                _canonical_graph_key(
                    item,
                    normalize_lifecycle=normalize_lifecycle,
                ),
            )
            for key, item in sorted(value.items())
        )
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__module__,
            type(value).__qualname__,
            tuple(
                (
                    field.name,
                    _canonical_graph_key(
                        getattr(value, field.name),
                        normalize_lifecycle=normalize_lifecycle,
                    ),
                )
                for field in fields(value)
            ),
        )
    return value


def _canonical_graph_equivalent(left: object, right: object) -> bool:
    return _canonical_graph_key(left) == _canonical_graph_key(right)


def _canonical_lifecycle_root_key(
    value: LifecycleCheckpoint | StructuralBaselineCapture,
) -> object:
    if isinstance(value, LifecycleCheckpoint):
        authorization = value.root_authorization_record
        policy = value.root_authorization_policy_record
        actor = value.root_actor_identity_record
        separation = value.root_separation_policy_record
    else:
        authorization = value.capture_approval_record
        policy = value.capture_authorization_record
        actor = value.capture_actor_identity_record
        separation = value.capture_separation_policy_record
    material = (
        value.checkpoint_record,
        value.generation_record,
        value.target_record,
        value.target_protected_state_record,
        authorization,
        policy,
        actor,
        separation,
    )
    return (
        "lifecycle_root",
        tuple(
            _canonical_graph_key(item, normalize_lifecycle=True)
            for item in material
        ),
    )


def _canonical_lifecycle_candidate_key(
    value: LifecycleCheckpoint | StructuralLifecycleCandidate,
) -> object:
    material = (
        value.checkpoint_record,
        value.generation_record,
        value.target_record,
        value.target_protected_state_record,
        value.predecessor_checkpoint,
        value.promotion_contract,
        value.evidence_cut,
        value.acceptance_request_record,
        value.approval_record,
        value.final_service_anchor_receipt,
        value.baseline_restoration_receipt,
        value.service_anchor_receipt,
    )
    return (
        "lifecycle_candidate",
        tuple(
            _canonical_graph_key(item, normalize_lifecycle=True)
            for item in material
        ),
    )


def _canonical_lifecycle_graph_equivalent(
    left: object,
    right: object,
) -> bool:
    return _canonical_graph_key(
        left,
        normalize_lifecycle=True,
    ) == _canonical_graph_key(
        right,
        normalize_lifecycle=True,
    )


def _canonical_graph_contains_once(values: tuple[object, ...], expected: object) -> bool:
    return (
        sum(_canonical_graph_equivalent(value, expected) for value in values) == 1
    )


class PromotionPhase(StrEnum):
    PUBLISHED = "published"
    PREVALIDATED = "prevalidated"
    ACTIVE = "active"
    ACCEPTED = "accepted"


_PREDECESSOR_PHASE = {
    PromotionPhase.PREVALIDATED: PromotionPhase.PUBLISHED,
    PromotionPhase.ACTIVE: PromotionPhase.PREVALIDATED,
    PromotionPhase.ACCEPTED: PromotionPhase.ACTIVE,
}

_PHASE_ESTABLISHING_OPERATION = {
    PromotionPhase.PUBLISHED: CriticalOperationKind.REPOSITORY_PUBLICATION,
    PromotionPhase.PREVALIDATED: CriticalOperationKind.PACKAGE_INSTALLATION,
    PromotionPhase.ACTIVE: CriticalOperationKind.PACKAGE_INSTALLATION,
    PromotionPhase.ACCEPTED: None,
}

_PHASE_TARGET_KIND = {
    PromotionPhase.PUBLISHED: OperationTargetKind.PACKAGE_REPOSITORY,
    PromotionPhase.PREVALIDATED: OperationTargetKind.ISOLATED_ROOT,
    PromotionPhase.ACTIVE: OperationTargetKind.LIVE_ROOT,
}

_SERVICE_BACKEND_CONTINUITY_FIELDS = (
    "backend_id",
    "backend_manifest_digest",
    "configuration_digest",
    "driver_device_digest",
    "model_identity_digest",
    "package_manifest_digest",
)


@dataclass(frozen=True, slots=True)
class PromotionObligation:
    """One canonical assignment/occurrence/impact obligation."""

    obligation_record: ControlRecord

    def __post_init__(self) -> None:
        _record(
            self.obligation_record,
            field="obligation_record",
            kind="promotion_obligation",
        )

    @property
    def obligation_digest(self) -> str:
        return self.obligation_record.digest()

    @property
    def assignment_digest(self) -> str:
        return self.obligation_record.payload["assignment_digest"]

    @property
    def occurrence_digest(self) -> str:
        return self.obligation_record.payload["occurrence_digest"]

    @property
    def impact(self) -> GateImpact:
        return GateImpact(self.obligation_record.payload["impact"])

    @property
    def scenario_operation_obligation_digest(self) -> str | None:
        return self.obligation_record.payload.get(
            "scenario_operation_obligation_digest"
        )


@dataclass(frozen=True, slots=True)
class OperationRequirement:
    """One approved occurrence-free critical-operation template."""

    requirement_record: ControlRecord
    target_record: ControlRecord
    assignment_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        requirement = _record(
            self.requirement_record,
            field="requirement_record",
            kind="operation_requirement",
        ).payload
        target = _record(
            self.target_record,
            field="target_record",
            kind="identity",
        ).payload
        if (
            target["identity_type"] != "target"
            or requirement["target_digest"] != self.target_record.digest()
            or requirement["target_id"] != target["identity_id"]
        ):
            raise ValueError("operation requirement does not bind its exact target")
        assignment_digest = requirement.get("assignment_digest")
        if assignment_digest is None:
            if self.assignment_record is not None:
                raise ValueError(
                    "nongate operation requirement cannot materialize an assignment"
                )
        else:
            assignment = _record(
                self.assignment_record,
                field="assignment_record",
                kind="assignment",
            )
            if assignment.digest() != assignment_digest:
                raise ValueError(
                    "operation requirement does not bind its exact assignment"
                )

    @property
    def requirement_digest(self) -> str:
        return self.requirement_record.digest()

    @property
    def realization_condition(self) -> str:
        return self.requirement_record.payload["realization_condition"]

    @property
    def assignment_digest(self) -> str | None:
        return self.requirement_record.payload.get("assignment_digest")


@dataclass(frozen=True, slots=True)
class OperationObligation:
    """One canonical required critical-operation occurrence."""

    obligation_record: ControlRecord
    requirement: OperationRequirement

    def __post_init__(self) -> None:
        _record(
            self.obligation_record,
            field="obligation_record",
            kind="operation_obligation",
        )
        payload = self.obligation_record.payload
        if not isinstance(self.requirement, OperationRequirement):
            raise TypeError("requirement must be an OperationRequirement")
        if (
            payload["operation_requirement_digest"]
            != self.requirement.requirement_digest
        ):
            raise ValueError(
                "operation obligation does not bind its approved requirement"
            )
        validate_operation_coordinates(
            CriticalOperationKind(payload["operation_kind"]),
            OperationSubjectKind(payload["subject_kind"]),
            OperationTargetKind(payload["target_kind"]),
            GenerationBindingMode(payload["generation_binding"]["mode"]),
            GenerationClass(payload["generation_class"]),
            LifecyclePhase(payload["lifecycle_phase"]),
        )
        if "operation_digest" not in payload:
            raise ValueError("operation obligation requires an exact operation binding")
        requirement = self.requirement.requirement_record.payload
        expected_coordinates = {
            "generation_class": requirement["generation_class"],
            "lifecycle_phase": requirement["lifecycle_phase"],
            "operation_kind": requirement["operation_kind"],
            "subject_kind": requirement["subject_kind"],
            "target_id": requirement["target_id"],
            "target_kind": requirement["target_kind"],
        }
        if any(payload[field] != value for field, value in expected_coordinates.items()):
            raise ValueError(
                "operation obligation does not refine its approved requirement coordinates"
            )
        if (
            payload["generation_binding"]["mode"]
            != requirement["generation_binding_mode"]
        ):
            raise ValueError(
                "operation obligation does not refine its approved generation binding"
            )

    @property
    def obligation_digest(self) -> str:
        return self.obligation_record.digest()

    @property
    def coordinates(self) -> tuple[object, ...]:
        return _operation_coordinates(self.obligation_record.payload)

    @property
    def operation_digest(self) -> str:
        return self.obligation_record.payload["operation_digest"]


@dataclass(frozen=True, slots=True)
class OperationRealization:
    """Exact lifecycle-derived material for one approved operation occurrence."""

    realization_record: ControlRecord
    requirement: OperationRequirement
    obligation: OperationObligation
    operation: RegisteredOperation
    observed_prestate_record: ControlRecord
    resolved_subject_record: ControlRecord | None = None
    resolved_generation_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        realization = _record(
            self.realization_record,
            field="realization_record",
            kind="operation_realization",
        ).payload
        observed_prestate = _record(
            self.observed_prestate_record,
            field="observed_prestate_record",
            kind="protected_state",
        )
        if not isinstance(self.requirement, OperationRequirement):
            raise TypeError("requirement must be an OperationRequirement")
        if not isinstance(self.obligation, OperationObligation):
            raise TypeError("obligation must be an OperationObligation")
        if not isinstance(self.operation, RegisteredOperation):
            raise TypeError("operation must be a RegisteredOperation")
        if (
            self.obligation.requirement.requirement_digest
            != self.requirement.requirement_digest
            or self.obligation.operation_digest != self.operation.operation_digest
        ):
            raise ValueError("operation realization graph is mismatched")
        expected = {
            "observed_prestate_digest": observed_prestate.digest(),
            "operation_digest": self.operation.operation_digest,
            "operation_obligation_digest": self.obligation.obligation_digest,
            "operation_requirement_digest": self.requirement.requirement_digest,
            "resolved_generation_binding": dict(
                self.operation.operation_record.payload["generation_binding"]
            ),
            "resolved_subject_digest": self.operation.operation_record.payload[
                "subject_digest"
            ],
        }
        if any(realization[field] != value for field, value in expected.items()):
            raise ValueError(
                "operation realization does not bind its exact requirement, obligation, operation, and prestate"
            )
        if (
            self.operation.expected_protected_state_record.digest()
            != observed_prestate.digest()
        ):
            raise ValueError(
                "operation realization does not bind the operation's target-specific observed prestate"
            )
        for name, record in (
            ("resolved_subject_record", self.resolved_subject_record),
            ("resolved_generation_record", self.resolved_generation_record),
        ):
            if record is not None:
                _any_record(record, field=name)
        if (
            self.resolved_subject_record is not None
            and self.resolved_subject_record.digest()
            != realization["resolved_subject_digest"]
        ):
            raise ValueError("operation realization resolved subject is mismatched")
        binding_generation = realization["resolved_generation_binding"].get(
            "generation_digest"
        )
        if (
            self.resolved_generation_record is not None
            and self.resolved_generation_record.digest() != binding_generation
        ):
            raise ValueError("operation realization resolved generation is mismatched")

    @property
    def realization_digest(self) -> str:
        return self.realization_record.digest()

    @property
    def resolved_subject_digest(self) -> str:
        return self.realization_record.payload["resolved_subject_digest"]

    @property
    def resolved_generation_binding(self) -> dict[str, object]:
        return dict(
            self.realization_record.payload["resolved_generation_binding"]
        )


_COMPOSITE_PROJECTION_FIELDS = {
    "accepted_generation_digest": "accepted_generation",
    "active_generation_digest": "active_generation",
    "authorization_policy_digest": "authorization_policy",
    "contract_digest": "contract",
    "fallback_digest": "fallback",
    "inventory_digest": "inventory",
    "quorum_policy_digest": "quorum_policy",
    "recovery_policy_digest": "recovery_policy",
    "requirements_digest": "requirements",
    "rollback_generation_digest": "rollback_generation",
    "rollback_registry_digest": "rollback_registry",
    "witness_roster_digest": "witness_roster",
}


@dataclass(frozen=True, slots=True, init=False)
class CompositeAuthorityManifest:
    """Closed structural aggregate for one composite-authority manifest."""

    manifest_record: ControlRecord
    requirements_record: ControlRecord
    contract_record: ControlRecord
    inventory_record: ControlRecord
    accepted_generation_record: ControlRecord
    active_generation_record: ControlRecord
    rollback_generation_record: ControlRecord
    rollback_registry_record: ControlRecord
    selected_rollback_record: ControlRecord
    recovery_policy_record: ControlRecord
    recovery_authorization_record: ControlRecord
    recovery_separation_policy_record: ControlRecord
    recovery_root_identity_record: ControlRecord
    authorization_policy_record: ControlRecord
    fallback_record: ControlRecord
    witness_roster_record: ControlRecord
    quorum_policy_record: ControlRecord
    witness_identity_records: tuple[ControlRecord, ...]

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError(
            "CompositeAuthorityManifest requires exact material through materialize()"
        )

    @classmethod
    def materialize(
        cls,
        *,
        manifest_record: ControlRecord,
        requirements_record: ControlRecord,
        contract_record: ControlRecord,
        inventory_record: ControlRecord,
        accepted_generation_record: ControlRecord,
        active_generation_record: ControlRecord,
        rollback_generation_record: ControlRecord,
        rollback_registry_record: ControlRecord,
        selected_rollback_record: ControlRecord,
        recovery_policy_record: ControlRecord,
        recovery_authorization_record: ControlRecord,
        recovery_separation_policy_record: ControlRecord,
        recovery_root_identity_record: ControlRecord,
        authorization_policy_record: ControlRecord,
        fallback_record: ControlRecord,
        witness_roster_record: ControlRecord,
        quorum_policy_record: ControlRecord,
        witness_identity_records: tuple[ControlRecord, ...],
    ) -> CompositeAuthorityManifest:
        if cls is not CompositeAuthorityManifest:
            raise TypeError(
                "materialize requires the exact CompositeAuthorityManifest class"
            )
        manifest = object.__new__(CompositeAuthorityManifest)
        values = locals()
        for field in fields(CompositeAuthorityManifest):
            object.__setattr__(manifest, field.name, values[field.name])
        CompositeAuthorityManifest.__post_init__(manifest)
        return manifest

    def __post_init__(self) -> None:
        payload = _record(
            self.manifest_record,
            field="manifest_record",
            kind="composite_authority",
        ).payload
        _record(
            self.requirements_record,
            field="requirements_record",
            kind="requirements",
        )
        contract = _record(
            self.contract_record,
            field="contract_record",
            kind="validation_contract",
        )
        inventory = _record(
            self.inventory_record,
            field="inventory_record",
            kind="installed_inventory",
        )
        rollback_registry = _record(
            self.rollback_registry_record,
            field="rollback_registry_record",
            kind="rollback_registry",
        )
        selected_rollback = _record(
            self.selected_rollback_record,
            field="selected_rollback_record",
            kind="rollback",
        )
        recovery_policy = _record(
            self.recovery_policy_record,
            field="recovery_policy_record",
            kind="recovery_policy",
        )
        recovery_authorization = _record(
            self.recovery_authorization_record,
            field="recovery_authorization_record",
            kind="authorization",
        )
        recovery_separation = _record(
            self.recovery_separation_policy_record,
            field="recovery_separation_policy_record",
            kind="separation_policy",
        )
        recovery_root = _record(
            self.recovery_root_identity_record,
            field="recovery_root_identity_record",
            kind="identity",
        )
        fallback = _any_record(
            self.fallback_record,
            field="fallback_record",
        )
        if fallback.kind not in {
            "composite_authority",
            "composite_fallback_reference",
        }:
            raise ValueError(
                "fallback_record must be a canonical composite authority reference"
            )
        for name in (
            "accepted_generation_record",
            "active_generation_record",
            "rollback_generation_record",
        ):
            _record(getattr(self, name), field=name, kind="generation")
        authorization = _record(
            self.authorization_policy_record,
            field="authorization_policy_record",
            kind="authorization",
        )
        roster = _record(
            self.witness_roster_record,
            field="witness_roster_record",
            kind="witness_roster",
        )
        policy = _record(
            self.quorum_policy_record,
            field="quorum_policy_record",
            kind="quorum_policy",
        )
        expected = {
            "accepted_generation_digest": self.accepted_generation_record.digest(),
            "active_generation_digest": self.active_generation_record.digest(),
            "authorization_policy_digest": authorization.digest(),
            "contract_digest": self.contract_record.digest(),
            "fallback_digest": fallback.digest(),
            "inventory_digest": self.inventory_record.digest(),
            "quorum_policy_digest": policy.digest(),
            "recovery_policy_digest": self.recovery_policy_record.digest(),
            "requirements_digest": self.requirements_record.digest(),
            "rollback_generation_digest": self.rollback_generation_record.digest(),
            "rollback_registry_digest": self.rollback_registry_record.digest(),
            "witness_roster_digest": roster.digest(),
        }
        if any(payload[field] != digest for field, digest in expected.items()):
            raise ValueError(
                "composite authority manifest does not bind its exact material"
            )
        selected_rollback_digest = selected_rollback.digest()
        if (
            selected_rollback_digest
            != rollback_registry.payload["selected_rollback_digest"]
            or selected_rollback_digest
            not in tuple(rollback_registry.payload["rollback_digests"])
        ):
            raise ValueError(
                "composite authority selected rollback is not the exact selected registry member"
            )
        rollback_generation_digest = self.rollback_generation_record.digest()
        if (
            selected_rollback.payload["destination_generation_digest"]
            != rollback_generation_digest
            or selected_rollback.payload["target_generation_digest"]
            != rollback_generation_digest
        ):
            raise ValueError(
                "composite authority selected rollback does not target its exact rollback generation"
            )
        active_generation_digest = self.active_generation_record.digest()
        if (
            active_generation_digest != rollback_generation_digest
            and selected_rollback.payload["origin_generation_digest"]
            != active_generation_digest
        ):
            raise ValueError(
                "composite authority divergent rollback does not originate from its exact active generation"
            )
        if (
            contract.payload["requirements_digest"]
            != self.requirements_record.digest()
            or contract.payload["authorization_policy_digest"]
            != authorization.digest()
            or inventory.payload["generation_digest"]
            != self.active_generation_record.digest()
            or inventory.payload["authorization_digest"] != authorization.digest()
            or rollback_registry.payload["authorization_digest"]
            != authorization.digest()
            or recovery_policy.payload["authorization_digest"]
            != recovery_authorization.digest()
            or recovery_policy.payload["separation_policy_digest"]
            != recovery_separation.digest()
            or recovery_policy.payload["recovery_root_digest"]
            != recovery_root.digest()
            or recovery_authorization.payload["separation_policy_digest"]
            != recovery_separation.digest()
            or recovery_authorization.payload["recovery_root_digest"]
            != recovery_root.digest()
            or not _authorization_admits_identity(
                recovery_authorization,
                recovery_separation,
                recovery_root,
                action="reinstate_composite_authority",
                subject_kind="composite_change_set",
            )
            or (
                fallback.kind == "composite_fallback_reference"
                and fallback.payload["authorization_digest"]
                != authorization.digest()
            )
        ):
            raise ValueError(
                "composite authority typed projections do not bind their exact manifest authority and generation"
            )
        _validate_composite_manifest_generation_pointers(self)
        identities = tuple(self.witness_identity_records)
        object.__setattr__(self, "witness_identity_records", identities)
        for identity in identities:
            _record(
                identity,
                field="witness_identity_records item",
                kind="identity",
            )
            if identity.payload["identity_type"] not in {"principal", "validator"}:
                raise ValueError("composite witnesses must be actor identities")
        identity_digests = tuple(identity.digest() for identity in identities)
        if (
            identity_digests != tuple(roster.payload["witness_identity_digests"])
            or policy.payload["witness_roster_digest"] != roster.digest()
            or policy.payload["threshold"] > len(identities)
        ):
            raise ValueError(
                "composite authority quorum policy does not bind its exact witness roster"
            )

    @property
    def manifest_digest(self) -> str:
        return self.manifest_record.digest()

    @property
    def promotional(self) -> bool:
        return False


def _composite_projection_diff(
    old: CompositeAuthorityManifest,
    candidate: CompositeAuthorityManifest,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            projection
            for field, projection in _COMPOSITE_PROJECTION_FIELDS.items()
            if old.manifest_record.payload[field]
            != candidate.manifest_record.payload[field]
        )
    )


def _validate_composite_manifest_generation_pointers(
    manifest: CompositeAuthorityManifest,
) -> None:
    pointers = {
        "accepted": manifest.accepted_generation_record.digest(),
        "active": manifest.active_generation_record.digest(),
        "rollback": manifest.rollback_generation_record.digest(),
    }
    if any(
        record.payload["generation_class"] != GenerationClass.C.value
        for record in (
            manifest.accepted_generation_record,
            manifest.active_generation_record,
            manifest.rollback_generation_record,
        )
    ):
        raise ValueError("composite authority pointers require exact C generations")
    if (
        pointers["active"] != pointers["accepted"]
        and pointers["rollback"] != pointers["accepted"]
    ):
        raise ValueError("composite authority generation pointers are inconsistent")


def _expected_composite_generation_binding(
    old: CompositeAuthorityManifest,
    candidate: CompositeAuthorityManifest,
    *,
    transition_mode: str,
) -> dict[str, object]:
    old_pointers = {
        "accepted": old.accepted_generation_record.digest(),
        "active": old.active_generation_record.digest(),
        "rollback": old.rollback_generation_record.digest(),
    }
    candidate_pointers = {
        "accepted": candidate.accepted_generation_record.digest(),
        "active": candidate.active_generation_record.digest(),
        "rollback": candidate.rollback_generation_record.digest(),
    }
    _validate_composite_manifest_generation_pointers(old)
    _validate_composite_manifest_generation_pointers(candidate)

    if transition_mode == "control_update":
        if candidate_pointers != old_pointers:
            raise ValueError("composite control update cannot change generation pointers")
        return {"mode": GenerationBindingMode.NO_GENERATION.value}
    if transition_mode == "activation":
        if not (
            old_pointers["active"] == old_pointers["accepted"]
            and candidate_pointers["active"] != old_pointers["active"]
            and candidate_pointers["accepted"] == old_pointers["accepted"]
            and candidate_pointers["rollback"] == old_pointers["accepted"]
        ):
            raise ValueError(
                "composite activation must preserve accepted, activate one new C generation, and reset rollback to the prior accepted generation"
            )
        return {
            "generation_digest": candidate_pointers["active"],
            "mode": GenerationBindingMode.REQUIRED_GENERATION.value,
        }
    if transition_mode == "acceptance":
        if not (
            old_pointers["active"] != old_pointers["accepted"]
            and candidate_pointers["active"] == old_pointers["active"]
            and candidate_pointers["accepted"] == old_pointers["active"]
            and candidate_pointers["rollback"] == old_pointers["rollback"]
        ):
            raise ValueError(
                "composite acceptance must accept the exact active C generation without changing active or rollback"
            )
        return {
            "generation_digest": candidate_pointers["accepted"],
            "mode": GenerationBindingMode.REQUIRED_GENERATION.value,
        }
    raise ValueError(
        "CompositeChangeSet requires a control-update, activation, or acceptance transition"
    )


@dataclass(frozen=True, slots=True)
class CompositeChangeSet:
    """One exact, quorum-approved, nonpromotional composite transition."""

    change_set_record: ControlRecord
    old_manifest: CompositeAuthorityManifest
    candidate_manifest: CompositeAuthorityManifest
    rollback_manifest: CompositeAuthorityManifest
    authorization_record: ControlRecord
    separation_policy_record: ControlRecord
    coordinator_identity_record: ControlRecord
    quorum_receipt_records: tuple[ControlRecord, ...]
    approval_records: tuple[ControlRecord, ...]

    def __post_init__(self) -> None:
        change_set = _record(
            self.change_set_record,
            field="change_set_record",
            kind="composite_change_set",
        ).payload
        for name in ("old_manifest", "candidate_manifest", "rollback_manifest"):
            if type(getattr(self, name)) is not CompositeAuthorityManifest:
                raise TypeError(
                    f"{name} must be an exact CompositeAuthorityManifest"
                )
        transition_mode = change_set["transition_mode"]
        if transition_mode not in {"control_update", "activation", "acceptance"}:
            raise ValueError(
                "CompositeChangeSet requires a control-update, activation, or acceptance transition"
            )
        expected_manifest_digests = {
            "candidate_manifest_digest": self.candidate_manifest.manifest_digest,
            "old_manifest_digest": self.old_manifest.manifest_digest,
            "rollback_manifest_digest": self.rollback_manifest.manifest_digest,
        }
        if any(
            change_set[field] != digest
            for field, digest in expected_manifest_digests.items()
        ) or not _canonical_graph_equivalent(
            self.rollback_manifest,
            self.old_manifest,
        ):
            raise ValueError(
                "composite transition does not bind its exact old, candidate, and rollback manifests"
            )
        if not _canonical_graph_equivalent(
            self.candidate_manifest.fallback_record,
            self.old_manifest.manifest_record,
        ):
            raise ValueError(
                "composite candidate fallback is not the exact old whole manifest"
            )
        changed_fields = _composite_projection_diff(
            self.old_manifest,
            self.candidate_manifest,
        )
        expected_binding = _expected_composite_generation_binding(
            self.old_manifest,
            self.candidate_manifest,
            transition_mode=transition_mode,
        )
        expected_quorum_mode = (
            "joint_consensus"
            if {"quorum_policy", "recovery_policy", "witness_roster"}
            & set(changed_fields)
            else "existing"
        )
        if (
            tuple(change_set["changed_fields"]) != changed_fields
            or dict(change_set["generation_binding"]) != expected_binding
            or change_set.get("authorization_action")
            != "transition_composite_authority"
            or change_set["quorum_mode"] != expected_quorum_mode
            or change_set["terminal_rule"] != "conjunctive"
        ):
            raise ValueError(
                "composite transition does not carry its derived diff, generation binding, quorum, and terminal rule"
            )

        authorization = _record(
            self.authorization_record,
            field="authorization_record",
            kind="authorization",
        )
        separation = _record(
            self.separation_policy_record,
            field="separation_policy_record",
            kind="separation_policy",
        )
        coordinator = _record(
            self.coordinator_identity_record,
            field="coordinator_identity_record",
            kind="identity",
        )
        if (
            change_set["authorization_digest"] != authorization.digest()
            or not _canonical_graph_equivalent(
                authorization,
                self.old_manifest.authorization_policy_record,
            )
            or change_set["coordinator_identity_digest"] != coordinator.digest()
            or not _authorization_admits_identity(
                authorization,
                separation,
                coordinator,
                action="transition_composite_authority",
                subject_kind="composite_change_set",
            )
        ):
            raise ValueError(
                "composite transition is not authorized by its exact old policy and coordinator"
            )
        self._validate_quorum(
            expected_quorum_mode=expected_quorum_mode,
            witness_roster_changed="witness_roster" in changed_fields,
        )

    def _validate_quorum(
        self,
        *,
        expected_quorum_mode: str,
        witness_roster_changed: bool,
    ) -> None:
        receipts = tuple(self.quorum_receipt_records)
        approvals = tuple(self.approval_records)
        object.__setattr__(self, "quorum_receipt_records", receipts)
        object.__setattr__(self, "approval_records", approvals)
        for receipt in receipts:
            _record(
                receipt,
                field="quorum_receipt_records item",
                kind="quorum_receipt",
            )
        for approval in approvals:
            _record(
                approval,
                field="approval_records item",
                kind="approval",
            )
        receipt_digests = tuple(receipt.digest() for receipt in receipts)
        approval_digests = tuple(approval.digest() for approval in approvals)
        if (
            len(receipt_digests) != len(set(receipt_digests))
            or len(approval_digests) != len(set(approval_digests))
        ):
            raise ValueError("composite quorum material contains duplicate records")
        expected_sides = (
            {"existing"}
            if expected_quorum_mode == "existing"
            else {"candidate", "existing"}
        )
        side_by_name = {receipt.payload["side"]: receipt for receipt in receipts}
        if len(side_by_name) != len(receipts) or set(side_by_name) != expected_sides:
            raise ValueError(
                "composite quorum does not contain its exact required side receipts"
            )
        approval_by_digest = {approval.digest(): approval for approval in approvals}
        referenced_approvals: set[str] = set()
        approved_identities_by_side: dict[str, set[str]] = {}
        for side, receipt_record in side_by_name.items():
            manifest = (
                self.old_manifest if side == "existing" else self.candidate_manifest
            )
            receipt = receipt_record.payload
            expected = {
                "authorization_digest": self.authorization_record.digest(),
                "change_set_digest": self.change_set_record.digest(),
                "quorum_policy_digest": manifest.quorum_policy_record.digest(),
                "witness_roster_digest": manifest.witness_roster_record.digest(),
            }
            if any(receipt[field] != digest for field, digest in expected.items()):
                raise ValueError(
                    "composite quorum receipt does not bind its exact side material"
                )
            side_approval_digests = tuple(receipt["approval_digests"])
            if any(
                digest not in approval_by_digest
                for digest in side_approval_digests
            ):
                raise ValueError(
                    "composite quorum receipt references an unmaterialized approval"
                )
            referenced_approvals.update(side_approval_digests)
            identity_by_digest = {
                identity.digest(): identity
                for identity in manifest.witness_identity_records
            }
            approved_identities: set[str] = set()
            for approval_digest in side_approval_digests:
                approval_record = approval_by_digest[approval_digest]
                approval = approval_record.payload
                actor = identity_by_digest.get(approval["actor_identity_digest"])
                if (
                    actor is None
                    or approval["action"] != "transition_composite_authority"
                    or approval["decision"] != "approved"
                    or approval["subject_digest"] != self.change_set_record.digest()
                    or approval["authorization_digest"]
                    != self.authorization_record.digest()
                    or not _authorization_admits_actor(
                        self.authorization_record,
                        self.separation_policy_record,
                        actor,
                        actor_identity_digest=approval["actor_identity_digest"],
                        actor_role=approval["actor_role"],
                        action="transition_composite_authority",
                        subject_kind="composite_change_set",
                        require_approver_role=True,
                    )
                    or parse_canonical_timestamp(approval["decided_at"])
                    > parse_canonical_timestamp(receipt["approved_at"])
                ):
                    raise ValueError(
                        "composite quorum contains an unauthorized witness approval"
                    )
                approved_identities.add(actor.digest())
            if len(approved_identities) < manifest.quorum_policy_record.payload[
                "threshold"
            ]:
                raise ValueError("composite quorum does not meet its side threshold")
            approved_identities_by_side[side] = approved_identities
        if referenced_approvals != set(approval_by_digest):
            raise ValueError("composite quorum contains unreferenced approvals")
        if witness_roster_changed:
            old_witnesses = set(
                self.old_manifest.witness_roster_record.payload[
                    "witness_identity_digests"
                ]
            )
            candidate_witnesses = set(
                self.candidate_manifest.witness_roster_record.payload[
                    "witness_identity_digests"
                ]
            )
            overlap = old_witnesses & candidate_witnesses
            approved_overlap = (
                approved_identities_by_side["existing"]
                & approved_identities_by_side["candidate"]
            )
            if not overlap or not overlap & approved_overlap:
                raise ValueError(
                    "joint witness transition lacks an overlapping witness approved on both sides"
                )

    @property
    def change_set_digest(self) -> str:
        return self.change_set_record.digest()

    @property
    def promotional(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class CompositeAuthorityCheckpoint:
    """Signed structural receipt for one exact committed composite manifest."""

    checkpoint_record: ControlRecord
    change_set: CompositeChangeSet
    manifest: CompositeAuthorityManifest
    register_observation_record: ControlRecord
    quorum_receipt_records: tuple[ControlRecord, ...]
    signer_identity_record: ControlRecord
    authorization_record: ControlRecord

    def __post_init__(self) -> None:
        checkpoint_record = _record(
            self.checkpoint_record,
            field="checkpoint_record",
            kind="composite_authority_checkpoint",
        )
        checkpoint = checkpoint_record.payload
        if type(self.change_set) is not CompositeChangeSet:
            raise TypeError("change_set must be an exact CompositeChangeSet")
        if type(self.manifest) is not CompositeAuthorityManifest:
            raise TypeError("manifest must be an exact CompositeAuthorityManifest")
        register_record = _record(
            self.register_observation_record,
            field="register_observation_record",
            kind="authority_register",
        )
        register = register_record.payload
        signer = _record(
            self.signer_identity_record,
            field="signer_identity_record",
            kind="identity",
        )
        authorization = _record(
            self.authorization_record,
            field="authorization_record",
            kind="authorization",
        )
        receipts = tuple(self.quorum_receipt_records)
        object.__setattr__(self, "quorum_receipt_records", receipts)
        for receipt in receipts:
            _record(
                receipt,
                field="quorum_receipt_records item",
                kind="quorum_receipt",
            )
        receipt_digests = tuple(receipt.digest() for receipt in receipts)
        change_set_receipt_digests = tuple(
            receipt.digest() for receipt in self.change_set.quorum_receipt_records
        )
        receipt_times = tuple(
            parse_canonical_timestamp(receipt.payload["approved_at"])
            for receipt in receipts
        )
        register_at = parse_canonical_timestamp(register["observed_at"])
        committed_at = parse_canonical_timestamp(checkpoint["committed_at"])
        signature = checkpoint_record.signature
        if (
            not receipts
            or len(receipt_digests) != len(set(receipt_digests))
            or not _canonical_graph_equivalent(
                self.change_set.candidate_manifest,
                self.manifest,
            )
            or checkpoint["change_set_digest"]
            != self.change_set.change_set_digest
            or receipt_digests != change_set_receipt_digests
            or register["status"] != "valid"
            or register["selected_manifest_digest"] != self.manifest.manifest_digest
            or tuple(register["quorum_receipt_digests"]) != receipt_digests
            or register["witness_roster_digest"]
            != self.manifest.witness_roster_record.digest()
            or checkpoint["selected_manifest_digest"]
            != self.manifest.manifest_digest
            or checkpoint["register_observation_digest"] != register_record.digest()
            or checkpoint["register_id"] != register["register_id"]
            or checkpoint["register_sequence"] != register["sequence"]
            or checkpoint["register_head_digest"] != register["register_head_digest"]
            or tuple(checkpoint["quorum_receipt_digests"]) != receipt_digests
            or checkpoint["signer_identity_digest"] != signer.digest()
            or checkpoint["authorization_digest"] != authorization.digest()
            or not _canonical_graph_equivalent(
                authorization,
                self.change_set.authorization_record,
            )
            or signer.digest()
            != self.change_set.coordinator_identity_record.digest()
            or signer.payload["identity_type"] not in {"principal", "validator"}
            or signature is None
            or signature["signed_digest"] != checkpoint_record.digest()
            or signature["signer_identity_digest"] != signer.digest()
            or max(receipt_times) > register_at
            or register_at > committed_at
        ):
            raise ValueError(
                "composite authority checkpoint does not bind one exact committed manifest graph"
            )

    @property
    def checkpoint_digest(self) -> str:
        return self.checkpoint_record.digest()

    @property
    def promotional(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class CompositeRegisterReinstatement:
    """Structural recovery-root selection of one exact prior whole manifest."""

    change_set_record: ControlRecord
    register_observation_record: ControlRecord
    prior_committed_checkpoint: CompositeAuthorityCheckpoint
    authorization_record: ControlRecord
    separation_policy_record: ControlRecord
    coordinator_identity_record: ControlRecord

    def __post_init__(self) -> None:
        change_set = _record(
            self.change_set_record,
            field="change_set_record",
            kind="composite_change_set",
        ).payload
        register = _record(
            self.register_observation_record,
            field="register_observation_record",
            kind="authority_register",
        ).payload
        if type(self.prior_committed_checkpoint) is not CompositeAuthorityCheckpoint:
            raise TypeError(
                "prior_committed_checkpoint must be an exact CompositeAuthorityCheckpoint"
            )
        prior_manifest = self.prior_committed_checkpoint.manifest
        authorization = _record(
            self.authorization_record,
            field="authorization_record",
            kind="authorization",
        )
        separation = _record(
            self.separation_policy_record,
            field="separation_policy_record",
            kind="separation_policy",
        )
        coordinator = _record(
            self.coordinator_identity_record,
            field="coordinator_identity_record",
            kind="identity",
        )
        prior = prior_manifest.manifest_digest
        if (
            change_set["transition_mode"] != "register_reinstatement"
            or change_set["old_manifest_digest"] != prior
            or change_set["candidate_manifest_digest"] != prior
            or change_set["rollback_manifest_digest"] != prior
            or tuple(change_set["changed_fields"])
            or dict(change_set["generation_binding"])
            != {"mode": GenerationBindingMode.NO_GENERATION.value}
            or change_set["quorum_mode"] != "recovery_root"
            or change_set["terminal_rule"] != "conjunctive"
            or change_set["authorization_action"]
            != "reinstate_composite_authority"
            or change_set["prior_committed_checkpoint_digest"]
            != self.prior_committed_checkpoint.checkpoint_digest
            or change_set[
                "current_authority_register_observation_digest"
            ]
            != self.register_observation_record.digest()
            or register["status"] not in {"absent", "corrupt"}
            or register["register_id"]
            != self.prior_committed_checkpoint.register_observation_record.payload[
                "register_id"
            ]
            or parse_canonical_timestamp(register["observed_at"])
            < parse_canonical_timestamp(
                self.prior_committed_checkpoint.checkpoint_record.payload[
                    "committed_at"
                ]
            )
            or register["witness_roster_digest"]
            != prior_manifest.witness_roster_record.digest()
        ):
            raise ValueError(
                "register reinstatement does not preserve the exact prior whole manifest"
            )
        if (
            change_set["authorization_digest"] != authorization.digest()
            or not _canonical_graph_equivalent(
                authorization,
                prior_manifest.recovery_authorization_record,
            )
            or not _canonical_graph_equivalent(
                separation,
                prior_manifest.recovery_separation_policy_record,
            )
            or not _canonical_graph_equivalent(
                coordinator,
                prior_manifest.recovery_root_identity_record,
            )
            or change_set["coordinator_identity_digest"] != coordinator.digest()
            or authorization.payload["recovery_root_digest"] != coordinator.digest()
            or authorization.payload["action"] != "reinstate_composite_authority"
            or authorization.payload["subject_kind"] != "composite_change_set"
            or not _authorization_admits_identity(
                authorization,
                separation,
                coordinator,
                action="reinstate_composite_authority",
                subject_kind="composite_change_set",
            )
        ):
            raise ValueError(
                "register reinstatement is not authorized by the exact recovery root"
            )

    @property
    def promotional(self) -> bool:
        return False


def _operation_coordinates(payload: object) -> tuple[object, ...]:
    if not hasattr(payload, "__getitem__"):
        raise TypeError("operation payload must be a mapping")
    binding = payload["generation_binding"]
    return (
        payload["intent_digest"],
        payload["subject_kind"],
        payload["subject_digest"],
        payload["operation_kind"],
        binding["mode"],
        binding.get("generation_digest"),
        binding.get("sentinel_digest"),
        payload["generation_class"],
        payload["lifecycle_phase"],
        payload["target_kind"],
        payload["target_id"],
    )


@dataclass(frozen=True, slots=True)
class PromotionContract:
    """Canonical C-generation requirements and total promotion obligations."""

    requirements_record: ControlRecord
    assignment_set_record: ControlRecord
    operation_requirement_set_record: ControlRecord
    operation_obligation_set_record: ControlRecord
    operation_realization_set_record: ControlRecord
    validation_contract_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    contract_record: ControlRecord
    obligations: tuple[PromotionObligation, ...]
    operation_requirements: tuple[OperationRequirement, ...]
    operation_obligations: tuple[OperationObligation, ...]
    operation_realizations: tuple[OperationRealization, ...]
    assignment_records: tuple[ControlRecord, ...]
    predecessor_checkpoint: (
        LifecycleCheckpoint
        | StructuralBaselineCapture
        | StructuralLifecycleCandidate
    )
    acceptance_authorization_record: ControlRecord | None = None
    acceptance_separation_policy_record: ControlRecord | None = None
    acceptance_actor_identity_record: ControlRecord | None = None
    baseline_restoration_receipt: BaselineRestorationReceipt | None = None
    service_anchor_receipt: ServiceAnchorReceipt | None = None

    def __post_init__(self) -> None:
        _record(self.requirements_record, field="requirements_record", kind="requirements")
        _record(
            self.assignment_set_record,
            field="assignment_set_record",
            kind="assignment_set",
        )
        _record(
            self.operation_requirement_set_record,
            field="operation_requirement_set_record",
            kind="operation_requirement_set",
        )
        _record(
            self.operation_obligation_set_record,
            field="operation_obligation_set_record",
            kind="operation_obligation_set",
        )
        _record(
            self.operation_realization_set_record,
            field="operation_realization_set_record",
            kind="operation_realization_set",
        )
        _record(
            self.validation_contract_record,
            field="validation_contract_record",
            kind="validation_contract",
        )
        _record(self.generation_record, field="generation_record", kind="generation")
        if self.generation_record.payload["generation_class"] != "c":
            raise ValueError("promotion contract requires a C generation")
        _record(self.target_record, field="target_record", kind="identity")
        _record(
            self.target_protected_state_record,
            field="target_protected_state_record",
            kind="protected_state",
        )
        _record(
            self.contract_record,
            field="contract_record",
            kind="promotion_contract",
        )
        if self.target_record.payload["identity_type"] != "target":
            raise ValueError("target_record must identify a target")
        assignment_records = tuple(self.assignment_records)
        object.__setattr__(self, "assignment_records", assignment_records)
        for assignment_record in assignment_records:
            _record(
                assignment_record,
                field="assignment_records item",
                kind="assignment",
            )
        obligations = tuple(self.obligations)
        object.__setattr__(self, "obligations", obligations)
        if not obligations or any(
            not isinstance(item, PromotionObligation) for item in obligations
        ):
            raise ValueError("obligations must contain PromotionObligation values")
        obligation_digests = tuple(item.obligation_digest for item in obligations)
        if len(obligation_digests) != len(set(obligation_digests)):
            raise ValueError("contract contains duplicate obligations")
        operation_requirements = tuple(self.operation_requirements)
        object.__setattr__(self, "operation_requirements", operation_requirements)
        if any(
            not isinstance(item, OperationRequirement)
            for item in operation_requirements
        ):
            raise ValueError(
                "operation_requirements must contain OperationRequirement values"
            )
        operation_requirement_digests = tuple(
            item.requirement_digest for item in operation_requirements
        )
        operation_requirement_ids = tuple(
            item.requirement_record.payload["requirement_id"]
            for item in operation_requirements
        )
        if len(operation_requirement_digests) != len(
            set(operation_requirement_digests)
        ) or len(operation_requirement_ids) != len(set(operation_requirement_ids)):
            raise ValueError("contract contains duplicate operation requirements")
        operation_obligations = tuple(self.operation_obligations)
        object.__setattr__(self, "operation_obligations", operation_obligations)
        if any(
            not isinstance(item, OperationObligation)
            for item in operation_obligations
        ):
            raise ValueError(
                "operation_obligations must contain OperationObligation values"
            )
        operation_obligation_digests = tuple(
            item.obligation_digest for item in operation_obligations
        )
        operation_obligation_ids = tuple(
            item.obligation_record.payload["obligation_id"]
            for item in operation_obligations
        )
        if len(operation_obligation_digests) != len(
            set(operation_obligation_digests)
        ) or len(operation_obligation_ids) != len(set(operation_obligation_ids)):
            raise ValueError("contract contains duplicate operation obligations")
        operation_realizations = tuple(self.operation_realizations)
        object.__setattr__(self, "operation_realizations", operation_realizations)
        if any(
            not isinstance(item, OperationRealization)
            for item in operation_realizations
        ):
            raise ValueError(
                "operation_realizations must contain OperationRealization values"
            )
        operation_realization_digests = tuple(
            item.realization_digest for item in operation_realizations
        )
        if len(operation_realization_digests) != len(
            set(operation_realization_digests)
        ):
            raise ValueError("contract contains duplicate operation realizations")
        if not _is_promotion_predecessor(self.predecessor_checkpoint):
            raise TypeError(
                "predecessor_checkpoint must be explicit structural or authority-issued lifecycle material"
            )

        payload = self.contract_record.payload
        validation_contract = self.validation_contract_record.payload
        if (
            validation_contract["requirements_digest"]
            != self.requirements_record.digest()
        ):
            raise ValueError("validation contract does not bind requirements")
        if (
            self.assignment_set_record.payload["requirements_digest"]
            != self.requirements_record.digest()
            or validation_contract["assignments_digest"]
            != self.assignment_set_record.digest()
        ):
            raise ValueError("validation contract does not bind canonical assignments")
        if (
            self.operation_requirement_set_record.payload["requirements_digest"]
            != self.requirements_record.digest()
            or validation_contract["operation_requirement_set_digest"]
            != self.operation_requirement_set_record.digest()
            or tuple(
                self.operation_requirement_set_record.payload[
                    "operation_requirement_digests"
                ]
            )
            != operation_requirement_digests
        ):
            raise ValueError(
                "validation contract does not bind canonical operation requirements"
            )
        if (
            self.operation_obligation_set_record.payload["requirements_digest"]
            != self.requirements_record.digest()
            or self.operation_obligation_set_record.payload[
                "operation_requirement_set_digest"
            ]
            != self.operation_requirement_set_record.digest()
        ):
            raise ValueError(
                "promotion contract does not bind canonical operation realizations"
            )
        assignment_digests = tuple(
            self.assignment_set_record.payload["assignment_digests"]
        )
        if tuple(item.digest() for item in assignment_records) != assignment_digests:
            raise ValueError("promotion contract does not materialize exact assignments")
        obligation_assignment_digests = tuple(
            item.assignment_digest for item in obligations
        )
        if (
            len(obligation_assignment_digests)
            != len(set(obligation_assignment_digests))
            or set(obligation_assignment_digests) != set(assignment_digests)
        ):
            raise ValueError(
                "promotion obligations do not cover the canonical assignment set exactly"
            )
        if tuple(
            self.operation_obligation_set_record.payload["obligation_digests"]
        ) != operation_obligation_digests:
            raise ValueError(
                "operation obligation set does not bind exact operation obligations"
            )
        if (
            self.operation_realization_set_record.payload[
                "operation_obligation_set_digest"
            ]
            != self.operation_obligation_set_record.digest()
            or tuple(
                self.operation_realization_set_record.payload[
                    "operation_realization_digests"
                ]
            )
            != operation_realization_digests
            or payload["operation_realization_set_digest"]
            != self.operation_realization_set_record.digest()
        ):
            raise ValueError(
                "promotion contract does not bind exact operation realizations"
            )
        requirement_by_digest = {
            item.requirement_digest: item for item in operation_requirements
        }
        obligations_by_requirement: dict[str, list[OperationObligation]] = {
            digest: [] for digest in requirement_by_digest
        }
        for operation_obligation in operation_obligations:
            requirement_digest = operation_obligation.requirement.requirement_digest
            if (
                requirement_by_digest.get(requirement_digest) is None
            ):
                raise ValueError(
                    "operation obligation references an unapproved requirement"
                )
            obligations_by_requirement[requirement_digest].append(
                operation_obligation
            )
        realization_by_obligation: dict[str, OperationRealization] = {}
        operation_obligation_digest_set = set(operation_obligation_digests)
        for realization in operation_realizations:
            obligation_digest = realization.obligation.obligation_digest
            if (
                obligation_digest in realization_by_obligation
                or obligation_digest not in operation_obligation_digest_set
            ):
                raise ValueError(
                    "operation realization does not cover exact approved obligations once"
                )
            realization_by_obligation[obligation_digest] = realization
        if set(realization_by_obligation) != set(operation_obligation_digests):
            raise ValueError(
                "operation realizations do not cover exact approved obligations once"
            )
        for requirement in operation_requirements:
            realizations = obligations_by_requirement[requirement.requirement_digest]
            if len(realizations) > 1:
                raise ValueError(
                    "operation requirement has duplicate exact realizations"
                )
            assignment = requirement.assignment_record
            unconditionally_applicable = (
                assignment is not None
                and assignment.payload["applicability"] == "unconditional"
            )
            if (
                requirement.realization_condition == "always"
                or unconditionally_applicable
            ) and len(realizations) != 1:
                raise ValueError(
                    "required operation template lacks its exact realization"
                )
        operation_obligation_by_digest = {
            item.obligation_digest: item for item in operation_obligations
        }
        assignment_by_digest = {
            item.digest(): item for item in assignment_records
        }
        linked_scenario_digests = [
            item.scenario_operation_obligation_digest
            for item in obligations
            if item.scenario_operation_obligation_digest is not None
        ]
        if len(linked_scenario_digests) != len(set(linked_scenario_digests)):
            raise ValueError(
                "scenario gates must link distinct critical-operation obligations"
            )
        for obligation in obligations:
            linked_digest = obligation.scenario_operation_obligation_digest
            assignment = assignment_by_digest[obligation.assignment_digest].payload
            execution_requirement = assignment["execution_requirement"]
            if execution_requirement == "evidence_only" and linked_digest is not None:
                raise ValueError(
                    "evidence-only assignments cannot claim scenario operations"
                )
            if (
                execution_requirement == "blocking_scenario"
                and assignment["applicability"] == "unconditional"
                and linked_digest is None
            ):
                raise ValueError(
                    "unconditional blocking-scenario assignments require one explicit scenario-gate link"
                )
            if linked_digest is None:
                continue
            linked_operation = operation_obligation_by_digest.get(linked_digest)
            if (
                obligation.impact is not GateImpact.BLOCKING
                or linked_operation is None
                or linked_operation.obligation_record.payload["operation_kind"]
                != "blocking_scenario"
                or linked_operation.obligation_record.payload["subject_kind"]
                != "gate_occurrence"
                or linked_operation.obligation_record.payload["subject_digest"]
                != obligation.occurrence_digest
            ):
                raise ValueError(
                    "scenario gate does not link its exact critical-operation obligation"
                )
        canonical_scenario_digests = {
            item.obligation_digest
            for item in operation_obligations
            if item.obligation_record.payload["operation_kind"]
            == "blocking_scenario"
        }
        if set(linked_scenario_digests) != canonical_scenario_digests:
            raise ValueError(
                "blocking-scenario obligations require one explicit scenario-gate link"
            )
        expected = {
            "requirements_digest": self.requirements_record.digest(),
            "validation_contract_digest": self.validation_contract_record.digest(),
            "generation_digest": self.generation_record.digest(),
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": self.target_protected_state_record.digest(),
            "obligation_digests": obligation_digests,
            "operation_obligation_set_digest": (
                self.operation_obligation_set_record.digest()
            ),
        }
        for field, value in expected.items():
            actual = tuple(payload[field]) if field == "obligation_digests" else payload[field]
            if actual != value:
                raise ValueError(f"promotion contract does not bind exact {field}")
        candidate = self.generation_record.digest()
        accepted = payload["expected_accepted_generation_digest"]
        active = payload["expected_active_generation_digest"]
        phase = PromotionPhase(payload["phase"])
        if phase is PromotionPhase.ACCEPTED and (
            accepted != candidate or active != candidate
        ):
            raise ValueError(
                "accepted phase requires accepted and active candidate generation"
            )
        if phase is PromotionPhase.ACTIVE and (
            active != candidate or accepted == candidate
        ):
            raise ValueError(
                "active phase requires the active candidate and a prior accepted generation"
            )
        if phase in {PromotionPhase.PUBLISHED, PromotionPhase.PREVALIDATED} and (
            accepted != active or active == candidate
        ):
            raise ValueError("pre-activation phases must preserve one prior generation")
        for obligation in operation_obligations:
            operation_payload = obligation.obligation_record.payload
            operation_generation = operation_payload["generation_binding"]
            operation_phase = PromotionPhase(
                operation_payload["lifecycle_phase"]
            )
            w4_rehearsal = (
                phase is PromotionPhase.PREVALIDATED
                and operation_payload["lifecycle_phase"]
                == PromotionPhase.ACTIVE.value
                and operation_payload["target_kind"]
                == OperationTargetKind.LIVE_ROOT.value
                and obligation.requirement.requirement_record.payload["purpose"]
                in {"baseline_rehearsal_install", "baseline_restoration"}
            )
            if (
                phase is PromotionPhase.ACCEPTED
                and operation_payload["lifecycle_phase"]
                == PromotionPhase.ACCEPTED.value
            ):
                raise ValueError(
                    "accepted cuts forbid accepted-phase critical operations"
                )
            if (
                operation_generation["mode"] != "required_generation"
                or operation_generation.get("generation_digest")
                != self.generation_record.digest()
                or operation_payload["generation_class"]
                != self.generation_record.payload["generation_class"]
                or (
                    phase is not PromotionPhase.ACCEPTED
                    and operation_phase is not phase
                    and not w4_rehearsal
                )
            ):
                raise ValueError(
                    "operation obligation does not bind the promotion generation and an established phase"
                )
            if (
                phase is PromotionPhase.ACCEPTED
                and (
                    operation_payload["operation_kind"] != "blocking_scenario"
                    or operation_phase is not PromotionPhase.ACTIVE
                    or operation_payload["target_kind"]
                    != OperationTargetKind.SERVICE.value
                )
            ):
                raise ValueError(
                    "accepted closeout scenarios must run against an active service"
                )
        state = self.target_protected_state_record.payload
        if state["target_digest"] != self.target_record.digest():
            raise ValueError("contract protected state does not bind target")
        if state["generation_digest"] != candidate:
            raise ValueError("contract protected state does not bind candidate generation")
        if state["target_kind"] != payload["target_kind"]:
            raise ValueError(
                "contract protected state and phase-establishing operation do not bind target kind"
            )
        expected_state_phase = (
            PromotionPhase.ACTIVE.value
            if phase is PromotionPhase.ACCEPTED
            else phase.value
        )
        if state["lifecycle_phase"] != expected_state_phase:
            raise ValueError(
                "contract protected state does not bind the established lifecycle phase"
            )

        if (
            payload["predecessor_checkpoint_digest"]
            != self.predecessor_checkpoint.checkpoint_digest
        ):
            raise ValueError("promotion contract does not bind its exact predecessor checkpoint")
        _validate_promotion_predecessor(
            phase=phase,
            generation_digest=candidate,
            target_digest=self.target_record.digest(),
            target_state_digest=self.target_protected_state_record.digest(),
            predecessor=self.predecessor_checkpoint,
        )
        predecessor_cut = self.predecessor_checkpoint.evidence_cut
        if phase is PromotionPhase.PUBLISHED:
            expected_accepted = self.predecessor_checkpoint.generation_record.digest()
            expected_active = expected_accepted
        else:
            if not isinstance(predecessor_cut, AtomicEvidenceCut):
                raise ValueError(
                    "promotion pointer continuity requires the predecessor evidence cut"
                )
            if phase is PromotionPhase.PREVALIDATED:
                expected_accepted = (
                    predecessor_cut.accepted_generation_record.digest()
                )
                expected_active = predecessor_cut.active_generation_record.digest()
            elif phase is PromotionPhase.ACTIVE:
                expected_accepted = (
                    predecessor_cut.accepted_generation_record.digest()
                )
                expected_active = candidate
            else:
                expected_accepted = candidate
                expected_active = candidate
        if (accepted, active) != (expected_accepted, expected_active):
            raise ValueError(
                "promotion generation pointers do not continue the exact predecessor state"
            )
        self._validate_operation_realization_roles()
        self._validate_phase_anchor_material(
            phase=phase,
            linked_scenario_digests=tuple(linked_scenario_digests),
        )
        if phase is PromotionPhase.ACCEPTED:
            self._validate_accepted_service_restart_model(
                assignment_by_digest=assignment_by_digest,
            )
        phase_operation_digest = payload.get(
            "phase_establishing_operation_obligation_digest"
        )
        if phase is PromotionPhase.ACCEPTED:
            if phase_operation_digest is not None:
                raise ValueError("accepted phase cannot claim a phase-establishing operation")
            authorization = _record(
                self.acceptance_authorization_record,
                field="acceptance_authorization_record",
                kind="authorization",
            )
            separation = _record(
                self.acceptance_separation_policy_record,
                field="acceptance_separation_policy_record",
                kind="separation_policy",
            )
            actor = _record(
                self.acceptance_actor_identity_record,
                field="acceptance_actor_identity_record",
                kind="identity",
            )
            if (
                payload["acceptance_authorization_digest"]
                != authorization.digest()
                or not _authorization_admits_identity(
                    authorization,
                    separation,
                    actor,
                    action="accept_generation",
                    subject_kind="acceptance_request",
                    require_approver_role=True,
                )
            ):
                raise ValueError(
                    "accepted phase does not bind an authorized acceptance actor"
                )
        else:
            if any(
                material is not None
                for material in (
                    self.acceptance_authorization_record,
                    self.acceptance_separation_policy_record,
                    self.acceptance_actor_identity_record,
                )
            ):
                raise ValueError(
                    "nonaccepted phase cannot bind acceptance authorization material"
                )
            phase_operation = operation_obligation_by_digest.get(
                phase_operation_digest
            )
            if (
                phase_operation is None
                or phase_operation.obligation_record.payload["lifecycle_phase"]
                != phase.value
                or phase_operation.obligation_record.payload["operation_kind"]
                != _PHASE_ESTABLISHING_OPERATION[phase].value
                or phase_operation.obligation_record.payload["target_kind"]
                != _PHASE_TARGET_KIND[phase].value
                or payload["target_kind"] != _PHASE_TARGET_KIND[phase].value
            ):
                raise ValueError(
                    "promotion contract does not identify its exact phase-establishing operation obligation"
                )

    def _validate_operation_realization_roles(self) -> None:
        captured = _captured_baseline(self.predecessor_checkpoint)
        linked_occurrence_by_operation_obligation = {
            obligation.scenario_operation_obligation_digest: (
                obligation.occurrence_digest
            )
            for obligation in self.obligations
            if obligation.scenario_operation_obligation_digest is not None
        }
        for realization in self.operation_realizations:
            requirement = realization.requirement.requirement_record.payload
            operation = realization.operation.operation_record.payload
            subject_role = requirement["subject_binding_role"]
            expected_subject = {
                "candidate_generation": self.generation_digest,
                "captured_baseline": captured.generation_record.digest(),
                "gate_occurrence": linked_occurrence_by_operation_obligation.get(
                    realization.obligation.obligation_digest
                ),
            }.get(subject_role)
            if subject_role in {"composite_authority", "control_record"}:
                subject_record = realization.resolved_subject_record
                try:
                    subject_record = (
                        _record(
                            subject_record,
                            field="resolved_subject_record",
                            kind="composite_authority",
                        )
                        if subject_role == "composite_authority"
                        else _any_record(
                            subject_record,
                            field="resolved_subject_record",
                        )
                    )
                except (TypeError, ValueError):
                    raise ValueError(
                        "operation realization lacks its typed approved subject material"
                    ) from None
                expected_subject = subject_record.digest()
            if expected_subject is None or (
                realization.resolved_subject_digest != expected_subject
            ):
                raise ValueError(
                    "operation realization does not resolve its approved subject binding role"
                )

            generation_role = requirement["generation_binding_role"]
            expected_generation_binding: dict[str, object]
            if generation_role == "candidate_generation":
                expected_generation_binding = {
                    "generation_digest": self.generation_digest,
                    "mode": GenerationBindingMode.REQUIRED_GENERATION.value,
                }
            elif generation_role == "captured_baseline_generation":
                expected_generation_binding = {
                    "generation_digest": captured.generation_record.digest(),
                    "mode": GenerationBindingMode.REQUIRED_GENERATION.value,
                }
            elif generation_role == "predecessor_generation":
                expected_generation_binding = {
                    "generation_digest": (
                        self.predecessor_checkpoint.generation_record.digest()
                    ),
                    "mode": GenerationBindingMode.REQUIRED_GENERATION.value,
                }
            elif generation_role == "no_generation":
                expected_generation_binding = {
                    "mode": GenerationBindingMode.NO_GENERATION.value,
                }
            else:
                expected_generation_binding = {
                    "generation_digest": captured.generation_record.digest(),
                    "mode": GenerationBindingMode.B0_CAPTURE_SENTINEL.value,
                    "sentinel_digest": captured.checkpoint_digest,
                }
            if realization.resolved_generation_binding != expected_generation_binding:
                raise ValueError(
                    "operation realization does not resolve its approved generation binding role"
                )
            observed_prestate = realization.observed_prestate_record.payload
            if (
                observed_prestate["target_digest"]
                != realization.requirement.target_record.digest()
                or observed_prestate["target_kind"] != requirement["target_kind"]
                or operation["expected_protected_state_digest"]
                != realization.observed_prestate_record.digest()
                or parse_canonical_timestamp(observed_prestate["observed_at"])
                > parse_canonical_timestamp(
                    realization.operation.intent_record.payload["registered_at"]
                )
            ):
                raise ValueError(
                    "operation realization does not bind a target-specific observed prestate"
                )
            lifecycle_pointer_digests = {
                self.predecessor_checkpoint.target_protected_state_record.digest(),
                self.target_protected_state_record.digest(),
            }
            if realization.observed_prestate_record.digest() in (
                lifecycle_pointer_digests
            ):
                raise ValueError(
                    "operation target prestate observation must remain distinct from lifecycle pointer state"
                )

    def _validate_phase_anchor_material(
        self,
        *,
        phase: PromotionPhase,
        linked_scenario_digests: tuple[str, ...],
    ) -> None:
        payload = self.contract_record.payload
        if phase is PromotionPhase.ACTIVE:
            receipt = self.baseline_restoration_receipt
            if not isinstance(receipt, BaselineRestorationReceipt):
                raise TypeError(
                    "active contract requires a BaselineRestorationReceipt"
                )
            if (
                payload["baseline_restoration_receipt_digest"]
                != receipt.receipt_digest
                or not isinstance(
                    self.predecessor_checkpoint,
                    (LifecycleCheckpoint, StructuralLifecycleCandidate),
                )
                or not _canonical_graph_equivalent(
                    self.predecessor_checkpoint.baseline_restoration_receipt,
                    receipt,
                )
            ):
                raise ValueError(
                    "active contract does not consume its predecessor's exact baseline restoration receipt"
                )
        elif self.baseline_restoration_receipt is not None:
            raise ValueError(
                "only an active contract may consume baseline restoration"
            )

        scenario_required = bool(linked_scenario_digests)
        if phase is PromotionPhase.ACCEPTED and scenario_required:
            receipt = self.service_anchor_receipt
            if (
                not isinstance(receipt, ServiceAnchorReceipt)
                or payload.get("predecessor_service_anchor_receipt_digest")
                != receipt.receipt_digest
                or not isinstance(
                    self.predecessor_checkpoint,
                    (LifecycleCheckpoint, StructuralLifecycleCandidate),
                )
                or not _canonical_graph_equivalent(
                    self.predecessor_checkpoint.service_anchor_receipt,
                    receipt,
                )
                or receipt.generation_digest != self.generation_digest
            ):
                raise ValueError(
                    "accepted contract does not consume its predecessor's exact service anchor receipt"
                )
        elif self.service_anchor_receipt is not None or (
            "predecessor_service_anchor_receipt_digest" in payload
        ):
            raise ValueError(
                "a service anchor receipt is required exactly for accepted scenario obligations"
            )

    def _validate_accepted_service_restart_model(
        self,
        *,
        assignment_by_digest: dict[str, ControlRecord],
    ) -> None:
        final_obligations = [
            obligation
            for obligation in self.operation_obligations
            if obligation.requirement.requirement_record.payload["purpose"]
            == "final_service_restart"
        ]
        if len(final_obligations) != 1:
            raise ValueError(
                "accepted contract requires exactly one final service restart"
            )
        final_obligation = final_obligations[0]
        final_requirement = final_obligation.requirement
        final_assignment_digest = final_requirement.assignment_digest
        final_assignment = assignment_by_digest.get(final_assignment_digest)
        final_realizations = [
            realization
            for realization in self.operation_realizations
            if realization.obligation.obligation_digest
            == final_obligation.obligation_digest
        ]
        if (
            final_assignment is None
            or final_assignment.payload["applicability"] != "unconditional"
            or final_assignment.payload["execution_requirement"]
            != "blocking_scenario"
            or final_requirement.realization_condition != "always"
            or len(final_realizations) != 1
        ):
            raise ValueError(
                "final service restart requires one unconditional always-realized blocking assignment"
            )
        final_operation = final_realizations[0].operation
        if (
            self.operation_obligations[-1].obligation_digest
            != final_obligation.obligation_digest
            or self.operation_realizations[-1].realization_digest
            != final_realizations[0].realization_digest
            or final_operation.intent_record.payload["journal_sequence"]
            != max(
                operation.intent_record.payload["journal_sequence"]
                for operation in (
                    realization.operation
                    for realization in self.operation_realizations
                )
            )
            or final_operation.terminal_sequence
            != max(
                realization.operation.terminal_sequence
                for realization in self.operation_realizations
            )
        ):
            raise ValueError("final service restart must be the last critical operation")
        for realization in self.operation_realizations:
            operation = realization.operation
            payload = operation.operation_record.payload
            if (
                payload["operation_kind"]
                != CriticalOperationKind.BLOCKING_SCENARIO.value
                or payload["target_kind"] != OperationTargetKind.SERVICE.value
            ):
                continue
            purpose = realization.requirement.requirement_record.payload["purpose"]
            expected_epoch = operation.expected_protected_state_record.payload.get(
                "process_epoch"
            )
            intended_epoch = operation.intended_protected_state_record.payload.get(
                "process_epoch"
            )
            restart = purpose in {"service_restart", "final_service_restart"}
            if (
                not isinstance(expected_epoch, str)
                or not isinstance(intended_epoch, str)
                or restart != (expected_epoch != intended_epoch)
            ):
                raise ValueError(
                    "service restart operations change process epoch and ordinary scenarios preserve it"
                )

    @property
    def contract_digest(self) -> str:
        return self.contract_record.digest()

    @property
    def generation_digest(self) -> str:
        return self.generation_record.digest()

    @property
    def phase(self) -> PromotionPhase:
        return PromotionPhase(self.contract_record.payload["phase"])

    @property
    def target(self) -> OperationTarget:
        return OperationTarget(
            kind=OperationTargetKind(self.contract_record.payload["target_kind"]),
            target_id=self.target_record.payload["identity_id"],
        )


@dataclass(frozen=True, slots=True)
class RegisteredAttempt:
    """Canonical append-before-work intent, attempt, and terminal chain."""

    obligation_record: ControlRecord
    intent_record: ControlRecord
    attempt_record: ControlRecord
    terminal_record: ControlRecord

    def __post_init__(self) -> None:
        _record(
            self.obligation_record,
            field="obligation_record",
            kind="promotion_obligation",
        )
        _record(self.intent_record, field="intent_record", kind="intent")
        _record(self.attempt_record, field="attempt_record", kind="attempt")
        _record(self.terminal_record, field="terminal_record", kind="terminal_record")
        obligation = self.obligation_record.payload
        intent = self.intent_record.payload
        attempt = self.attempt_record.payload
        terminal = self.terminal_record.payload
        if intent["intent_type"] != "gate_occurrence":
            raise ValueError("registered gate attempt requires a gate-occurrence intent")
        if obligation["occurrence_digest"] != self.intent_record.digest():
            raise ValueError("obligation occurrence does not bind intent")
        if intent.get("assignment_digest") != obligation["assignment_digest"]:
            raise ValueError("intent does not bind obligation assignment")
        if attempt["intent_digest"] != self.intent_record.digest():
            raise ValueError("attempt does not bind intent")
        if attempt["assignment_digest"] != obligation["assignment_digest"]:
            raise ValueError("attempt does not bind obligation assignment")
        if attempt["actor_identity_digest"] != intent["actor_identity_digest"]:
            raise ValueError("attempt actor does not bind the registered gate actor")
        if attempt["context_digest"] != intent["context_digest"]:
            raise ValueError("attempt context does not bind intent")
        if terminal["terminal_type"] != "gate_attempt":
            raise ValueError("registered attempt requires a gate-attempt terminal")
        if terminal["attempt_digest"] != self.attempt_record.digest():
            raise ValueError("terminal does not bind attempt")
        if terminal["assignment_digest"] != obligation["assignment_digest"]:
            raise ValueError("terminal does not bind obligation assignment")
        intent_sequence = intent["journal_sequence"]
        attempt_sequence = attempt["journal_sequence"]
        terminal_sequence = terminal["journal_sequence"]
        if not intent_sequence < attempt_sequence < terminal_sequence:
            raise ValueError("journal order must be intent before attempt before terminal")
        if not (
            parse_canonical_timestamp(intent["registered_at"])
            <= parse_canonical_timestamp(attempt["started_at"])
            <= parse_canonical_timestamp(terminal["completed_at"])
        ):
            raise ValueError("attempt timestamps do not follow registration order")

    @property
    def obligation_digest(self) -> str:
        return self.obligation_record.digest()

    @property
    def attempt_digest(self) -> str:
        return self.attempt_record.digest()

    @property
    def assignment_digest(self) -> str:
        return self.attempt_record.payload["assignment_digest"]

    @property
    def occurrence_digest(self) -> str:
        return self.intent_record.digest()

    @property
    def terminal_sequence(self) -> int:
        return self.terminal_record.payload["journal_sequence"]


@dataclass(frozen=True, slots=True)
class RegisteredOperation:
    """One critical operation, including exact recovery provenance when used."""

    intent_record: ControlRecord
    operation_record: ControlRecord
    target_record: ControlRecord
    expected_protected_state_record: ControlRecord
    intended_protected_state_record: ControlRecord
    capability_record: ControlRecord
    terminal_record: ControlRecord
    validator_attestation_records: tuple[ControlRecord, ...]
    recovery_predecessor_operation: RegisteredOperation | None = None
    recovery_owner_identity_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        _record(self.intent_record, field="intent_record", kind="intent")
        _record(self.operation_record, field="operation_record", kind="operation")
        _record(self.target_record, field="target_record", kind="identity")
        _record(
            self.expected_protected_state_record,
            field="expected_protected_state_record",
            kind="protected_state",
        )
        _record(
            self.intended_protected_state_record,
            field="intended_protected_state_record",
            kind="protected_state",
        )
        _record(self.capability_record, field="capability_record", kind="capability")
        _record(self.terminal_record, field="terminal_record", kind="terminal_record")
        intent = self.intent_record.payload
        operation = self.operation_record.payload
        capability = self.capability_record.payload
        terminal = self.terminal_record.payload
        expected_state = self.expected_protected_state_record.payload
        intended_state = self.intended_protected_state_record.payload
        validator_attestations = tuple(self.validator_attestation_records)
        object.__setattr__(
            self,
            "validator_attestation_records",
            validator_attestations,
        )
        if intent["intent_type"] != "critical_operation":
            raise ValueError("registered operation requires a critical-operation intent")
        if operation["intent_digest"] != self.intent_record.digest():
            raise ValueError("critical operation does not bind intent")
        if intent["operation_plan_digest"] != operation["plan_digest"]:
            raise ValueError("operation intent does not bind plan")
        if intent["subject_digest"] != operation["subject_digest"]:
            raise ValueError("operation intent does not bind subject")
        if (
            self.target_record.payload["identity_type"] != "target"
            or operation["target_digest"] != self.target_record.digest()
            or operation["target_id"] != self.target_record.payload["identity_id"]
            or expected_state["target_digest"] != self.target_record.digest()
            or intended_state["target_digest"] != self.target_record.digest()
        ):
            raise ValueError("critical operation does not bind its exact target identity")
        if (
            expected_state["target_kind"] != operation["target_kind"]
            or intended_state["target_kind"] != operation["target_kind"]
        ):
            raise ValueError(
                "critical operation protected states must retain the exact target kind"
            )
        if (
            operation["expected_protected_state_digest"]
            != self.expected_protected_state_record.digest()
            or operation["intended_protected_state_digest"]
            != self.intended_protected_state_record.digest()
        ):
            raise ValueError("critical operation does not bind exact protected-state records")
        recovery_operation = (
            operation["operation_kind"] == CriticalOperationKind.RECOVERY.value
        )
        state_digest_unchanged = (
            expected_state["state_digest"] == intended_state["state_digest"]
        )
        if (
            expected_state["projection_id"] != intended_state["projection_id"]
            or (
                state_digest_unchanged
                and (
                    not recovery_operation
                    or expected_state["generation_digest"]
                    != intended_state["generation_digest"]
                    or expected_state["lifecycle_phase"]
                    != intended_state["lifecycle_phase"]
                    or expected_state.get("process_epoch")
                    != intended_state.get("process_epoch")
                )
            )
            or expected_state["fence_epoch"] + 1 != intended_state["fence_epoch"]
        ):
            raise ValueError(
                "critical operation protected state must keep one projection and advance one fence epoch"
            )
        binding = operation["generation_binding"]
        if (
            (
                operation["operation_kind"] == CriticalOperationKind.ROLLBACK.value
                and expected_state["generation_digest"]
                != binding.get("generation_digest")
            )
            or (
                operation["operation_kind"] != CriticalOperationKind.ROLLBACK.value
                and intended_state["generation_digest"]
                != binding.get("generation_digest")
            )
            or intended_state["lifecycle_phase"] != operation["lifecycle_phase"]
        ):
            raise ValueError(
                "critical operation intended state does not bind its generation and lifecycle phase"
            )
        if recovery_operation:
            predecessor = self.recovery_predecessor_operation
            if not isinstance(predecessor, RegisteredOperation):
                raise ValueError(
                    "recovery operation requires its exact failed predecessor operation"
                )
            owner = _record(
                self.recovery_owner_identity_record,
                field="recovery_owner_identity_record",
                kind="identity",
            )
            predecessor_operation = predecessor.operation_record.payload
            predecessor_terminal = predecessor.terminal_record.payload
            predecessor_expected_state = (
                predecessor.expected_protected_state_record.payload
            )
            predecessor_intended_state = (
                predecessor.intended_protected_state_record.payload
            )
            predecessor_binding = predecessor_operation["generation_binding"]
            b0_binding_mode = GenerationBindingMode.B0_CAPTURE_SENTINEL.value
            if (
                binding["mode"] == b0_binding_mode
                or predecessor_binding["mode"] == b0_binding_mode
            ) and (
                binding["mode"] != b0_binding_mode
                or predecessor_binding["mode"] != b0_binding_mode
                or binding["sentinel_digest"]
                != predecessor_binding["sentinel_digest"]
            ):
                raise ValueError(
                    "B0 recovery must retain the exact predecessor capture sentinel"
                )
            owner_roles = tuple(owner.payload.get("roles", ()))
            if any(
                target_kind != operation["target_kind"]
                for target_kind in (
                    predecessor_operation["target_kind"],
                    predecessor_expected_state["target_kind"],
                    predecessor_intended_state["target_kind"],
                    expected_state["target_kind"],
                    intended_state["target_kind"],
                )
            ):
                raise ValueError(
                    "recovery successor and failed predecessor must retain the exact target kind"
                )
            if (
                predecessor_terminal["journal_sequence"]
                >= intent["journal_sequence"]
            ):
                raise ValueError(
                    "recovery journal order must place the failed predecessor terminal before the successor intent"
                )
            predecessor_completed_at = parse_canonical_timestamp(
                predecessor_terminal["completed_at"]
            )
            if parse_canonical_timestamp(
                expected_state["observed_at"]
            ) > predecessor_completed_at:
                raise ValueError(
                    "recovery expected snapshot observation cannot follow the failed predecessor terminal"
                )
            if (
                capability["capability_type"] != "recovery"
                or predecessor_terminal["outcome"] != "failed"
                or predecessor_terminal["operation_digest"]
                != predecessor.operation_digest
                or capability["predecessor_operation_id"]
                != predecessor_operation["operation_id"]
                or capability["predecessor_failure_record_digest"]
                != predecessor.terminal_digest
                or capability["predecessor_fence_epoch"]
                != predecessor.capability_record.payload["fence_epoch"]
                or expected_state["fence_epoch"]
                != capability["predecessor_fence_epoch"]
                or capability["recovery_contract_digest"]
                != predecessor_operation["recovery_contract_digest"]
                or predecessor_operation["recovery_target_digest"]
                != self.intended_protected_state_record.digest()
                or capability["authorizer_digest"] != owner.digest()
                or capability["recovery_owner_role"] not in owner_roles
                or owner.payload["identity_type"]
                not in {"principal", "validator"}
                or operation["subject_kind"]
                != OperationSubjectKind.CONTROL_RECORD.value
                or operation["subject_digest"]
                != predecessor_operation["recovery_contract_digest"]
                or predecessor_terminal["poststate_digest"]
                != self.expected_protected_state_record.digest()
                or operation["generation_class"]
                != predecessor_operation["generation_class"]
                or self.target_record.digest()
                != predecessor.target_record.digest()
                or predecessor_completed_at
                > parse_canonical_timestamp(intent["registered_at"])
            ):
                raise ValueError(
                    "recovery capability does not bind the exact failed predecessor recovery contract, predecessor recovery target, owner, and fence"
                )
        elif (
            capability["capability_type"] != "operation"
            or self.recovery_predecessor_operation is not None
            or self.recovery_owner_identity_record is not None
        ):
            raise ValueError(
                "non-recovery operation requires an exact operation capability and forbids recovery provenance"
            )
        capability_expected = {
            "authority_head_digest": operation["authority_head_digest"],
            "intended_protected_state_digest": operation[
                "intended_protected_state_digest"
            ],
            "intent_digest": self.intent_record.digest(),
            "operation_digest": self.operation_record.digest(),
            "operation_id": operation["operation_id"],
            "plan_digest": operation["plan_digest"],
            "single_use_scope_digest": self.operation_record.digest(),
            "subject_digest": operation["subject_digest"],
            "target_id": operation["target_id"],
            "target_kind": operation["target_kind"],
        }
        if any(
            capability[field] != expected
            for field, expected in capability_expected.items()
        ) or (
            capability["status"] != "consumed"
            or capability["fence_epoch"] != intended_state["fence_epoch"]
        ):
            raise ValueError(
                "fenced capability does not bind the complete critical operation"
            )
        if terminal["terminal_type"] != "critical_operation":
            raise ValueError("registered operation requires a critical-operation terminal")
        if terminal["operation_digest"] != self.operation_record.digest():
            raise ValueError("terminal does not bind critical operation")
        if terminal["capability_digest"] != self.capability_record.digest():
            raise ValueError("terminal does not bind the fenced capability")
        for attestation_record in validator_attestations:
            _record(
                attestation_record,
                field="validator_attestation_records item",
                kind="operation_attestation",
            )
        if tuple(terminal["validator_attestation_digests"]) != tuple(
            item.digest() for item in validator_attestations
        ):
            raise ValueError(
                "terminal does not bind the exact operation validator attestations"
            )
        if intent["journal_sequence"] >= terminal["journal_sequence"]:
            raise ValueError("journal order must be intent before operation terminal")
        if (
            terminal["outcome"] == "succeeded"
            and terminal["poststate_digest"]
            != operation["intended_protected_state_digest"]
        ):
            raise ValueError("operation terminal does not bind intended protected state")
        registered_at = parse_canonical_timestamp(intent["registered_at"])
        completed_at = parse_canonical_timestamp(terminal["completed_at"])
        if registered_at > completed_at:
            raise ValueError("operation terminal cannot precede intent registration")
        issued_at = parse_canonical_timestamp(capability["issued_at"])
        expires_at = parse_canonical_timestamp(capability["expires_at"])
        expected_observed_at = parse_canonical_timestamp(
            expected_state["observed_at"]
        )
        intended_observed_at = parse_canonical_timestamp(
            intended_state["observed_at"]
        )
        if not (
            expected_observed_at
            <= registered_at
            <= issued_at
            <= intended_observed_at
            <= completed_at
            <= expires_at
        ):
            raise ValueError(
                "critical operation must complete under its live fenced capability"
            )
        for attestation_record in validator_attestations:
            attestation = attestation_record.payload
            if attestation["operation_digest"] != self.operation_record.digest():
                raise ValueError(
                    "validator attestation does not bind the critical operation"
                )
            if attestation["subject_digest"] != operation["subject_digest"]:
                raise ValueError("validator attestation does not bind operation subject")
            if attestation["validator_digest"] != operation["terminal_validator_digest"]:
                raise ValueError("validator attestation does not bind terminal validator")
            if attestation["outcome"] != terminal["outcome"]:
                raise ValueError("validator attestation does not bind terminal outcome")
            if attestation["poststate_digest"] != terminal["poststate_digest"]:
                raise ValueError("validator attestation does not bind terminal poststate")
            observed_at = parse_canonical_timestamp(attestation["observed_at"])
            if terminal["outcome"] == "succeeded" and not (
                intended_observed_at <= observed_at <= completed_at
            ):
                raise ValueError(
                    "successful validator attestation observation must occur between the intended protected state and terminal"
                )
            if terminal["outcome"] != "succeeded" and not (
                registered_at <= observed_at <= completed_at
            ):
                raise ValueError(
                    "validator attestation observation must occur between intent and terminal"
                )

    @property
    def operation_digest(self) -> str:
        return self.operation_record.digest()

    @property
    def terminal_digest(self) -> str:
        return self.terminal_record.digest()

    @property
    def capability_digest(self) -> str:
        return self.capability_record.digest()

    @property
    def terminal_sequence(self) -> int:
        return self.terminal_record.payload["journal_sequence"]


def _authorization_admits_identity(
    authorization_record: ControlRecord,
    separation_policy_record: ControlRecord,
    identity_record: ControlRecord,
    *,
    action: str,
    subject_kind: str,
    require_approver_role: bool = False,
) -> bool:
    return bool(
        _eligible_authorization_roles(
            authorization_record,
            separation_policy_record,
            identity_record,
            action=action,
            subject_kind=subject_kind,
            require_approver_role=require_approver_role,
        )
    )


def _eligible_authorization_roles(
    authorization_record: ControlRecord,
    separation_policy_record: ControlRecord,
    identity_record: ControlRecord,
    *,
    action: str,
    subject_kind: str,
    require_approver_role: bool = False,
) -> set[str]:
    authorization = authorization_record.payload
    separation = separation_policy_record.payload
    identity_digest = identity_record.digest()
    identity_roles = set(identity_record.payload.get("roles", ()))
    allowed_roles = set(authorization.get("allowed_actor_roles", ()))
    allowed_identities = set(
        authorization.get("allowed_actor_identity_digests", ())
    )
    required_roles = set(separation["required_actor_roles"])
    if (
        authorization["action"] != action
        or authorization["subject_kind"] != subject_kind
        or authorization["separation_policy_digest"]
        != separation_policy_record.digest()
        or identity_record.payload["identity_type"] not in {"principal", "validator"}
        or identity_digest in separation["forbidden_actor_identity_digests"]
        or not required_roles <= identity_roles
    ):
        return set()
    eligible_roles = (
        identity_roles
        if identity_digest in allowed_identities
        else identity_roles & allowed_roles
    )
    if required_roles:
        eligible_roles &= required_roles
    if require_approver_role:
        eligible_roles &= set(authorization["approver_roles"])
    return eligible_roles


def _authorization_admits_actor(
    authorization_record: ControlRecord,
    separation_policy_record: ControlRecord,
    identity_record: ControlRecord,
    *,
    actor_identity_digest: str,
    actor_role: str,
    action: str,
    subject_kind: str = "gate",
    require_approver_role: bool = False,
) -> bool:
    eligible_roles = _eligible_authorization_roles(
        authorization_record,
        separation_policy_record,
        identity_record,
        action=action,
        subject_kind=subject_kind,
        require_approver_role=require_approver_role,
    )
    return (
        actor_identity_digest == identity_record.digest()
        and actor_role in eligible_roles
    )


_ATTESTATION_UNKNOWN_REASONS = {
    "assignment_mismatch",
    "context_mismatch",
    "dependency_mismatch",
    "gate_mismatch",
    "reported_unknown",
    "separation_violation",
    "subject_mismatch",
}
_POST_PROOF_UNKNOWN_REASONS = {
    "missing_attestation",
    *_ATTESTATION_UNKNOWN_REASONS,
}


def _proof_matches_assignment(
    proof: object,
    assignment: object,
    *,
    assignment_digest: str,
    context_digest: str,
) -> bool:
    return (
        proof["predicate_digest"] == assignment["predicate_digest"]
        and proof["assignment_digest"] == assignment_digest
        and proof["context_digest"] == context_digest
        and proof["dependency_projection_digest"]
        == assignment["dependency_projection_digest"]
        and proof["gate_digest"] == assignment["gate_digest"]
        and proof["subject_digest"] == assignment["subject_digest"]
    )


def _attestation_unknown_reason(
    record: ControlRecord,
    *,
    assignment: object,
    assignment_digest: str,
    context_digest: str,
    authorization_record: ControlRecord,
    separation_policy_record: ControlRecord,
    validator_identity_record: ControlRecord,
) -> str | None:
    attestation = record.payload
    if attestation["assignment_digest"] != assignment_digest:
        return "assignment_mismatch"
    if attestation["subject_digest"] != assignment["subject_digest"]:
        return "subject_mismatch"
    if attestation["gate_digest"] != assignment["gate_digest"]:
        return "gate_mismatch"
    if attestation["context_digest"] != context_digest:
        return "context_mismatch"
    if (
        attestation["dependency_projection_digest"]
        != assignment["dependency_projection_digest"]
    ):
        return "dependency_mismatch"
    if not _authorization_admits_actor(
        authorization_record,
        separation_policy_record,
        validator_identity_record,
        actor_identity_digest=attestation["actor_identity_digest"],
        actor_role=attestation["actor_role"],
        action="attest_gate",
    ):
        return "separation_violation"
    if attestation["outcome"] == "unknown":
        return "reported_unknown"
    return None


@dataclass(frozen=True, slots=True)
class BoundEvaluation:
    """A canonical evaluation and every record used to derive it."""

    attempt_record: ControlRecord
    context_record: ControlRecord
    assignment_record: ControlRecord
    gate_record: ControlRecord
    attestation_authorization_record: ControlRecord
    separation_policy_record: ControlRecord
    validator_identity_record: ControlRecord
    evidence_records: tuple[ControlRecord, ...]
    evaluation_record: ControlRecord
    validity_policy_record: ControlRecord
    invalidation_policy_record: ControlRecord
    evaluated_dependency_projection_record: ControlRecord
    current_dependency_projection_record: ControlRecord
    trusted_time_observation_record: ControlRecord
    invalidation_stream_checkpoint_record: ControlRecord
    currency_proof_record: ControlRecord
    predicate_authorization_record: ControlRecord | None = None
    inclusion_edge_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        _record(self.attempt_record, field="attempt_record", kind="attempt")
        _record(self.context_record, field="context_record", kind="validation_context")
        _record(self.assignment_record, field="assignment_record", kind="assignment")
        _record(self.gate_record, field="gate_record", kind="gate")
        _record(
            self.attestation_authorization_record,
            field="attestation_authorization_record",
            kind="authorization",
        )
        _record(
            self.separation_policy_record,
            field="separation_policy_record",
            kind="separation_policy",
        )
        _record(
            self.validator_identity_record,
            field="validator_identity_record",
            kind="identity",
        )
        _record(self.evaluation_record, field="evaluation_record", kind="evaluation")
        _record(
            self.validity_policy_record,
            field="validity_policy_record",
            kind="validity_policy",
        )
        _record(
            self.invalidation_policy_record,
            field="invalidation_policy_record",
            kind="invalidation_policy",
        )
        _record(
            self.evaluated_dependency_projection_record,
            field="evaluated_dependency_projection_record",
            kind="dependency_projection",
        )
        _record(
            self.current_dependency_projection_record,
            field="current_dependency_projection_record",
            kind="dependency_projection",
        )
        trusted_time = _record(
            self.trusted_time_observation_record,
            field="trusted_time_observation_record",
            kind="trusted_time_observation",
        ).payload
        stream_checkpoint = _record(
            self.invalidation_stream_checkpoint_record,
            field="invalidation_stream_checkpoint_record",
            kind="invalidation_stream_checkpoint",
        ).payload
        currency_proof = _record(
            self.currency_proof_record,
            field="currency_proof_record",
            kind="evidence_currency_proof",
        ).payload
        evidence_records = tuple(self.evidence_records)
        object.__setattr__(self, "evidence_records", evidence_records)
        for evidence in evidence_records:
            _any_record(evidence, field="evidence_records item")
        assignment = self.assignment_record.payload
        gate = self.gate_record.payload
        attestation_authorization = self.attestation_authorization_record.payload
        separation = self.separation_policy_record.payload
        validator_identity = self.validator_identity_record.payload
        evaluation = self.evaluation_record.payload
        validator_identity_digest = self.validator_identity_record.digest()
        if (
            assignment["gate_digest"] != self.gate_record.digest()
            or assignment["authorization_policy_digest"]
            != self.attestation_authorization_record.digest()
            or assignment["separation_policy_digest"]
            != self.separation_policy_record.digest()
            or gate["validator_digest"] != validator_identity_digest
            or gate["attestation_authorization_digest"]
            != self.attestation_authorization_record.digest()
            or validator_identity["identity_type"] not in {"principal", "validator"}
            or attestation_authorization["subject_kind"] != "gate"
            or attestation_authorization["action"] != "attest_gate"
            or attestation_authorization["separation_policy_digest"]
            != self.separation_policy_record.digest()
            or validator_identity_digest
            in separation["forbidden_actor_identity_digests"]
            or not _authorization_admits_identity(
                self.attestation_authorization_record,
                self.separation_policy_record,
                self.validator_identity_record,
                action="attest_gate",
                subject_kind="gate",
            )
        ):
            raise ValueError(
                "gate evidence does not bind its validator authorization and separation policy"
            )
        if (
            assignment["validity_policy_digest"]
            != self.validity_policy_record.digest()
            or assignment["invalidation_policy_digest"]
            != self.invalidation_policy_record.digest()
            or assignment["dependency_projection_digest"]
            != self.evaluated_dependency_projection_record.digest()
        ):
            raise ValueError(
                "gate evidence does not bind its validity, invalidation, and dependency policies"
            )
        attempt_started_at = parse_canonical_timestamp(
            self.attempt_record.payload["started_at"]
        )
        evaluated_at = parse_canonical_timestamp(evaluation["evaluated_at"])
        if evaluated_at < attempt_started_at:
            raise ValueError("evaluation cannot precede attempt start")
        context_digest = self.context_record.digest()
        assignment_digest = self.assignment_record.digest()
        if self.attempt_record.payload["assignment_digest"] != assignment_digest:
            raise ValueError("attempt does not bind assignment")
        if self.attempt_record.payload["context_digest"] != context_digest:
            raise ValueError("attempt does not bind validation context")
        if (
            self.attempt_record.payload["actor_identity_digest"]
            != validator_identity_digest
        ):
            raise ValueError("attempt does not bind the authorized gate validator")
        if evaluation["assignment_digest"] != assignment_digest:
            raise ValueError("evaluation does not bind assignment")
        if evaluation["context_digest"] != context_digest:
            raise ValueError("evaluation does not bind validation context")
        if (
            evaluation["dependency_projection_digest"]
            != assignment["dependency_projection_digest"]
        ):
            raise ValueError("evaluation does not bind assignment dependency projection")

        applicability = evaluation["applicability"]
        attestation_records = tuple(
            evidence for evidence in evidence_records if evidence.kind == "attestation"
        )
        predicate_proof_records = tuple(
            evidence
            for evidence in evidence_records
            if evidence.kind == "predicate_proof"
        )
        if len(attestation_records) + len(predicate_proof_records) != len(
            evidence_records
        ):
            raise ValueError(
                "evaluation evidence must be attestations or one predicate proof"
            )
        conditional = assignment["applicability"] == "conditional"
        unknown_reason = evaluation.get("unknown_reason")
        predicate_proof: ControlRecord | None = None
        if conditional:
            predicate_authorization = _record(
                self.predicate_authorization_record,
                field="predicate_authorization_record",
                kind="authorization",
            )
            if (
                gate.get("predicate_authorization_digest")
                != predicate_authorization.digest()
                or predicate_authorization.payload["separation_policy_digest"]
                != self.separation_policy_record.digest()
            ):
                raise ValueError(
                    "predicate authorization does not bind the gate separation policy"
                )
            proof_required = (
                applicability in {"applicable", "not_applicable"}
                or unknown_reason == "applicability_proof_mismatch"
                or unknown_reason in _POST_PROOF_UNKNOWN_REASONS
            )
            if len(predicate_proof_records) != int(proof_required):
                if applicability in {"applicable", "not_applicable"}:
                    raise ValueError(
                        "conditional evaluation requires one current predicate proof"
                    )
                raise ValueError(
                    "conditional evaluation does not bind its exact predicate-proof provenance"
                )
            if proof_required:
                predicate_proof = predicate_proof_records[0]
                proof = predicate_proof.payload
                proof_authorized = _authorization_admits_actor(
                    predicate_authorization,
                    self.separation_policy_record,
                    self.validator_identity_record,
                    actor_identity_digest=proof["actor_identity_digest"],
                    actor_role=proof["actor_role"],
                    action="evaluate_gate_predicate",
                )
                proof_matches = proof_authorized and _proof_matches_assignment(
                    proof,
                    assignment,
                    assignment_digest=assignment_digest,
                    context_digest=context_digest,
                )
                if unknown_reason == "applicability_proof_mismatch":
                    if proof_matches:
                        raise ValueError(
                            "applicability-proof mismatch reason does not match its exact proof"
                        )
                else:
                    if not proof_authorized:
                        raise ValueError(
                            "predicate proof actor is not authorized by the gate separation policy"
                        )
                    if not proof_matches:
                        if proof["predicate_digest"] != assignment["predicate_digest"]:
                            raise ValueError(
                                "predicate proof does not bind assignment predicate"
                            )
                        for field in (
                            "assignment_digest",
                            "context_digest",
                            "dependency_projection_digest",
                            "gate_digest",
                            "subject_digest",
                        ):
                            expected = (
                                assignment_digest
                                if field == "assignment_digest"
                                else context_digest
                                if field == "context_digest"
                                else assignment[field]
                            )
                            if proof[field] != expected:
                                raise ValueError(
                                    f"predicate proof does not bind assignment {field}"
                                )
                proof_observed_at = parse_canonical_timestamp(proof["observed_at"])
                if proof_observed_at < attempt_started_at:
                    raise ValueError("predicate observation cannot precede attempt start")
                if proof_observed_at > evaluated_at:
                    raise ValueError("evaluation cannot precede predicate proof")
                if (
                    evaluation.get("predicate_proof_digest")
                    != predicate_proof.digest()
                ):
                    raise ValueError("evaluation does not bind predicate proof")
        elif unknown_reason in {
            "applicability_proof_mismatch",
            "missing_applicability_proof",
        }:
            raise ValueError(
                "unconditional evaluation cannot claim applicability-proof provenance"
            )
        elif (
            predicate_proof_records
            or self.predicate_authorization_record is not None
            or "predicate_proof_digest" in evaluation
        ):
            raise ValueError("unconditional evaluation cannot bind a predicate proof")

        if applicability == "applicable":
            if not attestation_records:
                raise ValueError("applicable evaluation requires attestations")
            if conditional and not predicate_proof.payload["is_applicable"]:
                raise ValueError("applicable predicate proof must prove true")
            for evidence in attestation_records:
                payload = evidence.payload
                for field in (
                    "assignment_digest",
                    "context_digest",
                    "dependency_projection_digest",
                    "gate_digest",
                    "subject_digest",
                ):
                    expected = (
                        assignment_digest
                        if field == "assignment_digest"
                        else context_digest
                        if field == "context_digest"
                        else assignment[field]
                    )
                    if payload[field] != expected:
                        raise ValueError(f"attestation does not bind assignment {field}")
                if payload["outcome"] != evaluation["outcome"]:
                    raise ValueError("evaluation outcome does not match attestation")
                if not _authorization_admits_actor(
                    self.attestation_authorization_record,
                    self.separation_policy_record,
                    self.validator_identity_record,
                    actor_identity_digest=payload["actor_identity_digest"],
                    actor_role=payload["actor_role"],
                    action="attest_gate",
                ):
                    raise ValueError(
                        "attestation actor is not authorized by the gate separation policy"
                    )
                if parse_canonical_timestamp(
                    payload["observed_at"]
                ) < attempt_started_at:
                    raise ValueError("attestation observation cannot precede attempt start")
                if parse_canonical_timestamp(payload["observed_at"]) > evaluated_at:
                    raise ValueError("evaluation cannot precede an attestation")
            if tuple(evaluation["attestation_digests"]) != tuple(
                item.digest() for item in attestation_records
            ):
                raise ValueError("evaluation does not bind exact attestation set")
        elif applicability == "not_applicable":
            if attestation_records or predicate_proof is None:
                raise ValueError("not-applicable evaluation requires one predicate proof")
            if not conditional:
                raise ValueError("unconditional assignment cannot be non-applicable")
            if predicate_proof.payload["is_applicable"]:
                raise ValueError("not-applicable predicate proof must prove false")
        elif applicability == "applicable_unknown":
            if unknown_reason == "missing_applicability_proof":
                if evidence_records:
                    raise ValueError(
                        "missing-evidence unknown reason does not match its assignment provenance"
                    )
            elif unknown_reason == "missing_attestation":
                if attestation_records or len(predicate_proof_records) != int(
                    conditional
                ):
                    raise ValueError(
                        "missing-attestation reason does not bind its exact applicability proof"
                    )
                if conditional and not predicate_proof.payload["is_applicable"]:
                    raise ValueError(
                        "missing-attestation predicate proof must prove true"
                    )
            elif unknown_reason == "applicability_proof_mismatch":
                if not conditional or predicate_proof is None or attestation_records:
                    raise ValueError(
                        "applicability-proof mismatch requires its exact predicate proof"
                    )
            elif unknown_reason in _ATTESTATION_UNKNOWN_REASONS:
                if len(attestation_records) != 1 or len(
                    predicate_proof_records
                ) != int(conditional):
                    raise ValueError(
                        "attestation-derived unknown reason requires one exact attestation"
                    )
                if conditional and not predicate_proof.payload["is_applicable"]:
                    raise ValueError(
                        "attestation-derived predicate proof must prove true"
                    )
                attestation = attestation_records[0]
                actual_reason = _attestation_unknown_reason(
                    attestation,
                    assignment=assignment,
                    assignment_digest=assignment_digest,
                    context_digest=context_digest,
                    authorization_record=self.attestation_authorization_record,
                    separation_policy_record=self.separation_policy_record,
                    validator_identity_record=self.validator_identity_record,
                )
                if actual_reason != unknown_reason:
                    raise ValueError(
                        "unknown reason does not match its exact attestation provenance"
                    )
                observed_at = parse_canonical_timestamp(
                    attestation.payload["observed_at"]
                )
                if not attempt_started_at <= observed_at <= evaluated_at:
                    raise ValueError(
                        "unknown attestation must fall between attempt and evaluation"
                    )
                if tuple(evaluation["attestation_digests"]) != (
                    attestation.digest(),
                ):
                    raise ValueError(
                        "unknown evaluation does not bind its exact attestation"
                    )
            else:
                raise ValueError("applicable-unknown evaluation has no canonical reason")
        elif evidence_records:
            raise ValueError("not-due evaluation cannot bind terminal evidence")

        context = self.context_record.payload
        if context["context_type"] == "active_contract":
            if self.inclusion_edge_record is not None:
                raise ValueError("active evidence cannot claim a preassembly inclusion edge")
        else:
            edge = _record(
                self.inclusion_edge_record,
                field="inclusion_edge_record",
                kind="inclusion_edge",
            )
            edge_payload = edge.payload
            expected = {
                "preassembly_context_digest": context_digest,
                "preassembly_profile_digest": context["profile_digest"],
                "source_closure_digest": context["source_closure_digest"],
                "artifact_digests": tuple(context["artifact_digests"]),
            }
            for field, value in expected.items():
                actual = (
                    tuple(edge_payload[field])
                    if field == "artifact_digests"
                    else edge_payload[field]
                )
                if actual != value:
                    raise ValueError(f"inclusion edge does not bind exact {field}")
            if assignment_digest not in edge_payload["assignment_digests"]:
                raise ValueError("inclusion edge does not bind assignment")
            if (
                self.evaluation_record.digest()
                not in edge_payload["preassembly_evaluation_digests"]
            ):
                raise ValueError("inclusion edge does not bind evaluation")
            if parse_canonical_timestamp(edge_payload["verified_at"]) < evaluated_at:
                raise ValueError(
                    "inclusion edge verification cannot precede its evaluation"
                )
        expected_currency_proof = {
            "evaluated_dependency_projection_digest": (
                self.evaluated_dependency_projection_record.digest()
            ),
            "evaluation_digest": self.evaluation_record.digest(),
            "inclusion_edge_digests": (
                (self.inclusion_edge_record.digest(),)
                if self.inclusion_edge_record is not None
                else ()
            ),
            "invalidation_policy_digest": self.invalidation_policy_record.digest(),
            "invalidation_stream_checkpoint_digest": (
                self.invalidation_stream_checkpoint_record.digest()
            ),
            "trusted_time_observation_digest": (
                self.trusted_time_observation_record.digest()
            ),
            "validity_policy_digest": self.validity_policy_record.digest(),
        }
        if any(
            (
                tuple(currency_proof[field])
                if field.endswith("_digests")
                else currency_proof[field]
            )
            != value
            for field, value in expected_currency_proof.items()
        ):
            raise ValueError("currency proof does not bind exact evaluation material")
        if (
            stream_checkpoint["invalidation_policy_digest"]
            != self.invalidation_policy_record.digest()
            or stream_checkpoint["current_dependency_projection_digest"]
            != self.current_dependency_projection_record.digest()
            or trusted_time["authority_head_digest"]
            != stream_checkpoint["authority_head_digest"]
        ):
            raise ValueError(
                "currency proof does not bind one authority-backed invalidation view"
            )
        trusted_at = parse_canonical_timestamp(trusted_time["observed_at"])
        if parse_canonical_timestamp(stream_checkpoint["checkpointed_at"]) > trusted_at:
            raise ValueError("trusted time cannot precede the invalidation checkpoint")
        if not self.structural_currency_current:
            raise ValueError("canonical evidence is stale under its currency proof")

    @property
    def assignment_digest(self) -> str:
        return self.assignment_record.digest()

    @property
    def attempt_digest(self) -> str:
        return self.attempt_record.digest()

    @property
    def evaluation_record_digest(self) -> str:
        return self.evaluation_record.digest()

    @property
    def structural_admissibility(self) -> bool:
        """Shape/currentness result whose proof provenance remains nonauthoritative."""

        evaluation = self.evaluation_record.payload
        return self.structural_currency_current and evaluation["applicability"] in {
            "applicable",
            "not_applicable",
        }

    @property
    def structural_currency_current(self) -> bool:
        """Derive freshness from materialized policy, projection, stream, and time."""

        trusted_at = parse_canonical_timestamp(
            self.trusted_time_observation_record.payload["observed_at"]
        )
        return self._currency_current_at(trusted_at)

    def _currency_current_at(self, current_at: datetime) -> bool:
        """Recompute bound dependency and evidence currency at one later boundary."""

        invalidation_keys = tuple(
            self.invalidation_policy_record.payload["dependency_keys"]
        )
        evaluated = dict(
            zip(
                self.evaluated_dependency_projection_record.payload[
                    "dependency_keys"
                ],
                self.evaluated_dependency_projection_record.payload[
                    "dependency_digests"
                ],
                strict=True,
            )
        )
        current = dict(
            zip(
                self.current_dependency_projection_record.payload["dependency_keys"],
                self.current_dependency_projection_record.payload[
                    "dependency_digests"
                ],
                strict=True,
            )
        )
        if any(
            key not in evaluated
            or key not in current
            or evaluated[key] != current[key]
            for key in invalidation_keys
        ):
            return False
        policy = self.validity_policy_record.payload
        constituents = [
            (
                (
                    "predicate_proof_max_age_seconds"
                    if evidence.kind == "predicate_proof"
                    else "attestation_max_age_seconds"
                ),
                parse_canonical_timestamp(evidence.payload["observed_at"]),
            )
            for evidence in self.evidence_records
        ]
        if self.inclusion_edge_record is not None:
            constituents.append(
                (
                    "inclusion_edge_max_age_seconds",
                    parse_canonical_timestamp(
                        self.inclusion_edge_record.payload["verified_at"]
                    ),
                )
            )
        return all(
            observed_at <= current_at
            and (
                max_age_field not in policy
                or current_at
                <= observed_at + timedelta(seconds=policy[max_age_field])
            )
            for max_age_field, observed_at in constituents
        )


def registration_set_digest(
    attempts: tuple[RegisteredAttempt, ...],
    operations: tuple[RegisteredOperation, ...] = (),
) -> str:
    """Bind the complete canonical gate and critical-operation registration set."""

    attempts = tuple(attempts)
    operations = tuple(operations)
    material = bytearray(b"arch-strix-halo/promotion-registration-set/v3\x00")
    for attempt in sorted(attempts, key=lambda item: item.obligation_digest):
        if not isinstance(attempt, RegisteredAttempt):
            raise TypeError("attempts must contain RegisteredAttempt values")
        for record in (
            attempt.obligation_record,
            attempt.intent_record,
            attempt.attempt_record,
            attempt.terminal_record,
        ):
            material.extend(record.digest().encode("ascii"))
            material.extend(b"\x00")
    for operation in sorted(operations, key=lambda item: item.operation_digest):
        if not isinstance(operation, RegisteredOperation):
            raise TypeError("operations must contain RegisteredOperation values")
        for record in (
            operation.intent_record,
            operation.operation_record,
            operation.capability_record,
            *operation.validator_attestation_records,
            operation.terminal_record,
        ):
            material.extend(record.digest().encode("ascii"))
            material.extend(b"\x00")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _materialized_operation_graph(
    operations: tuple[RegisteredOperation, ...],
) -> tuple[RegisteredOperation, ...]:
    materialized: list[RegisteredOperation] = []
    by_terminal: dict[str, RegisteredOperation] = {}
    active: set[int] = set()

    def visit(operation: RegisteredOperation) -> None:
        identity = id(operation)
        if identity in active:
            raise ValueError("recovery predecessor graph contains a cycle")
        active.add(identity)
        try:
            predecessor = operation.recovery_predecessor_operation
            if predecessor is not None:
                visit(predecessor)
            existing = by_terminal.get(operation.terminal_digest)
            if existing is not None:
                if not _canonical_graph_equivalent(existing, operation):
                    raise ValueError(
                        "atomic cut contains inconsistent duplicate operation material"
                    )
                return
            by_terminal[operation.terminal_digest] = operation
            materialized.append(operation)
        finally:
            active.remove(identity)

    for operation in operations:
        visit(operation)
    return tuple(materialized)


@dataclass(frozen=True, slots=True)
class AtomicEvidenceCut:
    """Canonical contents of one structurally complete evidence cut."""

    cut_record: ControlRecord
    accepted_generation_record: ControlRecord
    active_generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    attempts: tuple[RegisteredAttempt, ...]
    evaluations: tuple[BoundEvaluation, ...]
    inclusion_edge_records: tuple[ControlRecord, ...] = ()
    operations: tuple[RegisteredOperation, ...] = ()
    validator_attestation_records: tuple[ControlRecord, ...] = ()
    observation_records: tuple[ControlRecord, ...] = ()

    def __post_init__(self) -> None:
        _record(self.cut_record, field="cut_record", kind="atomic_evidence_cut")
        _record(
            self.accepted_generation_record,
            field="accepted_generation_record",
            kind="generation",
        )
        _record(
            self.active_generation_record,
            field="active_generation_record",
            kind="generation",
        )
        _record(self.target_record, field="target_record", kind="identity")
        _record(
            self.target_protected_state_record,
            field="target_protected_state_record",
            kind="protected_state",
        )
        attempts = tuple(self.attempts)
        evaluations = tuple(self.evaluations)
        edges = tuple(self.inclusion_edge_records)
        operations = tuple(self.operations)
        validator_attestations = tuple(self.validator_attestation_records)
        observations = tuple(self.observation_records)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "inclusion_edge_records", edges)
        object.__setattr__(self, "operations", operations)
        object.__setattr__(
            self,
            "validator_attestation_records",
            validator_attestations,
        )
        object.__setattr__(self, "observation_records", observations)
        if any(not isinstance(item, RegisteredAttempt) for item in attempts):
            raise TypeError("attempts must contain RegisteredAttempt values")
        if any(not isinstance(item, BoundEvaluation) for item in evaluations):
            raise TypeError("evaluations must contain BoundEvaluation values")
        for edge in edges:
            _record(edge, field="inclusion_edge_records item", kind="inclusion_edge")
        if any(not isinstance(item, RegisteredOperation) for item in operations):
            raise TypeError("operations must contain RegisteredOperation values")
        for attestation_record in validator_attestations:
            _record(
                attestation_record,
                field="validator_attestation_records item",
                kind="operation_attestation",
            )
        for observation_record in observations:
            observation_record = _any_record(
                observation_record,
                field="observation_records item",
            )
            if observation_record.kind not in {
                "backend_provenance",
                "readiness",
                "service_health_observation",
            }:
                raise ValueError(
                    "atomic cut contains unsupported typed service observation"
                )
        expected_validator_attestations = tuple(
            attestation_record.digest()
            for operation in operations
            for attestation_record in operation.validator_attestation_records
        )
        if tuple(item.digest() for item in validator_attestations) != (
            expected_validator_attestations
        ):
            raise ValueError(
                "atomic cut does not bind exact operation validator attestations"
            )
        payload = self.cut_record.payload
        expected = {
            "accepted_generation_digest": self.accepted_generation_record.digest(),
            "active_generation_digest": self.active_generation_record.digest(),
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": self.target_protected_state_record.digest(),
            "attempt_digests": tuple(item.attempt_digest for item in attempts),
            "evaluation_digests": tuple(
                item.evaluation_record_digest for item in evaluations
            ),
            "currency_proof_digests": tuple(
                item.currency_proof_record.digest() for item in evaluations
            ),
            "inclusion_edge_digests": tuple(item.digest() for item in edges),
            "operation_digests": tuple(item.operation_digest for item in operations),
            "operation_terminal_digests": tuple(
                item.terminal_digest for item in operations
            ),
            "capability_digests": tuple(
                item.capability_digest for item in operations
            ),
            "observation_digests": tuple(item.digest() for item in observations),
            "registration_set_digest": registration_set_digest(attempts, operations),
        }
        for field, value in expected.items():
            actual = tuple(payload[field]) if field.endswith("_digests") else payload[field]
            if actual != value:
                raise ValueError(f"atomic cut does not bind exact {field}")
        state = self.target_protected_state_record.payload
        if state["target_digest"] != self.target_record.digest():
            raise ValueError("cut protected state does not bind target")
        if state["generation_digest"] != payload["generation_digest"]:
            raise ValueError("cut protected state does not bind candidate generation")
        journal_events: list[tuple[int, datetime]] = []
        for attempt in attempts:
            journal_events.extend(
                (
                    (
                        attempt.intent_record.payload["journal_sequence"],
                        parse_canonical_timestamp(
                            attempt.intent_record.payload["registered_at"]
                        ),
                    ),
                    (
                        attempt.attempt_record.payload["journal_sequence"],
                        parse_canonical_timestamp(
                            attempt.attempt_record.payload["started_at"]
                        ),
                    ),
                    (
                        attempt.terminal_record.payload["journal_sequence"],
                        parse_canonical_timestamp(
                            attempt.terminal_record.payload["completed_at"]
                        ),
                    ),
                )
            )
        for operation in _materialized_operation_graph(operations):
            journal_events.extend(
                (
                    (
                        operation.intent_record.payload["journal_sequence"],
                        parse_canonical_timestamp(
                            operation.intent_record.payload["registered_at"]
                        ),
                    ),
                    (
                        operation.terminal_record.payload["journal_sequence"],
                        parse_canonical_timestamp(
                            operation.terminal_record.payload["completed_at"]
                        ),
                    ),
                )
            )
        sequences = tuple(sequence for sequence, _ in journal_events)
        if (
            any(sequence <= 0 for sequence in sequences)
            or len(sequences) != len(set(sequences))
            or any(
                sequence > payload["complete_through_sequence"]
                for sequence in sequences
            )
        ):
            raise ValueError(
                "atomic cut journal sequences must be positive, globally unique, and complete"
            )
        ordered_event_times = tuple(
            event_time for _, event_time in sorted(journal_events)
        )
        if tuple(sorted(ordered_event_times)) != ordered_event_times:
            raise ValueError("atomic cut journal time contradicts sequence order")
        service_scenarios = sorted(
            (
                operation
                for operation in operations
                if operation.operation_record.payload["operation_kind"]
                == CriticalOperationKind.BLOCKING_SCENARIO.value
                and operation.operation_record.payload["target_kind"]
                == OperationTargetKind.SERVICE.value
            ),
            key=lambda operation: operation.intent_record.payload[
                "journal_sequence"
            ],
        )
        previous_by_target: dict[str, RegisteredOperation] = {}
        for operation in service_scenarios:
            target_digest = operation.target_record.digest()
            previous = previous_by_target.get(target_digest)
            if previous is not None and (
                operation.expected_protected_state_record.digest()
                != previous.intended_protected_state_record.digest()
                or previous.terminal_sequence
                >= operation.intent_record.payload["journal_sequence"]
                or parse_canonical_timestamp(
                    previous.terminal_record.payload["completed_at"]
                )
                > parse_canonical_timestamp(
                    operation.intent_record.payload["registered_at"]
                )
            ):
                raise ValueError(
                    "service scenarios on one target must consume the prior exact terminal poststate"
                )
            previous_by_target[target_digest] = operation
        observed_at = parse_canonical_timestamp(payload["observed_at"])
        latest_material = _latest_cut_evidence_timestamp(self)
        if observed_at < latest_material:
            raise ValueError("atomic cut observation cannot precede its evidence")
        attempt_by_digest = {
            attempt.attempt_digest: attempt for attempt in attempts
        }
        latest_terminal_at = max(
            parse_canonical_timestamp(item.terminal_record.payload["completed_at"])
            for item in (*attempts, *operations)
        )
        for evaluation in evaluations:
            stream = evaluation.invalidation_stream_checkpoint_record.payload
            trusted = evaluation.trusted_time_observation_record.payload
            registered_attempt = attempt_by_digest.get(evaluation.attempt_digest)
            if (
                registered_attempt is None
                or stream["authority_head_digest"] != payload["authority_head_digest"]
                or stream["authority_manifest_digest"]
                != payload["authority_manifest_digest"]
                or stream["completeness_proof_digest"]
                != payload["completeness_proof_digest"]
                or stream["fork_proof_digest"] != payload["fork_proof_digest"]
                or stream["complete_through_sequence"]
                != payload["complete_through_sequence"]
                or trusted["authority_head_digest"] != payload["authority_head_digest"]
            ):
                raise ValueError(
                    "atomic cut currency proof does not bind its exact authority view"
                )
            checkpointed_at = parse_canonical_timestamp(stream["checkpointed_at"])
            if not latest_terminal_at <= checkpointed_at <= observed_at:
                raise ValueError(
                    "invalidation checkpoint must certify the exact cut after every terminal"
                )
            max_age = evaluation.validity_policy_record.payload.get(
                "evidence_cut_max_age_seconds"
            )
            trusted_at = parse_canonical_timestamp(trusted["observed_at"])
            if trusted_at < observed_at or (
                max_age is not None
                and trusted_at > observed_at + timedelta(seconds=max_age)
            ):
                raise ValueError("atomic cut is stale under its trusted time proof")

    @property
    def cut_record_digest(self) -> str:
        return self.cut_record.digest()

    @property
    def phase(self) -> PromotionPhase:
        return PromotionPhase(self.cut_record.payload["phase"])


def _validate_admission_currentness(
    cut: AtomicEvidenceCut,
    *,
    boundary: datetime,
) -> None:
    """Require every bound evaluation and its cut to remain current."""

    cut_observed_at = parse_canonical_timestamp(
        cut.cut_record.payload["observed_at"]
    )
    for evaluation in cut.evaluations:
        policy = evaluation.validity_policy_record.payload
        cut_max_age = policy.get("evidence_cut_max_age_seconds")
        if not evaluation._currency_current_at(boundary) or (
            cut_max_age is not None
            and boundary
            > cut_observed_at + timedelta(seconds=cut_max_age)
        ):
            raise ValueError(
                "promotion evidence is not current at issuance boundary"
            )


@dataclass(frozen=True, slots=True)
class BaselineRestorationReceipt:
    """Exact W4 isolated qualification and live-root restoration receipt."""

    receipt_record: ControlRecord
    promotion_contract: PromotionContract
    captured_checkpoint: LifecycleCheckpoint | StructuralBaselineCapture
    target_record: ControlRecord
    isolated_install_operation: RegisteredOperation
    phase_establishing_operation_obligation: OperationObligation
    live_prestate_protected_state_record: ControlRecord
    rehearsal_install_operation: RegisteredOperation
    rollback_record: ControlRecord
    restoration_operation: RegisteredOperation
    smoke_attempt: RegisteredAttempt
    smoke_evaluation: BoundEvaluation
    smoke_contract_record: ControlRecord
    evidence_cut: AtomicEvidenceCut

    def __post_init__(self) -> None:
        receipt = _record(
            self.receipt_record,
            field="receipt_record",
            kind="baseline_restoration_receipt",
        ).payload
        target = _record(
            self.target_record,
            field="target_record",
            kind="identity",
        )
        live_prestate = _record(
            self.live_prestate_protected_state_record,
            field="live_prestate_protected_state_record",
            kind="protected_state",
        )
        rollback = _record(
            self.rollback_record,
            field="rollback_record",
            kind="rollback",
        ).payload
        smoke_contract = _record(
            self.smoke_contract_record,
            field="smoke_contract_record",
            kind="restored_baseline_smoke_contract",
        ).payload
        if not isinstance(self.promotion_contract, PromotionContract):
            raise TypeError("baseline restoration receipt requires its W4 contract")
        if not isinstance(
            self.captured_checkpoint,
            (LifecycleCheckpoint, StructuralBaselineCapture),
        ):
            raise TypeError("captured_checkpoint must be captured B0 lifecycle material")
        if (
            not isinstance(self.isolated_install_operation, RegisteredOperation)
            or not isinstance(
                self.phase_establishing_operation_obligation,
                OperationObligation,
            )
            or not isinstance(self.rehearsal_install_operation, RegisteredOperation)
            or not isinstance(self.restoration_operation, RegisteredOperation)
            or not isinstance(self.smoke_attempt, RegisteredAttempt)
            or not isinstance(self.smoke_evaluation, BoundEvaluation)
            or not isinstance(self.evidence_cut, AtomicEvidenceCut)
        ):
            raise TypeError("baseline restoration receipt material is incomplete")
        captured_record = self.captured_checkpoint.checkpoint_record.payload
        captured_state_record = self.captured_checkpoint.target_protected_state_record
        captured_state = captured_state_record.payload
        isolated = self.isolated_install_operation
        rehearsal = self.rehearsal_install_operation
        restoration = self.restoration_operation
        isolated_expected = isolated.expected_protected_state_record.payload
        isolated_intended = isolated.intended_protected_state_record.payload
        rehearsal_intended_record = rehearsal.intended_protected_state_record
        rehearsal_intended = rehearsal_intended_record.payload
        restored_record = restoration.intended_protected_state_record
        restored = restored_record.payload
        smoke_terminal = self.smoke_attempt.terminal_record
        expected_receipt = {
            "candidate_live_protected_state_digest": rehearsal_intended_record.digest(),
            "captured_checkpoint_digest": self.captured_checkpoint.checkpoint_digest,
            "captured_generation_digest": self.captured_checkpoint.generation_record.digest(),
            "captured_protected_state_digest": captured_state_record.digest(),
            "isolated_install_operation_digest": isolated.operation_digest,
            "isolated_install_operation_terminal_digest": isolated.terminal_digest,
            "live_prestate_protected_state_digest": live_prestate.digest(),
            "post_restoration_gate_terminal_digest": smoke_terminal.digest(),
            "post_restoration_smoke_attempt_digest": self.smoke_attempt.attempt_digest,
            "post_restoration_smoke_evaluation_digest": self.smoke_evaluation.evaluation_record_digest,
            "phase_establishing_operation_obligation_digest": (
                self.phase_establishing_operation_obligation.obligation_digest
            ),
            "post_restoration_smoke_contract_digest": (
                self.smoke_contract_record.digest()
            ),
            "prevalidated_promotion_contract_digest": (
                self.promotion_contract.contract_digest
            ),
            "rehearsal_install_operation_digest": rehearsal.operation_digest,
            "rehearsal_install_operation_terminal_digest": rehearsal.terminal_digest,
            "restoration_evidence_cut_digest": self.evidence_cut.cut_record_digest,
            "restoration_operation_digest": restoration.operation_digest,
            "restoration_operation_terminal_digest": restoration.terminal_digest,
            "restored_generation_digest": restored["generation_digest"],
            "restored_fence_epoch": restored["fence_epoch"],
            "restored_projection_digest": rollback[
                "target_projection_digest"
            ],
            "restored_protected_state_digest": restored_record.digest(),
            "rollback_digest": self.rollback_record.digest(),
            "target_digest": target.digest(),
        }
        if any(receipt[field] != value for field, value in expected_receipt.items()):
            raise ValueError(
                "baseline restoration receipt does not bind its exact W4 material"
            )
        if (
            (captured_record["generation_class"], captured_record["phase"])
            != (GenerationClass.B0.value, LifecyclePhase.CAPTURED.value)
            or target.payload["identity_type"] != "target"
            or captured_record["target_digest"] != target.digest()
            or self.evidence_cut.phase is not PromotionPhase.PREVALIDATED
            or self.promotion_contract.phase is not PromotionPhase.PREVALIDATED
            or self.evidence_cut.cut_record.payload["contract_digest"]
            != self.promotion_contract.contract_digest
            or self.phase_establishing_operation_obligation.operation_digest
            != isolated.operation_digest
            or self.promotion_contract.contract_record.payload[
                "phase_establishing_operation_obligation_digest"
            ]
            != self.phase_establishing_operation_obligation.obligation_digest
            or not _canonical_graph_contains_once(
                self.evidence_cut.operations,
                isolated,
            )
            or not _canonical_graph_contains_once(
                self.evidence_cut.operations,
                rehearsal,
            )
            or not _canonical_graph_contains_once(
                self.evidence_cut.operations,
                restoration,
            )
            or not _canonical_graph_contains_once(
                self.evidence_cut.attempts,
                self.smoke_attempt,
            )
            or not _canonical_graph_contains_once(
                self.evidence_cut.evaluations,
                self.smoke_evaluation,
            )
            or self.smoke_evaluation.attempt_digest
            != self.smoke_attempt.attempt_digest
        ):
            raise ValueError("baseline restoration receipt is not rooted in the exact W4 cut")
        isolated_payload = isolated.operation_record.payload
        rehearsal_payload = rehearsal.operation_record.payload
        restoration_payload = restoration.operation_record.payload
        if (
            (
                isolated_payload["operation_kind"],
                isolated_payload["target_kind"],
                isolated_payload["lifecycle_phase"],
            )
            != (
                CriticalOperationKind.PACKAGE_INSTALLATION.value,
                OperationTargetKind.ISOLATED_ROOT.value,
                PromotionPhase.PREVALIDATED.value,
            )
            or isolated.target_record.digest() != target.digest()
            or isolated_expected["target_digest"] != target.digest()
            or isolated_expected["target_kind"]
            != OperationTargetKind.ISOLATED_ROOT.value
            or isolated_expected["generation_digest"]
            != captured_state["generation_digest"]
            or isolated_expected["projection_id"] != captured_state["projection_id"]
            or isolated_expected["state_digest"] != captured_state["state_digest"]
            or isolated_intended["generation_digest"]
            != self.evidence_cut.cut_record.payload["generation_digest"]
            or isolated_intended["target_kind"]
            != OperationTargetKind.ISOLATED_ROOT.value
            or isolated.terminal_record.payload["outcome"] != "succeeded"
        ):
            raise ValueError("W4 isolated installation is not rooted in captured B0")
        if (
            live_prestate.payload["target_digest"] != target.digest()
            or live_prestate.payload["target_kind"]
            != OperationTargetKind.LIVE_ROOT.value
            or live_prestate.payload["generation_digest"]
            != captured_state["generation_digest"]
            or live_prestate.payload["projection_id"] != captured_state["projection_id"]
            or live_prestate.payload["state_digest"] != captured_state["state_digest"]
            or (
                rehearsal_payload["operation_kind"],
                rehearsal_payload["target_kind"],
                rehearsal_payload["lifecycle_phase"],
            )
            != (
                CriticalOperationKind.PACKAGE_INSTALLATION.value,
                OperationTargetKind.LIVE_ROOT.value,
                PromotionPhase.ACTIVE.value,
            )
            or rehearsal.expected_protected_state_record.digest() != live_prestate.digest()
            or rehearsal.target_record.digest() != target.digest()
            or rehearsal_intended["generation_digest"]
            != self.evidence_cut.cut_record.payload["generation_digest"]
            or rehearsal_intended["target_kind"]
            != OperationTargetKind.LIVE_ROOT.value
            or rehearsal.terminal_record.payload["outcome"] != "succeeded"
        ):
            raise ValueError("W4 rehearsal installation does not bind the live B0 prestate")
        restoration_effects = {
            item["projection_digest"]
            for item in restoration_payload["declared_effects"]
        }
        if (
            (
                restoration_payload["operation_kind"],
                restoration_payload["target_kind"],
                restoration_payload["lifecycle_phase"],
            )
            != (
                CriticalOperationKind.ROLLBACK.value,
                OperationTargetKind.LIVE_ROOT.value,
                PromotionPhase.ACTIVE.value,
            )
            or restoration.expected_protected_state_record.digest()
            != rehearsal_intended_record.digest()
            or restoration.target_record.digest() != target.digest()
            or restored["generation_digest"] != captured_state["generation_digest"]
            or restored["target_kind"] != OperationTargetKind.LIVE_ROOT.value
            or restored["projection_id"] != live_prestate.payload["projection_id"]
            or restored["state_digest"] != live_prestate.payload["state_digest"]
            or restoration.terminal_record.payload["outcome"] != "succeeded"
            or rollback["operation_digest"] != restoration.operation_digest
            or rollback["generation_binding"].get("generation_digest")
            != self.evidence_cut.cut_record.payload["generation_digest"]
            or rollback["origin_generation_digest"]
            != self.evidence_cut.cut_record.payload["generation_digest"]
            or rollback["destination_generation_digest"]
            != captured_state["generation_digest"]
            or rollback["target_generation_digest"] != captured_state["generation_digest"]
            or rollback["target_digest"] != target.digest()
            or rollback["target_protected_state_digest"] != restored_record.digest()
            or rollback["target_state_digest"] != restored["state_digest"]
            or rollback["target_projection_digest"] not in restoration_effects
            or rollback["terminal_gate_digest"] != smoke_terminal.digest()
        ):
            raise ValueError("W4 restoration does not bind the exact rollback target")
        evaluation = self.smoke_evaluation.evaluation_record.payload
        expected_smoke_contract = {
            "assignment_digest": self.smoke_evaluation.assignment_record.digest(),
            "attestation_authorization_digest": (
                self.smoke_evaluation.attestation_authorization_record.digest()
            ),
            "expected_outcome": "pass",
            "gate_digest": self.smoke_evaluation.gate_record.digest(),
            "restored_protected_state_digest": restored_record.digest(),
            "target_digest": target.digest(),
            "validation_contract_digest": (
                self.promotion_contract.validation_contract_record.digest()
            ),
            "validator_digest": (
                self.smoke_evaluation.validator_identity_record.digest()
            ),
        }
        if (
            any(
                smoke_contract[field] != value
                for field, value in expected_smoke_contract.items()
            )
            or self.smoke_attempt.obligation_record.payload["assignment_digest"]
            != self.smoke_evaluation.assignment_record.digest()
            or smoke_terminal.payload["poststate_digest"]
            != restored_record.digest()
            or smoke_terminal.payload["outcome"] != "succeeded"
            or (evaluation["applicability"], evaluation["outcome"])
            != ("applicable", "pass")
        ):
            raise ValueError("W4 post-restoration smoke does not prove the restored state")
        sequence = (
            self.smoke_attempt.intent_record.payload["journal_sequence"],
            isolated.intent_record.payload["journal_sequence"],
            isolated.terminal_sequence,
            rehearsal.intent_record.payload["journal_sequence"],
            rehearsal.terminal_sequence,
            restoration.intent_record.payload["journal_sequence"],
            restoration.terminal_sequence,
            self.smoke_attempt.attempt_record.payload["journal_sequence"],
            self.smoke_attempt.terminal_sequence,
        )
        if tuple(sorted(sequence)) != sequence or len(set(sequence)) != len(sequence):
            raise ValueError("W4 restoration journal is not strictly ordered")
        chronology = (
            parse_canonical_timestamp(isolated.intent_record.payload["registered_at"]),
            parse_canonical_timestamp(isolated.terminal_record.payload["completed_at"]),
            parse_canonical_timestamp(rehearsal.intent_record.payload["registered_at"]),
            parse_canonical_timestamp(rehearsal.terminal_record.payload["completed_at"]),
            parse_canonical_timestamp(restoration.intent_record.payload["registered_at"]),
            parse_canonical_timestamp(restoration.terminal_record.payload["completed_at"]),
            parse_canonical_timestamp(self.smoke_attempt.attempt_record.payload["started_at"]),
            parse_canonical_timestamp(evaluation["evaluated_at"]),
            parse_canonical_timestamp(smoke_terminal.payload["completed_at"]),
            parse_canonical_timestamp(self.evidence_cut.cut_record.payload["observed_at"]),
        )
        if tuple(sorted(chronology)) != chronology:
            raise ValueError("W4 restoration chronology is not strictly causal")

    @property
    def receipt_digest(self) -> str:
        return self.receipt_record.digest()

    @property
    def restored_protected_state_record(self) -> ControlRecord:
        return self.restoration_operation.intended_protected_state_record


@dataclass(frozen=True, slots=True)
class ServiceAnchorReceipt:
    """Exact active-cut service state authorized for accepted closeout."""

    receipt_record: ControlRecord
    promotion_contract: PromotionContract
    evidence_cut: AtomicEvidenceCut
    target_record: ControlRecord
    service_protected_state_record: ControlRecord
    establishing_operation: RegisteredOperation
    active_phase_operation: RegisteredOperation
    backend_provenance_record: ControlRecord
    service_health_observation_records: tuple[ControlRecord, ...]
    readiness_record: ControlRecord
    observer_authorization_record: ControlRecord
    observer_separation_policy_record: ControlRecord
    observer_identity_record: ControlRecord

    def __post_init__(self) -> None:
        receipt = _record(
            self.receipt_record,
            field="receipt_record",
            kind="service_anchor_receipt",
        ).payload
        if not isinstance(self.promotion_contract, PromotionContract):
            raise TypeError("service anchor requires its active promotion contract")
        if not isinstance(self.evidence_cut, AtomicEvidenceCut):
            raise TypeError("service anchor requires its exact active evidence cut")
        if not isinstance(self.establishing_operation, RegisteredOperation):
            raise TypeError("service anchor requires its establishing operation")
        target = _record(
            self.target_record,
            field="target_record",
            kind="identity",
        )
        state = _record(
            self.service_protected_state_record,
            field="service_protected_state_record",
            kind="protected_state",
        ).payload
        backend = _record(
            self.backend_provenance_record,
            field="backend_provenance_record",
            kind="backend_provenance",
        ).payload
        readiness = _record(
            self.readiness_record,
            field="readiness_record",
            kind="readiness",
        ).payload
        authorization = _record(
            self.observer_authorization_record,
            field="observer_authorization_record",
            kind="authorization",
        )
        separation = _record(
            self.observer_separation_policy_record,
            field="observer_separation_policy_record",
            kind="separation_policy",
        )
        observer = _record(
            self.observer_identity_record,
            field="observer_identity_record",
            kind="identity",
        )
        health_records = tuple(self.service_health_observation_records)
        object.__setattr__(
            self,
            "service_health_observation_records",
            health_records,
        )
        if not health_records:
            raise ValueError("service anchor requires service health observations")
        for health_record in health_records:
            _record(
                health_record,
                field="service_health_observation_records item",
                kind="service_health_observation",
            )
        operation = self.establishing_operation
        active_operation = self.active_phase_operation
        if not isinstance(active_operation, RegisteredOperation):
            raise TypeError("service anchor requires its active phase operation")
        active_terminal_at = parse_canonical_timestamp(
            active_operation.terminal_record.payload["completed_at"]
        )
        service_prestate_at = parse_canonical_timestamp(
            operation.expected_protected_state_record.payload["observed_at"]
        )
        if (
            active_operation.terminal_sequence
            >= operation.intent_record.payload["journal_sequence"]
            or active_terminal_at >= service_prestate_at
        ):
            raise ValueError(
                "service anchor work cannot begin before the active phase installation is complete"
            )
        matching_obligations = [
            obligation
            for obligation in self.promotion_contract.operation_obligations
            if obligation.operation_digest == operation.operation_digest
            and obligation.requirement.requirement_record.payload["purpose"]
            == "service_anchor"
        ]
        expected = {
            "active_evidence_cut_digest": self.evidence_cut.cut_record_digest,
            "active_phase_operation_terminal_digest": (
                active_operation.terminal_digest
            ),
            "active_promotion_contract_digest": self.promotion_contract.contract_digest,
            "backend_provenance_digest": self.backend_provenance_record.digest(),
            "establishing_operation_digest": operation.operation_digest,
            "generation_digest": self.promotion_contract.generation_digest,
            "operation_terminal_digest": operation.terminal_digest,
            "process_epoch": state.get("process_epoch"),
            "readiness_digest": self.readiness_record.digest(),
            "service_protected_state_digest": self.service_protected_state_record.digest(),
            "target_digest": target.digest(),
        }
        if any(receipt[field] != value for field, value in expected.items()):
            raise ValueError("service anchor receipt does not bind its exact active material")
        if (
            self.promotion_contract.phase is not PromotionPhase.ACTIVE
            or self.evidence_cut.phase is not PromotionPhase.ACTIVE
            or self.evidence_cut.cut_record.payload["contract_digest"]
            != self.promotion_contract.contract_digest
            or len(matching_obligations) != 1
            or sum(
                _canonical_graph_equivalent(item, operation)
                for item in self.evidence_cut.operations
            )
            != 1
            or sum(
                _canonical_graph_equivalent(item, active_operation)
                for item in self.evidence_cut.operations
            )
            != 1
            or self.promotion_contract.contract_record.payload[
                "phase_establishing_operation_obligation_digest"
            ]
            not in {
                item.obligation_digest
                for item in self.promotion_contract.operation_obligations
                if item.operation_digest == active_operation.operation_digest
            }
            or target.payload["identity_type"] != "target"
            or operation.target_record.digest() != target.digest()
            or operation.intended_protected_state_record.digest()
            != self.service_protected_state_record.digest()
            or operation.operation_record.payload["operation_kind"]
            != CriticalOperationKind.BLOCKING_SCENARIO.value
            or operation.operation_record.payload["target_kind"]
            != OperationTargetKind.SERVICE.value
            or operation.operation_record.payload["lifecycle_phase"]
            != PromotionPhase.ACTIVE.value
            or operation.terminal_record.payload["outcome"] != "succeeded"
            or operation.terminal_record.payload["poststate_digest"]
            != self.service_protected_state_record.digest()
            or state["generation_digest"] != self.promotion_contract.generation_digest
            or state["target_digest"] != target.digest()
            or state["target_kind"] != OperationTargetKind.SERVICE.value
            or state["lifecycle_phase"] != PromotionPhase.ACTIVE.value
            or not isinstance(state.get("process_epoch"), str)
            or parse_canonical_timestamp(operation.terminal_record.payload["completed_at"])
            > parse_canonical_timestamp(self.evidence_cut.cut_record.payload["observed_at"])
        ):
            raise ValueError("service anchor is not established by one exact active-cut operation")

        process_epoch = state["process_epoch"]
        observation_digests = tuple(
            item.digest() for item in self.evidence_cut.observation_records
        )
        exact_observation_digests = (
            self.backend_provenance_record.digest(),
            *(item.digest() for item in health_records),
            self.readiness_record.digest(),
        )
        common = {
            "backend_provenance_digest": self.backend_provenance_record.digest(),
            "generation_digest": self.promotion_contract.generation_digest,
            "process_epoch": process_epoch,
            "service_protected_state_digest": (
                self.service_protected_state_record.digest()
            ),
            "target_digest": target.digest(),
        }
        if (
            readiness["backend_manifest_digest"]
            != backend["backend_manifest_digest"]
        ):
            raise ValueError(
                "service readiness does not bind its exact backend manifest"
            )
        if (
            observation_digests != exact_observation_digests
            or backend["authorization_digest"] != authorization.digest()
            or backend["observer_identity_digest"] != observer.digest()
            or any(backend[field] != value for field, value in common.items() if field != "backend_provenance_digest")
            or readiness["status"] != "ready"
            or any(readiness[field] != value for field, value in common.items())
            or tuple(readiness["service_health_observation_digests"])
            != tuple(item.digest() for item in health_records)
            or not _authorization_admits_identity(
                authorization,
                separation,
                observer,
                action="observe_service",
                subject_kind="protected_state",
            )
        ):
            raise ValueError(
                "service anchor observations do not bind one authorized process epoch"
            )
        for health_record in health_records:
            health = health_record.payload
            if (
                health["status"] != "ready"
                or health["authorization_digest"] != authorization.digest()
                or health["observer_identity_digest"] != observer.digest()
                or any(health[field] != value for field, value in common.items())
            ):
                raise ValueError(
                    "service anchor health does not bind its backend process epoch"
                )
        service_terminal_at = parse_canonical_timestamp(
            operation.terminal_record.payload["completed_at"]
        )
        backend_at = parse_canonical_timestamp(backend["observed_at"])
        health_times = tuple(
            parse_canonical_timestamp(item.payload["observed_at"])
            for item in health_records
        )
        readiness_at = parse_canonical_timestamp(readiness["observed_at"])
        cut_at = parse_canonical_timestamp(
            self.evidence_cut.cut_record.payload["observed_at"]
        )
        issued_at = parse_canonical_timestamp(receipt["issued_at"])
        expires_at = parse_canonical_timestamp(receipt["expires_at"])
        if (
            not (
                active_terminal_at
                < service_terminal_at
                <= backend_at
                <= min(health_times)
                <= max(health_times)
                <= readiness_at
                <= cut_at
                <= issued_at
                < expires_at
            )
            or expires_at - issued_at != timedelta(seconds=300)
            or cut_at - backend_at > timedelta(seconds=300)
            or issued_at - readiness_at > timedelta(seconds=300)
        ):
            raise ValueError("service anchor health lease is stale or noncausal")

    @property
    def receipt_digest(self) -> str:
        return self.receipt_record.digest()

    @property
    def generation_digest(self) -> str:
        return self.service_protected_state_record.payload["generation_digest"]


@dataclass(frozen=True, slots=True)
class FinalServiceAnchorReceipt:
    """Fresh post-cut service anchor established by the final restart."""

    receipt_record: ControlRecord
    promotion_contract: PromotionContract
    evidence_cut: AtomicEvidenceCut
    predecessor_service_anchor_receipt: ServiceAnchorReceipt
    final_restart_operation: RegisteredOperation
    target_record: ControlRecord
    service_protected_state_record: ControlRecord
    backend_provenance_record: ControlRecord
    service_health_observation_records: tuple[ControlRecord, ...]
    readiness_record: ControlRecord
    observer_authorization_record: ControlRecord
    observer_separation_policy_record: ControlRecord
    observer_identity_record: ControlRecord

    def __post_init__(self) -> None:
        receipt = _record(
            self.receipt_record,
            field="receipt_record",
            kind="final_service_anchor_receipt",
        ).payload
        if (
            not isinstance(self.promotion_contract, PromotionContract)
            or self.promotion_contract.phase is not PromotionPhase.ACCEPTED
            or not isinstance(self.evidence_cut, AtomicEvidenceCut)
            or self.evidence_cut.phase is not PromotionPhase.ACCEPTED
            or not isinstance(
                self.predecessor_service_anchor_receipt,
                ServiceAnchorReceipt,
            )
            or not isinstance(self.final_restart_operation, RegisteredOperation)
        ):
            raise TypeError(
                "final service anchor requires its accepted cut, predecessor anchor, and final restart"
            )
        target = _record(self.target_record, field="target_record", kind="identity")
        state_record = _record(
            self.service_protected_state_record,
            field="service_protected_state_record",
            kind="protected_state",
        )
        state = state_record.payload
        backend_record = _record(
            self.backend_provenance_record,
            field="backend_provenance_record",
            kind="backend_provenance",
        )
        backend = backend_record.payload
        readiness_record = _record(
            self.readiness_record,
            field="readiness_record",
            kind="readiness",
        )
        readiness = readiness_record.payload
        authorization = _record(
            self.observer_authorization_record,
            field="observer_authorization_record",
            kind="authorization",
        )
        separation = _record(
            self.observer_separation_policy_record,
            field="observer_separation_policy_record",
            kind="separation_policy",
        )
        observer = _record(
            self.observer_identity_record,
            field="observer_identity_record",
            kind="identity",
        )
        health_records = tuple(self.service_health_observation_records)
        object.__setattr__(
            self,
            "service_health_observation_records",
            health_records,
        )
        if not health_records:
            raise ValueError("final service anchor requires fresh service health")
        for health_record in health_records:
            _record(
                health_record,
                field="service_health_observation_records item",
                kind="service_health_observation",
            )
        operation = self.final_restart_operation
        matching_obligations = [
            obligation
            for obligation in self.promotion_contract.operation_obligations
            if obligation.operation_digest == operation.operation_digest
            and obligation.requirement.requirement_record.payload["purpose"]
            == "final_service_restart"
        ]
        expected = {
            "backend_provenance_digest": backend_record.digest(),
            "evidence_cut_digest": self.evidence_cut.cut_record_digest,
            "final_restart_operation_digest": operation.operation_digest,
            "final_restart_operation_terminal_digest": operation.terminal_digest,
            "generation_digest": self.promotion_contract.generation_digest,
            "predecessor_service_anchor_receipt_digest": (
                self.predecessor_service_anchor_receipt.receipt_digest
            ),
            "process_epoch": state.get("process_epoch"),
            "promotion_contract_digest": self.promotion_contract.contract_digest,
            "readiness_digest": readiness_record.digest(),
            "service_protected_state_digest": state_record.digest(),
            "target_digest": target.digest(),
        }
        if any(receipt[field] != value for field, value in expected.items()):
            raise ValueError(
                "final service anchor receipt does not bind its exact accepted material"
            )
        if (
            self.evidence_cut.cut_record.payload["contract_digest"]
            != self.promotion_contract.contract_digest
            or len(matching_obligations) != 1
            or sum(
                _canonical_graph_equivalent(item, operation)
                for item in self.evidence_cut.operations
            )
            != 1
            or not _canonical_graph_equivalent(
                self.evidence_cut.operations[-1],
                operation,
            )
            or operation.target_record.digest() != target.digest()
            or operation.intended_protected_state_record.digest()
            != state_record.digest()
            or operation.terminal_record.payload["outcome"] != "succeeded"
            or operation.terminal_record.payload["poststate_digest"]
            != state_record.digest()
            or state["generation_digest"] != self.promotion_contract.generation_digest
            or state["target_digest"] != target.digest()
            or state["target_kind"] != OperationTargetKind.SERVICE.value
            or state["lifecycle_phase"] != PromotionPhase.ACTIVE.value
            or not isinstance(state.get("process_epoch"), str)
            or state["process_epoch"]
            == operation.expected_protected_state_record.payload.get(
                "process_epoch"
            )
            or target.digest()
            != self.predecessor_service_anchor_receipt.target_record.digest()
            or not _canonical_graph_equivalent(
                self.predecessor_service_anchor_receipt,
                self.promotion_contract.service_anchor_receipt,
            )
            or self.promotion_contract.contract_record.payload[
                "predecessor_service_anchor_receipt_digest"
            ]
            != self.predecessor_service_anchor_receipt.receipt_digest
        ):
            raise ValueError(
                "final service anchor is not established by the exact final restart"
            )
        process_epoch = state["process_epoch"]
        common = {
            "generation_digest": self.promotion_contract.generation_digest,
            "process_epoch": process_epoch,
            "service_protected_state_digest": state_record.digest(),
            "target_digest": target.digest(),
        }
        predecessor_backend = (
            self.predecessor_service_anchor_receipt.backend_provenance_record.payload
        )
        if any(
            backend[field] != predecessor_backend[field]
            for field in _SERVICE_BACKEND_CONTINUITY_FIELDS
        ):
            raise ValueError(
                "final service anchor does not preserve its predecessor backend provenance"
            )
        health_digests = tuple(record.digest() for record in health_records)
        exact_observation_digests = (
            backend_record.digest(),
            *health_digests,
            readiness_record.digest(),
        )
        complete_observation_digests = tuple(
            record.digest() for record in self.evidence_cut.observation_records
        )
        if (
            backend["authorization_digest"] != authorization.digest()
            or backend["observer_identity_digest"] != observer.digest()
            or any(backend[field] != value for field, value in common.items())
            or readiness["backend_provenance_digest"] != backend_record.digest()
            or readiness["backend_manifest_digest"]
            != backend["backend_manifest_digest"]
            or readiness["status"] != "ready"
            or any(readiness[field] != value for field, value in common.items())
            or tuple(readiness["service_health_observation_digests"])
            != health_digests
            or complete_observation_digests[-len(exact_observation_digests) :]
            != exact_observation_digests
            or not _authorization_admits_identity(
                authorization,
                separation,
                observer,
                action="observe_service",
                subject_kind="protected_state",
            )
        ):
            raise ValueError(
                "final service observations do not bind one authorized fresh process epoch"
            )
        for health_record in health_records:
            health = health_record.payload
            if (
                health["status"] != "ready"
                or health["authorization_digest"] != authorization.digest()
                or health["observer_identity_digest"] != observer.digest()
                or health["backend_provenance_digest"] != backend_record.digest()
                or any(health[field] != value for field, value in common.items())
            ):
                raise ValueError(
                    "final service health does not bind its exact backend process epoch"
                )
        terminal_at = parse_canonical_timestamp(
            operation.terminal_record.payload["completed_at"]
        )
        backend_at = parse_canonical_timestamp(backend["observed_at"])
        health_times = tuple(
            parse_canonical_timestamp(record.payload["observed_at"])
            for record in health_records
        )
        readiness_at = parse_canonical_timestamp(readiness["observed_at"])
        cut_at = parse_canonical_timestamp(
            self.evidence_cut.cut_record.payload["observed_at"]
        )
        issued_at = parse_canonical_timestamp(receipt["issued_at"])
        expires_at = parse_canonical_timestamp(receipt["expires_at"])
        if (
            not (
                terminal_at
                < backend_at
                <= min(health_times)
                <= max(health_times)
                <= readiness_at
                <= cut_at
                <= issued_at
                < expires_at
            )
            or expires_at - issued_at != timedelta(seconds=300)
            or issued_at - backend_at > timedelta(seconds=300)
        ):
            raise ValueError("final service anchor health lease is stale or noncausal")

    @property
    def receipt_digest(self) -> str:
        return self.receipt_record.digest()

    @property
    def expires_at(self) -> datetime:
        return parse_canonical_timestamp(self.receipt_record.payload["expires_at"])


def _validate_checkpoint_receipts(
    *,
    checkpoint_record: ControlRecord,
    promotion_contract: PromotionContract,
    evidence_cut: AtomicEvidenceCut,
    baseline_restoration_receipt: BaselineRestorationReceipt | None,
    service_anchor_receipt: ServiceAnchorReceipt | None,
) -> None:
    payload = checkpoint_record.payload
    phase = promotion_contract.phase
    if phase is PromotionPhase.PREVALIDATED:
        if (
            not isinstance(
                baseline_restoration_receipt,
                BaselineRestorationReceipt,
            )
            or payload.get("baseline_restoration_receipt_digest")
            != baseline_restoration_receipt.receipt_digest
            or not _canonical_graph_equivalent(
                baseline_restoration_receipt.promotion_contract,
                promotion_contract,
            )
            or not _canonical_graph_equivalent(
                baseline_restoration_receipt.evidence_cut,
                evidence_cut,
            )
            or baseline_restoration_receipt.captured_checkpoint.checkpoint_digest
            != _captured_baseline(
                promotion_contract.predecessor_checkpoint
            ).checkpoint_digest
        ):
            raise ValueError(
                "prevalidated checkpoint requires its exact W4 baseline restoration receipt"
            )
    elif baseline_restoration_receipt is not None or (
        "baseline_restoration_receipt_digest" in payload
    ):
        raise ValueError(
            "only a prevalidated checkpoint may own baseline restoration"
        )

    service_anchor_required = any(
        item.requirement_record.payload["purpose"] == "service_anchor"
        for item in promotion_contract.operation_requirements
    )
    if phase is PromotionPhase.ACTIVE and service_anchor_required:
        if (
            not isinstance(service_anchor_receipt, ServiceAnchorReceipt)
            or payload.get("service_anchor_receipt_digest")
            != service_anchor_receipt.receipt_digest
            or not _canonical_graph_equivalent(
                service_anchor_receipt.promotion_contract,
                promotion_contract,
            )
            or not _canonical_graph_equivalent(
                service_anchor_receipt.evidence_cut,
                evidence_cut,
            )
        ):
            raise ValueError(
                "active checkpoint requires its exact service anchor receipt"
            )
        established_at = parse_canonical_timestamp(payload["established_at"])
        issued_at = parse_canonical_timestamp(
            service_anchor_receipt.receipt_record.payload["issued_at"]
        )
        expires_at = parse_canonical_timestamp(
            service_anchor_receipt.receipt_record.payload["expires_at"]
        )
        if not issued_at <= established_at <= expires_at:
            raise ValueError(
                "active checkpoint establishment is outside its service anchor validity window"
            )
    elif service_anchor_receipt is not None or (
        "service_anchor_receipt_digest" in payload
    ):
        raise ValueError(
            "service anchor ownership is allowed only for an active checkpoint with an approved service-anchor requirement"
        )


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class LifecycleCheckpoint:
    """One immutable lifecycle receipt with its materialized predecessor chain."""

    checkpoint_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    predecessor_checkpoint: LifecycleCheckpoint | None = None
    promotion_contract: PromotionContract | None = None
    evidence_cut: AtomicEvidenceCut | None = None
    authority_proof_record: ControlRecord | None = None
    acceptance_request_record: ControlRecord | None = None
    approval_record: ControlRecord | None = None
    final_service_anchor_receipt: FinalServiceAnchorReceipt | None = None
    baseline_restoration_receipt: BaselineRestorationReceipt | None = None
    service_anchor_receipt: ServiceAnchorReceipt | None = None
    root_authorization_record: ControlRecord | None = None
    root_authorization_policy_record: ControlRecord | None = None
    root_actor_identity_record: ControlRecord | None = None
    root_separation_policy_record: ControlRecord | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError(
            "LifecycleCheckpoint can only be issued by authority admission"
        )

    def __post_init__(self) -> None:
        _record(
            self.checkpoint_record,
            field="checkpoint_record",
            kind="lifecycle_checkpoint",
        )
        _record(self.generation_record, field="generation_record", kind="generation")
        _record(self.target_record, field="target_record", kind="identity")
        _record(
            self.target_protected_state_record,
            field="target_protected_state_record",
            kind="protected_state",
        )
        payload = self.checkpoint_record.payload
        expected = {
            "generation_digest": self.generation_record.digest(),
            "generation_class": self.generation_record.payload["generation_class"],
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": (
                self.target_protected_state_record.digest()
            ),
        }
        if any(payload[field] != value for field, value in expected.items()):
            raise ValueError("lifecycle checkpoint does not bind its exact material")
        if self.target_record.payload["identity_type"] != "target":
            raise ValueError("lifecycle checkpoint target must be a target identity")
        state = self.target_protected_state_record.payload
        if (
            state["target_digest"] != self.target_record.digest()
            or state["generation_digest"] != self.generation_record.digest()
        ):
            raise ValueError("lifecycle checkpoint protected state is mismatched")
        root = (
            payload["generation_class"] == "b0" and payload["phase"] == "captured"
        )
        if root:
            if self.predecessor_checkpoint is not None:
                raise ValueError("captured B0 checkpoint must be the lifecycle root")
            try:
                approval_record = _record(
                    self.root_authorization_record,
                    field="root_authorization_record",
                    kind="approval",
                )
            except (TypeError, ValueError):
                raise ValueError(
                    "captured B0 checkpoint requires its exact root authorization material"
                ) from None
            if payload["root_authorization_digest"] != approval_record.digest():
                raise ValueError(
                    "captured B0 checkpoint requires its exact root authorization material"
                )
            approval = approval_record.payload
            policy = _record(
                self.root_authorization_policy_record,
                field="root_authorization_policy_record",
                kind="authorization",
            )
            actor = _record(
                self.root_actor_identity_record,
                field="root_actor_identity_record",
                kind="identity",
            )
            separation = _record(
                self.root_separation_policy_record,
                field="root_separation_policy_record",
                kind="separation_policy",
            )
            if (
                approval["action"] != "capture_baseline"
                or approval["decision"] != "approved"
                or approval["subject_digest"]
                != self.target_protected_state_record.digest()
                or approval["authorization_digest"] != policy.digest()
                or approval["actor_identity_digest"] != actor.digest()
                or not _authorization_admits_actor(
                    policy,
                    separation,
                    actor,
                    actor_identity_digest=approval["actor_identity_digest"],
                    actor_role=approval["actor_role"],
                    action="capture_baseline",
                    subject_kind="protected_state",
                    require_approver_role=True,
                )
                or not (
                    parse_canonical_timestamp(state["observed_at"])
                    <= parse_canonical_timestamp(approval["decided_at"])
                    <= parse_canonical_timestamp(payload["established_at"])
                )
            ):
                raise ValueError(
                    "captured B0 checkpoint root approval is not exactly authorized"
                )
            if any(
                material is not None
                for material in (
                    self.promotion_contract,
                    self.evidence_cut,
                    self.authority_proof_record,
                    self.acceptance_request_record,
                    self.approval_record,
                    self.final_service_anchor_receipt,
                )
            ):
                raise ValueError(
                    "captured B0 checkpoint cannot bind promotion material"
                )
            if state["lifecycle_phase"] != "captured":
                raise ValueError("captured B0 checkpoint requires captured protected state")
        else:
            if any(
                material is not None
                for material in (
                    self.root_authorization_record,
                    self.root_authorization_policy_record,
                    self.root_actor_identity_record,
                    self.root_separation_policy_record,
                )
            ):
                raise ValueError(
                    "nonroot lifecycle checkpoint cannot bind root authorization material"
                )
            if not isinstance(self.predecessor_checkpoint, LifecycleCheckpoint):
                raise ValueError("nonroot lifecycle checkpoint requires its predecessor")
            if (
                payload["predecessor_checkpoint_digest"]
                != self.predecessor_checkpoint.checkpoint_digest
                or parse_canonical_timestamp(payload["established_at"])
                < parse_canonical_timestamp(
                    self.predecessor_checkpoint.checkpoint_record.payload[
                        "established_at"
                    ]
                )
            ):
                raise ValueError(
                    "lifecycle checkpoint does not bind its ordered predecessor"
                )
        if payload["generation_class"] == "c":
            if (
                self.predecessor_checkpoint is None
                or not isinstance(self.promotion_contract, PromotionContract)
                or not isinstance(self.evidence_cut, AtomicEvidenceCut)
                or self.authority_proof_record is None
            ):
                raise ValueError(
                    "nonroot C checkpoint requires its materialized contract, cut, and authority proof"
                )
            _validate_promotion_predecessor(
                phase=PromotionPhase(payload["phase"]),
                generation_digest=self.generation_record.digest(),
                target_digest=self.target_record.digest(),
                target_state_digest=self.target_protected_state_record.digest(),
                predecessor=self.predecessor_checkpoint,
            )
            expected_state_phase = (
                "active" if payload["phase"] == "accepted" else payload["phase"]
            )
            if state["lifecycle_phase"] != expected_state_phase:
                raise ValueError(
                    "C checkpoint protected state does not match its established phase"
                )
            self._validate_materialized_promotion()
        elif payload["generation_class"] == "f":
            raise ValueError(
                "unverified F material is a structural foundation candidate, not a lifecycle checkpoint"
            )
        elif not root:
            raise ValueError(
                "only captured B0 roots and materialized C checkpoints are supported"
            )
        seen: set[str] = set()
        checkpoint: LifecycleCheckpoint | None = self
        while checkpoint is not None:
            if checkpoint.checkpoint_digest in seen:
                raise ValueError("lifecycle checkpoint chain contains a cycle")
            seen.add(checkpoint.checkpoint_digest)
            checkpoint = checkpoint.predecessor_checkpoint

    def _validate_materialized_promotion(self) -> None:
        payload = self.checkpoint_record.payload
        contract = self.promotion_contract
        cut = self.evidence_cut
        proof_record = _record(
            self.authority_proof_record,
            field="authority_proof_record",
            kind="promotion_authority_proof",
        )
        predecessor = self.predecessor_checkpoint
        assert isinstance(contract, PromotionContract)
        assert isinstance(cut, AtomicEvidenceCut)
        assert isinstance(predecessor, LifecycleCheckpoint)
        expected = {
            "authority_proof_digest": proof_record.digest(),
            "contract_digest": contract.contract_digest,
            "evidence_cut_digest": cut.cut_record_digest,
            "generation_digest": contract.generation_digest,
            "phase": contract.phase.value,
            "predecessor_checkpoint_digest": predecessor.checkpoint_digest,
            "target_digest": contract.target_record.digest(),
            "target_protected_state_digest": (
                contract.target_protected_state_record.digest()
            ),
        }
        if any(payload[field] != value for field, value in expected.items()):
            raise ValueError(
                "lifecycle checkpoint does not bind its exact materialized promotion"
            )
        if (
            contract.generation_record.digest() != self.generation_record.digest()
            or contract.target_record.digest() != self.target_record.digest()
            or contract.target_protected_state_record.digest()
            != self.target_protected_state_record.digest()
            or not _canonical_lifecycle_graph_equivalent(
                contract.predecessor_checkpoint,
                predecessor,
            )
        ):
            raise ValueError(
                "materialized promotion does not bind the checkpoint object graph"
            )

        assess_promotion_cut(contract, cut)
        _validate_cut_follows_predecessor(contract, cut)
        _validate_checkpoint_receipts(
            checkpoint_record=self.checkpoint_record,
            promotion_contract=contract,
            evidence_cut=cut,
            baseline_restoration_receipt=self.baseline_restoration_receipt,
            service_anchor_receipt=self.service_anchor_receipt,
        )
        phase = PromotionPhase(payload["phase"])
        if phase is PromotionPhase.ACCEPTED:
            if (
                type(self.acceptance_request_record) is not ControlRecord
                or type(self.approval_record) is not ControlRecord
            ):
                raise ValueError(
                    "accepted checkpoint requires its materialized request and approval"
                )
            _validate_acceptance_material(
                contract,
                cut,
                self.final_service_anchor_receipt,
                self.acceptance_request_record,
                self.approval_record,
            )
            if (
                not isinstance(
                    self.final_service_anchor_receipt,
                    FinalServiceAnchorReceipt,
                )
                or payload["final_service_anchor_receipt_digest"]
                != self.final_service_anchor_receipt.receipt_digest
                or proof_record.payload["final_service_anchor_receipt_digest"]
                != self.final_service_anchor_receipt.receipt_digest
                or payload["acceptance_request_digest"]
                != self.acceptance_request_record.digest()
                or payload["approval_digest"] != self.approval_record.digest()
            ):
                raise ValueError(
                    "accepted checkpoint does not bind its exact request and approval"
                )
        elif (
            self.acceptance_request_record is not None
            or self.approval_record is not None
            or self.final_service_anchor_receipt is not None
        ):
            raise ValueError(
                "nonaccepted checkpoint cannot bind acceptance request or approval"
            )

        proof = _record(
            proof_record,
            field="authority_proof_record",
            kind="promotion_authority_proof",
        ).payload
        challenge = PromotionAuthorityChallenge.from_cut(
            contract,
            cut,
            authority_adapter_identity_digest=proof[
                "authority_adapter_identity_digest"
            ],
            authority_view_digest=proof["authority_view_digest"],
            predecessor_checkpoint=predecessor,
            acceptance_request_record=self.acceptance_request_record,
            approval_record=self.approval_record,
            final_service_anchor_receipt=self.final_service_anchor_receipt,
        )
        _verify_authority_proof(proof_record, challenge)
        proof_verified_at = parse_canonical_timestamp(proof["verified_at"])
        if proof_verified_at < _latest_cut_evidence_timestamp(cut) or (
            self.approval_record is not None
            and proof_verified_at
            < parse_canonical_timestamp(
                self.approval_record.payload["decided_at"]
            )
        ) or (
            self.final_service_anchor_receipt is not None
            and proof_verified_at > self.final_service_anchor_receipt.expires_at
        ):
            raise ValueError(
                "authority proof cannot precede its cut or acceptance approval"
            )
        _validate_admission_currentness(cut, boundary=proof_verified_at)
        established_at = parse_canonical_timestamp(payload["established_at"])
        if (
            established_at < proof_verified_at
            or (
                self.final_service_anchor_receipt is not None
                and established_at > self.final_service_anchor_receipt.expires_at
            )
        ):
            raise ValueError(
                "lifecycle checkpoint cannot precede its authority proof"
            )
        _validate_admission_currentness(cut, boundary=established_at)

    @property
    def checkpoint_digest(self) -> str:
        return self.checkpoint_record.digest()

    @property
    def phase(self) -> LifecyclePhase:
        return LifecyclePhase(self.checkpoint_record.payload["phase"])

    @property
    def promotional(self) -> bool:
        return _is_authority_issued_checkpoint(self)


@dataclass(frozen=True, slots=True)
class _LifecycleCheckpointSeal:
    fingerprint: object
    checkpoint_references: tuple[
        weakref.ReferenceType[LifecycleCheckpoint],
        ...,
    ]


_ISSUED_LIFECYCLE_CHECKPOINTS: dict[
    int,
    tuple[
        weakref.ReferenceType[LifecycleCheckpoint],
        _LifecycleCheckpointSeal,
    ],
] = {}


def _lifecycle_seal_material(
    value: LifecycleCheckpoint,
) -> tuple[object, tuple[LifecycleCheckpoint, ...]]:
    """Snapshot live record bytes and every checkpoint identity in one graph."""

    checkpoints: list[LifecycleCheckpoint] = []
    active: set[int] = set()

    def visit(item: object) -> object:
        if type(item) is ControlRecord:
            record = _any_record(item, field="lifecycle seal record")
            return ("control_record", record.canonical_bytes())
        if isinstance(item, ControlRecord):
            raise TypeError("lifecycle seal record must be an exact ControlRecord")
        if isinstance(item, StrEnum):
            return (
                "enum",
                type(item).__module__,
                type(item).__qualname__,
                item.value,
            )
        if item is None or type(item) in {bool, bytes, int, str}:
            return (type(item).__name__, item)

        tracked = isinstance(item, tuple | list | dict) or (
            is_dataclass(item) and not isinstance(item, type)
        )
        if not tracked:
            raise TypeError(
                f"unsupported lifecycle seal value: {type(item).__name__}"
            )
        identity = id(item)
        if identity in active:
            raise ValueError("lifecycle issuance seal graph must be acyclic")
        active.add(identity)
        try:
            if isinstance(item, LifecycleCheckpoint):
                checkpoints.append(item)
            if isinstance(item, tuple | list):
                return (
                    type(item).__name__,
                    tuple(visit(child) for child in item),
                )
            if isinstance(item, dict):
                return (
                    "dict",
                    tuple(
                        (visit(key), visit(child))
                        for key, child in sorted(item.items())
                    ),
                )
            return (
                "dataclass",
                type(item).__module__,
                type(item).__qualname__,
                tuple(
                    (field.name, visit(getattr(item, field.name)))
                    for field in fields(item)
                ),
            )
        finally:
            active.remove(identity)

    return visit(value), tuple(checkpoints)


def _is_authority_issued_checkpoint(value: object) -> bool:
    """Return whether this exact, unchanged checkpoint identity was issued here."""

    if not isinstance(value, LifecycleCheckpoint):
        return False
    entry = _ISSUED_LIFECYCLE_CHECKPOINTS.get(id(value))
    if entry is None or entry[0]() is not value:
        return False
    try:
        fingerprint, checkpoints = _lifecycle_seal_material(value)
        seal = entry[1]
        return (
            seal.fingerprint == fingerprint
            and len(seal.checkpoint_references) == len(checkpoints)
            and all(
                reference() is checkpoint
                for reference, checkpoint in zip(
                    seal.checkpoint_references,
                    checkpoints,
                    strict=True,
                )
            )
        )
    except Exception:  # noqa: BLE001 - malformed public objects must fail closed
        return False


def _seal_authority_issued_checkpoint(
    checkpoint: LifecycleCheckpoint,
) -> LifecycleCheckpoint:
    """Seal one fully validated checkpoint without trusting dataclass equality."""

    identity = id(checkpoint)

    def forget(reference: weakref.ReferenceType[LifecycleCheckpoint]) -> None:
        current = _ISSUED_LIFECYCLE_CHECKPOINTS.get(identity)
        if current is not None and current[0] is reference:
            _ISSUED_LIFECYCLE_CHECKPOINTS.pop(identity, None)

    fingerprint, checkpoints = _lifecycle_seal_material(checkpoint)
    reference = weakref.ref(checkpoint, forget)
    _ISSUED_LIFECYCLE_CHECKPOINTS[identity] = (
        reference,
        _LifecycleCheckpointSeal(
            fingerprint=fingerprint,
            checkpoint_references=tuple(
                weakref.ref(item) for item in checkpoints
            ),
        ),
    )
    return checkpoint


def _issue_lifecycle_checkpoint(
    *,
    checkpoint_record: ControlRecord,
    generation_record: ControlRecord,
    target_record: ControlRecord,
    target_protected_state_record: ControlRecord,
    predecessor_checkpoint: LifecycleCheckpoint,
    promotion_contract: PromotionContract,
    evidence_cut: AtomicEvidenceCut,
    authority_proof_record: ControlRecord,
    acceptance_request_record: ControlRecord | None,
    approval_record: ControlRecord | None,
    final_service_anchor_receipt: FinalServiceAnchorReceipt | None,
    baseline_restoration_receipt: BaselineRestorationReceipt | None,
    service_anchor_receipt: ServiceAnchorReceipt | None,
) -> LifecycleCheckpoint:
    checkpoint = object.__new__(LifecycleCheckpoint)
    values = {
        "checkpoint_record": checkpoint_record,
        "generation_record": generation_record,
        "target_record": target_record,
        "target_protected_state_record": target_protected_state_record,
        "predecessor_checkpoint": predecessor_checkpoint,
        "promotion_contract": promotion_contract,
        "evidence_cut": evidence_cut,
        "authority_proof_record": authority_proof_record,
        "acceptance_request_record": acceptance_request_record,
        "approval_record": approval_record,
        "final_service_anchor_receipt": final_service_anchor_receipt,
        "baseline_restoration_receipt": baseline_restoration_receipt,
        "service_anchor_receipt": service_anchor_receipt,
        "root_authorization_record": None,
        "root_authorization_policy_record": None,
        "root_actor_identity_record": None,
        "root_separation_policy_record": None,
    }
    for field, value in values.items():
        object.__setattr__(checkpoint, field, value)
    checkpoint.__post_init__()
    return _seal_authority_issued_checkpoint(checkpoint)


@dataclass(frozen=True, slots=True)
class StructuralBaselineCapture:
    """Caller-constructible B0 capture material with no root-authority admission."""

    structural_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    capture_approval_record: ControlRecord | None = None
    capture_authorization_record: ControlRecord | None = None
    capture_actor_identity_record: ControlRecord | None = None
    capture_separation_policy_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        record = _record(
            self.structural_record,
            field="structural_record",
            kind="lifecycle_checkpoint",
        ).payload
        generation = _record(
            self.generation_record,
            field="generation_record",
            kind="generation",
        ).payload
        target = _record(
            self.target_record,
            field="target_record",
            kind="identity",
        ).payload
        state = _record(
            self.target_protected_state_record,
            field="target_protected_state_record",
            kind="protected_state",
        ).payload
        expected = {
            "generation_class": GenerationClass.B0.value,
            "generation_digest": self.generation_record.digest(),
            "phase": LifecyclePhase.CAPTURED.value,
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": (
                self.target_protected_state_record.digest()
            ),
        }
        if any(record[field] != value for field, value in expected.items()):
            raise ValueError("structural B0 capture does not bind its exact material")
        if (
            generation["generation_class"] != GenerationClass.B0.value
            or target["identity_type"] != "target"
            or state["generation_digest"] != self.generation_record.digest()
            or state["target_digest"] != self.target_record.digest()
            or state["lifecycle_phase"] != LifecyclePhase.CAPTURED.value
            or parse_canonical_timestamp(state["observed_at"])
            > parse_canonical_timestamp(record["established_at"])
        ):
            raise ValueError("structural B0 capture material is mismatched")
        material = (
            self.capture_approval_record,
            self.capture_authorization_record,
            self.capture_actor_identity_record,
            self.capture_separation_policy_record,
        )
        if any(item is not None for item in material):
            if not all(type(item) is ControlRecord for item in material):
                raise ValueError(
                    "structural B0 capture authorization material must be complete"
                )
            approval_record = _record(
                self.capture_approval_record,
                field="capture_approval_record",
                kind="approval",
            )
            authorization_record = _record(
                self.capture_authorization_record,
                field="capture_authorization_record",
                kind="authorization",
            )
            actor_record = _record(
                self.capture_actor_identity_record,
                field="capture_actor_identity_record",
                kind="identity",
            )
            separation_record = _record(
                self.capture_separation_policy_record,
                field="capture_separation_policy_record",
                kind="separation_policy",
            )
            approval = approval_record.payload
            if (
                record.get("root_authorization_digest")
                != approval_record.digest()
                or approval["action"] != "capture_baseline"
                or approval["decision"] != "approved"
                or approval["subject_digest"]
                != self.target_protected_state_record.digest()
                or approval["authorization_digest"]
                != authorization_record.digest()
                or approval["actor_identity_digest"] != actor_record.digest()
                or not _authorization_admits_actor(
                    authorization_record,
                    separation_record,
                    actor_record,
                    actor_identity_digest=approval["actor_identity_digest"],
                    actor_role=approval["actor_role"],
                    action="capture_baseline",
                    subject_kind="protected_state",
                    require_approver_role=True,
                )
                or not (
                    parse_canonical_timestamp(state["observed_at"])
                    <= parse_canonical_timestamp(approval["decided_at"])
                    <= parse_canonical_timestamp(record["established_at"])
                )
            ):
                raise ValueError(
                    "structural B0 capture approval is not exactly authorized"
                )

    @property
    def checkpoint_digest(self) -> str:
        return self.structural_record.digest()

    @property
    def checkpoint_record(self) -> ControlRecord:
        return self.structural_record

    @property
    def evidence_cut(self) -> None:
        return None

    @property
    def predecessor_checkpoint(self) -> None:
        return None

    @property
    def root_authorization_record(self) -> ControlRecord | None:
        return self.capture_approval_record

    @property
    def root_authorization_policy_record(self) -> ControlRecord | None:
        return self.capture_authorization_record

    @property
    def root_actor_identity_record(self) -> ControlRecord | None:
        return self.capture_actor_identity_record

    @property
    def root_separation_policy_record(self) -> ControlRecord | None:
        return self.capture_separation_policy_record

    @property
    def phase(self) -> LifecyclePhase:
        return LifecyclePhase.CAPTURED

    @property
    def promotional(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class StructuralLifecycleCandidate:
    """Materialized C assessment chain that carries no admission authority."""

    structural_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    predecessor_checkpoint: (
        LifecycleCheckpoint
        | StructuralBaselineCapture
        | StructuralLifecycleCandidate
    )
    promotion_contract: PromotionContract
    evidence_cut: AtomicEvidenceCut
    acceptance_request_record: ControlRecord | None = None
    approval_record: ControlRecord | None = None
    final_service_anchor_receipt: FinalServiceAnchorReceipt | None = None
    baseline_restoration_receipt: BaselineRestorationReceipt | None = None
    service_anchor_receipt: ServiceAnchorReceipt | None = None

    def __post_init__(self) -> None:
        record = _record(
            self.structural_record,
            field="structural_record",
            kind="lifecycle_checkpoint",
        ).payload
        if record["generation_class"] != GenerationClass.C.value:
            raise ValueError("structural lifecycle candidate requires a C generation")
        if not _is_promotion_predecessor(self.predecessor_checkpoint):
            raise TypeError("structural lifecycle candidate requires a predecessor")
        if not isinstance(self.promotion_contract, PromotionContract) or not isinstance(
            self.evidence_cut,
            AtomicEvidenceCut,
        ):
            raise TypeError(
                "structural lifecycle candidate requires materialized contract and cut"
            )
        expected = {
            "contract_digest": self.promotion_contract.contract_digest,
            "evidence_cut_digest": self.evidence_cut.cut_record_digest,
            "generation_digest": self.generation_record.digest(),
            "phase": self.promotion_contract.phase.value,
            "predecessor_checkpoint_digest": self.predecessor_checkpoint.checkpoint_digest,
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": self.target_protected_state_record.digest(),
        }
        if any(record[field] != value for field, value in expected.items()):
            raise ValueError(
                "structural lifecycle candidate does not bind its exact material"
            )
        if (
            self.promotion_contract.generation_record.digest()
            != self.generation_record.digest()
            or self.promotion_contract.target_record.digest()
            != self.target_record.digest()
            or self.promotion_contract.target_protected_state_record.digest()
            != self.target_protected_state_record.digest()
            or not _canonical_lifecycle_graph_equivalent(
                self.promotion_contract.predecessor_checkpoint,
                self.predecessor_checkpoint,
            )
        ):
            raise ValueError(
                "structural lifecycle candidate does not bind its object graph"
            )
        assess_promotion_cut(self.promotion_contract, self.evidence_cut)
        _validate_checkpoint_receipts(
            checkpoint_record=self.structural_record,
            promotion_contract=self.promotion_contract,
            evidence_cut=self.evidence_cut,
            baseline_restoration_receipt=self.baseline_restoration_receipt,
            service_anchor_receipt=self.service_anchor_receipt,
        )
        if self.promotion_contract.phase is PromotionPhase.ACCEPTED:
            if (
                type(self.acceptance_request_record) is not ControlRecord
                or type(self.approval_record) is not ControlRecord
            ):
                raise ValueError(
                    "accepted structural candidate requires request and approval"
                )
            _validate_acceptance_material(
                self.promotion_contract,
                self.evidence_cut,
                self.final_service_anchor_receipt,
                self.acceptance_request_record,
                self.approval_record,
            )
            if (
                not isinstance(
                    self.final_service_anchor_receipt,
                    FinalServiceAnchorReceipt,
                )
                or record["final_service_anchor_receipt_digest"]
                != self.final_service_anchor_receipt.receipt_digest
                or record["acceptance_request_digest"]
                != self.acceptance_request_record.digest()
                or record["approval_digest"] != self.approval_record.digest()
            ):
                raise ValueError(
                    "accepted structural candidate does not bind its exact request and approval"
                )
        elif (
            self.acceptance_request_record is not None
            or self.approval_record is not None
            or self.final_service_anchor_receipt is not None
        ):
            raise ValueError(
                "nonaccepted structural candidate cannot bind acceptance material"
            )
        latest_material = max(
            parse_canonical_timestamp(
                self.predecessor_checkpoint.checkpoint_record.payload[
                    "established_at"
                ]
            ),
            _latest_cut_evidence_timestamp(self.evidence_cut),
        )
        if self.approval_record is not None:
            latest_material = max(
                latest_material,
                parse_canonical_timestamp(
                    self.approval_record.payload["decided_at"]
                ),
            )
        if self.final_service_anchor_receipt is not None:
            latest_material = max(
                latest_material,
                parse_canonical_timestamp(
                    self.final_service_anchor_receipt.receipt_record.payload[
                        "issued_at"
                    ]
                ),
            )
        if parse_canonical_timestamp(record["established_at"]) < latest_material:
            raise ValueError(
                "structural lifecycle candidate cannot precede its complete cut, predecessor, or approval"
            )
        if (
            self.final_service_anchor_receipt is not None
            and parse_canonical_timestamp(record["established_at"])
            > self.final_service_anchor_receipt.expires_at
        ):
            raise ValueError(
                "structural lifecycle candidate cannot outlive its final service anchor"
            )

    @property
    def checkpoint_digest(self) -> str:
        return self.structural_record.digest()

    @property
    def checkpoint_record(self) -> ControlRecord:
        return self.structural_record

    @property
    def phase(self) -> LifecyclePhase:
        return LifecyclePhase(self.structural_record.payload["phase"])

    @property
    def promotional(self) -> bool:
        return False


def _is_promotion_predecessor(value: object) -> bool:
    return (
        isinstance(value, LifecycleCheckpoint)
        and _is_authority_issued_checkpoint(value)
    ) or isinstance(
        value,
        (StructuralBaselineCapture, StructuralLifecycleCandidate),
    )


@dataclass(frozen=True, slots=True)
class StructuralFoundationCandidate:
    """Nonpromotional F material whose opaque proof digests are not trusted."""

    structural_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    predecessor_checkpoint: LifecycleCheckpoint | StructuralBaselineCapture

    def __post_init__(self) -> None:
        record = _record(
            self.structural_record,
            field="structural_record",
            kind="lifecycle_checkpoint",
        ).payload
        _record(self.generation_record, field="generation_record", kind="generation")
        _record(self.target_record, field="target_record", kind="identity")
        state = _record(
            self.target_protected_state_record,
            field="target_protected_state_record",
            kind="protected_state",
        ).payload
        if not isinstance(
            self.predecessor_checkpoint,
            (LifecycleCheckpoint, StructuralBaselineCapture),
        ):
            raise TypeError(
                "predecessor_checkpoint must be captured lifecycle material"
            )
        predecessor = self.predecessor_checkpoint.checkpoint_record.payload
        expected = {
            "generation_class": GenerationClass.F.value,
            "generation_digest": self.generation_record.digest(),
            "phase": LifecyclePhase.FOUNDATION_VALIDATION.value,
            "predecessor_checkpoint_digest": (
                self.predecessor_checkpoint.checkpoint_digest
            ),
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": (
                self.target_protected_state_record.digest()
            ),
        }
        if any(record[field] != value for field, value in expected.items()):
            raise ValueError(
                "structural foundation candidate does not bind its exact material"
            )
        if (
            self.generation_record.payload["generation_class"] != GenerationClass.F.value
            or self.target_record.payload["identity_type"] != "target"
            or state["generation_digest"] != self.generation_record.digest()
            or state["target_digest"] != self.target_record.digest()
            or state["target_kind"] != OperationTargetKind.ISOLATED_ROOT.value
            or state["lifecycle_phase"]
            != LifecyclePhase.FOUNDATION_VALIDATION.value
        ):
            raise ValueError("structural foundation candidate material is mismatched")
        if (
            predecessor["generation_class"],
            predecessor["phase"],
        ) != (GenerationClass.B0.value, LifecyclePhase.CAPTURED.value):
            raise ValueError(
                "structural foundation candidate requires its captured B0 predecessor"
            )
        if predecessor["target_digest"] != self.target_record.digest():
            raise ValueError("foundation predecessor binds another target")
        if not (
            parse_canonical_timestamp(predecessor["established_at"])
            <= parse_canonical_timestamp(state["observed_at"])
            <= parse_canonical_timestamp(record["established_at"])
        ):
            raise ValueError(
                "structural foundation candidate chronology is not ordered"
            )

    @property
    def promotional(self) -> bool:
        return False

    @property
    def structural_digest(self) -> str:
        return self.structural_record.digest()


def _validate_promotion_predecessor(
    *,
    phase: PromotionPhase,
    generation_digest: str,
    target_digest: str,
    target_state_digest: str,
    predecessor: (
        LifecycleCheckpoint
        | StructuralBaselineCapture
        | StructuralLifecycleCandidate
    ),
) -> None:
    if isinstance(predecessor, LifecycleCheckpoint) and (
        not _is_authority_issued_checkpoint(predecessor)
    ):
        raise ValueError(
            "promotion predecessor is not an authority-issued lifecycle checkpoint"
        )
    predecessor_payload = predecessor.checkpoint_record.payload
    predecessor_coordinate = (
        predecessor_payload["generation_class"],
        predecessor_payload["phase"],
    )
    if predecessor_payload["target_digest"] != target_digest:
        raise ValueError("promotion predecessor binds another target")
    if phase is PromotionPhase.PUBLISHED:
        if predecessor_coordinate not in {("b0", "captured"), ("c", "accepted")}:
            raise ValueError(
                "published phase requires captured B0 or prior accepted C predecessor"
            )
        if (
            predecessor_coordinate == ("c", "accepted")
            and predecessor_payload["generation_digest"] == generation_digest
        ):
            raise ValueError("published phase requires a new C generation")
        return
    expected_predecessor_phase = _PREDECESSOR_PHASE[phase].value
    if (
        predecessor_coordinate != ("c", expected_predecessor_phase)
        or predecessor_payload["generation_digest"] != generation_digest
    ):
        raise ValueError(
            "promotion phase does not bind the exact prior phase of the same C generation"
        )
    if (
        phase is PromotionPhase.ACCEPTED
        and predecessor_payload["target_protected_state_digest"]
        != target_state_digest
    ):
        raise ValueError(
            "accepted phase must preserve the active predecessor protected state"
        )


def _captured_baseline(
    material: LifecycleCheckpoint | StructuralBaselineCapture | StructuralLifecycleCandidate,
) -> LifecycleCheckpoint | StructuralBaselineCapture:
    current = material
    while isinstance(current, (LifecycleCheckpoint, StructuralLifecycleCandidate)):
        payload = current.checkpoint_record.payload
        if (payload["generation_class"], payload["phase"]) == ("b0", "captured"):
            return current
        predecessor = current.predecessor_checkpoint
        if predecessor is None:
            break
        current = predecessor
    if isinstance(current, StructuralBaselineCapture):
        return current
    raise ValueError("promotion lifecycle does not trace to one captured B0 root")


@dataclass(frozen=True, slots=True)
class PromotionCutAssessment:
    """Semantic result; authoritative only after a production authority check."""

    contract_digest: str
    generation_digest: str
    phase: PromotionPhase
    cut_record_digest: str
    obligation_evaluation_digests: tuple[str, ...]
    authoritative: bool = False


@dataclass(frozen=True, slots=True)
class PromotionAuthorityChallenge:
    """Exact immutable cut coordinates a production authority must verify."""

    promotion_contract_digest: str
    validation_contract_digest: str
    atomic_evidence_cut_digest: str
    authority_adapter_identity_digest: str
    authority_view_digest: str
    authority_manifest_digest: str
    authority_head_digest: str
    journal_head_digest: str
    completeness_proof_digest: str
    fork_proof_digest: str
    complete_through_sequence: int
    attempt_digests: tuple[str, ...]
    evaluation_digests: tuple[str, ...]
    currency_proof_digests: tuple[str, ...]
    inclusion_edge_digests: tuple[str, ...]
    operation_digests: tuple[str, ...]
    capability_digests: tuple[str, ...]
    operation_terminal_digests: tuple[str, ...]
    observation_digests: tuple[str, ...]
    phase: PromotionPhase
    predecessor_checkpoint_digest: str
    acceptance_request_digest: str | None = None
    approval_digest: str | None = None
    final_service_anchor_receipt_digest: str | None = None

    @classmethod
    def from_cut(
        cls,
        contract: PromotionContract,
        cut: AtomicEvidenceCut,
        *,
        authority_adapter_identity_digest: str,
        authority_view_digest: str,
        predecessor_checkpoint: LifecycleCheckpoint,
        acceptance_request_record: ControlRecord | None = None,
        approval_record: ControlRecord | None = None,
        final_service_anchor_receipt: FinalServiceAnchorReceipt | None = None,
    ) -> PromotionAuthorityChallenge:
        payload = cut.cut_record.payload
        for evaluation in cut.evaluations:
            stream = evaluation.invalidation_stream_checkpoint_record.payload
            trusted = evaluation.trusted_time_observation_record.payload
            if (
                stream["authority_view_digest"] != authority_view_digest
                or stream["authority_head_digest"] != payload["authority_head_digest"]
                or stream["authority_manifest_digest"]
                != payload["authority_manifest_digest"]
                or stream["completeness_proof_digest"]
                != payload["completeness_proof_digest"]
                or stream["fork_proof_digest"] != payload["fork_proof_digest"]
                or trusted["authority_head_digest"] != payload["authority_head_digest"]
            ):
                raise ValueError(
                    "currency authority material does not bind the challenged production view"
                )
        return cls(
            promotion_contract_digest=contract.contract_digest,
            validation_contract_digest=contract.validation_contract_record.digest(),
            atomic_evidence_cut_digest=cut.cut_record_digest,
            authority_adapter_identity_digest=authority_adapter_identity_digest,
            authority_view_digest=authority_view_digest,
            authority_manifest_digest=payload["authority_manifest_digest"],
            authority_head_digest=payload["authority_head_digest"],
            journal_head_digest=payload["journal_head_digest"],
            completeness_proof_digest=payload["completeness_proof_digest"],
            fork_proof_digest=payload["fork_proof_digest"],
            complete_through_sequence=payload["complete_through_sequence"],
            attempt_digests=tuple(payload["attempt_digests"]),
            evaluation_digests=tuple(payload["evaluation_digests"]),
            currency_proof_digests=tuple(payload["currency_proof_digests"]),
            inclusion_edge_digests=tuple(payload["inclusion_edge_digests"]),
            operation_digests=tuple(payload["operation_digests"]),
            capability_digests=tuple(payload["capability_digests"]),
            operation_terminal_digests=tuple(
                payload["operation_terminal_digests"]
            ),
            observation_digests=tuple(payload["observation_digests"]),
            phase=contract.phase,
            predecessor_checkpoint_digest=(
                predecessor_checkpoint.checkpoint_digest
            ),
            acceptance_request_digest=(
                acceptance_request_record.digest()
                if acceptance_request_record is not None
                else None
            ),
            approval_digest=(
                approval_record.digest() if approval_record is not None else None
            ),
            final_service_anchor_receipt_digest=(
                final_service_anchor_receipt.receipt_digest
                if final_service_anchor_receipt is not None
                else None
            ),
        )


@runtime_checkable
class PromotionAuthority(Protocol):
    """Reconstruct an exact authoritative cut and return its canonical proof.

    Implementations must verify the journal/view identity, exact record sets,
    completeness proof, and fork proof from their authoritative substrate. A
    proof that merely echoes the caller's challenge is non-authoritative.
    """

    @property
    def authority_adapter_identity_digest(self) -> str: ...

    @property
    def authority_view_digest(self) -> str: ...

    def verify_promotion_cut(
        self,
        challenge: PromotionAuthorityChallenge,
    ) -> ControlRecord: ...


class PromotionDenied(ControlAuthorityError):
    """The canonical cut cannot satisfy every promotion obligation."""


def _deny(code: str, message: str) -> None:
    raise PromotionDenied(code, message)


def _validate_contract_time_budgets(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
) -> None:
    """Fail closed when a cut exceeds its immutable validation time budgets."""

    validation_contract = contract.validation_contract_record.payload
    max_live_attempt = timedelta(
        seconds=validation_contract["max_live_attempt_seconds"]
    )
    for attempt in cut.attempts:
        duration = parse_canonical_timestamp(
            attempt.terminal_record.payload["completed_at"]
        ) - parse_canonical_timestamp(attempt.attempt_record.payload["started_at"])
        if duration > max_live_attempt:
            _deny(
                "PROMOTION_ATTEMPT_DID_NOT_PASS",
                "gate attempt exceeded the validation-contract live-attempt time budget",
            )
    for operation in cut.operations:
        duration = parse_canonical_timestamp(
            operation.terminal_record.payload["completed_at"]
        ) - parse_canonical_timestamp(operation.intent_record.payload["registered_at"])
        if duration > max_live_attempt:
            _deny(
                "PROMOTION_OPERATION_DID_NOT_PASS",
                "critical operation exceeded the validation-contract live-attempt time budget",
            )
    if contract.phase not in {
        PromotionPhase.PREVALIDATED,
        PromotionPhase.ACCEPTED,
    }:
        return
    registered_at = min(
        *(
            parse_canonical_timestamp(attempt.intent_record.payload["registered_at"])
            for attempt in cut.attempts
        ),
        *(
            parse_canonical_timestamp(
                operation.intent_record.payload["registered_at"]
            )
            for operation in cut.operations
        ),
    )
    terminal_or_cut_at = max(
        parse_canonical_timestamp(cut.cut_record.payload["observed_at"]),
        *(
            parse_canonical_timestamp(
                attempt.terminal_record.payload["completed_at"]
            )
            for attempt in cut.attempts
        ),
        *(
            parse_canonical_timestamp(
                operation.terminal_record.payload["completed_at"]
            )
            for operation in cut.operations
        ),
    )
    max_suite = timedelta(seconds=validation_contract["max_suite_seconds"])
    if terminal_or_cut_at - registered_at > max_suite:
        _deny(
            "PROMOTION_EVIDENCE_NOT_CURRENT",
            "terminal lifecycle cut exceeded the validation-contract suite time budget",
        )


def assess_operation_obligations(
    obligations: tuple[OperationObligation, ...],
    operations: tuple[RegisteredOperation, ...],
    *,
    authority_head_digest: str,
    captured_baseline_protected_state_record: ControlRecord | None = None,
) -> tuple[str, ...]:
    """Match a complete operation set to generic exact authority coordinates.

    Operation obligations cover every legal B0, F, and C authority coordinate.
    A C promotion contract is one consumer and separately constrains its
    obligations to the promoted generation class and phase.
    Captured-baseline recovery binds the exact protected-state material so its
    terminal destination restores that baseline's generation, projection, and
    state rather than only naming its digest as a recovery target.
    """

    obligations = tuple(obligations)
    operations = tuple(operations)
    if any(not isinstance(item, OperationObligation) for item in obligations):
        raise TypeError("obligations must contain OperationObligation values")
    if any(not isinstance(item, RegisteredOperation) for item in operations):
        raise TypeError("operations must contain RegisteredOperation values")
    if captured_baseline_protected_state_record is not None:
        _record(
            captured_baseline_protected_state_record,
            field="captured_baseline_protected_state_record",
            kind="protected_state",
        )
    expected_by_operation = {item.operation_digest: item for item in obligations}
    if len(expected_by_operation) != len(obligations):
        _deny(
            "PROMOTION_OPERATIONS_INCOMPLETE",
            "operation obligations contain duplicate exact operation bindings",
        )
    actual_digests: set[str] = set()
    operation_digests: list[str] = []
    for registered_operation in operations:
        operation = registered_operation.operation_record.payload
        operation_digest = registered_operation.operation_digest
        obligation = expected_by_operation.get(operation_digest)
        if (
            operation["authority_head_digest"] != authority_head_digest
            or obligation is None
            or _operation_coordinates(operation) != obligation.coordinates
            or not _operation_refines_requirement(
                obligation.requirement,
                registered_operation,
                captured_baseline_protected_state_record=(
                    captured_baseline_protected_state_record
                ),
            )
        ):
            _deny(
                "PROMOTION_OPERATION_BINDING_MISMATCH",
                "critical operation does not bind the exact canonical operation envelope and authority head",
            )
        if operation_digest in actual_digests:
            _deny(
                "PROMOTION_OPERATIONS_INCOMPLETE",
                "critical operation set contains a duplicate exact operation",
            )
        actual_digests.add(operation_digest)
        operation_digests.append(operation_digest)
    if actual_digests != set(expected_by_operation):
        _deny(
            "PROMOTION_OPERATIONS_INCOMPLETE",
            "critical operation set does not cover canonical operation obligations exactly",
        )
    if any(
        item.terminal_record.payload["outcome"] != "succeeded"
        for item in operations
    ):
        _deny(
            "PROMOTION_OPERATION_DID_NOT_PASS",
            "a critical operation did not terminalize successfully",
        )
    return tuple(operation_digests)


def _operation_refines_requirement(
    requirement: OperationRequirement,
    operation: RegisteredOperation,
    *,
    captured_baseline_protected_state_record: ControlRecord | None,
) -> bool:
    approved = requirement.requirement_record.payload
    realized = operation.operation_record.payload
    exact_fields = (
        "declared_effects",
        "generation_class",
        "lifecycle_phase",
        "operation_kind",
        "plan_digest",
        "recovery_contract_digest",
        "subject_kind",
        "target_id",
        "target_kind",
        "terminal_validator_digest",
    )
    if any(realized[field] != approved[field] for field in exact_fields):
        return False
    if (
        realized["target_digest"] != requirement.target_record.digest()
        or operation.target_record.digest() != requirement.target_record.digest()
        or realized["generation_binding"]["mode"]
        != approved["generation_binding_mode"]
        or realized.get("rollback_contract_digest")
        != approved.get("rollback_contract_digest")
    ):
        return False
    recovery_target_by_role = {
        "captured_baseline": (
            captured_baseline_protected_state_record.digest()
            if captured_baseline_protected_state_record is not None
            else None
        ),
        "expected_prestate": operation.expected_protected_state_record.digest(),
        "predecessor_state": operation.expected_protected_state_record.digest(),
    }
    expected_recovery_target = recovery_target_by_role[
        approved["recovery_target_role"]
    ]
    if (
        approved["purpose"] == "baseline_restoration"
        and captured_baseline_protected_state_record is not None
    ):
        baseline = captured_baseline_protected_state_record.payload
        destination = operation.intended_protected_state_record.payload
        if any(
            destination[field] != baseline[field]
            for field in (
                "generation_digest",
                "projection_id",
                "state_digest",
            )
        ):
            return False
    return (
        expected_recovery_target is not None
        and realized["recovery_target_digest"] == expected_recovery_target
    )


def _verify_authority_proof(
    proof_record: ControlRecord,
    challenge: PromotionAuthorityChallenge,
) -> None:
    proof = _record(
        proof_record,
        field="promotion authority proof",
        kind="promotion_authority_proof",
    ).payload
    expected = {
        "atomic_evidence_cut_digest": challenge.atomic_evidence_cut_digest,
        "attempt_digests": challenge.attempt_digests,
        "authority_adapter_identity_digest": (
            challenge.authority_adapter_identity_digest
        ),
        "authority_head_digest": challenge.authority_head_digest,
        "authority_manifest_digest": challenge.authority_manifest_digest,
        "authority_view_digest": challenge.authority_view_digest,
        "complete_through_sequence": challenge.complete_through_sequence,
        "completeness_proof_digest": challenge.completeness_proof_digest,
        "currency_proof_digests": challenge.currency_proof_digests,
        "evaluation_digests": challenge.evaluation_digests,
        "fork_proof_digest": challenge.fork_proof_digest,
        "inclusion_edge_digests": challenge.inclusion_edge_digests,
        "journal_head_digest": challenge.journal_head_digest,
        "operation_digests": challenge.operation_digests,
        "capability_digests": challenge.capability_digests,
        "operation_terminal_digests": challenge.operation_terminal_digests,
        "observation_digests": challenge.observation_digests,
        "phase": challenge.phase.value,
        "predecessor_checkpoint_digest": challenge.predecessor_checkpoint_digest,
        "promotion_contract_digest": challenge.promotion_contract_digest,
        "validation_contract_digest": challenge.validation_contract_digest,
    }
    if challenge.acceptance_request_digest is not None:
        expected["acceptance_request_digest"] = challenge.acceptance_request_digest
    if challenge.approval_digest is not None:
        expected["approval_digest"] = challenge.approval_digest
    if challenge.final_service_anchor_receipt_digest is not None:
        expected["final_service_anchor_receipt_digest"] = (
            challenge.final_service_anchor_receipt_digest
        )
    for field, value in expected.items():
        actual = tuple(proof[field]) if field.endswith("_digests") else proof[field]
        if actual != value:
            _deny(
                "PROMOTION_AUTHORITY_PROOF_MISMATCH",
                f"authority proof does not bind exact {field}",
            )


def assess_promotion_cut(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
) -> PromotionCutAssessment:
    """Assess canonical semantics without asserting authority provenance."""

    cut_payload = cut.cut_record.payload
    contract_payload = contract.contract_record.payload
    if cut_payload["contract_digest"] != contract.contract_digest:
        _deny("PROMOTION_CONTRACT_MISMATCH", "cut does not bind canonical contract")
    if cut_payload["generation_digest"] != contract.generation_digest:
        _deny("PROMOTION_GENERATION_MISMATCH", "cut does not bind candidate generation")
    if cut_payload["phase"] != contract.phase.value:
        _deny("PROMOTION_PHASE_MISMATCH", "cut does not bind requested phase")
    if (
        cut_payload["target_digest"] != contract.target_record.digest()
        or cut_payload["target_kind"] != contract.target.kind.value
    ):
        _deny("PROMOTION_TARGET_MISMATCH", "cut does not bind requested target")
    if (
        cut.target_protected_state_record.digest()
        != contract.target_protected_state_record.digest()
    ):
        _deny(
            "PROMOTION_TARGET_STATE_MISMATCH",
            "cut does not bind the exact protected-state record",
        )
    if (
        cut.accepted_generation_record.digest()
        != contract_payload["expected_accepted_generation_digest"]
        or cut.active_generation_record.digest()
        != contract_payload["expected_active_generation_digest"]
    ):
        _deny("PROMOTION_GENERATION_MISMATCH", "generation pointers differ from contract")

    _validate_contract_time_budgets(contract, cut)

    obligation_by_digest = {
        item.obligation_digest: item for item in contract.obligations
    }
    attempt_by_obligation = {item.obligation_digest: item for item in cut.attempts}
    if set(attempt_by_obligation) != set(obligation_by_digest) or len(
        attempt_by_obligation
    ) != len(cut.attempts):
        _deny("PROMOTION_ATTEMPTS_INCOMPLETE", "attempts do not cover total obligations")
    evaluation_by_attempt = {item.attempt_digest: item for item in cut.evaluations}
    if len(evaluation_by_attempt) != len(cut.evaluations):
        _deny("PROMOTION_EVIDENCE_INCOMPLETE", "evaluations contain duplicate attempts")
    operation_obligation_by_digest = {
        item.obligation_digest: item for item in contract.operation_obligations
    }
    operation_by_digest = {
        item.operation_digest: item for item in cut.operations
    }

    evaluation_digests: list[str] = []
    applicability_by_assignment: dict[str, str] = {}
    used_attempts: set[str] = set()
    expected_edges: set[str] = set()
    for obligation_digest, obligation in obligation_by_digest.items():
        attempt = attempt_by_obligation[obligation_digest]
        bound = evaluation_by_attempt.get(attempt.attempt_digest)
        if bound is None:
            _deny("PROMOTION_EVIDENCE_INCOMPLETE", "obligation has no evaluation")
        used_attempts.add(attempt.attempt_digest)
        if (
            attempt.assignment_digest != obligation.assignment_digest
            or attempt.occurrence_digest != obligation.occurrence_digest
            or bound.assignment_digest != obligation.assignment_digest
            or bound.assignment_record.payload["impact"] != obligation.impact.value
        ):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "records bind different obligation coordinates",
            )
        terminal_attestations = tuple(
            attempt.terminal_record.payload["validator_attestation_digests"]
        )
        expected_attestations = tuple(
            item.digest()
            for item in bound.evidence_records
            if item.kind == "attestation"
        )
        expected_predicate_proof = bound.evaluation_record.payload.get(
            "predicate_proof_digest"
        )
        if (
            terminal_attestations != expected_attestations
            or attempt.terminal_record.payload.get("predicate_proof_digest")
            != expected_predicate_proof
        ):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "terminal does not bind evaluated evidence",
            )
        if parse_canonical_timestamp(
            bound.evaluation_record.payload["evaluated_at"]
        ) > parse_canonical_timestamp(attempt.terminal_record.payload["completed_at"]):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "gate terminal cannot precede its evaluation",
            )
        scenario_obligation_digest = (
            obligation.scenario_operation_obligation_digest
        )
        if scenario_obligation_digest is not None:
            if not bound.evidence_records or not bound.structural_admissibility:
                _deny(
                    "PROMOTION_EVIDENCE_NOT_CURRENT",
                    "scenario-linked evidence is missing, stale, or inadmissible",
                )
            scenario_obligation = operation_obligation_by_digest[
                scenario_obligation_digest
            ]
            scenario_operation = operation_by_digest.get(
                scenario_obligation.operation_digest
            ) or next(
                (
                    item
                    for item in cut.operations
                    if item.operation_record.payload["operation_kind"]
                    == "blocking_scenario"
                    and item.operation_record.payload["subject_digest"]
                    == obligation.occurrence_digest
                ),
                None,
            )
            if scenario_operation is not None:
                operation_registered_at = parse_canonical_timestamp(
                    scenario_operation.intent_record.payload["registered_at"]
                )
                capability_issued_at = parse_canonical_timestamp(
                    scenario_operation.capability_record.payload["issued_at"]
                )
                attempt_started_at = parse_canonical_timestamp(
                    attempt.attempt_record.payload["started_at"]
                )
                earliest_evidence_at = min(
                    parse_canonical_timestamp(item.payload["observed_at"])
                    for item in bound.evidence_records
                )
                gate_terminal_at = parse_canonical_timestamp(
                    attempt.terminal_record.payload["completed_at"]
                )
                operation_terminal_at = parse_canonical_timestamp(
                    scenario_operation.terminal_record.payload["completed_at"]
                )
                gate_registered_at = parse_canonical_timestamp(
                    attempt.intent_record.payload["registered_at"]
                )
                evaluated_at = parse_canonical_timestamp(
                    bound.evaluation_record.payload["evaluated_at"]
                )
                intended_observed_at = parse_canonical_timestamp(
                    scenario_operation.intended_protected_state_record.payload[
                        "observed_at"
                    ]
                )
                operation_attestation_times = tuple(
                    parse_canonical_timestamp(item.payload["observed_at"])
                    for item in scenario_operation.validator_attestation_records
                )
                attestation_floor = gate_terminal_at
                if (
                    scenario_operation.terminal_record.payload["outcome"]
                    == "succeeded"
                ):
                    attestation_floor = max(
                        attestation_floor,
                        intended_observed_at,
                    )
                if (
                    attempt.intent_record.payload["journal_sequence"]
                    >= scenario_operation.intent_record.payload["journal_sequence"]
                    or scenario_operation.intent_record.payload["journal_sequence"]
                    >= attempt.attempt_record.payload["journal_sequence"]
                    or attempt.attempt_record.payload["journal_sequence"]
                    >= attempt.terminal_record.payload["journal_sequence"]
                    or operation_registered_at >= attempt_started_at
                    or gate_registered_at >= operation_registered_at
                    or capability_issued_at >= attempt_started_at
                    or operation_registered_at >= earliest_evidence_at
                    or capability_issued_at >= earliest_evidence_at
                    or attempt.terminal_record.payload["journal_sequence"]
                    >= scenario_operation.terminal_record.payload[
                        "journal_sequence"
                    ]
                    or gate_terminal_at >= operation_terminal_at
                    or earliest_evidence_at > evaluated_at
                    or evaluated_at > gate_terminal_at
                    or gate_terminal_at > intended_observed_at
                    or any(
                        not attestation_floor
                        <= attested_at
                        <= operation_terminal_at
                        for attested_at in operation_attestation_times
                    )
                ):
                    _deny(
                        "PROMOTION_OPERATION_BINDING_MISMATCH",
                        "scenario operation must be fenced before gate work and terminalize after its gate",
                    )

        context = bound.context_record.payload
        if (
            context["requirements_digest"] != contract.requirements_record.digest()
            or context["assignments_digest"]
            != contract.assignment_set_record.digest()
        ):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "validation context does not bind canonical requirements and assignments",
            )
        if context["context_type"] == "active_contract":
            if (
                context["contract_digest"]
                != contract.validation_contract_record.digest()
                or context["requirements_digest"] != contract.requirements_record.digest()
                or context["generation_digest"] != contract.generation_digest
            ):
                _deny(
                    "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                    "active context does not bind contract generation",
                )
        else:
            edge = bound.inclusion_edge_record
            assert edge is not None
            edge_payload = edge.payload
            if (
                edge_payload["active_contract_digest"]
                != contract.validation_contract_record.digest()
                or edge_payload["generation_digest"] != contract.generation_digest
            ):
                _deny(
                    "PROMOTION_INCLUSION_EDGE_MISMATCH",
                    "inclusion edge does not bind active contract generation",
                )
            expected_edges.add(edge.digest())

        evaluation = bound.evaluation_record.payload
        applicability = evaluation["applicability"]
        applicability_by_assignment[bound.assignment_digest] = applicability
        outcome = evaluation["outcome"]
        execution_requirement = bound.assignment_record.payload[
            "execution_requirement"
        ]
        scenario_linked = (
            obligation.scenario_operation_obligation_digest is not None
        )
        if (
            applicability == "applicable"
            and (execution_requirement == "blocking_scenario") != scenario_linked
        ) or (
            applicability == "not_applicable" and scenario_linked
        ):
            _deny(
                "PROMOTION_OPERATION_BINDING_MISMATCH",
                "evaluation applicability does not match its assignment scenario requirement",
            )
        expected_terminal_outcome = {
            ("applicable", "blocked"): "failed",
            ("applicable", "fail"): "failed",
            ("applicable", "pass"): "succeeded",
            ("applicable_unknown", "unknown"): "unknown",
            ("not_applicable", "not_applicable"): "succeeded",
            ("not_due", "unknown"): "unknown",
        }.get((applicability, outcome))
        if (
            expected_terminal_outcome is None
            or attempt.terminal_record.payload["outcome"]
            != expected_terminal_outcome
            or (
                attempt.attempt_record.payload["decision"] == "blocked"
                and not (
                    applicability == "applicable"
                    and outcome == "blocked"
                    and expected_terminal_outcome == "failed"
                )
            )
        ):
            _deny(
                "PROMOTION_ATTEMPT_DID_NOT_PASS",
                "attempt admission and terminal outcome do not support its evaluation",
            )
        if not bound.structural_admissibility:
            _deny("PROMOTION_EVIDENCE_NOT_CURRENT", "evidence is stale or inadmissible")
        if obligation.impact is GateImpact.BLOCKING:
            satisfied = (
                evaluation["applicability"] == "applicable"
                and evaluation["outcome"] == "pass"
            ) or (
                evaluation["applicability"] == "not_applicable"
                and evaluation["outcome"] == "not_applicable"
            )
            if not satisfied:
                _deny("PROMOTION_EVIDENCE_DID_NOT_PASS", "blocking obligation did not pass")
        evaluation_digests.append(bound.evaluation_record_digest)

    if set(evaluation_by_attempt) != used_attempts:
        _deny("PROMOTION_EVIDENCE_INCOMPLETE", "evaluation set contains extra attempts")
    realization_counts: dict[str, int] = {
        requirement.requirement_digest: 0
        for requirement in contract.operation_requirements
    }
    for operation_obligation in contract.operation_obligations:
        realization_counts[operation_obligation.requirement.requirement_digest] += 1
    for requirement in contract.operation_requirements:
        assignment_digest = requirement.assignment_digest
        if assignment_digest is None:
            continue
        applicability = applicability_by_assignment.get(assignment_digest)
        expected_count = 1 if applicability == "applicable" else 0
        if applicability not in {"applicable", "not_applicable"} or (
            realization_counts[requirement.requirement_digest] != expected_count
        ):
            _deny(
                "PROMOTION_OPERATION_BINDING_MISMATCH",
                "conditional operation realization does not match its exact evaluation applicability",
            )
    if {item.digest() for item in cut.inclusion_edge_records} != expected_edges:
        _deny("PROMOTION_INCLUSION_EDGE_MISMATCH", "cut inclusion-edge set is not exact")
    actual_operation_digests = {
        item.operation_digest for item in cut.operations
    }
    if (
        len(cut.operations) != len(contract.operation_obligations)
        or len(actual_operation_digests) != len(cut.operations)
    ):
        _deny(
            "PROMOTION_OPERATIONS_INCOMPLETE",
            "critical operation set does not cover canonical operation obligations exactly",
        )
    _validate_cut_follows_predecessor(contract, cut)
    assess_operation_obligations(
        contract.operation_obligations,
        cut.operations,
        authority_head_digest=cut_payload["authority_head_digest"],
        captured_baseline_protected_state_record=(
            _captured_baseline(contract.predecessor_checkpoint)
            .target_protected_state_record
        ),
    )
    if contract.phase is not PromotionPhase.ACCEPTED:
        phase_obligation_digest = contract.contract_record.payload[
            "phase_establishing_operation_obligation_digest"
        ]
        phase_operation_digest = next(
            obligation.operation_digest
            for obligation in contract.operation_obligations
            if obligation.obligation_digest == phase_obligation_digest
        )
        phase_operation = next(
            operation
            for operation in cut.operations
            if operation.operation_digest == phase_operation_digest
        )
        if (
            phase_operation.terminal_record.payload["outcome"] != "succeeded"
            or phase_operation.intended_protected_state_record.digest()
            != contract.target_protected_state_record.digest()
            or phase_operation.terminal_record.payload["poststate_digest"]
            != contract.target_protected_state_record.digest()
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "phase-establishing operation did not terminalize at the contract target state",
            )
    return PromotionCutAssessment(
        contract_digest=contract.contract_digest,
        generation_digest=contract.generation_digest,
        phase=contract.phase,
        cut_record_digest=cut.cut_record_digest,
        obligation_evaluation_digests=tuple(evaluation_digests),
    )


def build_acceptance_request(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
    assessment: PromotionCutAssessment,
    final_service_anchor_receipt: FinalServiceAnchorReceipt,
    *,
    record_id: str,
    requested_at: str,
) -> ControlRecord:
    """Build the immutable request for one already-assessed accepted cut."""

    if contract.phase is not PromotionPhase.ACCEPTED:
        raise ValueError("only an accepted-phase contract can request acceptance")
    if (
        not isinstance(final_service_anchor_receipt, FinalServiceAnchorReceipt)
        or not _canonical_graph_equivalent(
            final_service_anchor_receipt.promotion_contract,
            contract,
        )
        or not _canonical_graph_equivalent(
            final_service_anchor_receipt.evidence_cut,
            cut,
        )
    ):
        raise ValueError(
            "acceptance request requires the exact final service anchor receipt"
        )
    if (
        assessment.authoritative
        or assessment.contract_digest != contract.contract_digest
        or assessment.generation_digest != contract.generation_digest
        or assessment.phase is not contract.phase
        or assessment.cut_record_digest != cut.cut_record_digest
    ):
        raise ValueError("acceptance request requires the exact structural assessment")
    requested = parse_canonical_timestamp(requested_at)
    latest_evidence = _latest_cut_evidence_timestamp(cut)
    predecessor_time = parse_canonical_timestamp(
        contract.predecessor_checkpoint.checkpoint_record.payload["established_at"]
    )
    issued_at = parse_canonical_timestamp(
        final_service_anchor_receipt.receipt_record.payload["issued_at"]
    )
    if requested < max(latest_evidence, predecessor_time, issued_at) or (
        requested > final_service_anchor_receipt.expires_at
    ):
        raise ValueError("acceptance request cannot precede its complete evidence cut")
    return ControlRecord.build(
        kind="acceptance_request",
        record_id=record_id,
        payload={
            "acceptance_authorization_digest": contract.contract_record.payload[
                "acceptance_authorization_digest"
            ],
            "atomic_evidence_cut_digest": cut.cut_record_digest,
            "final_service_anchor_receipt_digest": (
                final_service_anchor_receipt.receipt_digest
            ),
            "generation_digest": contract.generation_digest,
            "predecessor_checkpoint_digest": (
                contract.predecessor_checkpoint.checkpoint_digest
            ),
            "promotion_contract_digest": contract.contract_digest,
            "requested_at": requested_at,
            "target_digest": contract.target_record.digest(),
            "target_protected_state_digest": (
                contract.target_protected_state_record.digest()
            ),
        },
    )


def _latest_cut_evidence_timestamp(cut: AtomicEvidenceCut) -> datetime:
    return max(
        (
            parse_canonical_timestamp(
                cut.target_protected_state_record.payload["observed_at"]
            ),
            parse_canonical_timestamp(cut.cut_record.payload["observed_at"]),
            *(
                parse_canonical_timestamp(
                    observation_record.payload["observed_at"]
                )
                for observation_record in cut.observation_records
            ),
            *(
                parse_canonical_timestamp(
                    evaluation.evaluation_record.payload["evaluated_at"]
                )
                for evaluation in cut.evaluations
            ),
            *(
                parse_canonical_timestamp(
                    attempt.terminal_record.payload["completed_at"]
                )
                for attempt in cut.attempts
            ),
            *(
                parse_canonical_timestamp(
                    operation.terminal_record.payload["completed_at"]
                )
                for operation in cut.operations
            ),
            *(
                parse_canonical_timestamp(edge.payload["verified_at"])
                for edge in cut.inclusion_edge_records
            ),
            *(
                parse_canonical_timestamp(
                    evaluation.trusted_time_observation_record.payload[
                        "observed_at"
                    ]
                )
                for evaluation in cut.evaluations
            ),
            *(
                parse_canonical_timestamp(
                    evaluation.invalidation_stream_checkpoint_record.payload[
                        "checkpointed_at"
                    ]
                )
                for evaluation in cut.evaluations
            ),
        )
    )


def _accepted_service_renewal_groups(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
) -> tuple[dict[str, object], ...]:
    """Partition and validate every accepted-cut service readiness renewal."""

    receipt = contract.service_anchor_receipt
    if not isinstance(receipt, ServiceAnchorReceipt):
        return ()
    authorization = receipt.observer_authorization_record
    separation = receipt.observer_separation_policy_record
    observer = receipt.observer_identity_record
    anchored_backend = receipt.backend_provenance_record.payload
    if not _authorization_admits_identity(
        authorization,
        separation,
        observer,
        action="observe_service",
        subject_kind="protected_state",
    ):
        _deny(
            "PROMOTION_TARGET_STATE_MISMATCH",
            "accepted service readiness lacks exact observer authority",
        )
    records = cut.observation_records
    groups: list[dict[str, object]] = []
    index = 0
    while index < len(records):
        backend_record = records[index]
        if backend_record.kind != "backend_provenance":
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted service readiness observations are not canonical contiguous groups",
            )
        index += 1
        health_records: list[ControlRecord] = []
        while index < len(records) and (
            records[index].kind == "service_health_observation"
        ):
            health_records.append(records[index])
            index += 1
        if (
            not health_records
            or index >= len(records)
            or records[index].kind != "readiness"
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted service readiness observations are incomplete",
            )
        readiness_record = records[index]
        index += 1
        backend = backend_record.payload
        readiness = readiness_record.payload
        health_digests = tuple(record.digest() for record in health_records)
        state_digest = backend["service_protected_state_digest"]
        epoch = backend["process_epoch"]
        common = {
            "generation_digest": contract.generation_digest,
            "process_epoch": epoch,
            "service_protected_state_digest": state_digest,
            "target_digest": receipt.target_record.digest(),
        }
        if any(
            backend[field] != anchored_backend[field]
            for field in _SERVICE_BACKEND_CONTINUITY_FIELDS
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted service readiness renewal substitutes anchored backend provenance",
            )
        if (
            backend["authorization_digest"] != authorization.digest()
            or backend["observer_identity_digest"] != observer.digest()
            or any(backend[field] != value for field, value in common.items())
            or readiness["backend_provenance_digest"] != backend_record.digest()
            or readiness["backend_manifest_digest"]
            != backend["backend_manifest_digest"]
            or readiness["status"] != "ready"
            or any(readiness[field] != value for field, value in common.items())
            or tuple(readiness["service_health_observation_digests"])
            != health_digests
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted service readiness renewal is not bound to one exact process epoch",
            )
        for health_record in health_records:
            health = health_record.payload
            if (
                health["authorization_digest"] != authorization.digest()
                or health["observer_identity_digest"] != observer.digest()
                or health["backend_provenance_digest"]
                != backend_record.digest()
                or health["status"] != "ready"
                or any(health[field] != value for field, value in common.items())
            ):
                _deny(
                    "PROMOTION_TARGET_STATE_MISMATCH",
                    "accepted service health renewal is substituted or cross-epoch",
                )
        backend_at = parse_canonical_timestamp(backend["observed_at"])
        health_times = tuple(
            parse_canonical_timestamp(record.payload["observed_at"])
            for record in health_records
        )
        readiness_at = parse_canonical_timestamp(readiness["observed_at"])
        if not (
            backend_at
            <= min(health_times)
            <= max(health_times)
            <= readiness_at
            <= parse_canonical_timestamp(cut.cut_record.payload["observed_at"])
        ) or readiness_at - backend_at > timedelta(seconds=300):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted service readiness renewal is stale or noncausal",
            )
        groups.append(
            {
                "backend_at": backend_at,
                "expires_at": readiness_at + timedelta(seconds=300),
                "process_epoch": epoch,
                "readiness_at": readiness_at,
                "records": (backend_record, *health_records, readiness_record),
                "state_digest": state_digest,
            }
        )
    return tuple(groups)


def _validate_cut_follows_predecessor(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
) -> None:
    predecessor_time = parse_canonical_timestamp(
        contract.predecessor_checkpoint.checkpoint_record.payload["established_at"]
    )
    phase_operation_digest = None
    if contract.phase is not PromotionPhase.ACCEPTED:
        phase_obligation_digest = contract.contract_record.payload[
            "phase_establishing_operation_obligation_digest"
        ]
        phase_operation_digest = next(
            obligation.operation_digest
            for obligation in contract.operation_obligations
            if obligation.obligation_digest == phase_obligation_digest
        )
    for attempt in cut.attempts:
        if (
            parse_canonical_timestamp(attempt.intent_record.payload["registered_at"])
            < predecessor_time
        ):
            _deny(
                "PROMOTION_PHASE_MISMATCH",
                "gate evidence cannot be registered before the exact predecessor checkpoint",
            )
    for operation in cut.operations:
        if (
            parse_canonical_timestamp(operation.intent_record.payload["registered_at"])
            < predecessor_time
        ):
            _deny(
                "PROMOTION_PHASE_MISMATCH",
                "critical operation cannot be registered before the exact predecessor checkpoint",
            )
    if contract.phase is PromotionPhase.ACCEPTED:
        scenario_operations = sorted(
            (
                operation
                for operation in cut.operations
                if operation.operation_record.payload["operation_kind"]
                == "blocking_scenario"
            ),
            key=lambda operation: operation.intent_record.payload["journal_sequence"],
        )
        service_receipt = contract.service_anchor_receipt
        service_anchor = (
            service_receipt.service_protected_state_record
            if isinstance(service_receipt, ServiceAnchorReceipt)
            else None
        )
        service_target = (
            service_receipt.target_record
            if isinstance(service_receipt, ServiceAnchorReceipt)
            else None
        )
        lease_expires_at = (
            parse_canonical_timestamp(
                service_receipt.receipt_record.payload["expires_at"]
            )
            if isinstance(service_receipt, ServiceAnchorReceipt)
            else None
        )
        lease_epoch = (
            service_receipt.service_protected_state_record.payload.get(
                "process_epoch"
            )
            if isinstance(service_receipt, ServiceAnchorReceipt)
            else None
        )
        lease_readiness_at = (
            parse_canonical_timestamp(
                service_receipt.readiness_record.payload["observed_at"]
            )
            if isinstance(service_receipt, ServiceAnchorReceipt)
            else None
        )
        last_renewal_readiness_at = lease_readiness_at
        purpose_by_operation_digest = {
            obligation.operation_digest: obligation.requirement.requirement_record.payload[
                "purpose"
            ]
            for obligation in contract.operation_obligations
        }
        if scenario_operations and (
            type(service_anchor) is not ControlRecord
            or type(service_target) is not ControlRecord
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted scenarios require exact active-service anchor material",
            )
        renewal_groups = _accepted_service_renewal_groups(
            contract,
            cut,
        )
        renewal_index = 0
        previous_state = service_anchor
        previous_terminal_time: datetime | None = None
        for operation in cut.operations:
            payload = operation.operation_record.payload
            if payload["lifecycle_phase"] == PromotionPhase.ACCEPTED.value:
                _deny(
                    "PROMOTION_PHASE_MISMATCH",
                    "accepted cuts cannot relabel critical operations as accepted-phase work",
                )
        for operation in scenario_operations:
            payload = operation.operation_record.payload
            assert type(previous_state) is ControlRecord
            assert type(service_target) is ControlRecord
            expected_state = operation.expected_protected_state_record.payload
            intended_state = operation.intended_protected_state_record.payload
            purpose = purpose_by_operation_digest.get(operation.operation_digest)
            if purpose is None:
                _deny(
                    "PROMOTION_OPERATION_BINDING_MISMATCH",
                    "accepted service operation is absent from the exact contract",
                )
            restart = purpose in {"service_restart", "final_service_restart"}
            registered_at = parse_canonical_timestamp(
                operation.intent_record.payload["registered_at"]
            )
            capability_issued_at = parse_canonical_timestamp(
                operation.capability_record.payload["issued_at"]
            )
            current_epoch = expected_state.get("process_epoch")
            while (
                lease_expires_at is None
                or lease_epoch != current_epoch
                or max(registered_at, capability_issued_at) > lease_expires_at
            ):
                if renewal_index >= len(renewal_groups):
                    _deny(
                        "PROMOTION_TARGET_STATE_MISMATCH",
                        "accepted closeout lacks fresh exact service readiness before dependent scenario work",
                    )
                group = renewal_groups[renewal_index]
                renewal_index += 1
                if (
                    group["state_digest"] != previous_state.digest()
                    or group["process_epoch"] != current_epoch
                    or group["backend_at"]
                    <= (
                        previous_terminal_time
                        if previous_terminal_time is not None
                        else predecessor_time
                    )
                    or (
                        last_renewal_readiness_at is not None
                        and group["backend_at"]
                        <= last_renewal_readiness_at
                    )
                    or group["readiness_at"] >= registered_at
                ):
                    _deny(
                        "PROMOTION_TARGET_STATE_MISMATCH",
                        "accepted closeout service readiness renewal is stale, substituted, or cross-epoch",
                    )
                lease_epoch = group["process_epoch"]
                lease_expires_at = group["expires_at"]
                lease_readiness_at = group["readiness_at"]
                last_renewal_readiness_at = group["readiness_at"]
            terminal_at = parse_canonical_timestamp(
                operation.terminal_record.payload["completed_at"]
            )
            if lease_readiness_at is None or lease_readiness_at >= registered_at:
                _deny(
                    "PROMOTION_TARGET_STATE_MISMATCH",
                    "accepted closeout service readiness must strictly precede dependent scenario intent",
                )
            while lease_expires_at is None or terminal_at > lease_expires_at:
                if renewal_index >= len(renewal_groups):
                    _deny(
                        "PROMOTION_TARGET_STATE_MISMATCH",
                        "accepted closeout service readiness does not cover dependent scenario work through its terminal",
                    )
                group = renewal_groups[renewal_index]
                renewal_index += 1
                if (
                    group["state_digest"] != previous_state.digest()
                    or group["process_epoch"] != current_epoch
                    or group["backend_at"]
                    <= max(
                        previous_terminal_time
                        if previous_terminal_time is not None
                        else predecessor_time,
                        lease_readiness_at,
                    )
                    or group["readiness_at"] == registered_at
                    or group["readiness_at"] >= terminal_at
                    or group["readiness_at"] > lease_expires_at
                ):
                    _deny(
                        "PROMOTION_TARGET_STATE_MISMATCH",
                        "accepted closeout service readiness renewal does not continuously cover one exact scenario attempt",
                    )
                lease_epoch = group["process_epoch"]
                lease_expires_at = group["expires_at"]
                lease_readiness_at = group["readiness_at"]
                last_renewal_readiness_at = group["readiness_at"]
            if (
                payload["lifecycle_phase"] != PromotionPhase.ACTIVE.value
                or payload["target_kind"] != OperationTargetKind.SERVICE.value
                or operation.target_record.digest() != service_target.digest()
                or operation.expected_protected_state_record.digest()
                != previous_state.digest()
                or expected_state["generation_digest"]
                != contract.generation_digest
                or intended_state["generation_digest"]
                != contract.generation_digest
                or expected_state["lifecycle_phase"]
                != PromotionPhase.ACTIVE.value
                or intended_state["lifecycle_phase"]
                != PromotionPhase.ACTIVE.value
                or expected_state["target_kind"]
                != OperationTargetKind.SERVICE.value
                or intended_state["target_kind"]
                != OperationTargetKind.SERVICE.value
                or expected_state.get("process_epoch")
                != previous_state.payload.get("process_epoch")
                or restart
                != (
                    intended_state.get("process_epoch")
                    != expected_state.get("process_epoch")
                )
                or expected_state["projection_id"]
                != previous_state.payload["projection_id"]
                or intended_state["projection_id"]
                != previous_state.payload["projection_id"]
                or expected_state["fence_epoch"]
                != previous_state.payload["fence_epoch"]
                or intended_state["fence_epoch"]
                != previous_state.payload["fence_epoch"] + 1
                or parse_canonical_timestamp(previous_state.payload["observed_at"])
                > registered_at
                or (
                    previous_terminal_time is not None
                    and previous_terminal_time > registered_at
                )
            ):
                _deny(
                    "PROMOTION_TARGET_STATE_MISMATCH",
                    "accepted closeout scenario does not bind the exact candidate active-service fence",
                )
            previous_state = operation.intended_protected_state_record
            previous_terminal_time = terminal_at
            if restart:
                lease_epoch = None
                lease_expires_at = None
                lease_readiness_at = None
        if scenario_operations:
            if renewal_index >= len(renewal_groups):
                _deny(
                    "PROMOTION_TARGET_STATE_MISMATCH",
                    "accepted closeout lacks final post-restart service readiness",
                )
            final_group = renewal_groups[renewal_index]
            renewal_index += 1
            assert type(previous_state) is ControlRecord
            if (
                previous_terminal_time is None
                or final_group["state_digest"] != previous_state.digest()
                or final_group["process_epoch"]
                != previous_state.payload.get("process_epoch")
                or final_group["backend_at"] <= previous_terminal_time
                or (
                    last_renewal_readiness_at is not None
                    and final_group["backend_at"]
                    <= last_renewal_readiness_at
                )
            ):
                _deny(
                    "PROMOTION_TARGET_STATE_MISMATCH",
                    "accepted closeout final service readiness is substituted or cross-epoch",
                )
        if renewal_index != len(renewal_groups):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "accepted closeout contains unused service readiness observations",
            )
        return
    if phase_operation_digest is None:
        return
    phase_operation = next(
        (
            operation
            for operation in cut.operations
            if operation.operation_digest == phase_operation_digest
        ),
        None,
    )
    if phase_operation is None:
        _deny(
            "PROMOTION_OPERATION_BINDING_MISMATCH",
            "phase-establishing operation is absent from the exact cut",
        )
    intended_state = contract.target_protected_state_record
    expected_phase_state = phase_operation.expected_protected_state_record
    if contract.phase is PromotionPhase.ACTIVE:
        receipt = contract.baseline_restoration_receipt
        assert isinstance(receipt, BaselineRestorationReceipt)
        expected_phase_state = receipt.restored_protected_state_record
    elif contract.phase is PromotionPhase.PREVALIDATED:
        captured_state = _captured_baseline(
            contract.predecessor_checkpoint
        ).target_protected_state_record.payload
        phase_expected = phase_operation.expected_protected_state_record.payload
        if (
            phase_expected["generation_digest"]
            != captured_state["generation_digest"]
            or phase_expected["target_digest"] != contract.target_record.digest()
            or phase_expected["target_kind"]
            != OperationTargetKind.ISOLATED_ROOT.value
            or phase_expected["projection_id"] != captured_state["projection_id"]
            or phase_expected["state_digest"] != captured_state["state_digest"]
        ):
            _deny(
                "PROMOTION_TARGET_STATE_MISMATCH",
                "prevalidated installation is not rooted in the captured B0 state",
            )
        expected_phase_state = phase_operation.expected_protected_state_record
    if (
        phase_operation.expected_protected_state_record.digest()
        != expected_phase_state.digest()
        or phase_operation.intended_protected_state_record.digest()
        != intended_state.digest()
        or phase_operation.capability_record.payload["fence_epoch"]
        != intended_state.payload["fence_epoch"]
        or expected_phase_state.payload["projection_id"]
        != intended_state.payload["projection_id"]
        or expected_phase_state.payload["fence_epoch"] + 1
        != intended_state.payload["fence_epoch"]
    ):
        _deny(
            "PROMOTION_TARGET_STATE_MISMATCH",
            "phase operation does not advance the exact predecessor protected state",
        )


def _validate_acceptance_material(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
    final_service_anchor_receipt: FinalServiceAnchorReceipt | None,
    request_record: ControlRecord,
    approval_record: ControlRecord,
) -> None:
    request = _record(
        request_record,
        field="acceptance_request",
        kind="acceptance_request",
    ).payload
    approval = _record(
        approval_record,
        field="acceptance approval",
        kind="approval",
    ).payload
    if (
        not isinstance(final_service_anchor_receipt, FinalServiceAnchorReceipt)
        or not _canonical_graph_equivalent(
            final_service_anchor_receipt.promotion_contract,
            contract,
        )
        or not _canonical_graph_equivalent(
            final_service_anchor_receipt.evidence_cut,
            cut,
        )
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "acceptance material does not bind the exact final service anchor",
        )
    predecessor_time = parse_canonical_timestamp(
        contract.predecessor_checkpoint.checkpoint_record.payload["established_at"]
    )
    expected_request = {
        "acceptance_authorization_digest": contract.contract_record.payload[
            "acceptance_authorization_digest"
        ],
        "atomic_evidence_cut_digest": cut.cut_record_digest,
        "final_service_anchor_receipt_digest": (
            final_service_anchor_receipt.receipt_digest
        ),
        "generation_digest": contract.generation_digest,
        "predecessor_checkpoint_digest": (
            contract.predecessor_checkpoint.checkpoint_digest
        ),
        "promotion_contract_digest": contract.contract_digest,
        "target_digest": contract.target_record.digest(),
        "target_protected_state_digest": (
            contract.target_protected_state_record.digest()
        ),
    }
    if any(request[field] != value for field, value in expected_request.items()):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "acceptance request does not bind the exact contract, cut, predecessor, generation, target, and authorization",
        )
    requested_at = parse_canonical_timestamp(request["requested_at"])
    if requested_at < max(
        predecessor_time,
        _latest_cut_evidence_timestamp(cut),
        parse_canonical_timestamp(
            final_service_anchor_receipt.receipt_record.payload["issued_at"]
        ),
    ) or requested_at > final_service_anchor_receipt.expires_at:
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "acceptance request cannot precede its complete evidence cut",
        )
    authorization = _record(
        contract.acceptance_authorization_record,
        field="acceptance_authorization_record",
        kind="authorization",
    )
    separation = _record(
        contract.acceptance_separation_policy_record,
        field="acceptance_separation_policy_record",
        kind="separation_policy",
    )
    actor = _record(
        contract.acceptance_actor_identity_record,
        field="acceptance_actor_identity_record",
        kind="identity",
    )
    if (
        approval["action"] != "accept_generation"
        or approval["decision"] != "approved"
        or approval["subject_digest"] != request_record.digest()
        or approval["authorization_digest"]
        != request["acceptance_authorization_digest"]
        or approval["actor_identity_digest"] != actor.digest()
        or not _authorization_admits_actor(
            authorization,
            separation,
            actor,
            actor_identity_digest=approval["actor_identity_digest"],
            actor_role=approval["actor_role"],
            action="accept_generation",
            subject_kind="acceptance_request",
            require_approver_role=True,
        )
        or parse_canonical_timestamp(approval["decided_at"]) < requested_at
        or parse_canonical_timestamp(approval["decided_at"])
        > final_service_anchor_receipt.expires_at
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "acceptance approval does not approve the exact request after it exists",
        )


def admit_promotion(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
    predecessor_checkpoint: LifecycleCheckpoint,
    authority: object,
    *,
    acceptance_request: ControlRecord | None = None,
    approval: ControlRecord | None = None,
    final_service_anchor_receipt: FinalServiceAnchorReceipt | None = None,
    baseline_restoration_receipt: BaselineRestorationReceipt | None = None,
    service_anchor_receipt: ServiceAnchorReceipt | None = None,
    checkpoint_id: str,
    established_at: str,
) -> LifecycleCheckpoint:
    """Admit after production proof and an authority-issued predecessor.

    W0 intentionally exposes no root-authority bootstrap. A structural B0
    capture can be assessed, but cannot start an authoritative lifecycle.
    """

    assess_promotion_cut(contract, cut)
    if contract.phase is PromotionPhase.ACCEPTED:
        if acceptance_request is None or approval is None:
            _deny(
                "PROMOTION_PHASE_MISMATCH",
                "accepted admission requires an exact request and approval",
            )
        _validate_acceptance_material(
            contract,
            cut,
            final_service_anchor_receipt,
            acceptance_request,
            approval,
        )
    elif (
        acceptance_request is not None
        or approval is not None
        or final_service_anchor_receipt is not None
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "nonaccepted admission forbids acceptance request and approval",
        )
    if not isinstance(predecessor_checkpoint, LifecycleCheckpoint) or (
        not _is_authority_issued_checkpoint(predecessor_checkpoint)
    ):
        raise NonPromotionalEvidence(
            "EVIDENCE_NONPROMOTIONAL",
            "admission requires an authority-admitted predecessor; W0 provides no root-authority bootstrap",
        )
    if not _canonical_lifecycle_graph_equivalent(
        contract.predecessor_checkpoint,
        predecessor_checkpoint,
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "admission does not bind the contract's exact authoritative predecessor checkpoint",
        )
    if not isinstance(authority, PromotionAuthority):
        raise NonPromotionalEvidence(
            "EVIDENCE_NONPROMOTIONAL",
            "authority cannot independently verify an exact promotion cut",
        )
    challenge = PromotionAuthorityChallenge.from_cut(
        contract,
        cut,
        authority_adapter_identity_digest=(
            authority.authority_adapter_identity_digest
        ),
        authority_view_digest=authority.authority_view_digest,
        predecessor_checkpoint=predecessor_checkpoint,
        acceptance_request_record=acceptance_request,
        approval_record=approval,
        final_service_anchor_receipt=final_service_anchor_receipt,
    )
    proof_record = authority.verify_promotion_cut(challenge)
    _verify_authority_proof(proof_record, challenge)
    proof_verified_at = parse_canonical_timestamp(
        proof_record.payload["verified_at"]
    )
    if proof_verified_at < _latest_cut_evidence_timestamp(cut) or (
        approval is not None
        and proof_verified_at
        < parse_canonical_timestamp(approval.payload["decided_at"])
    ) or (
        final_service_anchor_receipt is not None
        and proof_verified_at > final_service_anchor_receipt.expires_at
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "authority proof cannot precede its complete cut or acceptance approval",
        )
    try:
        _validate_admission_currentness(cut, boundary=proof_verified_at)
    except ValueError:
        _deny(
            "PROMOTION_EVIDENCE_NOT_CURRENT",
            "promotion evidence is not current at authority-proof issuance",
        )
    established = parse_canonical_timestamp(established_at)
    if (
        established < proof_verified_at
        or established
        < parse_canonical_timestamp(
            predecessor_checkpoint.checkpoint_record.payload["established_at"]
        )
        or (
            approval is not None
            and established
            < parse_canonical_timestamp(approval.payload["decided_at"])
        )
        or (
            final_service_anchor_receipt is not None
            and established > final_service_anchor_receipt.expires_at
        )
    ):
        _deny(
            "PROMOTION_PHASE_MISMATCH",
            "lifecycle checkpoint cannot precede its proof, predecessor, or approval",
        )
    try:
        _validate_admission_currentness(cut, boundary=established)
    except ValueError:
        _deny(
            "PROMOTION_EVIDENCE_NOT_CURRENT",
            "promotion evidence is not current at checkpoint issuance",
        )
    require_promotable(authority)
    checkpoint_record = ControlRecord.build(
        kind="lifecycle_checkpoint",
        record_id=f"lifecycle-checkpoint:{checkpoint_id}",
        payload={
            "authority_proof_digest": proof_record.digest(),
            "checkpoint_id": checkpoint_id,
            "contract_digest": contract.contract_digest,
            "evidence_cut_digest": cut.cut_record_digest,
            "established_at": established_at,
            "generation_class": "c",
            "generation_digest": contract.generation_digest,
            "phase": contract.phase.value,
            "predecessor_checkpoint_digest": predecessor_checkpoint.checkpoint_digest,
            "target_digest": contract.target_record.digest(),
            "target_protected_state_digest": (
                contract.target_protected_state_record.digest()
            ),
            **(
                {
                    "acceptance_request_digest": acceptance_request.digest(),
                    "approval_digest": approval.digest(),
                    "final_service_anchor_receipt_digest": (
                        final_service_anchor_receipt.receipt_digest
                    ),
                }
                if acceptance_request is not None
                and approval is not None
                and final_service_anchor_receipt is not None
                else {}
            ),
            **(
                {
                    "baseline_restoration_receipt_digest": (
                        baseline_restoration_receipt.receipt_digest
                    )
                }
                if baseline_restoration_receipt is not None
                else {}
            ),
            **(
                {
                    "service_anchor_receipt_digest": (
                        service_anchor_receipt.receipt_digest
                    )
                }
                if service_anchor_receipt is not None
                else {}
            ),
        },
    )
    return _issue_lifecycle_checkpoint(
        checkpoint_record=checkpoint_record,
        generation_record=contract.generation_record,
        target_record=contract.target_record,
        target_protected_state_record=contract.target_protected_state_record,
        predecessor_checkpoint=predecessor_checkpoint,
        promotion_contract=contract,
        evidence_cut=cut,
        authority_proof_record=proof_record,
        acceptance_request_record=acceptance_request,
        approval_record=approval,
        final_service_anchor_receipt=final_service_anchor_receipt,
        baseline_restoration_receipt=baseline_restoration_receipt,
        service_anchor_receipt=service_anchor_receipt,
    )
