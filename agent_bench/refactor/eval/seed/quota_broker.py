"""Quota Broker — REFACTOR semilla: passes gate, but monolith design.

Passes cleaner-gate (all checks PASS). Tests PASS. But:
- apply() is still a single monolith mixing eligibility, cache, emit, log
- No extracted helpers beyond _is_eligible
- REFACTOR agent should improve this by splitting concerns
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quota_broker")

SKIP = object()
DEFAULT_TIMEOUT = 600
EMPTY_MSG = "records must not be empty"
TRACE_PREFIX = "trace_"


class SinkError(Exception):
    pass


def normalize(value: Any, *, fallback: int = 10) -> int:
    if value is None:
        return fallback
    return int(value)


def _membership_ok(rec: Any, spec: Any) -> bool:
    """Allow/deny/extra_key — flat, no nesting."""
    deny = getattr(spec, "deny", None)
    if deny is not None:
        if rec.kind in deny:
            return False
    allow = getattr(spec, "allow", None)
    if allow is not None:
        if rec.kind not in allow:
            return False
    if getattr(spec, "extra_key", None) is not None:
        if getattr(rec, "tag", None) != spec.extra_key:
            return False
    return True


def _is_eligible(rec: Any, spec: Any) -> bool:
    """Flat acceptance — delegates membership to helper."""
    if rec.kind is SKIP:
        return False
    if not rec.active:
        return False
    if not rec.visible:
        return False
    if rec.score < spec.threshold:
        return False
    if not _membership_ok(rec, spec):
        return False
    if getattr(spec, "flag", False):
        return True
    if getattr(spec, "mode", None) == "strict":
        return True
    if hasattr(spec, "flag"):
        return False
    if hasattr(spec, "mode"):
        return False
    return True


def _resolve_emit_key(rec: Any, path_map: Any) -> Any:
    """Resolve emit key from path_map."""
    if not path_map:
        return rec.key
    mapped = path_map.get(rec.key)
    return rec.key if mapped is None else mapped


def _try_emit(rec: Any, spec: Any, sink: Any, path_map: Any, timeout: int) -> bool:
    """Try to emit one record. Returns True on success, False on SinkError."""
    try:
        sink.emit(rec.kind, _resolve_emit_key(rec, path_map), str(rec.score), timeout=timeout)
    except SinkError:
        return False
    return True


def apply(
    records: Any, spec: Any, sink: Any, clock: Any,
    *, timeout: int = DEFAULT_TIMEOUT,
) -> tuple[tuple[Any, ...], tuple[Any, ...], int]:
    """Monolith — mixes eligibility, cache, emit, log. REFACTOR should split."""
    if not records:
        raise ValueError(EMPTY_MSG)
    clock.now()
    max_emit = getattr(spec, "max_emit", None)
    stop_on_first = getattr(spec, "stop_on_first", False)
    path_map = getattr(spec, "path_map", None)
    accepted: list[Any] = []
    rejected: list[Any] = []
    total_weight = 0
    emitted = 0

    for rec in records:
        if stop_on_first and accepted:
            break
        if not _is_eligible(rec, spec):
            rejected.append(rec)
            continue
        if max_emit is not None and emitted >= max_emit:
            rejected.append(rec)
            continue
        if rec.key in apply._cache:
            rec.trace_id = apply._cache[rec.key]
            accepted.append(rec)
            total_weight += rec.weight
            continue
        total_weight += rec.weight
        if not _try_emit(rec, spec, sink, path_map, timeout):
            rejected.append(rec)
            continue
        rec.trace_id = f"{TRACE_PREFIX}{rec.key}"
        apply._cache[rec.key] = rec.trace_id
        emitted += 1
        logger.info("accepted %s score=%s", rec.key, rec.score)
        print(f"dispatch {rec.key} {rec.kind}", flush=True)
        accepted.append(rec)
    return (tuple(accepted), tuple(rejected), total_weight)


apply._cache: dict = {}
