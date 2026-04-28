# Claude Code — chain submodule

This is **`movie-finder-chain`** (`backend/chain/`) — part of the Movie Finder project.
GitHub repo: `aharbii/movie-finder-chain` · Parent repo: `aharbii/movie-finder`

> See root `CLAUDE.md` for: full submodule map, GitHub issue/PR hygiene, cross-cutting checklist, coding standards, branching strategy, session start protocol.

---

## What this submodule does

LangGraph 8-node AI pipeline — the core intelligence layer of Movie Finder.

**Pipeline flow:**
`classify` → `search_rag` → `enrich_imdb` → `reason` → `route` → `refine` / `confirm` / `answer`

- **State:** `MovieFinderState` (TypedDict) shared across all nodes
- **Models:** classifier and reasoning LLMs resolved by provider factory
- **Embeddings:** query-time embedding provider resolved by factory (must match ingestion)
- **Vector search:** vector store provider resolved by factory (default Qdrant Cloud)
- **IMDb enrichment:** via `imdbapi` submodule (path dependency)
- **Bounded refinement:** max 3 cycles (`MAX_REFINEMENTS`)
- **Tracing:** LangSmith (opt-in via `LANGSMITH_TRACING=true`)
- **uv workspace member** of `backend/`

### Key source layout

```
src/chain/
├── config.py          # Pydantic BaseSettings — all env vars loaded here
├── graph.py           # LangGraph Pregel graph definition (node wiring)
├── state.py           # MovieFinderState TypedDict
├── models/            # Domain data structures
├── nodes/             # Individual node implementations (pure functions)
├── prompts/           # LLM prompt templates
├── rag/               # Vector search providers and RAG search service
└── utils/             # Helpers and LLM/embedding factories
```

---

## Technology stack (chain-specific)

| Layer        | Stack                                                                       |
| ------------ | --------------------------------------------------------------------------- |
| Language     | Python 3.13, uv workspace member of `backend/`                              |
| AI pipeline  | LangGraph 0.2+, LangChain 0.3+                                              |
| LLM          | Provider factory: Anthropic (default), OpenAI, Groq, Together, Ollama, Google |
| Embeddings   | Provider factory: OpenAI (default), Ollama, HuggingFace, SentenceTransformers |
| Vector store | Provider factory: Qdrant (default), ChromaDB, Pinecone, pgvector              |
| IMDb         | `imdbapi` submodule (path dependency)                                       |
| Tracing      | LangSmith (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`)   |
| Tests        | `pytest --asyncio-mode=auto`, verbose                                       |

---

## Environment variables (`.env.example`)

```
QDRANT_URL, QDRANT_API_KEY_RO
VECTOR_STORE=qdrant, VECTOR_COLLECTION_PREFIX=movies
EMBEDDING_PROVIDER=openai, EMBEDDING_MODEL=text-embedding-3-large, EMBEDDING_DIMENSION=3072
CLASSIFIER_PROVIDER=anthropic, CLASSIFIER_MODEL=claude-haiku-4-5-20251001
REASONING_PROVIDER=anthropic, REASONING_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, TOGETHER_API_KEY, GOOGLE_API_KEY
RAG_TOP_K=8, MAX_REFINEMENTS=3, IMDB_SEARCH_LIMIT=3, CONFIDENCE_THRESHOLD=0.3
LOG_LEVEL
LANGSMITH_TRACING=false, LANGSMITH_ENDPOINT, LANGSMITH_API_KEY, LANGSMITH_PROJECT
```

---

## Design patterns (chain-specific)

| Pattern                  | Where                              | Rule                                                                                                                            |
| ------------------------ | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **State machine**        | `graph.py`                         | New behaviour = new node or new edge. Never add conditional branching inside an existing node to handle a different phase.      |
| **Pure functions**       | `nodes/`                           | Nodes take `MovieFinderState` and return a partial state update. No side effects except external I/O (LLM calls, Qdrant, IMDb). |
| **Strategy**             | LLM / embedding / vector providers | New provider = new strategy implementation, not branching in node logic.                                                        |
| **Configuration object** | `config.py`                        | All settings loaded via `Pydantic BaseSettings` once at startup. Never `os.getenv()` inside node functions.                     |
| **Adapter**              | `rag/` providers                   | Vector store providers adapt client libraries to the domain interface. Nodes never call vector SDKs directly.                   |
| **Factory**              | `utils/llm_factory.py`, `rag/`      | Provider objects are created in cached factories and consumed by nodes/services.                                                |

**Critical state rule:** Access `MovieFinderState` fields safely with `.get()` and defaults.

**Vector naming invariant:** Query-time and ingestion-time vector targets must both resolve
`{prefix}_{sanitized_model}_{dimension}` using the same sanitization contract as `rag/`.

---

## Coding standards (additions to root CLAUDE.md)

- Every node function must be fully typed (`mypy --strict` must pass)
- Use `logging` — not `print()`. LangSmith handles LLM call observability.
- No mutable default arguments in node signatures — use `None` with `if x is None: x = []`

---

## Pre-commit hooks

```bash
make pre-commit
```

Hooks: whitespace/YAML/safety checks, `detect-secrets`, `mypy --strict`, `ruff-check --fix`, `ruff-format`. **Never `--no-verify`.**

---

## VSCode setup

- `settings.json` — attached-container interpreter (`/opt/venv/bin/python`), Ruff, mypy strict, pytest discovery
- `launch.json` — `chat.py` interactive runner + pytest all / current file inside the attached container
- `tasks.json` — Docker-backed `make ...` targets

**Workflow:** run `make dev`, then attach VS Code to the running `chain` container.

---

## Workflow invariants (chain-specific)

- Gitlink path is `chain` inside `aharbii/movie-finder-backend`. Parent path filters must use `chain`, not `chain/**`.
- Embedding model change here requires coordinating with `rag/` — query-time and ingestion-time embeddings must match.
- Vector store or collection naming changes require coordinating with `rag/`, backend env wiring, and infrastructure.

Run `/session-start` in root workspace.

---

## Cross-cutting change checklist (chain-specific rows)

| #   | Category           | Key gate                                                                                                                                                                    |
| --- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Branch**         | `feature/fix/chore/docs` in this repo + pointer-bump `chore/` in `backend/` and root                                                                                        |
| 2   | **ADR**            | New LLM provider, embedding model, external dep, or pipeline architecture → ADR in `docs/`                                                                                  |
| 3   | **Env & secrets**  | `.env.example` updated here + `backend/` + `rag/` if embedding changes + root; tuning params updated; new keys → Key Vault + Jenkins                                        |
| 4   | **Docker**         | `Dockerfile` updated (workspace root context includes `imdbapi/` + `chain/`)                                                                                                |
| 5   | **Diagrams**       | `04-langgraph-pipeline.puml`, `05-langgraph-statemachine.puml`, `09-seq-langgraph-execution.puml`; `workspace.dsl` if C4 changed; commit to `docs/` first; **never `.mdj`** |

### Sibling submodules likely affected

| Submodule                | Why                                                                    |
| ------------------------ | ---------------------------------------------------------------------- |
| `backend/app/`           | SSE event fields and API response shape                                |
| `rag/`                   | Embedding model must stay in sync with query-time embedding            |
| `backend/chain/imdbapi/` | IMDb data shape changes break `enrich_imdb` node                       |
| `frontend/`              | SSE events consumed by `EventSource` — field renames are breaking      |
| `infrastructure/`        | New LLM or embedding provider = new secret, possibly new Azure service |
| `docs/`                  | Pipeline diagrams, architecture docs                                   |

### Submodule pointer bump

```bash
git add chain && git commit -m "chore(chain): bump to latest main"   # in backend/
git add backend && git commit -m "chore(backend): bump to latest main"  # in root
```

### Pull request

- [ ] PR in `aharbii/movie-finder-chain` discloses the AI authoring tool + model
- [ ] PR in `aharbii/movie-finder-backend` (pointer bump)
- [ ] PR in `aharbii/movie-finder` (pointer bump)
- [ ] Any AI-assisted review comment or approval discloses the review tool + model
