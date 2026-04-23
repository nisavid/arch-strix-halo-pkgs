from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import importlib
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


class FakeTensor:
    def __init__(self, shape: tuple[int, ...]):
        self.shape = shape


class FakeFinite:
    def all(self):
        return self

    def item(self) -> bool:
        return True


def _load_smoke_module(monkeypatch):
    sys.modules.pop("vllm_flash_attn_smoke", None)
    return importlib.import_module("vllm_flash_attn_smoke")


def _install_fake_stack(monkeypatch, *, backend_name: str = "FLASH_ATTN"):
    torch = ModuleType("torch")
    torch.float16 = object()

    def randn(shape, *, dtype, device):
        assert dtype is torch.float16
        assert device == "cuda"
        return FakeTensor(tuple(shape))

    torch.randn = randn
    torch.manual_seed = lambda seed: None
    torch.cuda = SimpleNamespace(
        is_available=lambda: True,
        synchronize=lambda: None,
    )
    torch.isfinite = lambda tensor: FakeFinite()
    monkeypatch.setitem(sys.modules, "torch", torch)

    class RocmPlatform:
        @staticmethod
        def get_vit_attn_backend(head_dim, dtype):
            assert head_dim == 32
            assert dtype is torch.float16
            return SimpleNamespace(name=backend_name)

    rocm = ModuleType("vllm.platforms.rocm")
    rocm.RocmPlatform = RocmPlatform
    monkeypatch.setitem(sys.modules, "vllm.platforms.rocm", rocm)

    wrappers = ModuleType("vllm.v1.attention.ops.vit_attn_wrappers")

    def vit_flash_attn_wrapper(q, k, v, batch_size, is_rocm_aiter, fa_version):
        assert q.shape == (1, 16, 2, 32)
        assert k.shape == q.shape
        assert v.shape == q.shape
        assert batch_size == 1
        assert is_rocm_aiter is False
        assert fa_version is None
        return FakeTensor(q.shape)

    wrappers.vit_flash_attn_wrapper = vit_flash_attn_wrapper
    monkeypatch.setitem(
        sys.modules,
        "vllm.v1.attention.ops.vit_attn_wrappers",
        wrappers,
    )

    backend = ModuleType(
        "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2"
    )
    wrapper = SimpleNamespace(USE_TRITON_ROCM=True, flash_attn_gpu=backend)
    flash_attn = ModuleType("flash_attn")
    flash_attn.flash_attn_interface = wrapper
    monkeypatch.setitem(sys.modules, "flash_attn", flash_attn)


def test_vllm_flash_attn_smoke_exposes_help_without_importing_vllm():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/vllm_flash_attn_smoke.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run bounded vLLM consumer smokes" in result.stdout
    assert "vit-wrapper" in result.stdout


def test_vllm_flash_attn_vit_wrapper_smoke_accepts_flash_attn_backend(
    monkeypatch,
    capsys,
):
    _install_fake_stack(monkeypatch)
    smoke = _load_smoke_module(monkeypatch)

    rc = smoke.main(["--mode", "vit-wrapper"])

    output = capsys.readouterr().out
    assert rc == 0
    assert "mode vit-wrapper" in output
    assert "vit_backend FLASH_ATTN" in output
    assert "vllm_flash_attn_vit_ok" in output


def test_vllm_flash_attn_vit_wrapper_rejects_non_flash_attn_selection(
    monkeypatch,
    capsys,
):
    _install_fake_stack(monkeypatch, backend_name="TORCH_SDPA")
    smoke = _load_smoke_module(monkeypatch)

    rc = smoke.main(["--mode", "vit-wrapper"])

    output = capsys.readouterr().out
    assert rc == 1
    assert "vit_backend TORCH_SDPA" in output
    assert "vllm_flash_attn_vit_ok" not in output
