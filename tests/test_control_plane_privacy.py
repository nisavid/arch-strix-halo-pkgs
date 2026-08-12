import json
import sys
from pathlib import Path

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

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64
DIGEST_3 = "sha256:" + "3" * 64
DIGEST_4 = "sha256:" + "4" * 64
DIGEST_5 = "sha256:" + "5" * 64
DIGEST_6 = "sha256:" + "6" * 64
TIMESTAMP = "2026-08-12T10:00:00Z"


def _gate_payload() -> dict[str, object]:
    return {
        "assertion_digest": DIGEST_1,
        "evidence_shape_digest": DIGEST_2,
        "fixture_role_digest": DIGEST_3,
        "gate_id": "gate_1",
        "validator_digest": DIGEST_4,
    }


def _attestation_payload(**changes: object) -> dict[str, object]:
    payload = {
        "actor_identity_digest": DIGEST_1,
        "actor_role": "validator",
        "assignment_digest": DIGEST_2,
        "context_digest": DIGEST_3,
        "dependency_projection_digest": DIGEST_4,
        "gate_digest": DIGEST_5,
        "observed_at": TIMESTAMP,
        "outcome": "pass",
        "raw_payload_reference_digest": DIGEST_6,
        "subject_digest": DIGEST_6,
    }
    payload.update(changes)
    return payload


def _evaluation_payload() -> dict[str, object]:
    return {
        "admissible": False,
        "applicability": "applicable",
        "assignment_digest": DIGEST_1,
        "attestation_digests": [DIGEST_2],
        "context_digest": DIGEST_3,
        "currency": "current",
        "dependency_projection_digest": DIGEST_4,
        "evaluated_at": TIMESTAMP,
        "outcome": "blocked",
    }


def test_opaque_reference_is_derived_instead_of_caller_selected() -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )

    envelope = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
    )

    assert envelope.payload["binding"]["opaque_ref"] == (
        "opaque_hmac_sha256:v1:"
        "aGckuknkI3vsBra-uuRCj6nwZQKzsaFtq3sDcLlIuLU"
    )
    assert "private-host" not in envelope.payload["binding"]["opaque_ref"]
    assert envelope.record_id.startswith("public_envelope_sha256:v1:")
    assert len(envelope.record_id) == len("public_envelope_sha256:v1:") + 64

    with pytest.raises(TypeError):
        restricted.public_envelope(  # type: ignore[call-arg]
            envelope_id="private-host:/restricted/path",
            opaque_reference_key=b"r" * 32,
        )
    with pytest.raises(TypeError):
        restricted.public_envelope(  # type: ignore[call-arg]
            opaque_ref="opaque:v1:private-host-identity",
            opaque_reference_key=b"r" * 32,
        )


def test_public_envelope_exports_only_schema_owned_metadata_and_safe_bindings() -> None:
    restricted = ControlRecord.build(
        kind="attestation",
        record_id="attestation_1",
        payload=_attestation_payload(),
    )

    envelope = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
        commitment_key=b"k" * 32,
    )

    assert envelope.kind == "public_envelope"
    assert envelope.payload["source_kind"] == "attestation"
    assert envelope.payload["public"] == {"outcome": "pass"}
    assert envelope.payload["binding"] == {
        "keyed_commitment": (
            "hmac_sha256:"
            "90ba835600e3079298449973b6f8be4719acc3f7a0465868bdda7b8ce2b3cd54"
        ),
        "opaque_ref": (
            "opaque_hmac_sha256:v1:"
            "SRhmDFI5_A9394t8pDqRALas0zEfCt1yMvVthXHQTjU"
        ),
    }
    wire = envelope.canonical_bytes()
    assert DIGEST_1.encode() not in wire
    assert DIGEST_6.encode() not in wire
    assert restricted.digest().encode() not in wire
    assert ControlRecord.parse(wire).canonical_bytes() == wire


def test_public_envelope_accepts_each_safe_binding_independently() -> None:
    restricted = ControlRecord.build(
        kind="evaluation",
        record_id="evaluation_1",
        payload=_evaluation_payload(),
    )

    by_reference = restricted.public_envelope(
        opaque_reference_key=b"r" * 32,
    )
    by_commitment = restricted.public_envelope(
        commitment_key=b"c" * 32,
    )

    assert set(by_reference.payload["binding"]) == {"opaque_ref"}
    assert set(by_commitment.payload["binding"]) == {"keyed_commitment"}


def test_retention_metadata_envelopes_do_not_expose_the_raw_record_or_lease_link(
) -> None:
    lease = ControlRecord.build(
        kind="retention_lease",
        record_id="retention_lease_1",
        payload={
            "expires_at": TIMESTAMP,
            "issued_at": "2026-08-12T09:00:00Z",
            "key_version": "evidence_key_v1",
            "lease_id": "retention_lease_1",
            "status": "active",
        },
    )
    reference = ControlRecord.build(
        kind="restricted_reference",
        record_id="restricted_reference_1",
        payload={
            "created_at": TIMESTAMP,
            "key_version": "evidence_key_v1",
            "reference_id": "restricted_reference_1",
            "restricted_record_digest": DIGEST_1,
            "retention_lease_digest": lease.digest(),
            "storage_authority_digest": DIGEST_2,
        },
    )

    lease_envelope = lease.public_envelope(opaque_reference_key=b"r" * 32)
    reference_envelope = reference.public_envelope(
        opaque_reference_key=b"r" * 32
    )

    assert lease_envelope.payload["public"] == {"status": "active"}
    assert reference_envelope.payload["public"] == {}
    for wire in (
        lease_envelope.canonical_bytes(),
        reference_envelope.canonical_bytes(),
    ):
        assert DIGEST_1.encode() not in wire
        assert lease.digest().encode() not in wire
        assert reference.digest().encode() not in wire


@pytest.mark.parametrize(
    ("opaque_reference_key", "commitment_key", "code"),
    [
        (None, None, RecordErrorCode.PRIVACY_BINDING_REQUIRED),
        (b"weak", None, RecordErrorCode.INVALID_OPAQUE_REFERENCE_KEY),
        (None, b"weak", RecordErrorCode.INVALID_COMMITMENT_KEY),
    ],
)
def test_public_envelope_fails_closed_without_a_safe_binding(
    opaque_reference_key: bytes | None,
    commitment_key: bytes | None,
    code: RecordErrorCode,
) -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )

    with pytest.raises(PrivacyEnvelopeError) as caught:
        restricted.public_envelope(
            opaque_reference_key=opaque_reference_key,
            commitment_key=commitment_key,
        )

    assert caught.value.code is code


def test_public_envelope_kind_cannot_bypass_the_schema_owned_projection() -> None:
    with pytest.raises(PrivacyEnvelopeError) as caught:
        ControlRecord.build(
            kind="public_envelope",
            record_id="envelope_1",
            payload={"secret": "token_should_never_be_public"},
        )

    assert caught.value.code is RecordErrorCode.INVALID_PUBLIC_ENVELOPE


def test_direct_constructor_cannot_bypass_public_envelope_validation() -> None:
    with pytest.raises(TypeError):
        ControlRecord(  # type: ignore[call-arg]
            kind="public_envelope",
            record_id="/private/host",
            payload={"secret": "token"},
            _digest="sha256:" + "0" * 64,
        )


def test_public_envelope_rejects_a_detached_signature_privacy_channel() -> None:
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )
    envelope = restricted.public_envelope(opaque_reference_key=b"r" * 32)
    document = json.loads(envelope.canonical_bytes())
    document["signature"] = {
        "private_host": "private-host",
        "private_path": "/restricted/path",
    }
    wire = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    with pytest.raises(PrivacyEnvelopeError) as caught:
        ControlRecord.parse(wire)

    assert caught.value.code is RecordErrorCode.INVALID_PUBLIC_ENVELOPE


def test_restricted_signature_is_never_copied_into_a_public_envelope() -> None:
    unsigned = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
    )
    restricted = ControlRecord.build(
        kind="gate",
        record_id="gate_1",
        payload=_gate_payload(),
        signature={
            "algorithm": "ed25519",
            "signed_digest": unsigned.digest(),
            "signer_identity_digest": DIGEST_6,
            "value": (
                "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nz"
                "c3Nzc3Nzc3Nzc3Nzc3Nzcw"
            ),
        },
    )

    envelope = restricted.public_envelope(opaque_reference_key=b"r" * 32)

    assert envelope.signature is None
    assert b"signer_identity_digest" not in envelope.canonical_bytes()
