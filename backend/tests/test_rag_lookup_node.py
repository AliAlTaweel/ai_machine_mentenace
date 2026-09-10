from backend.graph.nodes.rag_lookup import make_rag_lookup_node, DiagnosisResult, RequiredPart


def fake_embed(text: str) -> list[float]:
    return [0.1, 0.2]


def test_rag_lookup_node_returns_diagnosis_when_manual_found(fake_llm):
    def fake_search(collection, query_embedding, top_k=3):
        return [{"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]}]

    llm = fake_llm(structured_responses=[
        DiagnosisResult(
            diagnosis="Main spindle bearing wear",
            repair_steps=["Power down", "Replace bearing"],
            required_parts=[RequiredPart(part_id="BEARING-X4", name="Bearing X4", quantity=1)],
        )
    ])
    node = make_rag_lookup_node(llm, manuals_collection=object(), embed_fn=fake_embed, search_fn=fake_search)

    result = node({"machine_id": "CNC-Mill-200", "error_code": "E101", "error_description": "grinding noise"})

    assert result["no_procedure_found"] is False
    assert result["diagnosis"] == "Main spindle bearing wear"
    assert result["required_parts"] == [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]


def test_rag_lookup_node_embeds_machine_id_and_error_code_with_description(fake_llm):
    """The search query must include machine_id/error_code, not just the free-text
    description — otherwise near-duplicate manual language for a different
    machine can be retrieved (e.g. two machines both describe a MOTOR-C2 fault)."""
    captured = {}

    def capturing_embed(text: str) -> list[float]:
        captured["text"] = text
        return [0.1, 0.2]

    def fake_search(collection, query_embedding, top_k=3):
        return [{"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]}]

    llm = fake_llm(
        structured_responses=[
            DiagnosisResult(
                diagnosis="Main spindle bearing wear",
                repair_steps=["Power down", "Replace bearing"],
                required_parts=[],
            )
        ]
    )
    node = make_rag_lookup_node(llm, manuals_collection=object(), embed_fn=capturing_embed, search_fn=fake_search)

    node({"machine_id": "CNC-Mill-200", "error_code": "E101", "error_description": "motor won't turn"})

    assert "CNC-Mill-200" in captured["text"]
    assert "E101" in captured["text"]
    assert "motor won't turn" in captured["text"]


def test_rag_lookup_node_reports_no_procedure_found_when_no_chunks(fake_llm):
    def fake_search(collection, query_embedding, top_k=3):
        return []

    llm = fake_llm()  # generate_structured should never be called
    node = make_rag_lookup_node(llm, manuals_collection=object(), embed_fn=fake_embed, search_fn=fake_search)

    result = node({"machine_id": "CNC-Mill-200", "error_code": "Z999", "error_description": "unknown issue"})

    assert result["no_procedure_found"] is True
    assert result["required_parts"] == []
    assert llm.prompts == []
