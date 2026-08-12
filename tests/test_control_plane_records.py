from pathlib import Path
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
    "intent",
    "invalidation",
    "operation",
    "protected_state",
    "public_envelope",
    "readiness",
    "recovery",
    "restricted_reference",
    "retention_lease",
    "rollback",
    "terminal_record",
    "validation_context",
}


def test_record_builds_a_known_canonical_v1_vector() -> None:
    record = ControlRecord.build(
        kind="gate",
        record_id="record_1",
        payload={"label": "Cafe\u0301", "gate_id": "gate_1", "blocking": True},
    )
    assert record.digest() == (
        "sha256:af27858009ba32669ea94d00cfd90af7c52624d1e0dda11e1ed0a378c9d8c73c"
    )
    assert record.canonical_bytes() == (
        b'{"digest":"sha256:af27858009ba32669ea94d00cfd90af7c52624d1e0dda11e1ed0a378c9d8c73c",'
        b'"kind":"gate","payload":{"blocking":true,"gate_id":"gate_1",'
        b'"label":"Caf\xc3\xa9"},"record_id":"record_1",'
        b'"schema":"arch_strix_halo.control_record","schema_version":1}'
    )


def test_record_kind_registry_is_closed_and_covers_the_w0_model() -> None:
    assert RECORD_KINDS == EXPECTED_RECORD_KINDS
    for kind in EXPECTED_RECORD_KINDS:
        payload = (
            {
                "binding": {"opaque_ref": "opaque:v1:ABCDEFGHIJKLMNOPQRSTUV"},
                "public": {},
                "source_kind": "gate",
            }
            if kind == "public_envelope"
            else {}
        )
        assert ControlRecord.build(
            kind=kind,
            record_id=f"{kind}_1",
            payload=payload,
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
        ({"number": 1.5}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"number": float("nan")}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"number": 2**63}, RecordErrorCode.UNSUPPORTED_NUMBER),
        ({"sequence": (1, 2)}, RecordErrorCode.INVALID_TYPE),
        ({"text": "unsafe\ud800"}, RecordErrorCode.UNSAFE_UNICODE),
        ({"text": "right-to-left\u202e"}, RecordErrorCode.UNSAFE_UNICODE),
        (
            _nested_payload(MAX_NESTING_DEPTH + 1),
            RecordErrorCode.EXCESSIVE_DEPTH,
        ),
        (
            {"text": "x" * (MAX_RECORD_BYTES + 1)},
            RecordErrorCode.EXCESSIVE_SIZE,
        ),
    ],
)
def test_build_rejects_values_without_a_safe_canonical_v1_form(
    payload: dict[object, object],
    code: RecordErrorCode,
) -> None:
    with pytest.raises(CanonicalizationError) as caught:
        ControlRecord.build(kind="gate", record_id="record_1", payload=payload)

    assert caught.value.code is code


def test_build_rejects_a_cyclic_payload_and_boolean_record_id() -> None:
    cyclic: dict[str, object] = {}
    cyclic["cycle"] = cyclic

    with pytest.raises(CanonicalizationError) as caught_cycle:
        ControlRecord.build(kind="gate", record_id="record_1", payload=cyclic)
    with pytest.raises(CanonicalizationError) as caught_id:
        ControlRecord.build(kind="gate", record_id=True, payload={})  # type: ignore[arg-type]

    assert caught_cycle.value.code is RecordErrorCode.CYCLIC_VALUE
    assert caught_id.value.code is RecordErrorCode.INVALID_TYPE


def test_built_record_is_detached_from_caller_mutation() -> None:
    payload = {"gate_id": "gate_1", "observations": ["first"]}
    record = ControlRecord.build(kind="gate", record_id="record_1", payload=payload)
    before = record.canonical_bytes()

    payload["observations"].append("second")  # type: ignore[union-attr]

    assert record.canonical_bytes() == before


def test_parse_round_trips_canonical_bytes_and_signature_is_not_hashed() -> None:
    unsigned = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload={"outcome": "pass"},
    )
    signed = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload={"outcome": "pass"},
        signature={
            "algorithm": "ed25519",
            "key_id": "signer_1",
            "value": "opaque_signature_value",
        },
    )

    parsed = ControlRecord.parse(signed.canonical_bytes())

    assert signed.digest() == unsigned.digest()
    assert parsed.canonical_bytes() == signed.canonical_bytes()
    assert parsed.signature == signed.signature


def _valid_wire(**overrides: object) -> bytes:
    record = ControlRecord.build(kind="gate", record_id="record_1", payload={})
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
        payload={"label": "Café"},
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
