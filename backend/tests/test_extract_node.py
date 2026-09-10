from backend.graph.nodes.extract import make_extract_node, ExtractedError


def test_extract_node_returns_fields_when_complete(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="loud grinding noise")
    ])
    node = make_extract_node(llm)

    result = node({"user_input": "CNC mill throwing E101, grinding noise from spindle"})

    assert result == {
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "error_description": "loud grinding noise",
        "needs_clarification": False,
    }


def test_extract_node_asks_for_clarification_when_machine_id_missing(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id=None, error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    result = node({"user_input": "something is making a grinding noise, error E101"})

    assert result["needs_clarification"] is True
    assert "machine ID" in result["clarification_message"]


def test_extract_node_includes_pdf_text_in_prompt(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    node({"user_input": "see attached log", "pdf_text": "ERROR LOG: E101 detected at 14:02"})

    assert "ERROR LOG: E101 detected at 14:02" in llm.prompts[0]
