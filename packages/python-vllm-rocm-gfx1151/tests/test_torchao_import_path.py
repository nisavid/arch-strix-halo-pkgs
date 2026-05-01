from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.1.patch"
)


def test_pkgbuild_carries_merged_torchao_and_cli_startup_patches():
    text = PKGBUILD.read_text()

    assert "pkgver=0.20.1" in text
    assert "pkgrel=3" in text
    assert PATCH.name in text
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in text
    assert '_apply_patch_if_needed "${_vllm_source_patch}"' in text
    assert "0009-lazy-import-torchao-config-only-for-torchao-quantization.patch" not in text
    assert "0010-cli-help-avoids-eager-benchmark-imports.patch" not in text
    assert "0011-openai-protocol-lazifies-chat-utils-import.patch" not in text
    assert "0012-arg-utils-lazifies-transformers-utils-imports.patch" not in text
    assert "0013-cli-help-keeps-top-level-path-runtime-light.patch" not in text
    assert "_apply_all_source_patches" in text


def test_merged_torchao_patch_keeps_version_checks_metadata_only_and_lazy_loads_torchao_config():
    text = PATCH.read_text()

    assert "torchao_utils.py" in text
    assert "Check installed torchao version without importing the torchao package" in text
    assert "+from importlib import metadata" in text
    assert '+            installed_version = metadata.version("torchao")' in text
    assert "+        except (metadata.PackageNotFoundError, version.InvalidVersion):" in text
    assert (
        "from vllm.model_executor.layers.quantization.torchao_utils import ("
        in text
    )
    assert "-def torchao_version_at_least(torchao_version: str) -> bool:" in text
    assert "-    if find_spec(\"torchao\"):" in text
    assert (
        "-from vllm.model_executor.layers.quantization.torchao import "
        "torchao_version_at_least" in text
    )
    assert '-    from .torchao import TorchAOConfig' in text
    assert '+    if quantization == "torchao":' in text
    assert '+        from .torchao import TorchAOConfig' in text
    assert '+        method_to_config["torchao"] = TorchAOConfig' in text


def test_merged_cli_patch_keeps_top_level_help_off_runtime_paths():
    text = PATCH.read_text()

    assert "+def _should_load_benchmark_module() -> bool:" in text
    assert '+        benchmark_module = _BenchHelpModule()' in text
    assert '+class _BenchHelpSubcommand:' in text
    assert '+            usage=\"vllm bench <bench_type> [options]\",' in text
    assert "-from vllm.entrypoints.chat_utils import make_tool_call_id" in text
    assert "+def _make_tool_call_id() -> str:" in text
    assert '+    from vllm.entrypoints.chat_utils import make_tool_call_id' in text
    assert "+    id: str = Field(default_factory=_make_tool_call_id)" in text
    assert "-from vllm.transformers_utils.config import (" in text
    assert "-from vllm.transformers_utils.gguf_utils import is_gguf" in text
    assert "-from vllm.transformers_utils.repo_utils import get_model_path" in text
    assert "-from vllm.transformers_utils.utils import is_cloud_storage" in text
    assert "+            from vllm.transformers_utils.repo_utils import get_model_path" in text
    assert "+        from vllm.transformers_utils.gguf_utils import is_gguf" in text
    assert "+        from vllm.transformers_utils.config import (" in text
    assert "+        from vllm.transformers_utils.utils import is_cloud_storage" in text
    assert "+class _StaticSubcommand:" in text
    assert "+class _StaticHelpModule:" in text
    assert "+def _selected_subcommand() -> str | None:" in text
    assert '+        openai_module = _StaticHelpModule(' in text
    assert '+        serve_module = _StaticHelpModule(' in text
    assert '+        launch_module = _StaticHelpModule(' in text
    assert '+        collect_env_module = _StaticHelpModule(' in text
    assert '+        run_batch_module = _StaticHelpModule(' in text
    assert "-from vllm.engine.arg_utils import EngineArgs" in text
    assert "-from vllm.platforms import current_platform" in text
    assert "+    from vllm.engine.arg_utils import EngineArgs" in text
    assert "+    from vllm.platforms import current_platform" in text
