# AGENTS.md

Instructions for AI coding agents working on this project. Follow these rules exactly.

## Golden Rule

Every commit must leave the codebase in a passing state: lint clean, tests green, coverage at or above 80%.

## Before You Write Code

1. **Read the relevant source files** before proposing changes. Understand existing patterns.
2. **Check `CLAUDE.md`** for architecture, conventions, and test mapping.
3. **Check `todos/`** for known issues and their priority. Do not duplicate work already tracked there.
4. **Understand the plugin pattern.** Driver code lives in `etc/dbus-serialinverter/`. The `Inverter` base class defines the contract — all inverter implementations extend it.

## Code Quality Standards

- Target Python 3.8+ compatibility (VenusOS constraint). Use `dataclasses`, f-strings with `=` debug specifier, walrus operator, and other 3.8+ features freely.
- Max line length: 120 characters (enforced by ruff).
- Follow existing code style. Do not add type annotations, docstrings, or comments to code you did not change.
- Do not over-engineer. Fix what is asked. Do not refactor adjacent code, add abstractions, or introduce patterns that do not already exist in the codebase.
- Do not modify vendored code in `etc/dbus-serialinverter/pymodbus/`.

## Separation of Concerns in Commits

Each commit must be a single logical change. This is non-negotiable.

**One commit per concern:**
- A bug fix is one commit.
- Its corresponding test is part of that same commit (fix + test travel together).
- A refactor is a separate commit from a bug fix, even if they touch the same file.
- A new inverter driver is one commit. Registering it in `supported_inverter_types` is part of that commit.
- Lint-only fixes (whitespace, import ordering) are their own commit, separate from functional changes.
- Documentation updates are their own commit.

**Do not mix:**
- Bug fixes with unrelated refactors.
- Multiple independent bug fixes in one commit.
- Functional changes with formatting changes.
- Test additions with unrelated test modifications.

**Commit message format:**
- First line: imperative mood, under 72 characters (e.g., `fix position typo in Inverter base class`)
- Blank line, then body if needed explaining *why*, not *what*.
- Reference the todo number if applicable (e.g., `Resolves todo 001`).

## Verify, Validate, Lint — Every Time

Run these commands after every change, before every commit. Both must pass.

```bash
# 1. Lint
ruff check etc/dbus-serialinverter/*.py tests/

# 2. Tests with coverage
python -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80
```

**If lint fails:** Fix the lint errors. Do not suppress warnings with `# noqa` unless you have a specific, documented reason.

**If tests fail:** Fix the failing test or the code that broke it. Do not skip tests. Do not lower the coverage threshold.

**If coverage drops below 80%:** Add tests for the new or changed code before committing.

## Writing Tests

- Every bug fix and new feature requires a test.
- Test files go in `tests/` and follow the naming pattern `test_NNN_description.py`.
- Each test file must stub out VenusOS/D-Bus packages so it runs without hardware. Follow the stub pattern in existing test files (patch `sys.modules` before importing driver code).
- Each test file must have a `__main__` block so it can run standalone: `python tests/test_NNN_description.py`.
- Test the behavior, not the implementation. Assert on observable outcomes.

## Commit Workflow

After making changes:

1. **Lint:** `ruff check etc/dbus-serialinverter/*.py tests/`
2. **Test:** `python -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80`
3. **Review the diff:** `git diff` — confirm only intended changes are staged.
4. **Stage specific files:** `git add <files>` — do not use `git add -A` or `git add .`.
5. **Commit** with a clear message.
6. **Verify post-commit:** `git status` to confirm a clean working tree for that change.

Repeat for each logical change. Do not batch unrelated changes.

## What Not To Do

- Do not commit `.env`, `credentials.json`, `token.json`, or any secrets.
- Do not commit changes to vendored `pymodbus/`.
- Do not create new files when editing an existing file achieves the goal.
- Do not push to `master` without a pull request.
- Do not amend commits that have already been pushed.
- Do not use `--no-verify` to bypass hooks.
- Do not lower the coverage threshold or add `# pragma: no cover` without justification.
- Do not introduce new dependencies. This runs on resource-constrained VenusOS devices.
