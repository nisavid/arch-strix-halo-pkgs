from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_smoke_common import (
    KNOWN_ANSWER_PROMPT,
    long_decode_max_model_len,
    long_decode_max_tokens,
    long_decode_prompt,
    validate_known_answer_text,
    validate_long_decode_text,
)


def test_known_answer_prompt_asks_for_the_first_ten_primes():
    assert "first ten prime numbers" in KNOWN_ANSWER_PROMPT


@pytest.mark.parametrize(
    "text",
    [
        "2, 3, 5, 7, 11, 13, 17, 19, 23, 29",
        "2, 3, 5, 7, 11, 13, 17, 19, 23, 29.\n",
        "The first ten prime numbers are: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29",
    ],
)
def test_known_answer_accepts_the_exact_prime_list(text: str):
    validate_known_answer_text(text)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty"),
        ("2, 3, 5, 7, 11, 13, 17, 19, 23", "expected the first ten primes"),
        ("1, 2, 3, 5, 7, 11, 13, 17, 19, 23", "expected the first ten primes"),
        ("2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31", "expected the first ten primes"),
        ("2, 3, 5, 7, 11, 13, 17, 19, 23, 29 語語", "non-ASCII"),
    ],
)
def test_known_answer_rejects_wrong_or_garbled_output(text: str, reason: str):
    with pytest.raises(RuntimeError, match=reason):
        validate_known_answer_text(text)


def _counting_text(count: int, code_word: str = "PELICAN") -> str:
    numbers = ", ".join(str(value) for value in range(1, count + 1))
    return f"{numbers}\nCode word: {code_word}"


def test_long_decode_prompt_names_the_count_and_code_word():
    prompt = long_decode_prompt(150)

    assert "PELICAN" in prompt
    assert "count from 1 to 150" in prompt


def test_long_decode_accepts_full_count_followed_by_the_code_word():
    validate_long_decode_text(_counting_text(150), count=150)
    validate_long_decode_text(
        _counting_text(150).replace("Code word: PELICAN", "**Code word:** Pelican"),
        count=150,
    )


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty"),
        (_counting_text(149), "expected 1..150"),
        (_counting_text(150).replace("77, 78", "77, 77, 78"), "expected 1..150"),
        (_counting_text(150).replace("98, 99", "98, 98"), "expected 1..150"),
        ("1, 2, 3, ..., 150\nCode word: PELICAN", "expected 1..150"),
        (_counting_text(150, code_word="PENGUIN"), "code word"),
        (_counting_text(150).replace("40, 41", "40, да 41"), "non-ASCII"),
        ("PELICAN\n" + _counting_text(150, code_word=""), "code word"),
    ],
)
def test_long_decode_rejects_skipped_repeated_or_garbled_output(text: str, reason: str):
    with pytest.raises(RuntimeError, match=reason):
        validate_long_decode_text(text, count=150)


@pytest.mark.parametrize(
    ("count", "max_tokens", "max_model_len"),
    [
        # The default E2B-sized count keeps the original 800/1024 budget.
        (150, 800, 1024),
        # Measured with the 26B-A4B tokenizer: 1146 output tokens after a
        # 68-token chat prompt, 1214 in total, past the 1024-token window.
        (250, 1250, 1536),
    ],
)
def test_long_decode_budget_scales_with_the_count(
    count: int, max_tokens: int, max_model_len: int
):
    assert long_decode_max_tokens(count) == max_tokens
    assert long_decode_max_model_len(count) == max_model_len
