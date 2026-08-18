"""Capability discovery backed by the packaged candidate catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import yaml

from .models import ENGINE_VERSION, FEATURE_VERSION, SCHEMA_VERSION, canonical_sha256
from .profiles import FAST_CONTROL_PROFILE, FORMAL_PROFILE


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    engine_version: str
    schema_version: str
    feature_version: str
    feature_count: int
    features: tuple[dict[str, Any], ...]
    claim_ceiling: str
    catalogue_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "feature_version": self.feature_version,
            "feature_count": self.feature_count,
            "features": list(self.features),
            "claim_ceiling": self.claim_ceiling,
            "catalogue_hash": self.catalogue_hash,
        }


def capabilities() -> CapabilityReport:
    resource = files("nodi_foundation.data").joinpath("feature_catalog_candidate.yaml")
    document = yaml.safe_load(resource.read_text(encoding="utf-8"))
    raw_features = tuple(dict(row) for row in document["features"])
    features = tuple(
        {
            **row,
            "implementation_status": str(row["formal_status"]),
            "profile_status": {
                FORMAL_PROFILE: str(row["formal_status"]),
                FAST_CONTROL_PROFILE: "SCALING_CONTROL_ONLY",
            },
        }
        for row in raw_features
    )
    return CapabilityReport(
        engine_version=ENGINE_VERSION,
        schema_version=SCHEMA_VERSION,
        feature_version=FEATURE_VERSION,
        feature_count=len(features),
        features=features,
        claim_ceiling=str(document["claim_ceiling"]),
        catalogue_hash=canonical_sha256(document),
    )
