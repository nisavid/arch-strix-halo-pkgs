from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_TOOL = REPO_ROOT / "tools/gemma4_text_smoke.py"
COMMON_TOOL = REPO_ROOT / "tools/gemma4_smoke_common.py"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"


def test_text_only_smoke_tool_uses_tokenizer_not_processor():
    text = SMOKE_TOOL.read_text()

    assert "import argparse" in text
    assert "from transformers import AutoTokenizer" in text
    assert "AutoProcessor" not in text
    assert "apply_chat_template" in text
    assert 'parser.add_argument("--gpu-memory-utilization", type=float, default=0.75)' in text
    assert 'parser.add_argument("--max-model-len", type=int, default=128)' in text
    assert 'parser.add_argument("--max-tokens", type=int, default=16)' in text
    assert 'parser.add_argument("--max-num-batched-tokens", type=int, default=None)' in text
    assert 'def effective_max_num_batched_tokens(args: argparse.Namespace, model: Path) -> int | None:' in text
    assert 'if is_gemma4_26b_a4b(str(model)):' in text
    assert 'return 32' in text
    assert '"limit_mm_per_prompt": {"image": 0, "audio": 0, "video": 0},' in text
    assert "validate_basic_chat_text(output.text)" in text
    assert 'llm = LLM(**llm_kwargs)' in text


def test_text_smoke_supports_compiled_execution_mode():
    text = SMOKE_TOOL.read_text()

    assert "--execution-mode" in text
    assert '"compiled"' in text
    assert 'if args.execution_mode == "eager":' in text


def test_current_state_documents_tokenizer_only_text_smokes():
    text = CURRENT_STATE.read_text()

    assert (
        "for text-only offline inference, render prompts with\n"
        "    `tokenizer.apply_chat_template(..., add_generation_prompt=True)`"
    ) in text
    assert (
        "for multimodal offline inference, use `AutoProcessor.apply_chat_template`"
    ) in text


def test_basic_text_validation_rejects_non_ascii_garbage():
    spec = importlib.util.spec_from_file_location("gemma4_smoke_common", COMMON_TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    try:
        module.validate_basic_chat_text("au로-ถed- \\اً way-\u200b**1-나 own")
    except RuntimeError as exc:
        assert "unexpected non-ASCII content" in str(exc)
    else:
        raise AssertionError("expected non-ASCII garbage to fail validation")
