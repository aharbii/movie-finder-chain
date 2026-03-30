"""Movie Finder Chain — Streaming Example.

Demonstrates how to stream the chain's responses token-by-token using
``astream_events``.  Useful for building real-time UI feedback.

Run::

    make example-streaming
"""

from __future__ import annotations

import asyncio
import os
from typing import cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph.graph import CompiledGraph

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

from chain.graph import compile_graph  # noqa: E402
from chain.state import MovieFinderState  # noqa: E402


async def stream_discovery(query: str, thread_id: str = "stream-demo") -> MovieFinderState:
    """Stream a discovery query and print tokens as they arrive.

    Returns the final graph state so callers can inspect enriched_movies.
    """
    graph: CompiledGraph = compile_graph()
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\nUser: {query}")
    print("\nAssistant: ", end="", flush=True)

    final_state = cast(MovieFinderState, {})

    async for event in graph.astream_events(
        {"messages": [HumanMessage(content=query)]},
        config=config,
        version="v2",
    ):
        event_type = event.get("event", "")

        # Print LLM text chunks as they arrive (node output, not tool calls)
        if event_type == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                parts = content if isinstance(content, list) else [content]
                for part in parts:
                    if isinstance(part, str):
                        print(part, end="", flush=True)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        print(part.get("text", ""), end="", flush=True)

        # Capture the final state after the graph completes
        elif event_type == "on_chain_end" and event.get("name") == "LangGraph":
            final_state = cast(MovieFinderState, event["data"].get("output", {}))

    print()  # newline after streaming ends
    return final_state


async def stream_qa(question: str, thread_id: str) -> None:
    """Stream a Q&A response for an already-confirmed movie session."""
    graph: CompiledGraph = compile_graph()
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\nUser: {question}")
    print("\nAssistant: ", end="", flush=True)

    async for event in graph.astream_events(
        {"messages": [HumanMessage(content=question)]},
        config=config,
        version="v2",
    ):
        event_type = event.get("event", "")
        if event_type == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                parts = content if isinstance(content, list) else [content]
                for part in parts:
                    if isinstance(part, str):
                        print(part, end="", flush=True)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        print(part.get("text", ""), end="", flush=True)

    print()


async def main() -> None:
    print("=" * 60)
    print("Movie Finder — Streaming Demo")
    print("=" * 60)

    thread = "stream-session-1"

    # --- Discovery ---
    state = await stream_discovery(
        "A movie where a man wakes up reliving the same day over and over again "
        "until he learns to be a better person.",
        thread_id=thread,
    )

    candidates = state.get("enriched_movies", [])
    print(f"\n[{len(candidates)} candidate(s) returned. Phase: '{state.get('phase')}']")

    if not candidates:
        print("No candidates — check your Qdrant connection and dataset.")
        return

    # --- Simulated confirmation (first candidate) ---
    graph = compile_graph()
    config = {"configurable": {"thread_id": thread}}

    confirm_state = cast(
        MovieFinderState,
        await graph.ainvoke(
            {"messages": [HumanMessage(content="Yes, the first one!")]},
            config=config,
        ),
    )

    if confirm_state.get("phase") != "qa":
        print("[Confirmation did not succeed in this demo run]")
        return

    print(f"\n[Confirmed: {confirm_state.get('confirmed_movie_title')}]")

    # --- Streaming Q&A ---
    await stream_qa("Who directed it and what other famous movies did they make?", thread)
    await stream_qa("What is the IMDb rating and how many people voted?", thread)


if __name__ == "__main__":
    asyncio.run(main())
