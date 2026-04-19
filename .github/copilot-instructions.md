# GitHub Copilot — movie-finder-chain

LangGraph 8-node AI pipeline — classifies user intent, performs semantic search, enriches via IMDb, and streams Q&A answers.

> For full project context, persona prompts, and architecture reference: see root `.github/copilot-instructions.md`.

---

## Python standards

- Every node function must be fully typed — `mypy --strict` must pass
- Use `logging`, not `print()`. LangSmith handles LLM call observability.
- No mutable default arguments in node signatures — use `None` with `if x is None: x = []`
- Tests: `pytest --asyncio-mode=auto`. No real LLM/Qdrant/IMDb calls — mock at the HTTP boundary.
- Run `make help` for all available targets

---

## Design patterns

| Pattern                  | Rule                                                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| **State machine**        | New behaviour = new node or new edge. Never add conditional branching inside an existing node to handle a different phase.      |
| **Pure functions**       | Nodes take `MovieFinderState` and return a partial state update. No side effects except external I/O (LLM, Qdrant, IMDb).      |
| **Strategy**             | New LLM or embedding provider = new class implementing the provider interface. No `if provider == "openai"` in core logic.     |
| **Factory**              | Node construction is centralised in `graph.py`. Nodes are registered once and are pure functions.                              |
| **Configuration object** | All settings loaded via Pydantic `BaseSettings` once at startup in `config.py`. Never `os.getenv()` inside node functions.     |

**Critical state rule:** `MovieFinderState` has `total=False` — when reading state fields in nodes, always use `.get()` with a safe default.

---

## Key files

| Path              | Description                                                              |
| ----------------- | ------------------------------------------------------------------------ |
| `src/chain/graph.py`  | LangGraph graph definition — node wiring and edge registration       |
| `src/chain/state.py`  | `MovieFinderState` TypedDict shared across all nodes                 |
| `src/chain/nodes/`    | Individual node implementations (pure functions)                     |
| `src/chain/config.py` | Pydantic `BaseSettings` — single source for all env vars             |
| `src/chain/rag/`      | Qdrant vector search wrapper — nodes never call `qdrant-client` directly |
