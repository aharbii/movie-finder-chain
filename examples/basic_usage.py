"""Movie Finder Chain — Basic Usage Examples.

Demonstrates the three-phase conversation loop:

1. Discovery  — user describes a plot, chain searches and presents candidates.
2. Confirmation — user identifies their movie (or says it's not there).
3. Q&A         — open-ended questions about the confirmed movie.

Prerequisites
-------------
Install dependencies::

    cd backend
    uv sync --all-packages

Create and populate a .env file (copy from .env.example)::

    cp ../../.env.example ../../.env
    # Fill in: QDRANT_ENDPOINT, QDRANT_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY

Ensure Qdrant is populated by running rag_ingestion first.

Run::

    cd backend
    uv run python chain/examples/basic_usage.py
"""

from __future__ import annotations

import asyncio
import os
import warnings

# Suppress langchain_core's pydantic-v1 compatibility warning on Python 3.14+.
# This is a third-party issue; pydantic v1 shim is unused by our code.
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality",
    category=UserWarning,
    module="langchain_core",
)

from dotenv import load_dotenv  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../../.env"))

from chain.graph import compile_graph  # noqa: E402  (after load_dotenv)


def _last_ai_message(state: dict) -> str:
    """Extract the text of the last AIMessage from state."""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return "(no response)"


def _print_divider(label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Demo 1 — Discovery phase only (inspect what the graph returns)
# ---------------------------------------------------------------------------


async def demo_discovery() -> None:
    """Show how the graph processes a plot description and returns candidates."""
    _print_divider("DEMO 1 — Discovery (plot → candidate pool)")

    graph = compile_graph()
    config = {"configurable": {"thread_id": "demo-discovery"}}

    user_query = (
        "A movie about a group of thieves who break into people's dreams "
        "to steal secrets, but then they're asked to plant an idea instead."
    )

    print(f"\nUser: {user_query}")

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_query)]},
        config=config,
    )

    print(f"\nAssistant:\n{_last_ai_message(result)}")
    print(f"\n[Phase is now: '{result.get('phase')}']")
    print(f"[Candidates found: {len(result.get('enriched_movies', []))}]")


# ---------------------------------------------------------------------------
# Demo 2 — Full discovery → confirmation → Q&A conversation
# ---------------------------------------------------------------------------


async def demo_full_conversation() -> None:
    """Walk through all three phases in a single continuous session."""
    _print_divider("DEMO 2 — Full conversation (discovery → confirmation → Q&A)")

    graph = compile_graph()
    config = {"configurable": {"thread_id": "demo-full"}}

    # ---- Turn 1: Discovery ----
    user_query = (
        "I remember a movie where a man travels through a black hole to save humanity "
        "and visits different planets, and it has something to do with time dilation."
    )
    print(f"\nUser: {user_query}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_query)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")

    # ---- Turn 2: Confirmation ----
    user_confirmation = "Yes! It's the first one."
    print(f"\nUser: {user_confirmation}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_confirmation)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")

    if state.get("phase") != "qa":
        print("[Movie not confirmed in this run — ending early]")
        return

    print(
        f"\n[Confirmed: '{state.get('confirmed_movie_title')}' (IMDb: {state.get('confirmed_movie_id')})]"
    )

    # ---- Turn 3: Q&A — Is it suitable for children? ----
    qa_question_1 = "Is this movie appropriate for a 10-year-old?"
    print(f"\nUser: {qa_question_1}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=qa_question_1)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")

    # ---- Turn 4: Q&A — Director's other work ----
    qa_question_2 = "What other movies has the director made?"
    print(f"\nUser: {qa_question_2}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=qa_question_2)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")


# ---------------------------------------------------------------------------
# Demo 3 — Refinement loop (user says the movie isn't in the list)
# ---------------------------------------------------------------------------


async def demo_refinement() -> None:
    """Show the refinement loop when the user's movie is not in the initial results."""
    _print_divider("DEMO 3 — Refinement loop")

    graph = compile_graph()
    config = {"configurable": {"thread_id": "demo-refinement"}}

    # Vague query that may not return the right movie immediately
    user_query = "A movie with a twist ending that surprised everyone."
    print(f"\nUser: {user_query}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_query)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")

    # User says the movie isn't in the list, adds more detail
    user_denial = (
        "No, none of these. It was a psychological thriller from the late 90s. "
        "The main character has a split personality and doesn't realise it until the end."
    )
    print(f"\nUser: {user_denial}")

    state = await graph.ainvoke(
        {"messages": [HumanMessage(content=user_denial)]},
        config=config,
    )
    print(f"\nAssistant:\n{_last_ai_message(state)}")
    print(f"\n[Refinement count: {state.get('refinement_count', 0)}]")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run all demos."""
    print("Movie Finder Chain — Basic Usage Examples")
    print("Requires: .env file with valid API keys and a populated Qdrant instance.")

    await demo_discovery()
    await demo_full_conversation()
    await demo_refinement()


if __name__ == "__main__":
    asyncio.run(main())
