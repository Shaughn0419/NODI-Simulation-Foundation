"""Stable public facade for NODI Simulation Foundation."""

from .batch import BatchResult, ExecutionSpec, simulate_batch
from .capabilities import CapabilityReport, capabilities
from .datasets import DatasetSpec, build_dataset
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

__version__ = "1.0.0"

__all__ = [
    "EnvironmentState",
    "BatchResult",
    "CapabilityReport",
    "DatasetRelease",
    "DatasetSpec",
    "ExecutionSpec",
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
    "capabilities",
    "build_dataset",
    "build_intervention_pairs",
    "derive_observation",
    "simulate_state",
    "simulate_batch",
    "validate_release",
]
