# Foundation numerical output contracts

`tools/foundation_numeric_fixtures.py` implements the three selected numerical
assertions for [Freeze W0 fixtures, probes, Kokoro, and operational bounds](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107).
`tools/hip_vector_add_fixture.py` loads the selected HIP source with a
caller-supplied whole-file digest. These CPU-only interfaces check numbers
and retained bytes, respectively; they are not the complete nine-probe
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

## Retained HIP source

The selected vector-add source remains `tools/buildroot/probe/hello.hip`. Its
whole-file SHA-256 is
`729b393536433e9837ff5950b021439c7c59ae50a27545d3a264b1d60063422b`.
The file is retained unchanged; this increment does not regenerate, compile,
or execute it. The selected inputs and exact numerical assertion remain
`N=2^20`, `a[i]=i`, `b[i]=2*i`, and `c[i]=3*i`.

`load_hip_vector_add_fixture(path, *, expected_sha256)` is the public loader
in `tools/hip_vector_add_fixture.py`. The caller supplies the 64-character
lowercase hexadecimal SHA-256 from the externally reviewed fixture record.
The loader validates that digest's shape before accessing the file, reads
its complete bytes, and rejects a digest mismatch with a descriptive
`ValueError`. Malformed digests also raise `ValueError`; ordinary filesystem
read errors propagate. It does not decode, parse, compile, or execute the
source.

The result is a frozen, slotted `HipVectorAddFixture`: `.source` contains the
retained immutable `bytes`, and `.sha256` contains the verified lowercase
hexadecimal digest. Ordinary assignment to either public field is refused.

Successful loading establishes equality of the complete file bytes with
the supplied digest. It does not establish that the supplied digest was
independently reviewed or that the source was selected from an acceptable
origin. Deriving the expected digest from the same file during loading is
not an external fixture binding. Compilation, device selection, runtime/API
status, synchronization, package origins and dependencies, and operating
bounds require their separate evidence.

A later runtime adapter must supply the genuinely observed output to
`validate_numeric_output("hip-vector-add", output)` as a flat Python
sequence of 1,048,576 values without altering the values. That independent
checker requires exactly `3*i` at every zero-based index; loading source
bytes does not produce or validate a numerical runtime result.

## Evidence and remaining gates

`pytest tests/test_foundation_numeric_fixtures.py -q` exercises the numerical
interface on constructed CPU data. Its outputs come from the selected
contract, not a production oracle used to generate test expectations. It
needs no GPU imports, subprocesses, model downloads, or model caches.

The focused command exercises real-file retention,
altered bytes, malformed digests, digest validation before file access,
ordinary filesystem errors, and immutable result fields through the public
file-and-digest interface. These checks concern retained source bytes; they
do not run the HIP source or establish a GPU result.

```sh
pytest tests/test_hip_vector_add_fixture.py tests/test_foundation_numeric_fixtures.py -q
```

These CPU contracts do not prove input dtype, device selection, compilation,
runtime/API status, synchronization, dependency closure, or package origins.
The separate rocBLAS and ONNX artifact preparations must be integrated and
reviewed before this page describes them as implemented. GPU adapters,
per-probe duration/resource limits, the six nonnumerical foundation
contracts, and the complete catalog's origin and dependency fields remain
in the fixture-freeze ticket. W1, W4, and W6 retain their own runtime gates;
CPU checks do not satisfy them.

The existing `run-local-inference-scenarios` procedure remains unchanged.
Connecting its consumers to the final reviewed catalog and recording the
source revision consumed belong to the fixture freeze, after the remaining
fields are settled. This partial increment does not freeze that catalog.
The completed fixture freeze is a prerequisite of the Lemonade family
build; the build is not a prerequisite of this CPU-only preparation.
