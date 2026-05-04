# python-torch-migraphx-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `python-project-torch-migraphx`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/torch_migraphx`
- Package version: `1.2`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
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

The promoted runtime lanes are FX lowering, PT2E quantizer imports, a tiny
Dynamo named-backend smoke, and bounded ResNet-style Dynamo/PT2E scenario
smokes. The package should import MIGraphX, TorchAO PT2E, Torch-MIGraphX, and
the Torch-MIGraphX PT2E quantizer from package-owned paths, lower a tiny
`x + 1` module to a MIGraphX-backed `SplitModule` on the `gfx1151` GPU with
matching PyTorch output, import `torch_migraphx.dynamo`, import `sqlite3` after
Torch-MIGraphX, and compile bounded ResNet-style CNNs through
`torch.compile(..., backend="migraphx")`.

Dynamo registration stays lazy on base import, and the package preloads
PyTorch AOTAutograd before MIGraphX native modules because importing
AOTAutograd or `sqlite3` after the MIGraphX Python extension can segfault on
the local Python 3.14 and PyTorch 2.11 stack.


## Scaffold notes

- Builds from upstream master at 6b2cd2237e83b675ae671650d08343dfbb0be5f3 because PyPI and the only upstream tag remain at 1.1 while current master reports version 1.2.
- Uses the ROCm compiler lane explicitly and strips the unsupported -famd-opt flag from wheel C/C++ flags.
- Depends on the local MIGraphX split package because the Python binding is installed under /opt/rocm/lib with migraphx.pth.
- Relaxes upstream's numpy metadata cap for the repo's numpy 2.x lane.
- Patches Torch-MIGraphX PT2E quantizer imports to use TorchAO's current pt2e.quantizer modules.
- Preloads PyTorch AOTAutograd before MIGraphX native modules so torch.compile(..., backend="migraphx") can use the named backend without the import-order segfault.

## Intentional Divergences

- There is no current Arch-family Torch-MIGraphX package baseline, so this package is closure-first and tracks the audited upstream master commit that reports package version 1.2.
- Carries a PT2E compatibility patch because PyTorch 2.11 documents PT2E quantization through TorchAO while current Torch-MIGraphX still imports removed torch.ao quantize_pt2e and quantizer modules.
- Keeps Dynamo registration lazy on base import and preloads PyTorch AOTAutograd before MIGraphX native modules so named-backend registration can import safely on the local Python 3.14 and PyTorch 2.11 stack.
- Relaxes upstream's numpy <2.0 wheel metadata because the local runtime and FX smoke use the repo's python-numpy-gfx1151 2.x lane.

## Update Notes

- Track the upstream master commit until ROCm publishes a post-1.1 tag containing the version 1.2 Python package metadata.
- Keep CC and CXX bound to /opt/rocm/lib/llvm/bin/amdclang and amdclang++ during builds; the generic c++ path failed on inherited Strix tuning flags.
- Keep the installed _torch_migraphx extension RPATH pointed at the sibling torch/lib directory so libc10, libtorch_cpu, and libtorch_python resolve without LD_LIBRARY_PATH.
- Keep the numpy metadata patch while the local package depends on the repo's numpy 2.x lane.
- Re-run host-device FX lowering after every MIGraphX, PyTorch, TorchAO, or Torch-MIGraphX rebuild.
- Re-run the PT2E quantizer import and tiny torch.compile backend smokes after every PyTorch, TorchAO, or Torch-MIGraphX rebuild because those lanes depend on moved TorchAO APIs and PyTorch AOTAutograd import ordering.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
