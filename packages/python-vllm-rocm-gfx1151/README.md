# python-vllm-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `vllm`
- Scaffold template: `python-project-vllm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/vllm-project/vllm.git`
- Derived pkgver seed: `0.19.0.r8.d20260317.gad42886`
- Recipe steps: `19, 20, 21, 22, 23, 24`
- Recipe dependencies: `pytorch, triton, aotriton`
- Recorded reference packages: `aur/python-vllm`
- Authoritative reference package: `aur/python-vllm`
- Advisory reference packages: `none`
- Applied source patch files/actions: `30`

## Recipe notes

Upstream vLLM (not ROCm fork). AITER integration comes from
PyTorch's third_party/aiter/ which has full gfx1151 support.

Build attempts AITER first (VLLM_ROCM_USE_AITER=1). If AITER
compilation fails, falls back to Triton-only build. Result is
recorded in .aiter-status file ("enabled" or "disabled").

## Scaffold notes

- There does not appear to be a current dedicated python-vllm-rocm AUR package; the closest package baseline is the generic AUR python-vllm package, with ROCm-specific integration coming from this recipe.
- Use the latest stable upstream release tarball (v0.19.0) instead of a floating full Git clone. Upstream currently exposes a 0.19.1 release candidate but not a final 0.19.1 release, so the stable tag is the safer packaging baseline.
- This scaffold carries the minimal Python-3.14 source patch needed to build from the stable tarball: relax the Python upper bound and extend the hard-coded CMake supported-version list through 3.14.
- Carries a package-local CLI import patch so vllm --version remains a metadata-only path instead of importing optional OpenAI and Triton runtime modules at startup.
- Carries a ROCm-specific Triton compatibility patch so the vendored triton_kernels tree is treated as unavailable when the installed Triton runtime lacks CUDA-only APIs such as triton.language.target_info or triton.constexpr_function.
- Carries a ROCm-platform fallback patch so Strix Halo can fall back from AMDSMI ASIC-info lookup to torch.cuda without tripping the import-time `warning_once` circular import path.
- Carries an optional-SageMaker patch so `vllm --help` and the base OpenAI server routes stay usable when `model_hosting_container_standards` is not installed.
- The currently installed external python-torchao-rocm package is not import-clean at the native extension layer on this host, but vLLM's current TorchAO-facing Python APIs still work. Treat that as an external package defect to revisit only if this repo needs functioning TorchAO custom ops rather than the existing Python-level quantization helpers.
- makepkg -e reuses src/, so build() intentionally reapplies the carried source patches before wheel generation instead of assuming prepare() already ran in the current tree.
- Upstream openai-harmony is a small Rust/PyO3 helper library with published manylinux wheels, not a ROCm-specific component. If Arch still lacks an official package, the right local story is a closure package derived from aur/python-openai-harmony. If this repo ingests it locally, it should still inherit the normal Strix build lane for applicable native code: Zen 5 / znver5 CPU tuning, -O3 or equivalent, LTO when compatible, and PGO when the build system exposes a maintainable path.
- Do not treat a successful build as sufficient for system-Python cutover; the gate is a real vLLM smoke test after the TheRock ROCm split packages are installed coherently.
- Keep the gfx1151 ROCm/AITER recipe patches in the source package, but evaluate Python-3.14 compatibility separately from ROCm runtime/linker issues.
- The earlier numba-pin idea is not currently part of the actual built package story; treat any numba change as a separate follow-up until it is backed by a real source patch.

## Intentional Divergences

- This package is ROCm-specific even though the closest Arch-family baseline is the generic aur/python-vllm package.
- Carries a deliberate Python-3.14 compatibility delta and recipe-specific ROCm/AITER integration that are not part of the generic baseline.

## Update Notes

- Check upstream vllm release notes and pyproject metadata first, then reconcile the Python upper-bound and hard-coded supported-version list with the current state of Python 3.14 support.
- If numba remains part of the Python 3.14 story, capture it as a real source patch or package dependency decision rather than a no-op scripted edit.
- Keep vllm --version as a metadata-only smoke path. If upstream CLI imports optional OpenAI or Triton modules eagerly again, prefer restoring a lazy import boundary over adding unrelated hard runtime dependencies just for version output.
- Treat openai-harmony as a normal runtime-closure package, not an optdepend, if this repo wants GPT-OSS/Harmony paths to work. The current AUR baseline is a good starting point, but it omits the upstream python-pydantic runtime dependency and should not be copied blindly. The reason to package it locally is closure and metadata correctness, not a ROCm-specific patch lane.
- Keep the vendored triton_kernels path gated on the installed Triton runtime rather than forcing python-triton-gfx1151 to emulate CUDA-only APIs such as triton.language.target_info. On this ROCm lane, treat unavailable vendored Triton kernels as a clean fallback, not as a hard runtime error.
- Keep SageMaker integration optional unless this repo intentionally packages `model_hosting_container_standards`; missing SageMaker helpers should disable only SageMaker-specific routes, not the base CLI or local server startup paths.
- Keep the ROCm GCN-arch fallback import-safe on Strix Halo. AMDSMI ASIC-info probes can fail even when the device is visible; that must degrade to `torch.cuda` probing rather than crashing during module import.
- Treat the current external python-torchao-rocm _C-extension failure as a host-package defect, not a blocker for this vLLM lane. import vllm stays clean, and the TorchAO Python-level APIs vLLM touches still work on the reference host; only revisit this if TorchAO custom ops or torchao-backed serving paths actually require the native extension.
- Treat runtime validation against the live ROCm stack as mandatory; a successful wheel build is not enough.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
