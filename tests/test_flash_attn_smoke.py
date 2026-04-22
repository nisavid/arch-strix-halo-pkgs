from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _install_fake_flash_attn(
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_triton_rocm: bool,
    call_log: list[str] | None = None,
    backend_module_name: str = "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2",
    backend_file: str = "/fake/aiter/interface_v2.py",
    backend_use_triton_rocm: bool = True,
):
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__version__ = "9.9.9"

    backend = types.ModuleType(backend_module_name)
    backend.USE_TRITON_ROCM = backend_use_triton_rocm
    backend.__file__ = backend_file

    wrapper = types.ModuleType("flash_attn.flash_attn_interface")
    wrapper.USE_TRITON_ROCM = use_triton_rocm
    wrapper.__file__ = "/fake/flash_attn/flash_attn_interface.py"
    wrapper.flash_attn_gpu = backend

    def flash_attn_qkvpacked_func(qkv, **kwargs):
        if call_log is not None:
            call_log.append(f"qkvpacked_func:{kwargs}")
        batch_size, seqlen, _, heads, head_dim = qkv.shape
        return types.SimpleNamespace(shape=(batch_size, seqlen, heads, head_dim))

    flash_attn.flash_attn_qkvpacked_func = flash_attn_qkvpacked_func
    flash_attn.flash_attn_interface = wrapper
    flash_attn.flash_attn_gpu = backend

    monkeypatch.setitem(sys.modules, "flash_attn", flash_attn)
    monkeypatch.setitem(sys.modules, "flash_attn.flash_attn_interface", wrapper)
    monkeypatch.setitem(sys.modules, backend_module_name, backend)
    return flash_attn, wrapper, backend


def _install_fake_torch(monkeypatch: pytest.MonkeyPatch, *, call_log: list[str] | None = None):
    torch = types.ModuleType("torch")

    class FakeTensor:
        def __init__(self, shape, *, dtype=None):
            self.shape = tuple(shape)
            self.dtype = dtype

        def to(self, device):
            self.device = device
            return self

    class FakeFiniteMask:
        def all(self):
            return True

    class FakeGenerator:
        def __init__(self, device=None):
            self.device = device
            self.seed = None

        def manual_seed(self, seed):
            self.seed = seed
            return self

    class FakeCuda:
        def __init__(self):
            self.available = True

        def is_available(self):
            return self.available

        def synchronize(self):
            if call_log is not None:
                call_log.append("cuda.synchronize")
            return None

    torch.float16 = object()
    torch.cuda = FakeCuda()
    torch.device = lambda name: name
    torch.Generator = FakeGenerator
    torch.manual_seed = lambda seed: None
    torch.randn = lambda *shape, **kwargs: FakeTensor(shape, dtype=kwargs.get("dtype"))
    torch.isfinite = lambda tensor: FakeFiniteMask()
    torch.Tensor = FakeTensor

    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def _load_smoke_module(monkeypatch: pytest.MonkeyPatch):
    sys.modules.pop("flash_attn_smoke", None)
    return importlib.import_module("flash_attn_smoke")


def test_backend_import_reports_triton_rocm_backend(monkeypatch, capsys):
    flash_attn, wrapper, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "mode backend-import" in output
    assert "flash_attn_version 9.9.9" in output
    assert "use_triton_rocm True" in output
    assert "backend_module aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in output
    assert "backend_file /fake/aiter/interface_v2.py" in output
    assert "flash_attn_import_ok" in output
    assert attempted == ["flash_attn"]
    assert wrapper.flash_attn_gpu is backend


def test_backend_import_fails_when_pinned_aiter_backend_raises_even_if_later_backend_is_ok(
    monkeypatch, capsys
):
    flash_attn, wrapper, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    wrapper.flash_attn_gpu = types.ModuleType("flash_attn.ops.triton.backend")
    wrapper.flash_attn_gpu.__file__ = "/fake/flash_attn/ops/triton/backend.py"

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc != 0
    output = capsys.readouterr()
    assert "flash_attn_backend_error" in output.out
    assert "flash_attn.flash_attn_interface.flash_attn_gpu flash_attn.ops.triton.backend" in output.out
    assert "!= aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in output.out
    assert attempted == ["flash_attn"]


def test_backend_import_rejects_non_triton_rocm_backend(monkeypatch, capsys):
    flash_attn, _, _ = _install_fake_flash_attn(
        monkeypatch,
        use_triton_rocm=False,
    )
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc != 0
    output = capsys.readouterr().out
    assert "flash_attn_backend_error" in output
    assert "flash_attn.flash_attn_interface USE_TRITON_ROCM != True" in output
    assert attempted == ["flash_attn"]


def test_qkvpacked_tiny_reports_shape_and_finiteness(monkeypatch, capsys):
    call_log: list[str] = []
    _install_fake_flash_attn(monkeypatch, use_triton_rocm=True, call_log=call_log)
    _install_fake_torch(monkeypatch, call_log=call_log)

    flash_attn_smoke = _load_smoke_module(monkeypatch)

    rc = flash_attn_smoke.main(["--mode", "qkvpacked-tiny"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "mode qkvpacked-tiny" in output
    assert "shape (1, 16, 2, 32)" in output
    assert "finite True" in output
    assert "flash_attn_qkvpacked_ok" in output
    assert call_log == ["qkvpacked_func:{'dropout_p': 0.0, 'causal': False}", "cuda.synchronize"]


def test_qkvpacked_tiny_propagates_runtime_errors_from_smoke_logic(monkeypatch):
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__version__ = "9.9.9"
    flash_attn.flash_attn_interface = types.SimpleNamespace(
        USE_TRITON_ROCM=True,
        __file__="/fake/flash_attn/flash_attn_interface.py",
        flash_attn_gpu=types.SimpleNamespace(
            __name__="aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2",
            __file__="/fake/aiter/interface_v2.py",
        ),
    )

    def raising_flash_attn_qkvpacked_func(qkv, **kwargs):
        raise RuntimeError("smoke runtime regression")

    flash_attn.flash_attn_qkvpacked_func = raising_flash_attn_qkvpacked_func
    monkeypatch.setitem(sys.modules, "flash_attn", flash_attn)
    monkeypatch.setitem(
        sys.modules,
        "flash_attn.flash_attn_interface",
        flash_attn.flash_attn_interface,
    )
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)

    with pytest.raises(RuntimeError, match="smoke runtime regression"):
        flash_attn_smoke.main(["--mode", "qkvpacked-tiny"])
