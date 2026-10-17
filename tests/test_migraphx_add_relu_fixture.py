from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


_GRAPH_BYTES = b"constructed graph bytes for the loader test"


def _selected_document():
    return {
        "schema_version": 1,
        "probe": "migraphx-add-relu",
        "shape": [2, 3],
        "layout": "row-major",
        "encoding": "ieee754-binary32-little-endian-hex",
        "payloads": {
            "x_hex": "0000803f000000c000004040000080c00000a0400000c0c0",
            "y_hex": "0000003f0000803f000080c00000803f0000c0c00000e040",
            "expected_z_hex": "0000c03f000000000000000000000000000000000000803f",
        },
    }


def _write_fixture(tmp_path, document):
    # Graph bytes are opaque here; the retained-artifact producer validates ONNX.
    onnx_path = tmp_path / "tiny.onnx"
    onnx_path.write_bytes(_GRAPH_BYTES)
    payload_bytes = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    payload_path = tmp_path / "migraphx-add-relu.json"
    payload_path.write_bytes(payload_bytes)
    return onnx_path, payload_path, {
        "expected_onnx_sha256": hashlib.sha256(_GRAPH_BYTES).hexdigest(),
        "expected_payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }


def _write_raw_payload_fixture(tmp_path, raw_payload):
    onnx_path, payload_path, digests = _write_fixture(tmp_path, _selected_document())
    payload_path.write_bytes(raw_payload)
    digests["expected_payload_sha256"] = hashlib.sha256(raw_payload).hexdigest()
    return onnx_path, payload_path, digests


def test_loader_returns_model_bytes_and_selected_tensors_with_matching_digests(tmp_path):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_fixture(tmp_path, _selected_document())

    fixture = load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)

    assert (fixture.onnx_bytes, fixture.x, fixture.y, fixture.expected_z) == (
        _GRAPH_BYTES,
        ((1.0, -2.0, 3.0), (-4.0, 5.0, -6.0)),
        ((0.5, 1.0, -4.0), (1.0, -6.0, 7.0)),
        ((1.5, 0.0, 0.0), (0.0, 0.0, 1.0)),
    )


def test_loader_rejects_wrong_declared_shape_with_matching_digests(tmp_path):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    document["shape"] = [3, 2]
    onnx_path, payload_path, digests = _write_fixture(tmp_path, document)

    with pytest.raises(ValueError, match="shape"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


_OMIT_FIELD = object()


@pytest.mark.parametrize(
    ("field_path", "replacement"),
    [
        pytest.param((), [], id="root-list"),
        pytest.param((), None, id="root-null"),
        pytest.param((), "metadata", id="root-string"),
        pytest.param((), 1, id="root-number"),
        pytest.param((), True, id="root-boolean"),
        pytest.param(("schema_version",), 2, id="wrong-schema-version"),
        pytest.param(("schema_version",), True, id="boolean-schema-version"),
        pytest.param(("schema_version",), 1.0, id="float-schema-version"),
        pytest.param(("schema_version",), "1", id="string-schema-version"),
        pytest.param(("schema_version",), None, id="null-schema-version"),
        pytest.param(("probe",), "other-probe", id="wrong-probe"),
        pytest.param(("probe",), None, id="null-probe"),
        pytest.param(("shape",), [2.0, 3], id="float-first-dimension"),
        pytest.param(("shape",), [2, 3.0], id="float-second-dimension"),
        pytest.param(("shape",), [True, 3], id="boolean-first-dimension"),
        pytest.param(("shape",), [2, False], id="boolean-second-dimension"),
        pytest.param(("shape",), "2x3", id="string-shape"),
        pytest.param(("shape",), None, id="null-shape"),
        pytest.param(("shape",), [2], id="short-shape"),
        pytest.param(("shape",), [2, 3, 4], id="long-shape"),
        pytest.param(("layout",), "column-major", id="wrong-layout"),
        pytest.param(("layout",), None, id="null-layout"),
        pytest.param(
            ("encoding",),
            "ieee754-binary32-big-endian-hex",
            id="wrong-encoding",
        ),
        pytest.param(("encoding",), None, id="null-encoding"),
        pytest.param(("payloads",), [], id="payloads-list"),
        pytest.param(("payloads",), None, id="payloads-null"),
        pytest.param(("payloads",), "payloads", id="payloads-string"),
        pytest.param(("payloads",), 1, id="payloads-number"),
        pytest.param(("payloads",), True, id="payloads-boolean"),
        *[
            pytest.param((key,), _OMIT_FIELD, id=f"missing-{key}")
            for key in (
                "schema_version",
                "probe",
                "shape",
                "layout",
                "encoding",
                "payloads",
            )
        ],
        *[
            pytest.param(("payloads", key), _OMIT_FIELD, id=f"missing-{key}")
            for key in ("x_hex", "y_hex", "expected_z_hex")
        ],
        pytest.param(("unexpected",), True, id="extra-root-key"),
        pytest.param(
            ("payloads", "unexpected_hex"),
            "0000c03f000000000000000000000000000000000000803f",
            id="extra-payload-key",
        ),
    ],
)
def test_loader_rejects_metadata_outside_the_closed_contract(
    tmp_path, field_path, replacement
):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    if field_path:
        owner = document
        for field in field_path[:-1]:
            owner = owner[field]
        if replacement is _OMIT_FIELD:
            del owner[field_path[-1]]
        else:
            owner[field_path[-1]] = replacement
        message = f"{field_path[0]}|keys"
    else:
        document = replacement
        message = "document|metadata|object|root"

    onnx_path, payload_path, digests = _write_fixture(tmp_path, document)

    with pytest.raises(ValueError, match=message):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.mark.parametrize("field_name", ("x_hex", "y_hex", "expected_z_hex"))
@pytest.mark.parametrize(
    "replacement",
    [
        pytest.param(None, id="null"),
        pytest.param(1, id="integer"),
        pytest.param(1.5, id="float"),
        pytest.param(True, id="boolean"),
        pytest.param([], id="list"),
        pytest.param({}, id="object"),
        pytest.param("", id="empty"),
        pytest.param("00000000" * 5, id="five-values"),
        pytest.param("00000000" * 7, id="seven-values"),
        pytest.param("0" * 47, id="odd-length"),
        pytest.param("g" + "0" * 47, id="nonhex-character"),
        pytest.param("0000803F" + "00000000" * 5, id="uppercase"),
        pytest.param(" " + "00000000" * 6, id="leading-whitespace"),
        pytest.param("00000000" * 6 + " ", id="trailing-whitespace"),
        pytest.param("00000000 " * 6, id="embedded-whitespace"),
        pytest.param("  " + "0" * 46, id="whitespace-in-48-characters"),
        *[
            pytest.param(
                "00000000" * position + word + "00000000" * (5 - position),
                id=f"{label}-position-{position}",
            )
            for label, word in (
                ("positive-infinity", "0000807f"),
                ("negative-infinity", "000080ff"),
                ("quiet-nan", "0000c07f"),
                ("negative-quiet-nan", "0000c0ff"),
                ("signaling-nan", "0100807f"),
            )
            for position in range(6)
        ],
    ],
)
def test_loader_rejects_noncanonical_or_nonfinite_payloads(
    tmp_path, field_name, replacement
):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    document["payloads"][field_name] = replacement
    onnx_path, payload_path, digests = _write_fixture(tmp_path, document)

    with pytest.raises(ValueError, match=field_name):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.mark.parametrize(
    ("encoded", "expected"),
    [
        pytest.param(
            "00000000000000800000803f000000c0000060400000b0c0",
            ((0.0, -0.0, 1.0), (-2.0, 3.5, -5.5)),
            id="finite-values-and-signed-zero",
        ),
        pytest.param(
            "01000000ffff7f7fffff7fff000080000000808001000080",
            (
                (2.0**-149, 3.4028234663852886e38, -3.4028234663852886e38),
                (2.0**-126, -(2.0**-126), -(2.0**-149)),
            ),
            id="finite-binary32-extremes",
        ),
    ],
)
def test_loader_accepts_finite_tensors_without_enforcing_the_selected_oracle(
    tmp_path, encoded, expected
):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    document["payloads"] = {
        "x_hex": encoded,
        "y_hex": encoded,
        "expected_z_hex": encoded,
    }
    onnx_path, payload_path, digests = _write_fixture(tmp_path, document)

    fixture = load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)

    assert (fixture.x, fixture.y, fixture.expected_z) == (expected, expected, expected)


@pytest.mark.parametrize(
    ("file_kind", "label"),
    [pytest.param("onnx", "ONNX", id="onnx"), pytest.param("payload", "payload", id="json")],
)
def test_loader_rejects_independently_altered_file_bytes(tmp_path, file_kind, label):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_fixture(tmp_path, _selected_document())
    altered_path = onnx_path if file_kind == "onnx" else payload_path
    altered_path.write_bytes(altered_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match=rf"migraphx-add-relu: {label}.*SHA-256"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.mark.parametrize(
    ("file_kind", "label"),
    [pytest.param("onnx", "ONNX", id="onnx"), pytest.param("payload", "payload", id="json")],
)
@pytest.mark.parametrize(
    "raw_payload",
    [
        pytest.param(b"{", id="malformed-json"),
        pytest.param(b"\xff", id="malformed-utf8"),
    ],
)
def test_loader_checks_each_digest_before_payload_decoding(
    tmp_path, file_kind, label, raw_payload
):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_fixture(tmp_path, _selected_document())
    payload_path.write_bytes(raw_payload)
    if file_kind == "onnx":
        onnx_path.write_bytes(_GRAPH_BYTES + b"\n")
        digests["expected_payload_sha256"] = hashlib.sha256(raw_payload).hexdigest()

    with pytest.raises(ValueError, match=rf"migraphx-add-relu: {label}.*SHA-256"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.mark.parametrize("file_kind", ("onnx", "payload"))
def test_loader_preserves_missing_file_errors(tmp_path, file_kind):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_fixture(tmp_path, _selected_document())
    missing_path = onnx_path if file_kind == "onnx" else payload_path
    missing_path.unlink()

    with pytest.raises(FileNotFoundError) as error:
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)

    assert error.value.filename == str(missing_path)


@pytest.mark.parametrize(
    "raw_payload",
    [
        pytest.param(b"\xff", id="invalid-utf8-leading-byte"),
        pytest.param(b'{"probe":"\xc3("}', id="invalid-utf8-continuation"),
        pytest.param(b'{"probe":"\xe2\x82"}', id="incomplete-utf8-sequence"),
        pytest.param(b"", id="empty-json"),
        pytest.param(b"{", id="incomplete-json"),
        pytest.param(b'{"schema_version":1,}', id="trailing-comma"),
        pytest.param(b"{} trailing text", id="trailing-text"),
    ],
)
def test_loader_reports_payload_decoding_errors_with_json_context(tmp_path, raw_payload):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_raw_payload_fixture(tmp_path, raw_payload)

    with pytest.raises(ValueError, match=r"migraphx-add-relu:.*JSON"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.fixture
def retained_fixture():
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    fixture_dir = Path(__file__).resolve().parents[1] / "inference" / "fixtures"
    return load_migraphx_add_relu_fixture(
        fixture_dir / "migraphx-add-relu.onnx",
        fixture_dir / "migraphx-add-relu.json",
        expected_onnx_sha256="9895918501d5a1c87dc74c1435b8f2aca52f17b1193d0f0a09ce8cbc421abcf9",
        expected_payload_sha256="51c1978fc14288167aec152d3a8b4768f405e519b987c230da7375ad24f17048",
    )


@pytest.mark.parametrize("depth", [sys.getrecursionlimit() + 10, 10_000])
def test_loader_reports_excessive_json_nesting_as_a_validation_error(tmp_path, depth):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    onnx_path, payload_path, digests = _write_raw_payload_fixture(
        tmp_path, b"[" * depth + b"0" + b"]" * depth
    )

    with pytest.raises(ValueError, match=r"migraphx-add-relu:.*JSON"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


def test_loader_returns_retained_graph_bytes_and_selected_tensors(retained_fixture):
    onnx_path = (
        Path(__file__).resolve().parents[1]
        / "inference"
        / "fixtures"
        / "migraphx-add-relu.onnx"
    )

    assert (
        retained_fixture.onnx_bytes,
        retained_fixture.x,
        retained_fixture.y,
        retained_fixture.expected_z,
    ) == (
        onnx_path.read_bytes(),
        ((1.0, -2.0, 3.0), (-4.0, 5.0, -6.0)),
        ((0.5, 1.0, -4.0), (1.0, -6.0, 7.0)),
        ((1.5, 0.0, 0.0), (0.0, 0.0, 1.0)),
    )


def test_retained_expected_output_satisfies_the_independent_numeric_oracle(
    retained_fixture,
):
    from foundation_numeric_fixtures import validate_numeric_output

    assert validate_numeric_output("migraphx-add-relu", retained_fixture.expected_z) is None


@pytest.mark.parametrize("field_name", ("onnx_bytes", "x", "y", "expected_z"))
def test_retained_fixture_fields_cannot_be_replaced(retained_fixture, field_name):
    replacement = (
        b"replacement graph bytes"
        if field_name == "onnx_bytes"
        else ((9.0, 9.0, 9.0), (9.0, 9.0, 9.0))
    )

    with pytest.raises(FrozenInstanceError):
        setattr(retained_fixture, field_name, replacement)


@pytest.mark.parametrize("field_name", ("onnx_bytes", "x", "y", "expected_z"))
def test_retained_fixture_fields_cannot_be_deleted(retained_fixture, field_name):
    with pytest.raises(FrozenInstanceError):
        delattr(retained_fixture, field_name)


def test_retained_graph_bytes_cannot_be_modified(retained_fixture):
    with pytest.raises(TypeError):
        retained_fixture.onnx_bytes[0] = 0


@pytest.mark.parametrize("field_name", ("x", "y", "expected_z"))
@pytest.mark.parametrize("level", ("tensor", "row"))
def test_retained_tensors_cannot_be_modified_at_either_level(
    retained_fixture, field_name, level
):
    tensor = getattr(retained_fixture, field_name)

    with pytest.raises(TypeError):
        if level == "tensor":
            tensor[0] = (0.0, 0.0, 0.0)
        else:
            tensor[0][0] = 0.0


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
@pytest.mark.parametrize("location", ("root", "schema_version", "shape", "x_hex"))
def test_loader_rejects_nonstandard_json_constants(tmp_path, constant, location):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    if location == "root":
        raw_payload = constant.encode("utf-8")
    else:
        replacements = {
            "schema_version": ('"schema_version": 1', f'"schema_version": {constant}'),
            "shape": ('"shape": [2, 3]', f'"shape": [{constant}, 3]'),
            "x_hex": (
                f'"x_hex": {json.dumps(document["payloads"]["x_hex"])}',
                f'"x_hex": {constant}',
            ),
        }
        original_pair, replacement_pair = replacements[location]
        serialized = json.dumps(document)
        assert serialized.count(original_pair) == 1
        raw_payload = serialized.replace(original_pair, replacement_pair, 1).encode("utf-8")
    onnx_path, payload_path, digests = _write_raw_payload_fixture(tmp_path, raw_payload)

    with pytest.raises(ValueError, match=r"migraphx-add-relu:.*JSON"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)


@pytest.mark.parametrize(
    "field_path",
    [
        *[
            pytest.param((key,), id=f"root-{key}")
            for key in ("schema_version", "probe", "shape", "layout", "encoding", "payloads")
        ],
        *[
            pytest.param(("payloads", key), id=f"payload-{key}")
            for key in ("x_hex", "y_hex", "expected_z_hex")
        ],
    ],
)
@pytest.mark.parametrize("identical", (True, False), ids=("identical", "conflicting"))
def test_loader_rejects_duplicate_json_object_keys(tmp_path, field_path, identical):
    from migraphx_add_relu_fixture import load_migraphx_add_relu_fixture

    document = _selected_document()
    value = document
    for field in field_path:
        value = value[field]
    key = field_path[-1]
    first_value = value if identical else "conflicting value"
    original_pair = f"{json.dumps(key)}: {json.dumps(value)}"
    duplicate_pair = f"{json.dumps(key)}: {json.dumps(first_value)}, {original_pair}"
    serialized = json.dumps(document)
    assert serialized.count(original_pair) == 1
    raw_payload = serialized.replace(original_pair, duplicate_pair, 1).encode("utf-8")
    onnx_path, payload_path, digests = _write_raw_payload_fixture(tmp_path, raw_payload)

    with pytest.raises(ValueError, match=r"migraphx-add-relu:.*JSON"):
        load_migraphx_add_relu_fixture(onnx_path, payload_path, **digests)
