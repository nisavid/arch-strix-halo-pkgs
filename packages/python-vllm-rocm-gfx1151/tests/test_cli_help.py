from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SAGEMAKER_API_ROUTER = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib/python3.14/site-packages/vllm/entrypoints/sagemaker/api_router.py"
)
LORA_API_ROUTER = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib/python3.14/site-packages/vllm/entrypoints/serve/lora/api_router.py"
)


def test_sagemaker_router_is_optional_in_built_package():
    text = SAGEMAKER_API_ROUTER.read_text()
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
    text = LORA_API_ROUTER.read_text()
    assert (
        "import model_hosting_container_standards.sagemaker as "
        "sagemaker_standards"
    ) in text
    assert "except ModuleNotFoundError:" in text
    assert "sagemaker_standards = None" in text
    assert "if sagemaker_standards is None:" in text
    assert "SageMaker container standards are not installed; skipping " in text
    assert "runtime LoRA update routes." in text
