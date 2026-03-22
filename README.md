# movie-finder-chain

LangGraph pipeline that powers the Movie Finder conversational AI.  The chain
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

| Node | Model | Responsibility |
|---|---|---|
| `rag_search` | — | Embed query with OpenAI, search Qdrant, return top-k candidates |
| `imdb_enrichment` | — | Parallel IMDB search + `batch_get` for full metadata |
| `validation` | — | Filter by confidence, deduplicate by IMDb ID, cap at 5 |
| `presentation` | — | Format candidate pool as an AI message for the user |
| `confirmation` | Claude Haiku | Classify user response: confirmed / not_found / unclear |
| `refinement` | Claude Sonnet | Extract new plot details from conversation, build richer query |
| `qa_agent` | Claude Sonnet + IMDb tools | ReAct agent for open-ended movie Q&A |
| `dead_end` | — | Graceful exit after max refinement cycles |

### Event-driven design

Each user message triggers a new `graph.ainvoke()` call with the same
`thread_id`.  State is persisted by the checkpointer (in-memory `MemorySaver`
by default, swappable for Redis/Postgres).  No `interrupt()` / resume
complexity — the graph reads `phase` from state to decide which branch runs.

---

## Project structure

```
chain/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .pre-commit-config.yaml
├── README.md
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
    │   └── service.py          ← MovieSearchService (OpenAI embed + Qdrant search)
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

## Installation

### Using uv (recommended)

```bash
# From the backend/ workspace root
cd backend
uv sync --all-packages
```

This installs the chain package and its path-dependency (`imdbapi-client`)
into a shared `.venv`.

### Standalone

```bash
cd backend/chain
uv sync
```

---

## Configuration

Copy the root `.env.example` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `QDRANT_ENDPOINT` | ✅ | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | ✅ | Qdrant API key |
| `QDRANT_COLLECTION` | optional | Collection name (default: `text-embedding-3-large`) |
| `OPENAI_API_KEY` | ✅ | For `text-embedding-3-large` embeddings |
| `ANTHROPIC_API_KEY` | ✅ | For Claude Haiku (classifier) + Claude Sonnet (Q&A) |
| `CLASSIFIER_MODEL` | optional | Default: `claude-haiku-4-5-20251001` |
| `REASONING_MODEL` | optional | Default: `claude-sonnet-4-6` |
| `RAG_TOP_K` | optional | Qdrant result count (default: `8`) |
| `MAX_REFINEMENTS` | optional | Max refinement cycles before dead-end (default: `3`) |
| `CONFIDENCE_THRESHOLD` | optional | Min IMDb match confidence (default: `0.3`) |
| `LANGCHAIN_TRACING_V2` | optional | `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | optional | LangSmith API key |
| `LANGCHAIN_PROJECT` | optional | LangSmith project name (default: `movie-finder`) |

> **Note**: `QDRANT_COLLECTION` must match the embedding model used during
> `rag_ingestion` (default: `text-embedding-3-large`).

---

## Usage

### Minimal example

```python
import asyncio
from langchain_core.messages import HumanMessage
from chain import compile_graph

async def main():
    graph = compile_graph()
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

### FastAPI integration (future)

```python
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage
from chain import compile_graph

app = FastAPI()
graph = compile_graph()  # singleton — shared across requests

@app.post("/chat/{session_id}")
async def chat(session_id: str, message: str):
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.ainvoke(
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
# Run all tests with coverage
cd backend/chain
uv run pytest --cov=chain --cov-report=term-missing

# Run a specific module
uv run pytest tests/test_nodes.py -v

# Run only routing logic (fast, no mocking needed)
uv run pytest tests/test_graph.py -v
```

### Test coverage targets

| Module | What's tested |
|---|---|
| `test_rag_service.py` | `MovieSearchService.search()`, `_to_list()` edge cases |
| `test_nodes.py` | Every node function (mocked LLM, IMDB, and RAG deps) |
| `test_graph.py` | Routing functions, graph compilation, node registration |
| `test_models.py` | Pydantic models: defaults, validation, round-trip serialisation |

---

## Development

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files   # run once to check existing code
```

Hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`,
`detect-private-key`, `detect-secrets`, `ruff-check --fix`, `ruff-format`,
`mypy`.

### Linting & type checking

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

---

## Docker

### Build and run the chain service

```bash
docker compose up --build
```

The `docker-compose.yml` spins up:
- A local **Qdrant** instance (port `6333`) for development
- The **chain** container (ready for use as a library or test runner)

Environment variables are loaded from the root `.env` file.

### Build the image standalone

```bash
docker build -t movie-finder-chain .
```

---

## LangSmith Monitoring

Set the following environment variables to enable end-to-end tracing in
[LangSmith](https://smith.langchain.com):

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=<your key>
LANGCHAIN_PROJECT=movie-finder
```

LangChain/LangGraph picks these up automatically.  Each graph invocation
produces a run trace showing all nodes, LLM calls, tool invocations, and
their latencies.

---

## Dependencies

| Package | Purpose |
|---|---|
| `langgraph` | Stateful graph runtime |
| `langchain-anthropic` | Claude models (classifier + Q&A agent) |
| `langchain-core` | Message types, tool protocol |
| `langsmith` | Observability / tracing |
| `imdbapi-client` | IMDb REST API client (path dep from `../imdbapi`) |
| `openai` | `text-embedding-3-large` for RAG query embedding |
| `qdrant-client` | Vector search against the movie plot collection |
| `pydantic-settings` | Env-var configuration with validation |
