from __future__ import annotations

from datetime import datetime
from pathlib import Path


def default_run_root(repo_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return repo_root / "docs/worklog/inference-runs" / timestamp
