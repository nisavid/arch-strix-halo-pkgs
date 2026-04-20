# python-pytorch-opt-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `pytorch`
- Scaffold template: `python-project-pytorch-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/pytorch.git`
- Package version: `2.11.0`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `9, 10, 11`
- Recipe dependencies: `therock, cpython`
- Recorded reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm, cachyos-extra-znver4/python-pytorch-opt-rocm`
- Authoritative reference package: `extra/python-pytorch-opt-rocm`
- Advisory reference packages: `extra/python-pytorch-rocm, cachyos-extra-znver4/python-pytorch-opt-rocm`
- Applied source patch files/actions: `9`

## Recipe notes

ROCm fork carries AMD-specific fixes (hipify, Tensile, rocm_smi
linkage) not yet upstreamed. The upstream pytorch/pytorch works with
USE_ROCM=1 but AMD's CI tests against this fork.

USE_ROCM_CK_GEMM=ON enables Composable Kernel GEMM for ROCm.

## Scaffold notes

- Authoritative base: Arch split package python-pytorch-opt-rocm 2.11.0-3, with python-pytorch-rocm kept as an advisory sibling because the same pkgbase carries both variants.
- The recipe intentionally tracks the ROCm/pytorch fork rather than upstream pytorch/pytorch because AMD validates that branch and carries ROCm-specific integration fixes not yet upstreamed.
- Keep nearby Cachy packaging as advisory input for compiler defaults and dependency polish, but use the Arch split-package structure as the distro-integration baseline.
- The first real build must preserve the recipe's ROCm-specific fixes: HIPGraph.hip stub rewrite, NumPy 2 target C-API define, clang ABI flag removal, gfx1151 CK enablement, and post-install patchelf fixes for torch/lib and libtorch_hip.so.
- Use OpenBLAS explicitly for this lane. Letting the build auto-detect host oneMKL produced a broken wheel with /opt/intel/oneapi runpaths and NumPy import failures.
- On Arch Python 3.14, the CMake install target currently mirrors /usr/lib and /usr/include into the source tree and then fails on a root-owned _sysconfigdata pyc. The maintained workaround is to build first, accept that known install failure, restage the built torch/lib and torch/bin artifacts, and assemble the wheel with SKIP_BUILD_DEPS=1.

## Intentional Divergences

- Uses the Arch split-package structure as the integration baseline but deliberately tracks ROCm/pytorch release/2.11 rather than upstream pytorch/pytorch.
- Carries recipe-specific ROCm fixes such as the HIPGraph stub rewrite, gfx1151 CK enablement, and post-install patchelf/linker cleanup.
- Pins PyTorch's BLAS/LAPACK provider to OpenBLAS and uses a two-stage wheel assembly flow on Arch Python 3.14 to avoid host oneMKL contamination and the broken install target that mirrors /usr/lib into the source tree.

## Update Notes

- When updating, inspect the current Arch python-pytorch pkgbase first, then re-evaluate every carried recipe/source patch against the chosen ROCm fork.
- Keep the package version aligned with the built wheel version; do not repeat the earlier mismatch where the package claimed 2.11.0 but the built wheel came from develop.
- Keep openblas explicit in both depends and makedepends so the build does not drift back to generic host BLAS auto-detection.
- Preserve the current Arch Python 3.14 wheel flow unless upstream changes materially: build CMake artifacts first, tolerate the known _sysconfigdata__linux_x86_64-linux-gnu.cpython-314.pyc install failure, restage the built torch/lib and torch/bin payloads, then run SKIP_BUILD_DEPS=1 python setup.py bdist_wheel.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
