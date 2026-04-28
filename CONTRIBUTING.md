# Contributing to movie-finder-chain

The chain is a **LangGraph multi-agent pipeline** that orchestrates RAG search, IMDb enrichment, user confirmation, and Q&A. This guide covers everything specific to the AI Engineering team's workflow.

For org-wide conventions (branching, commits, PRs, release process) see the [backend CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Table of contents

1. [Development setup](#development-setup)
2. [Project structure](#project-structure)
3. [Understanding the graph](#understanding-the-graph)
4. [Adding a new node](#adding-a-new-node)
5. [Modifying prompts](#modifying-prompts)
6. [Testing strategy](#testing-strategy)
7. [Running examples](#running-examples)
8. [Observability with LangSmith](#observability-with-langsmith)

---

## Development setup

The chain is a **uv workspace member** of the backend repo, but this child repo
now uses a Docker-only local workflow from `backend/chain/`.

### Start the repo-local dev container

```bash
make init               # build image, create .env from template, install git hook
cp .env.example .env    # if .env was not created automatically
$EDITOR .env
make editor-up          # start container for VS Code attach
```

Keep `make editor-up` running in one terminal. In another terminal, use the
repo-local targets:

```bash
make lint
make format
make typecheck
make test
make test-coverage
make pre-commit
```

If you use VS Code, attach to the running `chain` container after `make editor-up`.
The committed `.vscode/` settings, tasks, and launch configs assume that
attached-container workflow.

### Minimum required environment variables

```
QDRANT_URL=
QDRANT_API_KEY_RO=
VECTOR_COLLECTION_PREFIX=movies
EMBEDDING_MODEL=text-embedding-3-large
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

`make test` and `make test-coverage` use stubs only. They do not require live
Qdrant, OpenAI, or Anthropic credentials.

---

## Project structure

```
chain/
├── Makefile               ← Docker-only local workflow targets
├── src/chain/
│   ├── __init__.py          ← public API: compile_graph()
│   ├── config.py            ← ChainConfig (Pydantic Settings, all env vars)
│   ├── state.py             ← MovieFinderState (TypedDict, shared across nodes)
│   ├── graph.py             ← compile_graph() factory + routing functions
│   ├── models/
│   │   └── output.py        ← Pydantic output models for structured LLM responses
│   ├── nodes/               ← one file per graph node (8 total)
│   │   ├── rag_search.py
│   │   ├── imdb_enrichment.py
│   │   ├── validation.py
│   │   ├── presentation.py
│   │   ├── confirmation.py
│   │   ├── refinement.py
│   │   ├── qa_agent.py
│   │   └── dead_end.py
│   ├── prompts/             ← prompt templates (embedded as package resources)
│   │   ├── confirmation.md
│   │   ├── refinement.md
│   │   └── qa_context.md
│   └── rag/
│       └── service.py       ← MovieSearchService (OpenAI embed + Qdrant search)
├── tests/
│   ├── conftest.py          ← shared fixtures and mock factories
│   ├── test_graph.py        ← routing logic and graph compilation
│   ├── test_models.py       ← Pydantic model validation
│   ├── test_nodes.py        ← each node function (fully mocked)
│   └── test_rag_service.py  ← MovieSearchService unit tests
├── examples/
│   ├── basic_usage.py       ← 3 demo flows: discovery, full chat, refinement
│   └── streaming_example.py ← token-level streaming demo
└── prompts/                 ← reference copies of prompts (for easy editing)
    ├── confirmation.md
    ├── refinement.md
    └── qa_context.md
```

---

## Understanding the graph

The graph is compiled by `compile_graph()` in `graph.py`. The flow:

```
START
  └── rag_search          ← embed user query, search Qdrant
        └── imdb_enrichment  ← parallel IMDb fetch for each candidate
              └── validation   ← filter by confidence, deduplicate
                    └── presentation  ← format candidates → AIMessage
                          └── [human turn] ← await user response
                                ├── confirmation  ← Claude Haiku classifier
                                │     ├── confirmed → qa_agent  ← Claude Sonnet ReAct
                                │     │                 └── END
                                │     ├── not_found / max refinements → dead_end → END
                                │     └── unclear / refine → refinement
                                │                              └── rag_search (loop)
                                └── [continues until confirmed or dead_end]
```

**State** (`state.py`) flows through every node as a TypedDict. Each node reads from state and returns a partial dict of updated fields. The graph merges the updates.

**Routing** is in `graph.py` — two routing functions `_route_by_phase` and `_route_after_confirmation` determine which node runs next based on state fields.

---

## Adding a new node

1. **Create** `src/chain/nodes/my_node.py`:

```python
from chain.state import MovieFinderState

async def my_node(state: MovieFinderState) -> dict:
    """One-line description of what this node does."""
    # read from state
    # do async work
    # return only the fields you're updating
    return {"some_field": new_value}
```

2. **Register** in `graph.py`:

```python
from chain.nodes.my_node import my_node

builder.add_node("my_node", my_node)
builder.add_edge("previous_node", "my_node")
builder.add_edge("my_node", "next_node")   # or add_conditional_edges
```

3. **Add state field** in `state.py` if the node needs a new field:

```python
class MovieFinderState(TypedDict):
    # ... existing fields ...
    my_new_field: str | None   # add Annotated[..., reducer] if list accumulation needed
```

4. **Write tests** in `tests/test_nodes.py` — see the [testing strategy](#testing-strategy) section.

---

## Modifying prompts

Prompts live in two places:

- `prompts/` — reference copies for easy reading/editing
- `src/chain/prompts/` — the copies actually loaded by the package at runtime (via `importlib.resources`)

**Always edit both.** After editing, confirm the node that loads the prompt reads from `src/chain/prompts/`:

```python
# pattern used in nodes (e.g. confirmation.py)
from importlib.resources import files
prompt = files("chain.prompts").joinpath("confirmation.md").read_text()
```

Prompt changes don't require code changes — just edit the `.md` files and the nodes pick them up on the next run.

---

## Testing strategy

**Rule: no real API calls in tests.** Every external call is mocked.

### Mocking the LLM

```python
# in conftest.py — use the mock_llm fixture
def mock_llm(mocker):
    mock = AsyncMock()
    mock.with_structured_output.return_value = mock
    mock.ainvoke.return_value = ConfirmationClassification(
        decision="confirmed", movie_index=0, reasoning="test"
    )
    return mock
```

### Mocking Qdrant / RAG

```python
# patch at the service level
mocker.patch(
    "chain.nodes.rag_search.MovieSearchService.search",
    return_value=[sample_rag_candidate()]
)
```

### Mocking IMDb

```python
# patch the imdbapi client methods
mocker.patch(
    "chain.nodes.imdb_enrichment.IMDBAPIClient",
    return_value=AsyncMock(...)
)
```

### Running tests

```bash
make test
make test-coverage
```

---

## Running examples

Examples make real API calls — ensure `.env` is filled in first.

```bash
make example-basic
make example-streaming
```

---

## Observability with LangSmith

Enable tracing to debug the graph execution step by step:

```bash
# in .env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-key>
LANGSMITH_PROJECT=movie-finder
```

Every graph invocation will appear in the [LangSmith UI](https://smith.langchain.com) with per-node inputs, outputs, latency, and token counts.
