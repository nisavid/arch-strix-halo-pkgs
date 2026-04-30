import os
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_LIB = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib"
)


def _resolve_artifact(relative_path: str) -> Path | None:
    matches = list(PKG_LIB.glob(f"python*/site-packages/{relative_path}"))
    if not matches:
        return None

    def _python_version_key(path: Path) -> tuple[int, ...]:
        match = re.search(r"/python(\d+(?:\.\d+)*)/", path.as_posix())
        if match is None:
            return (-1,)
        return tuple(int(part) for part in match.group(1).split("."))

    return max(matches, key=_python_version_key)


def _require_or_skip(path: Path | None, label: str) -> Path:
    if path is not None:
        return path
    if os.getenv("REQUIRE_BUILT_VLLM_PACKAGE") == "1":
        pytest.fail(f"expected built vLLM package artifact missing: {label}")
    pytest.skip("built vLLM package image is not present")


def test_sagemaker_router_is_optional_in_built_package():
    router = _require_or_skip(
        _resolve_artifact("vllm/entrypoints/sagemaker/api_router.py"),
        "vllm/entrypoints/sagemaker/api_router.py",
    )

    text = router.read_text()
    assert (
        "import model_hosting_container_standards.sagemaker as "
        "sagemaker_standards"
    ) in text
    assert "except ModuleNotFoundError:" in text
    assert "sagemaker_standards = None" in text
    assert "if sagemaker_standards is None:" in text
    assert "SageMaker container standards are not installed; skipping " in text
    assert "SageMaker-specific API routes." in text
    assert "if sagemaker_standards is None:\n        return app" in text


def test_lora_router_skips_runtime_update_routes_without_sagemaker_standards():
    router = _require_or_skip(
        _resolve_artifact("vllm/entrypoints/serve/lora/api_router.py"),
        "vllm/entrypoints/serve/lora/api_router.py",
    )

    text = router.read_text()
    assert (
        "import model_hosting_container_standards.sagemaker as "
        "sagemaker_standards"
    ) in text
    assert "except ModuleNotFoundError:" in text
    assert "sagemaker_standards = None" in text
    assert "if sagemaker_standards is None:" in text
    assert "SageMaker container standards are not installed; skipping " in text
    assert "runtime LoRA update routes." in text
