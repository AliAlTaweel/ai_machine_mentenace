from typing import Callable

from pydantic import BaseModel

from backend.graph.state import GraphState
from backend.llm.base import LLMClient


class ExtractedError(BaseModel):
    machine_id: str | None = None
    error_code: str | None = None
    description: str


def make_extract_node(llm: LLMClient) -> Callable[[GraphState], dict]:
    def extract_node(state: GraphState) -> dict:
        # `transcript` accumulates for the life of the thread (operator.add
        # reducer, never cleared), so once one report has been fully
        # extracted and diagnosed, later unrelated reports must NOT be
        # re-blended with that old text — otherwise the LLM latches onto an
        # earlier machine_id/error_code instead of the new one. Only pull in
        # prior turns when the previous turn was itself a clarification
        # request for THIS report (needs_clarification=True), so a
        # multi-turn "machine ID?" -> "it's the CNC mill" round-trip still
        # combines correctly.
        if state.get("needs_clarification"):
            transcript = state.get("transcript") or []
            text = "\n".join(transcript) if transcript else (state.get("user_input") or "")
        else:
            text = state.get("user_input") or ""
        if state.get("pdf_text"):
            text = f"{text}\n\nError log:\n{state['pdf_text']}"

        prompt = (
            "Extract the machine ID, error code, and a short description of the "
            "problem from this maintenance report. If the machine ID or error code "
            "is not clearly stated, leave that field null rather than guessing.\n\n"
            f"Report:\n{text}"
        )
        extracted = llm.generate_structured(prompt, ExtractedError)

        missing = []
        if extracted.machine_id is None:
            missing.append("machine ID")
        if extracted.error_code is None:
            missing.append("error code")
        if missing:
            return {
                "needs_clarification": True,
                "clarification_message": (
                    f"I need the {' and '.join(missing)} to continue — could you provide it?"
                ),
            }

        return {
            "machine_id": extracted.machine_id,
            "error_code": extracted.error_code,
            "error_description": extracted.description,
            "needs_clarification": False,
        }

    return extract_node
