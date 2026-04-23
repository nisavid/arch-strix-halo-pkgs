from __future__ import annotations

from pathlib import Path
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.scenario_loader import load_scenarios


def test_tracked_inference_scenarios_cover_vllm_llamacpp_and_lemonade():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")

    ids = {scenario.id for scenario in scenarios}
    engines = {scenario.engine for scenario in scenarios}
    tags_by_id = {scenario.id: set(scenario.tags) for scenario in scenarios}

    assert "vllm.gemma4.26b-a4b.text.basic" in ids
    assert "vllm.gemma4.26b-a4b.server.basic" in ids
    assert "vllm.gemma4.e2b.server.reasoning" in ids
    assert "vllm.gemma4.e2b.server.tool" in ids
    assert "vllm.gemma4.e2b.server.structured" in ids
    assert "vllm.gemma4.e2b.server.benchmark-lite" in ids
    assert "vllm.gemma4.e2b.server.image" in ids
    assert "vllm.gemma4.e2b.server.attn-triton" in ids
    assert "vllm.gemma4.e2b.server.attn-aiter-fa-blocked" in ids
    assert "vllm.gemma4.e2b.text.compiled" in ids
    assert "vllm.gemma4.26b-a4b.text.compiled" in ids
    assert "vllm.gemma4.26b-a4b.server.moe-aiter" in ids
    assert "vllm.torchao.tiny.generate" in ids
    assert "vllm.gemma4.e2b.torchao.real-model" in ids
    assert "vllm.qwen3_5.0_8b.text.basic" in ids
    assert "vllm.qwen3_5.0_8b.text.compiled" in ids
    assert "vllm.qwen3_5.0_8b.text.flash-attn-ck-blocked" in ids
    assert "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control" in ids
    assert (
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-compiled" in ids
    )
    assert "vllm.qwen3_6.35b-a3b.server.reasoning" in ids
    assert "vllm.qwen3_6.35b-a3b.server.reasoning-disabled" in ids
    assert "vllm.qwen3_6.35b-a3b.server.mtp" in ids
    assert "vllm.qwen3_6.35b-a3b.server.tool" in ids
    assert "vllm.qwen3_6.35b-a3b.server.benchmark-lite" in ids
    assert "vllm.qwen3_6.35b-a3b.server.advanced-selectors" in ids
    assert "vllm.qwen3_6.35b-a3b.server.long-context-reduced" in ids
    assert "vllm.qwen3_6.35b-a3b.server.media-embedding" in ids
    assert "vllm.speculative.eagle3.llama3_1_8b.server.basic" in ids
    assert "vllm.speculative.dflash.qwen3_8b-speculators.server.blocked" in ids
    assert "flash-attn.triton-amd.backend-import" in ids
    assert "flash-attn.triton-amd.qkvpacked-tiny" in ids
    assert "flash-attn.ck.varlen-tiny" in ids
    assert "vllm.pooling.multilingual-e5-small.embeddings" in ids
    assert "vllm.pooling.jina-reranker-v3.rerank" in ids
    assert "transformers.zeroentropy.zembed-1.embeddings" in ids
    assert "transformers.zeroentropy.zerank-2.rerank" in ids
    assert "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked" in ids
    assert "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked" in ids
    assert "vllm.qwen3.0_6b-fp8-kv.text.fp8-dense-quark" in ids
    assert "vllm.qwen2_5.0_5b-gptq-int4.text.basic" in ids
    assert "vllm.qwen3_5.2b-nvfp4.text.unsupported-rocm-gfx1151" in ids
    assert "llama.cpp.hip.help" in ids
    assert "llama.cpp.vulkan.help" in ids
    assert "lemonade.cli.help" in ids
    assert "lemonade.server.help" in ids
    assert "lemonade.pooling.zembed-1-q4-k-m.embeddings" in ids
    assert "lemonade.pooling.bge-reranker-v2-m3.rerank" in ids
    assert "torch-migraphx.pt2e.quantizer-import" in ids
    assert "torch-migraphx.resnet-tiny.dynamo" in ids
    assert "torch-migraphx.resnet-tiny.pt2e" in ids
    assert engines == {
        "vllm",
        "llama.cpp",
        "lemonade",
        "transformers",
        "torch-migraphx",
        "flash-attn",
    }
    assert "smoke" in tags_by_id["vllm.gemma4.26b-a4b.text.basic"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.image"]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "kernel-probe" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "flash-attention" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "blocked" in tags_by_id["vllm.gemma4.e2b.text.compiled"]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.26b-a4b.server.moe-aiter"]
    assert "quantization-probe" in tags_by_id["vllm.gemma4.e2b.torchao.real-model"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.torchao.real-model"]
    assert "blocked" not in tags_by_id["vllm.gemma4.e2b.torchao.real-model"]
    assert "pt2e" in tags_by_id["torch-migraphx.pt2e.quantizer-import"]
    assert "quantization-probe" in tags_by_id[
        "torch-migraphx.pt2e.quantizer-import"
    ]
    assert "compiled-probe" in tags_by_id["torch-migraphx.resnet-tiny.dynamo"]
    assert "resnet" in tags_by_id["torch-migraphx.resnet-tiny.dynamo"]
    assert "pt2e" in tags_by_id["torch-migraphx.resnet-tiny.pt2e"]
    assert "compiled-probe" in tags_by_id["torch-migraphx.resnet-tiny.pt2e"]
    assert "quantization-probe" in tags_by_id["torch-migraphx.resnet-tiny.pt2e"]
    assert "qwen3.5" in tags_by_id["vllm.qwen3_5.0_8b.text.basic"]
    assert "compiled-probe" in tags_by_id["vllm.qwen3_5.0_8b.text.compiled"]
    assert "kernel-probe" in tags_by_id[
        "vllm.qwen3_5.0_8b.text.flash-attn-ck-blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.qwen3_5.0_8b.text.flash-attn-ck-blocked"
    ]
    assert "qwen3.6" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked"
    ]
    assert "control" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control"
    ]
    assert "compiled-probe" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-compiled"
    ]
    assert "server" in tags_by_id["vllm.qwen3_6.35b-a3b.server.reasoning"]
    assert "exploratory" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.server.reasoning"
    ]
    assert "mtp" in tags_by_id["vllm.qwen3_6.35b-a3b.server.mtp"]
    assert "tool" in tags_by_id["vllm.qwen3_6.35b-a3b.server.tool"]
    assert "benchmark-lite" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.server.benchmark-lite"
    ]
    assert "advanced-selectors" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.server.advanced-selectors"
    ]
    assert "long-context" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.server.long-context-reduced"
    ]
    assert "multimodal" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.server.media-embedding"
    ]
    assert "eagle3" in tags_by_id[
        "vllm.speculative.eagle3.llama3_1_8b.server.basic"
    ]
    assert "dflash" in tags_by_id[
        "vllm.speculative.dflash.qwen3_8b-speculators.server.blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.speculative.dflash.qwen3_8b-speculators.server.blocked"
    ]
    assert tags_by_id["flash-attn.triton-amd.backend-import"] >= {
        "smoke",
        "flash-attention",
        "triton-amd",
    }
    assert tags_by_id["flash-attn.triton-amd.qkvpacked-tiny"] >= {
        "smoke",
        "flash-attention",
        "triton-amd",
        "kernel-probe",
    }
    assert "moe" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    ]
    assert "quark" in tags_by_id[
        "vllm.qwen3.0_6b-fp8-kv.text.fp8-dense-quark"
    ]
    assert "gptq" in tags_by_id["vllm.qwen2_5.0_5b-gptq-int4.text.basic"]
    assert "blocked" in tags_by_id[
        "vllm.qwen3_5.2b-nvfp4.text.unsupported-rocm-gfx1151"
    ]
    assert "pooling" in tags_by_id["vllm.pooling.multilingual-e5-small.embeddings"]
    assert "embeddings" in tags_by_id[
        "vllm.pooling.multilingual-e5-small.embeddings"
    ]
    assert "rerank" in tags_by_id["vllm.pooling.jina-reranker-v3.rerank"]
    assert "blocked" in tags_by_id["vllm.pooling.jina-reranker-v3.rerank"]
    assert "flex-attention" in tags_by_id[
        "vllm.pooling.jina-reranker-v3.rerank"
    ]


def test_gemma4_aiter_flash_attention_probe_records_current_blocker():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    probe = by_id["vllm.gemma4.e2b.server.attn-aiter-fa-blocked"]

    assert probe.model == "google/gemma-4-E2B-it"
    assert set(probe.tags) >= {
        "smoke",
        "gemma4",
        "server",
        "kernel-probe",
        "flash-attention",
        "aiter",
        "blocked",
        "exploratory",
    }
    assert probe.definition["given"]["tool"] == "gemma4_server_smoke.basic"
    assert probe.definition["when"]["argv"] == [
        "--attention-backend",
        "ROCM_AITER_FA",
        "--max-model-len",
        "128",
        "--max-num-batched-tokens",
        "32",
        "--startup-timeout",
        "90",
    ]

    assertions = probe.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {
            "kind": "server_log.contains",
            "value": "Selected backend AttentionBackendEnum.ROCM_AITER_FA is not valid",
        },
        {"kind": "server_log.contains", "value": "compute capability not supported"},
    ):
        assert expected in assertions


def test_qwen_recipe_surfaces_link_runnable_local_scenarios():
    scenario_path = REPO_ROOT / "inference/scenarios/vllm-qwen.toml"
    document = tomllib.loads(scenario_path.read_text(encoding="utf-8"))
    surfaces = {surface["id"]: surface for surface in document["recipe_surface"]}
    runnable_ids = {
        scenario.id for scenario in load_scenarios(REPO_ROOT / "inference/scenarios")
    }

    expected_ids = {
        "vllm.qwen.recipe.qwen3_6.server.reasoning",
        "vllm.qwen.recipe.qwen3_6.server.mtp",
        "vllm.qwen.recipe.qwen3_5.server.throughput_text",
        "vllm.qwen.recipe.qwen3_5.server.throughput_multimodal",
        "vllm.qwen.recipe.qwen3_5.server.latency_mtp",
        "vllm.qwen.recipe.qwen3_5.server.tool_calling",
        "vllm.qwen.recipe.qwen3_5.benchmark.openai_chat",
        "vllm.qwen.recipe.qwen3_5.client.openai_multimodal",
        "vllm.qwen.recipe.qwen3_5.server.long_context_yarn",
    }
    allowed_statuses = {"validated", "tracked", "planned", "advisory-only"}

    assert expected_ids <= set(surfaces)
    assert all(surface["status"] in allowed_statuses for surface in surfaces.values())
    assert not set(surfaces) & runnable_ids
    assert surfaces["vllm.qwen.recipe.qwen3_6.server.reasoning"]["status"] == (
        "validated"
    )
    assert surfaces["vllm.qwen.recipe.qwen3_6.server.reasoning"][
        "local_scenarios"
    ] == [
        "vllm.qwen3_6.35b-a3b.server.reasoning",
        "vllm.qwen3_6.35b-a3b.server.reasoning-disabled",
    ]
    assert surfaces["vllm.qwen.recipe.qwen3_6.server.mtp"]["local_scenarios"] == [
        "vllm.qwen3_6.35b-a3b.server.mtp"
    ]
    assert surfaces["vllm.qwen.recipe.qwen3_5.server.tool_calling"][
        "local_scenarios"
    ] == ["vllm.qwen3_6.35b-a3b.server.tool"]
    assert surfaces["vllm.qwen.recipe.qwen3_5.benchmark.openai_chat"][
        "local_scenarios"
    ] == ["vllm.qwen3_6.35b-a3b.server.benchmark-lite"]
    assert surfaces["vllm.qwen.recipe.qwen3_5.client.openai_multimodal"][
        "local_scenarios"
    ] == ["vllm.qwen3_6.35b-a3b.server.media-embedding"]
    assert surfaces["vllm.qwen.recipe.qwen3_5.server.long_context_yarn"][
        "local_scenarios"
    ] == ["vllm.qwen3_6.35b-a3b.server.long-context-reduced"]
    assert surfaces["vllm.qwen.recipe.qwen3_5.server.throughput_text"][
        "status"
    ] == "advisory-only"
    assert surfaces["vllm.qwen.recipe.qwen3_6.server.mtp"]["status"] == "validated"
    assert surfaces["vllm.qwen.recipe.qwen3_5.server.tool_calling"]["status"] == (
        "validated"
    )
    assert surfaces["vllm.qwen.recipe.qwen3_6.server.advanced_selectors"][
        "status"
    ] == "validated"
    assert surfaces["vllm.qwen.recipe.qwen3_5.benchmark.openai_chat"][
        "status"
    ] == "validated"
    assert surfaces["vllm.qwen.recipe.qwen3_5.client.openai_multimodal"][
        "status"
    ] == "validated"
    assert "--reasoning-parser qwen3" in surfaces[
        "vllm.qwen.recipe.qwen3_6.server.reasoning"
    ]["required_flags"]
    assert "--language-model-only" in surfaces[
        "vllm.qwen.recipe.qwen3_5.server.throughput_text"
    ]["required_flags"]
    assert "--mm-encoder-tp-mode data" in surfaces[
        "vllm.qwen.recipe.qwen3_5.server.throughput_multimodal"
    ]["required_flags"]
    assert "--tool-call-parser qwen3_coder" in surfaces[
        "vllm.qwen.recipe.qwen3_5.server.tool_calling"
    ]["required_flags"]
    assert "VLLM_ALLOW_LONG_MAX_MODEL_LEN=1" in surfaces[
        "vllm.qwen.recipe.qwen3_5.server.long_context_yarn"
    ]["required_flags"]


def test_qwen_server_scenarios_record_reduced_local_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    expected_modes = {
        "vllm.qwen3_6.35b-a3b.server.reasoning": "reasoning_ok",
        "vllm.qwen3_6.35b-a3b.server.reasoning-disabled": "reasoning_disabled_ok",
        "vllm.qwen3_6.35b-a3b.server.mtp": "mtp_ok",
        "vllm.qwen3_6.35b-a3b.server.tool": "tool_ok",
        "vllm.qwen3_6.35b-a3b.server.benchmark-lite": "benchmark_lite_ok",
        "vllm.qwen3_6.35b-a3b.server.advanced-selectors": "advanced_selectors_ok",
        "vllm.qwen3_6.35b-a3b.server.long-context-reduced": (
            "long_context_reduced_ok"
        ),
        "vllm.qwen3_6.35b-a3b.server.media-embedding": "media_embedding_ok",
    }

    for scenario_id, ok_marker in expected_modes.items():
        scenario = by_id[scenario_id]
        mode = scenario_id.rsplit(".", 1)[1]
        assert scenario.model == "Qwen/Qwen3.6-35B-A3B"
        assert set(scenario.tags) >= {"smoke", "qwen", "qwen3.6", "server", "exploratory"}
        assert scenario.definition["given"]["tool"] == f"qwen_server_smoke.{mode}"
        assert scenario.definition["when"]["env"] == {
            "VLLM_ROCM_USE_AITER": "0",
            "VLLM_ROCM_USE_AITER_MOE": "0",
        }
        assertions = scenario.definition["then"]["assert"]
        for expected in (
            {"kind": "exit_code.equals", "value": 0},
            {"kind": "stdout.contains", "value": "server_ready"},
            {"kind": "stdout.contains", "value": ok_marker},
            {
                "kind": "server_log.contains",
                "value": "Using TRITON backend for Unquantized MoE",
            },
        ):
            assert expected in assertions


def test_speculative_decoding_scenarios_record_upstream_evidence():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    eagle3 = by_id["vllm.speculative.eagle3.llama3_1_8b.server.basic"]
    dflash = by_id["vllm.speculative.dflash.qwen3_8b-speculators.server.blocked"]

    assert eagle3.model == "meta-llama/Llama-3.1-8B-Instruct"
    assert eagle3.speculative_model == (
        "RedHatAI/Llama-3.1-8B-Instruct-speculator.eagle3"
    )
    assert set(eagle3.tags) >= {
        "vllm",
        "speculative-decoding",
        "eagle3",
        "server",
        "exploratory",
    }
    assert eagle3.definition["given"]["tool"] == "qwen_server_smoke.benchmark-lite"
    assert eagle3.definition["given"]["speculative_config"] == {
        "method": "eagle3",
        "model": "RedHatAI/Llama-3.1-8B-Instruct-speculator.eagle3",
        "draft_tensor_parallel_size": 2,
        "num_speculative_tokens": 2,
    }
    assert eagle3.definition["source_url"] == (
        "https://docs.vllm.ai/en/latest/features/speculative_decoding/eagle/"
    )

    assert dflash.model == "nm-testing/dflash-qwen3-8b-speculators"
    assert dflash.speculative_model == "nm-testing/dflash-qwen3-8b-speculators"
    assert set(dflash.tags) >= {
        "vllm",
        "speculative-decoding",
        "dflash",
        "qwen",
        "qwen3",
        "server",
        "blocked",
        "exploratory",
    }
    assert dflash.definition["source_url"] == (
        "https://github.com/vllm-project/vllm/pull/38300"
    )
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {"kind": "output.contains", "value": "DFlashDraftModel"},
    ):
        assert expected in dflash.definition["then"]["assert"]


def test_flash_attn_scenarios_record_triton_amd_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    backend_import = by_id["flash-attn.triton-amd.backend-import"]
    qkvpacked_tiny = by_id["flash-attn.triton-amd.qkvpacked-tiny"]
    vllm_vit = by_id["vllm.flash-attn.triton-amd.vit-wrapper"]

    assert backend_import.engine == "flash-attn"
    assert backend_import.model == "builtin"
    assert backend_import.definition["given"]["tool"] == "flash_attn_smoke.backend-import"
    assert backend_import.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE",
    }
    assert set(backend_import.tags) >= {
        "smoke",
        "flash-attention",
        "triton-amd",
    }

    assert qkvpacked_tiny.engine == "flash-attn"
    assert qkvpacked_tiny.model == "builtin"
    assert qkvpacked_tiny.definition["given"]["tool"] == "flash_attn_smoke.qkvpacked-tiny"
    assert qkvpacked_tiny.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE",
    }
    assert qkvpacked_tiny.definition["when"]["argv"] == [
        "--seqlen",
        "16",
        "--heads",
        "2",
        "--head-dim",
        "32",
    ]
    assert set(qkvpacked_tiny.tags) >= {
        "smoke",
        "flash-attention",
        "triton-amd",
        "kernel-probe",
    }

    assert vllm_vit.engine == "vllm"
    assert vllm_vit.model == "builtin"
    assert vllm_vit.definition["given"]["tool"] == "vllm_flash_attn_smoke.vit-wrapper"
    assert vllm_vit.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE",
    }
    assert set(vllm_vit.tags) >= {
        "smoke",
        "vllm",
        "flash-attention",
        "triton-amd",
        "kernel-probe",
    }
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "mode vit-wrapper"},
        {"kind": "stdout.contains", "value": "vit_backend FLASH_ATTN"},
        {"kind": "stdout.contains", "value": "vllm_flash_attn_vit_ok"},
    ):
        assert expected in vllm_vit.definition["then"]["assert"]


def test_flash_attn_scenarios_record_ck_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    backend_import = by_id["flash-attn.ck.backend-import"]
    qkvpacked_tiny = by_id["flash-attn.ck.qkvpacked-tiny"]
    varlen_tiny = by_id["flash-attn.ck.varlen-tiny"]

    assert backend_import.engine == "flash-attn"
    assert backend_import.model == "builtin"
    assert backend_import.definition["given"]["tool"] == "flash_attn_smoke.ck-backend-import"
    assert backend_import.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "FALSE",
    }
    assert set(backend_import.tags) >= {
        "smoke",
        "flash-attention",
        "ck",
    }

    assert qkvpacked_tiny.engine == "flash-attn"
    assert qkvpacked_tiny.model == "builtin"
    assert qkvpacked_tiny.definition["given"]["tool"] == "flash_attn_smoke.ck-qkvpacked-tiny"
    assert qkvpacked_tiny.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "FALSE",
    }
    assert qkvpacked_tiny.definition["when"]["argv"] == [
        "--seqlen",
        "16",
        "--heads",
        "2",
        "--head-dim",
        "32",
    ]
    assert set(qkvpacked_tiny.tags) >= {
        "smoke",
        "flash-attention",
        "ck",
        "kernel-probe",
    }

    assert varlen_tiny.engine == "flash-attn"
    assert varlen_tiny.model == "builtin"
    assert varlen_tiny.definition["given"]["tool"] == "flash_attn_smoke.ck-varlen-tiny"
    assert varlen_tiny.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "FALSE",
    }
    assert varlen_tiny.definition["when"]["argv"] == [
        "--seqlen",
        "16",
        "--heads",
        "2",
        "--head-dim",
        "32",
    ]
    assert set(varlen_tiny.tags) >= {
        "smoke",
        "flash-attention",
        "ck",
        "kernel-probe",
    }


def test_gemma4_e2b_compiled_probe_records_current_blocker():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    probe = by_id["vllm.gemma4.e2b.text.compiled"]

    assert probe.model == "google/gemma-4-E2B-it"
    assert set(probe.tags) >= {
        "smoke",
        "gemma4",
        "compiled-probe",
        "blocked",
        "exploratory",
    }
    assert probe.definition["given"]["tool"] == "gemma4_text_smoke"
    assert probe.definition["when"]["argv"] == [
        "--execution-mode",
        "compiled",
        "--max-model-len",
        "512",
    ]

    assertions = probe.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {
            "kind": "output.contains",
            "value": "basic mode response included unexpected non-ASCII content",
        },
    ):
        assert expected in assertions


def test_qwen3_6_fp8_moe_probes_record_backend_modes():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")

    no_aiter = next(
        scenario
        for scenario in scenarios
        if scenario.id
        == "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked"
    )
    forced_aiter = next(
        scenario
        for scenario in scenarios
        if scenario.id == "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    )

    assert no_aiter.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }
    assert forced_aiter.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "1",
        "VLLM_ROCM_USE_AITER_MOE": "1",
    }
    assert {
        "kind": "stdout.contains",
        "value": "config_quantization_config_present true",
    } in no_aiter.definition["then"]["assert"]
    assert {
        "kind": "stdout.contains",
        "value": "config_quantization_config_present true",
    } in forced_aiter.definition["then"]["assert"]


def test_quantization_lane_probes_record_root_cause_contracts():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    fp8_dense = by_id["vllm.qwen3.0_6b-fp8-kv.text.fp8-dense-quark"]
    assert fp8_dense.model == "EliovpAI/Qwen3-0.6B-FP8-KV"
    assert set(fp8_dense.tags) >= {
        "qwen",
        "qwen3",
        "fp8",
        "quark",
        "kv-cache-fp8",
        "quantization-probe",
        "exploratory",
    }
    assert fp8_dense.definition["given"]["tool"] == "qwen_text_smoke"
    assert fp8_dense.definition["when"]["argv"] == [
        "--quantization",
        "quark",
        "--kv-cache-dtype",
        "fp8",
        "--max-model-len",
        "128",
    ]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "quantization quark"},
        {"kind": "stdout.contains", "value": "kv_cache_dtype fp8"},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present true",
        },
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
    ):
        assert expected in fp8_dense.definition["then"]["assert"]

    gptq = by_id["vllm.qwen2_5.0_5b-gptq-int4.text.basic"]
    assert gptq.model == "Qwen/Qwen2.5-0.5B-Instruct-GPTQ-Int4"
    assert set(gptq.tags) >= {
        "qwen",
        "qwen2.5",
        "gptq",
        "int4",
        "quantization-probe",
        "exploratory",
    }
    assert gptq.definition["when"]["argv"] == [
        "--dtype",
        "float16",
        "--max-model-len",
        "128",
    ]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "dtype float16"},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present true",
        },
        {"kind": "stdout.contains", "value": "config_model_type qwen2"},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
    ):
        assert expected in gptq.definition["then"]["assert"]

    nvfp4 = by_id["vllm.qwen3_5.2b-nvfp4.text.unsupported-rocm-gfx1151"]
    assert nvfp4.model == "AxionML/Qwen3.5-2B-NVFP4"
    assert set(nvfp4.tags) >= {
        "qwen",
        "qwen3.5",
        "nvfp4",
        "modelopt",
        "quantization-probe",
        "blocked",
        "exploratory",
    }
    assert nvfp4.definition["when"]["argv"] == [
        "--quantization",
        "modelopt_fp4",
        "--max-model-len",
        "128",
    ]
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present true",
        },
        {
            "kind": "output.contains",
            "value": "modelopt_fp4 quantization is currently not supported in rocm.",
        },
    ):
        assert expected in nvfp4.definition["then"]["assert"]


def test_qwen3_5_compiled_probe_records_validation_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    probe = by_id["vllm.qwen3_5.0_8b.text.compiled"]

    assert probe.model == "Qwen/Qwen3.5-0.8B"
    assert set(probe.tags) >= {
        "smoke",
        "qwen",
        "qwen3.5",
        "hybrid",
        "gdn",
        "compiled-probe",
        "exploratory",
    }
    assert probe.definition["given"]["tool"] == "qwen_text_smoke"
    assert probe.definition["when"]["argv"] == ["--execution-mode", "compiled"]

    assertions = probe.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "config_model_type qwen3_5"},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
    ):
        assert expected in assertions


def test_qwen3_5_flash_attn_ck_probe_records_validation_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    probe = by_id["vllm.qwen3_5.0_8b.text.flash-attn-ck-blocked"]

    assert probe.model == "Qwen/Qwen3.5-0.8B"
    assert set(probe.tags) >= {
        "qwen",
        "qwen3.5",
        "flash-attention",
        "ck",
        "kernel-probe",
        "exploratory",
        "blocked",
    }
    assert probe.definition["given"]["tool"] == "qwen_text_smoke"
    assert probe.definition["when"]["argv"] == [
        "--attention-backend",
        "FLASH_ATTN",
        "--expected-flash-attn-backend",
        "ck",
        "--gpu-memory-utilization",
        "0.55",
    ]
    assert probe.definition["when"]["env"] == {
        "FLASH_ATTENTION_TRITON_AMD_ENABLE": "FALSE",
    }

    assertions = probe.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {"kind": "stdout.contains", "value": "attention_backend FLASH_ATTN"},
        {"kind": "stdout.contains", "value": "flash_attn_use_triton_rocm False"},
        {"kind": "stdout.contains", "value": "flash_attn_backend_module flash_attn_2_cuda"},
        {"kind": "stdout.contains", "value": "config_head_dim 256"},
        {
            "kind": "output.contains",
            "value": "ROCm flash-attn varlen API is not vLLM-compatible",
        },
    ):
        assert expected in assertions


def test_vllm_pooling_scenarios_record_validation_contracts():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    embeddings = by_id["vllm.pooling.multilingual-e5-small.embeddings"]
    rerank = by_id["vllm.pooling.jina-reranker-v3.rerank"]

    assert embeddings.model == "intfloat/multilingual-e5-small"
    assert embeddings.definition["given"]["tool"] == "vllm_pooling_smoke.embeddings"
    assert set(embeddings.tags) >= {
        "smoke",
        "vllm",
        "pooling",
        "embeddings",
        "rocm",
        "flex-attention",
    }
    assert embeddings.definition["when"]["argv"] == [
        "--attention-backend",
        "FLEX_ATTENTION",
        "--max-model-len",
        "256",
    ]

    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "runner pooling"},
        {"kind": "stdout.contains", "value": "attention_backend FLEX_ATTENTION"},
        {"kind": "stdout.contains", "value": "embedding_count 3"},
        {"kind": "stdout.contains", "value": "embeddings_finite_ok"},
        {"kind": "stdout.contains", "value": "embedding_ranking_ok"},
        {"kind": "stdout.contains", "value": "embeddings_ok"},
    ):
        assert expected in embeddings.definition["then"]["assert"]

    assert rerank.model == "jinaai/jina-reranker-v3"
    assert rerank.definition["given"]["tool"] == "vllm_pooling_smoke.rerank"
    assert set(rerank.tags) >= {
        "smoke",
        "vllm",
        "pooling",
        "rerank",
        "rocm",
        "flex-attention",
        "blocked",
    }
    assert rerank.definition["when"]["argv"] == [
        "--attention-backend",
        "FLEX_ATTENTION",
        "--max-model-len",
        "512",
    ]

    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {"kind": "stdout.contains", "value": "runner pooling"},
        {"kind": "stdout.contains", "value": "attention_backend FLEX_ATTENTION"},
        {"kind": "stdout.contains", "value": "pooling_task classify"},
        {"kind": "stdout.contains", "value": "convert classify"},
        {"kind": "stdout.contains", "value": "TransformersForSequenceClassification"},
        {
            "kind": "stderr.contains",
            "value": "Following weights were not initialized from checkpoint",
        },
        {"kind": "stderr.contains", "value": "model.lm_head.weight"},
        {"kind": "stderr.contains", "value": "score.weight"},
    ):
        assert expected in rerank.definition["then"]["assert"]


def test_qwen3_6_unquantized_moe_control_records_validation_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    control = by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control"
    ]

    assert control.model == "Qwen/Qwen3.6-35B-A3B"
    assert set(control.tags) >= {
        "smoke",
        "qwen",
        "qwen3.6",
        "moe",
        "unquantized",
        "control",
        "exploratory",
    }
    assert control.definition["given"]["tool"] == "qwen_text_smoke"
    assert control.definition["when"]["argv"] == [
        "--max-num-batched-tokens",
        "32",
        "--gpu-memory-utilization",
        "0.9",
    ]
    assert control.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }

    assertions = control.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present false",
        },
        {"kind": "stdout.contains", "value": "config_model_type qwen3_5_moe"},
        {
            "kind": "stdout.contains",
            "value": "text_config_model_type qwen3_5_moe_text",
        },
        {"kind": "stdout.contains", "value": "config_num_hidden_layers 40"},
        {"kind": "stdout.contains", "value": "config_num_experts 256"},
        {"kind": "stdout.contains", "value": "config_num_experts_per_tok 8"},
        {
            "kind": "stdout.contains",
            "value": "config_layer_types full_attention:10,linear_attention:30",
        },
        {"kind": "stdout.contains", "value": "llm_init_ok"},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
        {
            "kind": "output.contains",
            "value": "Using TRITON backend for Unquantized MoE",
        },
    ):
        assert expected in assertions


def test_qwen3_6_unquantized_moe_compiled_control_records_validation_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    control = by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-compiled"
    ]

    assert control.model == "Qwen/Qwen3.6-35B-A3B"
    assert set(control.tags) >= {
        "smoke",
        "qwen",
        "qwen3.6",
        "moe",
        "unquantized",
        "control",
        "compiled-probe",
        "exploratory",
    }
    assert control.definition["given"]["tool"] == "qwen_text_smoke"
    assert control.definition["when"]["argv"] == [
        "--execution-mode",
        "compiled",
        "--max-num-batched-tokens",
        "32",
        "--gpu-memory-utilization",
        "0.9",
    ]
    assert control.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }

    assertions = control.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present false",
        },
        {"kind": "stdout.contains", "value": "config_model_type qwen3_5_moe"},
        {
            "kind": "stdout.contains",
            "value": "text_config_model_type qwen3_5_moe_text",
        },
        {"kind": "stdout.contains", "value": "config_num_hidden_layers 40"},
        {"kind": "stdout.contains", "value": "config_num_experts 256"},
        {"kind": "stdout.contains", "value": "config_num_experts_per_tok 8"},
        {
            "kind": "stdout.contains",
            "value": "config_layer_types full_attention:10,linear_attention:30",
        },
        {"kind": "stdout.contains", "value": "llm_init_ok"},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
        {
            "kind": "output.contains",
            "value": "Using TRITON backend for Unquantized MoE",
        },
    ):
        assert expected in assertions


def test_gemma4_real_model_torchao_serialized_scenario_records_skip_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    scenario = by_id["vllm.gemma4.e2b.torchao.real-model"]

    assert scenario.model == "google/gemma-4-E2B-it"
    assert scenario.definition["given"]["tool"] == "torchao_vllm_smoke.real-model"
    assert set(scenario.tags) >= {
        "smoke",
        "gemma4",
        "torchao",
        "quantization-probe",
        "exploratory",
    }
    assert "blocked" not in scenario.tags

    assertions = scenario.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {"kind": "stdout.contains", "value": "prepare_real_ok"},
        {"kind": "stdout.contains", "value": "skip_quantized_modules"},
        {"kind": "stdout.contains", "value": "quantized_patterns"},
        {"kind": "stdout.contains", "value": "llm_init_ok"},
        {"kind": "stdout.contains", "value": "generation_ok"},
    ):
        assert expected in assertions


def test_lemonade_help_smokes_assert_current_help_markers():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    cli_assertions = by_id["lemonade.cli.help"].definition["then"]["assert"]
    server_assertions = by_id["lemonade.server.help"].definition["then"]["assert"]

    assert {"kind": "output.contains", "value": "Lemonade CLI"} in cli_assertions
    assert {"kind": "output.contains", "value": "Lightweight LLM server"} in server_assertions
    assert {"kind": "output.contains", "value": "OPTIONS:"} in cli_assertions
    assert {"kind": "output.contains", "value": "OPTIONS:"} in server_assertions
