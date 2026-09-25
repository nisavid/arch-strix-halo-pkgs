from __future__ import annotations

import re


LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
ASCII_RESPONSE_PUNCTUATION = frozenset(",.!?;:-'\"()[]{}")


def validate_basic_chat_text(content: str, *, expected_words: int = 5) -> str:
    stripped = content.strip()
    if not stripped:
        raise RuntimeError("basic mode response content was empty")

    if not _is_ascii_chat_text(stripped):
        raise RuntimeError(
            "basic mode response included unexpected non-ASCII content: "
            f"{stripped!r}"
        )

    words = LATIN_WORD_RE.findall(stripped)
    if len(words) != expected_words:
        raise RuntimeError(
            "basic mode response did not contain exactly "
            f"{expected_words} Latin words: {stripped!r}"
        )

    return stripped


def _is_ascii_chat_text(text: str) -> bool:
    for char in text:
        if char.isascii() and (
            char.isalnum() or char.isspace() or char in ASCII_RESPONSE_PUNCTUATION
        ):
            continue
        return False
    return True


# Output-correctness checks for the Gemma 4 decode path. A Triton
# unified-attention miscompile on gfx1151 shows up as wrong tokens during
# decode, not as a failed run, so these checks compare greedy output with
# answers that are known in advance.
FIRST_TEN_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)
KNOWN_ANSWER_PROMPT = (
    "List the first ten prime numbers in increasing order. "
    "Output only the numbers, separated by commas."
)
KNOWN_ANSWER_MAX_TOKENS = 64

LONG_DECODE_CODE_WORD = "PELICAN"
LONG_DECODE_DEFAULT_COUNT = 150
# Counting to 150 is about 650 Gemma 4 tokens: long enough to cross the E2B
# 512-token sliding window, so recalling the code word at the end depends on
# the full-attention layers.
LONG_DECODE_MAX_TOKENS = 800
LONG_DECODE_MAX_MODEL_LEN = 1024

INTEGER_RE = re.compile(r"\d+")


def long_decode_prompt(count: int = LONG_DECODE_DEFAULT_COUNT) -> str:
    return (
        f"Remember this code word: {LONG_DECODE_CODE_WORD}. "
        f"First, count from 1 to {count}, writing every number in order, "
        "separated by commas and spaces. Then, on a new line, write "
        '"Code word: " followed by the code word. Output nothing else.'
    )


def validate_known_answer_text(content: str) -> str:
    stripped = _require_clean_ascii(content, label="known-answer")
    numbers = tuple(int(value) for value in INTEGER_RE.findall(stripped))
    if numbers != FIRST_TEN_PRIMES:
        raise RuntimeError(
            "known-answer response: expected the first ten primes "
            f"{list(FIRST_TEN_PRIMES)}, got {list(numbers)}: {stripped!r}"
        )
    return stripped


def validate_long_decode_text(
    content: str,
    *,
    count: int = LONG_DECODE_DEFAULT_COUNT,
    code_word: str = LONG_DECODE_CODE_WORD,
) -> str:
    stripped = _require_clean_ascii(content, label="long-decode")
    code_word_at = stripped.casefold().rfind(code_word.casefold())
    last_digit_at = max(
        (match.end() for match in INTEGER_RE.finditer(stripped)),
        default=-1,
    )
    if code_word_at < 0 or code_word_at < last_digit_at:
        raise RuntimeError(
            f"long-decode response did not end with the code word {code_word!r}: "
            f"{_excerpt(stripped)!r}"
        )
    numbers = [int(value) for value in INTEGER_RE.findall(stripped)]
    expected = list(range(1, count + 1))
    if numbers != expected:
        raise RuntimeError(
            f"long-decode response: expected 1..{count} in order, "
            f"first divergence {_first_divergence(numbers, expected)}: "
            f"{_excerpt(stripped)!r}"
        )
    return stripped


def _require_clean_ascii(content: str, *, label: str) -> str:
    stripped = content.strip()
    if not stripped:
        raise RuntimeError(f"{label} response content was empty")
    for char in stripped:
        if char.isascii() and (char.isprintable() or char in "\n\r\t"):
            continue
        raise RuntimeError(
            f"{label} response included unexpected non-ASCII content: "
            f"{_excerpt(stripped)!r}"
        )
    return stripped


def _first_divergence(actual: list[int], expected: list[int]) -> str:
    for index, (got, want) in enumerate(zip(actual, expected)):
        if got != want:
            return f"at index {index}: got {got}, expected {want}"
    return f"after {min(len(actual), len(expected))} numbers: got {len(actual)}, expected {len(expected)}"


def _excerpt(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]} ... {text[-half:]}"
