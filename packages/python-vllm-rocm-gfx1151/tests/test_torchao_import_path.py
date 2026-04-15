from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0008-torchao-version-check-stays-metadata-only.patch"
)
BENCH_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0010-cli-help-avoids-eager-benchmark-imports.patch"
)
OPENAI_PROTOCOL_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0011-openai-protocol-lazifies-chat-utils-import.patch"
)
ARG_UTILS_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0012-arg-utils-lazifies-transformers-utils-imports.patch"
)


def test_pkgbuild_carries_torchao_import_patch():
    text = PKGBUILD.read_text()

    assert "pkgrel=17" in text
    assert PATCH.name in text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in text
    assert (
        '_apply_patch_if_needed '
        '"0009-lazy-import-torchao-config-only-for-torchao-quantization.patch"'
        in text
    )
    assert BENCH_PATCH.name in text
    assert f'_apply_patch_if_needed "{BENCH_PATCH.name}"' in text
    assert OPENAI_PROTOCOL_PATCH.name in text
    assert f'_apply_patch_if_needed "{OPENAI_PROTOCOL_PATCH.name}"' in text
    assert ARG_UTILS_PATCH.name in text
    assert f'_apply_patch_if_needed "{ARG_UTILS_PATCH.name}"' in text


def test_patch_moves_generic_version_checks_to_metadata_only_helper():
    text = PATCH.read_text()

    assert "torchao_utils.py" in text
    assert "Check installed torchao version without importing the torchao package" in text
    assert (
        "from vllm.model_executor.layers.quantization.torchao_utils import ("
        in text
    )
    assert (
        "-from vllm.model_executor.layers.quantization.torchao import "
        "torchao_version_at_least" in text
    )


def test_patch_lazy_imports_torchao_config_only_for_torchao_quantization():
    text = (
        REPO_ROOT
        / "packages/python-vllm-rocm-gfx1151/"
        / "0009-lazy-import-torchao-config-only-for-torchao-quantization.patch"
    ).read_text()

    assert '-    from .torchao import TorchAOConfig' in text
    assert '+    if quantization == "torchao":' in text
    assert '+        from .torchao import TorchAOConfig' in text
    assert '+        method_to_config["torchao"] = TorchAOConfig' in text


def test_patch_keeps_top_level_help_off_the_benchmark_import_path():
    text = BENCH_PATCH.read_text()

    assert "+def _should_load_benchmark_module() -> bool:" in text
    assert '+        benchmark_module = _BenchHelpModule()' in text
    assert '+class _BenchHelpSubcommand:' in text
    assert '+            usage=\"vllm bench <bench_type> [options]\",' in text


def test_patch_keeps_openai_protocol_off_chat_utils_import_path():
    text = OPENAI_PROTOCOL_PATCH.read_text()

    assert "-from vllm.entrypoints.chat_utils import make_tool_call_id" in text
    assert "+def _make_tool_call_id() -> str:" in text
    assert '+    from vllm.entrypoints.chat_utils import make_tool_call_id' in text
    assert "+    id: str = Field(default_factory=_make_tool_call_id)" in text


def test_patch_keeps_engine_args_off_transformers_utils_import_path():
    text = ARG_UTILS_PATCH.read_text()

    assert "-from vllm.transformers_utils.config import (" in text
    assert "-from vllm.transformers_utils.gguf_utils import is_gguf" in text
    assert "-from vllm.transformers_utils.repo_utils import get_model_path" in text
    assert "-from vllm.transformers_utils.utils import is_cloud_storage" in text
    assert "+            from vllm.transformers_utils.repo_utils import get_model_path" in text
    assert "+        from vllm.transformers_utils.gguf_utils import is_gguf" in text
    assert "+        from vllm.transformers_utils.config import (" in text
    assert "+        from vllm.transformers_utils.utils import is_cloud_storage" in text
