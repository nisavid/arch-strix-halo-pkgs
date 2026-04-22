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
):
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__version__ = "9.9.9"

    backend = types.ModuleType("flash_attn.flash_attn_interface")
    backend.USE_TRITON_ROCM = use_triton_rocm
    backend.__file__ = "/fake/flash_attn/flash_attn_interface.py"

    def flash_attn_qkvpacked_func(qkv, **kwargs):
        if call_log is not None:
            call_log.append(f"qkvpacked_func:{kwargs}")
        batch_size, seqlen, _, heads, head_dim = qkv.shape
        return types.SimpleNamespace(shape=(batch_size, seqlen, heads, head_dim))

    flash_attn.flash_attn_qkvpacked_func = flash_attn_qkvpacked_func
    flash_attn.flash_attn_interface = backend

    monkeypatch.setitem(sys.modules, "flash_attn", flash_attn)
    monkeypatch.setitem(sys.modules, "flash_attn.flash_attn_interface", backend)
    return flash_attn, backend


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
    flash_attn, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            raise ImportError("optional candidate missing")
        if name == "flash_attn.flash_attn_interface":
            return backend
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "mode backend-import" in output
    assert "flash_attn_version 9.9.9" in output
    assert "use_triton_rocm True" in output
    assert "backend_module flash_attn.flash_attn_interface" in output
    assert "backend_file /fake/flash_attn/flash_attn_interface.py" in output
    assert "flash_attn_import_ok" in output
    assert "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in attempted


def test_backend_import_rejects_non_triton_rocm_backend(monkeypatch):
    flash_attn, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=False)
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            raise ImportError("optional candidate missing")
        if name == "flash_attn.flash_attn_interface":
            return backend
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    assert flash_attn_smoke.main(["--mode", "backend-import"]) != 0
    assert "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in attempted


def test_backend_import_reports_no_valid_backend(monkeypatch, capsys):
    flash_attn, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=False)
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)

    def fake_import_module(name: str):
        if name == "flash_attn":
            return flash_attn
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            raise ImportError("optional candidate missing")
        if name == "flash_attn.flash_attn_interface":
            return backend
        if name == "flash_attn.ops.triton.flash_attn_interface":
            raise ModuleNotFoundError(name)
        if name == "flash_attn.ops.triton.backend":
            raise ModuleNotFoundError(name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc != 0
    output = capsys.readouterr()
    assert "flash_attn_backend_error FLASH_ATTN_BACKEND_NOT_FOUND" in output.out


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


def test_backend_import_skips_broken_optional_candidate_and_uses_aiter_backend(
    monkeypatch, capsys
):
    flash_attn, _ = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    aiter_backend = types.ModuleType(
        "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2"
    )
    aiter_backend.USE_TRITON_ROCM = True
    aiter_backend.__file__ = "/fake/aiter/interface_v2.py"

    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        if name == "flash_attn.flash_attn_interface":
            raise ImportError("broken optional candidate")
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            return aiter_backend
        raise ModuleNotFoundError(name)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "backend_module aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in output
    assert "backend_file /fake/aiter/interface_v2.py" in output
    assert "flash_attn_import_ok" in output
    assert "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2" in attempted


def test_backend_import_skips_runtime_error_candidate_and_uses_later_backend(
    monkeypatch, capsys
):
    flash_attn, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    attempted: list[str] = []

    def fake_import_module(name: str):
        attempted.append(name)
        if name == "flash_attn":
            return flash_attn
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            raise RuntimeError("broken optional candidate")
        if name == "flash_attn.flash_attn_interface":
            return backend
        if name == "flash_attn.ops.triton.flash_attn_interface":
            return backend
        raise ModuleNotFoundError(name)

    flash_attn_smoke = _load_smoke_module(monkeypatch)
    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "backend_module flash_attn.flash_attn_interface" in output
    assert "backend_file /fake/flash_attn/flash_attn_interface.py" in output
    assert "flash_attn_import_ok" in output
    assert attempted.index("aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2") < attempted.index(
        "flash_attn.flash_attn_interface"
    )


def test_backend_import_reports_skipped_probe_diagnostics_to_stderr(monkeypatch, capsys):
    flash_attn, backend = _install_fake_flash_attn(monkeypatch, use_triton_rocm=True)
    _install_fake_torch(monkeypatch)

    flash_attn_smoke = _load_smoke_module(monkeypatch)

    def fake_import_module(name: str):
        if name == "flash_attn":
            return flash_attn
        if name == "aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2":
            raise RuntimeError("broken optional candidate")
        if name == "flash_attn.flash_attn_interface":
            return backend
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(flash_attn_smoke.importlib, "import_module", fake_import_module)

    rc = flash_attn_smoke.main(["--mode", "backend-import"])

    assert rc == 0
    output = capsys.readouterr()
    assert (
        "backend_probe_skipped aiter.ops.triton._triton_kernels.flash_attn_triton_amd.interface_v2 "
        "RuntimeError: broken optional candidate"
        in output.err
    )


def test_qkvpacked_tiny_propagates_runtime_errors_from_smoke_logic(monkeypatch):
    flash_attn = types.ModuleType("flash_attn")
    flash_attn.__version__ = "9.9.9"
    flash_attn.flash_attn_interface = types.SimpleNamespace(
        USE_TRITON_ROCM=True,
        __file__="/fake/flash_attn/flash_attn_interface.py",
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
