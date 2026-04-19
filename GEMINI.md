# Gemini CLI — chain submodule

This is **`movie-finder-chain`** (`backend/chain/`) — part of the Movie Finder project.
GitHub repo: `aharbii/movie-finder-chain` · Parent repo: `aharbii/movie-finder`

> See root GEMINI.md for: full submodule map, GitHub issue/PR hygiene, coding standards, branching strategy, session start protocol.

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

## Common tasks

```bash
make lint / make format / make typecheck / make test / make pre-commit
```

Docker-only local workflow. `mypy --strict` must pass for all nodes.

---

## VS Code setup

`backend/chain/.vscode/` — full workspace configuration for chain only.

- Workflow: run `make dev`, then attach VS Code to the running `chain` container
- Interpreter: `/opt/venv/bin/python` inside the attached container
- `launch.json`: `chat.py` interactive runner + pytest all/current file in the attached container
- `tasks.json`: Docker-backed `make ...` targets from `backend/chain/`

---

## Workflow invariants (chain-specific)

- Gitlink path is `chain` inside `aharbii/movie-finder-backend`. Parent path filters must use `chain`, not `chain/**`.
- Embedding model change here requires coordinating with `rag/` — query-time and ingestion-time embeddings must match.

### Submodule pointer bump

```bash
git add chain && git commit -m "chore(chain): bump to latest main"   # in backend/
git add backend && git commit -m "chore(backend): bump to latest main"  # in root
```
