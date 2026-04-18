from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Scenario:
    id: str
    summary: str
    engine: str
    model: str
    definition: dict
    source_path: Path


def load_scenarios(scenario_dir: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    seen_ids: set[str] = set()
    for path in sorted(scenario_dir.rglob("*.toml")):
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        for raw in document.get("scenario", []):
            given = raw["given"]
            scenario_id = str(raw["id"])
            if scenario_id in seen_ids:
                raise ValueError(f"DUPLICATE_SCENARIO_ID: {scenario_id}")
            seen_ids.add(scenario_id)
            scenarios.append(
                Scenario(
                    id=scenario_id,
                    summary=str(raw["summary"]),
                    engine=str(given["engine"]),
                    model=str(given["model"]),
                    definition=raw,
                    source_path=path,
                )
            )
    return scenarios


def select_scenarios(
    scenarios: list[Scenario],
    *,
    engines: set[str],
    models: set[str],
    scenario_ids: set[str],
) -> list[Scenario]:
    selected: list[Scenario] = []
    for scenario in scenarios:
        if engines and scenario.engine not in engines:
            continue
        if models and scenario.model not in models:
            continue
        if scenario_ids and scenario.id not in scenario_ids:
            continue
        selected.append(scenario)
    return selected
