"""Canonical, non-authoritative promotion assessment at one evidence cut."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ._authority import ControlAuthorityError, OperationTarget, OperationTargetKind
from ._authority import require_promotable
from ._evaluation import GateImpact
from ._records import ControlRecord


def _record(value: object, *, field: str, kind: str) -> ControlRecord:
    if not isinstance(value, ControlRecord):
        raise TypeError(f"{field} must be a ControlRecord")
    if value.kind != kind:
        raise ValueError(f"{field} must be a canonical {kind} record")
    return value


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


class PromotionPhase(StrEnum):
    PUBLISHED = "published"
    PREVALIDATED = "prevalidated"
    ACTIVE = "active"
    ACCEPTED = "accepted"


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


@dataclass(frozen=True, slots=True)
class PromotionContract:
    """Canonical requirements and total obligation set for one promotion phase."""

    requirements_record: ControlRecord
    generation_record: ControlRecord
    target_record: ControlRecord
    target_protected_state_record: ControlRecord
    contract_record: ControlRecord
    obligations: tuple[PromotionObligation, ...]

    def __post_init__(self) -> None:
        _record(self.requirements_record, field="requirements_record", kind="requirements")
        _record(self.generation_record, field="generation_record", kind="generation")
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
        obligations = tuple(self.obligations)
        object.__setattr__(self, "obligations", obligations)
        if not obligations or any(
            not isinstance(item, PromotionObligation) for item in obligations
        ):
            raise ValueError("obligations must contain PromotionObligation values")
        obligation_digests = tuple(item.obligation_digest for item in obligations)
        if len(obligation_digests) != len(set(obligation_digests)):
            raise ValueError("contract contains duplicate obligations")

        payload = self.contract_record.payload
        expected = {
            "requirements_digest": self.requirements_record.digest(),
            "generation_digest": self.generation_record.digest(),
            "target_digest": self.target_record.digest(),
            "target_protected_state_digest": self.target_protected_state_record.digest(),
            "obligation_digests": obligation_digests,
        }
        for field, value in expected.items():
            actual = tuple(payload[field]) if field == "obligation_digests" else payload[field]
            if actual != value:
                raise ValueError(f"promotion contract does not bind exact {field}")
        state = self.target_protected_state_record.payload
        if state["target_digest"] != self.target_record.digest():
            raise ValueError("contract protected state does not bind target")
        if state["generation_digest"] != payload["expected_active_generation_digest"]:
            raise ValueError("contract protected state does not bind expected active generation")

        candidate = self.generation_record.digest()
        accepted = payload["expected_accepted_generation_digest"]
        active = payload["expected_active_generation_digest"]
        phase = PromotionPhase(payload["phase"])
        if phase is PromotionPhase.ACCEPTED and (accepted != candidate or active != candidate):
            raise ValueError("accepted phase requires accepted and active candidate generation")
        if phase is PromotionPhase.ACTIVE and active != candidate:
            raise ValueError("active phase requires the active candidate generation")
        if phase in {PromotionPhase.PUBLISHED, PromotionPhase.PREVALIDATED} and (
            accepted != active or active == candidate
        ):
            raise ValueError("pre-activation phases must preserve one prior generation")

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
        if not intent["registered_at"] <= attempt["started_at"] <= terminal["completed_at"]:
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
class BoundEvaluation:
    """A canonical evaluation and every record used to derive it."""

    attempt_record: ControlRecord
    context_record: ControlRecord
    assignment_record: ControlRecord
    evidence_records: tuple[ControlRecord, ...]
    evaluation_record: ControlRecord
    inclusion_edge_record: ControlRecord | None = None

    def __post_init__(self) -> None:
        _record(self.attempt_record, field="attempt_record", kind="attempt")
        _record(self.context_record, field="context_record", kind="validation_context")
        _record(self.assignment_record, field="assignment_record", kind="assignment")
        _record(self.evaluation_record, field="evaluation_record", kind="evaluation")
        evidence_records = tuple(self.evidence_records)
        object.__setattr__(self, "evidence_records", evidence_records)
        assignment = self.assignment_record.payload
        evaluation = self.evaluation_record.payload
        context_digest = self.context_record.digest()
        assignment_digest = self.assignment_record.digest()
        if assignment["context_digest"] != context_digest:
            raise ValueError("assignment does not bind validation context")
        if self.attempt_record.payload["assignment_digest"] != assignment_digest:
            raise ValueError("attempt does not bind assignment")
        if self.attempt_record.payload["context_digest"] != context_digest:
            raise ValueError("attempt does not bind validation context")
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
        if applicability == "applicable":
            if not evidence_records:
                raise ValueError("applicable evaluation requires attestations")
            for evidence in evidence_records:
                _record(evidence, field="evidence_records item", kind="attestation")
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
                if _moment(payload["observed_at"]) > _moment(evaluation["evaluated_at"]):
                    raise ValueError("evaluation cannot precede an attestation")
            if tuple(evaluation["attestation_digests"]) != tuple(
                item.digest() for item in evidence_records
            ):
                raise ValueError("evaluation does not bind exact attestation set")
        elif applicability == "not_applicable":
            if len(evidence_records) != 1:
                raise ValueError("not-applicable evaluation requires one predicate proof")
            proof = _record(
                evidence_records[0],
                field="evidence_records item",
                kind="predicate_proof",
            )
            payload = proof.payload
            if assignment["applicability"] != "conditional":
                raise ValueError("unconditional assignment cannot be non-applicable")
            if payload["is_applicable"]:
                raise ValueError("not-applicable predicate proof must prove false")
            if payload["predicate_digest"] != assignment["predicate_digest"]:
                raise ValueError("predicate proof does not bind assignment predicate")
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
                    raise ValueError(f"predicate proof does not bind assignment {field}")
            if evaluation["predicate_proof_digest"] != proof.digest():
                raise ValueError("evaluation does not bind predicate proof")
            if _moment(payload["observed_at"]) > _moment(evaluation["evaluated_at"]):
                raise ValueError("evaluation cannot precede predicate proof")
        elif evidence_records:
            raise ValueError("unknown or not-due evaluation cannot bind terminal evidence")

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

    @property
    def assignment_digest(self) -> str:
        return self.assignment_record.digest()

    @property
    def attempt_digest(self) -> str:
        return self.attempt_record.digest()

    @property
    def evaluation_record_digest(self) -> str:
        return self.evaluation_record.digest()


def registration_set_digest(attempts: tuple[RegisteredAttempt, ...]) -> str:
    """Bind the complete canonical intent/attempt/terminal registration set."""

    attempts = tuple(attempts)
    material = bytearray(b"arch-strix-halo/promotion-registration-set/v2\x00")
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
    return "sha256:" + hashlib.sha256(material).hexdigest()


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
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "evaluations", evaluations)
        object.__setattr__(self, "inclusion_edge_records", edges)
        if any(not isinstance(item, RegisteredAttempt) for item in attempts):
            raise TypeError("attempts must contain RegisteredAttempt values")
        if any(not isinstance(item, BoundEvaluation) for item in evaluations):
            raise TypeError("evaluations must contain BoundEvaluation values")
        for edge in edges:
            _record(edge, field="inclusion_edge_records item", kind="inclusion_edge")
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
            "inclusion_edge_digests": tuple(item.digest() for item in edges),
            "registration_set_digest": registration_set_digest(attempts),
        }
        for field, value in expected.items():
            actual = tuple(payload[field]) if field.endswith("_digests") else payload[field]
            if actual != value:
                raise ValueError(f"atomic cut does not bind exact {field}")
        state = self.target_protected_state_record.payload
        if state["target_digest"] != self.target_record.digest():
            raise ValueError("cut protected state does not bind target")
        if state["generation_digest"] != self.active_generation_record.digest():
            raise ValueError("cut protected state does not bind active generation")
        if any(
            item.terminal_sequence > payload["complete_through_sequence"]
            for item in attempts
        ):
            raise ValueError("cut does not include every terminal sequence")

    @property
    def cut_record_digest(self) -> str:
        return self.cut_record.digest()

    @property
    def phase(self) -> PromotionPhase:
        return PromotionPhase(self.cut_record.payload["phase"])


@dataclass(frozen=True, slots=True)
class PromotionCutAssessment:
    """Semantic result; authoritative only after a production authority check."""

    contract_digest: str
    generation_digest: str
    phase: PromotionPhase
    cut_record_digest: str
    obligation_evaluation_digests: tuple[str, ...]
    authoritative: bool = False


class PromotionDenied(ControlAuthorityError):
    """The canonical cut cannot satisfy every promotion obligation."""


def _deny(code: str, message: str) -> None:
    raise PromotionDenied(code, message)


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

    evaluation_digests: list[str] = []
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
        ):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "records bind different obligation coordinates",
            )
        terminal_evidence = tuple(
            attempt.terminal_record.payload["validator_attestation_digests"]
        )
        if terminal_evidence != tuple(item.digest() for item in bound.evidence_records):
            _deny(
                "PROMOTION_EVIDENCE_BINDING_MISMATCH",
                "terminal does not bind evaluated evidence",
            )

        context = bound.context_record.payload
        if context["context_type"] == "active_contract":
            if (
                context["contract_digest"] != contract.requirements_record.digest()
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
                != contract.requirements_record.digest()
                or edge_payload["generation_digest"] != contract.generation_digest
            ):
                _deny(
                    "PROMOTION_INCLUSION_EDGE_MISMATCH",
                    "inclusion edge does not bind active contract generation",
                )
            expected_edges.add(edge.digest())

        evaluation = bound.evaluation_record.payload
        if evaluation["currency"] != "current" or not evaluation["admissible"]:
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
    if {item.digest() for item in cut.inclusion_edge_records} != expected_edges:
        _deny("PROMOTION_INCLUSION_EDGE_MISMATCH", "cut inclusion-edge set is not exact")
    return PromotionCutAssessment(
        contract_digest=contract.contract_digest,
        generation_digest=contract.generation_digest,
        phase=contract.phase,
        cut_record_digest=cut.cut_record_digest,
        obligation_evaluation_digests=tuple(evaluation_digests),
    )


def admit_promotion(
    contract: PromotionContract,
    cut: AtomicEvidenceCut,
    evidence_view: object,
) -> PromotionCutAssessment:
    """Admit only after the production authority proves cut provenance."""

    require_promotable(evidence_view)
    return replace(assess_promotion_cut(contract, cut), authoritative=True)
