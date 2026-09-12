"""Retrieval-quality regression tests for the seeded manuals.

These exist so a change to chunking, the embedding model, or the RAG query
construction has to prove it doesn't regress retrieval, rather than relying
on eyeballing search results. Ranking is done with a brute-force in-process
cosine similarity (backend.rag.eval), independent of Atlas $vectorSearch, so
these run without a live cluster.
"""

import pytest

from backend.rag.embeddings import embed_text
from backend.rag.eval import rank_by_similarity, recall_at_k
from backend.rag.manuals_seed import SAMPLE_MANUALS

# (query, expected_manual_id). Query text mirrors how rag_lookup_node builds
# its query: f"{machine_id} {error_code} {error_description}". One exact-wording
# case and one paraphrased case per seeded manual, so the eval also covers
# queries that don't just echo the manual's own vocabulary back at it.
EVAL_CASES = [
    ("CNC-Mill-200 E101 grinding noise above 2000 RPM", "CNC-MILL-200-E101"),
    ("CNC-Mill-200 E101 machine vibrates and makes a grinding sound at high speed", "CNC-MILL-200-E101"),
    ("CNC-Mill-200 E204 drive motor overcurrent", "CNC-MILL-200-E204"),
    ("CNC-Mill-200 E204 the drive motor keeps drawing too much current and overheating", "CNC-MILL-200-E204"),
    ("Conveyor-Belt-A7 B12 belt slippage and tearing", "CONVEYOR-A7-B12"),
    ("Conveyor-Belt-A7 B12 the belt looks worn and frayed along the edges", "CONVEYOR-A7-B12"),
    ("Conveyor-Belt-A7 B20 drive motor stall", "CONVEYOR-A7-B20"),
    ("Conveyor-Belt-A7 B20 conveyor motor stalled and rollers seem jammed", "CONVEYOR-A7-B20"),
    ("Hydraulic-Press-9 H33 loss of hydraulic pressure", "HYDRAULIC-PRESS-9-H33"),
    ("Hydraulic-Press-9 H33 fluid leaking around the valve, losing pressure", "HYDRAULIC-PRESS-9-H33"),
]

# search_manuals is called with top_k=3 in production (rag_lookup_node) —
# recall@3 is what actually determines whether the LLM ever sees the right
# excerpt.
RECALL_AT_K = 3
BASELINE_RECALL = 0.8


@pytest.fixture(scope="module")
def corpus():
    return [
        {"manual_id": manual["manual_id"], "embedding": embed_text(manual["chunk_text"])}
        for manual in SAMPLE_MANUALS
    ]


@pytest.mark.parametrize("query,expected_manual_id", EVAL_CASES)
def test_expected_manual_is_in_top_k(corpus, query, expected_manual_id):
    ranked = rank_by_similarity(embed_text(query), corpus)
    assert expected_manual_id in ranked[:RECALL_AT_K], (
        f"expected {expected_manual_id!r} in top {RECALL_AT_K} for query {query!r}, got {ranked}"
    )


def test_recall_at_k_meets_baseline(corpus):
    recall = recall_at_k(EVAL_CASES, corpus, embed_text, k=RECALL_AT_K)
    assert recall >= BASELINE_RECALL, (
        f"recall@{RECALL_AT_K} dropped to {recall:.2f} (baseline {BASELINE_RECALL}) — "
        "a chunking, embedding, or query-construction change hurt retrieval quality"
    )
