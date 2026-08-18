"""Command-line interface for the stable Foundation product surface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .batch import ExecutionSpec, simulate_batch
from .capabilities import capabilities
from .datasets import build_dataset, dataset_spec_from_mapping
from .interventions import PairSpec, build_intervention_pairs
from .models import ENGINE_VERSION, FEATURE_VERSION, SCHEMA_VERSION, SimulationState, canonical_json
from .releases import validate_release
from .simulate import simulate_state


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _execution(args: argparse.Namespace, *, output_dir: Path | None = None) -> ExecutionSpec:
    return ExecutionSpec(
        workers=args.workers,
        chunk_size=args.chunk_size,
        cache_dir=args.cache_dir,
        output_dir=output_dir,
        resume=not args.no_resume,
    )


def _add_execution(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-resume", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nodi-foundation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("info")
    subparsers.add_parser("capabilities")

    simulate_parser = subparsers.add_parser("simulate")
    simulate_parser.add_argument("state", type=Path)
    simulate_parser.add_argument("--output", type=Path, required=True)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("states", type=Path)
    batch_parser.add_argument("--output", type=Path, required=True)
    _add_execution(batch_parser)

    dataset_parser = subparsers.add_parser("dataset")
    dataset_parser.add_argument("action", choices=("build",))
    dataset_parser.add_argument("spec", type=Path)
    dataset_parser.add_argument("--output", type=Path, required=True)

    pair_parser = subparsers.add_parser("pairs")
    pair_parser.add_argument("action", choices=("build",))
    pair_parser.add_argument("spec", type=Path)
    pair_parser.add_argument("--output", type=Path, required=True)
    _add_execution(pair_parser)

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("action", choices=("validate",))
    release_parser.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "info":
        print(
            canonical_json(
                {
                    "product": "NODI Simulation Foundation",
                    "package_version": __version__,
                    "engine_version": ENGINE_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "feature_version": FEATURE_VERSION,
                }
            )
        )
        return 0
    if args.command == "capabilities":
        print(canonical_json(capabilities().to_payload()))
        return 0
    if args.command == "simulate":
        raw = _load_document(args.state)
        state_result = simulate_state(SimulationState.from_mapping(raw))
        _write_json(args.output, state_result.to_payload())
        print(state_result.result_hash)
        return 0
    if args.command == "batch":
        rows = [
            json.loads(line)
            for line in args.states.read_text(encoding="utf-8").splitlines()
            if line
        ]
        batch_result = simulate_batch(rows, execution=_execution(args, output_dir=args.output))
        print(
            canonical_json(
                {
                    "state_count": batch_result.state_count,
                    "cache_hits": batch_result.cache_hits,
                    "resumed_chunks": batch_result.resumed_chunks,
                }
            )
        )
        return 0
    if args.command == "dataset":
        raw = _load_document(args.spec)
        release = build_dataset(dataset_spec_from_mapping(dict(raw), output_dir=args.output))
        print(release.release_id)
        return 0
    if args.command == "pairs":
        raw = dict(_load_document(args.spec))
        anchors = tuple(SimulationState.from_mapping(row) for row in raw["anchor_states"])
        spec = PairSpec(
            output_dir=args.output,
            anchor_states=anchors,
            feature=str(raw["feature"]),
            low_value=float(raw["low_value"]),
            high_value=float(raw["high_value"]),
            release_name=str(raw.get("release_name", "NODI-PAIRS-CUSTOM-V4")),
            execution=_execution(args),
            feature_catalogue_hash=(
                None
                if raw.get("feature_catalogue_hash") is None
                else str(raw["feature_catalogue_hash"])
            ),
            qualification_report_hash=(
                None
                if raw.get("qualification_report_hash") is None
                else str(raw["qualification_report_hash"])
            ),
        )
        print(build_intervention_pairs(spec).release_id)
        return 0
    if args.command == "release":
        report = validate_release(args.path)
        print(canonical_json(report.to_payload()))
        return 0 if report.valid else 2
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    sys.exit(main())
