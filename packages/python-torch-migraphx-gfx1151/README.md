# python-torch-migraphx-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `python-project-torch-migraphx`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `1.2`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `4`

## Recipe notes

Builds Torch-MIGraphX from audited upstream `master` at
`6b2cd2237e83b675ae671650d08343dfbb0be5f3` because PyPI and the only upstream
tag remain at `1.1` while current upstream reports package version `1.2`.

The package is bound to the coherent local ROCm stack: `migraphx-gfx1151`
provides the Python `migraphx` extension under `/opt/rocm/lib`, PyTorch and
TorchAO come from the local `gfx1151` package family, and the wheel build uses
the ROCm clang lane explicitly.

The promoted runtime lane is FX lowering. A staged target imported MIGraphX,
TorchAO PT2E, and Torch-MIGraphX, then a host-device smoke lowered a tiny
`x + 1` module to a MIGraphX-backed `SplitModule`. Dynamo backend registration
stays lazy because importing PyTorch AOTAutograd after `_torch_migraphx`
currently segfaults on the local Python 3.14 and PyTorch 2.11 stack.

The installed-system gate is publish/install with the matching TorchAO pkgrel,
then rerun the import and FX smoke without temporary `PYTHONPATH` overlays.


## Scaffold notes

- Builds from upstream master at 6b2cd2237e83b675ae671650d08343dfbb0be5f3 because PyPI and the only upstream tag remain at 1.1 while current master reports version 1.2.
- Uses the ROCm compiler lane explicitly and strips the unsupported -famd-opt flag from wheel C/C++ flags.
- Depends on the local MIGraphX split package because the Python binding is installed under /opt/rocm/lib with migraphx.pth.
- Relaxes upstream's numpy metadata cap for the repo's numpy 2.x lane.
- The package is promoted on an FX smoke, not Dynamo, until the Dynamo backend import no longer segfaults after _torch_migraphx loads.

## Intentional Divergences

- There is no current Arch-family Torch-MIGraphX package baseline, so this package is closure-first and tracks the audited upstream master commit that reports package version 1.2.
- Carries a PT2E compatibility patch because PyTorch 2.11 documents PT2E quantization through TorchAO while current Torch-MIGraphX still imports the removed torch.ao.quantization.quantize_pt2e module.
- Keeps Dynamo registration lazy because importing the Dynamo backend after the native _torch_migraphx extension currently segfaults on the local Python 3.14 and PyTorch 2.11 stack; FX lowering is the promoted smoke lane.
- Relaxes upstream's numpy <2.0 wheel metadata because the local runtime and FX smoke use the repo's python-numpy-gfx1151 2.x lane.

## Update Notes

- Track the upstream master commit until ROCm publishes a post-1.1 tag containing the version 1.2 Python package metadata.
- Keep CC and CXX bound to /opt/rocm/lib/llvm/bin/amdclang and amdclang++ during builds; the generic c++ path failed on inherited Strix tuning flags.
- Keep the installed _torch_migraphx extension RPATH pointed at the sibling torch/lib directory so libc10, libtorch_cpu, and libtorch_python resolve without LD_LIBRARY_PATH.
- Keep the numpy metadata patch while the local package depends on the repo's numpy 2.x lane.
- Re-run host-device FX lowering after every MIGraphX, PyTorch, TorchAO, or Torch-MIGraphX rebuild.
- Do not promote Dynamo or torch.compile backend coverage until explicit host validation proves import and a tiny compile no longer segfault.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
