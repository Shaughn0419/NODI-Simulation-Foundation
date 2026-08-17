"""Content-addressed immutable release manifests and validation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    SCHEMA_VERSION,
    canonical_json,
    canonical_sha256,
)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    release_id: str | None
    release_type: str | None
    file_count: int
    errors: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "release_id": self.release_id,
            "release_type": self.release_type,
            "file_count": self.file_count,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class DatasetRelease:
    path: Path
    release_id: str
    state_count: int
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PairRelease:
    path: Path
    release_id: str
    pair_count: int
    manifest: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_release_manifest(
    directory: Path,
    *,
    release_type: str,
    primary_files: tuple[str, ...],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    files = []
    for relative in primary_files:
        path = directory / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(
            {
                "path": relative.replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    body = {
        "manifest_schema_version": 1,
        "release_type": release_type,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "feature_version": FEATURE_VERSION,
        "files": files,
        "metadata": metadata,
    }
    manifest = {**body, "release_id": canonical_sha256(body)}
    _atomic_write(directory / "manifest.json", canonical_json(manifest) + "\n")
    return manifest


def validate_release(path: str | Path) -> ValidationReport:
    directory = Path(path)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return ValidationReport(False, None, None, 0, ("E_RELEASE_MANIFEST_MISSING",))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ValidationReport(False, None, None, 0, ("E_RELEASE_MANIFEST_INVALID",))
    errors: list[str] = []
    release_id = manifest.get("release_id")
    release_type = manifest.get("release_type")
    body = dict(manifest)
    body.pop("release_id", None)
    if not isinstance(release_id, str) or canonical_sha256(body) != release_id:
        errors.append("E_RELEASE_MANIFEST_HASH_MISMATCH")
    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("E_RELEASE_FILE_LIST_INVALID")
        files = []
    for row in files:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            errors.append("E_RELEASE_FILE_ENTRY_INVALID")
            continue
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append("E_RELEASE_PATH_INVALID")
            continue
        artifact = directory / relative
        if not artifact.is_file():
            errors.append(f"E_RELEASE_FILE_MISSING:{row['path']}")
            continue
        if artifact.stat().st_size != row.get("size_bytes"):
            errors.append(f"E_RELEASE_SIZE_MISMATCH:{row['path']}")
        if sha256_file(artifact) != row.get("sha256"):
            errors.append(f"E_RELEASE_HASH_MISMATCH:{row['path']}")
    return ValidationReport(
        valid=not errors,
        release_id=release_id if isinstance(release_id, str) else None,
        release_type=release_type if isinstance(release_type, str) else None,
        file_count=len(files),
        errors=tuple(errors),
    )
