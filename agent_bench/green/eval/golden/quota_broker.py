"""Quota Broker — golden implementation for GREEN benchmark.

Every pin here has an observable effect. Dead `pass` branches are forbidden.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quota_broker")

SKIP = object()


class SinkError(Exception):
    """Raised when the sink rejects an emit."""


def normalize(value: Any, *, fallback: int = 10) -> int:
    if value is None:
        return fallback
    return int(value)


def apply(
    records: list[Any],
    spec: Any,
    sink: Any,
    clock: Any,
    *,
    timeout: float = 600.0,
) -> tuple[tuple[Any, ...], tuple[Any, ...], int]:
    if records is None or len(records) == 0:
        raise ValueError("records must not be empty")

    clock.now()

    allow = getattr(spec, "allow", None)
    deny = getattr(spec, "deny", None)
    max_emit = getattr(spec, "max_emit", None)
    path_map = getattr(spec, "path_map", None)
    threshold = getattr(spec, "threshold", 50)

    accepted: list[Any] = []
    rejected: list[Any] = []
    total_weight = 0
    emit_count = 0

    if not hasattr(apply, "_cache"):
        apply._cache = {}

    for rec in records:
        if max_emit is not None and emit_count >= max_emit:
            rejected.append(rec)
            continue

        if rec.kind is SKIP:
            rejected.append(rec)
            continue

        if rec.score < threshold:
            rejected.append(rec)
            continue

        active = getattr(rec, "active", True)
        visible = getattr(rec, "visible", True)
        if not (active and visible):
            rejected.append(rec)
            continue

        if hasattr(spec, "mode") or hasattr(spec, "flag"):
            mode = getattr(spec, "mode", "relaxed")
            flag = getattr(spec, "flag", False)
            if not (mode == "strict" or flag):
                rejected.append(rec)
                continue

        if deny is not None and rec.kind in deny:
            rejected.append(rec)
            continue
        if allow is not None and rec.kind not in allow:
            rejected.append(rec)
            continue

        if hasattr(spec, "extra_key"):
            if getattr(rec, "tag", None) != spec.extra_key:
                rejected.append(rec)
                continue

        cache_key = getattr(rec, "key", None)
        if cache_key in apply._cache:
            rec.trace_id = apply._cache[cache_key]
            continue

        emit_key = rec.key
        if path_map is not None:
            mapped = path_map.get(rec.key, rec.key)
            emit_key = rec.key if mapped is None else mapped

        total_weight += getattr(rec, "weight", rec.score)

        try:
            sink.emit(rec.kind, emit_key, str(rec.score), timeout=timeout)
        except SinkError as e:
            rejected.append(rec)
            logger.error("SinkError: %s", str(e))
            continue
        except TypeError:
            raise

        rec.trace_id = f"trace_{rec.key}"
        if cache_key is not None:
            apply._cache[cache_key] = rec.trace_id

        logger.info("accepted %s score=%s", rec.key, rec.score)
        print(f"dispatch {rec.key} {rec.kind}", flush=True)

        accepted.append(rec)
        emit_count += 1

        if getattr(spec, "stop_on_first", False):
            break

    return (tuple(accepted), tuple(rejected), total_weight)
