# python-xgrammar-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/mlc-ai/xgrammar`
- Package version: `0.2.3`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `aur/python-xgrammar`
- Authoritative reference package: `aur/python-xgrammar`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

xgrammar is the grammar engine behind vLLM's default structured-output
backend. vLLM 0.30.0 imports it at module level in `vllm/parser/harmony.py`,
which the engine core, the offline `LLM` and the API server all reach, so no
vLLM process starts without it. The package builds the C++ engine and its
TVM-FFI bindings on the local amdclang native-wheel lane.


## Scaffold notes

- Part of the vLLM runtime dependency closure (#110).
- Renders through the Blackcat native-wheel lane; Blackcat's recipe does not name this package.
- scikit-build-core drives CMake with the ninja generator. CMake finds tvm_ffi through the installed python-apache-tvm-ffi-gfx1151 package, so that lane must be in the root before this build.

## Intentional Divergences

- Builds xgrammar 0.2.3 from the PyPI sdist instead of repacking a wheel like the AUR package, whose 0.2.x packages also omit the apache-tvm-ffi dependency and fail at `import xgrammar` with `No module named 'tvm_ffi'`.
- Pins 0.2.3 instead of the latest release: vLLM 0.30.0 requires xgrammar >=0.2.1,<1.0.0, its CUDA and CPU CI locks test 0.2.3 (the ROCm lock tests 0.2.1), and 0.2.3 publishes CPython 3.14 wheels.
- Builds the C++ grammar engine and its TVM-FFI bindings through the Blackcat native-wheel compiler lane with amdclang and Zen 5 flags, against python-apache-tvm-ffi-gfx1151.
- Carries every upstream runtime requirement from the published metadata, mapped to the local lanes: apache-tvm-ffi, pydantic, torch, transformers, triton, numpy and typing-extensions.
- Builds with `skip_dependency_check = true`: scikit-build-core's `get_requires_for_build_wheel` hook asks the no-isolation frontend for the PyPI `cmake` distribution, but Arch supplies CMake as `/usr/bin/cmake`, which the scikit-build-core backend finds and uses, so the frontend dependency check is stricter than the actual build.

## Update Notes

- Check vLLM's requirements/common.txt specifier and its requirements/test CI locks together before updating, and move python-apache-tvm-ffi-gfx1151 with it when the tvm-ffi floor changes.
- The build is CPU-only. CMakeLists.txt enables only CXX and never looks for CUDA; the CUDA token-bitmask kernel is a runtime JIT that vLLM does not call on ROCm, where Model Runner V2 applies bitmasks with its own Triton kernel. The package passes XGRAMMAR_ENABLE_CPPTRACE=OFF and XGRAMMAR_BUILD_CXX_TESTS=OFF explicitly, because both would build submodules.
- Upstream CMake adds `-Wall -Wextra -Werror` and `-flto=auto`. A 2026-09-25 syntax-only probe compiled all 22 C++ sources with amdclang 23, the lane's Zen 5 flags and those warnings without an error; the first package build is the full check. amdclang links with ld.lld, which reads the LTO bitcode archives.
- After publishing a rebuilt package, verify `import xgrammar`, then compile the Gemma 4 structured-output smoke schema with `xgrammar.GrammarCompiler` and fill a token bitmask on CPU through the installed local Python lane.
- On 2026-09-25, added at 0.2.3 for the generation-C W2A closure (#110, #111). vLLM 0.30.0 imports xgrammar at module level in `vllm/parser/harmony.py`, which every vLLM process reaches, and uses it for `response_format` json_schema requests. The upstream build compiles 22 C++ sources plus the bindings; expect about 5-10 minutes of CPU time. It is built in the rootless C build root in the vLLM lease job, after python-apache-tvm-ffi-gfx1151.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
