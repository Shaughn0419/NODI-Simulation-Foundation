"""Run the single formal-M1 qualification panel and nested performance pilot."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import pstats
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from time import monotonic
from typing import Any

from nodi_foundation import (
    EnvironmentState,
    GeometryState,
    ObservationOperatorState,
    ParticleState,
    PositionState,
    SimulationState,
    SourceState,
    capabilities,
    simulate_state,
)
from nodi_foundation._physics.formal_m1 import (
    CONFIG_HASH,
    clear_formal_caches,
    evaluate_formal_m1,
    formal_cache_stats,
)
from nodi_foundation.models import canonical_sha256
from nodi_foundation.profiles import FAST_CONTROL_PROFILE
from nodi_foundation.resources import (
    COMMITTED_MEMORY_LIMIT_BYTES,
    assert_resource_budget,
    system_committed_memory_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
PAPER1_ROOT = ROOT.parent / "NODI_ReferenceCoupling_Paper"
PAPER1_COMMIT = "bb27a3ac882344e4ef26663102cd6c0a6882b675"
PANEL_TOLERANCE = 0.10
POWER_FLOOR_W = 1.0e-18


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_sha256(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def _verify_paper1_source_lock() -> dict[str, Any]:
    source_map = json.loads((ROOT / "source_map.json").read_text(encoding="utf-8"))
    authority = source_map["physics_authority"]
    if authority["commit"] != PAPER1_COMMIT:
        raise RuntimeError("Foundation source map does not bind the qualification commit")
    subprocess.check_call(
        ["git", "-C", str(PAPER1_ROOT), "cat-file", "-e", f"{PAPER1_COMMIT}^{{commit}}"]
    )
    for source in authority["sources"]:
        actual = subprocess.check_output(
            [
                "git",
                "-C",
                str(PAPER1_ROOT),
                "rev-parse",
                f"{PAPER1_COMMIT}:{source['path']}",
            ],
            text=True,
        ).strip()
        if actual != source["blob"]:
            raise RuntimeError(f"Paper 1 source-lock blob drift: {source['path']}")
    return {
        "repository": authority["repository"],
        "locked_commit": PAPER1_COMMIT,
        "locked_source_blob_count": len(authority["sources"]),
        "local_checkout_head_observed": _git_head(PAPER1_ROOT),
        "locked_objects_verified": True,
        "runtime_import_in_product": False,
    }


def _relative(first: float, second: float, floor: float = POWER_FLOOR_W) -> float:
    return abs(first - second) / max(abs(first), abs(second), floor)


def _field_refinement(first: Any, second: Any) -> float:
    first_c = complex(first.C_r_W, first.C_i_W)
    second_c = complex(second.C_r_W, second.C_i_W)
    complex_error = abs(first_c - second_c) / max(abs(first_c), abs(second_c), POWER_FLOOR_W)
    return max(
        _relative(first.B_bg_W, second.B_bg_W),
        _relative(first.S_W, second.S_W),
        complex_error,
    )


def _panel_reference_states() -> tuple[SimulationState, ...]:
    rows = (
        ((8.0e-7, 5.5e-7, 90.0), (6.6e-7, 1.0e-6, 1.0, 0.0, 0.0), (1.33, 1.45)),
        ((6.0e-7, 3.0e-7, 90.0), (5.5e-7, 8.0e-7, 0.5, 0.0, 0.0), (1.33, 1.45)),
        ((9.0e-7, 5.5e-7, 85.0), (5.32e-7, 1.0e-6, 1.5, 2.0e-7, -1.0e-7), (1.34, 1.46)),
        ((1.2e-6, 7.0e-7, 88.0), (7.0e-7, 1.5e-6, 2.0, -3.0e-7, 2.0e-7), (1.32, 1.44)),
        ((1.6e-6, 9.0e-7, 90.0), (6.0e-7, 1.2e-6, 0.75, 4.0e-7, -2.0e-7), (1.35, 1.50)),
        ((7.0e-7, 2.5e-7, 82.0), (4.5e-7, 7.0e-7, 1.25, -1.0e-7, 1.0e-7), (1.31, 1.42)),
        ((2.0e-6, 1.2e-6, 87.0), (6.5e-7, 1.8e-6, 3.0, 5.0e-7, 4.0e-7), (1.39, 1.54)),
        ((1.0e-6, 4.0e-7, 80.0), (4.8e-7, 9.0e-7, 4.0, -2.5e-7, 3.0e-7), (1.36, 1.48)),
    )
    states = []
    for geometry, source, environment in rows:
        states.append(
            SimulationState(
                geometry=GeometryState(*geometry),
                source=SourceState(
                    wavelength_m=source[0],
                    waist_m=source[1],
                    incident_power_W=source[2],
                    beam_offset_longitudinal_m=source[3],
                    beam_offset_lateral_m=source[4],
                ),
                environment=EnvironmentState(*environment),
            )
        )
    return tuple(states)


def _panel_particles() -> tuple[ParticleState, ...]:
    return tuple(
        ParticleState(*row)
        for row in (
            (3.0e-8, 1.34, 0.0),
            (5.0e-8, 1.38, 0.0),
            (8.0e-8, 1.45, 0.0),
            (1.0e-7, 1.38, 0.0),
            (1.2e-7, 1.60, 0.01),
            (1.4e-7, 1.80, 0.05),
            (1.5e-7, 2.00, 0.20),
            (7.0e-8, 1.32, 0.02),
        )
    )


def _panel_positions_operators() -> tuple[tuple[PositionState, ObservationOperatorState], ...]:
    return (
        (PositionState(0.0, 0.0, 0.5), ObservationOperatorState()),
        (
            PositionState(4.0e-7, 0.0, 0.3),
            ObservationOperatorState(collection_na=0.70, analyzer_azimuth_rad=math.pi / 4.0),
        ),
        (
            PositionState(-4.0e-7, -0.5, 0.7),
            ObservationOperatorState(
                collection_na=0.95, analyzer_ellipticity_rad=math.pi / 8.0
            ),
        ),
        (
            PositionState(0.0, 0.5, 0.5),
            ObservationOperatorState(pupil_inner_radius=0.2, pupil_outer_radius=0.9),
        ),
        (
            PositionState(2.0e-7, -0.25, 0.2),
            ObservationOperatorState(
                detector_sector_center_rad=math.pi / 3.0,
                detector_sector_width_rad=math.pi,
            ),
        ),
        (
            PositionState(-2.0e-7, 0.25, 0.8),
            ObservationOperatorState(
                analyzer_azimuth_rad=math.pi / 3.0,
                analyzer_ellipticity_rad=-math.pi / 8.0,
                detector_sector_center_rad=5.0 * math.pi / 4.0,
                detector_sector_width_rad=math.pi / 2.0,
            ),
        ),
    )


def _panel_states() -> tuple[SimulationState, ...]:
    states = []
    for reference in _panel_reference_states():
        for particle in _panel_particles():
            for position, operator in _panel_positions_operators():
                states.append(
                    replace(
                        reference,
                        particle=particle,
                        position=position,
                        observation=operator,
                    )
                )
    if len(states) != 384 or len({state.state_id for state in states}) != 384:
        raise RuntimeError("qualification panel identity is not exactly 384 unique states")
    return tuple(states)


def _direct_parity() -> dict[str, Any]:
    golden_path = ROOT / "tests/golden/m1_baseline_v1.json"
    upstream = json.loads(golden_path.read_text(encoding="utf-8"))
    result = simulate_state(SimulationState())
    fields = {
        "B_bg_W": (result.B_bg_W, float(upstream["B_bg_W"])),
        "S_W": (result.S_W, float(upstream["S_W"])),
        "C_r_W": (result.C_r_W, float(upstream["C_r_W"])),
        "C_i_W": (result.C_i_W, float(upstream["C_i_W"])),
        "Y_0_W": (result.Y_0_W, float(upstream["Y_0_W"])),
        "eta_real": (float(result.eta_real), float(upstream["eta_real"])),
        "eta_imag": (float(result.eta_imag), float(upstream["eta_imag"])),
    }
    rows = {
        name: {
            "foundation": values[0],
            "paper1": values[1],
            "relative_error": _relative(values[0], values[1], 1.0e-10),
        }
        for name, values in fields.items()
    }
    phase_error = abs(float(result.C_phase_rad) - float(upstream["C_phase_rad"]))
    passed = all(row["relative_error"] <= PANEL_TOLERANCE for row in rows.values())
    passed = passed and phase_error <= PANEL_TOLERANCE
    return {
        "scope": "FROZEN_CANONICAL_SHARED_STATE_ONLY_NOT_DOMAIN_VALIDATION",
        "paper1_golden_path": str(golden_path.relative_to(ROOT)).replace("\\", "/"),
        "paper1_golden_sha256": _sha256(golden_path),
        "tolerance": PANEL_TOLERANCE,
        "quantities": rows,
        "phase_absolute_error_rad": phase_error,
        "status": "PASS" if passed else "FAIL",
    }


def _invariants() -> dict[str, Any]:
    base = SimulationState()
    zero = simulate_state(
        replace(
            base,
            particle=replace(
                base.particle,
                refractive_index_real=base.environment.fill_refractive_index,
                refractive_index_imag=0.0,
            ),
        )
    )
    doubled = simulate_state(replace(base, source=replace(base.source, incident_power_W=2.0)))
    first = simulate_state(base)
    power_error = max(
        _relative(getattr(doubled, name), 2.0 * getattr(first, name))
        for name in ("B_bg_W", "S_W", "C_r_W", "C_i_W")
    )
    annular = simulate_state(
        replace(
            base,
            observation=replace(base.observation, pupil_inner_radius=0.25, pupil_outer_radius=0.9),
        )
    )
    left = simulate_state(replace(base, position=replace(base.position, lateral_fraction=-0.4)))
    right = simulate_state(replace(base, position=replace(base.position, lateral_fraction=0.4)))
    symmetry_error = max(_relative(left.B_bg_W, right.B_bg_W), _relative(left.S_W, right.S_W))
    before = evaluate_formal_m1(base)
    clear_formal_caches()
    after = evaluate_formal_m1(base)
    cache_identity = before == after
    checks = {
        "zero_contrast": {
            "status": "PASS" if zero.S_W <= 1.0e-24 and zero.C_r_W == zero.C_i_W == 0.0 else "FAIL",
            "S_W": zero.S_W,
        },
        "absolute_power_homogeneity": {
            "status": "PASS" if power_error <= 2.0e-12 else "FAIL",
            "maximum_relative_error": power_error,
        },
        "annular_support_monotonicity": {
            "status": "PASS"
            if annular.B_bg_W <= first.B_bg_W and annular.S_W <= first.S_W
            else "FAIL",
            "B_ratio": annular.B_bg_W / first.B_bg_W,
            "S_ratio": annular.S_W / first.S_W,
        },
        "symmetric_position_power": {
            "status": "PASS" if symmetry_error <= 2.0e-12 else "FAIL",
            "maximum_relative_error": symmetry_error,
        },
        "cache_on_off_identity": {"status": "PASS" if cache_identity else "FAIL"},
    }
    return {
        "checks": checks,
        "status": "PASS" if all(row["status"] == "PASS" for row in checks.values()) else "FAIL",
    }


def _qualification_panel() -> dict[str, Any]:
    clear_formal_caches()
    rows = []
    maximum_refinement = 0.0
    maximum_cauchy_excess = 0.0
    fast_discrepancies: dict[str, list[float]] = {
        name: [] for name in ("B_bg_W", "S_W", "C_r_W", "C_i_W")
    }
    block_sets: dict[str, set[str]] = {
        name: set() for name in ("reference", "particle", "position", "operator")
    }
    numerical_receipts: set[str] = set()
    for index, state in enumerate(_panel_states()):
        coarse = evaluate_formal_m1(state, pupil_order=(8, 16))
        middle = evaluate_formal_m1(state, pupil_order=(12, 24))
        final = evaluate_formal_m1(state, pupil_order=(16, 32))
        refinement = _field_refinement(middle, final)
        coarse_to_final = _field_refinement(coarse, final)
        cauchy_excess = max(
            0.0,
            final.C_r_W**2 + final.C_i_W**2 - final.B_bg_W * final.S_W,
        )
        fast = simulate_state(replace(state, physics_profile_id=FAST_CONTROL_PROFILE))
        for name in fast_discrepancies:
            value = _relative(getattr(final, name), getattr(fast, name))
            fast_discrepancies[name].append(value)
        maximum_refinement = max(maximum_refinement, refinement)
        maximum_cauchy_excess = max(maximum_cauchy_excess, cauchy_excess)
        block_sets["reference"].add(final.reference_block_id)
        block_sets["particle"].add(final.particle_block_id)
        block_sets["position"].add(final.position_block_id)
        block_sets["operator"].add(final.operator_block_id)
        numerical_receipts.update(final.numerical_receipt_ids)
        status = (
            "PASS"
            if refinement <= PANEL_TOLERANCE
            and final.B_bg_W >= 0.0
            and final.S_W >= 0.0
            and cauchy_excess <= 1.0e-24
            else "FAIL"
        )
        rows.append(
            {
                "case_id": f"Q{index:03d}",
                "state_id": state.state_id,
                "status": status,
                "refinement_middle_to_final": refinement,
                "refinement_coarse_to_final": coarse_to_final,
                "cauchy_excess_W2": cauchy_excess,
                "formal": {
                    "B_bg_W": final.B_bg_W,
                    "S_W": final.S_W,
                    "C_r_W": final.C_r_W,
                    "C_i_W": final.C_i_W,
                },
            }
        )
    discrepancy_summary = {
        name: {
            "median": sorted(values)[len(values) // 2],
            "maximum": max(values),
        }
        for name, values in fast_discrepancies.items()
    }
    return {
        "panel_id": "FORMAL_M1_V2_QUALIFICATION_PANEL",
        "design": "8_REFERENCE_X_8_PARTICLE_X_6_POSITION_OPERATOR_PREDECLARED",
        "state_count": len(rows),
        "case_tolerance": PANEL_TOLERANCE,
        "maximum_middle_to_final_refinement": maximum_refinement,
        "maximum_cauchy_excess_W2": maximum_cauchy_excess,
        "fast_control_discrepancy_is_characterization_not_parity": discrepancy_summary,
        "unique_block_counts": {name: len(values) for name, values in block_sets.items()},
        "numerical_receipt_count": len(numerical_receipts),
        "numerical_receipt_set_sha256": canonical_sha256(sorted(numerical_receipts)),
        "case_results": rows,
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
    }


def _pilot_reference_states() -> tuple[SimulationState, ...]:
    geometries = (
        GeometryState(6.0e-7, 3.0e-7, 90.0),
        GeometryState(8.0e-7, 5.5e-7, 90.0),
        GeometryState(1.2e-6, 7.0e-7, 86.0),
        GeometryState(1.8e-6, 1.0e-6, 88.0),
    )
    sources = (
        SourceState(wavelength_m=4.8e-7, waist_m=7.0e-7, incident_power_W=0.5),
        SourceState(wavelength_m=5.5e-7, waist_m=9.0e-7, incident_power_W=1.0),
        SourceState(wavelength_m=6.6e-7, waist_m=1.2e-6, incident_power_W=2.0),
        SourceState(wavelength_m=7.0e-7, waist_m=1.8e-6, incident_power_W=4.0),
    )
    environments = (
        EnvironmentState(1.30, 1.40),
        EnvironmentState(1.33, 1.45),
        EnvironmentState(1.36, 1.50),
        EnvironmentState(1.39, 1.54),
    )
    return tuple(
        SimulationState(geometry=geometry, source=source, environment=environment)
        for geometry in geometries
        for source in sources
        for environment in environments
    )


def _pilot_states() -> tuple[SimulationState, ...]:
    particles = (
        ParticleState(4.0e-8, 1.34, 0.0),
        ParticleState(8.0e-8, 1.38, 0.0),
        ParticleState(1.0e-7, 1.55, 0.01),
        ParticleState(1.2e-7, 1.80, 0.05),
    )
    positions = (
        PositionState(0.0, 0.0, 0.5),
        PositionState(2.0e-7, -0.5, 0.3),
        PositionState(-2.0e-7, 0.5, 0.7),
        PositionState(4.0e-7, 0.0, 0.8),
    )
    operators = (
        ObservationOperatorState(),
        ObservationOperatorState(analyzer_azimuth_rad=math.pi / 4.0),
        ObservationOperatorState(analyzer_ellipticity_rad=math.pi / 8.0),
        ObservationOperatorState(
            analyzer_azimuth_rad=math.pi / 3.0,
            analyzer_ellipticity_rad=-math.pi / 8.0,
        ),
    )
    states = tuple(
        replace(reference, particle=particle, position=position, observation=operator)
        for reference in _pilot_reference_states()
        for particle in particles
        for position in positions
        for operator in operators
    )
    if len(states) != 4096 or len({state.state_id for state in states}) != 4096:
        raise RuntimeError("performance pilot identity is not exactly 4096 unique states")
    return states


def _profile_rows(profile: cProfile.Profile) -> dict[str, dict[str, float | int]]:
    stats = pstats.Stats(profile)
    wanted = {"_reference_scalar", "_mie_solution", "_fields", "_evaluate_formal_cached"}
    rows: dict[str, dict[str, float | int]] = {}
    for (_, _, function), values in stats.stats.items():
        if function in wanted:
            primitive_calls, total_calls, own_seconds, cumulative_seconds, _callers = values
            rows[function] = {
                "primitive_calls": primitive_calls,
                "total_calls": total_calls,
                "own_seconds": own_seconds,
                "inclusive_seconds": cumulative_seconds,
            }
    return rows


def _performance_pilot() -> dict[str, Any]:
    states = _pilot_states()
    resource = assert_resource_budget(1)
    clear_formal_caches()
    stop = threading.Event()
    samples: list[int] = []

    def monitor() -> None:
        while not stop.wait(0.05):
            value = system_committed_memory_bytes()
            if value is not None:
                samples.append(value)

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    profile = cProfile.Profile()
    started = monotonic()
    profile.enable()
    results = [simulate_state(state) for state in states]
    profile.disable()
    cold_seconds = monotonic() - started
    stop.set()
    watcher.join()
    cold_stats = formal_cache_stats()
    warm_started = monotonic()
    warm_hashes = [simulate_state(state).result_hash for state in states]
    warm_seconds = monotonic() - warm_started
    if warm_hashes != [result.result_hash for result in results]:
        raise RuntimeError("warm-cache pilot changed result identity or order")
    warm_stats = formal_cache_stats()
    block_counts = {
        name: len({getattr(result, name) for result in results})
        for name in (
            "reference_block_id",
            "particle_block_id",
            "position_block_id",
            "operator_block_id",
        )
    }
    peak_commit = max(samples) if samples else system_committed_memory_bytes()
    estimated = {
        str(count): cold_seconds * count / len(states)
        for count in (32768, 524288, 65536)
    }
    cache_expectations = (
        cold_stats["reference"]["misses"] == 64
        and cold_stats["position_field"]["misses"] == 1024
        and cold_stats["position_field"]["hits"] == 3072
        and warm_stats["operator_summary"]["hits"] == 4096
    )
    return {
        "pilot_id": "FORMAL_M1_V2_NESTED_PERFORMANCE_PILOT",
        "design": "64_REFERENCE_X_4_PARTICLE_X_4_POSITION_X_4_ANALYZER_OPERATOR",
        "state_count": len(states),
        "selected_workers": 1,
        "selected_chunk_size": 1024,
        "cache_persistence": "IN_PROCESS_CONTENT_ADDRESSED_LRU_PLUS_OPTIONAL_PUBLIC_BATCH_CACHE",
        "cold_profiled_seconds": cold_seconds,
        "warm_operator_summary_seconds": warm_seconds,
        "cold_amortized_state_seconds": cold_seconds / len(states),
        "warm_amortized_state_seconds": warm_seconds / len(states),
        "cold_cache_stats": cold_stats,
        "warm_cache_stats": warm_stats,
        "inclusive_layer_profile": _profile_rows(profile),
        "unique_block_counts": block_counts,
        "system_committed_memory_before_bytes": resource.committed_memory_bytes,
        "system_committed_memory_peak_bytes": peak_commit,
        "committed_memory_limit_bytes": COMMITTED_MEMORY_LIMIT_BYTES,
        "linear_runtime_estimate_seconds": estimated,
        "timing_note": "CPROFILE_COLD_TIMING_IS_CONSERVATIVE_AND_INCLUDES_PUBLIC_RESULT_HASHING",
        "status": "PASS" if cache_expectations else "FAIL",
    }


def build_report() -> dict[str, Any]:
    paper1_lock = _verify_paper1_source_lock()
    direct = _direct_parity()
    invariants = _invariants()
    panel = _qualification_panel()
    if any(item["status"] != "PASS" for item in (direct, invariants, panel)):
        raise RuntimeError("formal qualification failed before performance pilot")
    pilot = _performance_pilot()
    capability = capabilities()
    overall = "PASS_WITH_LIMITS" if pilot["status"] == "PASS" else "FAIL"
    report: dict[str, Any] = {
        "report_schema_version": 1,
        "report_id": "FORMAL_M1_V2_QUALIFICATION_REPORT",
        "overall_disposition": overall,
        "physics_profile_id": "FORMAL_FIELD_COUPLING_M1_V2",
        "engine_schema_feature_versions": ["2.0.0", "2.0", "2.0"],
        "foundation_source_commit": _git_head(ROOT),
        "physics_implementation_sha256": _source_sha256(
            ROOT / "src/nodi_foundation/_physics/formal_m1.py"
        ),
        "numerical_profile_sha256": CONFIG_HASH,
        "feature_catalogue_hash": capability.catalogue_hash,
        "paper1_source_lock": paper1_lock,
        "direct_parity": direct,
        "formal_extension_invariants": invariants,
        "qualification_panel": panel,
        "performance_pilot": pilot,
        "per_feature_status": [
            {
                "id": row["id"],
                "status": row["profile_status"]["FORMAL_FIELD_COUPLING_M1_V2"],
                "formal_domain": row.get("formal_domain", row["domain"]),
            }
            for row in capability.features
        ],
        "deferred_or_unsupported": [
            "CORE_SHELL_PARTICLE",
            "COLLECTION_NA_GREATER_THAN_OR_EQUAL_TO_ONE",
            "FULL_MAXWELL_OR_COMSOL_RUNTIME",
            "MULTIPLE_SCATTERING_OR_PARTICLE_BACKACTION",
            "EVENT_TIME_NOISE_LOCKIN_OR_READOUT",
        ],
        "paper2_final_data_generation_eligible": overall == "PASS_WITH_LIMITS",
        "claim_ceiling": "FIRST_ORDER_FORMAL_FIELD_COUPLING_M1_WITH_DECLARED_LIMITS",
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "formal_m1_v2_qualification_report.json",
    )
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(report["overall_disposition"])
    print(_sha256(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
