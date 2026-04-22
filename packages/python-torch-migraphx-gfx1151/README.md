# python-torch-migraphx-gfx1151

- Upstream: <https://github.com/ROCm/torch_migraphx>
- Package version: `1.2`
- Source commit: `6b2cd2237e83b675ae671650d08343dfbb0be5f3`
- Local role: package the Torch-MIGraphX FX lane against the coherent
  `gfx1151` ROCm, PyTorch, TorchAO, and MIGraphX package family.

This package depends on the local `migraphx-gfx1151` split exposing the real
MIGraphX Python module. The import path also depends on PyTorch 2.11's PT2E
layout, where current docs route PT2E quantization through TorchAO rather than
`torch.ao.quantization.quantize_pt2e`.

## Local Patch Carry

- `0001-import-pt2e-quantization-from-torchao.patch` keeps Torch-MIGraphX
  compatible with the installed PyTorch 2.11 and TorchAO 0.17 package layout.
- `0002-keep-dynamo-registration-lazy.patch` keeps base `import torch_migraphx`
  and the FX lowering path importable. Eager Dynamo backend registration loads
  PyTorch AOTAutograd after the `_torch_migraphx` extension and currently
  segfaults on this Python 3.14 stack, so Dynamo remains an explicit follow-up
  lane rather than a package-import side effect.

## Validation

The current package shape was validated from a staged target with MIGraphX,
TorchAO PT2E, Torch-MIGraphX import, and a host-device FX lowering smoke. The
equivalent installed-system import checks are:

```bash
python -c 'import migraphx; print(migraphx.__file__)'
python -c 'import torchao.quantization.pt2e.quantize_pt2e; import torch_migraphx'
```

The equivalent installed-system FX smoke is:

```bash
python - <<'PY'
import torch
import torch_migraphx

class M(torch.nn.Module):
    def forward(self, x):
        return x + 1

mgx = torch_migraphx.fx.lower_to_mgx(
    M().eval(),
    [torch.randn(1, 4)],
    min_acc_module_size=1,
    suppress_accuracy_check=True,
)
print(type(mgx).__name__)
PY
```

The smoke produced a MIGraphX-backed `SplitModule` on a host run with GPU
device access.

The package artifact builds as
`python-torch-migraphx-gfx1151-1.2-1-x86_64.pkg.tar.zst`. The installed-system
gate is publish/install with the matching `python-torchao-rocm-gfx1151`
pkgrel, then rerun the import and FX smoke without temporary `PYTHONPATH`
overlays.
