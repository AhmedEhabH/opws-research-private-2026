> **CURRENT PHASE (2026-09-22):** WP-1b selection-only agent comparison
> (MAIN_297 + variance 15x3 + scoring), then WP-2 / E2E-G6. The single
> current-state source is the LIVE STATUS block in `README.md`, generated from
> `docs/LIVE_STATUS.json`. The historical release-facts trail (v0.9.x pilot /
> preflight closures) moved verbatim to
> `docs/history/AGENTS_RELEASE_FACTS_ARCHIVE_2026-09-22.md`; it is NOT current
> guidance.

# AGENTS.md — Dependency-Aware Selective Regeneration Benchmark

## Project facts

- **Language:** Python 3.11
- **Source:** `src/benchmark/`
- **Entry:** `seven_arm_benchmark.py`
- **Tests:** Pytest (test suite under `tests/`)
- **Lint:** Ruff (pyproject.toml config)
- **Types:** Mypy strict (`pyproject.toml`)
- **Kaggle:** generated code under `kaggle_upload/code/`
- **Bundle:** `scripts/build_upload_bundle.py`
- **Docs:** `docs/`
- **Updates:** ledgers under `selective_updates/`

## Working rule

inspect minimally → edit narrowly → changed-file diagnostics → affected tests → full validation only at final gate

## Context rules

Start with:
```
git status --short
git diff --stat
git diff --name-only
```

Use exact searches before reading whole files. Read only:
- changed files
- related symbols
- directly affected tests
- necessary configuration (pyproject.toml)

Do not read entire repository, generated code (unless verifying derivatives), datasets, large logs, or unrelated documentation.

## Large-file reading rule

`DECISIONS.md` (~210 KB), `TODO.md` (~190 KB), `00_CURRENT_RESEARCH_STATE.md`
(~120 KB) and `docs/RESEARCH_JOURNEY.md` are append-only records. Never read
them whole: `grep`/`Select-String` for the section you need, then read only that
range. Append new decisions at the end of `DECISIONS.md`.

## Visible TODO progress (standing)

- Update the visible TODO checklist immediately after each completed phase or
  subphase, and whenever the active item changes.
- Keep exactly one item `in_progress`; mark finished items completed at once;
  keep the remaining major items visible.
- Long paid runs are CHUNKED (`--max-items N --resume`, one chunk per tool call,
  <= 45 min per call). After every chunk, update the TODO with the progress line
  from `progress.json`, e.g. `MAIN_297 — 120/297 complete · $2.31`.
- Never block a single tool call on a multi-hour process.

NATIVE TODO — MANDATORY FOR EVERY MULTI-STEP TASK

For every task with 2+ execution steps:

1. The FIRST tool call of the execution phase MUST be native `todowrite`.
2. No shell/read/edit work beyond minimal task identification may begin before
   the Todo exists.
3. Keep exactly one item in_progress.
4. Update native Todo before and after every atomic step.
5. For long work, expose live counts: x/y, chunk a/b, task name.
6. Persist detailed progress separately, but native Todo is mandatory UI state.
7. If native Todo is unavailable, report TODO_UI_UNAVAILABLE explicitly.

This requirement applies to every future Mission automatically.

## Long-running commands (standing)

- Full pytest suite: ~50+ min on Ahmed's workstation. Tool timeout
  5,400,000 ms (90 min). Run it once, at the final validation gate, or while a
  network-bound paid chunk loop is NOT running in the same call.
- Never pipe a long run through `Select-Object -Last N` (it buffers to the end
  and shows no output for the whole run). Redirect to a log file
  (`*> logs\pytest_full.log`) and read the tail afterwards.
- Never relaunch a long process before confirming the previous one ended
  (`Get-Process python*`).

## Paid WP-1b runs: harness vs scaffold (standing)

- The agent scaffold (`src/benchmark/strategies/iterative_agent.py`,
  `repository_tools.py`) is FROZEN (protocol v3; one-amendment rule closed).
- Harness code (`src/benchmark/wp1b/*`, `scripts/wp1b_*`) may be fixed ONLY for
  a harness defect, with a failing test first, a DECISIONS.md entry, and no
  change to any scientific knob. If a crash originates in frozen agent code:
  STOP and report.
- MAIN runs use the MAIN-mode Review Card (`scripts/wp1b_main_review_card.py`):
  only instrument-level anomalies block. Per-task agent behaviour (EMPTY,
  rejected repeats, 0 reads, forced final, one cost ratio > 1) is DATA.
  See `docs/WP1B_MAIN297_EXECUTION_ADDENDUM_2026-09-22.md`.

## Validation order

1. `git diff --check`
2. Ruff on changed Python files
3. Mypy on changed production Python files only
4. Python compile check on changed Python files
5. Targeted Pytest
6. Full Pytest only before commit/merge or when shared interfaces changed
7. Bundle only when production code changed

## WP-1b review card

Every paid CALIBRATION run ends with a Review Card (`scripts/run_review_card.py
<records_dir>` writes `REVIEW_CARD.md`), and the STOP report quotes its
BLOCKING and INFORMATIONAL anomaly flags. BLOCKING anomalies fail the run;
INFORMATIONAL anomalies are reported but do not fail it. Every paid MAIN or
variance run ends with the MAIN-mode card (`scripts/wp1b_main_review_card.py
<run_dir>`), whose BLOCKING set is instrument-level only (M1-M5).

## Resource rules

- No pytest-xdist by default
- No watch mode, GPU, dataset/model downloads, clean rebuild
- No full test suite after every small patch
- No parallel heavy commands
- Trim logs to first root cause and relevant tail (~120 lines max)
- **Full-suite runtime policy:** the full suite takes ~50+ min on Ahmed's
  machine. Use a tool timeout of 5,400,000 ms (90 min), redirect output to a log
  file (never `Select-Object -Last` as the live pipe). Run it exactly once at the
  final validation gate; never restart it unless the previous pytest process is
  confirmed terminated (check `Get-Process python*` / poll the log).

## Git rules

Do not commit, push, merge, tag, reset, stash, force, or delete files unless explicitly requested in the current task.

## Scientific rules

- Ground Truth is evaluation-only.
- Do not claim Scientific Smoke or Pilot success without real execution.
- Keep PROJECT_HANDOFF and MASTER_IMPLEMENTATION_PLAN truthful.
- Update README only when user-facing behavior changes.
- Stable tag only after a successful Scientific Smoke audit.

## Kaggle / GitHub boundary (standing contract, enforced by tests)

GitHub is owner-controlled source/release storage only. Kaggle launch/resume
cells never contact GitHub, and no GitHub credential is needed in Kaggle.
Annotated stable tags are created on the accepted source commit and locally
verified against that commit after real preflight passes. Historical candidate
trail (e.g. `v0.9.22-d12-candidate`, superseded) is archived in
`docs/history/AGENTS_RELEASE_FACTS_ARCHIVE_2026-09-22.md`.

## Release provenance invariant

- Artifact source commit MUST equal immutable release tag peel.
- Create the tag explicitly on the accepted artifact source commit (not HEAD).
- Post-tag docs evidence commits are never tag targets.

## Stop / Blocker Reporting Contract

Before stopping for ANY reason (needs auth, missing input, blocker, task
complete, uncertain decision, permission rule, resource boundary), print a
structured report containing:

1. **Execution Identity** — provider, model, branch, HEAD, origin/main, tree state
2. **Why I Am Stopping** — exact reason; COMPLETE / BLOCKED / NEEDS AUTHORIZATION / NEEDS INPUT
3. **What I Completed** — per-file table: File | Symbol | Old | New | Why | Dependencies
4. **Verification Performed** — compile, lint, mypy, tests (PASS/FAIL/NOT RUN/BLOCKED with exact counts)
5. **Pre-Benchmark Validation** — dataset, prompt, pipeline, dry-run, integration, metrics
6. **Independent Self-Audit** — objective unchanged, plan adherence, over-engineering, debt, durability, freshness, tag state
7. **Exact Current State** — where project stops in the pipeline
8. **What Remains** — ordered remaining tasks
9. **What I Need From User** — minimum input or `Nothing — I can continue automatically.`
10. **Recommended Next Action** — exact next command; if existing instructions authorize it, continue without stopping

Never end with only "Proceed?" or a bare question.

## Project Export Rule (every mandatory stop)

At every STOP / Mandatory Stop Report, create a filtered audit ZIP in the
parent directory of `project/` named exactly `project-YYYY-MM-DD-HHmm.zip`
(local creation timestamp). This is workflow/documentation only — do NOT
create a release, move, or tag for this rule.

**Include:** ALL files tracked by `git ls-files` (source, tests, notebooks,
docs, configs, scripts, `benchmark_data/`, `reports/`, `.opencode/` workflow
files, etc.), `.git/`,
`dist/pilot-kaggle-upload.zip`, `dist/pilot-kaggle-upload.zip.sha256`.
`runs_dryrun/` is a **frozen HISTORICAL tracked fixture** (7 records,
`profile=smoke`, source `0c831e3`, added at commit `b203b21`) and is included
only for historical reproducibility — it is NOT current candidate proof and
MUST NOT be used for Pilot launch authorization; current D9 evidence is a fresh
exact-artifact 48/48 run generated into a fresh temporary/output directory.

**Exclude:** `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`,
`__pycache__/`, `*.pyc`, `.opencode/node_modules/`, `dist/_provcheck*`,
extracted `dist/pilot-kaggle-upload/`, `dist/pilot-repo-cache/`.

**Do not delete** anything from the real project. Only the share ZIP is
filtered.

After creation verify required members inside the ZIP (`.git/HEAD`,
`dist/pilot-kaggle-upload.zip`, `.sha256`), compute size + SHA-256, and
print:

```
PROJECT_EXPORT_READY
PROJECT_EXPORT_NAME=project-YYYY-MM-DD-HHmm.zip
PROJECT_EXPORT_PATH=<absolute path>
PROJECT_EXPORT_SIZE_BYTES=<bytes>
PROJECT_EXPORT_SHA256=<sha256>
UPLOAD_THIS_FILE=project-YYYY-MM-DD-HHmm.zip
```

The Stop Report must include this filename so the user knows which file to
upload.

## End-of-mission state update (mandatory)

Standing rule for every future mission (WP1B_TOOLFIX_LIVESTATUS_2026-09-21, B5):

1. Update `docs/LIVE_STATUS.json` with the mission's outcome (keep every
   schema key; an external study-deck builder consumes it).
2. Run `python scripts/render_live_status.py --write` to regenerate the block
   in the four current-facing files (README.md,
   START_HERE_CURRENT_2026-09-21b.md, PROGRESS.md,
   00_CURRENT_RESEARCH_STATE.md).
3. `tests/unit/test_live_status_blocks.py` must pass (byte-for-byte sync).
4. Distinguish "gate passed" from "instrument valid" in every STOP report:
   tally raw per-call outcomes from the sidecar
   (`scripts/wp1b_sidecar_tool_audit.py`), not only the gate result.
