import re

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    sentences = []
    for paragraph in _PARAGRAPH_SPLIT_RE.split(text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences.extend(s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip())
    return sentences


def _take_trailing_overlap(sentences: list[str], overlap_tokens: int) -> list[str]:
    overlap: list[str] = []
    token_count = 0
    for sentence in reversed(sentences):
        overlap.insert(0, sentence)
        token_count += len(sentence.split())
        if token_count >= overlap_tokens:
            break
    return overlap


def chunk_text(text: str, max_tokens: int = 300, overlap_tokens: int = 40) -> list[str]:
    """Split text into token-bounded chunks on sentence boundaries.

    Word count is used as a token proxy — good enough for sizing chunks
    without adding a tokenizer dependency. Chunks overlap by roughly
    `overlap_tokens` so a procedure spanning a chunk boundary isn't lost
    entirely from either chunk. A single sentence longer than max_tokens is
    kept whole rather than cut mid-sentence.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = len(sentence.split())
        if current and current_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(current))
            current = _take_trailing_overlap(current, overlap_tokens)
            current_tokens = sum(len(s.split()) for s in current)
        current.append(sentence)
        current_tokens += sentence_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks
