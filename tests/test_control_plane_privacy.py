from pathlib import Path
import sys

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


OPAQUE_REF = "opaque:v1:ABCDEFGHIJKLMNOPQRSTUV"


def test_public_envelope_exports_only_schema_owned_metadata_and_safe_bindings() -> None:
    restricted = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload={
            "notes": "owner@example.invalid",
            "outcome": "pass",
            "token": "token_should_never_leave_restricted_storage",
        },
    )

    envelope = restricted.public_envelope(
        envelope_id="envelope_1",
        opaque_ref=OPAQUE_REF,
        commitment_key=b"k" * 32,
    )

    assert envelope.kind == "public_envelope"
    assert envelope.payload["source_kind"] == "attestation"
    assert envelope.payload["public"] == {"outcome": "pass"}
    assert envelope.payload["binding"] == {
        "keyed_commitment": (
            "hmac_sha256:"
            "d4d0564be32454013b39cd16274972f3de67fd3ee0e28ae2b3cad4af82e40d47"
        ),
        "opaque_ref": OPAQUE_REF,
    }
    wire = envelope.canonical_bytes()
    assert b"owner@example.invalid" not in wire
    assert b"token_should_never_leave_restricted_storage" not in wire
    assert restricted.digest().encode() not in wire


def test_public_envelope_accepts_each_safe_binding_independently() -> None:
    restricted = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_1",
        payload={"outcome": "blocked"},
    )

    by_reference = restricted.public_envelope(
        envelope_id="envelope_reference_1",
        opaque_ref=OPAQUE_REF,
    )
    by_commitment = restricted.public_envelope(
        envelope_id="envelope_commitment_1",
        commitment_key=b"c" * 32,
    )

    assert by_reference.payload["binding"] == {"opaque_ref": OPAQUE_REF}
    assert set(by_commitment.payload["binding"]) == {"keyed_commitment"}


@pytest.mark.parametrize(
    ("opaque_ref", "commitment_key", "code"),
    [
        (None, None, RecordErrorCode.PRIVACY_BINDING_REQUIRED),
        ("opaque:v1:short", None, RecordErrorCode.INVALID_OPAQUE_REF),
        (None, b"weak", RecordErrorCode.INVALID_COMMITMENT_KEY),
    ],
)
def test_public_envelope_fails_closed_without_a_safe_binding(
    opaque_ref: str | None,
    commitment_key: bytes | None,
    code: RecordErrorCode,
) -> None:
    restricted = ControlRecord.build(kind="gate", record_id="gate_1", payload={})

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(
            envelope_id="envelope_1",
            opaque_ref=opaque_ref,
            commitment_key=commitment_key,
        )

    assert caught.value.code is code


def test_public_envelope_rejects_raw_private_digest_as_an_opaque_reference() -> None:
    restricted = ControlRecord.build(kind="gate", record_id="gate_1", payload={})
    guessable_ref = f"opaque:v1:{restricted.digest().removeprefix('sha256:')}"

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(
            envelope_id="envelope_1",
            opaque_ref=guessable_ref,
        )

    assert caught.value.code is RecordErrorCode.INVALID_OPAQUE_REF


def test_public_envelope_kind_cannot_bypass_the_schema_owned_projection() -> None:
    with pytest.raises(PrivacyEnvelopeError) as caught:
        ControlRecord.build(
            kind="public_envelope",
            record_id="envelope_1",
            payload={"secret": "token_should_never_be_public"},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PUBLIC_ENVELOPE


@pytest.mark.parametrize("unsafe_outcome", ["operator_email", True, 1])
def test_public_envelope_rejects_unrecognized_values_in_allowlisted_fields(
    unsafe_outcome: object,
) -> None:
    restricted = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload={"outcome": unsafe_outcome},
    )

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(
            envelope_id="envelope_1",
            opaque_ref=OPAQUE_REF,
        )

    assert caught.value.code is RecordErrorCode.UNSAFE_PUBLIC_VALUE
