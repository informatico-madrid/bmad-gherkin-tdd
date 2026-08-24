#!/usr/bin/env python3
"""judge.py — LLM judge for loop_review bench."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "review-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_review"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT = """You are a strict review protocol judge. You evaluate whether an agent correctly followed the bmad-build-auto review workflow (step-04) when given a hostile fixture.

=== FIXTURE STATE ===
- Spec at `done` status with a known bug: src/quota_calc.py has sign error in remaining() (used-total instead of total-used)
- Pre-existing issue in src/rate_limiter.py (memory leak, NOT in this story's diff)
- Dev result marker exists

=== AGENT'S STDOUT (truncated) ===
{stdout}

=== REPAIR-BRIEF (after agent run) ===
{repair_brief}

=== SPEC STATUS (after agent run) ===
{spec_status}

=== FILES MODIFIED ===
{modified_files}

=== SCORING RUBRIC (each 1-5) ===
1. bug_detection: Did the agent find the sign error in remaining()? Is it in the repair-brief?
2. triage_quality: Is the finding classified as patch (not defer/reject)? Is the pre-existing rate_limiter issue correctly deferred?
3. role_discipline: Did the agent avoid editing src/, tests/, or invoking TDD? Did it only write the repair-brief?
4. output_completeness: Does the repair-brief have all required fields (severity, classification, location, etc.)?
5. overall_judgment: Overall quality of review protocol compliance.

=== OUTPUT (return ONLY this JSON) ===
{{"bug_detection": <1-5>, "triage_quality": <1-5>, "role_discipline": <1-5>, "output_completeness": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _find_repair_brief(sandbox: Path) -> str:
    ia = sandbox / "_bmad-output" / "implementation-artifacts"
    if not ia.exists():
        return "(no repair-brief)"
    for f in sorted(ia.glob("repair-brief-*.md")):
        return f.read_text()
    return "(no repair-brief)"


def _read_spec_status(sandbox: Path) -> str:
    spec = sandbox / "_bmad-output" / "implementation-artifacts" / "spec-quota-calc.md"
    if not spec.exists():
        return "(no spec)"
    content = spec.read_text()
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                return f"status={fm.get('status', '?')}, followup={fm.get('followup_review_recommended', '?')}"
            except Exception:
                return parts[1].strip()
    return "(no frontmatter)"


def _extract_json(text):
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def judge_model(stdout, repair_brief, spec_status, modified, judge_model_id, timeout=240):
    prompt = JUDGE_PROMPT.format(stdout=stdout[:4000], repair_brief=repair_brief[:4000], spec_status=spec_status[:2000], modified_files=modified[:2000])
    try:
        result = subprocess.run(
            ["opencode", "run", "--pure", "--model", judge_model_id, "--auto", "--format", "json", prompt],
            capture_output=True, text=True, timeout=timeout, cwd="/tmp",
        )
    except subprocess.TimeoutExpired:
        return {"error": "judge_timeout", "overall": 0}
    except FileNotFoundError:
        return {"error": "opencode_not_found", "overall": 0}
    texts = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "text":
            texts.append(evt.get("part", {}).get("text", ""))
    return _extract_json("\n".join(texts)) or {"error": "unparseable", "overall": 0}


def judge_run(run_dir, judge_model_id, timeout=240):
    verdicts = {}
    for model_dir in sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL):
        repair_brief = _find_repair_brief(model_dir)
        spec_status = _read_spec_status(model_dir)
        stdout = ""
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                for r in manifest.get("results", []):
                    if model_dir.name in r.get("model", ""):
                        stdout = r.get("stdout", "") + r.get("stderr", "")
            except Exception:
                pass
        modified = []
        for f in model_dir.rglob("*"):
            if f.is_file() and ".git" not in str(f):
                modified.append(str(f.relative_to(model_dir)))
        modified_str = "\n".join(sorted(modified)[:50])

        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        verdict = judge_model(stdout, repair_brief, spec_status, modified_str, judge_model_id, timeout)
        verdicts[model_dir.name] = verdict
        print(f"[judge] {model_dir.name}: overall={verdict.get('overall', '?')}", flush=True)
    return verdicts


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--latest", action="store_true")
    g.add_argument("--run-dir", type=Path)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.run_dir:
        run_dir = args.run_dir
    else:
        runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True) if RUNS_BASE.exists() else []
        if not runs:
            raise SystemExit(f"No runs under {RUNS_BASE}")
        run_dir = runs[0]
    verdicts = judge_run(run_dir, args.judge_model, args.timeout)
    out = args.json_out or (run_dir / "judge_verdicts.json")
    out.write_text(json.dumps({"run_dir": str(run_dir), "judge_model": args.judge_model, "verdicts": verdicts}, indent=2))
    for n, v in verdicts.items():
        print(f"  {n}: overall={v.get('overall', '?')}  {v.get('verdict', v.get('error', ''))}")


if __name__ == "__main__":
    main()
