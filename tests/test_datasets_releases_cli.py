from __future__ import annotations

import json
import runpy
from pathlib import Path

import jsonschema
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from nodi_foundation import (
    DatasetSpec,
    ExecutionSpec,
    PairSpec,
    SimulationState,
    build_dataset,
    build_intervention_pairs,
    capabilities,
    validate_release,
)
from nodi_foundation.cli import main
from nodi_foundation.errors import FoundationError
from nodi_foundation.models import canonical_json, canonical_sha256
from nodi_foundation.profiles import (
    FAST_CONTROL_PROFILE,
    FORMAL_PROFILE,
    FORMAL_QUALIFICATION_REPORT_SHA256,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v5_release_boundary_campaigns_have_disjoint_state_and_split_identities() -> None:
    builder = runpy.run_path(str(ROOT / "tools/build_reference_releases_v5.py"))
    reference_blocks = builder["_reference_blocks"]
    states_for_references = builder["_states_for_references"]
    development = reference_blocks(4, builder["DEVELOPMENT_SEED"])
    evaluation = reference_blocks(
        4,
        builder["EVALUATION_SEED"],
        boundary_policy=builder["EVALUATION_BOUNDARY_POLICY"],
    )
    development_ids = {
        state.state_id
        for state in states_for_references(tuple(enumerate(development)))
    }
    evaluation_ids = {
        state.state_id
        for state in states_for_references(tuple(enumerate(evaluation)))
    }
    assert len(development_ids) == len(evaluation_ids) == 512
    assert development_ids.isdisjoint(evaluation_ids)
    assert {state.split_group_id for state in development}.isdisjoint(
        state.split_group_id for state in evaluation
    )


def test_v5_fragment_consolidation_stabilizes_optional_reason_schema(tmp_path) -> None:
    builder = runpy.run_path(str(ROOT / "tools/build_reference_releases_v5.py"))
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    target = tmp_path / "combined.parquet"
    pq.write_table(
        pa.Table.from_pylist([{"value": 1, "coupling_undefined_reason": None}]),
        first,
    )
    pq.write_table(
        pa.Table.from_pylist(
            [{"value": 2, "coupling_undefined_reason": "REFERENCE_FIELD_BELOW_THRESHOLD"}]
        ),
        second,
    )

    builder["_consolidate"]([first, second], target)

    table = pq.read_table(target)
    assert pa.types.is_string(table.schema.field("coupling_undefined_reason").type)
    assert table["coupling_undefined_reason"].to_pylist() == [
        None,
        "REFERENCE_FIELD_BELOW_THRESHOLD",
    ]


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
                profile=FAST_CONTROL_PROFILE,
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
    assert len([name for name in table.column_names if name.startswith("derived.")]) == 50
    for row in table.to_pylist():
        assert row["derived.effective_confinement_ratio"] >= (
            row["derived.particle_geometric_confinement_ratio"]
        )
        assert row["derived.minimum_surface_clearance_m"] >= (
            row["environment.effective_wall_exclusion_m"] - 1.0e-21
        )
        assert row["derived.minimum_effective_wall_margin_m"] >= -1.0e-21
        assert 0.0 < row["derived.collection_sine_in_fill"] < 1.0


def test_pair_release_matches_schema(tmp_path) -> None:
    catalogue_hash = capabilities().catalogue_hash
    release = build_intervention_pairs(
        PairSpec(
            output_dir=tmp_path / "pairs",
            anchor_states=(SimulationState(),),
            feature="particle_diameter",
            low_value=6.0e-8,
            high_value=1.2e-7,
            execution=ExecutionSpec(workers=1),
            feature_catalogue_hash=catalogue_hash,
            qualification_report_hash=FORMAL_QUALIFICATION_REPORT_SHA256,
        )
    )
    assert release.pair_count == 1
    assert validate_release(release.path).valid
    row = pq.read_table(release.path / "pairs.parquet").to_pylist()[0]
    schema = json.loads((ROOT / "schemas/pair_schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(row)
    assert row["delta_S_W"] > 0.0


def test_formal_release_requires_and_preserves_qualification_binding(tmp_path) -> None:
    catalogue_hash = capabilities().catalogue_hash
    with pytest.raises(FoundationError, match="qualified report"):
        build_dataset(
            DatasetSpec(
                output_dir=tmp_path / "unqualified",
                state_count=1,
                feature_catalogue_hash=catalogue_hash,
                qualification_report_hash="0" * 64,
                execution=ExecutionSpec(workers=1),
            )
        )
    release = build_dataset(
        DatasetSpec(
            output_dir=tmp_path / "formal",
            state_count=2,
            feature_catalogue_hash=catalogue_hash,
            qualification_report_hash=FORMAL_QUALIFICATION_REPORT_SHA256,
            execution=ExecutionSpec(workers=1),
        )
    )
    assert validate_release(release.path).valid
    table = pq.read_table(release.path / "data.parquet", columns=["physics_profile_id"])
    assert set(table["physics_profile_id"].to_pylist()) == {FORMAL_PROFILE}

    manifest_path = release.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metadata"]["profile"] = FAST_CONTROL_PROFILE
    manifest["metadata"]["formal_reference_label_eligible"] = False
    body = dict(manifest)
    body.pop("release_id")
    manifest["release_id"] = canonical_sha256(body)
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    report = validate_release(release.path)
    assert "E_RELEASE_MIXED_OR_MISMATCHED_PROFILE_ROWS" in report.errors


def test_cli_info_capabilities_simulate_and_dataset(tmp_path, capsys) -> None:
    assert main(["info"]) == 0
    assert json.loads(capsys.readouterr().out)["package_version"] == "5.0.0"
    assert main(["capabilities"]) == 0
    assert json.loads(capsys.readouterr().out)["feature_count"] == 27

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
            profile=FAST_CONTROL_PROFILE,
            execution=ExecutionSpec(workers=1),
        )
    )
    with (release.path / "data.parquet").open("ab") as stream:
        stream.write(b"tamper")
    report = validate_release(release.path)
    assert not report.valid
    assert any("MISMATCH" in error for error in report.errors)
