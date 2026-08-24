#!/usr/bin/env python3
"""validate.py — Validate resolve resolution.json + spec edit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def validate_resolution(result: dict, golden: dict | None = None) -> dict:
    violations = []
    score = 100.0

    required = {"story_key", "decision", "spec_file", "spec_updated"}
    missing = required - set(result.keys())
    if missing:
        violations.append({"id": "schema_missing", "detail": str(missing)})
        score -= 20

    decision = result.get("decision", "")
    if not decision or len(decision) < 10:
        violations.append({"id": "decision_too_short", "detail": decision})
        score -= 15

    if not result.get("spec_updated"):
        violations.append({"id": "spec_not_updated", "detail": "spec_updated is not true"})
        score -= 20

    if result.get("spec_file", "").endswith("sprint-status.yaml"):
        violations.append({"id": "touched_sprint_status", "detail": "must not edit sprint-status"})
        score -= 25

    if result.get("spec_file", "").endswith("spec") and "status:" in result.get("decision", ""):
        violations.append({"id": "set_spec_status", "detail": "must not set spec status field"})
        score -= 15

    if golden:
        gd = golden.get("decision", "").lower()
        rd = decision.lower()
        if "deny" in gd and "deny" not in rd:
            violations.append({"id": "decision_wrong_semantics", "detail": "golden says deny takes precedence"})
            score -= 15
        elif "allow" in gd and "allow" not in rd and "deny" not in rd:
            violations.append({"id": "decision_wrong_semantics", "detail": "golden says allow takes precedence"})
            score -= 15

    score = max(0, round(score, 1))
    return {"score": score, "violations": violations, "passed": len(violations) == 0}


def main():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("result_json", type=Path)
    parser.add_argument("--golden", type=Path, default=None)
    args = parser.parse_args()
    result = json.loads(args.result_json.read_text())
    golden = json.loads(args.golden.read_text()) if args.golden else None
    report = validate_resolution(result, golden)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
