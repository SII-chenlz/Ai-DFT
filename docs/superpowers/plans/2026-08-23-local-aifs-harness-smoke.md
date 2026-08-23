# Local AIFS Harness Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AIFS repository installable into a local DeepSeek Harness Web profile so a user can configure a model key and generate/validate a REST input card end to end.

**Architecture:** Keep `deepseek-harness/` untouched. Turn `dsh-plugin-aifs` into an out-of-tree Harness bundle whose patch inserts the AIFS plugin into the Web profile. Run the FastAPI backend as a separate localhost process, with all secrets and the REST basis pool supplied by environment variables.

**Tech Stack:** Python/FastAPI, TypeScript/Cordis plugin, DeepSeek Harness profile bundles, shell scripts, JSON/YAML/TOML, pytest, Vitest, TypeScript.

**Spec:** `../AIFS-DeepSeek-Harness-完整架构规格.md`

## Global Constraints

- Never modify or commit files under `../deepseek-harness/`.
- Never commit `DEEPSEEK_API_KEY`, access tokens, real server addresses, or user data.
- Keep the initial product localhost-only: Harness Web on `127.0.0.1:3080`, FastAPI on `127.0.0.1:8000`.
- REST input cards must pass the independent backend validator before being described as valid.
- The plugin must remain an HTTP adapter; recommendation, RAG, knowledge graph, and REST execution stay out of scope.

### Task 1: Make the AIFS plugin a Harness bundle

**Files:**
- Modify: `dsh-plugin-aifs/package.json`
- Create: `dsh-plugin-aifs/cordis.patch.yml`
- Modify: `dsh-plugin-aifs/tests/plugin.spec.ts`
- Create: `dsh-plugin-aifs/tests/bundle-manifest.spec.ts`

**Interfaces:**
- Produces a package manifest with `dsh.bundle.patch` and a patch inserting the `aifs` plugin row.
- The inserted row loads `./src/index.ts` through the package entry and injects only `tools`.

- [x] Write a failing manifest test asserting `dsh.bundle.patch`, patch existence, and an `aifs` row.
- [x] Run the focused Vitest test and confirm it fails because the manifest and patch are absent.
- [x] Add the bundle metadata and patch without touching upstream Harness files.
- [x] Run the focused test, the full plugin test suite, and TypeScript typecheck.
- [x] Commit as `feat: make AIFS plugin installable as Harness bundle`.

### Task 2: Add AIFS system prompt and profile configuration

**Files:**
- Create: `profiles/aifs-web/README.md`
- Create: `profiles/aifs-web/cordis.patch.yml`
- Modify: `dsh-plugin-aifs/cordis.patch.yml`
- Modify: `dsh-plugin-aifs/src/index.ts`
- Modify: `dsh-plugin-aifs/tests/plugin.spec.ts`

**Interfaces:**
- The plugin exports an AIFS prompt section through the Harness system-prompt service when available.
- The prompt tells the model to ask for missing coordinates/charge/spin, use structured tools, validate generated cards, and never invent evidence.
- The profile patch keeps the official Web bundle and adds the AIFS bundle by package installation; no secret is placed in YAML.

- [x] Add a failing test for the stable prompt text and prompt registration lifecycle.
- [x] Run the focused test and confirm the prompt is not yet registered.
- [x] Implement prompt registration and disposer cleanup; leave behavior unchanged when `systemPrompt` is unavailable in the standalone plugin test fixture.
- [x] Add a profile README showing the exact `dsh plugin --profile web add <local-package>` command and the required environment variables.
- [x] Run plugin tests and typecheck.
- [x] Commit as `feat: add AIFS agent guidance and local profile instructions`.

### Task 3: Add local backend and Harness launch scripts

**Files:**
- Create: `.env.example`
- Create: `scripts/start-backend.sh`
- Create: `scripts/check-local.sh`
- Modify: `scripts/README.md`
- Modify: `README.md`
- Modify: `backend/.env.example`

**Interfaces:**
- `scripts/start-backend.sh` loads only local environment configuration and starts `uvicorn aifs.api:app` on `127.0.0.1:8000`.
- `scripts/check-local.sh` checks `/health`, then exercises generate and validate with a temporary safe basis-pool fixture; it never requires a model key.
- Documentation explains that `DEEPSEEK_API_KEY` belongs to the Harness environment, while `AIFS_BASIS_SET_POOL` belongs to the backend environment.

- [x] Add a shell-level test or deterministic script mode that fails when the backend health endpoint is unavailable.
- [x] Implement scripts with `set -euo pipefail`, no secret echoing, and explicit repository-relative paths.
- [x] Run shell syntax checks, backend tests, and the local health/generate/validate smoke check.
- [x] Commit as `feat: add localhost AIFS startup and smoke scripts`.

### Task 4: Verify the real package/profile seam

**Files:**
- Modify: `dsh-plugin-aifs/README.md`
- Modify: `profiles/README.md`
- Create: `scripts/install-plugin-local.sh`
- Create: `scripts/verify-harness-mount.sh`

**Interfaces:**
- `install-plugin-local.sh` invokes the upstream CLI’s profile plugin command from the AIFS checkout, but writes only to the user’s DSH profile directory.
- `verify-harness-mount.sh` checks package metadata, profile dependency state, and the expected AIFS bundle row without starting a network service.

- [x] Add deterministic checks for the local package path and profile manifest before installation.
- [x] Implement the scripts with an explicit `DSH_HOME` override supported for disposable tests.
- [ ] Run the scripts against a temporary DSH home and confirm the upstream repository remains clean; full installation is blocked here because upstream dependencies are not installed and registry access is unavailable.
- [x] Run all backend/plugin/prototype tests and record any unavailable full Harness build as a limitation.
- [x] Commit as `test: verify local AIFS Harness mounting seam`.

## Final Verification

- `python -m pytest -q backend/tests` — all backend tests pass.
- `python -m ruff check backend` — no lint errors.
- `npm test` in `dsh-plugin-aifs` — all plugin tests pass.
- `npm run typecheck` in `dsh-plugin-aifs` — no TypeScript errors.
- `python -m pytest -q prototype-v0/tests` — legacy tests pass and files remain unchanged.
- Shell syntax checks pass for every new script.
- `git -C ../deepseek-harness status --short` — empty.
- `git status --short` — empty after the final commit.
