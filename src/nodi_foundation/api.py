"""The sole authoritative public API facade."""

from .batch import BatchResult, ExecutionSpec, simulate_batch
from .capabilities import CapabilityReport, capabilities
from .datasets import DatasetSpec, build_dataset
from .errors import (
    E_DOMAIN_INVALID,
    E_FEATURE_UNSUPPORTED,
    E_NUMERICAL_NONFINITE,
    E_OPERATOR_UNQUALIFIED,
    E_RELEASE_HASH_MISMATCH,
    E_RESOURCE_LIMIT,
    E_SCHEMA_INCOMPATIBLE,
    FoundationError,
)
from .interventions import PairSpec, build_intervention_pairs
from .models import (
    EnvironmentState,
    GeometryState,
    ObservationOperatorState,
    ParticleState,
    PositionState,
    SimulationState,
    SourceState,
    StateResult,
)
from .releases import DatasetRelease, PairRelease, ValidationReport, validate_release
from .simulate import derive_observation, simulate_state

__version__ = "5.0.0"

__all__ = [
    "BatchResult",
    "CapabilityReport",
    "DatasetRelease",
    "DatasetSpec",
    "E_DOMAIN_INVALID",
    "E_FEATURE_UNSUPPORTED",
    "E_NUMERICAL_NONFINITE",
    "E_OPERATOR_UNQUALIFIED",
    "E_RELEASE_HASH_MISMATCH",
    "E_RESOURCE_LIMIT",
    "E_SCHEMA_INCOMPATIBLE",
    "EnvironmentState",
    "ExecutionSpec",
    "FoundationError",
    "GeometryState",
    "ObservationOperatorState",
    "ParticleState",
    "PairRelease",
    "PairSpec",
    "PositionState",
    "SimulationState",
    "SourceState",
    "StateResult",
    "ValidationReport",
    "__version__",
    "build_dataset",
    "build_intervention_pairs",
    "capabilities",
    "derive_observation",
    "simulate_batch",
    "simulate_state",
    "validate_release",
]
