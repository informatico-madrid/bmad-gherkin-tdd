"""Quota Broker — hollow stub for GREEN benchmark."""

from __future__ import annotations

from typing import Any

SKIP = object()


class SinkError(Exception):
    """Raised when the sink rejects an emit."""


def apply(
    records: list[Any],
    spec: Any,
    sink: Any,
    clock: Any,
    *,
    timeout: float = 600.0,
) -> tuple[Any, ...]:
    raise NotImplementedError("quota_broker.apply is a hollow stub")


def normalize(value: Any, *, fallback: int = 10) -> int:
    raise NotImplementedError("quota_broker.normalize is a hollow stub")
