"""Regression tests for the bmad-loop profiles shipped by this module."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PROFILE_NAMES = ("opencode-http.toml", "opencode-http-review.toml")
OPENCODE_QUOTA_ERROR = (
    'timestamp=2026-08-27T14:12:52.998Z level=ERROR run=fake0003 '
    'message="stream error" providerID=openai modelID=gpt-5.6-luna '
    'error.error="AI_APICallError: The usage limit has been reached"'
)


@pytest.mark.parametrize("profile_name", PROFILE_NAMES)
def test_opencode_profiles_classify_the_actual_quota_error(profile_name: str) -> None:
    profile = tomllib.loads(
        (ROOT / "bmad-loop" / "profiles" / profile_name).read_text(encoding="utf-8")
    )
    patterns = profile.get("env_fault_patterns", [])

    assert patterns
    assert any(re.search(pattern, OPENCODE_QUOTA_ERROR) for pattern in patterns)
