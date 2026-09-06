"""
Pluggable LLM layer. The important design decision isn't which provider you
call -- it's the prompt contract: the model is instructed to answer ONLY from
the provided chunks and explicitly say when the context doesn't contain the
answer, instead of falling back on its training-data guess. That's what
"grounded" actually means, and it's the difference between a RAG demo and a
RAG system you'd trust output from.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.chunking import Chunk

SYSTEM_PROMPT = """You are a codebase assistant. Answer the user's question using ONLY the \
provided code/document excerpts below. Each excerpt is labeled with its file path and line range.

Rules:
- If the excerpts don't contain enough information to answer, say so explicitly \
instead of guessing from general knowledge.
- When you reference something from an excerpt, cite it inline like: (file.py:12-30)
- Be concise and technical. Do not repeat the excerpts verbatim; explain them.
"""


def build_context_block(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"--- {c.file} (lines {c.start_line}-{c.end_line}) ---\n{c.text}")
    return "\n\n".join(parts)


class LLMClient(ABC):
    @abstractmethod
    def generate(self, question: str, chunks: list[Chunk]) -> str:
        ...


class MockLLMClient(LLMClient):
    """Deterministic, no-API-key client. Used for local dev, tests, and demoing
    the retrieval quality on its own before wiring up a paid provider."""

    def generate(self, question: str, chunks: list[Chunk]) -> str:
        if not chunks:
            return "No relevant context was found in the indexed repository for this question."
        top = chunks[0]
        return (
            f"[mock provider -- set LLM_PROVIDER=openai or anthropic for real answers]\n"
            f"Based on the top match in {top.file} (lines {top.start_line}-{top.end_line}), "
            f"here is the most relevant excerpt:\n\n{top.text[:400]}"
        )


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, question: str, chunks: list[Chunk]) -> str:
        context = build_context_block(chunks)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

class GroqClient(LLMClient):
    """Groq is OpenAI-API-compatible, so this reuses the `openai` SDK --
    just pointed at Groq's endpoint instead of OpenAI's."""

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self._model = model

    def generate(self, question: str, chunks: list[Chunk]) -> str:
        context = build_context_block(chunks)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, question: str, chunks: list[Chunk]) -> str:
        context = build_context_block(chunks)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))


def get_llm_client(provider: str, openai_api_key: str | None, openai_model: str,
                    anthropic_api_key: str | None, anthropic_model: str,
                    groq_api_key: str | None = None, groq_model: str = "llama-3.3-70b-versatile") -> LLMClient:
    if provider == "openai":
        if not openai_api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set")
        return OpenAIClient(openai_api_key, openai_model)
    if provider == "anthropic":
        if not anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set")
        return AnthropicClient(anthropic_api_key, anthropic_model)
    if provider == "groq":
        if not groq_api_key:
            raise ValueError("LLM_PROVIDER=groq requires GROQ_API_KEY to be set")
        return GroqClient(groq_api_key, groq_model)
    return MockLLMClient()
