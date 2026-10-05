# Foundation numerical output contracts

`tools/foundation_numeric_fixtures.py` implements the three selected numerical
assertions for [Freeze W0 fixtures, probes, Kokoro, and operational bounds](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107).
It is a CPU-only checker for observed numbers, not the complete nine-probe
foundation catalog or a GPU runner.

## Public interface

`validate_numeric_output(probe, output)` returns `None` only when every value
and the shape match the selected fixture. Otherwise it raises `ValueError`
with the probe and the invalid shape or value location. Values must be real
numbers, excluding booleans and complex numbers. Nonfinite values cannot
equal any selected expected value and are rejected. Comparison is exact
numeric equality: signed zero is accepted, but a tiny nonzero difference is
not. The checker does not round, cast to binary32, or apply a tolerance.

The supported containers are sized, indexed Python sequences, such as lists,
tuples, and ranges. A runtime adapter must project its observed tensor into
the required sequence shape without altering the values. A NumPy array or
GPU tensor is not this interface's container contract.

| Probe | Output shape | Expected values |
| --- | --- | --- |
| `hip-vector-add` | Flat sequence of 1,048,576 values | At every zero-based index `i`, `3*i` |
| `rocblas-sgemm` | Flat sequence of four values, column-major | `[19, 43, 22, 50]` |
| `migraphx-add-relu` | Two nested rows of three values | `[[1.5, 0, 0], [0, 0, 1]]` |

## Selected inputs

The [recorded numerical selection](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107#issuecomment-5987546437)
fixes these deliberately small or exactly representable binary32 values:

- HIP vector add uses `N=2^20`, `a[i]=i`, and `b[i]=2*i`. The published
  `tools/buildroot/probe/hello.hip` checks `c[i]=3*i` for every element.
- rocBLAS uses 2×2 SGEMM, no transpose, leading dimensions 2, `alpha=1`,
  and `beta=0`. In row notation, `A=[[1,2],[3,4]]`, `B=[[5,6],[7,8]]`, and
  `C=[[19,22],[43,50]]`. The interface accepts C's column-major order,
  not the row-major flattening.
- MIGraphX uses a binary32 Add→Relu graph with shape `[2,3]`, opset 13,
  and IR 8. Inputs are `x=[[1,-2,3],[-4,5,-6]]` and
  `y=[[0.5,1,-4],[1,-6,7]]`.

## Evidence and remaining gates

`pytest tests/test_foundation_numeric_fixtures.py -q` exercises the public
interface on constructed CPU data. Its outputs come from the selected
contract, not a production oracle used to generate test expectations. It
needs no GPU imports, subprocesses, model downloads, or model caches.

These assertions do not prove input dtype, device selection, compilation,
runtime/API status, synchronization, dependency closure, or package origins.
The serialized HIP/ONNX fixtures and their digests, GPU adapters, per-probe
duration/resource limits, and the six nonnumerical foundation contracts
remain in the fixture-freeze ticket. W1, W4, and W6 retain their own runtime
gates; CPU checks do not satisfy them.

The existing `run-local-inference-scenarios` procedure remains unchanged.
Connecting its consumers to the final reviewed catalog belongs to the
fixture freeze, after those remaining fields are settled. This partial
numeric implementation neither freezes that catalog nor clears its native
dependency on the Lemonade family build.
