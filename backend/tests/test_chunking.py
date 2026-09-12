from backend.rag.chunking import chunk_text


def test_chunk_text_returns_single_chunk_for_short_text():
    text = "Error E101 indicates bearing wear. Replace the bearing and retest."

    chunks = chunk_text(text, max_tokens=300, overlap_tokens=40)

    assert chunks == [text]


def test_chunk_text_returns_empty_list_for_blank_text():
    assert chunk_text("   \n\n  ", max_tokens=300, overlap_tokens=40) == []


def test_chunk_text_splits_long_text_on_sentence_boundaries():
    sentences = [f"Sentence number {i} describes step {i} of the repair procedure." for i in range(20)]
    text = " ".join(sentences)

    chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.rstrip().endswith(".")


def test_chunk_text_never_cuts_a_sentence_in_half():
    sentences = [f"This is sentence {i} of the manual, describing a repair step in detail." for i in range(15)]
    text = " ".join(sentences)

    chunks = chunk_text(text, max_tokens=40, overlap_tokens=8)

    reconstructed = " ".join(chunks)
    for sentence in sentences:
        assert sentence in reconstructed


def test_chunk_text_overlaps_consecutive_chunks():
    sentences = [f"Step {i}: perform inspection number {i} on the assembly." for i in range(20)]
    text = " ".join(sentences)

    chunks = chunk_text(text, max_tokens=30, overlap_tokens=10)

    assert len(chunks) >= 2
    first_chunk_sentences = chunks[0].split(". ")
    second_chunk_sentences = chunks[1].split(". ")
    shared = set(first_chunk_sentences) & set(second_chunk_sentences)
    assert shared, "expected the tail of chunk N to reappear at the head of chunk N+1"


def test_chunk_text_keeps_oversized_single_sentence_whole():
    long_sentence = "This single sentence is deliberately long " + "and keeps going " * 30 + "before it ends."

    chunks = chunk_text(long_sentence, max_tokens=10, overlap_tokens=2)

    assert chunks == [long_sentence]


def test_chunk_text_splits_on_paragraph_breaks_too():
    text = "First paragraph sentence one. First paragraph sentence two.\n\nSecond paragraph sentence one."

    chunks = chunk_text(text, max_tokens=300, overlap_tokens=40)

    assert len(chunks) == 1
    assert "First paragraph sentence one." in chunks[0]
    assert "Second paragraph sentence one." in chunks[0]
