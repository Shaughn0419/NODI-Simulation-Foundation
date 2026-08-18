"""Immutable public input and result models with canonical identities."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .errors import (
    E_DOMAIN_INVALID,
    E_NUMERICAL_NONFINITE,
    E_SCHEMA_INCOMPATIBLE,
    FoundationError,
)

SCHEMA_VERSION = "4.0"
ENGINE_VERSION = "4.0.0"
FEATURE_VERSION = "4.0"

BOTTOM_WIDTH_RELATIVE_TOLERANCE = 1.0e-12


def canonical_json(value: object) -> str:
    """Serialize a JSON-compatible value without NaN or representation drift."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FoundationError(E_NUMERICAL_NONFINITE, "value is not canonical JSON") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FoundationError(E_DOMAIN_INVALID, f"{name} must be a finite number")


def _closed(name: str, value: float, lower: float, upper: float) -> None:
    _finite(name, value)
    if not lower <= value <= upper:
        raise FoundationError(E_DOMAIN_INVALID, f"{name} must be in [{lower}, {upper}]")


def _canonical_periodic(name: str, value: float, period: float) -> float:
    """Validate one period and canonicalize its duplicated upper endpoint."""

    _finite(name, value)
    if not 0.0 <= value <= period:
        raise FoundationError(E_DOMAIN_INVALID, f"{name} must be in [0, {period})")
    return 0.0 if value == period or value == 0.0 else value


def raw_bottom_width(width_m: float, depth_m: float, sidewall_angle_deg: float) -> float:
    """Return the signed ideal trapezoid bottom width without clipping."""

    if sidewall_angle_deg == 90.0:
        return width_m
    return width_m - 2.0 * depth_m / math.tan(math.radians(sidewall_angle_deg))


def dry_etch_bottom_width(width_m: float, depth_m: float, sidewall_angle_deg: float) -> float:
    """Return the nonnegative dry-etch bottom width, canonicalizing roundoff only."""

    removal = 0.0
    if sidewall_angle_deg != 90.0:
        removal = 2.0 * depth_m / math.tan(math.radians(sidewall_angle_deg))
    raw = width_m - removal
    tolerance = BOTTOM_WIDTH_RELATIVE_TOLERANCE * max(width_m, removal, 1.0e-9)
    if raw < -tolerance:
        raise FoundationError(E_DOMAIN_INVALID, "dry-etch sidewalls produce negative bottom width")
    return 0.0 if raw <= tolerance else raw


@dataclass(frozen=True, slots=True)
class GeometryState:
    width_m: float = 8.0e-7
    depth_m: float = 5.5e-7
    sidewall_angle_deg: float = 90.0

    def __post_init__(self) -> None:
        _closed("width_m", self.width_m, 2.0e-7, 2.0e-6)
        _closed("depth_m", self.depth_m, 2.0e-7, 2.0e-6)
        _closed("sidewall_angle_deg", self.sidewall_angle_deg, 70.0, 90.0)


@dataclass(frozen=True, slots=True)
class ParticleState:
    diameter_m: float = 1.0e-7
    refractive_index_real: float = 1.38
    refractive_index_imag: float = 0.0

    def __post_init__(self) -> None:
        _closed("diameter_m", self.diameter_m, 2.0e-8, 2.0e-7)
        _closed("refractive_index_real", self.refractive_index_real, 1.30, 2.00)
        _closed("refractive_index_imag", self.refractive_index_imag, 0.0, 0.20)


@dataclass(frozen=True, slots=True)
class PositionState:
    longitudinal_over_w0: float = 0.0
    lateral_fraction: float = 0.0
    depth_fraction: float = 0.5

    def __post_init__(self) -> None:
        _closed("longitudinal_over_w0", self.longitudinal_over_w0, -2.0, 2.0)
        _closed("lateral_fraction", self.lateral_fraction, -1.0, 1.0)
        _closed("depth_fraction", self.depth_fraction, 0.05, 0.95)


@dataclass(frozen=True, slots=True)
class SourceState:
    wavelength_m: float = 6.6e-7
    waist_m: float = 1.0e-6
    normalization_power_W: float = 1.0
    beam_offset_longitudinal_over_w0: float = 0.0
    beam_offset_lateral_over_w0: float = 0.0
    polarization_azimuth_rad: float = 0.0
    ellipticity_rad: float = 0.0
    degree_of_polarization: float = 0.0

    def __post_init__(self) -> None:
        _closed("wavelength_m", self.wavelength_m, 4.0e-7, 9.0e-7)
        _closed("waist_m", self.waist_m, 5.0e-7, 2.0e-6)
        _closed("normalization_power_W", self.normalization_power_W, 0.25, 4.0)
        _closed(
            "beam_offset_longitudinal_over_w0",
            self.beam_offset_longitudinal_over_w0,
            -1.5,
            1.5,
        )
        _closed(
            "beam_offset_lateral_over_w0",
            self.beam_offset_lateral_over_w0,
            -1.5,
            1.5,
        )
        azimuth = _canonical_periodic(
            "polarization_azimuth_rad", self.polarization_azimuth_rad, math.pi
        )
        _closed("ellipticity_rad", self.ellipticity_rad, -math.pi / 4.0, math.pi / 4.0)
        _closed("degree_of_polarization", self.degree_of_polarization, 0.0, 1.0)
        ellipticity = 0.0 if self.ellipticity_rad == 0.0 else self.ellipticity_rad
        if self.degree_of_polarization == 0.0:
            azimuth = 0.0
            ellipticity = 0.0
        elif abs(ellipticity) == math.pi / 4.0:
            azimuth = 0.0
        object.__setattr__(self, "polarization_azimuth_rad", azimuth)
        object.__setattr__(self, "ellipticity_rad", ellipticity)

    @property
    def beam_offset_longitudinal_m(self) -> float:
        return self.beam_offset_longitudinal_over_w0 * self.waist_m

    @property
    def beam_offset_lateral_m(self) -> float:
        return self.beam_offset_lateral_over_w0 * self.waist_m


@dataclass(frozen=True, slots=True)
class EnvironmentState:
    fill_refractive_index: float = 1.33
    wall_refractive_index: float = 1.45
    effective_wall_exclusion_m: float = 5.0e-9

    def __post_init__(self) -> None:
        _closed("fill_refractive_index", self.fill_refractive_index, 1.30, 1.40)
        _closed("wall_refractive_index", self.wall_refractive_index, 1.40, 1.55)
        _closed("effective_wall_exclusion_m", self.effective_wall_exclusion_m, 0.0, 2.0e-8)


@dataclass(frozen=True, slots=True)
class ObservationOperatorState:
    collection_na: float = 0.90
    analyzer_azimuth_rad: float = 0.0
    analyzer_ellipticity_rad: float = 0.0
    pupil_inner_radius: float = 0.0
    pupil_outer_radius: float = 1.0
    detector_sector_center_rad: float = 0.0
    detector_sector_width_rad: float = 2.0 * math.pi

    def __post_init__(self) -> None:
        _closed("collection_na", self.collection_na, 0.40, 1.20)
        analyzer_azimuth = _canonical_periodic(
            "analyzer_azimuth_rad", self.analyzer_azimuth_rad, math.pi
        )
        _closed(
            "analyzer_ellipticity_rad",
            self.analyzer_ellipticity_rad,
            -math.pi / 4.0,
            math.pi / 4.0,
        )
        _closed("pupil_inner_radius", self.pupil_inner_radius, 0.0, 0.75)
        _closed("pupil_outer_radius", self.pupil_outer_radius, 0.85, 1.0)
        if self.pupil_outer_radius < self.pupil_inner_radius + 0.1:
            raise FoundationError(E_DOMAIN_INVALID, "pupil outer radius must exceed inner by 0.1")
        sector_center = _canonical_periodic(
            "detector_sector_center_rad",
            self.detector_sector_center_rad,
            2.0 * math.pi,
        )
        _closed(
            "detector_sector_width_rad",
            self.detector_sector_width_rad,
            math.pi / 6.0,
            2.0 * math.pi,
        )
        analyzer_ellipticity = (
            0.0 if self.analyzer_ellipticity_rad == 0.0 else self.analyzer_ellipticity_rad
        )
        if abs(analyzer_ellipticity) == math.pi / 4.0:
            analyzer_azimuth = 0.0
        if self.detector_sector_width_rad == 2.0 * math.pi:
            sector_center = 0.0
        object.__setattr__(self, "analyzer_azimuth_rad", analyzer_azimuth)
        object.__setattr__(self, "analyzer_ellipticity_rad", analyzer_ellipticity)
        object.__setattr__(self, "detector_sector_center_rad", sector_center)


@dataclass(frozen=True, slots=True)
class SimulationState:
    geometry: GeometryState = GeometryState()
    particle: ParticleState = ParticleState()
    position: PositionState = PositionState()
    source: SourceState = SourceState()
    environment: EnvironmentState = EnvironmentState()
    observation: ObservationOperatorState = ObservationOperatorState()
    physics_profile_id: str = "FORMAL_FIELD_COUPLING_M1_V4_DRY_ETCH"

    def __post_init__(self) -> None:
        from .profiles import (
            FAST_CONTROL_DOMAIN,
            FAST_CONTROL_PROFILE,
            FORMAL_DOMAIN,
            SUPPORTED_PROFILES,
        )

        if self.physics_profile_id not in SUPPORTED_PROFILES:
            raise FoundationError(
                E_DOMAIN_INVALID, f"unsupported physics profile {self.physics_profile_id!r}"
            )
        domain = (
            FAST_CONTROL_DOMAIN
            if self.physics_profile_id == FAST_CONTROL_PROFILE
            else FORMAL_DOMAIN
        )
        for name, value in (
            ("width_m", self.geometry.width_m),
            ("depth_m", self.geometry.depth_m),
            ("sidewall_angle_deg", self.geometry.sidewall_angle_deg),
            ("diameter_m", self.particle.diameter_m),
            ("wavelength_m", self.source.wavelength_m),
        ):
            lower, upper = domain[name]
            _closed(name, value, lower, upper)
        if self.physics_profile_id == FAST_CONTROL_PROFILE:
            bottom = raw_bottom_width(
                self.geometry.width_m,
                self.geometry.depth_m,
                self.geometry.sidewall_angle_deg,
            )
            if bottom <= 0.0:
                raise FoundationError(
                    E_DOMAIN_INVALID, "scaling-control geometry requires positive bottom width"
                )
        else:
            bottom = dry_etch_bottom_width(
                self.geometry.width_m,
                self.geometry.depth_m,
                self.geometry.sidewall_angle_deg,
            )
            if self.source.waist_m < self.source.wavelength_m:
                raise FoundationError(
                    E_DOMAIN_INVALID,
                    "formal dry-etch profile requires beam waist at least one wavelength",
                )
        radius = 0.5 * self.particle.diameter_m
        effective_radius = radius + self.environment.effective_wall_exclusion_m
        if 2.0 * effective_radius >= self.geometry.depth_m:
            raise FoundationError(
                E_DOMAIN_INVALID, "particle plus effective clearance does not fit channel depth"
            )
        z = effective_radius + self.position.depth_fraction * (
            self.geometry.depth_m - 2.0 * effective_radius
        )
        local_width = bottom + (self.geometry.width_m - bottom) * (z / self.geometry.depth_m)
        if local_width <= 2.0 * effective_radius:
            raise FoundationError(
                E_DOMAIN_INVALID,
                "particle plus effective clearance does not fit local channel width",
            )
        if self.observation.collection_na >= self.environment.fill_refractive_index:
            raise FoundationError(
                E_DOMAIN_INVALID, "collection NA must be below the fill-medium refractive index"
            )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def state_id(self) -> str:
        return canonical_sha256(self.to_payload())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SimulationState:
        expected = {
            "geometry",
            "particle",
            "position",
            "source",
            "environment",
            "observation",
            "physics_profile_id",
        }
        unknown = set(value) - expected
        if unknown:
            raise FoundationError(
                E_DOMAIN_INVALID, f"unknown SimulationState fields: {sorted(unknown)}"
            )
        try:
            return cls(
                geometry=GeometryState(**dict(value.get("geometry", {}))),
                particle=ParticleState(**dict(value.get("particle", {}))),
                position=PositionState(**dict(value.get("position", {}))),
                source=SourceState(**dict(value.get("source", {}))),
                environment=EnvironmentState(**dict(value.get("environment", {}))),
                observation=ObservationOperatorState(**dict(value.get("observation", {}))),
                physics_profile_id=str(
                    value.get("physics_profile_id", "FORMAL_FIELD_COUPLING_M1_V4_DRY_ETCH")
                ),
            )
        except TypeError as exc:
            raise FoundationError(E_DOMAIN_INVALID, "invalid SimulationState structure") from exc


@dataclass(frozen=True, slots=True)
class StateResult:
    state_id: str
    inputs: dict[str, Any]
    physics_profile_id: str
    fidelity_class: str
    claim_ceiling: str
    reference_block_id: str
    particle_block_id: str
    position_block_id: str
    operator_block_id: str
    numerical_receipt_ids: tuple[str, ...]
    B_bg_W: float
    S_W: float
    C_r_W: float
    C_i_W: float
    Y_0_W: float
    combined_total_W: float
    eta_real: float | None
    eta_imag: float | None
    eta_abs: float | None
    C_phase_rad: float | None
    numerical_status: str
    uncertainty: dict[str, Any]
    applicability_profile_id: str
    operator_qualification_status: str
    engine_version: str
    schema_version: str
    feature_version: str
    config_hash: str
    result_hash: str

    def payload_without_hash(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("result_hash")
        return payload

    def to_payload(self) -> dict[str, Any]:
        payload = self.payload_without_hash()
        if canonical_sha256(payload) != self.result_hash:
            raise FoundationError(E_SCHEMA_INCOMPATIBLE, "StateResult identity changed")
        return {**payload, "result_hash": self.result_hash}

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_payload())
