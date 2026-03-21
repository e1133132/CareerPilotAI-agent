from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from agents import orchestrator
from nodes import (
    human_node,
    check_exit_condition,
    orchestrator_routing,
    participant_node,
    summarizer_node,
)
from state import State


load_dotenv(override=True)
import os
'''print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))'''
import sys
print("[BOOT] python executable:", sys.executable)
print("[BOOT] main file:", __file__)

def build_graph():
    builder = StateGraph(State)

    builder.add_node("human", human_node)
    builder.add_node("orchestrator", orchestrator)
    builder.add_node("participant", participant_node)
    builder.add_node("summarizer", summarizer_node)

    builder.add_edge(START, "human")

    builder.add_conditional_edges(
        "human",
        check_exit_condition,
        {"summarizer": "summarizer", "orchestrator": "orchestrator"},
    )

    builder.add_conditional_edges(
        "orchestrator",
        orchestrator_routing,
        {"participant": "participant", "human": "human"},
    )

    builder.add_edge("participant", "orchestrator")
    builder.add_edge("summarizer", END)

    return builder.compile()


def main():
    print("=== CAREERPILOT AI (Agentic Career Advisor) ===")
    print("Type 'exit' anytime at prompts to end.\n")

    graph = build_graph()
    print(graph.get_graph().draw_ascii())

    initial_state: State = {
        "messages": [],
        "stage": "intake",
        "next_agent": None,
    }

    graph.invoke(initial_state)


if __name__ == "__main__":
    main()

