from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalFilters(BaseModel):
    sections: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_page_range(self) -> "RetrievalFilters":
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_start > self.page_end
        ):
            raise ValueError("page_start must not be greater than page_end")
        return self


class RetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    workspace_id: str
    paper_id: str
    paper_title: str
    text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    section: str | None = None
    content_type: str = "text"
    chunk_index: int | None = None
    content_hash: str | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


class EvidenceSource(BaseModel):
    source_id: str
    candidate: RetrievalCandidate