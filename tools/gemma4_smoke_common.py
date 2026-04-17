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
