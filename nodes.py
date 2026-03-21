from __future__ import annotations

from typing import Literal

from agents import participant, summarizer
from state import State


def human_node(state: State) -> dict:
    """
    Intake node: ask for resume path or pasted text, and optional target roles.
    """
    if state.get("stage") not in (None, "intake"):
        # end
        user_input = input("\nType 'exit' to finish, or press Enter to re-run: ").strip()
        return {"messages": [{"role": "user", "content": user_input}]}

    print("\nProvide your resume as either a file path (txt) or paste text.")
    resume_path = input("Resume path (leave blank to paste): ").strip()
    resume_text = None
    if not resume_path:
        print("\nPaste resume text. End with a single line containing only 'EOF'.")
        lines = []
        while True:
            line = input()
            if line.strip() == "EOF":
                break
            lines.append(line)
        resume_text = "\n".join(lines).strip()

    roles_raw = input("\nTarget roles (comma separated, optional): ").strip()
    target_roles = [r.strip() for r in roles_raw.split(",") if r.strip()] if roles_raw else []

    return {
        "resume_path": resume_path or None,
        "resume_text": resume_text or None,
        "target_roles": target_roles or None,
        "stage": "intake",
        "messages": [{"role": "user", "content": "Provided resume input."}],
    }


def check_exit_condition(state: State) -> Literal["summarizer", "orchestrator"]:
    messages = state.get("messages", [])
    if messages:
        content = (messages[-1].get("content") or "").lower()
        if "exit" in content:
            return "summarizer"
    return "orchestrator"


def orchestrator_routing(state: State) -> Literal["participant", "human"]:
    next_agent = state.get("next_agent") or "human"
    return "human" if next_agent == "human" else "participant"


def participant_node(state: State) -> dict:
    next_agent = state.get("next_agent") or "resume_analysis"
    result = participant(next_agent, state)
    if result and "messages" in result:
        for msg in result["messages"]:
            # concise progress
            print(f"{msg.get('name','Agent')}: {msg.get('content','')}")
        return result
    return {}


def summarizer_node(state: State) -> dict:
    print("\n=== CAREERPILOT AI DONE ===\n")
    print(summarizer(state))
    return {}

