"""Bounded worker and committed-memory checks."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

from .errors import E_RESOURCE_LIMIT, FoundationError

MAX_WORKERS = 24
COMMITTED_MEMORY_LIMIT_BYTES = 210_000_000_000
COMMITTED_MEMORY_SOFT_STOP_BYTES = 206_000_000_000
COMMITTED_MEMORY_EMERGENCY_STOP_BYTES = 208_000_000_000
FULL_RUN_LAUNCH_HEADROOM_BYTES = 30_000_000_000
DEFAULT_WORKER_RESERVE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    workers: int
    committed_memory_bytes: int | None
    projected_committed_memory_bytes: int | None
    committed_memory_limit_bytes: int


def system_committed_memory_bytes() -> int | None:
    """Return system committed bytes on Windows, or ``None`` if unavailable."""

    if sys.platform != "win32":
        return None

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    windll = getattr(ctypes, "windll", None)
    if windll is None or not windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPageFile - status.ullAvailPageFile)


def assert_resource_budget(
    workers: int,
    *,
    worker_reserve_bytes: int = DEFAULT_WORKER_RESERVE_BYTES,
    launch_headroom_bytes: int = 0,
) -> ResourceSnapshot:
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= MAX_WORKERS:
        raise FoundationError(E_RESOURCE_LIMIT, f"workers must be in [1, {MAX_WORKERS}]")
    if worker_reserve_bytes < 0:
        raise FoundationError(E_RESOURCE_LIMIT, "worker reserve must be nonnegative")
    if launch_headroom_bytes < 0:
        raise FoundationError(E_RESOURCE_LIMIT, "launch headroom must be nonnegative")
    committed = system_committed_memory_bytes()
    projected = (
        None
        if committed is None
        else committed + workers * worker_reserve_bytes + launch_headroom_bytes
    )
    if committed is not None and committed >= COMMITTED_MEMORY_LIMIT_BYTES:
        raise FoundationError(E_RESOURCE_LIMIT, "system committed memory is already at the limit")
    if projected is not None and projected >= COMMITTED_MEMORY_LIMIT_BYTES:
        raise FoundationError(E_RESOURCE_LIMIT, "projected committed memory reaches the limit")
    return ResourceSnapshot(
        workers=workers,
        committed_memory_bytes=committed,
        projected_committed_memory_bytes=projected,
        committed_memory_limit_bytes=COMMITTED_MEMORY_LIMIT_BYTES,
    )


def default_worker_count() -> int:
    return max(1, min(os.cpu_count() or 1, MAX_WORKERS))
