import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_LIB = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib"
)


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug_once(self, msg: str, *args, **kwargs) -> None:
        return None

    def info_once(self, msg: str, *args, **kwargs) -> None:
        return None

    def warning_once(self, msg: str, *args, **kwargs) -> None:
        self.warnings.append(msg % args if args else msg)


def _resolve_import_utils() -> Path | None:
    matches = sorted(PKG_LIB.glob("python*/site-packages/vllm/utils/import_utils.py"))
    return matches[-1] if matches else None


def _load_import_utils(monkeypatch, import_utils_path: Path):
    logger = RecordingLogger()
    vllm_pkg = ModuleType("vllm")
    vllm_pkg.__path__ = []  # type: ignore[attr-defined]
    vllm_logger = ModuleType("vllm.logger")
    vllm_logger.init_logger = lambda _name: logger

    monkeypatch.setitem(sys.modules, "vllm", vllm_pkg)
    monkeypatch.setitem(sys.modules, "vllm.logger", vllm_logger)

    spec = importlib.util.spec_from_file_location(
        "vllm_import_utils_under_test", import_utils_path
    )
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, logger


def test_vendored_triton_kernels_are_disabled_when_target_info_is_missing(monkeypatch):
    import_utils_path = _resolve_import_utils()
    if import_utils_path is None:
        pytest.skip("built vLLM package image is not present")

    import_utils, logger = _load_import_utils(monkeypatch, import_utils_path)

    monkeypatch.setattr(
        import_utils,
        "_has_module",
        lambda name: name == "vllm.third_party.triton_kernels",
    )

    attempted_import = False

    def _should_not_import():
        nonlocal attempted_import
        attempted_import = True
        raise AssertionError("vendored triton_kernels should be gated off first")

    monkeypatch.setattr(import_utils, "import_triton_kernels", _should_not_import)

    assert import_utils.has_triton_kernels() is False
    assert attempted_import is False
    assert any("triton.language.target_info" in msg for msg in logger.warnings)
