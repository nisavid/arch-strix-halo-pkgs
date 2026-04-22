from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOC = REPO_ROOT / "docs/maintainers/rocm-inference-reference.md"
INGESTION_SKILL = (
    REPO_ROOT / ".agents/skills/ingesting-rocm-inference-references/SKILL.md"
)
AGENTS = REPO_ROOT / "AGENTS.md"
BACKLOG = REPO_ROOT / "docs/backlog.md"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"
VLLM_COVERAGE = REPO_ROOT / "docs/maintainers/vllm-recipe-coverage.md"
PACKAGE_SKILL = (
    REPO_ROOT / ".agents/skills/maintaining-arch-strix-halo-packages/SKILL.md"
)
SCENARIO_SKILL = (
    REPO_ROOT / ".agents/skills/run-local-inference-scenarios/SKILL.md"
)
ALLOWED_STATUSES = {
    "`validated`",
    "`planned`",
    "`advisory-only`",
    "`requires-host-validation`",
}


def _source_disposition_rows():
    text = REFERENCE_DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = (
        "| Source | Source type | Retrieved | Validation status | "
        "Ingestion destination | Next gate | Notes |"
    )
    start = lines.index(header)
    rows = {}
    for line in lines[start + 2 :]:
        if not line.startswith("| "):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        source = cells[0].strip("<>")
        rows[source] = {
            "source_type": cells[1],
            "retrieved": cells[2],
            "status": cells[3],
            "destination": cells[4],
            "gate": cells[5],
            "notes": cells[6],
        }
    return rows


def test_rocm_inference_reference_preserves_source_disposition():
    text = REFERENCE_DOC.read_text(encoding="utf-8")
    rows = _source_disposition_rows()

    required_sources = {
        "github.com/ROCm/rocm-examples/tree/amd-staging",
        "AI/MIGraphX/Quantization",
        "Running-Quantized-ResNet50-via-MIGraphX.md",
        "github.com/ROCm/torch_migraphx",
        "deep-learning-compilation.html",
        "github.com/paudley/ai-notes/tree/main/strix-halo",
        "model-quantization.html",
        "model-acceleration-libraries.html",
        "optimizing-with-composable-kernel.html",
        "optimizing-triton-kernel.html",
        "profiling-and-debugging.html",
        "workload.html",
        "vllm-optimization.html",
        "github.com/ROCm/flash-attention",
    }
    for source_fragment in required_sources:
        matching_sources = [
            source for source in rows if source_fragment in source
        ]
        assert matching_sources, source_fragment
        row = rows[matching_sources[0]]
        assert row["retrieved"] == "2026-04-22"
        assert row["status"] in ALLOWED_STATUSES
        assert row["destination"]
        assert row["gate"]

    for term in [
        "validated",
        "planned",
        "advisory-only",
        "requires-host-validation",
        "source disposition",
        "mermaid",
        "migraphx-gfx1151",
        "python-torch-migraphx-gfx1151",
        "FLASH_ATTENTION_TRITON_AMD_ENABLE",
    ]:
        assert term in text

    flash_attention = rows["https://github.com/ROCm/flash-attention"]
    assert flash_attention["status"] == "`planned`"
    assert "docs/backlog.md" in flash_attention["destination"]
    assert "FlashAttention CK" in flash_attention["gate"]
    assert "FlashAttention Triton" in flash_attention["gate"]

    torch_migraphx = rows["https://github.com/ROCm/torch_migraphx/"]
    assert torch_migraphx["status"] == "`planned`"
    assert "python-torch-migraphx-gfx1151" in torch_migraphx["gate"]


def test_rocm_inference_ingestion_skill_covers_required_sinks():
    text = INGESTION_SKILL.read_text(encoding="utf-8")

    assert "name: ingesting-rocm-inference-references" in text
    assert "description: Use when" in text
    assert "source disposition" in text
    assert "parallel delegation" in text
    assert "process sources serially" in text
    assert "docs/maintainers/rocm-inference-reference.md" in text
    assert "docs/backlog.md" in text
    assert "docs/maintainers/current-state.md" in text
    assert "docs/maintainers/vllm-recipe-coverage.md" in text
    assert "inference/scenarios/" in text
    assert "validated" in text
    assert "advisory-only" in text
    assert "requires-host-validation" in text


def test_rocm_inference_reference_is_discoverable():
    agents = AGENTS.read_text(encoding="utf-8")
    package_skill = PACKAGE_SKILL.read_text(encoding="utf-8")
    scenario_skill = SCENARIO_SKILL.read_text(encoding="utf-8")

    for text in [agents, package_skill, scenario_skill]:
        assert "docs/maintainers/rocm-inference-reference.md" in text

    combined = "\n".join([agents, package_skill, scenario_skill])
    for trigger in [
        "MIGraphX",
        "FlashAttention",
        "AITER",
        "quantization",
        "profiling",
    ]:
        assert trigger in combined


def test_rocm_inference_backlog_and_state_are_guarded():
    backlog = BACKLOG.read_text(encoding="utf-8")
    current_state = CURRENT_STATE.read_text(encoding="utf-8")
    reference = REFERENCE_DOC.read_text(encoding="utf-8")
    coverage = VLLM_COVERAGE.read_text(encoding="utf-8")

    assert "Newly discovered ROCm inference candidates" in backlog
    assert "python-torch-migraphx-gfx1151" in backlog
    assert "MIGraphX Python binding" in backlog
    assert "package policy" in backlog
    assert "build proof" in backlog
    assert "python-torchao-rocm-gfx1151 0.17.0-2" in current_state
    assert "python-torch-migraphx-gfx1151 1.2-1" in current_state
    assert "MIGraphX-backed `SplitModule`" in current_state
    assert "publish/install of the built TorchAO and Torch-MIGraphX packages" in reference
    assert "FlashAttention CK" in backlog
    assert "FlashAttention Triton" in backlog
    assert "Freshness sweep triage gate" not in backlog
    assert "requires host validation" in backlog
    assert "ROCm inference reference boundary" in current_state
    assert "does not change validated host behavior" in current_state
    assert "triaged on 2026-04-22" in current_state
    assert "policies/package-freshness.toml" in current_state
    assert "Quark" in coverage
    assert "AWQ" in coverage
    assert "GPTQ" in coverage
    assert "FP8 KV-cache" in coverage
