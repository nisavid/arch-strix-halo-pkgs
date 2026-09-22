"""Resolve optional Lemonade loopback API keys from the run-time environment.

Scenario TOML never carries keys or credential paths. Operators supply them
when running scenarios, either as a value or as a path to a credential file
such as a systemd credential:

- ``LEMONADE_API_KEY`` or ``LEMONADE_API_KEY_FILE`` for regular endpoints
- ``LEMONADE_ADMIN_API_KEY`` or ``LEMONADE_ADMIN_API_KEY_FILE`` for
  ``/internal/*``; this falls back to the regular key, matching ``lemond``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


API_KEY_ENV = "LEMONADE_API_KEY"
API_KEY_FILE_ENV = "LEMONADE_API_KEY_FILE"
ADMIN_API_KEY_ENV = "LEMONADE_ADMIN_API_KEY"
ADMIN_API_KEY_FILE_ENV = "LEMONADE_ADMIN_API_KEY_FILE"


def _read_key(env: Mapping[str, str], value_name: str, file_name: str) -> str | None:
    key_file = env.get(file_name, "").strip()
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8").strip()
        if not key:
            raise ValueError(f"{file_name} names an empty credential file")
        return key
    key = env.get(value_name, "").strip()
    return key or None


def resolve_api_key(env: Mapping[str, str] | None = None) -> str | None:
    return _read_key(os.environ if env is None else env, API_KEY_ENV, API_KEY_FILE_ENV)


def resolve_admin_api_key(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    return _read_key(source, ADMIN_API_KEY_ENV, ADMIN_API_KEY_FILE_ENV) or resolve_api_key(
        source
    )


def auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}
