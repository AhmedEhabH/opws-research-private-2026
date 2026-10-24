# AGENTS.md — OPWS / Selective Regeneration Research Instrument

> **CURRENT PHASE (updated 2026-10-24):** M19 — OPWS fixed-patch scope-sufficiency
> instrument on branch `parallel/opws-instrument-build-2026-10-20`. Next: seven-task
> readiness, then real NEG / FULL_REFERENCE controls. E2E generation is a later,
> separate protocol. The previous WP-1b / Kaggle guidance is archived in
> `docs/history/AGENTS_WP1B_KAGGLE_ARCHIVE_2026-10-24.md` and is NOT current guidance.

## 1. Project facts

- Python 3.11 on Windows via `py -3.11`; real Saleor execution only in WSL Ubuntu-24.04 / Linux Docker.
- OPWS code: `scripts/opws_*.py`, `src/benchmark/wp2/`. OPWS tests: `tests/unit/opws/`.
- Binding artifacts: `research/opws/binding/`. Audit outputs: `D:\WP2\audit_results\<MISSION>\` (outside the repo).
- Saleor bare Git store: `D:\wp2_env_store\git_cache\saleor.git` (read-only use; never check out Saleor trees on Windows).
- Lint: Ruff. Types: Mypy strict on changed production files.

## 2. Frozen scientific artifacts — never modify, rewrite, regenerate or replace

- Protocols: R1 (`9038df3e…`), R1.1 (`7af88920…`), R2 baseline predictions (`6c2f698154ddcba22ff7d9a85656753a6eaee5ff`).
- MAIN297 predictions, labels and census.
- `research/opws/binding/OPWS_BEHAVIOR_CONTRACT_MANIFEST_219.json`
- `research/opws/binding/OPWS_F2P_NODE_CONTRACT_83.json` (historical, 795 F2P nodes)
- `research/opws/binding/OPWS_F2P_THREE_RUN_SENSITIVITY_83.json` (strict, 770 F2P nodes)
- `research/opws/binding/C2_MAIN83_JUNIT_EVIDENCE_MANIFEST.json`
- Evidence directory `D:\WP2\evidence\C2_MAIN83_JUNIT_RESCUE_2026-10-23\` (read-only; 1,801 files).
- Classifier semantics `src/benchmark/wp2/oracle_semantics_v2.py` (pin `aa85f495…`, LF bytes).

Corrections are ADDITIVE only: new versioned file + addendum document. Never edit a frozen file.

## 3. Scientific rules

- No real behavioral run (Saleor tests, Docker, NEG, FULL_REFERENCE, scoped arms) unless the current mission explicitly authorizes it.
- Pre-outcome discipline: populations, test-node lists, pilot tasks and statistics are frozen and committed BEFORE any behavioral outcome is seen. Never choose or drop a task because of a selector's outcome.
- Test identity: exact node-ID SET EQUALITY against the frozen contract. Never re-collect tests (`pytest --collect-only`) to replace frozen IDs. Lower-bound counts are not sufficient.
- Fail closed: missing, partial, unparsable or ambiguous evidence is BLOCKED, never PASS.
- Distinguish: unit/mock PASS ≠ structural audit PASS ≠ environment qualification ≠ behavioral sufficiency ≠ LLM-generated patch correctness.
- Never invent numbers, hashes, paths, file names or provenance. Unknown = `UNKNOWN`.

## 4. Hashing and file-writing rules

- Windows working copies may be CRLF. Hash committed content with the Git blob (`git show HEAD:<path>`), or report raw/LF/CRLF variants explicitly.
- Write generated artifacts as bytes (`write_bytes`), UTF-8 without BOM, LF line endings, deterministic JSON (`sort_keys`, fixed separators). No timestamps inside content-hashed payloads.
- Every new artifact: report its SHA-256 and the SHA-256 of every input it used.

## 5. Context and cost rules

- Never read whole any file larger than 200 KB. Use short bounded Python summaries (`py -3.11 -I -c ...`) that print counts and samples only.
- Large append-only records (`DECISIONS.md`, `TODO.md`, `00_CURRENT_RESEARCH_STATE.md`, `docs/RESEARCH_JOURNEY.md`): search, then read only the needed range.
- Read only the files the mission needs. Do not explore unrelated directories.
- **Usage reporting:** state the real provider and model. Do NOT estimate tokens or USD. Write `USAGE: read from harness status bar by owner` unless exact metered values are available to you.

## 6. Execution and resource rules

- Real execution only on Linux (WSL ext4 / Docker). Keep ≥ 30 GiB free on D: and 2× the observed per-task peak.
- Never `docker system prune`, delete images, volumes, wheelhouses or the env store.
- No two heavy processes at once (Docker runs, full test suites). One mission per Git worktree.
- Long commands: redirect to a log file; poll; never relaunch before confirming the previous process ended.
- No network downloads unless the mission authorizes them.

## 7. Working rule and validation order

inspect minimally → edit narrowly → test first for new behavior → validate.

1. `git diff --check` AND an explicit whitespace/CRLF check of untracked new files.
2. Ruff on changed Python files.
3. Mypy strict on changed production Python files.
4. Targeted pytest; then `py -3.11 -m pytest -q -p no:cacheprovider tests/unit/opws`.
5. The repository-wide suite is environment-blocked on Windows; do not run it unless asked.

## 8. Git rules

- Do not commit, push, tag, reset, stash, force or delete unless the current mission says so.
- When committing: stage explicit paths only; verify the staged list; push to `opws-private`; confirm local HEAD == remote SHA.

## 9. Native TODO (mandatory for multi-step missions)

- First execution tool call: native todo list. Exactly one item in progress. Update after every atomic step with live counts (x/y).

## 10. STOP report (every stop)

1. Identity — provider, model, branch, HEAD, tree state.
2. Status — COMPLETE / BLOCKED / NEEDS INPUT, with the exact reason.
3. Changes — file | what changed | why.
4. Verification — each check with PASS/FAIL/NOT RUN and exact counts.
5. Artifacts — paths and SHA-256 of all new outputs and their inputs.
6. Scientific boundary — what was proven and what was NOT (behavioral outcomes count).
7. Remaining work — ordered.
8. Next action — one exact command or mission.
9. Usage — per section 5.

## 11. Mission evidence bundle (replaces the old full-project export)

At a STOP, only if the mission produced new or changed files, create a small ZIP in
`D:\WP2\audit_results\<MISSION>\` named `<MISSION>_EVIDENCE_YYYY-MM-DD-HHmm.zip` containing:

- every new or modified file of this mission (tracked diffs and untracked additions),
- `git_status.txt` (`git status --porcelain --untracked-files=all`), `git_head.txt`, `git_diff.patch`,
- the mission report and logs (trimmed to ≤ 2 MB each).

Never include the whole repository, `.git`, caches, the evidence directory or Docker data.
Cap: 50 MB; if exceeded, STOP and list the largest members. Print:

```
EVIDENCE_BUNDLE_READY
EVIDENCE_BUNDLE_PATH=<absolute path>
EVIDENCE_BUNDLE_SIZE_BYTES=<bytes>
EVIDENCE_BUNDLE_SHA256=<sha256>
```

A full project export is created ONLY when the owner explicitly asks for it.

## 12. Live status

Update `docs/LIVE_STATUS.json` and run `py -3.11 scripts/render_live_status.py --write` only when a mission changes the project state (a commit, a frozen decision, a real run). Audit-only missions skip this.
