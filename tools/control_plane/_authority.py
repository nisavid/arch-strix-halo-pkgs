from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Protocol, runtime_checkable


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z")
_GENERATION_BINDINGS = {
    "required_generation",
    "b0_capture_sentinel",
    "no_generation",
    "emergency_root",
}


class ControlAuthorityError(RuntimeError):
    """Base error with a stable machine-readable failure code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class AuthorityUnavailable(ControlAuthorityError):
    """The requested authority observation or operation cannot be proven."""


class ForbiddenAuthoritySubstrate(ControlAuthorityError):
    """A mutable or target-local source was offered as production authority."""


class NonPromotionalEvidence(ControlAuthorityError):
    """Evidence is structurally useful but cannot authorize promotion."""


class AuthorityRole(StrEnum):
    SIGNER = "signer"
    EVIDENCE_STORE = "evidence_store"
    JOURNAL = "journal"
    COMPOSITE_REGISTER = "composite_register"
    WITNESS_QUORUM = "witness_quorum"
    FENCED_TARGET_LEASE = "fenced_target_lease"
    RECOVERY_ROOT = "recovery_root"
    TRUSTED_TIME = "trusted_time"


@dataclass(frozen=True)
class SubstrateBinding:
    """A declared provider for one production authority role.

    This is configuration identity, not proof that the provider is approved or
    authoritative. ``production_authority`` remains unavailable until a
    concrete adapter verifies that proof independently.
    """

    role: AuthorityRole
    provider: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, AuthorityRole):
            raise TypeError("role must be an AuthorityRole")
        if not isinstance(self.provider, str) or not _IDENTIFIER_RE.fullmatch(
            self.provider
        ):
            raise ValueError(
                "provider must be a lowercase identifier using '-' or '_' separators"
            )


@dataclass(frozen=True)
class ProductionTopology:
    bindings: tuple[SubstrateBinding, ...]

    def __post_init__(self) -> None:
        bindings = tuple(self.bindings)
        object.__setattr__(self, "bindings", bindings)
        roles = [binding.role for binding in bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("production topology contains duplicate authority roles")


@dataclass(frozen=True)
class OperationBinding:
    """Exact identity and state coordinates for one guarded operation."""

    operation_id: str
    intent_digest: str
    plan_digest: str
    subject_digest: str
    target_id: str
    expected_state_digest: str
    intended_state_digest: str
    generation_binding: str
    rollback_target_digest: str
    fence_epoch: int

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not _IDENTIFIER_RE.fullmatch(
            self.operation_id
        ):
            raise ValueError("operation_id must be a lowercase stable identifier")
        if not isinstance(self.target_id, str) or not _IDENTIFIER_RE.fullmatch(
            self.target_id
        ):
            raise ValueError("target_id must be a lowercase stable identifier")
        for field_name in (
            "intent_digest",
            "plan_digest",
            "subject_digest",
            "expected_state_digest",
            "intended_state_digest",
            "rollback_target_digest",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"{field_name} must be a canonical sha256 digest")
        if self.generation_binding not in _GENERATION_BINDINGS:
            choices = ", ".join(sorted(_GENERATION_BINDINGS))
            raise ValueError(f"generation_binding must be one of: {choices}")
        if (
            not isinstance(self.fence_epoch, int)
            or isinstance(self.fence_epoch, bool)
            or self.fence_epoch <= 0
        ):
            raise ValueError("fence_epoch must be a positive integer")


@dataclass(frozen=True)
class NonPromotionalReceipt:
    receipt_id: str
    sequence: int
    kind: str
    operation_id: str | None
    record_digest: str


@dataclass(frozen=True)
class NonPromotionalEvidenceView:
    """Evidence view produced by deterministic local or test adapters."""

    adapter_id: str
    receipts: tuple[NonPromotionalReceipt, ...]


@runtime_checkable
class AuthorityBackend(Protocol):
    """High-level seam implemented by fake and future production adapters."""

    def observe_active(self) -> str: ...

    def append_intent(self, binding: OperationBinding) -> object: ...

    def guarded_compare_and_swap(self, binding: OperationBinding) -> object: ...

    def evidence_view(self) -> object: ...


_FORBIDDEN_PROVIDERS = {
    "git",
    "mutable_local_file",
    "target_host_log",
}


def production_authority(
    topology: ProductionTopology | None = None,
) -> AuthorityBackend:
    """Bind production authority or fail before any side effect.

    Issue #104 deliberately lands the repository contract before choosing its
    independently operated substrate. Every configuration therefore remains
    unavailable in this version. Known non-authoritative providers receive a
    more specific refusal so future implementations cannot accidentally adopt
    them as a fallback.
    """

    if topology is None or not topology.bindings:
        raise AuthorityUnavailable(
            "AUTHORITY_TOPOLOGY_UNBOUND",
            "no operator-approved production authority topology is bound",
        )
    for binding in topology.bindings:
        if binding.provider in _FORBIDDEN_PROVIDERS:
            raise ForbiddenAuthoritySubstrate(
                "AUTHORITY_SUBSTRATE_FORBIDDEN",
                f"{binding.provider!r} cannot provide {binding.role.value} authority",
            )
    missing_roles = set(AuthorityRole) - {
        binding.role for binding in topology.bindings
    }
    if missing_roles:
        missing = ", ".join(sorted(role.value for role in missing_roles))
        raise AuthorityUnavailable(
            "AUTHORITY_TOPOLOGY_INCOMPLETE",
            f"production topology is missing required roles: {missing}",
        )
    raise AuthorityUnavailable(
        "AUTHORITY_SUBSTRATE_UNBOUND",
        "declared providers have no independently verified production adapter",
    )


def require_promotable(evidence_view: object) -> None:
    """Reject promotion until a verified production adapter owns this seam."""

    del evidence_view
    raise NonPromotionalEvidence(
        "EVIDENCE_NONPROMOTIONAL",
        "evidence was not produced by a verified production authority",
    )
