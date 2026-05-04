# python-triton-gfx1151

## Maintenance Snapshot

- Recipe package key: `triton`
- Scaffold template: `python-project-triton-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/triton.git`
- Package version: `3.0.0+git0ec280cf`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `15, 16, 17`
- Recipe dependencies: `therock, pytorch`
- Recorded reference packages: `extra/python-triton, cachyos-extra-znver4/python-triton`
- Authoritative reference package: `extra/python-triton`
- Advisory reference packages: `cachyos-extra-znver4/python-triton`
- Applied source patch files/actions: `3`

## Recipe notes

ROCm performance fork of Triton.

CRITICAL: Does NOT use TheRock's LLVM. TheRock ships LLVM 22 but
Triton's codebase expects ~LLVM 19 APIs. Triton downloads and builds
its own LLVM internally. Do NOT set LLVM_SYSPATH.

gfx11 support: warp_size=32 configured in backends/amd/compiler.py.

target_info and gluon are CUDA-only features -- NOT available in
the ROCm fork. This is expected and not a gap.

Triton compiler bug on gfx1151: the unified attention kernel
(triton_unified_attention.py:239) previously produced "operation
scheduled before its operands" errors. With Patch 2 below
(AttrsDescriptor __repr__) applied, torch.compile with Inductor
works correctly on gfx1151 — --enforce-eager is NOT required.
Verified with Qwen2.5-7B-Instruct: all AITER optimizations active,
correct output across multiple inference tests.

Inductor codegen bug: AttrsDescriptor in triton/backends/compiler.py
has no __repr__ method. torch Inductor codegen uses {triton_meta!r}
to serialize kernel metadata into generated Python source files.
Without __repr__, Python produces angle-bracket object repr
(<triton.backends.compiler.AttrsDescriptor object at 0x...>) which
is invalid Python syntax, causing SyntaxError at import time.
Fixed by Patch 2 below.

IMPORTANT: When switching between compilation configurations
(e.g., changing custom_ops, enabling/disabling AITER), stale
Inductor caches (/tmp/torchinductor_$USER/) and Triton caches
(~/.triton/cache/) must be cleared to avoid KeyError crashes
from mismatched guard expressions. The vLLM compile cache
(~/.cache/vllm/torch_compile_cache/) is config-hash-keyed and
does not require manual clearing.

## Scaffold notes

- Authoritative base: Arch python-triton 3.5.1-4 for distro integration and Python-3.14 carry patches.
- The recipe intentionally swaps in ROCm/triton main_perf instead of upstream triton-lang/triton. That makes Arch's package an advisory base rather than a source-identical one.
- Do not point Triton at TheRock's LLVM. The recipe notes that this ROCm fork still expects an older LLVM API line and must use its own compatible LLVM path instead.
- The renderer must include the package source patches in `prepare()` for this package. The `AttrsDescriptor.__repr__` edit is a runtime correctness patch, not cosmetic metadata; if it is absent from the installed package, torch.compile / Inductor can emit syntactically invalid generated Python.
- Rebuild and reinstall `python-triton-gfx1151` after patch-carry changes before treating compiled vLLM probes as repaired on the host.

## Intentional Divergences

- Uses Arch's Python packaging and integration baseline but deliberately swaps in ROCm/triton main_perf for the source lane.
- Builds Triton's compatible sidecar LLVM instead of trying to force the ROCm fork onto TheRock's installed LLVM API line.

## Update Notes

- Check Arch's current Triton Python packaging first for Python-version fixes and install layout changes, then re-evaluate whether ROCm/triton still needs its separate LLVM lane.
- Keep pkgver and provides aligned with the ROCm fork's generated wheel metadata from python/setup.py; do not reuse Arch's triton-lang release version when the source lane is ROCm/triton main_perf.
- Keep local source edits as patch files; this package is a likely upstream-candidate area.
- The `AttrsDescriptor.__repr__` patch is runtime correctness carry. If it is absent from the installed package, torch.compile / Inductor can emit syntactically invalid generated Python.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
