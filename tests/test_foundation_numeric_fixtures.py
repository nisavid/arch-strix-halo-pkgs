from pathlib import Path
import math
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from foundation_numeric_fixtures import validate_numeric_output


def test_rocblas_rejects_row_major_output_with_a_descriptive_error():
    with pytest.raises(ValueError, match="rocblas-sgemm.*index 1"):
        validate_numeric_output("rocblas-sgemm", [19, 22, 43, 50])


@pytest.mark.parametrize("output", ([19, 43, 22], [19, 43, 22, 50, 0]))
def test_rocblas_requires_exactly_four_values(output):
    with pytest.raises(ValueError, match="rocblas-sgemm.*four values"):
        validate_numeric_output("rocblas-sgemm", output)


def test_rocblas_accepts_the_selected_column_major_result():
    assert validate_numeric_output("rocblas-sgemm", [19.0, 43.0, 22.0, 50.0]) is None


def test_migraphx_checks_the_selected_two_by_three_values():
    with pytest.raises(ValueError, match="migraphx-add-relu.*row 1.*column 2"):
        validate_numeric_output("migraphx-add-relu", [[1.5, 0, 0], [0, 0, 2]])


def test_migraphx_accepts_exact_finite_values_in_the_selected_shape():
    assert (
        validate_numeric_output("migraphx-add-relu", [[1.5, 0.0, 0.0], [0.0, 0.0, 1.0]])
        is None
    )


@pytest.mark.parametrize("boolean", (False, True))
def test_migraphx_does_not_accept_boolean_values_as_numbers(boolean):
    output = [[1.5, 0, 0], [0, 0, 1]]
    output[1][2 if boolean else 1] = boolean
    with pytest.raises(ValueError, match="migraphx-add-relu.*finite real number"):
        validate_numeric_output("migraphx-add-relu", output)


def test_hip_checks_the_last_element_not_a_sample():
    output = list(range(0, 3 * 2**20, 3))
    output[-1] = 3_145_726
    with pytest.raises(ValueError, match="hip-vector-add.*index 1048575"):
        validate_numeric_output("hip-vector-add", output)


def test_hip_accepts_every_selected_vector_value():
    assert validate_numeric_output("hip-vector-add", range(0, 3_145_728, 3)) is None


def test_rocblas_rejects_complex_values_even_when_the_real_parts_match():
    with pytest.raises(ValueError, match="rocblas-sgemm.*finite real number"):
        validate_numeric_output("rocblas-sgemm", [19 + 0j, 43, 22, 50])


@pytest.mark.parametrize("position", range(4))
@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_rocblas_rejects_nonfinite_values_at_every_position(position, value):
    output = [19, 43, 22, 50]
    output[position] = value
    with pytest.raises(ValueError, match=f"rocblas-sgemm.*index {position}"):
        validate_numeric_output("rocblas-sgemm", output)


def test_rocblas_does_not_round_a_nearby_value_to_binary32():
    with pytest.raises(ValueError, match="rocblas-sgemm.*index 0"):
        validate_numeric_output("rocblas-sgemm", [math.nextafter(19.0, 20.0), 43, 22, 50])


@pytest.mark.parametrize(
    "output",
    (None, [], [1.5, 0, 0, 0, 0, 1], [[1.5, 0], [0, 0]], [[1.5, 0, 0], [0, 0, 1], [0, 0, 0]]),
)
def test_migraphx_rejects_wrong_or_flattened_shapes(output):
    with pytest.raises(ValueError, match="migraphx-add-relu.*2x3 tensor"):
        validate_numeric_output("migraphx-add-relu", output)


@pytest.mark.parametrize("position", range(6))
@pytest.mark.parametrize("value", (float("nan"), float("inf"), "0", None, 0j))
def test_migraphx_rejects_invalid_values_at_every_position(position, value):
    output = [[1.5, 0, 0], [0, 0, 1]]
    row, column = divmod(position, 3)
    output[row][column] = value
    with pytest.raises(ValueError, match=f"migraphx-add-relu.*row {row}.*column {column}"):
        validate_numeric_output("migraphx-add-relu", output)


def test_migraphx_does_not_tolerate_a_tiny_nonzero_output():
    with pytest.raises(ValueError, match="migraphx-add-relu.*row 0.*column 1"):
        validate_numeric_output("migraphx-add-relu", [[1.5, 1e-50, 0], [0, 0, 1]])


def test_migraphx_accepts_signed_zero_by_numeric_equality():
    assert validate_numeric_output("migraphx-add-relu", ((1.5, -0.0, 0), (0, -0.0, 1))) is None


@pytest.mark.parametrize("output", (None, [], range(1_048_575), range(1_048_577)))
def test_hip_requires_the_selected_vector_length(output):
    with pytest.raises(ValueError, match="hip-vector-add.*flat vector of 1048576 values"):
        validate_numeric_output("hip-vector-add", output)


@pytest.mark.parametrize("value", (False, float("nan"), float("inf"), "0", [0], 0j))
def test_hip_requires_real_finite_scalar_values(value):
    output = list(range(0, 3_145_728, 3))
    output[0] = value
    with pytest.raises(ValueError, match="hip-vector-add.*index 0"):
        validate_numeric_output("hip-vector-add", output)


def test_hip_checks_an_interior_element_exactly():
    output = list(range(0, 3_145_728, 3))
    output[12_345] = math.nextafter(37_035.0, 37_036.0)
    with pytest.raises(ValueError, match="hip-vector-add.*index 12345"):
        validate_numeric_output("hip-vector-add", output)


def test_unknown_probe_is_a_descriptive_validation_error():
    with pytest.raises(ValueError, match="Unknown numerical probe"):
        validate_numeric_output("other", [])
