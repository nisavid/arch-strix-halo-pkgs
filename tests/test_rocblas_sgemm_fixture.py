import hashlib
import json
from pathlib import Path
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

RETAINED_FIXTURE = TOOLS_DIR.parent / "inference/fixtures/rocblas-sgemm.json"
RETAINED_SHA256 = "05da9cb62a4841a3a0bf3bbcc22495457937d0adca19ff4e0914847f8de625e9"


def selected_document():
    return {
        "schema_version": 1,
        "probe": "rocblas-sgemm",
        "shape": [2, 2],
        "layout": "column-major",
        "encoding": "ieee754-binary32-little-endian-hex",
        "parameters": {
            "trans_a": "N",
            "trans_b": "N",
            "lda": 2,
            "ldb": 2,
            "ldc": 2,
            "alpha_hex": "0000803f",
            "beta_hex": "00000000",
        },
        "payloads": {
            "a_hex": "0000803f000040400000004000008040",
            "b_hex": "0000a0400000e0400000c04000000041",
            "expected_c_hex": "0000984100002c420000b04100004842",
        },
    }


def write_document(tmp_path, document):
    path = tmp_path / "fixture.json"
    raw = json.dumps(document).encode("utf-8")
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_fixture_loads_the_selected_column_major_values(tmp_path):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, digest = write_document(tmp_path, selected_document())
    fixture = load_rocblas_sgemm_fixture(path, expected_sha256=digest)

    assert (
        fixture.a,
        fixture.b,
        fixture.expected_c,
        fixture.alpha,
        fixture.beta,
        fixture.sha256,
    ) == (
        (1, 3, 2, 4),
        (5, 7, 6, 8),
        (19, 43, 22, 50),
        1,
        0,
        digest,
    )


def test_digest_mismatch_fails_before_malformed_content_is_decoded(tmp_path):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path = tmp_path / "fixture.json"
    path.write_bytes(b"not JSON")
    with pytest.raises(ValueError, match="rocblas-sgemm.*SHA-256 mismatch"):
        load_rocblas_sgemm_fixture(path, expected_sha256="0" * 64)


@pytest.mark.parametrize("digest", [None, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64])
def test_expected_digest_must_be_lowercase_64_digit_hex(tmp_path, digest):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, _ = write_document(tmp_path, selected_document())
    with pytest.raises(ValueError, match="rocblas-sgemm.*expected_sha256.*lowercase"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize("raw", [b"not JSON", b"\xff", b'{"payloads":'])
def test_malformed_matching_bytes_raise_a_fixture_content_error(tmp_path, raw):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path = tmp_path / "fixture.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="rocblas-sgemm.*JSON"):
        load_rocblas_sgemm_fixture(
            path, expected_sha256=hashlib.sha256(raw).hexdigest()
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("probe", "rocblas-sgemm"),
        ("lda", 2),
        ("a_hex", "0000803f000040400000004000008040"),
    ],
)
def test_duplicate_json_fields_are_rejected_at_every_object_depth(tmp_path, key, value):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    field = json.dumps(key) + ": " + json.dumps(value)
    raw = (
        json.dumps(selected_document())
        .replace(field, field + ", " + field)
        .encode("utf-8")
    )
    path = tmp_path / "fixture.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="rocblas-sgemm.*duplicate"):
        load_rocblas_sgemm_fixture(
            path, expected_sha256=hashlib.sha256(raw).hexdigest()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("probe", "other"),
        ("probe", None),
        ("shape", [2, 3]),
        ("shape", [2]),
        ("shape", [2.0, 2]),
        ("shape", [True, 2]),
        ("layout", "row-major"),
        ("encoding", "ieee754-binary32-big-endian-hex"),
    ],
)
def test_fixture_metadata_must_describe_the_selected_sgemm(tmp_path, field, value):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    document[field] = value
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*{field}"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize("section", [None, "parameters", "payloads"])
@pytest.mark.parametrize("change", ["not-object", "missing-field", "extra-field"])
def test_fixture_objects_require_exact_schema_fields(tmp_path, section, change):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    target = document if section is None else document[section]
    if change == "missing-field":
        del target[next(iter(target))]
    elif change == "extra-field":
        target["extra"] = "unrecognized"
    elif section is None:
        document = []
    else:
        document[section] = []
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match="rocblas-sgemm.*fields"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("trans_a", "T"),
        ("trans_b", "C"),
        ("lda", 1),
        ("ldb", True),
        ("ldc", 2.0),
        ("alpha_hex", "00000000"),
        ("beta_hex", "0000803f"),
    ],
)
def test_sgemm_parameters_preserve_the_selected_operation(tmp_path, field, value):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    document["parameters"][field] = value
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*{field}"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize(
    "section,field",
    [
        ("parameters", "alpha_hex"),
        ("parameters", "beta_hex"),
        ("payloads", "a_hex"),
        ("payloads", "b_hex"),
        ("payloads", "expected_c_hex"),
    ],
)
@pytest.mark.parametrize(
    "malformation",
    ["non-string", "short", "long", "non-hex", "uppercase", "whitespace"],
)
def test_payloads_require_exact_lowercase_hex_lengths(
    tmp_path, section, field, malformation
):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    original = document[section][field]
    document[section][field] = {
        "non-string": None,
        "short": original[:-2],
        "long": original + "00",
        "non-hex": "g" * len(original),
        "uppercase": "A" * len(original),
        "whitespace": " " + original[1:],
    }[malformation]
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*{field}.*hex"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize("field", ["a_hex", "b_hex", "expected_c_hex"])
@pytest.mark.parametrize("nonfinite", ["0000c07f", "0000807f", "000080ff"])
@pytest.mark.parametrize("position", range(4))
def test_nonfinite_binary32_matrix_values_are_rejected(
    tmp_path, field, nonfinite, position
):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    payload = document["payloads"][field]
    offset = position * 8
    document["payloads"][field] = payload[:offset] + nonfinite + payload[offset + 8 :]
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*{field}.*finite"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_numbers_are_not_accepted_as_json(tmp_path, token):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    raw = (
        json.dumps(selected_document())
        .replace('"schema_version": 1', '"schema_version": ' + token)
        .encode("utf-8")
    )
    path = tmp_path / "fixture.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="rocblas-sgemm.*JSON.*nonfinite"):
        load_rocblas_sgemm_fixture(
            path, expected_sha256=hashlib.sha256(raw).hexdigest()
        )


def test_retained_artifact_matches_its_external_record_and_selected_values():
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    fixture = load_rocblas_sgemm_fixture(
        RETAINED_FIXTURE, expected_sha256=RETAINED_SHA256
    )
    assert (fixture.a, fixture.b, fixture.expected_c, fixture.alpha, fixture.beta) == (
        (1, 3, 2, 4),
        (5, 7, 6, 8),
        (19, 43, 22, 50),
        1,
        0,
    )


@pytest.mark.parametrize("field", ["alpha_hex", "beta_hex"])
@pytest.mark.parametrize("nonfinite", ["0000c07f", "0000807f", "000080ff"])
def test_nonfinite_binary32_sgemm_scalars_are_rejected(tmp_path, field, nonfinite):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    document = selected_document()
    document["parameters"][field] = nonfinite
    path, digest = write_document(tmp_path, document)
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*{field}.*finite"):
        load_rocblas_sgemm_fixture(path, expected_sha256=digest)


@pytest.mark.parametrize(
    "condition,exception",
    [
        ("missing", FileNotFoundError),
        ("directory", IsADirectoryError),
        ("unreadable", PermissionError),
    ],
)
def test_filesystem_errors_keep_their_normal_subtype(tmp_path, condition, exception):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path = tmp_path / "fixture.json"
    if condition == "directory":
        path.mkdir()
    elif condition == "unreadable":
        path.write_bytes(b"unreadable")
        path.chmod(0)
    try:
        with pytest.raises(exception):
            load_rocblas_sgemm_fixture(path, expected_sha256="0" * 64)
    finally:
        if condition == "unreadable":
            path.chmod(0o600)


def test_verified_fields_cannot_be_replaced_through_vars():
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    fixture = load_rocblas_sgemm_fixture(
        RETAINED_FIXTURE, expected_sha256=RETAINED_SHA256
    )
    with pytest.raises((AttributeError, TypeError)):
        vars(fixture)["expected_c"] = (0, 0, 0, 0)
    assert fixture.expected_c == (19, 43, 22, 50)
    assert fixture.sha256 == RETAINED_SHA256


@pytest.mark.parametrize("field", ["a", "b", "expected_c", "alpha", "beta", "sha256"])
def test_fixture_fields_cannot_be_reassigned(tmp_path, field):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, digest = write_document(tmp_path, selected_document())
    fixture = load_rocblas_sgemm_fixture(path, expected_sha256=digest)
    with pytest.raises(AttributeError):
        setattr(fixture, field, None)


@pytest.mark.parametrize("field", ["a", "b", "expected_c", "alpha", "beta", "sha256"])
def test_fixture_fields_cannot_be_deleted(tmp_path, field):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, digest = write_document(tmp_path, selected_document())
    fixture = load_rocblas_sgemm_fixture(path, expected_sha256=digest)
    with pytest.raises(AttributeError):
        delattr(fixture, field)


def test_fixture_matrix_elements_cannot_be_changed(tmp_path):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, digest = write_document(tmp_path, selected_document())
    fixture = load_rocblas_sgemm_fixture(path, expected_sha256=digest)
    with pytest.raises(TypeError):
        fixture.a[0] = 0


@pytest.mark.parametrize("change", ["big-endian", "row-major", "whitespace"])
def test_retained_digest_rejects_changed_bytes_even_when_json_is_valid(
    tmp_path, change
):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    raw = RETAINED_FIXTURE.read_bytes()
    if change == "big-endian":
        raw = raw.replace(
            b"0000803f000040400000004000008040", b"3f800000404000004000000040800000"
        )
    elif change == "row-major":
        raw = raw.replace(
            b"0000803f000040400000004000008040", b"0000803f000000400000404000008040"
        )
    else:
        raw += b"\n"
    path = tmp_path / "fixture.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="rocblas-sgemm.*SHA-256 mismatch"):
        load_rocblas_sgemm_fixture(path, expected_sha256=RETAINED_SHA256)


def test_loading_requires_an_external_digest(tmp_path):
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    path, _ = write_document(tmp_path, selected_document())
    with pytest.raises(TypeError, match="expected_sha256"):
        load_rocblas_sgemm_fixture(path)


def test_retained_expected_output_matches_the_existing_independent_validator():
    from foundation_numeric_fixtures import validate_numeric_output
    from rocblas_sgemm_fixture import load_rocblas_sgemm_fixture

    fixture = load_rocblas_sgemm_fixture(
        RETAINED_FIXTURE, expected_sha256=RETAINED_SHA256
    )
    assert validate_numeric_output("rocblas-sgemm", fixture.expected_c) is None
