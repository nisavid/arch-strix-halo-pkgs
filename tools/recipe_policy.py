"""Load policies/recipe-packages.toml with shared source pins expanded.

A top-level ``[source_pins]`` table names source revisions that several
packages share, such as one fork commit built into more than one package.
Package values refer to a pin as ``{source_pins.<name>}``; loading the policy
through this module replaces every reference with the pinned value, so a
repin is a one-line change to the table.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib


SOURCE_PINS_KEY = "source_pins"
SOURCE_PIN_TOKEN = re.compile(r"\{source_pins\.([A-Za-z0-9_-]+)\}")


def expand_source_pins(value, pins: dict[str, str]):
    """Return ``value`` with every ``{source_pins.<name>}`` reference expanded.

    Walks nested dicts and lists. An unknown pin name raises ``KeyError`` so a
    typo cannot render a literal placeholder into a PKGBUILD.
    """
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in pins:
                raise KeyError(f"unknown source pin: {name}")
            return str(pins[name])

        return SOURCE_PIN_TOKEN.sub(replace, value)
    if isinstance(value, dict):
        return {key: expand_source_pins(item, pins) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_source_pins(item, pins) for item in value]
    return value


def resolve_recipe_policy(payload: dict) -> dict:
    """Return a copy of a parsed recipe policy with source pins expanded."""
    pins = payload.get(SOURCE_PINS_KEY, {})
    resolved = dict(payload)
    resolved["packages"] = expand_source_pins(payload.get("packages", {}), pins)
    return resolved


def load_recipe_policy(path: Path) -> dict:
    with path.open("rb") as handle:
        return resolve_recipe_policy(tomllib.load(handle))
