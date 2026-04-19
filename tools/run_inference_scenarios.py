#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.menu import prompt_for_scenarios
from inference.runner import build_run_plan, run_scenarios
from inference.scenario_loader import load_scenarios, select_scenarios


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run declarative local inference scenarios serially"
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=Path("inference/scenarios"),
        help="directory containing scenario TOML files",
    )
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="select scenarios that include this tag; repeat for multiple tags",
    )
    parser.add_argument(
        "--include-exploratory",
        action="store_true",
        help="include exploratory scenarios in broad engine/model/tag selections",
    )
    parser.add_argument(
        "--model-path",
        action="append",
        default=[],
        help="bind a logical model id to a local filesystem path as MODEL=PATH",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        help="optional run artifact directory; defaults to docs/worklog/inference-runs/<timestamp>",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_model_bindings(raw_bindings: list[str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for raw in raw_bindings:
        if "=" not in raw:
            raise SystemExit(f"MODEL_PATH_BINDING_INVALID: {raw!r}")
        model, path = raw.split("=", 1)
        if not model or not path:
            raise SystemExit(f"MODEL_PATH_BINDING_INVALID: {raw!r}")
        bindings[model] = path
    return bindings


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    model_bindings = parse_model_bindings(args.model_path)
    scenarios = load_scenarios(args.scenario_dir.resolve())
    selected = select_scenarios(
        scenarios,
        engines=set(args.engine),
        models=set(args.model),
        scenario_ids=set(args.scenario),
        tags=set(args.tag),
        include_exploratory=args.include_exploratory,
    )
    if not (args.engine or args.model or args.scenario or args.tag):
        if sys.stdin.isatty() and sys.stdout.isatty():
            selected = prompt_for_scenarios(scenarios)
        else:
            print(
                "SCENARIO_SELECTION_REQUIRED: choose --engine, --model, --scenario, or run interactively",
                file=sys.stderr,
            )
            return 2
    if not selected:
        print("SCENARIO_SELECTION_EMPTY: no scenarios matched the requested filters", file=sys.stderr)
        return 2

    payload = build_run_plan(
        selected,
        repo_root=repo_root,
        run_root=args.run_root.resolve() if args.run_root is not None else None,
        model_bindings=model_bindings,
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    summary = run_scenarios(
        selected,
        repo_root=repo_root,
        run_root=Path(payload["planned_run_root"]),
        model_bindings=model_bindings,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
