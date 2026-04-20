from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from safetensors import safe_open


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_TOOL = REPO_ROOT / "tools/torchao_vllm_smoke.py"


def test_prepare_only_builds_torchao_serialized_checkpoint(tmp_path: Path) -> None:
    out_dir = tmp_path / "torchao-smoke"
    env = {"PYTHONPYCACHEPREFIX": "/tmp"}

    result = subprocess.run(
        [sys.executable, str(SMOKE_TOOL), "--prepare-only", "--work-dir", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    quant_dir = out_dir / "tiny-llama-torchao"
    config = json.loads((quant_dir / "config.json").read_text())

    assert "prepare_ok" in result.stdout
    assert config["quantization_config"]["quant_method"] == "torchao"
    assert set(config["quantization_config"]["quant_type"]) == {"default"}
    assert config["hidden_size"] // config["num_attention_heads"] == 64
    assert (quant_dir / "model.safetensors").exists()

    with safe_open(str(quant_dir / "model.safetensors"), framework="pt") as f:
        metadata = f.metadata()
    weight_metadata = metadata["model.layers.0.self_attn.q_proj.weight"]
    assert '"_type": "Int8Tensor"' in weight_metadata
    assert '"bfloat16"' in weight_metadata


def test_dry_run_describes_real_model_quantize_and_serve_path(tmp_path: Path) -> None:
    source_model = tmp_path / "gemma-4-E2B-it"
    source_model.mkdir()
    work_dir = tmp_path / "torchao-real"

    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_TOOL),
            "--dry-run",
            "--source-model",
            str(source_model),
            "--work-dir",
            str(work_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )

    plan = json.loads(result.stdout)
    assert plan["mode"] == "real-model"
    assert plan["source_model"] == str(source_model)
    assert plan["quantized_model"] == str(work_dir / "real-model-torchao")
    assert plan["quantization"] == "torchao-int8-weight-only"
    assert plan["online_quantization"] is False
    assert plan["warning_markers"] == [
        "Stored version is not the same as current default version",
        "Cannot use ROCm custom paged attention kernel, falling back to Triton implementation",
    ]


def test_dry_run_describes_online_real_model_quantization(tmp_path: Path) -> None:
    source_model = tmp_path / "gemma-4-E2B-it"
    source_model.mkdir()
    work_dir = tmp_path / "torchao-real"

    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_TOOL),
            "--dry-run",
            "--source-model",
            str(source_model),
            "--online-quantization",
            "--work-dir",
            str(work_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )

    plan = json.loads(result.stdout)
    assert plan["mode"] == "real-model-online"
    assert plan["source_model"] == str(source_model)
    assert plan["quantized_model"] is None
    assert plan["online_quantization"] is True


def test_online_quantization_requires_source_model(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_TOOL),
            "--dry-run",
            "--online-quantization",
            "--work-dir",
            str(tmp_path / "torchao-real"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )

    assert result.returncode == 2
    assert "--online-quantization requires --source-model" in result.stderr


def test_dry_run_keeps_hub_source_model_refs_unresolved(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SMOKE_TOOL),
            "--dry-run",
            "--source-model",
            "google/gemma-4-E2B-it",
            "--work-dir",
            str(tmp_path / "torchao-real"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp"},
    )

    plan = json.loads(result.stdout)
    assert plan["source_model"] == "google/gemma-4-E2B-it"


def test_warning_classifier_reports_known_torchao_warnings() -> None:
    module = load_smoke_module()

    warnings = module.classify_warning_text(
        "WARNING Stored version is not the same as current default version\n"
        "WARNING Cannot use ROCm custom paged attention kernel, falling back to Triton implementation\n"
    )

    assert warnings == {
        "torchao_version_mismatch": True,
        "rocm_paged_attention_fallback": True,
    }


def test_real_model_save_prefers_processor_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_smoke_module()
    calls: list[tuple[str, str, str]] = []

    class FakeProcessor:
        def save_pretrained(self, path: Path) -> None:
            calls.append(("processor", "save", str(path)))

    class FakeAutoProcessor:
        @staticmethod
        def from_pretrained(source_model: str, *, trust_remote_code: bool):
            calls.append(("processor", source_model, str(trust_remote_code)))
            return FakeProcessor()

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(source_model: str, *, trust_remote_code: bool):
            calls.append(("tokenizer", source_model, str(trust_remote_code)))
            raise AssertionError("tokenizer fallback should not be used")

    monkeypatch.setattr(module, "AutoProcessor", FakeAutoProcessor)
    monkeypatch.setattr(module, "AutoTokenizer", FakeAutoTokenizer)

    module.save_processor_or_tokenizer("gemma4", tmp_path)

    assert calls == [
        ("processor", "gemma4", "True"),
        ("processor", "save", str(tmp_path)),
    ]


def test_real_model_save_falls_back_to_tokenizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_smoke_module()
    calls: list[tuple[str, str, str]] = []

    class FakeAutoProcessor:
        @staticmethod
        def from_pretrained(source_model: str, *, trust_remote_code: bool):
            calls.append(("processor", source_model, str(trust_remote_code)))
            raise OSError("no processor")

    class FakeTokenizer:
        def save_pretrained(self, path: Path) -> None:
            calls.append(("tokenizer", "save", str(path)))

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(source_model: str, *, trust_remote_code: bool):
            calls.append(("tokenizer", source_model, str(trust_remote_code)))
            return FakeTokenizer()

    monkeypatch.setattr(module, "AutoProcessor", FakeAutoProcessor)
    monkeypatch.setattr(module, "AutoTokenizer", FakeAutoTokenizer)

    module.save_processor_or_tokenizer("text-model", tmp_path)

    assert calls == [
        ("processor", "text-model", "True"),
        ("tokenizer", "text-model", "True"),
        ("tokenizer", "save", str(tmp_path)),
    ]


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("torchao_vllm_smoke", SMOKE_TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
