import operator
from typing import Annotated, TypedDict


class GraphState(TypedDict, total=False):
    user_input: str
    transcript: Annotated[list[str], operator.add]
    pdf_text: str | None
    machine_id: str | None
    error_code: str | None
    error_description: str | None
    needs_clarification: bool
    clarification_message: str | None
    diagnosis: str | None
    repair_steps: list[str] | None
    no_procedure_found: bool
    required_parts: list[dict] | None
    inventory_status: list[dict] | None
    needs_approval: bool
    approval_decision: str | None
    work_order_id: str | None
    work_order_status: str | None
