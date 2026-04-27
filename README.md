# Movie Finder Chain

LangGraph pipeline that powers the Movie Finder conversational AI. The chain
takes a natural-language plot description, searches a Qdrant vector store of
Wikipedia movie plots (populated by `rag_ingestion`), enriches the results
with live IMDb metadata, and guides the user through a discovery →
confirmation → Q&A flow.

---

## Architecture

```
User message
     │
     ▼
[route_by_phase]
     │
     ├── phase="discovery" ──► rag_search ──► imdb_enrichment ──► validation ──► presentation ──► END
     │                                                                                  ▲
     │                                                              (refinement loop) ──┘
     │
     ├── phase="confirmation" ──► confirmation ──► confirmed? ──► qa_agent ──► END
     │                                          ├── not found? ──► refinement ──► rag_search (loop)
     │                                          ├── exhausted? ──► dead_end ──► END
     │                                          └── unclear? ──► END (wait for next message)
     │
     └── phase="qa" ──► qa_agent ──► END (loop per user question)
```

### Nodes

| Node              | Model                      | Responsibility                                                  |
| ----------------- | -------------------------- | --------------------------------------------------------------- |
| `rag_search`      | Embedding factory           | Embed query, search vector store, return top-k candidates       |
| `imdb_enrichment` | —                          | Bounded-concurrency IMDb search + timeout-capped enrichment     |
| `validation`      | —                          | Filter by confidence, deduplicate by IMDb ID, cap at 5          |
| `presentation`    | —                          | Format candidate pool as an AI message for the user             |
| `confirmation`    | Classifier factory          | Classify user response: confirmed / not_found / unclear         |
| `refinement`      | Classifier factory          | Extract new plot details from conversation, build richer query  |
| `qa_agent`        | Reasoning factory + tools   | ReAct agent for open-ended movie Q&A                            |
| `dead_end`        | —                          | Graceful exit after max refinement cycles                       |

### Event-driven design

Each user message triggers a new `graph.ainvoke()` call with the same
`thread_id`. State is persisted by the checkpointer. Use
`checkpoint_lifespan()` with `DATABASE_URL` for a shared Postgres-backed
checkpointer in production; local tests can still use the in-memory
`MemorySaver`. No `interrupt()` / resume
complexity — the graph reads `phase` from state to decide which branch runs.

---

## Project structure

```
chain/
├── Makefile
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .pre-commit-config.yaml
├── README.md
├── CONTRIBUTING.md
├── examples/
│   ├── basic_usage.py          ← discovery + confirmation + Q&A walk-through
│   └── streaming_example.py    ← token-level streaming demo
├── prompts/                    ← originals (kept for reference)
└── src/chain/
    ├── __init__.py             ← exports compile_graph()
    ├── config.py               ← Pydantic Settings (env vars)
    ├── state.py                ← MovieFinderState TypedDict
    ├── graph.py                ← compile_graph()
    ├── prompts/                ← prompt files (inside package for importlib.resources)
    │   ├── confirmation.md
    │   ├── refinement.md
    │   └── qa_context.md
    ├── models/
    │   └── output.py           ← Pydantic output models
    ├── rag/
    │   └── service.py          ← MovieSearchService (embedding + vector search)
    └── nodes/
        ├── rag_search.py
        ├── imdb_enrichment.py
        ├── validation.py
        ├── presentation.py
        ├── confirmation.py
        ├── refinement.py
        ├── qa_agent.py
        └── dead_end.py
```

---

## Local workflow

`movie-finder-chain` is a child repo inside the backend workspace, but its
local contributor contract is Docker-only and runs from `backend/chain/`.

Prerequisites:

- Docker with the Compose plugin
- `make`

Initialize, then start the persistent dev container:

```bash
make init       # build image, create .env from template, install git pre-commit hook
make editor-up  # start container for VS Code attach
```

`make editor-up` keeps the `chain` container running for attached-container editing.
In a second terminal, use the repo-local targets:

```bash
make lint           # ruff check (report only)
make fix            # ruff check --fix + ruff format (auto-apply)
make format         # ruff format (apply)
make typecheck      # mypy --strict
make test           # pytest
make test-coverage  # pytest + coverage XML/HTML report
make pre-commit     # all hooks (full gate — also runs on git commit)
make check          # lint + typecheck + test-coverage
```

VS Code is configured for this workflow: after `make editor-up`, attach to the
running `chain` container and use the committed `.vscode/` launch/tasks files.

## Configuration

Copy `.env.example` to `.env` and fill in the values needed for live examples
or interactive runs:

```bash
cp .env.example .env
```

| Variable                 | Required  | Description                                          |
| ------------------------ | --------- | ---------------------------------------------------- |
| `QDRANT_URL`             | live runs | Qdrant Cloud cluster URL                             |
| `QDRANT_API_KEY_RO`      | live runs | Read-only Qdrant API key                             |
| `VECTOR_STORE`           | optional  | Vector store provider (default: `qdrant`)            |
| `VECTOR_COLLECTION_PREFIX` | optional | Dynamic vector collection prefix (default: `movies`) |
| `VECTOR_STORE_URL`       | optional  | Generic vector store URL override                    |
| `VECTOR_STORE_API_KEY`   | optional  | Generic vector store API key override                |
| `EMBEDDING_PROVIDER`     | optional  | Embedding provider (default: `openai`)               |
| `EMBEDDING_MODEL`        | optional  | Embedding model (default: `text-embedding-3-large`)  |
| `EMBEDDING_DIMENSION`    | optional  | Embedding dimension (default: `3072`)                |
| `CLASSIFIER_PROVIDER`    | optional  | Classifier LLM provider (default: `anthropic`)       |
| `REASONING_PROVIDER`     | optional  | Reasoning LLM provider (default: `anthropic`)        |
| `OPENAI_API_KEY`         | live runs | Required when using OpenAI embeddings or chat        |
| `ANTHROPIC_API_KEY`      | live runs | Required when using Anthropic chat models            |
| `DATABASE_URL`           | optional  | Postgres URL for persistent LangGraph checkpoints    |
| `CLASSIFIER_MODEL`       | optional  | Default: `claude-haiku-4-5-20251001`                 |
| `REASONING_MODEL`        | optional  | Default: `claude-sonnet-4-6`                         |
| `RAG_TOP_K`              | optional  | Vector result count (default: `8`)                   |
| `MAX_REFINEMENTS`        | optional  | Max refinement cycles before dead-end (default: `3`) |
| `IMDB_SEARCH_LIMIT`      | optional  | Max IMDb search hits per candidate (default: `3`)    |
| `IMDB_SEARCH_CONCURRENCY` | optional | Max concurrent IMDb search requests (default: `2`)   |
| `IMDB_RETRY_BASE_DELAY_SECONDS` | optional | Fallback retry delay on IMDb 429s (default: `2.0`) |
| `IMDB_NODE_TIMEOUT_SECONDS` | optional | Hard timeout before degrading to RAG-only results (default: `10.0`) |
| `CONFIDENCE_THRESHOLD`   | optional  | Minimum IMDb match confidence (default: `0.3`)       |
| `LANGSMITH_TRACING`      | optional  | `true` to enable LangSmith tracing                   |
| `LANGSMITH_API_KEY`      | optional  | LangSmith API key                                    |
| `LANGSMITH_PROJECT`      | optional  | LangSmith project name (default: `movie-finder`)     |

`make test` and `make test-coverage` do not require live Qdrant or LLM
credentials because the test suite fully stubs those integrations.

The IMDb enrichment node is intentionally latency-bounded. If IMDb search or
metadata fetches overrun `IMDB_NODE_TIMEOUT_SECONDS`, the chain returns degraded
RAG-only candidates instead of stalling the user-facing stream.

`QDRANT_API_KEY_RW` is intentionally absent from this repo. The chain is a
read-only Qdrant consumer and never writes to the collection.

---

## Usage

### Minimal example

```python
import asyncio
from langchain_core.messages import HumanMessage
from chain import checkpoint_lifespan, compile_graph

async def main():
    async with checkpoint_lifespan() as checkpointer:
        graph = compile_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "session-1"}}

    # Turn 1 — Discovery
    state = await graph.ainvoke(
        {"messages": [HumanMessage("A heist movie where they steal dreams")]},
        config=config,
    )
    print(state["messages"][-1].content)   # candidate pool

    # Turn 2 — Confirmation
    state = await graph.ainvoke(
        {"messages": [HumanMessage("Yes, the first one!")]},
        config=config,
    )
    print(state["messages"][-1].content)   # confirmation ack

    # Turn 3 — Q&A
    state = await graph.ainvoke(
        {"messages": [HumanMessage("Is it suitable for kids?")]},
        config=config,
    )
    print(state["messages"][-1].content)   # IMDb-grounded answer

asyncio.run(main())
```

### Streaming responses

```python
async for event in graph.astream_events(
    {"messages": [HumanMessage("A movie about dreams within dreams")]},
    config=config,
    version="v2",
):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"].get("chunk")
        if chunk:
            print(chunk.content, end="", flush=True)
```

### FastAPI integration

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage

from chain import checkpoint_lifespan, compile_graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with checkpoint_lifespan() as checkpointer:
        app.state.graph = compile_graph(checkpointer=checkpointer)
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/chat/{session_id}")
async def chat(session_id: str, message: str):
    config = {"configurable": {"thread_id": session_id}}
    state = await app.state.graph.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )
    last_ai = next(
        (m for m in reversed(state["messages"]) if isinstance(m, AIMessage)),
        None,
    )
    return {"reply": last_ai.content if last_ai else ""}
```

---

## Testing

All tests run without real API calls (OpenAI, IMDB, Qdrant, Anthropic are
all mocked via `unittest.mock`).

```bash
make test
make test-coverage
```

### Test coverage targets

| Module                | What's tested                                                   |
| --------------------- | --------------------------------------------------------------- |
| `test_rag_service.py` | `MovieSearchService.search()`, `_to_list()` edge cases          |
| `test_nodes.py`       | Every node function (mocked LLM, IMDB, and RAG deps)            |
| `test_graph.py`       | Routing functions, graph compilation, node registration         |
| `test_models.py`      | Pydantic models: defaults, validation, round-trip serialisation |

---

## Development

Use the repo-local Docker targets for all quality checks:

```bash
make lint           # ruff check (report only)
make fix            # ruff check --fix + ruff format (auto-apply)
make format         # ruff format
make typecheck      # mypy --strict
make pre-commit     # full hook suite (also enforced on git commit)
make check          # lint + typecheck + test-coverage (CI gate)
```

Hooks enforced on every `git commit` via the hook installed by `make init`:
`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`,
`check-json`, `check-ast`, `debug-statements`, `detect-private-key`,
`detect-secrets`, `ruff-check --fix`, `ruff-format`, `mypy`.

### Examples

```bash
make example-basic
make example-streaming
```

---

## Container workflow

`make editor-up` starts a persistent `chain` container for attached-container
editing, interactive debugging, and ad hoc shell access via `make shell`.

`docker-compose.yml` intentionally defines only the `chain` container. Qdrant
remains external-only; this repo no longer ships or documents a local Qdrant
developer flow.

---

## LangSmith Monitoring

Set the following environment variables to enable end-to-end tracing in
[LangSmith](https://smith.langchain.com):

```env
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your key>
LANGSMITH_PROJECT=movie-finder
```

The graph mirrors these to the legacy `LANGCHAIN_*` aliases automatically. Each graph invocation
produces a run trace showing all nodes, LLM calls, tool invocations, and
their latencies.

---

## Dependencies

| Package               | Purpose                                                             |
| --------------------- | ------------------------------------------------------------------- |
| `langgraph`           | Stateful graph runtime                                              |
| `langchain-anthropic` | Default Claude model provider                                        |
| `langchain-openai`    | Default OpenAI-compatible chat/embedding provider                    |
| `langchain-core`      | Message types, tool protocol                                        |
| `langsmith`           | Observability / tracing                                             |
| `imdbapi-client`      | IMDb REST API client (path dep from `./imdbapi` — nested submodule) |
| `openai`              | Default `text-embedding-3-large` query embedding                     |
| `qdrant-client`       | Default vector search backend                                       |
| `pydantic-settings`   | Env-var configuration with validation                               |

Optional vector-store SDKs are installed through extras: `chromadb` and
`pgvector` in `local`, `pinecone` in `cloud`.
