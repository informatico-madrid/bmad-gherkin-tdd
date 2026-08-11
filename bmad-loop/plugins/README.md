# Generic quality gates plugin template for bmad-loop.
#
# This is a template for a bmad-loop plugin that adds TDD/Gherkin gates to a loop.
# Copy to {project}/.bmad-loop/plugins/<name>/ and rename the classes/functions;
# fill in the project-specific commands (mutation, test, contracts check).
#
# Pattern reference: the upstream bmad-loop plugin surface (plugin.toml declaring
# pre_story / post_worktree_setup / pre_commit hooks). A full working implementation
# is project-specific; this template documents the seams.

# plugin.toml
# ---
# [plugin]
# name = "<name>-gates"
# version = "0.1.0"
# hooks = ["pre_story", "post_worktree_setup", "pre_commit"]
# ---

# bmad_loop_plugin.py (illustrative)
#
# from bmad_loop.plugins import Hook
#
# class GherkinGate(Hook):
#     def pre_story(self, story_key: str, worktree: str) -> None:
#         # Require a signed contract before dev:
#         #   {worktree}/tests/contracts/{story_key}.feature with '# Status: APPROVED'
#         raise_not_approved = NotImplementedError
#
#     def post_worktree_setup(self, worktree: str) -> None:
#         # Optionally symlink the project's harness-quality-gate sibling etc.
#         pass
#
#     def pre_commit(self, worktree: str, diff_files) -> None:
#         # Run mutation gate + anti-fixture grep + test suite.
#         run_mutation = NotImplementedError
