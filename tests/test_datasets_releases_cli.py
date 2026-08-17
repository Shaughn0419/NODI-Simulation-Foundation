from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pyarrow.parquet as pq
import yaml

from nodi_foundation import (
    DatasetSpec,
    ExecutionSpec,
    PairSpec,
    SimulationState,
    build_dataset,
    build_intervention_pairs,
    validate_release,
)
from nodi_foundation.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_state_schema_accepts_canonical_state() -> None:
    schema = json.loads((ROOT / "schemas/state_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(SimulationState().to_payload())


def test_dataset_release_is_deterministic_and_valid(tmp_path) -> None:
    def build(name: str, workers: int, chunk_size: int):
        return build_dataset(
            DatasetSpec(
                output_dir=tmp_path / name,
                state_count=16,
                feature_ranges={
                    "particle_diameter": (6.0e-8, 1.2e-7),
                    "particle_lateral": (-0.5, 0.5),
                    "wavelength": (5.5e-7, 7.0e-7),
                },
                seed=17,
                execution=ExecutionSpec(workers=workers, chunk_size=chunk_size),
            )
        )

    first = build("first", workers=1, chunk_size=5)
    second = build("second", workers=2, chunk_size=5)
    assert first.release_id == second.release_id
    assert validate_release(first.path).valid
    table = pq.read_table(first.path / "data.parquet")
    assert table.num_rows == 16
    assert {"state_id", "S_W", "C_r_W", "C_i_W"} <= set(table.column_names)
    assert len([name for name in table.column_names if name.startswith("derived.")]) == 20


def test_pair_release_matches_schema(tmp_path) -> None:
    release = build_intervention_pairs(
        PairSpec(
            output_dir=tmp_path / "pairs",
            anchor_states=(SimulationState(),),
            feature="particle_diameter",
            low_value=6.0e-8,
            high_value=1.2e-7,
            execution=ExecutionSpec(workers=1),
        )
    )
    assert release.pair_count == 1
    assert validate_release(release.path).valid
    row = pq.read_table(release.path / "pairs.parquet").to_pylist()[0]
    schema = json.loads((ROOT / "schemas/pair_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(row)
    assert row["delta_S_W"] > 0.0


def test_cli_info_capabilities_simulate_and_dataset(tmp_path, capsys) -> None:
    assert main(["info"]) == 0
    assert json.loads(capsys.readouterr().out)["package_version"] == "1.0.0"
    assert main(["capabilities"]) == 0
    assert json.loads(capsys.readouterr().out)["feature_count"] == 26

    result_path = tmp_path / "result.json"
    assert main(["simulate", str(ROOT / "examples/state.yaml"), "--output", str(result_path)]) == 0
    capsys.readouterr()
    assert len(json.loads(result_path.read_text(encoding="utf-8"))["result_hash"]) == 64

    spec = yaml.safe_load((ROOT / "examples/dataset.yaml").read_text(encoding="utf-8"))
    spec["state_count"] = 8
    spec["execution"]["workers"] = 1
    spec_path = tmp_path / "dataset.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    release_path = tmp_path / "dataset"
    assert main(["dataset", "build", str(spec_path), "--output", str(release_path)]) == 0
    capsys.readouterr()
    assert validate_release(release_path).valid


def test_release_tamper_is_detected(tmp_path) -> None:
    release = build_dataset(
        DatasetSpec(
            output_dir=tmp_path / "release",
            state_count=2,
            execution=ExecutionSpec(workers=1),
        )
    )
    with (release.path / "data.parquet").open("ab") as stream:
        stream.write(b"tamper")
    report = validate_release(release.path)
    assert not report.valid
    assert any("MISMATCH" in error for error in report.errors)
