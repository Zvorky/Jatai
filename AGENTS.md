# AGENTS.md

This file defines mandatory rules for any agent executing development tasks in this repository.

## Mandatory Rules by Task

1. Before implementing any change, read `ARCHITECTURE.md` and `REQUIREMENTS.md`.
2. Map the user's prompt to pending tasks in `ToDo.md`.
3. Prioritize execution according to the `ToDo.md` structure: by implementation phase and by priority within the phase.
4. Keep `ToDo.md` updated during the task:
   - Mark progress of related tasks.
   - Create/adjust tasks when necessary.
   - Preserve organization by phases and priority.
5. Keep `README.md` updated whenever there is functional, usage, architecture, or folder structure impact.
6. Always keep the "File Structure" section in `README.md` updated.
   - If the section does not exist yet, create it on the first structure update.
   - Keep this section exclusive to system files/directories relevant to runtime/build/development flow.
   - The `docs/` directory is the only documentation directory allowed there, because it is part of the runtime documentation system.
   - Do NOT include project governance/documentation files there (for example `AGENTS.md`, `ARCHITECTURE.md`, `REQUIREMENTS.md`, `ToDo.md`, `README.md`, `LICENSE`).
   - Do NOT include developer-only utility directories (for example `tools/`).
   - Do NOT include paths ignored by `.gitignore`.
7. When finishing, explicitly inform the user:
   - Which files were updated.
   - Which tasks in `ToDo.md` were changed.
   - If there was an update to `README.md` (including "File Structure").
8. Keep Python dependencies file (`requirements.txt` or `pyproject.toml`) always updated:
   - Add new external library dependencies immediately when they are first used.
   - Update versions when upgrading packages.
   - Remove dependencies no longer in use.
   - Maintain consistency with code changes.
9. Keep all explicit project version citations synchronized whenever the version changes:
   - Run `tools/set_version <new_version>` instead of editing version references manually.
   - At minimum, keep `pyproject.toml`, `src/jatai/__init__.py`, `README.md`, `docs/jatai.1`, and `tools/set_version` aligned with the same current version.
   - Verify the replacement result after running the script (for example with `rg` and targeted file checks).
10. Whenever a new explicit project version citation is added in any file, register that file/pattern in `tools/set_version` (`VERSION_TARGETS`) in the same change set.

## Architecture & Requirements Governance

1. The agent must not make architecture or requirements decisions on its own.
2. If there is ambiguity, conflict, or lack of definition, the agent must ask the user how to proceed before implementing.
3. Exception: Only decide on its own when the user explicitly requests it.

## ARCHITECTURE/REQUIREMENTS → ToDo Synchronization Rule

Whenever `ARCHITECTURE.md` or `REQUIREMENTS.md` are changed:

1. Review the impact on the implementation plan.
2. Add or update pending tasks in `ToDo.md` according to the impact.
3. Keep the list ordered by phase and priority.
4. Explicitly inform the user about created/updated tasks.

## Quick Operational Checklist

- Read `ARCHITECTURE.md` and `REQUIREMENTS.md`.
- Locate related tasks in `ToDo.md`.
- Execute implementation without deciding architecture/requirements without authorization.
- Update `ToDo.md` and `README.md`.
- Ensure "File Structure" section is updated in `README.md` with only non-ignored system files (excluding project governance/documentation files).
- Update `pyproject.toml` version using `MAJOR.PHASE.ITERATION` before report/commit.
- Run `tools/set_version <new_version>` and verify all version citations were updated correctly.
- Report changes and pending items to the user.

## Language Requirements

**All code comments, documentation, commit messages, and code strings must be written in English.**

This ensures consistency, maintainability, and accessibility across the entire codebase for any contributor or maintainer.

## Testing Requirements & Validation Before Task Completion

### Mandatory Test Coverage

1. **Keep pytest suites updated** whenever code is implemented, modified, or refactored.
2. **Write exhaustive tests** covering three categories for every feature:
   - **Happy Path:** Normal execution scenarios with valid inputs and expected behavior.
   - **Error/Failure Scenarios:** Invalid inputs, edge cases, I/O failures, timeout conditions, and resource exhaustion.
   - **Malicious/Adversarial Scenarios:** Intentional abuse attempts (e.g., path traversal, injection attacks, race conditions, unauthorized access).
3. **Test location:** All tests must reside in `./tests/` directory, organized by module structure.
4. **Test framework:** Use `pytest` (as specified in REQUIREMENTS.md).

### Task Completion Validation Protocol

**Before marking any task as completed in `ToDo.md`:**

1. Run unit tests for all modified/new code:
   ```bash
   pytest ./tests/ -v --tb=short > pytest.log 2>&1
   ```
2. Verify all tests pass (exit code 0).
3. Save the output to `pytest.log` in the repository root.
4. If any test fails:
   - Do NOT mark the task as completed.
   - Fix the implementation.
   - Re-run tests and save new results to `pytest.log`.
5. Include `pytest.log` in the summary when reporting task completion to the user.

### Test Quality Standards

- Tests must be **deterministic:** Same code and test inputs always produce the same results.
- Tests must be **isolated:** No test should depend on or affect the execution of another test.
- Tests must cover **boundary conditions:** Off-by-one errors, empty collections, null values, maximum/minimum values.
- Tests must verify **side effects:** File system changes, state modifications, external calls.
- Use descriptive test names: `test_<function>_<scenario>_<expected_outcome>()` pattern.

## Project Versioning Policy

Versioning must strictly follow this scheme:

- **Format:** `MAJOR.PHASE.ITERATION`
- **Current channel:** While in `alpha`, versions stay in `0.x.x`.
- **MAJOR:** Updated **only** when explicitly requested by the user (manual decision).
- **PHASE:** Must match the current implementation phase in `ToDo.md` (e.g., if current phase is 4, use `0.4.x`).
- **ITERATION:** Incremented on each commit iteration for the same phase (patch-like counter).
- **Source of truth:** Update `pyproject.toml` `[project].version` before reporting and committing.

Branch flow constraints:

- Work normally happens in `dev`.
- Merging stable changes into `main` is only allowed when explicitly requested by the user.
- The agent must not trigger merge/release actions to `main` without that explicit request.

## Git Workflow & Final Reporting

### After All Tests Pass

1. **Verify implementation against ARCHITECTURE and REQUIREMENTS:**
   - Ensure all code changes align with `ARCHITECTURE.md` design decisions.
   - Verify all functional requirements from `REQUIREMENTS.md` are met or documented as pending.
   - If deviations exist, document them in the report or update ARCHITECTURE/REQUIREMENTS as needed.
   - Do NOT commit code that violates established architecture without explicit user authorization.

2. **Update project version before report/commit:**
   - Apply the `MAJOR.PHASE.ITERATION` rule from this document.
   - Keep `MAJOR` unchanged unless the user explicitly requested a major bump.
   - Set `PHASE` to the current `ToDo.md` phase being executed.
   - Increment `ITERATION` for each new commit in that same phase.
   - Run `tools/set_version <new_version>` before creating the report and commit.
   - Verify every explicit version citation was correctly updated across code/docs after running the script.

3. **Create a comprehensive .md report** in the `OUTBOX/` directory containing:
   - Summary of changes made.
   - Test results from `pytest.log`.
   - Files modified/created.
   - Tasks completed in `ToDo.md`.
   - Any breaking changes or migration notes.

4. **Commit your changes** to git:
   ```bash
   git add <modified files>
   git commit -m "<clear commit message describing changes>"
   ```
   - Keep commits atomic and focused on a single feature or fix.
   - If multiple tasks were implemented **in parallel**, commit only your own changes; avoid committing work from other concurrent tasks.
   - Commit message format: Start with a verb (e.g., "Add", "Fix", "Refactor"), include the task reference if applicable, and provide context.
   - **Commit messages must be short and direct.** If needed, split into multiple atomic commits rather than creating large messages.
   - Each commit should clearly describe a single logical change or feature.

5. **Exclude pytest.log from git** if not already in `.gitignore`:
   - The `pytest.log` file is for local validation only and should not be committed.

### Final User Summary

When reporting task completion, include:
- Task(s) marked as completed in `ToDo.md`.
- Files updated (including `pytest.log` path for test verification).
- Git commit hash and message.
- Link to the report in `OUTBOX/` if created.