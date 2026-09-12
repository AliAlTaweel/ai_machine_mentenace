from typing import Callable

from pydantic import BaseModel

from backend.graph.state import GraphState
from backend.llm.base import LLMClient
from backend.rag.embeddings import embed_text
from backend.rag.vector_search import search_manuals


class RequiredPart(BaseModel):
    part_id: str
    name: str
    quantity: int


class DiagnosisResult(BaseModel):
    diagnosis: str
    repair_steps: list[str]
    required_parts: list[RequiredPart]
    no_procedure_found: bool = False


def make_rag_lookup_node(
    llm: LLMClient,
    manuals_collection,
    embed_fn=embed_text,
    search_fn=search_manuals,
) -> Callable[[GraphState], dict]:
    def rag_lookup_node(state: GraphState) -> dict:
        query_text = f"{state['machine_id']} {state['error_code']} {state['error_description']}"
        query_embedding = embed_fn(query_text)
        chunks = search_fn(
            manuals_collection,
            query_embedding,
            top_k=3,
            machine_type=state["machine_id"],
        )

        if not chunks:
            return {
                "no_procedure_found": True,
                "diagnosis": "No relevant repair procedure was found in the technical manuals for this error.",
                "repair_steps": [],
                "required_parts": [],
            }

        context = "\n\n".join(c["chunk_text"] for c in chunks)
        prompt = (
            "Using ONLY the following excerpts from technical repair manuals, diagnose "
            f"the fault and list the repair steps and required spare parts for error "
            f"{state['error_code']} on machine {state['machine_id']}.\n\n"
            f"Manual excerpts:\n{context}\n\n"
            "If the excerpts do not actually cover this error, set no_procedure_found "
            "to true and leave diagnosis/repair_steps/required_parts empty rather than "
            "guessing."
        )
        result = llm.generate_structured(prompt, DiagnosisResult)

        diagnosis = (
            "No relevant repair procedure was found in the technical manuals for this error."
            if result.no_procedure_found and not result.diagnosis.strip()
            else result.diagnosis
        )

        return {
            "no_procedure_found": result.no_procedure_found,
            "diagnosis": diagnosis,
            "repair_steps": result.repair_steps,
            "required_parts": [p.model_dump() for p in result.required_parts],
        }

    return rag_lookup_node
