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

## VSCode setup

`backend/chain/.vscode/` — full workspace configuration for chain only.
- Interpreter: `backend/.venv/bin/python` (`uv sync --all-packages` from `backend/`)
- `launch.json`: `chat.py` interactive runner + pytest all/current file
- `tasks.json`: lint, test, pre-commit (commands cd to `backend/` for workspace context)
- Modifying configs: keep parity with `backend/.vscode/` aggregate tasks. Update `CLAUDE.md`,
  `GEMINI.md`, and `AGENTS.md` after.
