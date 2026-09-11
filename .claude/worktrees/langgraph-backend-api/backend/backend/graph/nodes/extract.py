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
        transcript = state.get("transcript")
        if not transcript:
            # Fall back to the single-turn input when no transcript has been
            # accumulated yet (e.g. direct unit-test invocation).
            transcript = [state["user_input"]] if state.get("user_input") else []
        text = "\n".join(transcript)
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
