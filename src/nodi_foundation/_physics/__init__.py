"""Internal physics-profile routing."""

from nodi_foundation.errors import E_DOMAIN_INVALID, FoundationError
from nodi_foundation.models import SimulationState
from nodi_foundation.profiles import FAST_CONTROL_PROFILE, FORMAL_PROFILE

from .formal_m1 import FormalPrimitives, evaluate_formal_m1
from .m1 import ScalingControlPrimitives, evaluate_scaling_control

PhysicsPrimitives = FormalPrimitives | ScalingControlPrimitives


def evaluate_profile(state: SimulationState) -> PhysicsPrimitives:
    if state.physics_profile_id == FORMAL_PROFILE:
        return evaluate_formal_m1(state)
    if state.physics_profile_id == FAST_CONTROL_PROFILE:
        return evaluate_scaling_control(state)
    raise FoundationError(
        E_DOMAIN_INVALID, f"unsupported physics profile {state.physics_profile_id!r}"
    )


__all__ = ["PhysicsPrimitives", "evaluate_formal_m1", "evaluate_profile"]
