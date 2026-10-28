from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "paper_chunks"

    bm25_index_path: str = "storage/bm25/index.sqlite3"

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int = 2048

    reranker_base_url: str | None = None
    reranker_api_key: str | None = None
    reranker_model: str | None = None

    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str | None = None
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"

    top_k_dense: int = Field(default=20, ge=1, le=100)
    top_k_sparse: int = Field(default=20, ge=1, le=100)
    top_k_reranked: int = Field(default=6, ge=1, le=50)
    max_context_tokens: int = Field(default=4000, ge=500)
    min_relevance_score: float = Field(default=0.35, ge=0.0, le=1.0)
    max_question_length: int = Field(default=4000, ge=100, le=20000)
    max_papers_per_query: int = Field(default=20, ge=1, le=100)
    use_fake_providers: bool | None = None

    model_config = SettingsConfigDict(
        env_file=(
            ".env",
            str(Path(__file__).resolve().parents[2] / "query_pipeline" / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.use_fake_providers is None:
            self.use_fake_providers = self.app_env != "production"
        if self.app_env == "production" and self.use_fake_providers:
            raise ValueError("Fake providers are not allowed in production")
        if self.embedding_dimension < 1:
            raise ValueError("Embedding dimension must be positive")
        # NVIDIA's embedding and chat endpoints commonly share one credential.
        # Keep the separate setting available for deployments with distinct keys.
        if not self.embedding_api_key:
            self.embedding_api_key = self.nvidia_api_key
        if not self.embedding_base_url:
            self.embedding_base_url = self.nvidia_base_url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
