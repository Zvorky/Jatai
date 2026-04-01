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
8. Keep `pyproject.toml` as the source of truth for Python dependencies:
   - Add new external library dependencies immediately to `[project].dependencies` in `pyproject.toml` when they are first used.
   - Update versions in `pyproject.toml` when upgrading packages and remove unused dependencies there.
   - If a `requirements.txt` file is needed for pinned environment reproducibility, generate or update it from `pyproject.toml` (for example via `pip-tools` ou `poetry export`).
   - Maintain consistency between `pyproject.toml` and any generated `requirements.txt` files; prefer `pyproject.toml` for packaging and distribution.
9. Keep all explicit project version citations synchronized whenever the version changes:
   - Run `tools/set_version <new_version>` instead of editing version references manually.
   - At minimum, keep `pyproject.toml`, `src/jatai/__init__.py`, `README.md`, `docs/jatai.1`, and `tools/set_version` aligned with the same current version.
   - Verify the replacement result after running the script (for example with `rg` and targeted file checks).
10. Whenever a new explicit project version citation is added in any file, register that file/pattern in `tools/set_version` (`VERSION_TARGETS`) in the same change set.
11. User-facing documentation under `docs/` must not reference ADRs or architecture/requirements governance artifacts.
   - Do NOT reference `ARCHITECTURE.md`, `REQUIREMENTS.md`, or ADR identifiers (for example, `ADR 13`) inside `docs/`.
   - Keep `docs/` focused on end-user operation and behavior; governance/design rationale belongs to developer-facing files.
12. Before creating any commit, the agent must explicitly classify it by asking: **"Is this commit code or documentation?"**
   - If the commit is **documentation-only**, no version bump is required.
   - If the commit includes **any code, tests, packaging, dependency, tooling, schema, or behavior change**, it is a **code commit** and the version bump must happen before the commit.
   - Mixed commits (code + documentation) are treated as **code commits**.
13. Every pending architecture/requirements decision that implies implementation work must be represented in `ToDo.md` as explicit actionable task(s) before implementation starts.
   - Do not leave ADR/REQUIREMENTS implementation implications implicit.
   - Add missing tasks immediately when a pending requirement/ADR is identified.
14. After implementing any code/behavior change, the agent must update all affected user-facing documentation under `docs/` before creating a commit.
   - Documentation in `docs/` must reflect the implemented behavior, command surface, options, and examples.
   - This documentation update is mandatory for code commits and must happen before the commit step.

## Architecture & Requirements Governance

1. The agent must not make architecture or requirements decisions on its own.
2. If there is ambiguity, conflict, or lack of definition, the agent must ask the user how to proceed before implementing.
3. Exception: Only decide on its own when the user explicitly requests it.
4. Tasks tagged `[ARCH]` in `ToDo.md` are **not implementation tasks** — they represent open architecture decisions. The agent must **never implement** an `[ARCH]` task; instead, it must present the question or decision point directly to the user and wait for explicit direction before proceeding.

## ARCHITECTURE/REQUIREMENTS → ToDo Synchronization Rule

Whenever `ARCHITECTURE.md` or `REQUIREMENTS.md` are changed:

1. Review the impact on the implementation plan.
2. Add or update pending tasks in `ToDo.md` according to the impact.
3. Keep the list ordered by phase and priority.
4. Explicitly inform the user about created/updated tasks.

When reviewing pending ADR/requirement items:

5. If an ADR/requirement defines behavior that is not fully implemented yet, add explicit implementation task(s) to `ToDo.md` even when no file in `ARCHITECTURE.md` or `REQUIREMENTS.md` was changed in that turn.

## ADR / REQ Reference Rules

- All architecture decisions in `ARCHITECTURE.md` MUST use the `[ADR-x]` header format and decision items MUST use `[ADR-x.y]` unique identifiers.
- All requirements in `REQUIREMENTS.md` MUST use the `[REQ-x]` identifiers for top-level groups and `[REQ-x.y]` for subitems.
- When mapping a user prompt to `ToDo.md`, every task that implements, fixes, or depends on an ADR or a REQ MUST include a `Related:` reference listing the exact identifier(s). Example:
   - `- [ ] Implement feature X`
      - `Related: [ADR-3], [REQ-2.1]`
- Do NOT add ADR prefixes to content items explicitly marked as "Context" inside `ARCHITECTURE.md` — context notes are documentation only and are not ADR entries.
- Do NOT create, rename, or merge ADR/REQ identifiers without explicit user approval. Propose identifier changes and get approval before applying them.
- Tasks in `ToDo.md` marked with `[ARCH]` are architecture decision placeholders and MUST NOT be implemented unless the user converts them to actionable tasks and provides ADR/REQ references.

## Quick Operational Checklist

- Read `ARCHITECTURE.md` and `REQUIREMENTS.md`.
- Locate related tasks in `ToDo.md`.
- Execute implementation without deciding architecture/requirements without authorization.
- Update `ToDo.md` and `README.md`.
- Ensure user-facing `docs/` content is updated to match implemented behavior before committing.
- Ensure "File Structure" section is updated in `README.md` with only non-ignored system files (excluding project governance/documentation files).
- Ensure pending ADR/requirements implications are reflected as explicit actionable tasks in `ToDo.md`.
- Classify the pending commit by asking: "Is this commit code or documentation?"
- For code commits, update `pyproject.toml` version using `MAJOR.PHASE.ITERATION` before report/commit.
- For code commits, run `tools/set_version <new_version>` and verify all version citations were updated correctly.
- Report changes and pending items to the user.
- **Always activate the Python virtual environment (venv) before running any tests or using Python commands.**

## Language Requirements

**All code comments, documentation, commit messages, and code strings must be written in English.**

This ensures consistency, maintainability, and accessibility across the entire codebase for any contributor or maintainer.

## Testing Requirements & Validation Before Task Completion

### Scope Exception for Development Tools (`tools/`)

When the agent is working exclusively on development tooling under `tools/` (without implementing product/runtime tasks from `ToDo.md`):

1. The task-completion workflow in this document (automated test gate, `pytest.log`, OUTBOX report, task completion tracking, and mandatory commit flow) does **not** apply.
2. Instead, the agent must perform **safe manual validation** of the modified tool/script, documenting command(s) executed and observed behavior in the final user summary.
3. Manual validation must avoid unsafe/destructive side effects (for example, no irreversible deletes outside isolated test paths).

### Mandatory Test Coverage

1. **Keep pytest suites updated** whenever code is implemented, modified, or refactored.
2. **Write exhaustive tests** covering three categories for every feature:
   - **Happy Path:** Normal execution scenarios with valid inputs and expected behavior.
   - **Error/Failure Scenarios:** Invalid inputs, edge cases, I/O failures, timeout conditions, and resource exhaustion.
   - **Malicious/Adversarial Scenarios:** Intentional abuse attempts (e.g., path traversal, injection attacks, race conditions, unauthorized access).
3. **Test location:** All tests must reside in `./tests/` directory, organized by module structure.
4. **Test framework:** Use `pytest` (as specified in REQUIREMENTS.md).

5. **Test-first synchronization requirement:** Before implementing any code that changes behavior defined by an ADR or `REQUIREMENTS.md`, update the automated pytest suites and the manual test scripts to encode the expected behavior as tests (these act as executable requirements/specs). The updated tests must be committed (or staged) alongside the `ToDo.md` tasks that describe the implementation work. This ensures tests define the acceptance criteria before code changes begin.

### Task Completion Validation Protocol

**Before marking any task as completed in `ToDo.md`:**

1. Run unit tests for all modified/new code:
   ```bash
   pytest ./tests/ -v --tb=short > pytest.log 2>&1
   ```
2. Verify all tests pass (exit code 0).
3. Save the output to `pytest.log` in the repository root.
4. In addition to the unit/test-suite run above, always execute the full test matrix before marking completion:
   - Run the full `pytest` suite across the repository (`pytest ./tests/`) and confirm exit code 0.
   - Run the manual test helper script and save its output to `manual-tests.log`:
      ```bash
      ./tools/manual_test_helper.sh > manual-tests.log 2>&1 || true
      ```
   - Verify `manual-tests.log` shows the full manual validation passes for the changed areas. If manual tests fail, do NOT mark the task as completed.
4. If any test fails:
   - Do NOT mark the task as completed.
   - Fix the implementation.
   - Re-run tests and save new results to `pytest.log`.
5. Include `pytest.log` in the summary when reporting task completion to the user.
6. Include `manual-tests.log` alongside `pytest.log` in the OUTBOX report when reporting task completion.

### Test Quality Standards

- Tests must be **deterministic:** Same code and test inputs always produce the same results.
- Tests must be **isolated:** No test should depend on or affect the execution of another test.
- Tests must cover **boundary conditions:** Off-by-one errors, empty collections, null values, maximum/minimum values.
- Tests must verify **side effects:** File system changes, state modifications, external calls.
- Use descriptive test names: `test_<function>_<scenario>_<expected_outcome>()` pattern.

### Manual Testing Protocol

### File-System First Design

Jatai is a **file-system first** system. Agents must preserve this principle in implementation, validation, and documentation.

1. The **primary interface** is the filesystem itself:
   - dropping files into `OUTBOX/`
   - receiving files in `INBOX/`
   - renaming files to apply/remove prefixes
   - renaming `.jatai` to `._jatai` and back for node lifecycle control
2. The CLI is a **secondary convenience tool**, mainly for initialization, inspection, and operator ergonomics.
3. Manual validation must prefer **direct filesystem operations** over CLI wrappers whenever the use case is fundamentally file-driven.
4. Verification must focus on **filesystem state**, for example:
   - `find`, `ls`, checksums, file counts, file names, and file contents
   - presence/absence of prefixed files
   - presence/absence of `.jatai` / `._jatai`
5. Tests and reports must make clear whether they validated:
   - direct filesystem behavior
   - daemon-mediated behavior
   - CLI convenience behavior
6. When a manual test can be written as a direct file operation, prefer that over testing only CLI output.
7. Documentation and helper scripts should reflect this architecture explicitly.

**After automated tests pass**, perform an end-to-end manual validation:

0. **Use the manual test helper script as the default execution path:**
   - Prefer updating and running `tools/manual_test_helper.sh` instead of performing ad-hoc command-by-command tests directly in terminal.
   - The script execution output is saved to `./manual-tests.log` (in the directory where it is executed).
   - When manual testing requirements evolve, update this script in the same change set so future runs stay reproducible.

1. **Install the project** following the instructions in `README.md` exactly (e.g., `pip install -e .` or the documented install command).

2. **Set up a test environment** using at least two node addresses under a local temporary directory (`./tmp_tests/`), for example:
   ```bash
   export JATAI_TEST_A=./tmp_tests/node_a
   export JATAI_TEST_B=./tmp_tests/node_b
   mkdir -p "$JATAI_TEST_A" "$JATAI_TEST_B"
   ```

3. **Run every documented command** from `README.md` (and any other user-facing documentation):
   - Execute each command against the test nodes.
   - Capture the full terminal output (stdout + stderr).
   - Verify behavior matches the documented description.

4. **Capture and record results:**
   - Include command invocations and their output in the `OUTBOX/` report.
   - Add a dedicated manual testing summary in the report covering: tested scopes, observed errors/failures, and an overall assessment.
   - Note any discrepancy between documented and actual behavior.
   - If a command fails or behaves unexpectedly, fix the implementation before proceeding.

5. **Clean up after manual tests:**
   ```bash
   rm -rf "$JATAI_TEST_A" "$JATAI_TEST_B"
   ```
   All files and directories created during manual testing under `./tmp_tests/` must be deleted before the final commit.

## Project Versioning Policy

Versioning must strictly follow this scheme:

- **Format:** `MAJOR.PHASE.ITERATION`
- **Current channel:** While in `alpha`, versions stay in `0.x.x`.
- **MAJOR:** Updated **only** when explicitly requested by the user (manual decision).
- **PHASE:** Must match the current implementation phase in `ToDo.md` (e.g., if current phase is 4, use `0.4.x`).
- **ITERATION:** Incremented on each commit iteration for the same phase (patch-like counter).
- **Source of truth:** Update `pyproject.toml` `[project].version` before reporting and committing.

Commit classification gate:

- Before creating any commit, the agent must explicitly ask itself: **"Is this commit code or documentation?"**
- **Documentation-only commit:** Changes limited to documentation/governance text with no source, test, packaging, dependency, script, schema, or runtime-behavior impact. No version bump is required.
- **Code commit:** Any commit that changes source code, tests, packaging metadata, dependencies, scripts, schemas, operational behavior, or mixes code with documentation. A version bump is required before the commit.
- When uncertain, classify the commit as a **code commit** and perform the bump.

Branch flow constraints:

- Work normally happens in `dev`.
- Merging stable changes into `main` is only allowed when explicitly requested by the user.
- The agent must not trigger merge/release actions to `main` without that explicit request.

## Git Workflow & Final Reporting

The workflow in this section applies to implementation tasks tied to `ToDo.md`. For changes scoped exclusively to development tools under `tools/`, follow the exception defined in **"Scope Exception for Development Tools (`tools/`)"**.

### After All Tests Pass

1. **Verify implementation against ARCHITECTURE and REQUIREMENTS:**
   - Ensure all code changes align with `ARCHITECTURE.md` design decisions.
   - Verify all functional requirements from `REQUIREMENTS.md` are met or documented as pending.
   - If deviations exist, document them in the report or update ARCHITECTURE/REQUIREMENTS as needed.
   - Do NOT commit code that violates established architecture without explicit user authorization.

2. **Update project version before report/commit:**
   - First classify the pending commit by asking: **"Is this commit code or documentation?"**
   - If the answer is **documentation-only**, skip the version bump and continue with the remaining applicable workflow steps.
   - If the answer is **code** (or mixed code + documentation), the version bump is mandatory before the commit.
   - Apply the `MAJOR.PHASE.ITERATION` rule from this document.
   - Keep `MAJOR` unchanged unless the user explicitly requested a major bump.
   - Set `PHASE` to the current `ToDo.md` phase being executed.
   - Increment `ITERATION` for each new commit in that same phase.
   - Run `tools/set_version <new_version>` before creating the report and commit.
   - Verify every explicit version citation was correctly updated across code/docs after running the script.

3. **Create a comprehensive .md report** in the `OUTBOX/` directory containing:
   - Summary of changes made.
   - Test results from `pytest.log`.
   - Manual testing summary (tested scopes, errors/failures found, and overall validation view).
   - `manual-tests.log` alongside `pytest.log`.
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
    - Also exclude `manual-tests.log` from commits; these logs should be included in the `OUTBOX/` report but not committed to the repository.

7. **Documentation sweep requirement:** After tests pass and before final report/merge, perform a full documentation sweep:
   - Update all affected files under `docs/` and `README.md` so they reflect implemented behavior and public command surfaces.
   - Conduct a documentation review across `docs/`, `README.md`, and `ARCHITECTURE.md` / `REQUIREMENTS.md` to ensure consistency and that no docs reference outdated ADRs or behaviors.
   - Only after documentation is updated and reviewed should the final OUTBOX report be generated and the commit considered complete.

### Final User Summary

When reporting task completion, include:
- Task(s) marked as completed in `ToDo.md`.
- Files updated (including `pytest.log` path for test verification).
- Git commit hash and message.
- Link to the report in `OUTBOX/` if created.