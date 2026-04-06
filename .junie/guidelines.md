# JetBrains AI (Junie) — chain submodule guidelines

This is **`movie-finder-chain`** (`backend/chain/`) — LangGraph AI pipeline.
GitHub repo: `aharbii/movie-finder-chain` · Parent: `aharbii/movie-finder`

---

## What this submodule does

LangGraph 8-node AI pipeline — the core intelligence layer of Movie Finder.

**Pipeline flow:**
`classify` → `search_rag` → `enrich_imdb` → `reason` → `route` → `refine` / `confirm` / `answer`

- **State:** `MovieFinderState` (TypedDict) shared across all nodes
- **Models:** Claude Haiku (classify), Claude Sonnet (confirm/refine/Q&A)
- **Embeddings:** OpenAI `text-embedding-3-large` at query time
- **Vector search:** Qdrant Cloud (always external)
- **IMDb enrichment:** via `imdbapi` submodule (path dependency)

### Key layout

```
src/chain/
├── config.py     Pydantic BaseSettings
├── graph.py      LangGraph Pregel graph definition (node wiring)
├── state.py      MovieFinderState TypedDict
├── nodes/        Individual node implementations (pure functions)
├── prompts/      LLM prompt templates
├── rag/          Qdrant vector search wrapper
└── utils/        Helpers
```

---

## Quality commands (Docker-only)

```bash
make pre-commit   # lint + typecheck + format
make test         # pytest --asyncio-mode=auto
make lint         # ruff check
make typecheck    # mypy --strict
```

---

## Design patterns

| Pattern      | Where     | Rule                                                                   |
| ------------ | --------- | ---------------------------------------------------------------------- |
| State machine| `graph.py`| New behaviour = new node or edge; never branch inside existing nodes   |
| Pure functions| `nodes/` | Nodes take state, return partial update — no side effects except I/O   |
| Strategy     | Providers | New model = new config value, not a new code path                      |
| Config object| `config.py`| All settings via `BaseSettings`; no `os.getenv()` inside nodes        |
| Adapter      | `rag/`    | Qdrant wrapper adapts client library to domain interface               |
| Factory      | `graph.py`| Node creation and wiring centralised; nodes registered once            |

**Critical:** `MovieFinderState` has `total=False` (issue #15 — tracked).
Always use `.get()` with a safe default when reading state fields in nodes.

---

## Python standards

- `mypy --strict` must pass; every node function fully typed
- No mutable default arguments — use `None` with `if x is None: x = []`
- Docstrings (Google style) on all public functions and classes
- No `print()` — use `logging`
- Async all the way
- Line length: 100

---

## Environment variables

```
QDRANT_URL, QDRANT_API_KEY_RO, QDRANT_COLLECTION_NAME
EMBEDDING_MODEL=text-embedding-3-large, EMBEDDING_DIMENSION=3072
ANTHROPIC_API_KEY
CLASSIFIER_MODEL=claude-haiku-4-5-20251001
REASONING_MODEL=claude-sonnet-4-6
OPENAI_API_KEY
RAG_TOP_K=8, MAX_REFINEMENTS=3, IMDB_SEARCH_LIMIT=3, CONFIDENCE_THRESHOLD=0.3
LANGSMITH_TRACING=false, LANGSMITH_ENDPOINT, LANGSMITH_API_KEY, LANGSMITH_PROJECT
```

---

## Workflow

- Branches: `feature/<kebab>`, `fix/<kebab>`, `chore/<kebab>`, `docs/<kebab>`
- Commits: `feat(chain): add Gemini embedding support`
- Pre-commit: `make pre-commit` (Docker)
- After merge: bump pointer in `backend/`, then in root `movie-finder`

---

## Submodule pointer bump

```bash
git add chain && git commit -m "chore(chain): bump to latest main"   # in backend/
git add backend && git commit -m "chore(backend): bump to latest main"  # in root
```
