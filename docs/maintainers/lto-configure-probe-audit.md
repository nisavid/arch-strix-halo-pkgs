# LTO and Object-Probing Configure Audit

This record covers the audit tracked in
[#168](https://github.com/nisavid/arch-strix-halo-pkgs/issues/168), a
sub-issue of W2A #98 that blocks #111. It asks one question: did makepkg's
link-time optimization (LTO) silently change a configure result in any
package lane? For W2A through the lease commit `0514904` the answer is no:
0 lanes are affected and 38 are clear. One vLLM archive check is still
pending.

The per-lane build-root details live in
[Generation-C Build Root](c-build-root.md). This page keeps the cross-lane
audit separate, so it can be rerun and updated on its own.

## The defect class

Some autoconf scripts compile a test object and then read the object file
to decide what to build. When makepkg's `-flto=auto` reaches such a
configure, the test object holds LLVM bitcode rather than native ELF. The
probe then picks a fallback, and the build still succeeds. The failure only
shows up at runtime.

The known instance is `python-apache-tvm-ffi-gfx1151` 0.1.10-1. Its vendored
libbacktrace ran `filetype.awk` on a bitcode `conftest.o`, chose
`unknown.lo`, and set `BACKTRACE_SUPPORTED=0`. As a result `syminfo_fn`
stayed NULL. The package built cleanly, but any tvm-ffi error that printed a
backtrace jumped to address 0 and segfaulted inside `backtrace_full`. The
segfault handler then re-entered and deadlocked. 0.1.10-1 is quarantined,
and 0.1.10-2 carries the fix.

## Flag matrix: LTO, not gvn

The native-wheel render template (`tools/render_recipe_scaffolds.py`) also
adds `-mllvm -enable-gvn-hoist` and `-mllvm -enable-gvn-sink` to about 22
lanes. Those flags were the first suspect, so a controlled rebuild of
tvm-ffi separated them from LTO:

| Variant | Flags | Result |
| --- | --- | --- |
| A | full lane flags (gvn + LTO) | segfault |
| B | LTO, no gvn | segfault |
| C | gvn, no LTO | ok |
| D | plain `-O2` | ok |

LTO alone reproduces the fault. The gvn flags are cleared, and they need no
blast-radius rebuild. The tvm-ffi lane's divergence notes record this
negative result.

## Scope and method

- The audit was read-only: no builds, configure A/B runs, GPU work or host
  changes. It covered the W2A sources at `0514904` and the F/W1 foundation
  sources, plus pinned sdists and tarballs (sha256-verified when fetched)
  and string or symbol checks on the shipped W2A archives.
- The build root's pinned makepkg.conf sets `OPTIONS=(... lto)` and
  `LTOFLAGS=-flto=auto`. makepkg's `lto.sh` appends only to `CFLAGS`,
  `CXXFLAGS` and `LDFLAGS`. It never touches `HIPFLAGS`.
- **`.BUILDINFO` `options = lto` is not evidence.** That field only echoes
  the global makepkg.conf. It does not reflect a per-PKGBUILD `!lto` or a
  lane that replaces its flags, so it does not show whether a lane's objects
  were built with LTO.

## Lane table

LTO column: **yes** means `-flto` reaches the compile flags. **link-only**
means it appears only in `LDFLAGS`. **no** means it is disabled or stripped.
**n/a** means nothing native is compiled. A libbacktrace marker check found
0 hits wherever it says so.

### Native-wheel lanes

| Lane | LTO | Vendored configure | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| apache-tvm-ffi 0.1.10-2 | CXX/LD yes; CFLAGS stripped | libbacktrace autoconf (the known instance) | CLEAR (fixed) | `drop_lto_from_cflags` plus a `wheel_required_strings` guard; the shipped `.so` has libbacktrace's `elf.c` strings |
| xgrammar 0.2.3-1 | yes | none run; system tvm_ffi | CLEAR | NEEDED `libtvm_ffi.so`, no libbacktrace strings |
| uvloop 0.22.1-2 | yes | vendored libuv never run (system libuv) | CLEAR | NEEDED `libuv.so.1`, no `uv_*` defined |
| numpy 2.5.3-1 | yes | none; meson runs its long-double probe | CLEAR | `NPY_SIZEOF_LONGDOUBLE 16` |
| pybase64 1.5.0-1 | yes | CMake reads compiler logs, not objects | CLEAR | AVX512 codecs present |
| sentencepiece 0.2.2-1 | yes | CMake only (abseil, protobuf-lite) | CLEAR | no configure or libtool files |
| pillow 12.3.0-1 | yes | none; system libraries | CLEAR | no configure or libtool files |
| pyyaml 6.0.3-2 | yes | none; system libyaml | CLEAR | NEEDED `libyaml-0.so.2` |
| psutil 7.2.2-2 | yes | none; compile-only checks | CLEAR | no object reads |
| httptools 0.8.0-2 | yes | none run; system llhttp | CLEAR | NEEDED `libllhttp.so.9.3` |
| aiohttp 3.14.3-1 | yes | none; system deps | CLEAR | NEEDED `libllhttp.so.9.3` |
| msgspec 0.21.1-2 | yes | none | CLEAR | single C extension |
| frozenlist 1.8.0-2 | yes | none | CLEAR | Cython only |
| multidict 6.9.1-1 | yes | none | CLEAR | C only |
| yarl 1.25.1-1 | yes | none | CLEAR | Cython only |
| zstandard 0.25.0-1 (not built) | would be yes | none; bundled zstd compiled directly | CLEAR | sdist scan |
| asyncpg 0.31.0-1 (not built) | would be yes | none | CLEAR | sdist scan |
| duckdb 1.5.3-1 (not built) | would be yes | no autoconf; ExternalProjects not built | CLEAR | sdist scan |
| auto-round 0.13.0-1 (not built) | n/a | none | CLEAR | pure Python |
| llmcompressor 0.10.0.1-5 (not built) | n/a | none | CLEAR | pure Python |
| accelerate 1.15.0-1 | n/a | none | CLEAR | arch `any` |
| compressed-tensors 0.17.0-1 | n/a | none | CLEAR | arch `any` |
| einops 0.8.2-1 | n/a | none | CLEAR | arch `any` |
| py-cpuinfo 9.0.0-1 | n/a | none | CLEAR | arch `any` |
| prometheus-fastapi-instrumentator 8.1.0-1 | n/a | none | CLEAR | arch `any` |
| torchao 0.18.0-1 | yes | no autoconf; CPU kernels off | CLEAR | ships only `_C.abi3.so` |

### Major lanes

| Lane | LTO | Vendored configure | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| pytorch 2.12.0-5 | no (flags replaced) | CMake or header-only; ExternalProjects disabled | CLEAR | no `-flto` or IPO in source or patches |
| triton 3.8.0 | yes | none | CLEAR | 0 markers in `libtriton.so` |
| aotriton 0.13b-1 | yes | none; system liblzma | CLEAR | 0 markers in shipped libraries |
| flash-attn 2.8.4-16 | no (`!lto`) | none | CLEAR | 0 markers |
| torchvision 0.27.1-1 | link-only | none | CLEAR | 0 markers |
| torch-migraphx 1.2-10 | link-only | none | CLEAR (two audits agree) | 0 markers |
| vllm 0.30.0-1 | no (`!lto` plus flag stripping) | HIP build uses only a pure-Python FetchContent | CLEAR (static only) | archive check pending, see below |
| openai-harmony 0.0.8-2 | no (flags unset) | none | CLEAR | 0 markers |

### Foundation (F/W1) lanes

| Lane | LTO | Vendored configure | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| therock-gfx1151 7.14.1-1 split family | not reachable (repackaging only) | built upstream by AMD CI, not by ASHP | CLEAR | `BACKTRACE_SUPPORTED 1`; native ELF `elf.o`, no `unknown.o` |
| migraphx-gfx1151 7.14.1-1 | no | none; pass/fail compile checks | CLEAR | built by the staging script, no IPO |
| python-gfx1151 3.14.7-1 | yes (`--with-lto`, fat objects) | top-level configure probes read the linked executable | CLEAR | native after link; `DOUBLE_IS_LITTLE_ENDIAN_IEEE754 1` |

Lane names drop the `python-` prefix and `-gfx1151`/`-rocm-gfx1151` suffix
except in the foundation table. The TheRock split family counts as one row,
so the tables hold 37 distinct lanes plus that family.

## Mitigations

- **`drop_lto_from_cflags`** (recipe policy) makes the rendered PKGBUILD call
  `_drop_lto_from_cflags`, which strips `-flto` from `CFLAGS` so C configure
  probes see native objects. C++ and link flags keep LTO.
- **`wheel_required_strings`** (recipe policy) adds a `package()` guard that
  fails the build unless a shipped file contains a variant-specific string.
  tvm-ffi requires libbacktrace's ELF-reader message in
  `tvm_ffi/lib/libtvm_ffi.so`, which only exists when `elf.lo` was built.

Any lane that vendors an autoconf subproject and keeps makepkg LTO should
adopt both.

## Pending check: vLLM archive

The vLLM 0.30.0-1 verdict comes from static analysis of the pinned tarball
and PKGBUILD. Its W2A archive is not built yet. Once it exists, confirm that
no shipped `.so` carries libbacktrace markers or LLVM bitcode sections:

```sh
bsdtar -xOf <vllm-archive> '*.so' | grep -ac 'backtrace_create_state'   # expect 0
readelf -S <extracted.so> | grep -E '\.llvmbc|\.llvm\.lto'            # expect no output
```

## Non-blocking follow-ups

These are hygiene suggestions, not defects:

- **Render-time lint.** Flag any lane whose sources contain `filetype.awk`
  or `ltmain.sh` while `lto` is active and `drop_lto_from_cflags` is unset.
- **LTO only in `LDFLAGS`.** torchvision and torch-migraphx replace
  `CFLAGS` and `CXXFLAGS` without LTO but keep `-flto=auto` in `LDFLAGS`.
  The objects are native, so this is harmless. For consistency, strip it or
  set `!lto`.
- Before #111 relies on tvm-ffi, confirm no consumer still pins 0.1.10-1.
