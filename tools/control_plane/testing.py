"""Deterministic nonpromotional adapters for repository behavioral tests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ._authority import (
    AuthorityUnavailable,
    NonPromotionalEvidenceView,
    NonPromotionalReceipt,
    OperationBinding,
)


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    kind: str
    operation_id: str | None
    record_digest: str
    active_digest: str | None


class InMemoryAuthority:
    """A strict in-memory adapter that can never produce promotional evidence."""

    adapter_id = "in_memory_nonpromotional_v1"

    def __init__(self, *, initial_active_digest: str | None = None) -> None:
        self._active_digest = initial_active_digest
        self._entries: list[JournalEntry] = []
        self._receipts: list[NonPromotionalReceipt] = []
        self._pending: dict[str, OperationBinding] = {}
        self._consumed: set[str] = set()
        self._last_fence_epoch = 0

    @property
    def journal_entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def observe_active(self) -> str:
        if self._active_digest is None:
            raise AuthorityUnavailable(
                "AUTHORITY_OBSERVATION_MISSING",
                "the fake has no configured active-state observation",
            )
        return self._active_digest

    def append_record(
        self,
        record_digest: str,
        *,
        kind: str = "evidence_record",
    ) -> NonPromotionalReceipt:
        return self._append(
            kind=kind,
            operation_id=None,
            record_digest=record_digest,
        )

    def append_intent(self, binding: OperationBinding) -> NonPromotionalReceipt:
        if binding.operation_id in self._pending or binding.operation_id in self._consumed:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_DUPLICATE",
                f"operation {binding.operation_id!r} is already registered",
            )
        self._pending[binding.operation_id] = binding
        return self._append(
            kind="operation_intent",
            operation_id=binding.operation_id,
            record_digest=binding.intent_digest,
        )

    def guarded_compare_and_swap(
        self,
        binding: OperationBinding,
    ) -> NonPromotionalReceipt:
        registered = self._pending.get(binding.operation_id)
        if registered is None:
            raise AuthorityUnavailable(
                "AUTHORITY_INTENT_MISSING",
                f"operation {binding.operation_id!r} has no registered intent",
            )
        if registered != binding:
            raise AuthorityUnavailable(
                "AUTHORITY_BINDING_MISMATCH",
                "the transition binding differs from its registered intent",
            )
        if binding.fence_epoch <= self._last_fence_epoch:
            self._append_precheck_failure(binding, "AUTHORITY_FENCE_STALE")
            raise AuthorityUnavailable(
                "AUTHORITY_FENCE_STALE",
                "the operation fence does not advance the target epoch",
            )
        active = self.observe_active()
        if active != binding.expected_state_digest:
            self._append_precheck_failure(binding, "AUTHORITY_PRESTATE_MISMATCH")
            raise AuthorityUnavailable(
                "AUTHORITY_PRESTATE_MISMATCH",
                "the observed state does not match the intent's expected state",
            )
        self._active_digest = binding.intended_state_digest
        self._last_fence_epoch = binding.fence_epoch
        self._pending.pop(binding.operation_id)
        self._consumed.add(binding.operation_id)
        return self._append(
            kind="guarded_transition",
            operation_id=binding.operation_id,
            record_digest=binding.intended_state_digest,
        )

    def evidence_view(self) -> NonPromotionalEvidenceView:
        return NonPromotionalEvidenceView(
            adapter_id=self.adapter_id,
            receipts=tuple(self._receipts),
        )

    def _append_precheck_failure(
        self,
        binding: OperationBinding,
        code: str,
    ) -> NonPromotionalReceipt:
        material = "\0".join(
            (binding.intent_digest, binding.operation_id, code)
        ).encode("utf-8")
        failure_digest = "sha256:" + hashlib.sha256(material).hexdigest()
        return self._append(
            kind="precheck_failed",
            operation_id=binding.operation_id,
            record_digest=failure_digest,
        )

    def _append(
        self,
        *,
        kind: str,
        operation_id: str | None,
        record_digest: str,
    ) -> NonPromotionalReceipt:
        sequence = len(self._entries) + 1
        receipt_material = "\0".join(
            (
                self.adapter_id,
                str(sequence),
                kind,
                operation_id or "",
                record_digest,
            )
        ).encode("utf-8")
        receipt_id = "sha256:" + hashlib.sha256(receipt_material).hexdigest()
        entry = JournalEntry(
            sequence=sequence,
            kind=kind,
            operation_id=operation_id,
            record_digest=record_digest,
            active_digest=self._active_digest,
        )
        receipt = NonPromotionalReceipt(
            receipt_id=receipt_id,
            sequence=sequence,
            kind=kind,
            operation_id=operation_id,
            record_digest=record_digest,
        )
        self._entries.append(entry)
        self._receipts.append(receipt)
        return receipt


__all__ = ["InMemoryAuthority", "JournalEntry"]
