from backend.rag.embeddings import embed_text, EMBEDDING_DIM


def test_embed_text_returns_correct_dimension():
    vector = embed_text("bearing failure on the main spindle")
    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vector)


def test_embed_text_is_deterministic():
    text = "hydraulic pressure loss"
    assert embed_text(text) == embed_text(text)
