from typing import Literal

from pydantic import BaseModel, Field, field_validator


ClaimType = Literal[
    "fact",
    "comparison",
    "interpretation",
    "uncertainty",
    "definition",
]


class GeneratedClaim(BaseModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    claim_type: ClaimType = "fact"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GeneratedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    claims: list[GeneratedClaim] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be empty")
        return value