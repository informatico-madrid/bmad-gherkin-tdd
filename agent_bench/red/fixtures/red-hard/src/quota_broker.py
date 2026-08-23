"""Quota Broker — hollow stub for benchmark.

This is NOT the SUT under test. It exists solely so that `import quota_broker`
does not explode. The benchmark evaluates test source code statically (AST +
contract), not via execution against this stub.
"""

from __future__ import annotations

from typing import Any


SKIP = object()
"""Sentinel: identity-only pass-through (is, not ==)."""


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
    """Dispatch records through a policy spec to a sink. HOLLOW — raises."""
    raise NotImplementedError("quota_broker.apply is a hollow stub")


def normalize(value: Any, *, fallback: int = 10) -> int:
    """Coerce value to int, using fallback for None only. HOLLOW — raises."""
    raise NotImplementedError("quota_broker.normalize is a hollow stub")
