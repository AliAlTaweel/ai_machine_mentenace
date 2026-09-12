import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_similarity(query_embedding: list[float], corpus: list[dict]) -> list[str]:
    """Rank corpus items (each a dict with "manual_id" and "embedding") by
    cosine similarity to query_embedding, most similar first.

    Brute-force, in-process ranking — deliberately independent of Atlas
    $vectorSearch so retrieval quality can be evaluated without a live
    cluster.
    """
    scored = [(item["manual_id"], cosine_similarity(query_embedding, item["embedding"])) for item in corpus]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [manual_id for manual_id, _ in scored]


def recall_at_k(cases: list[tuple[str, str]], corpus: list[dict], embed_fn, k: int) -> float:
    """Fraction of (query, expected_manual_id) cases where expected_manual_id
    appears in the top-k ranked results for that query."""
    if not cases:
        return 1.0
    hits = sum(1 for query, expected_id in cases if expected_id in rank_by_similarity(embed_fn(query), corpus)[:k])
    return hits / len(cases)
