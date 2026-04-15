from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_TOOL = REPO_ROOT / "tools/gemma4_text_smoke.py"
CURRENT_STATE = REPO_ROOT / "docs/maintainers/current-state.md"


def test_text_only_smoke_tool_uses_tokenizer_not_processor():
    text = SMOKE_TOOL.read_text()

    assert "from transformers import AutoTokenizer" in text
    assert "AutoProcessor" not in text
    assert "apply_chat_template" in text
    assert 'limit_mm_per_prompt={"image": 0, "audio": 0, "video": 0}' in text


def test_current_state_documents_tokenizer_only_text_smokes():
    text = CURRENT_STATE.read_text()

    assert (
        "for text-only offline inference, render prompts with\n"
        "    `tokenizer.apply_chat_template(..., add_generation_prompt=True)`"
    ) in text
    assert (
        "for multimodal offline inference, use `AutoProcessor.apply_chat_template`"
    ) in text
