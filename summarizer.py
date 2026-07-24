"""Grounded hierarchical summarization for medical chronology events."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from huggingface_hub import InferenceClient

DEFAULT_MODEL = "google/medgemma-4b-it"
MAX_CHUNK_CHARS = 12_000

SYSTEM_PROMPT = """You summarize longitudinal medical records for review.
Use ONLY facts explicitly present in the supplied events. Do not infer diagnoses,
causes, indications, treatment rationale, or outcomes. Preserve chronology.
Every factual statement must cite one or more supporting event IDs in square
brackets, for example [E000123]. If records conflict, state the conflict and cite
both sources. If a fact is unknown, say it is unknown. Do not provide medical advice.
"""


def _event_text(row: pd.Series) -> str:
    return (
        f"[{row['event_id']}]\n"
        f"Date: {row['encounter_date'].strftime('%Y-%m-%d')}\n"
        f"Record type: {row['record_type']}\n"
        f"Medicine type: {row['medicine_type']}\n"
        f"Provider: {row['primary_provider']}\n"
        f"Facility: {row['facility']}\n"
        f"Body parts: {row['body_parts']}\n"
        f"Narrative: {row['summary']}"
    )


def _chunk_events(df: pd.DataFrame, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0

    ordered = df.sort_values("encounter_date", ascending=True)
    for _, row in ordered.iterrows():
        event = _event_text(row)
        if current and current_chars + len(event) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
        current.append(event)
        current_chars += len(event)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _complete(client: InferenceClient, prompt: str, max_tokens: int = 1400) -> str:
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The inference endpoint returned an empty response.")
    return content.strip()


def summarize_events(
    df: pd.DataFrame,
    *,
    endpoint_url: str,
    api_token: str,
    focus: str = "Overall medical history",
) -> str:
    """Summarize filtered chronology events using map-reduce with event citations."""
    if df.empty:
        raise ValueError("No events were supplied for summarization.")
    if not endpoint_url.strip():
        raise ValueError("A Hugging Face Inference Endpoint URL is required.")

    client = InferenceClient(base_url=endpoint_url.strip(), api_key=api_token or None, timeout=180)
    chunks = _chunk_events(df)

    partials: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        prompt = f"""Create a concise factual summary for the requested focus: {focus}.
This is source chunk {index} of {len(chunks)}. Retain dates, diagnoses, treatments,
medications, investigations, procedures, material changes, and explicitly documented
status when relevant to the focus. Cite every statement with event IDs.

SOURCE EVENTS:\n{chunk}"""
        partials.append(_complete(client, prompt))

    if len(partials) == 1:
        return partials[0]

    combined = "\n\n".join(
        f"INTERMEDIATE SUMMARY {i}\n{text}" for i, text in enumerate(partials, start=1)
    )
    final_prompt = f"""Synthesize the intermediate summaries below into one longitudinal
medical summary focused on: {focus}.

Remove duplication, preserve chronology, retain the original [E...] citations,
and do not introduce facts not present in the intermediate summaries.

{combined}"""
    return _complete(client, final_prompt, max_tokens=1800)
