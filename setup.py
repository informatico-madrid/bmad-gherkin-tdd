"""Build shim: copy the module payload into the wheel.

The distribution is self-contained: ``build_py`` stages the payload
(``skills/``, ``templates/``, ``hooks/``, ``scripts/``, ``docs/``,
``opencode/``, ``bmad-loop/``, ``setup/``) into
``build/lib/bmad_gherkin_tdd/payload/`` so the installed ``bmad-gherkin-tdd``
CLI can install the module from the wheel without a source checkout.

Project metadata lives in ``pyproject.toml`` (PEP 621); this file only adds the
build command.
"""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

_PAYLOAD_DIRS = (
    "skills",
    "templates",
    "hooks",
    "scripts",
    "docs",
    "opencode",
    "bmad-loop",
    "setup",
)


class _BuildPyWithPayload(build_py):
    """build_py that additionally stages the module payload into the package."""

    def run(self) -> None:
        super().run()
        root = Path(__file__).parent
        target = Path(self.build_lib) / "bmad_gherkin_tdd" / "payload"
        for name in _PAYLOAD_DIRS:
            src = root / name
            if not src.is_dir():
                continue
            self.copy_tree(str(src), str(target / name))


setup(cmdclass={"build_py": _BuildPyWithPayload})
