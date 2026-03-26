# OpenAI Codex CLI — chain submodule

Foundational mandate for `movie-finder-chain` (`backend/chain/`).

---

## What this submodule does
LangGraph 8-node AI pipeline.
`classify` → `search_rag` → `enrich_imdb` → `reason` → `route` → `refine` / `confirm` / `answer`

---

## Technology stack
- LangGraph 0.2+, LangChain 0.3+
- Claude Haiku (classify), Claude Sonnet (reason/Q&A)
- OpenAI `text-embedding-3-large` (3072-dim)
- Qdrant Cloud (vector store)
- LangSmith (tracing)

---

## Design patterns
- **State machine:** New behaviour = new node/edge.
- **Pure functions:** Nodes take state and return partial updates.
- **Strategy:** Abstract LLM and embedding providers.
- **Critical state rule:** Access `MovieFinderState` fields safely with `.get()` (issue #15).

---

## Pre-commit & Linting
- `uv run pre-commit run --all-files` from this directory.
- `mypy --strict` must pass for all nodes.

---

## Workflow invariants

- This repo is the gitlink path `chain` inside `aharbii/movie-finder-backend`. Parent
  workflow/path filters must use `chain`, not `chain/**`.
- Cross-repo tracker issues originate in `aharbii/movie-finder`. Create the linked child issue in
  this repo only if this repo will actually change.
- Inspect `.github/ISSUE_TEMPLATE/*.yml`, `.github/PULL_REQUEST_TEMPLATE.md` when present, and a
  recent example before creating or editing issues/PRs. Do not improvise titles or bodies.
- For child issues in this repo, use `.github/ISSUE_TEMPLATE/linked_task.yml` and keep the
  description, file references, and acceptance criteria repo-specific.
- If CI, required checks, or merge policy changes affect this repo, update contributor-facing docs
  here and in `aharbii/movie-finder-backend` and/or `aharbii/movie-finder` where relevant.
- If a new standalone issue appears mid-session, branch from `main` unless stacking is explicitly
  requested.
- PR descriptions must disclose the AI authoring tool + model. Any AI-assisted review comment or
  approval must also disclose the review tool + model.

---

## VSCode setup

`backend/chain/.vscode/` — full workspace configuration for chain only.
- Interpreter: `backend/.venv/bin/python` (`uv sync --all-packages` from `backend/`)
- `launch.json`: `chat.py` interactive runner + pytest all/current file
- `tasks.json`: lint, test, pre-commit (commands cd to `backend/` for workspace context)
- Modifying configs: keep parity with `backend/.vscode/` aggregate tasks. Update `CLAUDE.md`,
  `GEMINI.md`, `AGENTS.md`, and the repo's `.github/copilot-instructions.md` after.
