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


def test_extract_node_builds_prompt_from_full_transcript(fake_llm):
    """Both turns' text must reach the prompt, not just the latest message.

    This is what lets a clarification round-trip succeed: turn 1 gives the
    machine ID, extract_node asks for the error code, and turn 2's reply
    (just the error code) must be combined with turn 1's text for extraction
    to succeed.
    """
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    node({
        "user_input": "E101",
        "transcript": ["CNC-Mill-200 is acting up", "E101"],
    })

    assert "CNC-Mill-200 is acting up" in llm.prompts[0]
    assert "E101" in llm.prompts[0]


def test_extract_node_includes_pdf_text_in_prompt(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    node({"user_input": "see attached log", "pdf_text": "ERROR LOG: E101 detected at 14:02"})

    assert "ERROR LOG: E101 detected at 14:02" in llm.prompts[0]
