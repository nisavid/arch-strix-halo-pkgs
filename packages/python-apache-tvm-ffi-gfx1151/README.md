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

## Update Notes

- Move this pin with xgrammar: re-check xgrammar's pyproject apache-tvm-ffi floor and vLLM's requirements/rocm.txt pin together before updating.
- xgrammar links libtvm_ffi.so and compiles against these headers, so rebuild python-xgrammar-gfx1151 after any update.
- The build is CPU-only: CMakeLists.txt enables CXX and C, and the pyproject passes TVM_FFI_BUILD_TESTS=OFF (googletest would need a fetch). No CUDA probe runs.
- After publishing a rebuilt package, verify `import tvm_ffi`, `tvm_ffi.core` and `python -m tvm_ffi.config --libfiles` through the installed local Python lane.
- On 2026-09-25, added at 0.1.10 for the generation-C W2A closure (#110, #111) as the runtime and build dependency of python-xgrammar-gfx1151. vLLM 0.30.0 imports xgrammar in every process, and xgrammar imports tvm_ffi (`xgrammar/base.py`, `exception.py` and `load_binding.py`). The upstream build compiles 23 C++ sources, 33 libbacktrace C files and one Cython module; expect a few minutes of CPU time. It is built in the rootless C build root in the vLLM lease job.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
