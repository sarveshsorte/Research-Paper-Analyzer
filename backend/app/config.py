from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "paper_chunks"

    bm25_index_path: str = "storage/bm25/index.sqlite3"
    # The backend's own SQLite database: users, documents, chunks and jobs.
    storage_path: str = "storage/researchlens.sqlite3"

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int = 2048

    reranker_base_url: str | None = None
    reranker_api_key: str | None = None
    reranker_model: str | None = None

    nebius_base_url: str = (
        "https://api.tokenfactory.us-central1.nebius.com/v1/"
    )
    nebius_api_key: str | None = None
    nebius_model: str | None = None

    top_k_dense: int = Field(default=25, ge=1, le=100)
    top_k_sparse: int = Field(default=25, ge=1, le=100)
    top_k_reranked: int = Field(default=8, ge=1, le=50)
    max_context_tokens: int = Field(default=6000, ge=500)
    min_relevance_score: float = Field(default=0.65, ge=0.0, le=1.0)
    max_question_length: int = Field(default=4000, ge=100, le=20000)
    max_papers_per_query: int = Field(default=20, ge=1, le=100)
    use_fake_providers: bool | None = None

    # Firebase Authentication. The service-account JSON is a secret: keep it out of
    # git. When the path is unset, Google Application Default Credentials are used.
    firebase_credentials_path: str | None = None
    firebase_project_id: str | None = None

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
