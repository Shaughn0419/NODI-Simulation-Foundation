"""Standalone first-order formal field-coupling M1 engine.

This module evaluates a finite trapezoid replacement-phase reference field and
a background-excited homogeneous-sphere Mie increment in one vector angular
pupil.  Both fields are consumed by the same positive observation operator.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy.constants import c, epsilon_0  # type: ignore[import-untyped]
from scipy.special import spherical_jn, spherical_yn  # type: ignore[import-untyped]

from nodi_foundation.errors import E_DOMAIN_INVALID, E_NUMERICAL_NONFINITE, FoundationError
from nodi_foundation.models import SimulationState, canonical_sha256

FloatArray = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]


def _configuration() -> tuple[dict[str, Any], str]:
    resource = files("nodi_foundation.data").joinpath("formal_m1_v2.json")
    raw = resource.read_bytes()
    document = json.loads(raw)
    return document, hashlib.sha256(raw).hexdigest()


CONFIG, CONFIG_HASH = _configuration()
NUMERICS = cast(dict[str, Any], CONFIG["numerics"])
LOW_FIELD_W = float(NUMERICS["low_field_W"])


@dataclass(frozen=True, slots=True)
class FormalPrimitives:
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


@dataclass(frozen=True, slots=True, eq=False)
class PupilGrid:
    rho: FloatArray
    theta: FloatArray
    phi: FloatArray
    weights_sr: FloatArray
    grid_id: str


@dataclass(frozen=True, slots=True)
class MieSolution:
    s1: ComplexArray
    s2: ComplexArray
    order: int
    receipt_id: str


def _freeze(array: NDArray[np.generic]) -> None:
    array.setflags(write=False)


@lru_cache(maxsize=256)
def _pupil_grid(
    collection_na: float,
    inner: float,
    outer: float,
    sector_center: float,
    sector_width: float,
    radial_order: int,
    azimuthal_order: int,
) -> PupilGrid:
    if collection_na >= 1.0:
        raise FoundationError(
            E_DOMAIN_INVALID,
            "formal M1 computational exit pupil requires collection_na < 1.0",
        )
    radial_nodes, radial_weights = np.polynomial.legendre.leggauss(radial_order)
    half_span = 0.5 * (outer - inner)
    rho_1d = inner + half_span * (radial_nodes + 1.0)
    rho_weights = half_span * radial_weights
    phi_1d = sector_center - 0.5 * sector_width + (
        np.arange(azimuthal_order, dtype=np.float64) + 0.5
    ) * (sector_width / azimuthal_order)
    rho, phi = np.meshgrid(rho_1d, phi_1d, indexing="ij")
    radial_weight, _ = np.meshgrid(rho_weights, phi_1d, indexing="ij")
    sine = collection_na * rho
    cosine = np.sqrt(1.0 - sine * sine)
    weights = (
        collection_na**2
        * rho
        / cosine
        * radial_weight
        * (sector_width / azimuthal_order)
    )
    flat_rho = np.asarray(rho.ravel(), dtype=np.float64)
    flat_theta = np.asarray(np.arcsin(sine).ravel(), dtype=np.float64)
    flat_phi = np.asarray(phi.ravel(), dtype=np.float64)
    flat_weights = np.asarray(weights.ravel(), dtype=np.float64)
    for item in (flat_rho, flat_theta, flat_phi, flat_weights):
        _freeze(item)
    grid_id = canonical_sha256(
        {
            "profile": "FORMAL_FIELD_COUPLING_M1_V2",
            "collection_na": collection_na,
            "inner": inner,
            "outer": outer,
            "sector_center": sector_center,
            "sector_width": sector_width,
            "radial_order": radial_order,
            "azimuthal_order": azimuthal_order,
        }
    )
    return PupilGrid(flat_rho, flat_theta, flat_phi, flat_weights, grid_id)


def _trapezoid_path(width: float, depth: float, angle_deg: float, u: FloatArray) -> FloatArray:
    if angle_deg == 90.0:
        return np.where(np.abs(u) <= 0.5 * width, depth, 0.0).astype(np.float64)
    tangent = math.tan(math.radians(angle_deg))
    top_half = 0.5 * width
    bottom_half = top_half - depth / tangent
    absolute = np.abs(u)
    path = np.where(
        absolute <= bottom_half,
        depth,
        np.where(absolute <= top_half, (top_half - absolute) * tangent, 0.0),
    )
    return np.asarray(path, dtype=np.float64)


@lru_cache(maxsize=1024)
def _reference_scalar(
    width: float,
    depth: float,
    angle_deg: float,
    wavelength: float,
    waist: float,
    power: float,
    offset_s: float,
    offset_u: float,
    fill_index: float,
    wall_index: float,
    grid: PupilGrid,
) -> ComplexArray:
    order = int(NUMERICS["reference_gauss_order_per_axis"])
    nodes, weights = np.polynomial.legendre.leggauss(order)
    half_length = 0.5 * float(CONFIG["physics"]["channel_length_waist_radii"]) * waist
    s = half_length * nodes
    ws = half_length * weights
    u = 0.5 * width * nodes
    wu = 0.5 * width * weights
    gaussian_s = np.exp(-((s - offset_s) / waist) ** 2)
    gaussian_u = np.exp(-((u - offset_u) / waist) ** 2)
    path = _trapezoid_path(width, depth, angle_deg, u)
    k0 = 2.0 * math.pi / wavelength
    phase_increment = np.exp(1j * k0 * (fill_index - wall_index) * path) - 1.0
    transverse = k0 * np.sin(grid.theta)
    q_s = transverse * np.cos(grid.phi)
    q_u = transverse * np.sin(grid.phi)
    fourier_s = (ws * gaussian_s) @ np.exp(-1j * np.outer(s, q_s))
    fourier_u = (wu * gaussian_u * phase_increment) @ np.exp(-1j * np.outer(u, q_u))
    peak_electric = math.sqrt(4.0 * power / (wall_index * epsilon_0 * c * math.pi * waist**2))
    common_phase = np.exp(1j * k0 * wall_index * depth / 2.0)
    k_exit = k0
    scale = (
        math.sqrt(wall_index * epsilon_0 * c / 2.0)
        * k_exit
        * np.sqrt(np.cos(grid.theta))
        / (2.0 * math.pi)
    )
    result = np.asarray(
        peak_electric * common_phase * fourier_s * fourier_u * scale,
        dtype=np.complex128,
    )
    if not np.all(np.isfinite(result)):
        raise FoundationError(E_NUMERICAL_NONFINITE, "formal reference field is nonfinite")
    _freeze(result)
    return result


def _riccati(order: int, value: complex) -> tuple[complex, complex, complex, complex]:
    jn = complex(spherical_jn(order, value))
    djn = complex(spherical_jn(order, value, derivative=True))
    yn = complex(spherical_yn(order, value))
    dyn = complex(spherical_yn(order, value, derivative=True))
    psi = value * jn
    dpsi = jn + value * djn
    xi = value * (jn + 1j * yn)
    dxi = jn + 1j * yn + value * (djn + 1j * dyn)
    return psi, dpsi, xi, dxi


def _mie_coefficients(size_parameter: float, relative_index: complex, order: int) -> ComplexArray:
    coefficients = np.empty((2, order), dtype=np.complex128)
    for offset, n in enumerate(range(1, order + 1)):
        psi_x, dpsi_x, xi_x, dxi_x = _riccati(n, complex(size_parameter))
        psi_mx, dpsi_mx, _, _ = _riccati(n, relative_index * size_parameter)
        denominator_a = relative_index * psi_mx * dxi_x - xi_x * dpsi_mx
        denominator_b = psi_mx * dxi_x - relative_index * xi_x * dpsi_mx
        if denominator_a == 0.0j or denominator_b == 0.0j:
            raise FoundationError(E_NUMERICAL_NONFINITE, "singular homogeneous Mie coefficient")
        coefficients[0, offset] = (
            relative_index * psi_mx * dpsi_x - psi_x * dpsi_mx
        ) / denominator_a
        coefficients[1, offset] = (
            psi_mx * dpsi_x - relative_index * psi_x * dpsi_mx
        ) / denominator_b
    return coefficients


def _mie_amplitudes(
    coefficients: ComplexArray, theta: FloatArray
) -> tuple[ComplexArray, ComplexArray]:
    mu = np.cos(theta)
    pi_nm2 = np.zeros_like(mu)
    pi_nm1 = np.ones_like(mu)
    s1 = np.zeros_like(theta, dtype=np.complex128)
    s2 = np.zeros_like(theta, dtype=np.complex128)
    for offset, n in enumerate(range(1, coefficients.shape[1] + 1)):
        pi_n = pi_nm1
        tau_n = n * mu * pi_n - (n + 1) * pi_nm2
        factor = (2 * n + 1) / (n * (n + 1))
        a_n, b_n = coefficients[:, offset]
        s1 += factor * (a_n * pi_n + b_n * tau_n)
        s2 += factor * (a_n * tau_n + b_n * pi_n)
        pi_next = ((2 * n + 1) * mu * pi_n - (n + 1) * pi_nm2) / n
        pi_nm2, pi_nm1 = pi_n, pi_next
    return s1, s2


@lru_cache(maxsize=2048)
def _mie_solution(
    diameter: float,
    particle_index_real: float,
    particle_index_imag: float,
    fill_index: float,
    wavelength: float,
    grid: PupilGrid,
) -> MieSolution:
    relative = complex(particle_index_real, particle_index_imag) / fill_index
    size = math.pi * diameter * fill_index / wavelength
    seed = max(3, int(math.floor(size + 4.0 * size ** (1.0 / 3.0) + 2.0)))
    step = int(NUMERICS["mie_order_step"])
    maximum = int(NUMERICS["mie_maximum_order"])
    relative_tolerance = float(NUMERICS["mie_relative_tolerance"])
    absolute_tolerance = float(NUMERICS["mie_absolute_tolerance"])
    passes_required = int(NUMERICS["mie_consecutive_passes"])
    previous: ComplexArray | None = None
    passes = 0
    final_s1: ComplexArray | None = None
    final_s2: ComplexArray | None = None
    final_order = seed
    for order in range(seed, maximum + 1, step):
        coefficients = _mie_coefficients(size, relative, order)
        s1, s2 = _mie_amplitudes(coefficients, grid.theta)
        current = np.concatenate((s1, s2))
        if previous is not None:
            absolute = float(np.max(np.abs(current - previous)))
            scale = float(np.max(np.abs(current)))
            relative_error = absolute / scale if scale > 0.0 else absolute
            passes = (
                passes + 1
                if absolute <= absolute_tolerance or relative_error <= relative_tolerance
                else 0
            )
        previous = current
        final_s1, final_s2, final_order = s1, s2, order
        if passes >= passes_required:
            break
    else:
        raise FoundationError(E_NUMERICAL_NONFINITE, "homogeneous Mie series did not converge")
    assert final_s1 is not None and final_s2 is not None
    final_s1 = np.asarray(final_s1, dtype=np.complex128)
    final_s2 = np.asarray(final_s2, dtype=np.complex128)
    _freeze(final_s1)
    _freeze(final_s2)
    receipt = canonical_sha256(
        {
            "kernel": "HOMOGENEOUS_COMPLEX_MIE_V2",
            "size_parameter": size,
            "relative_index": [relative.real, relative.imag],
            "final_order": final_order,
            "relative_tolerance": relative_tolerance,
            "absolute_tolerance": absolute_tolerance,
            "consecutive_passes": passes_required,
            "grid_id": grid.grid_id,
        }
    )
    return MieSolution(final_s1, final_s2, final_order, receipt)


def _particle_coordinates(state: SimulationState) -> tuple[float, float, float]:
    radius = 0.5 * state.particle.diameter_m
    geometry = state.geometry
    tangent = math.tan(math.radians(geometry.sidewall_angle_deg))
    bottom = geometry.width_m - 2.0 * geometry.depth_m / tangent
    z = radius + state.position.depth_fraction * (geometry.depth_m - 2.0 * radius)
    local_width = bottom + (geometry.width_m - bottom) * z / geometry.depth_m
    support = 0.5 * local_width - radius
    return state.position.longitudinal_m, state.position.lateral_fraction * support, z


def _source_covariance(state: SimulationState) -> ComplexArray:
    source = state.source
    q = source.degree_of_polarization * math.cos(2.0 * source.ellipticity_rad) * math.cos(
        2.0 * source.polarization_azimuth_rad
    )
    u = source.degree_of_polarization * math.cos(2.0 * source.ellipticity_rad) * math.sin(
        2.0 * source.polarization_azimuth_rad
    )
    v = source.degree_of_polarization * math.sin(2.0 * source.ellipticity_rad)
    return np.asarray([[1.0 + q, u - 1j * v], [u + 1j * v, 1.0 - q]]) * 0.5


def _analyzer_weight(state: SimulationState) -> ComplexArray:
    operator = state.observation
    q = math.cos(2.0 * operator.analyzer_ellipticity_rad) * math.cos(
        2.0 * operator.analyzer_azimuth_rad
    )
    u = math.cos(2.0 * operator.analyzer_ellipticity_rad) * math.sin(
        2.0 * operator.analyzer_azimuth_rad
    )
    v = math.sin(2.0 * operator.analyzer_ellipticity_rad)
    return np.asarray([[1.0 + q, u - 1j * v], [u + 1j * v, 1.0 - q]])


@lru_cache(maxsize=8192)
def _fields(
    state: SimulationState, grid: PupilGrid
) -> tuple[ComplexArray, ComplexArray, MieSolution]:
    source = state.source
    environment = state.environment
    reference_scalar = _reference_scalar(
        state.geometry.width_m,
        state.geometry.depth_m,
        state.geometry.sidewall_angle_deg,
        source.wavelength_m,
        source.waist_m,
        source.incident_power_W,
        source.beam_offset_longitudinal_m,
        source.beam_offset_lateral_m,
        environment.fill_refractive_index,
        environment.wall_refractive_index,
        grid,
    )
    node_count = grid.theta.size
    reference = np.zeros((2, node_count, 2), dtype=np.complex128)
    reference[0, :, 0] = reference_scalar
    reference[1, :, 1] = reference_scalar
    mie = _mie_solution(
        state.particle.diameter_m,
        state.particle.refractive_index_real,
        state.particle.refractive_index_imag,
        environment.fill_refractive_index,
        source.wavelength_m,
        grid,
    )
    s, u, z = _particle_coordinates(state)
    k0 = 2.0 * math.pi / source.wavelength_m
    peak = math.sqrt(
        4.0
        * source.incident_power_W
        / (environment.wall_refractive_index * epsilon_0 * c * math.pi * source.waist_m**2)
    )
    envelope = math.exp(
        -(
            (s - source.beam_offset_longitudinal_m) ** 2
            + (u - source.beam_offset_lateral_m) ** 2
        )
        / source.waist_m**2
    )
    local_phase = np.exp(
        1j
        * k0
        * (
            environment.wall_refractive_index * (z - 0.5 * state.geometry.depth_m)
            + (environment.fill_refractive_index - environment.wall_refractive_index) * z
        )
    )
    local = peak * envelope * local_phase
    cos_phi = np.cos(grid.phi)
    sin_phi = np.sin(grid.phi)
    k_fill = k0 * environment.fill_refractive_index
    prefactor = -math.sqrt(environment.fill_refractive_index * epsilon_0 * c / 2.0) / k_fill
    bridge = np.sqrt(
        (environment.wall_refractive_index / environment.fill_refractive_index)
        * np.cos(grid.theta)
    )
    translation = np.exp(
        -1j
        * k_fill
        * np.sin(grid.theta)
        * (s * cos_phi + u * sin_phi)
        + 1j * k_fill * (state.geometry.depth_m - z) * np.cos(grid.theta)
    )
    particle = np.empty((2, node_count, 2), dtype=np.complex128)
    for mode, (ex, ey) in enumerate(((local, 0.0j), (0.0j, local))):
        parallel = ex * cos_phi + ey * sin_phi
        perpendicular = -ex * sin_phi + ey * cos_phi
        e_theta = parallel * mie.s2
        e_phi = perpendicular * mie.s1
        particle[mode, :, 0] = e_theta * cos_phi - e_phi * sin_phi
        particle[mode, :, 1] = e_theta * sin_phi + e_phi * cos_phi
    particle *= (prefactor * bridge * translation)[None, :, None]
    return reference, particle, mie


def _gram(
    left: ComplexArray,
    right: ComplexArray,
    weights: FloatArray,
    analyzer: ComplexArray,
) -> ComplexArray:
    weighted = np.einsum("n,ab,mnb->mna", weights, analyzer, right, optimize=True)
    return np.asarray(np.einsum("mna,kna->mk", left.conj(), weighted, optimize=True))


def _block_ids(state: SimulationState, grid: PupilGrid) -> tuple[str, str, str, str]:
    payload = state.to_payload()
    reference = canonical_sha256(
        {
            "geometry": payload["geometry"],
            "source_field": {
                key: payload["source"][key]
                for key in (
                    "wavelength_m",
                    "waist_m",
                    "incident_power_W",
                    "beam_offset_longitudinal_m",
                    "beam_offset_lateral_m",
                )
            },
            "environment": payload["environment"],
            "grid_id": grid.grid_id,
        }
    )
    particle = canonical_sha256(
        {
            "particle": payload["particle"],
            "wavelength_m": payload["source"]["wavelength_m"],
            "fill_refractive_index": payload["environment"]["fill_refractive_index"],
            "grid_id": grid.grid_id,
        }
    )
    position = canonical_sha256(
        {
            "geometry": payload["geometry"],
            "particle_diameter_m": payload["particle"]["diameter_m"],
            "position": payload["position"],
            "local_source": payload["source"],
            "environment": payload["environment"],
        }
    )
    operator = canonical_sha256(
        {
            "observation": payload["observation"],
            "source_polarization": {
                key: payload["source"][key]
                for key in (
                    "polarization_azimuth_rad",
                    "ellipticity_rad",
                    "degree_of_polarization",
                )
            },
            "grid_id": grid.grid_id,
        }
    )
    return reference, particle, position, operator


@lru_cache(maxsize=16384)
def _evaluate_formal_cached(
    state: SimulationState,
    pupil_order: tuple[int, int],
) -> FormalPrimitives:
    radial, azimuthal = pupil_order
    grid = _pupil_grid(
        state.observation.collection_na,
        state.observation.pupil_inner_radius,
        state.observation.pupil_outer_radius,
        state.observation.detector_sector_center_rad,
        state.observation.detector_sector_width_rad,
        int(radial),
        int(azimuthal),
    )
    field_state = replace(
        state,
        source=replace(
            state.source,
            polarization_azimuth_rad=0.0,
            ellipticity_rad=0.0,
            degree_of_polarization=0.0,
        ),
        observation=replace(
            state.observation,
            analyzer_azimuth_rad=0.0,
            analyzer_ellipticity_rad=0.0,
        ),
    )
    reference, particle, mie = _fields(field_state, grid)
    gamma = _source_covariance(state)
    analyzer = _analyzer_weight(state)
    rr = complex(np.trace(gamma @ _gram(reference, reference, grid.weights_sr, analyzer)))
    ss = complex(np.trace(gamma @ _gram(particle, particle, grid.weights_sr, analyzer)))
    cc = complex(np.trace(gamma @ _gram(reference, particle, grid.weights_sr, analyzer)))
    tolerance = 1.0e-12 * max(abs(rr), abs(ss), abs(cc), 1.0)
    if abs(rr.imag) > tolerance or abs(ss.imag) > tolerance or rr.real < 0.0 or ss.real < 0.0:
        raise FoundationError(E_NUMERICAL_NONFINITE, "formal field power identity failed")
    values = (rr.real, ss.real, cc.real, cc.imag)
    if not all(math.isfinite(value) for value in values):
        raise FoundationError(E_NUMERICAL_NONFINITE, "formal field coupling is nonfinite")
    reference_id, particle_id, position_id, operator_id = _block_ids(state, grid)
    receipts = (
        canonical_sha256(
            {
                "numerical_profile_hash": CONFIG_HASH,
                "pupil_grid_id": grid.grid_id,
                "reference_gauss_order": NUMERICS["reference_gauss_order_per_axis"],
            }
        ),
        mie.receipt_id,
    )
    if rr.real <= LOW_FIELD_W or ss.real <= LOW_FIELD_W:
        return FormalPrimitives(
            rr.real,
            ss.real,
            0.0,
            0.0,
            None,
            None,
            None,
            None,
            "FORMAL_WITH_LIMITS",
            reference_id,
            particle_id,
            position_id,
            operator_id,
            receipts,
        )
    eta = cc / math.sqrt(rr.real * ss.real)
    if abs(eta) > 1.0 + 1.0e-10:
        raise FoundationError(E_NUMERICAL_NONFINITE, "formal coupling violates Cauchy bound")
    return FormalPrimitives(
        rr.real,
        ss.real,
        cc.real,
        cc.imag,
        eta.real,
        eta.imag,
        abs(eta),
        math.atan2(cc.imag, cc.real),
        "FORMAL_WITH_LIMITS",
        reference_id,
        particle_id,
        position_id,
        operator_id,
        receipts,
    )


def evaluate_formal_m1(
    state: SimulationState,
    *,
    pupil_order: tuple[int, int] | None = None,
) -> FormalPrimitives:
    """Evaluate the formal first-order M1 field chain for one validated state."""

    order = pupil_order or tuple(NUMERICS["production_pupil_order"])
    return _evaluate_formal_cached(state, (int(order[0]), int(order[1])))


def _cache_payload(info: object) -> dict[str, int | None]:
    values = info  # cache_info named tuple at runtime
    return {
        "hits": int(getattr(values, "hits")),
        "misses": int(getattr(values, "misses")),
        "maxsize": getattr(values, "maxsize"),
        "current_size": int(getattr(values, "currsize")),
    }


def formal_cache_stats() -> dict[str, dict[str, int | None]]:
    """Return compact in-process cache statistics for qualification receipts."""

    return {
        "reference": _cache_payload(_reference_scalar.cache_info()),
        "mie": _cache_payload(_mie_solution.cache_info()),
        "position_field": _cache_payload(_fields.cache_info()),
        "operator_summary": _cache_payload(_evaluate_formal_cached.cache_info()),
    }


def clear_formal_caches() -> None:
    """Clear all formal caches before a cold qualification or performance run."""

    _evaluate_formal_cached.cache_clear()
    _fields.cache_clear()
    _reference_scalar.cache_clear()
    _mie_solution.cache_clear()
    _pupil_grid.cache_clear()
