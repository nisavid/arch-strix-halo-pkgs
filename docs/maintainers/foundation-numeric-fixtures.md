# Foundation numerical fixtures and output contracts

`tools/foundation_numeric_fixtures.py` implements the three selected numerical
assertions for [Freeze W0 fixtures, probes, Kokoro, and operational bounds](https://github.com/nisavid/arch-strix-halo-pkgs/issues/107).
`tools/hip_vector_add_fixture.py` loads the selected HIP source with a
caller-supplied whole-file digest. `tools/rocblas_sgemm_fixture.py` loads and
verifies the retained rocBLAS input and expected-output bytes. These CPU-only
interfaces check numbers and retained bytes; they are not the complete
nine-probe foundation catalog or a GPU runner.

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

## Retained rocBLAS artifact

`inference/fixtures/rocblas-sgemm.json` retains the selected 2×2 SGEMM
fixture. Its complete-file SHA-256 is:

```text
05da9cb62a4841a3a0bf3bbcc22495457937d0adca19ff4e0914847f8de625e9
```

The schema-v1 JSON record fixes `probe = "rocblas-sgemm"`, shape `[2,2]`,
column-major layout, and `ieee754-binary32-little-endian-hex` encoding.
Each matrix payload contains 32 lowercase hexadecimal digits representing
four binary32 values. The scalar payloads contain eight digits each. The
operation has no transpose, leading dimensions 2, alpha 1, and beta 0.

| Payload | Decoded column-major values |
| --- | --- |
| A | `(1, 3, 2, 4)` |
| B | `(5, 7, 6, 8)` |
| Expected C | `(19, 43, 22, 50)` |

The file uses UTF-8, two-space indentation, LF, and one final newline.
Changing even its whitespace changes the recorded digest. Consumers pin
the digest from this external record together with the reviewed Git revision,
not a digest asserted inside the artifact.

`load_rocblas_sgemm_fixture(path: Path, *, expected_sha256: str)` returns a
frozen `RocblasSgemmFixture` with tuple fields `a`, `b`, and `expected_c`,
scalar fields `alpha` and `beta`, and the verified `sha256`. The digest is
mandatory and must contain exactly 64 lowercase hexadecimal digits. The
loader reads the file once and verifies its complete bytes before decoding
UTF-8 or JSON. It rejects duplicate JSON fields, unsupported or incomplete
schema fields, changed shape/layout/encoding/SGEMM parameters, malformed hex
or payload lengths, and nonfinite numbers. Digest and content failures raise
descriptive `ValueError`; filesystem failures retain their normal `OSError`
subtype.

A matching digest binds bytes only relative to the supplied external record.
It does not establish source provenance or approve a different numerical
fixture. The loader does not compute an SGEMM result or replace the existing
validator's independent literal oracle. Loading `expected_c` is not an
observed rocBLAS result. The loader imports no numerical or GPU runtime,
writes no files, and creates no executable scenario plan.

## Partial numerical artifact and consumer index

This partial index connects the selected numerical probe IDs to the retained
inputs and CPU consumers in this revision. MIGraphX has the selected output
assertion, but its retained graph, payload, and loader preparation is not
integrated here. The index is not a complete foundation catalog or an
executable scenario plan.

| Probe | Source or retained input | CPU consumer boundary |
| --- | --- | --- |
| `hip-vector-add` | `tools/buildroot/probe/hello.hip` | `tools/hip_vector_add_fixture.py` verifies externally pinned complete-file bytes and returns immutable `.source` and `.sha256`; it does not decode, parse, compile, or execute the source. |
| `rocblas-sgemm` | `inference/fixtures/rocblas-sgemm.json` | `tools/rocblas_sgemm_fixture.py` verifies externally pinned complete-file bytes and decodes fixture values; loading expected C is not an observed SGEMM result. |
| `migraphx-add-relu` | Selected x and y above; retained graph and payload preparation is not integrated. | `validate_numeric_output("migraphx-add-relu", output)` checks the selected two-row numerical answer; no retained-input loader is integrated here. |

## Evidence and remaining gates

Run the integrated retained-input loader and output-validator checks together:

```sh
pytest tests/test_hip_vector_add_fixture.py tests/test_rocblas_sgemm_fixture.py tests/test_foundation_numeric_fixtures.py -q
```

The HIP loader checks exercise real-file retention, altered bytes, malformed
digests, digest validation before file access, ordinary filesystem errors,
and immutable result fields through the public file-and-digest interface.
The rocBLAS loader checks use real temporary files and the retained artifact.
The output-validator checks use constructed CPU data; expected values come
from the selected contract, not a production oracle. The loaders and output
validator need no GPU imports, subprocesses, model downloads, or model caches.

Byte integrity and exact finite output equality are independent checks.
Neither establishes runtime binary32 behavior, target selection, API success,
compilation, synchronization, package origins, or dependency closure.

The separate MIGraphX retained-artifact and loader preparation must be
integrated and reviewed before this page describes it as implemented.
Catalog-dependent execution requires the retained artifact and loader
revisions to join the final reviewed catalog, reviewed foundation package
origins and dependencies, per-probe operating bounds, and consumer result
projections. GPU adapters, per-probe duration/resource limits, and the six
nonnumerical foundation contracts remain in the fixture-freeze ticket.
W1, W4, and W6 retain their own runtime gates; CPU checks do not satisfy them.

The existing `run-local-inference-scenarios` procedure remains unchanged.
Connecting its consumers to the final reviewed catalog and recording the
source revision consumed belong to the fixture freeze, after the remaining
fields are settled. This partial increment does not freeze that catalog.
The completed fixture freeze is a prerequisite of the Lemonade family
build; the build is not a prerequisite of this CPU-only preparation.
