#!/usr/bin/env python3
"""validate.py — Deterministic validation of sweep result.json.

Checks schema, partition completeness, evidence, format rules.
Returns a score (0–100) and a list of violations.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BUNDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
EFFECT_VALID = {"build", "close", "keep-open"}


def validate(result: dict, golden: dict | None = None) -> dict:
    """Validate a sweep result.json. Returns score + violations."""
    violations: list[dict] = []
    score = 100.0

    # ── Schema structure ─────────────────────────────────────────────
    required_top = {"workflow", "open_ids", "already_resolved", "bundles",
                    "blocked", "skip", "decisions", "escalations"}
    missing = required_top - set(result.keys())
    if missing:
        violations.append({"id": "schema_missing_fields", "detail": f"missing: {missing}"})
        score -= 20

    if result.get("workflow") != "deferred-sweep-triage":
        violations.append({"id": "schema_wrong_workflow", "detail": result.get("workflow")})
        score -= 5

    open_ids = set(result.get("open_ids", []))

    # ── Partition completeness ───────────────────────────────────────
    classified: dict[str, str] = {}  # id → category

    for entry in result.get("already_resolved", []):
        eid = entry.get("id", "")
        if eid in classified:
            violations.append({"id": "partition_duplicate", "detail": f"{eid} in multiple categories"})
            score -= 10
        classified[eid] = "already_resolved"
        if not entry.get("evidence"):
            violations.append({"id": "resolved_no_evidence", "detail": eid})
            score -= 5

    for bundle in result.get("bundles", []):
        bname = bundle.get("name", "")
        if not BUNDLE_RE.match(bname):
            violations.append({"id": "bundle_name_invalid", "detail": bname})
            score -= 5
        if not bundle.get("intent"):
            violations.append({"id": "bundle_no_intent", "detail": bname})
            score -= 5
        for eid in bundle.get("dw_ids", []):
            if eid in classified:
                violations.append({"id": "partition_duplicate", "detail": f"{eid} in multiple categories"})
                score -= 10
            classified[eid] = "bundles"

    for entry in result.get("blocked", []):
        eid = entry.get("id", "")
        if eid in classified:
            violations.append({"id": "partition_duplicate", "detail": f"{eid} in multiple categories"})
            score -= 10
        classified[eid] = "blocked"
        if not entry.get("blocker"):
            violations.append({"id": "blocked_no_blocker", "detail": eid})
            score -= 5

    for entry in result.get("skip", []):
        eid = entry.get("id", "")
        if eid in classified:
            violations.append({"id": "partition_duplicate", "detail": f"{eid} in multiple categories"})
            score -= 10
        classified[eid] = "skip"
        if not entry.get("reason"):
            violations.append({"id": "skip_no_reason", "detail": eid})
            score -= 5

    for entry in result.get("decisions", []):
        eid = entry.get("id", "")
        if eid in classified:
            violations.append({"id": "partition_duplicate", "detail": f"{eid} in multiple categories"})
            score -= 10
        classified[eid] = "decisions"
        options = entry.get("options", [])
        if len(options) < 2:
            violations.append({"id": "decision_few_options", "detail": eid})
            score -= 5
        for opt in options:
            if opt.get("effect") not in EFFECT_VALID:
                violations.append({"id": "decision_invalid_effect", "detail": f"{eid}/{opt.get('key')}"})
                score -= 5
            if opt.get("effect") == "build" and not opt.get("intent"):
                violations.append({"id": "decision_build_no_intent", "detail": f"{eid}/{opt.get('key')}"})
                score -= 3
        rec = entry.get("recommendation")
        opt_keys = {o.get("key") for o in options}
        if rec and rec not in opt_keys:
            violations.append({"id": "decision_bad_recommendation", "detail": f"{eid}: {rec}"})
            score -= 3

    # ── Open_ids completeness ────────────────────────────────────────
    if classified.keys() != open_ids:
        missing_from_class = open_ids - classified.keys()
        extra_in_class = classified.keys() - open_ids
        if missing_from_class:
            violations.append({"id": "open_ids_not_classified", "detail": sorted(missing_from_class)})
            score -= 10
        if extra_in_class:
            violations.append({"id": "classified_not_in_open", "detail": sorted(extra_in_class)})
            score -= 10

    # ── Golden comparison (if provided) ──────────────────────────────
    if golden:
        g_open = set(golden.get("open_ids", []))
        if open_ids != g_open:
            diff = open_ids.symmetric_difference(g_open)
            violations.append({"id": "open_ids_mismatch", "detail": sorted(diff)})
            score -= 5
        g_classified = {}
        for cat in ("already_resolved", "bundles", "blocked", "skip", "decisions"):
            for entry in golden.get(cat, []):
                eid = entry.get("id") or entry.get("name")
                if entry.get("dw_ids"):
                    for dw in entry["dw_ids"]:
                        g_classified[dw] = cat
                elif eid:
                    g_classified[eid] = cat
        for eid, expected_cat in g_classified.items():
            actual_cat = classified.get(eid)
            if actual_cat != expected_cat:
                violations.append({"id": "classification_mismatch",
                                   "detail": f"{eid}: expected {expected_cat}, got {actual_cat}"})
                score -= 8

    score = max(0, round(score, 1))
    return {"score": score, "violations": violations, "passed": len(violations) == 0}


def main():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("result_json", type=Path)
    parser.add_argument("--golden", type=Path, default=None)
    args = parser.parse_args()

    result = json.loads(args.result_json.read_text())
    golden = json.loads(args.golden.read_text()) if args.golden else None
    report = validate(result, golden)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
