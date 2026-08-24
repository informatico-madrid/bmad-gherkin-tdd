---
status: in-review
story_key: 4-2-quota-dispatch
---

# Story 4-2: Quota Dispatch

## Frozen After Approval

The system SHALL dispatch records through a policy spec, accepting records
that meet ALL of the following criteria and rejecting all others:

- `record.score >= spec.threshold` → accept (inclusive threshold)
- `record.active AND record.visible` → accept (both must be true)
- `record.kind NOT IN spec.deny` → accept
- `record.kind IN spec.allow` → accept (if allow is set)
- Records that fail ANY criterion are rejected

The dispatch function returns `(accepted, rejected, total_weight)` where
`total_weight` is the sum of `record.weight` for accepted records only.

**Edge case clarification needed:** The spec does not clarify behavior when
a record is both in `spec.allow` and in `spec.deny`. The implementation
must choose: does `deny` take precedence over `allow`, or does `allow`
take precedence? This ambiguity caused a CRITICAL escalation during review.

## Review Triage Log

The review session attempted to implement "deny takes precedence" but the
spec's `@s5` scenario only tests `kind not in allow` (rejection), not the
case where kind appears in BOTH allow and deny. The session could not
determine the intended behavior and escalated.

## Test Matrix

| @s | Given | When | Then |
|----|-------|------|------|
| @s1 | score=50, threshold=50 | apply | accepted (>=) |
| @s5 | kind="spam", allow=["work"], deny=["spam"] | apply | rejected |

## Acceptance Criteria

1. Records with score >= threshold are accepted
2. Records with score < threshold are rejected
3. The allow/deny precedence is deterministic and documented
