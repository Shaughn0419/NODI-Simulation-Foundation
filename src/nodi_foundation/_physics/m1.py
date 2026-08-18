"""Foundation-owned fast scaling control.

The control is calibrated to the frozen Paper 1 analytical M1 baseline and uses
declared closed-form scaling outside that point. It is not formal-field or
Paper 2 final-truth evidence.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from nodi_foundation.errors import E_NUMERICAL_NONFINITE, FoundationError
from nodi_foundation.models import SimulationState, canonical_sha256

BASE_B_BG_W = 0.20297283613317754
BASE_S_W = 3.1501989107668475e-7
BASE_ETA_REAL = -0.4593133792174526
BASE_ETA_IMAG = 0.29146640787414346
BASE_ETA_ABS = math.hypot(BASE_ETA_REAL, BASE_ETA_IMAG)
BASE_C_PHASE = math.atan2(BASE_ETA_IMAG, BASE_ETA_REAL)
LOW_FIELD_W = 1.0e-24

BASE_WIDTH_M = 8.0e-7
BASE_DEPTH_M = 5.5e-7
BASE_DIAMETER_M = 1.0e-7
BASE_PARTICLE_INDEX = complex(1.38, 0.0)
BASE_WAVELENGTH_M = 6.6e-7
BASE_WAIST_M = 1.0e-6
BASE_NORMALIZATION_POWER_W = 1.0
BASE_FILL_INDEX = 1.33
BASE_WALL_INDEX = 1.45
BASE_COLLECTION_NA = 0.90
CONFIG_HASH = canonical_sha256(
    {
        "engine": "FAST_SCALING_CONTROL_V1",
        "baseline_B_bg_W": BASE_B_BG_W,
        "baseline_S_W": BASE_S_W,
        "baseline_eta": [BASE_ETA_REAL, BASE_ETA_IMAG],
        "low_field_W": LOW_FIELD_W,
        "extension": "RAYLEIGH_GAUSSIAN_PHASE_OPERATOR_SCALING_V1",
    }
)


@dataclass(frozen=True, slots=True)
class ScalingControlPrimitives:
    B_bg_W: float
    S_W: float
    C_r_W: float
    C_i_W: float
    eta_real: float | None
    eta_imag: float | None
    eta_abs: float | None
    C_phase_rad: float | None
    operator_qualification_status: str
    reference_block_id: str
    particle_block_id: str
    position_block_id: str
    operator_block_id: str
    numerical_receipt_ids: tuple[str, ...]
    config_hash: str = CONFIG_HASH


def _bottom_width(state: SimulationState) -> float:
    geometry = state.geometry
    return geometry.width_m - 2.0 * geometry.depth_m / math.tan(
        math.radians(geometry.sidewall_angle_deg)
    )


def _particle_coordinates(state: SimulationState) -> tuple[float, float, float]:
    radius = 0.5 * state.particle.diameter_m
    effective_radius = radius + state.environment.effective_wall_exclusion_m
    bottom = _bottom_width(state)
    z = effective_radius + state.position.depth_fraction * (
        state.geometry.depth_m - 2.0 * effective_radius
    )
    width_at_z = bottom + (state.geometry.width_m - bottom) * (z / state.geometry.depth_m)
    lateral_support = 0.5 * width_at_z - effective_radius
    u = state.position.lateral_fraction * lateral_support
    return state.position.longitudinal_over_w0 * state.source.waist_m, u, z


def _reference_strength(
    width_m: float,
    depth_m: float,
    bottom_width_m: float,
    wavelength_m: float,
    waist_m: float,
    fill_index: float,
    wall_index: float,
) -> float:
    average_width = 0.5 * (width_m + bottom_width_m)
    transverse = math.erf(average_width / (math.sqrt(2.0) * waist_m)) ** 2
    phase = 2.0 * math.pi * (fill_index - wall_index) * depth_m / wavelength_m
    contrast = abs(cmath.exp(1j * phase) - 1.0) ** 2
    return transverse * contrast


def _rayleigh_strength(
    diameter_m: float,
    particle_index: complex,
    fill_index: float,
    wavelength_m: float,
) -> tuple[float, complex]:
    relative = particle_index / fill_index
    contrast = (relative * relative - 1.0) / (relative * relative + 2.0)
    medium_wavenumber = 2.0 * math.pi * fill_index / wavelength_m
    radius = 0.5 * diameter_m
    strength = medium_wavenumber**4 * radius**6 * abs(contrast) ** 2
    return strength, contrast


def _operator_factor(state: SimulationState) -> tuple[float, str]:
    source = state.source
    operator = state.observation
    q = math.cos(2.0 * source.ellipticity_rad) * math.cos(2.0 * source.polarization_azimuth_rad)
    u = math.cos(2.0 * source.ellipticity_rad) * math.sin(2.0 * source.polarization_azimuth_rad)
    v = math.sin(2.0 * source.ellipticity_rad)
    aq = math.cos(2.0 * operator.analyzer_ellipticity_rad) * math.cos(
        2.0 * operator.analyzer_azimuth_rad
    )
    au = math.cos(2.0 * operator.analyzer_ellipticity_rad) * math.sin(
        2.0 * operator.analyzer_azimuth_rad
    )
    av = math.sin(2.0 * operator.analyzer_ellipticity_rad)
    polarization = 1.0 + source.degree_of_polarization * (q * aq + u * au + v * av)
    annulus = operator.pupil_outer_radius**2 - operator.pupil_inner_radius**2
    sector = operator.detector_sector_width_rad / (2.0 * math.pi)
    factor = max(0.0, polarization) * annulus * sector
    baseline_operator = (
        operator.pupil_inner_radius == 0.0
        and operator.pupil_outer_radius == 1.0
        and operator.detector_sector_width_rad == 2.0 * math.pi
        and source.degree_of_polarization == 0.0
    )
    status = "QUALIFIED_CANONICAL_FULL_PUPIL" if baseline_operator else "SUPPORTED_WITH_LIMITS"
    return factor, status


def _control_ids(state: SimulationState) -> tuple[str, str, str, str, tuple[str, ...]]:
    payload = state.to_payload()
    reference = canonical_sha256(
        {
            "control": "REFERENCE_SCALING",
            "geometry": payload["geometry"],
            "source": payload["source"],
        }
    )
    particle = canonical_sha256(
        {
            "control": "RAYLEIGH_SCALING",
            "particle": payload["particle"],
            "environment": payload["environment"],
        }
    )
    position = canonical_sha256(
        {
            "control": "POSITION_SCALING",
            "position": payload["position"],
            "geometry": payload["geometry"],
        }
    )
    operator = canonical_sha256(
        {"control": "OPERATOR_SCALING", "observation": payload["observation"]}
    )
    return reference, particle, position, operator, (CONFIG_HASH,)


def evaluate_scaling_control(state: SimulationState) -> ScalingControlPrimitives:
    """Evaluate the explicitly selected fast scaling control."""

    source = state.source
    environment = state.environment
    operator = state.observation
    bottom = _bottom_width(state)
    reference = _reference_strength(
        state.geometry.width_m,
        state.geometry.depth_m,
        bottom,
        source.wavelength_m,
        source.waist_m,
        environment.fill_refractive_index,
        environment.wall_refractive_index,
    )
    base_reference = _reference_strength(
        BASE_WIDTH_M,
        BASE_DEPTH_M,
        BASE_WIDTH_M,
        BASE_WAVELENGTH_M,
        BASE_WAIST_M,
        BASE_FILL_INDEX,
        BASE_WALL_INDEX,
    )
    operator_factor, _qualification = _operator_factor(state)
    identifiers = _control_ids(state)
    collection_relative = (operator.collection_na / BASE_COLLECTION_NA) ** 2
    beam_reference_overlap = math.exp(
        -2.0
        * (source.beam_offset_longitudinal_m**2 + source.beam_offset_lateral_m**2)
        / source.waist_m**2
    )
    B_bg_W = (
        BASE_B_BG_W
        * (source.normalization_power_W / BASE_NORMALIZATION_POWER_W)
        * (reference / base_reference)
        * collection_relative
        * operator_factor
        * beam_reference_overlap
    )

    s, u, z = _particle_coordinates(state)
    ds = s - source.beam_offset_longitudinal_m
    du = u - source.beam_offset_lateral_m
    gaussian_power = math.exp(-2.0 * (ds * ds + du * du) / source.waist_m**2)
    particle_index = complex(
        state.particle.refractive_index_real,
        state.particle.refractive_index_imag,
    )
    rayleigh, polarizability = _rayleigh_strength(
        state.particle.diameter_m,
        particle_index,
        environment.fill_refractive_index,
        source.wavelength_m,
    )
    base_rayleigh, base_polarizability = _rayleigh_strength(
        BASE_DIAMETER_M,
        BASE_PARTICLE_INDEX,
        BASE_FILL_INDEX,
        BASE_WAVELENGTH_M,
    )
    S_W = (
        BASE_S_W
        * (source.normalization_power_W / BASE_NORMALIZATION_POWER_W)
        * (BASE_WAIST_M / source.waist_m) ** 2
        * (rayleigh / base_rayleigh)
        * gaussian_power
        * collection_relative
        * operator_factor
    )

    if B_bg_W <= LOW_FIELD_W or S_W <= LOW_FIELD_W:
        return ScalingControlPrimitives(
            B_bg_W=max(B_bg_W, 0.0),
            S_W=max(S_W, 0.0),
            C_r_W=0.0,
            C_i_W=0.0,
            eta_real=None,
            eta_imag=None,
            eta_abs=None,
            C_phase_rad=None,
            operator_qualification_status="SCALING_CONTROL_ONLY",
            reference_block_id=identifiers[0],
            particle_block_id=identifiers[1],
            position_block_id=identifiers[2],
            operator_block_id=identifiers[3],
            numerical_receipt_ids=identifiers[4],
        )

    average_width = 0.5 * (state.geometry.width_m + bottom)
    geometry_overlap = math.sqrt(
        min(average_width / BASE_WIDTH_M, 1.0) * min(state.geometry.depth_m / BASE_DEPTH_M, 1.0)
    )
    spatial_overlap = math.exp(-0.5 * (ds * ds + du * du) / source.waist_m**2)
    eta_abs = min(BASE_ETA_ABS * geometry_overlap * spatial_overlap, 1.0)
    base_channel_phase = (
        2.0 * math.pi * (BASE_FILL_INDEX - BASE_WALL_INDEX) * BASE_DEPTH_M / BASE_WAVELENGTH_M
    )
    channel_phase = (
        2.0
        * math.pi
        * (environment.fill_refractive_index - environment.wall_refractive_index)
        * state.geometry.depth_m
        / source.wavelength_m
    )
    position_phase = (
        2.0
        * math.pi
        * environment.fill_refractive_index
        * (z - 0.5 * state.geometry.depth_m)
        / source.wavelength_m
    )
    polarizability_phase = cmath.phase(polarizability) - cmath.phase(base_polarizability)
    phase = BASE_C_PHASE + (channel_phase - base_channel_phase) + position_phase
    sector_fraction_missing = 1.0 - operator.detector_sector_width_rad / (2.0 * math.pi)
    sector_phase = operator.detector_sector_center_rad * sector_fraction_missing
    phase += polarizability_phase + sector_phase
    eta = eta_abs * cmath.exp(1j * phase)
    cross = eta * math.sqrt(B_bg_W * S_W)
    values = (B_bg_W, S_W, cross.real, cross.imag, eta.real, eta.imag, eta_abs, phase)
    if not all(math.isfinite(value) for value in values):
        raise FoundationError(E_NUMERICAL_NONFINITE, "analytical M1 produced a nonfinite value")
    return ScalingControlPrimitives(
        B_bg_W=B_bg_W,
        S_W=S_W,
        C_r_W=cross.real,
        C_i_W=cross.imag,
        eta_real=eta.real,
        eta_imag=eta.imag,
        eta_abs=eta_abs,
        C_phase_rad=math.atan2(cross.imag, cross.real),
        operator_qualification_status="SCALING_CONTROL_ONLY",
        reference_block_id=identifiers[0],
        particle_block_id=identifiers[1],
        position_block_id=identifiers[2],
        operator_block_id=identifiers[3],
        numerical_receipt_ids=identifiers[4],
    )
