from typing import Protocol

from openai import AsyncOpenAI


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]:
        ...


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot embed empty text")
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
        except Exception as exc:
            raise ConnectionError("Embedding request failed") from exc
        data = response.data
        if not isinstance(data, list) or not data:
            raise ValueError("Embedding provider returned no data")
        vector = data[0].embedding
        if not isinstance(vector, list):
            raise ValueError("Embedding provider returned an invalid vector")
        return [float(value) for value in vector]

