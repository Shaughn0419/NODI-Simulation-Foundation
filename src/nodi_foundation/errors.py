"""Stable public error codes."""

from __future__ import annotations


class FoundationError(ValueError):
    """Typed product error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


E_DOMAIN_INVALID = "E_DOMAIN_INVALID"
E_FEATURE_UNSUPPORTED = "E_FEATURE_UNSUPPORTED"
E_OPERATOR_UNQUALIFIED = "E_OPERATOR_UNQUALIFIED"
E_NUMERICAL_NONFINITE = "E_NUMERICAL_NONFINITE"
E_RELEASE_HASH_MISMATCH = "E_RELEASE_HASH_MISMATCH"
E_SCHEMA_INCOMPATIBLE = "E_SCHEMA_INCOMPATIBLE"
E_RESOURCE_LIMIT = "E_RESOURCE_LIMIT"
