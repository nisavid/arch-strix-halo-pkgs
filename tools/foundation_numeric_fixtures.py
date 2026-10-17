"""Validate the selected W0 numerical outputs without loading a GPU runtime."""

from collections.abc import Sequence
from numbers import Real


def validate_numeric_output(probe: str, output: object) -> None:
    """Check exact numeric values and shape; return None or raise ValueError.

    Outputs are Python sequences of real scalars (not booleans). MIGraphX
    uses two nested rows; HIP and rocBLAS use flat sequences. Callers must
    project runtime tensors to those shapes without rounding their values.
    This checks numbers only, not dtype, device, origins, or runtime status.
    """
    if probe == "hip-vector-add":
        if not isinstance(output, Sequence) or len(output) != 2**20:
            raise ValueError(f"{probe}: expected a flat vector of 1048576 values")
        for index, actual in enumerate(output):
            if isinstance(actual, bool) or not isinstance(actual, Real):
                raise ValueError(f"{probe}: index {index} must be a finite real number")
            if actual != 3 * index:
                raise ValueError(f"{probe}: index {index} must equal {3 * index}")
        return
    if probe == "migraphx-add-relu":
        if (
            not isinstance(output, Sequence)
            or len(output) != 2
            or any(not isinstance(row, Sequence) or len(row) != 3 for row in output)
        ):
            raise ValueError(f"{probe}: expected a 2x3 tensor")
        for row_index, (actual_row, expected_row) in enumerate(
            zip(output, ((1.5, 0, 0), (0, 0, 1)), strict=True)
        ):
            for column, (actual, expected) in enumerate(
                zip(actual_row, expected_row, strict=True)
            ):
                if isinstance(actual, bool) or not isinstance(actual, Real):
                    raise ValueError(
                        f"{probe}: row {row_index}, column {column} must be a finite real number"
                    )
                if actual != expected:
                    raise ValueError(
                        f"{probe}: row {row_index}, column {column} must equal {expected}"
                    )
        return
    if probe != "rocblas-sgemm":
        raise ValueError(f"Unknown numerical probe: {probe}")
    if not isinstance(output, Sequence) or len(output) != 4:
        raise ValueError(f"{probe}: expected four values in column-major order")
    for index, (actual, expected) in enumerate(
        zip(output, (19, 43, 22, 50), strict=True)
    ):
        if isinstance(actual, bool) or not isinstance(actual, Real):
            raise ValueError(f"{probe}: index {index} must be a finite real number")
        if actual != expected:
            raise ValueError(f"{probe}: index {index} must equal {expected}")
