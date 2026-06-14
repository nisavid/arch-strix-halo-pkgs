# python-amd-aiter-gfx1151

## Maintenance Snapshot

- Recipe package key: `aiter`
- Scaffold template: `python-project-aiter`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/aiter.git`
- Package version: `0.1.14`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `29`
- Recipe dependencies: `pytorch, vllm`
- Recorded reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Authoritative reference package: `none`
- Advisory reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Applied source patch files/actions: `6`

## Recipe notes

Rebuilt from upstream AITER stable release v0.1.14. Keep the packaged CK ABI
aligned with the CK headers used by AITER's JIT at runtime.

PREBUILD_KERNELS=0: skip 45-minute full kernel precompilation.
Kernels are JIT-compiled on first use instead.

Package-local source patches are applied before wheel build for gfx1151
RDNA 3.5 compatibility and installed-system JIT/runtime behavior.


## Scaffold notes

- There is no standalone Arch, CachyOS, or AUR aiter package. The closest packaging lane is the PyTorch ROCm pkgbase that vendors the same submodule, so that pkgbase is advisory only.
- The package follows upstream AITER release tags, including release candidates and previews when they are the latest GitHub release.
- The package exports SETUPTOOLS_SCM_PRETEND_VERSION so the wheel metadata stays stable while building from the pinned upstream release tag.
- The recipe rebuilds AITER from the pinned upstream AITER source lane while keeping CK and generated kernel expectations explicit in the package.
- Upstream AITER declares pandas as a real dependency and FlyDSL as an optional acceleration path. Keep pandas in the package metadata, and package FlyDSL separately rather than silently depending on an unpublished wheel.
- Keep the gfx1151 RDNA 3.5 header fixes as package-local source patches applied before wheel build, split between the `vec_convert.h` packed-op fallbacks and the `hip_reduce.h` wave32/DPP compatibility rewrite.
- Keep the installed-system JIT runtime patch unless upstream fixes both assumptions itself: `hipcc` on the ambient PATH, and package-relative import of JIT-built modules even after copying the writable JIT tree out of read-only site-packages.
- Keep the gfx1x AITER-side MoE compatibility patches that are genuinely local: unknown-gfx probing, missing 1-stage ASM metadata, and CK 2-stage splitk normalization/forwarding. The current validated Gemma 4 26B-A4B lane uses TRITON backend for Unquantized MoE, so any attempt to move that model back onto AITER fused-MoE should be treated as fresh validation work, not as a presumed default-lane dependency.

## Intentional Divergences

- There is no standalone AITER package in Arch-family packaging; this package is recipe-first and follows upstream AITER release tags, including release candidates and previews when published through GitHub releases.
- Carries explicit package-local source patches for gfx1151 RDNA 3.5 header compatibility, split between vec_convert packed-op fallbacks and hip_reduce wave32/DPP compatibility, rather than leaving those fixes as manual post-build mutations.
- Carries an installed-system JIT runtime patch so AITER can find `hipcc` and import JIT-built modules from the writable user cache on read-only site-packages installs.
- Carries the gfx1x AITER-side MoE compatibility patches that are safe to keep local: unknown-gfx probing, missing 1-stage ASM metadata handling, and CK 2-stage splitk normalization/forwarding for AITER fused-MoE experiments and other non-Gemma lanes. The current validated Gemma 4 default path still uses TRITON for unquantized MoE.

## Update Notes

- Track upstream AITER releases as the package source lane, including release candidates and previews when upstream publishes them through GitHub releases.
- On 2026-04-23, reviewed AITER main through 8432ff3b6e356bc0f8c664a686334e3be7e736ec. The latest reviewed delta adds Gemma RMSNorm quant-fusion support, A16W16 tuning, MI308 MLA PS-mode work, FlyDSL AOT fixes, Kimi K2 FP4 tuned fMoE config updates, and CI/release workflow changes. It does not resolve the local gfx1151 OPUS FP8 mfma_adaptor gap, replace the RDNA header or JIT runtime patches, or change the currently validated Gemma TRITON default lane, so record the reviewed candidate head without repinning the package source.
- On 2026-04-24, reviewed AITER main through ed2db5ef0f6444b735f018c0f4688058c1bfeb26. The latest reviewed delta adds a Gluon paged-attention decode sliding-window MTP fix plus CI-only changes. Keep it recorded as a reviewed candidate head for future speculative/MTP work, but do not repin this package until a host scenario needs that Gluon path or the range reduces current gfx1151 patch carry.
- On 2026-04-24, reviewed AITER main through 033d8b9dbc635d30aa63906245c045f24f8cf796. The latest reviewed delta adds Qwen3.5 GDN prefill kernels, batch-prefill runtime dispatch for KV caches larger than 4 GiB, a top_k_per_row_prefill fix for large batched token counts, non-quantizing ASM fMoE kernels, MI308 tuning, and a GPT-OSS tuned-config revert. Keep it recorded as a reviewed candidate head for future Qwen3.5/GDN or fused-MoE validation, but do not repin the package source until a tracked host scenario needs this range or it replaces current gfx1151 patch carry.
- On 2026-04-26, reviewed AITER main through dcb0639d870783c2bc0c530e465f301032e756dc. The latest reviewed delta only optimizes the mHC prefill kernel for small M and updates its op test; it does not touch the gfx1151 RDNA header patches, JIT runtime patch, gfx1x MoE carries, or the Qwen3.6 FP8 OPUS mfma_adaptor blocker. Record the reviewed candidate head without repinning the package source.
- On 2026-04-28, reviewed AITER main through 6a7df2004f5f896471cf9e6ab588b6aec0357dc7. The range adds Triton A16W4 MoE kernels, MHA backward stride fixes, an mHC device fix, gfx950 A8W8 correctness updates, and CI workflow changes. It does not resolve the gfx1151 OPUS FP8 mfma_adaptor blocker or replace the local RDNA header/JIT runtime patch carry, so record the reviewed candidate head without repinning.
- On 2026-05-01, adopted AITER main at a0f25393903f5412b0fb997d5b825a0aeb257466. The d679e288..a0f2539 range includes HIP KL cache refactoring, JIT/setup handling, cache kernels, mHC small-M work, fused all-reduce/RMSNorm memory ordering, GemmTuner SplitK guards, MXFP4 fixes, preshuffled cache/indexer fixes, and tuning/test coverage.
- On 2026-05-10, adopted AITER stable tag v0.1.13 with the local gfx1151 RDNA header, JIT runtime, and gfx1x MoE compatibility carry preserved.
- On 2026-05-14, adopted AITER main d50194cae28f2e22f4dfff19a86577fe2fcbca27 as a post-0.1.13 snapshot because the range carries kernel, JIT, mHC, topk, and MXFP4 changes that are relevant to the local vLLM/AITER validation surface.
- On 2026-05-16, adopted upstream release tag v0.1.14-rc0 because prerelease GitHub releases are now intentional source-lane updates for this package.
- On 2026-05-25, adopted upstream release tag v0.1.14 because it supersedes the rc0 package lane. The stable release is cut from release/v0.1.14 at bd0534e96 and adds DSv4 fusions, MiniMax fused qknorm/allreduce, FlyDSL and Triton updates, and bug fixes while preserving the local gfx1151 patch carry.
- On 2026-05-31, reviewed upstream release tag v0.1.15-rc0 and rechecked the dependency closure. The RC remains the latest AITER release, adds DSv4-Pro/V4-Flash kernels, MoE and FlyDSL updates, Triton accumulator/split-k changes, MHC fused rmsnorm work, and OPUS updates, but it hard-pins flydsl==0.1.9.dev599, runs FlyDSL AOT during build, and requires triton>=3.6.0 for Gluon kernels. Public PyPI exposes FlyDSL 0.1.9.dev599 only as CPython manylinux wheels with no sdist/source artifact, and the local python-triton-gfx1151 source lane still tracks ROCm/triton main_perf at 0ec280cf rather than a Triton 3.6+ source package. Keep the package source on 0.1.14 until FlyDSL has a source-packageable local closure and a Triton 3.6+ ROCm source lane is dispositioned, or the final release removes those blockers.
- On 2026-06-14, recorded upstream release tag v0.1.15.post1 as the active tracked release target after it superseded the 0.1.15-rc0 blocker. Keep the package source on 0.1.14 until the post1 release metadata is re-reviewed against the FlyDSL source-packageability and Triton 3.6+ ROCm source-lane concerns, or a local dependency closure exists.
- Treat FlyDSL as a separate tracked package story; do not silently fold an unpublished wheel into this package.
- Keep the installed-system JIT runtime patch until upstream AITER stops assuming `hipcc` is on the ambient PATH and correctly imports modules copied to the writable user JIT cache from read-only site-packages installs.
- Keep the package's explicit ROCm toolchain exports in `build()` until upstream AITER stops probing `hipconfig` and `hipcc` through ambient shell state. The concrete build failure was `Could not find hipconfig in PATH or ROCM_HOME(/usr)`.
- Keep the split RDNA header carries narrow: `0001-gfx1151-rdna35-header-compat.patch` now covers only the `vec_convert.h` gfx11 packed-op fallbacks, while `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` carries the broader `hip_reduce.h` wave32/DPP rewrite. If that area is revisited, re-verify `hip_reduce.h` on its own instead of recombining unrelated header edits.
- Keep `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` on AITER's shipped `aiter_hip_common.h` include. A 2026-04-19 Qwen3.6 FP8 MoE probe selected AITER but failed JIT-building `module_quant` because an earlier patch variant rewrote `hip_reduce.h` to include nonexistent `hip_compat.h`.
- Treat the current Qwen3.6 FP8 MoE forced-AITER failure as an AITER opus/gfx1151 FP8-kernel feature gap, not a narrow include bug. A built-payload rerun with AITER pkgrel -8 and vLLM pkgrel -27 clears the `hip_compat.h` issue, then fails compiling `aiter.jit.module_quant` with `opus.hpp:3001:24: error: unknown type name 'mfma_adaptor'`; AITER defines `mfma_adaptor` only for `__GFX9__` device builds, while its alternate gfx1250 WMMA path uses FP8 builtins that hipcc rejects for gfx1151.
- Keep the unknown-gfx 2-stage fallback, missing-1-stage-metadata tuner skip, and CK 2-stage splitk normalization/forwarding fix until upstream AITER handles those gfx1x cases directly. Do not reintroduce an unquantized `torch_moe` fallback here: the concrete reference-host failure was `google/gemma-4-26B-A4B-it` generating corrupted text after such a fallback ran on AITER-shuffled weights.
- On 2026-05-26, bump pkgrel to 2 for delivery of the AITER rebuild against python-pytorch-opt-rocm-gfx1151 2.12.0-2 from ROCm/pytorch release/2.12 commit 26872debb4452ea6dc898288618a15595e2317d9.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
