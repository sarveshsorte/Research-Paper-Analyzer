from typing import Protocol

from openai import AsyncOpenAI

from query_pipeline.app.generation.parser import parse_generated_answer
from query_pipeline.app.schemas.generation import GeneratedAnswer
from query_pipeline.app.schemas.retrieval import EvidenceSource


class GenerationProvider(Protocol):
    async def generate(
        self, question: str, evidence: list[EvidenceSource]
    ) -> GeneratedAnswer:
        ...


class OpenAICompatibleGenerationProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def generate(
        self, question: str, evidence: list[EvidenceSource]
    ) -> GeneratedAnswer:
        evidence_text = "\n".join(
            f"[{item.source_id}] {item.candidate.text}" for item in evidence
        )
        fallback_source_ids = [item.source_id for item in evidence] or ["S1"]
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                top_p=0.95,
                max_tokens=3500,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                stream=False,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert scientific researcher and analyst. "
                            "Provide an extensive, comprehensive, and thoroughly reasoned answer synthesizing all facts from the supplied evidence. "
                            "Structure your answer with detailed paragraphs (typically 3-5 well-developed paragraphs) covering background, core methodologies, quantitative and empirical findings, comparative nuances across papers, and key takeaways/implications. "
                            "Extract 3-6 distinct, meaningful factual claims from your answer. "
                            "Every factual claim in 'claims' must cite the exact source ID(s) where that fact appears "
                            "(e.g. [\"S1\"]). Return ONLY a valid JSON object with keys: answer (string), "
                            "claims (array of objects with text, source_ids (array of strings), "
                            "claim_type ('fact'), confidence (1.0)), and uncertainties (array of strings)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\nEvidence:\n{evidence_text}",
                    },
                ],
            )
            content = completion.choices[0].message.content or ""
        except Exception as exc:
            raise ConnectionError("Nemotron generation request failed") from exc

        if not content.strip():
            raise ValueError("Generation provider returned an empty response")
        return parse_generated_answer(content, fallback_source_ids=fallback_source_ids)

