"""bmad-gherkin-tdd — contract-first TDD methodology module for BMAD.

The module is primarily a skills/config bundle plus an installer CLI:

    bmad-gherkin-tdd install --project .

Run ``bmad-gherkin-tdd --help`` for the full surface.
"""

__version__ = "0.1.0"

from . import cli  # noqa: E402,F401  (re-export so `python -m bmad_gherkin_tdd` works)

__all__ = ["__version__", "cli"]
