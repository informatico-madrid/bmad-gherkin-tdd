"""Quota Broker — CLEAN seed: tests PASS, cleaner-gate FAIL.

Deliberate structural dirt (do not "pretty" this file):
- KISS: apply + _apply_core both high cyclomatic complexity / arity
- DRY: accept/reject loop duplicated in apply and _apply_core
- YAGNI: unused json, math, os
- LoD: spec.a.b.c.d chain
The CLEAN agent must fix structure without changing observable behavior.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

logger = logging.getLogger("quota_broker")

SKIP = object()


class SinkError(Exception):
    pass


def normalize(value: Any, *, fallback: int = 10) -> int:
    if value is None:
        return fallback
    return int(value)


def _apply_core(
    records,
    spec,
    sink,
    clock,
    timeout,
    accepted,
    rejected,
    total_weight,
    emit_count,
    mode,
    flag,
    path_map,
    max_emit,
    stop_on_first,
):
    for rec in records:
        if max_emit is not None and emit_count >= max_emit:
            rejected.append(rec)
            continue
        if rec.kind is SKIP:
            rejected.append(rec)
            continue
        if rec.score < spec.threshold:
            rejected.append(rec)
            continue
        if not (rec.active and rec.visible):
            rejected.append(rec)
            continue
        if hasattr(spec, "mode") or hasattr(spec, "flag"):
            m = getattr(spec, "mode", "relaxed")
            f = getattr(spec, "flag", False)
            if not (m == "strict" or f):
                rejected.append(rec)
                continue
        allow = getattr(spec, "allow", None)
        deny = getattr(spec, "deny", None)
        if deny is not None and rec.kind in deny:
            rejected.append(rec)
            continue
        if allow is not None and rec.kind not in allow:
            rejected.append(rec)
            continue
        extra_key = getattr(spec, "extra_key", None)
        if extra_key is not None and getattr(rec, "tag", None) != extra_key:
            rejected.append(rec)
            continue
        if rec.key in apply._cache:
            rec.trace_id = apply._cache[rec.key]
            accepted.append(rec)
            total_weight += rec.weight
            continue
        emit_key = rec.key
        if path_map is not None:
            mapped = path_map.get(rec.key, rec.key)
            emit_key = rec.key if mapped is None else mapped
        total_weight += rec.weight
        try:
            sink.emit(rec.kind, emit_key, str(rec.score), timeout=timeout)
        except SinkError:
            rejected.append(rec)
            continue
        rec.trace_id = f"trace_{rec.key}"
        apply._cache[rec.key] = rec.trace_id
        emit_count += 1
        logger.info("accepted %s score=%s", rec.key, rec.score)
        print(f"dispatch {rec.key} {rec.kind}", flush=True)
        accepted.append(rec)
        if stop_on_first:
            break
    return emit_count, total_weight


def apply(
    records: Any,
    spec: Any,
    sink: Any,
    clock: Any,
    *,
    timeout: float = 600.0,
) -> tuple[tuple[Any, ...], tuple[Any, ...], int]:
    if not records:
        raise ValueError("records must not be empty")
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
        if max_emit is not None and emitted >= max_emit:
            rejected.append(rec)
            continue
        if rec.kind is SKIP:
            rejected.append(rec)
            continue
        if rec.score < spec.threshold:
            rejected.append(rec)
            continue
        if not (rec.active and rec.visible):
            rejected.append(rec)
            continue
        if hasattr(spec, "mode") or hasattr(spec, "flag"):
            m = getattr(spec, "mode", "relaxed")
            f = getattr(spec, "flag", False)
            if not (m == "strict" or f):
                rejected.append(rec)
                continue
        allow = getattr(spec, "allow", None)
        deny = getattr(spec, "deny", None)
        if deny is not None and rec.kind in deny:
            rejected.append(rec)
            continue
        if allow is not None and rec.kind not in allow:
            rejected.append(rec)
            continue
        extra_key = getattr(spec, "extra_key", None)
        if extra_key is not None and getattr(rec, "tag", None) != extra_key:
            rejected.append(rec)
            continue
        if rec.key in apply._cache:
            rec.trace_id = apply._cache[rec.key]
            accepted.append(rec)
            total_weight += rec.weight
            continue
        emit_key = rec.key
        if path_map is not None:
            mapped = path_map.get(rec.key, rec.key)
            emit_key = rec.key if mapped is None else mapped
        total_weight += rec.weight
        try:
            sink.emit(rec.kind, emit_key, str(rec.score), timeout=timeout)
        except SinkError:
            rejected.append(rec)
            continue
        rec.trace_id = f"trace_{rec.key}"
        apply._cache[rec.key] = rec.trace_id
        emitted += 1
        logger.info("accepted %s score=%s", rec.key, rec.score)
        print(f"dispatch {rec.key} {rec.kind}", flush=True)
        accepted.append(rec)
        if stop_on_first:
            break
    try:
        _ = spec.a.b.c.d
    except (AttributeError, TypeError):
        pass
    return (tuple(accepted), tuple(rejected), total_weight)


apply._cache: dict = {}
