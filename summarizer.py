"""Hierarchical medical-record summarization through Hugging Face Inference."""

from __future__ import annotations

import pandas as pd
from huggingface_hub import InferenceClient

DEFAULT_MODEL = "Falconsai/medical_summarization"
# The model tokenizer has a 512-token limit. A conservative character limit keeps
# most requests below that boundary without adding a tokenizer dependency.
MAX_CHUNK_CHARS = 1_600
MAX_REDUCTION_ROUNDS = 8


def _event_text(row: pd.Series) -> str:
    """Convert one chronology row to compact, human-readable source text."""
    metadata = [
        row["encounter_date"].strftime("%Y-%m-%d"),
        row["record_type"],
        row["medicine_type"],
        row["primary_provider"],
        row["facility"],
    ]
    header = " | ".join(str(value).strip() for value in metadata if str(value).strip())
    body_parts = str(row["body_parts"]).strip()
    narrative = str(row["summary"]).strip()
    parts = [header]
    if body_parts:
        parts.append(f"Body parts: {body_parts}")
    if narrative:
        parts.append(narrative)
    return ". ".join(part for part in parts if part)


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split long text into approximately sentence-aligned chunks."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_at = remaining.rfind(". ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind(" ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip(". ")
    if remaining:
        chunks.append(remaining)
    return chunks


def _pack_texts(texts: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack multiple texts into bounded chunks while preserving order."""
    pieces: list[str] = []
    for text in texts:
        pieces.extend(_split_text(text, max_chars=max_chars))

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for piece in pieces:
        separator_chars = 2 if current else 0
        if current and current_chars + separator_chars + len(piece) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
            separator_chars = 0
        current.append(piece)
        current_chars += separator_chars + len(piece)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _chunk_events(df: pd.DataFrame) -> list[str]:
    """Group chronology events into model-sized chronological text chunks."""
    ordered = df.sort_values("encounter_date", ascending=True)
    event_texts = [_event_text(row) for _, row in ordered.iterrows()]
    return _pack_texts(event_texts)


def _summarize_text(client: InferenceClient, text: str) -> str:
    """Summarize one model-sized text block."""
    result = client.summarization(
        text,
        model=DEFAULT_MODEL,
        truncation="longest_first",
    )
    summary = getattr(result, "summary_text", None)
    if summary is None and isinstance(result, dict):
        summary = result.get("summary_text")
    if not summary:
        summary = str(result).strip()
    if not summary:
        raise RuntimeError("Hugging Face returned an empty summary.")
    return summary.strip()


def _reduce_summaries(client: InferenceClient, summaries: list[str]) -> str:
    """Recursively summarize intermediate outputs until one summary remains."""
    current = summaries
    for _ in range(MAX_REDUCTION_ROUNDS):
        if len(current) == 1:
            return current[0]

        packed = _pack_texts(current)
        next_round = [_summarize_text(client, chunk) for chunk in packed]

        # Normally packing several short summaries into each request reduces the
        # list immediately. If every summary is already near the input limit,
        # force progress by combining pairs and allowing the next pass to re-split.
        if len(next_round) >= len(current) and len(next_round) > 1:
            next_round = [
                " ".join(next_round[index : index + 2])
                for index in range(0, len(next_round), 2)
            ]
        current = next_round

    return "\n\n".join(current)


def summarize_events(
    df: pd.DataFrame,
    *,
    api_token: str,
    endpoint_url: str = "",
    focus: str = "",
) -> str:
    """Summarize filtered chronology events using HF's serverless API.

    ``endpoint_url`` and ``focus`` are accepted for backward compatibility with
    the first MedGemma prototype; they are intentionally unused by this task-
    specific summarization model.
    """
    del endpoint_url, focus

    if df.empty:
        raise ValueError("No events were supplied for summarization.")
    if not api_token.strip():
        raise ValueError("A Hugging Face API token is required.")

    client = InferenceClient(
        provider="hf-inference",
        api_key=api_token.strip(),
        timeout=180,
    )
    chunks = _chunk_events(df)
    if not chunks:
        raise ValueError("The selected events contain no text to summarize.")

    partials = [_summarize_text(client, chunk) for chunk in chunks]
    return _reduce_summaries(client, partials)
