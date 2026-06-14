"""Regulatory intelligence — RAG over the ICH/FDA/EMA/WHO guidance corpus (Prompt 10).

:mod:`rag_search` retrieves the most relevant guidance chunks for a query (each with its source
document, section, effective date, official-source link, and the MolTrace calculator/module it
maps to) and synthesises an answer grounded ONLY in the retrieved chunks, with explicit citations.

Retrieval and synthesis both have a zero-dependency native path (lexical retrieval + extractive
synthesis) so the engine runs and tests offline; the production paths (vector embeddings, Claude
synthesis) plug in through injectable backends behind the optional ``rag`` extra. Licences are
honoured end to end: ICH/EMA/WHO chunks are internal-only, kept to minimal excerpts, and always
cited + linked to the official source. Any specific numeric limit defers to the deterministic
calculators — the LLM never invents a regulated number.
"""

from __future__ import annotations

from moltrace.regulatory.intelligence.rag_search import (
    AnthropicLLM,
    FaqEvalReport,
    LexicalRetriever,
    LLMClient,
    RegulatoryFaqPair,
    RegulatorySearchResult,
    RetrievedChunk,
    Retriever,
    SynthesizedAnswer,
    VectorRetriever,
    evaluate_faq_pairs,
    regulatory_search,
    synthesize_answer,
    workflow_relevance,
)

__all__ = [
    "AnthropicLLM",
    "FaqEvalReport",
    "LLMClient",
    "LexicalRetriever",
    "RegulatoryFaqPair",
    "RegulatorySearchResult",
    "RetrievedChunk",
    "Retriever",
    "SynthesizedAnswer",
    "VectorRetriever",
    "evaluate_faq_pairs",
    "regulatory_search",
    "synthesize_answer",
    "workflow_relevance",
]
