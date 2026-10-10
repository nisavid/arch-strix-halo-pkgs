"""Load retained rocBLAS fixture values without importing a numerical runtime."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct


@dataclass(frozen=True, slots=True)
class RocblasSgemmFixture:
    """Read-only column-major values and the verified complete-file digest."""

    a: tuple[float, ...]
    b: tuple[float, ...]
    expected_c: tuple[float, ...]
    alpha: float
    beta: float
    sha256: str


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite number {value!r}")


def _require_fields(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"rocblas-sgemm: {label} fields must be {sorted(fields)}")
    return value


def _decode_binary32(value: object, count: int, field: str) -> tuple[float, ...]:
    if not isinstance(value, str) or not re.fullmatch(
        f"[0-9a-f]{{{8 * count}}}", value
    ):
        raise ValueError(
            f"rocblas-sgemm: {field} must contain {8 * count} lowercase hex digits"
        )
    values = struct.unpack(f"<{count}f", bytes.fromhex(value))
    if any(not math.isfinite(number) for number in values):
        raise ValueError(f"rocblas-sgemm: {field} must encode finite binary32 values")
    return values


def load_rocblas_sgemm_fixture(
    path: Path, *, expected_sha256: str
) -> RocblasSgemmFixture:
    """Verify externally pinned bytes and decode the fixed SGEMM representation.

    The caller obtains expected_sha256 from the reviewed artifact record.
    Matching that digest does not establish provenance or a runtime result.
    Digest/content failures raise ValueError; filesystem errors propagate.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch(
        "[0-9a-f]{64}", expected_sha256
    ):
        raise ValueError(
            "rocblas-sgemm: expected_sha256 must be 64 lowercase hexadecimal digits"
        )
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("rocblas-sgemm: SHA-256 mismatch")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, RecursionError) as error:
        raise ValueError(f"rocblas-sgemm: invalid fixture JSON: {error}") from error
    document = _require_fields(
        document,
        {
            "schema_version",
            "probe",
            "shape",
            "layout",
            "encoding",
            "parameters",
            "payloads",
        },
        "fixture",
    )
    parameters = _require_fields(
        document["parameters"],
        {"trans_a", "trans_b", "lda", "ldb", "ldc", "alpha_hex", "beta_hex"},
        "parameters",
    )
    payloads = _require_fields(
        document["payloads"], {"a_hex", "b_hex", "expected_c_hex"}, "payloads"
    )
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("rocblas-sgemm: schema_version must be integer 1")
    for field, expected in (
        ("probe", "rocblas-sgemm"),
        ("layout", "column-major"),
        ("encoding", "ieee754-binary32-little-endian-hex"),
    ):
        if document.get(field) != expected:
            raise ValueError(f"rocblas-sgemm: {field} must be {expected!r}")
    shape = document.get("shape")
    if (
        not isinstance(shape, list)
        or shape != [2, 2]
        or any(type(size) is not int for size in shape)
    ):
        raise ValueError("rocblas-sgemm: shape must contain integer dimensions [2, 2]")
    for field in ("trans_a", "trans_b"):
        if parameters[field] != "N":
            raise ValueError(f"rocblas-sgemm: {field} must be 'N'")
    for field in ("lda", "ldb", "ldc"):
        if type(parameters[field]) is not int or parameters[field] != 2:
            raise ValueError(f"rocblas-sgemm: {field} must be integer 2")
    alpha = _decode_binary32(parameters["alpha_hex"], 1, "alpha_hex")[0]
    beta = _decode_binary32(parameters["beta_hex"], 1, "beta_hex")[0]
    if alpha != 1:
        raise ValueError("rocblas-sgemm: alpha_hex must encode binary32 1")
    if beta != 0:
        raise ValueError("rocblas-sgemm: beta_hex must encode binary32 0")
    return RocblasSgemmFixture(
        a=_decode_binary32(payloads["a_hex"], 4, "a_hex"),
        b=_decode_binary32(payloads["b_hex"], 4, "b_hex"),
        expected_c=_decode_binary32(payloads["expected_c_hex"], 4, "expected_c_hex"),
        alpha=alpha,
        beta=beta,
        sha256=digest,
    )
