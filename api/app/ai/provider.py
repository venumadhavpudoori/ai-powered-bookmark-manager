"""AI provider interface — swappable LLM + embedding backend.

Currently implements OpenAI. To swap providers, implement a new class
that inherits from AIProvider and update the factory function.
"""

import abc
import logging
from dataclasses import dataclass

import openai
import tiktoken

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Structured output from the LLM enrichment call."""
    summary: str
    takeaways: list[str]
    tags: list[str]
    input_tokens: int
    output_tokens: int


@dataclass
class EmbeddingResult:
    """Result from the embedding call."""
    embeddings: list[list[float]]
    model_name: str
    input_tokens: int


class AIProvider(abc.ABC):
    """Abstract interface for AI operations."""

    @abc.abstractmethod
    async def enrich(
        self, text: str, existing_tags: list[str], system_prompt: str
    ) -> EnrichmentResult:
        """Generate summary, takeaways, and tags from page text."""

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Generate embeddings for a list of text chunks."""

    @abc.abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single search query."""


class OpenAIProvider(AIProvider):
    """OpenAI-compatible provider (works with OpenAI, Azure, local proxies)."""

    def __init__(self) -> None:
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.llm_model = settings.LLM_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL
        self.embedding_dimension = settings.EMBEDDING_DIMENSION

    async def enrich(
        self, text: str, existing_tags: list[str], system_prompt: str
    ) -> EnrichmentResult:
        """Call the LLM to produce summary, takeaways, and tags."""
        import json

        from app.ai.prompts import build_enrich_prompt

        user_prompt = build_enrich_prompt(text, existing_tags)

        response = await self.client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1024,
        )

        content = response.choices[0].message.content or "{}"
        usage = response.usage

        # Parse and validate the JSON output
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error("LLM returned invalid JSON: %s", content[:200])
            raise ValueError("LLM returned invalid JSON")

        summary = data.get("summary", "")
        takeaways = data.get("takeaways", [])
        tags = data.get("tags", [])

        # Validate structure
        if not isinstance(summary, str):
            summary = str(summary)
        if not isinstance(takeaways, list):
            takeaways = []
        takeaways = [str(t) for t in takeaways[:5]]  # Cap at 5
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags[:8]]  # Cap at 8

        return EnrichmentResult(
            summary=summary,
            takeaways=takeaways,
            tags=tags,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Generate embeddings for a batch of text chunks."""
        response = await self.client.embeddings.create(
            model=self.embedding_model,
            input=texts,
            dimensions=self.embedding_dimension,
        )

        embeddings = [item.embedding for item in response.data]
        input_tokens = response.usage.total_tokens if response.usage else 0

        return EmbeddingResult(
            embeddings=embeddings,
            model_name=self.embedding_model,
            input_tokens=input_tokens,
        )

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a search query."""
        result = await self.embed([query])
        return result.embeddings[0]


class MockAIProvider(AIProvider):
    """Mock provider for testing without external API calls."""

    def __init__(self) -> None:
        self.llm_model = "mock-llm"
        self.embedding_model = "mock-embed"
        self.embedding_dimension = 1536

    async def enrich(
        self, text: str, existing_tags: list[str], system_prompt: str = ""
    ) -> EnrichmentResult:
        merged_tags = list(dict.fromkeys(existing_tags + ["ai", "bookmarks", "search"]))[:5]
        return EnrichmentResult(
            summary=f"Mock summary of content ({len(text)} characters).",
            takeaways=["Takeaway 1: core concept", "Takeaway 2: key implementation", "Takeaway 3: practical usage"],
            tags=merged_tags,
            input_tokens=100,
            output_tokens=50,
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        # Deterministic dummy vector with length 1536
        dummy = [0.01 * (i % 50) for i in range(self.embedding_dimension)]
        return EmbeddingResult(
            embeddings=[dummy for _ in texts],
            model_name=self.embedding_model,
            input_tokens=len(texts) * 20,
        )

    async def embed_query(self, query: str) -> list[float]:
        return [0.01 * (i % 50) for i in range(self.embedding_dimension)]


def get_ai_provider() -> AIProvider:
    """Factory function to get the configured AI provider."""
    provider_name = settings.AI_PROVIDER.lower()
    if provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "mock":
        return MockAIProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider_name}")


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens in text using tiktoken."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
