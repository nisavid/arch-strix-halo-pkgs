from pathlib import Path
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from hip_vector_add_fixture import load_hip_vector_add_fixture
from foundation_numeric_fixtures import validate_numeric_output


ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
SELECTED_SOURCE_SHA256 = (
    "729b393536433e9837ff5950b021439c7c59ae50a27545d3a264b1d60063422b"
)


def test_loader_retains_complete_source_bytes_and_the_verified_digest(tmp_path):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"abc")
    fixture = load_hip_vector_add_fixture(
        path,
        expected_sha256=ABC_SHA256,
    )
    assert fixture.source == b"abc"
    assert fixture.sha256 == ABC_SHA256


def test_loader_rejects_bytes_that_do_not_match_the_reviewed_digest(tmp_path):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"abd")
    with pytest.raises(ValueError, match="hip-vector-add.*SHA-256 mismatch"):
        load_hip_vector_add_fixture(
            path,
            expected_sha256=ABC_SHA256,
        )


@pytest.mark.parametrize(
    "digest",
    (None, False, 0, b"a" * 64, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, " " + "a" * 64),
)
def test_loader_rejects_invalid_digests_before_filesystem_access(tmp_path, digest):
    with pytest.raises(
        ValueError, match="hip-vector-add.*expected_sha256.*64 lowercase hexadecimal"
    ):
        load_hip_vector_add_fixture(tmp_path / "missing.hip", expected_sha256=digest)


def test_loader_requires_the_reviewed_digest_keyword(tmp_path):
    with pytest.raises(TypeError, match="expected_sha256"):
        load_hip_vector_add_fixture(tmp_path / "fixture.hip")


def test_loader_preserves_missing_file_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_hip_vector_add_fixture(tmp_path / "missing.hip", expected_sha256="a" * 64)


def test_loader_preserves_directory_errors(tmp_path):
    with pytest.raises(IsADirectoryError):
        load_hip_vector_add_fixture(tmp_path, expected_sha256="a" * 64)


def test_loader_preserves_filesystem_permission_errors(tmp_path, monkeypatch):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"abc")
    read_error = PermissionError("constructed filesystem read denial")

    def deny_read(candidate):
        assert candidate == path
        raise read_error

    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "read_bytes", deny_read)
        with pytest.raises(PermissionError) as raised:
            load_hip_vector_add_fixture(
                path,
                expected_sha256=ABC_SHA256,
            )
    assert raised.value is read_error


def test_loader_preserves_opaque_source_bytes_without_decoding(tmp_path):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"\x00\xff\nabc")
    fixture = load_hip_vector_add_fixture(
        path,
        expected_sha256="2842b1bb14932153d83cc128e181fae8ce3ad1e1e63345bcef87f195019378e2",
    )
    assert fixture.source == b"\x00\xff\nabc"


@pytest.mark.parametrize("field", ("source", "sha256"))
def test_loaded_fixture_fields_cannot_be_replaced(tmp_path, field):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"abc")
    fixture = load_hip_vector_add_fixture(
        path,
        expected_sha256=ABC_SHA256,
    )
    with pytest.raises(AttributeError):
        setattr(fixture, field, b"changed" if field == "source" else "a" * 64)


@pytest.mark.parametrize("field", ("source", "sha256"))
def test_loaded_fixture_fields_cannot_be_deleted(tmp_path, field):
    path = tmp_path / "fixture.hip"
    path.write_bytes(b"abc")
    fixture = load_hip_vector_add_fixture(
        path,
        expected_sha256=ABC_SHA256,
    )
    with pytest.raises(AttributeError):
        delattr(fixture, field)


def test_the_selected_source_is_bound_to_its_reviewed_digest():
    fixture = load_hip_vector_add_fixture(
        TOOLS_DIR / "buildroot" / "probe" / "hello.hip",
        expected_sha256=SELECTED_SOURCE_SHA256,
    )
    assert fixture.sha256 == SELECTED_SOURCE_SHA256
    assert fixture.source.startswith(b"#include <hip/hip_runtime.h>\n")


def test_the_selected_source_digest_rejects_a_changed_retained_file(tmp_path):
    path = tmp_path / "changed.hip"
    path.write_bytes((TOOLS_DIR / "buildroot" / "probe" / "hello.hip").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hip-vector-add.*SHA-256 mismatch"):
        load_hip_vector_add_fixture(
            path,
            expected_sha256=SELECTED_SOURCE_SHA256,
        )


def test_numerical_validation_remains_separate_from_source_loading():
    fixture = load_hip_vector_add_fixture(
        TOOLS_DIR / "buildroot" / "probe" / "hello.hip",
        expected_sha256=SELECTED_SOURCE_SHA256,
    )
    assert fixture.source
    assert validate_numeric_output("hip-vector-add", range(0, 3_145_728, 3)) is None
    output = list(range(0, 3_145_728, 3))
    output[-1] = 3_145_726
    with pytest.raises(ValueError, match="hip-vector-add.*index 1048575"):
        validate_numeric_output("hip-vector-add", output)
