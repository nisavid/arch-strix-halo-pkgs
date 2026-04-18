from __future__ import annotations

from .scenario_loader import Scenario


def prompt_for_scenarios(scenarios: list[Scenario]) -> list[Scenario]:
    if not scenarios:
        return []
    print("Available scenarios:")
    for index, scenario in enumerate(scenarios, start=1):
        print(f"{index}) {scenario.id} [{scenario.engine}]")
    raw = input("Choose scenario numbers (comma separated): ").strip()
    if not raw:
        raise SystemExit("NO_SCENARIOS_SELECTED")
    chosen: list[Scenario] = []
    for part in raw.split(","):
        index = int(part.strip())
        chosen.append(scenarios[index - 1])
    return chosen
