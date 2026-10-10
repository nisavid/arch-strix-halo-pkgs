"""Load retained MIGraphX Add→Relu inputs without a GPU runtime."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct


@dataclass(frozen=True, slots=True)
class MigraphxAddReluFixture:
    onnx_bytes: bytes
    x: tuple[tuple[float, ...], ...]
    y: tuple[tuple[float, ...], ...]
    expected_z: tuple[tuple[float, ...], ...]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("nonstandard JSON constant")


def _decode_tensor(encoded: object, field: str) -> tuple[tuple[float, ...], ...]:
    if not isinstance(encoded, str) or re.fullmatch(r"[0-9a-f]{48}", encoded) is None:
        raise ValueError(f"migraphx-add-relu: {field} must be 48 lowercase hexadecimal characters")
    values = struct.unpack("<6f", bytes.fromhex(encoded))
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"migraphx-add-relu: {field} must contain only finite binary32 values")
    return values[:3], values[3:]


def load_migraphx_add_relu_fixture(
    onnx_path: str | Path,
    payload_path: str | Path,
    *,
    expected_onnx_sha256: str,
    expected_payload_sha256: str,
) -> MigraphxAddReluFixture:
    """Retain graph bytes and decode the selected binary32-LE tensors."""
    onnx_bytes = Path(onnx_path).read_bytes()
    payload_bytes = Path(payload_path).read_bytes()
    if hashlib.sha256(onnx_bytes).hexdigest() != expected_onnx_sha256:
        raise ValueError("migraphx-add-relu: ONNX SHA-256 mismatch")
    if hashlib.sha256(payload_bytes).hexdigest() != expected_payload_sha256:
        raise ValueError("migraphx-add-relu: payload SHA-256 mismatch")

    try:
        document = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise ValueError("migraphx-add-relu: payload must be valid UTF-8 JSON with unique object keys") from exc
    if not isinstance(document, dict):
        raise ValueError("migraphx-add-relu: metadata must be a JSON object")
    if set(document) != {
        "schema_version",
        "probe",
        "shape",
        "layout",
        "encoding",
        "payloads",
    }:
        raise ValueError("migraphx-add-relu: metadata keys must match the selected schema")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("migraphx-add-relu: schema_version must be integer 1")
    for field, expected in (
        ("probe", "migraphx-add-relu"),
        ("layout", "row-major"),
        ("encoding", "ieee754-binary32-little-endian-hex"),
    ):
        value = document[field]
        if not isinstance(value, str) or value != expected:
            raise ValueError(f"migraphx-add-relu: {field} must be {expected!r}")
    shape = document["shape"]
    if (
        not isinstance(shape, list)
        or shape != [2, 3]
        or any(type(dimension) is not int for dimension in shape)
    ):
        raise ValueError("migraphx-add-relu: shape must be [2, 3] with integer dimensions")
    payloads = document["payloads"]
    if not isinstance(payloads, dict):
        raise ValueError("migraphx-add-relu: payloads must be a JSON object")
    if set(payloads) != {"x_hex", "y_hex", "expected_z_hex"}:
        raise ValueError("migraphx-add-relu: payloads keys must be x_hex, y_hex, expected_z_hex")
    return MigraphxAddReluFixture(
        onnx_bytes=onnx_bytes,
        x=_decode_tensor(payloads["x_hex"], "x_hex"),
        y=_decode_tensor(payloads["y_hex"], "y_hex"),
        expected_z=_decode_tensor(payloads["expected_z_hex"], "expected_z_hex"),
    )
