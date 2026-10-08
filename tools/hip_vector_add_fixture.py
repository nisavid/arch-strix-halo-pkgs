"""Load retained HIP source bytes without compiling or importing a GPU runtime."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class HipVectorAddFixture:
    """Immutable source bytes and their complete-file digest."""

    source: bytes
    sha256: str


def load_hip_vector_add_fixture(
    path: Path, *, expected_sha256: str
) -> HipVectorAddFixture:
    """Bind whole-file source bytes to a caller's reviewed external digest.

    Malformed digests or changed bytes raise ValueError; read errors propagate.
    This checks bytes, not source provenance, compilation, or a runtime result.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch(
        "[0-9a-f]{64}", expected_sha256
    ):
        raise ValueError(
            "hip-vector-add: expected_sha256 must be 64 lowercase hexadecimal digits"
        )
    source = path.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != expected_sha256:
        raise ValueError("hip-vector-add: SHA-256 mismatch")
    return HipVectorAddFixture(source=source, sha256=digest)
