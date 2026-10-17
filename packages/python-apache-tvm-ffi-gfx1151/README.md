# python-apache-tvm-ffi-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/apache/tvm-ffi`
- Package version: `0.1.10`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-apache-tvm-ffi`
- Authoritative reference package: `aur/python-apache-tvm-ffi`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

apache-tvm-ffi supplies the TVM FFI ABI, its shared library and its Cython
bindings. xgrammar 0.2.x builds its Python bindings as a TVM-FFI module and
imports tvm_ffi at run time, and vLLM 0.30.0 imports xgrammar in every
process. The package builds the C++ core and the Cython module on the local
amdclang native-wheel lane.


## Scaffold notes

- Part of the vLLM runtime dependency closure (#110), as the xgrammar dependency.
- Renders through the Blackcat native-wheel lane; Blackcat's recipe does not name this package.
- scikit-build-core drives CMake with the ninja generator and runs Cython; setuptools-scm reads the version from the sdist metadata.

## Intentional Divergences

- Pins 0.1.10 instead of the AUR 0.1.14.post1 package: xgrammar 0.2.3 requires apache-tvm-ffi >=0.1.9 at build and run time, and vLLM 0.30.0 requirements/rocm.txt pins apache-tvm-ffi ==0.1.10, so 0.1.10 meets both.
- Builds the C++ core, the bundled libbacktrace and the Cython module through the Blackcat native-wheel compiler lane with amdclang and Zen 5 flags. The wheel is a cp312-abi3 wheel (pyproject `wheel.py-api = "cp312"`).
- Depends on glibc, libgcc, libstdc++, python-gfx1151 and python-typing_extensions. Upstream 0.1.10 declares only typing-extensions >=4.5.
- Builds with `skip_dependency_check = true`: scikit-build-core's `get_requires_for_build_wheel` hook asks the no-isolation frontend for the PyPI `cmake` distribution, but Arch supplies CMake as `/usr/bin/cmake`, which the scikit-build-core backend finds and uses, so the frontend dependency check is stricter than the actual build.
- Compiles C without LTO (`drop_lto_from_cflags = true`) while C++ keeps makepkg's `-flto=auto`. The only C code is the bundled libbacktrace, a CMake ExternalProject whose autoconf configure gets `CMAKE_C_FLAGS`. Under `-flto`, its object-format probe (`filetype.awk` on `conftest.o`) reads LLVM bitcode instead of ELF, so configure builds `unknown.c` with `BACKTRACE_SUPPORTED=0`. That backend never sets `syminfo_fn`, and TVM-FFI's backtrace callback then calls a NULL pointer on the first raised error. 0.1.10-1 shipped that build. A 2026-09-25 flag matrix in the W2A root reproduced the crash with LTO whether or not `-enable-gvn-hoist`/`-enable-gvn-sink` were set, and never without LTO; configure with LTO-free CFLAGS and makepkg's LTO LDFLAGS detects `elf.lo` and `BACKTRACE_ELF_SIZE 64`. Drop this when upstream libbacktrace's filetype probe recognizes LLVM bitcode or tvm-ffi stops passing CFLAGS to the configure step; the package() guard catches a regression either way.
- Passes `TVM_FFI_BACKTRACE_ON_SEGFAULT=OFF`. With it ON, the SIGSEGV handler re-enters `TVMFFIBacktrace`, which blocks on the non-recursive mutex the crashing thread already holds, so any crash in the backtrace path hangs the process instead of failing. The trade-off is no TVM-FFI backtrace on a segfault; error backtraces through libbacktrace stay on. Drop this only after upstream makes the handler safe to re-enter.
- Passes `CMAKE_AR` and `CMAKE_RANLIB` as the ROCm LLVM `llvm-ar` and `llvm-ranlib`, which match amdclang and index LLVM bitcode archives, following the python-pytorch-opt-rocm-gfx1151 convention.
- package() fails unless `tvm_ffi/lib/libtvm_ffi.so` contains libbacktrace's elf.c message `no debug info in ELF executable`, so an unknown-format libbacktrace cannot ship again.

## Update Notes

- Move this pin with xgrammar: re-check xgrammar's pyproject apache-tvm-ffi floor and vLLM's requirements/rocm.txt pin together before updating.
- xgrammar links libtvm_ffi.so and compiles against these headers, so rebuild python-xgrammar-gfx1151 after any update.
- The build is CPU-only: CMakeLists.txt enables CXX and C, and the pyproject passes TVM_FFI_BUILD_TESTS=OFF (googletest would need a fetch). No CUDA probe runs.
- After publishing a rebuilt package, verify `import tvm_ffi`, `tvm_ffi.core` and `python -m tvm_ffi.config --libfiles` through the installed local Python lane.
- On 2026-09-25, added at 0.1.10 for the generation-C W2A closure (#110, #111) as the runtime and build dependency of python-xgrammar-gfx1151. vLLM 0.30.0 imports xgrammar in every process, and xgrammar imports tvm_ffi (`xgrammar/base.py`, `exception.py` and `load_binding.py`). The upstream build compiles 23 C++ sources, 33 libbacktrace C files and one Cython module; expect a few minutes of CPU time. It is built in the rootless C build root in the vLLM lease job.
- On 2026-09-25, rebuilt as 0.1.10-2: 0.1.10-1 crashed in libbacktrace on the first raised TVM-FFI error and then deadlocked in its segfault handler, which hung xgrammar's build-time stub generation. After installing a rebuild, run `tvm_ffi.core._object_type_key_to_index('no.such.Key')` under a timeout: it must return promptly instead of hanging.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
