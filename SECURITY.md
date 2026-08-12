# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

Only the latest released minor version receives security fixes. There is no
other support matrix at this time.

## Reporting a vulnerability

Please do **not** open a public issue for security vulnerabilities. Report them
privately by opening a [GitHub security advisory](https://github.com/informatico-madrid/bmad-gherkin-tdd/security/advisories/new)
(or email the maintainers if the repository does not yet have advisories enabled).

You can expect an acknowledgement within 48 hours and a triage decision within
one week. We will coordinate a fix and a release, and credit you in the advisory
unless you prefer to stay anonymous.

## Security notes for this module

- `hooks/tdd_cycle_gate.py` runs with the privileges of the coding CLI that invokes it.
  In loop mode (`BMAD_LOOP_MODE=1`) it fails **closed** on internal errors; outside loop
  mode it fails **open** so it can never brick a non-TDD workflow. Do not weaken either.
- State files under `.bmad-harness/` are treated as trusted gate state: symlinked state
  or lock files are denied before any write.
- The installer only writes files it recorded in `_bmad/gherkin-tdd/install.json`, and
  refuses to delete files that changed since install.
- The gate never executes the analysed content; Bash writes are blocked, not shell-executed.
