"""Canonical records and privacy-safe public envelopes for the control plane."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import json
import re
from types import MappingProxyType
from typing import Any
import unicodedata


SCHEMA_NAME = "arch_strix_halo.control_record"
SCHEMA_VERSION = 1
MAX_NESTING_DEPTH = 32
MAX_RECORD_BYTES = 1024 * 1024
MIN_CANONICAL_INTEGER = -(2**63)
MAX_CANONICAL_INTEGER = 2**63 - 1
_DIGEST_DOMAIN = b"arch-strix-halo/control-record/v1\x00"
_PUBLIC_COMMITMENT_DOMAIN = b"arch-strix-halo/public-envelope-commitment/v1\x00"
_SNAKE_CASE_KEY = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPAQUE_REF_PATTERN = re.compile(r"^opaque:v1:[A-Za-z0-9_-]{22,128}$")
_KEYED_COMMITMENT_PATTERN = re.compile(r"^hmac_sha256:[0-9a-f]{64}$")
_RAW_DIGEST_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RecordSchema:
    """The closed metadata policy for one canonical record kind."""

    kind: str
    public_fields: frozenset[str] = frozenset()


def _record_schema(kind: str, *public_fields: str) -> RecordSchema:
    return RecordSchema(kind=kind, public_fields=frozenset(public_fields))


RECORD_SCHEMAS: Mapping[str, RecordSchema] = MappingProxyType(
    {
        "approval": _record_schema("approval", "status"),
        "assignment": _record_schema("assignment", "status"),
        "attempt": _record_schema("attempt", "state"),
        "attestation": _record_schema("attestation", "outcome"),
        "authority_register": _record_schema("authority_register", "status"),
        "authorization": _record_schema("authorization", "status"),
        "capability": _record_schema("capability", "status"),
        "composite_authority": _record_schema("composite_authority", "status"),
        "composite_change_set": _record_schema("composite_change_set", "status"),
        "evaluation": _record_schema("evaluation", "outcome"),
        "exception": _record_schema("exception", "status"),
        "fixture_role": _record_schema("fixture_role"),
        "fixture_selector": _record_schema("fixture_selector"),
        "gate": _record_schema(
            "gate",
            "applicability",
            "blocking",
            "outcome",
        ),
        "generation": _record_schema("generation", "status"),
        "identity": _record_schema("identity", "status"),
        "intent": _record_schema("intent", "state"),
        "invalidation": _record_schema("invalidation", "status"),
        "operation": _record_schema("operation", "state"),
        "protected_state": _record_schema("protected_state", "status"),
        "public_envelope": _record_schema("public_envelope"),
        "readiness": _record_schema("readiness", "status"),
        "recovery": _record_schema("recovery", "state"),
        "restricted_reference": _record_schema("restricted_reference", "status"),
        "retention_lease": _record_schema("retention_lease", "status"),
        "rollback": _record_schema("rollback", "state"),
        "terminal_record": _record_schema("terminal_record", "outcome"),
        "validation_context": _record_schema("validation_context", "status"),
    }
)
RECORD_KINDS = frozenset(RECORD_SCHEMAS)

_PUBLIC_ENUM_VALUES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "applicability": frozenset({"applicable", "not_applicable", "not_due"}),
        "outcome": frozenset(
            {
                "accepted",
                "blocked",
                "fail",
                "failed",
                "not_applicable",
                "pass",
                "rejected",
                "succeeded",
                "unknown",
            }
        ),
        "state": frozenset(
            {
                "active",
                "blocked",
                "cancelled",
                "completed",
                "created",
                "failed",
                "inactive",
                "pending",
                "running",
                "succeeded",
                "unknown",
            }
        ),
        "status": frozenset(
            {
                "accepted",
                "active",
                "blocked",
                "closed",
                "current",
                "expired",
                "inactive",
                "invalid",
                "not_ready",
                "open",
                "pending",
                "ready",
                "rejected",
                "revoked",
                "stale",
                "unknown",
                "valid",
            }
        ),
    }
)


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
    DIGEST_MISMATCH = "digest_mismatch"
    PRIVACY_BINDING_REQUIRED = "privacy_binding_required"
    INVALID_OPAQUE_REF = "invalid_opaque_ref"
    INVALID_COMMITMENT_KEY = "invalid_commitment_key"
    UNSAFE_PUBLIC_VALUE = "unsafe_public_value"
    INVALID_PUBLIC_ENVELOPE = "invalid_public_envelope"


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


def _is_safe_public_value(field: str, value: Any) -> bool:
    if field == "blocking":
        return type(value) is bool
    return type(value) is str and value in _PUBLIC_ENUM_VALUES[field]


def _validate_opaque_ref(
    opaque_ref: Any,
    *,
    restricted_digest: str | None = None,
) -> str:
    if not isinstance(opaque_ref, str) or not _OPAQUE_REF_PATTERN.fullmatch(
        opaque_ref
    ):
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_OPAQUE_REF,
            "opaque reference must use opaque:v1 with at least 128 bits of token space",
        )
    token = opaque_ref.removeprefix("opaque:v1:")
    private_digest_hex = (
        restricted_digest.removeprefix("sha256:")
        if restricted_digest is not None
        else None
    )
    if _RAW_DIGEST_TOKEN_PATTERN.fullmatch(token) or (
        private_digest_hex is not None and private_digest_hex in token
    ):
        raise PrivacyEnvelopeError(
            RecordErrorCode.INVALID_OPAQUE_REF,
            "opaque reference must not expose a raw record digest",
        )
    return opaque_ref


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
        if not _is_safe_public_value(field, value):
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


@dataclass(frozen=True, slots=True)
class ControlRecord:
    """A schema-versioned control record with deterministic wire bytes."""

    kind: str
    record_id: str
    payload: Mapping[str, Any]
    _digest: str
    signature: Mapping[str, Any] | None = None

    @classmethod
    def build(
        cls,
        *,
        kind: str,
        record_id: str,
        payload: Mapping[str, Any],
        signature: Mapping[str, Any] | None = None,
    ) -> "ControlRecord":
        if not isinstance(kind, str):
            raise CanonicalizationError(
                RecordErrorCode.INVALID_TYPE,
                "record kind must be a string",
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
        if kind == "public_envelope":
            _validate_public_envelope_payload(normalized_payload)
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
        record = cls(
            kind=kind,
            record_id=normalized_record_id,
            payload=_freeze(normalized_payload),
            _digest=digest,
            signature=(
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
    def parse(cls, wire: bytes | str) -> "ControlRecord":
        if isinstance(wire, bytes):
            raw = wire
        elif isinstance(wire, str):
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
        if not isinstance(kind, str) or kind not in RECORD_KINDS:
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
        record = cls.build(
            kind=kind,
            record_id=document["record_id"],
            payload=document["payload"],
            signature=document.get("signature"),
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
        envelope_id: str,
        opaque_ref: str | None = None,
        commitment_key: bytes | None = None,
    ) -> "ControlRecord":
        """Project schema-owned metadata with a non-guessable restricted binding."""

        if opaque_ref is None and commitment_key is None:
            raise PrivacyEnvelopeError(
                RecordErrorCode.PRIVACY_BINDING_REQUIRED,
                "a public envelope requires an opaque reference or keyed commitment",
            )

        binding: dict[str, str] = {}
        if opaque_ref is not None:
            binding["opaque_ref"] = _validate_opaque_ref(
                opaque_ref,
                restricted_digest=self._digest,
            )

        if commitment_key is not None:
            if type(commitment_key) is not bytes or not 32 <= len(commitment_key) <= 4096:
                raise PrivacyEnvelopeError(
                    RecordErrorCode.INVALID_COMMITMENT_KEY,
                    "commitment key must contain between 32 and 4096 bytes",
                )
            commitment = hmac.new(
                commitment_key,
                _PUBLIC_COMMITMENT_DOMAIN + self._digest.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            binding["keyed_commitment"] = f"hmac_sha256:{commitment}"

        public: dict[str, bool | str] = {}
        for field in sorted(RECORD_SCHEMAS[self.kind].public_fields):
            if field not in self.payload:
                continue
            value = self.payload[field]
            if not _is_safe_public_value(field, value):
                raise PrivacyEnvelopeError(
                    RecordErrorCode.UNSAFE_PUBLIC_VALUE,
                    f"allowlisted public field has an unrecognized value: {field!r}",
                )
            public[field] = value

        return ControlRecord.build(
            kind="public_envelope",
            record_id=envelope_id,
            payload={
                "binding": binding,
                "public": public,
                "source_kind": self.kind,
            },
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
