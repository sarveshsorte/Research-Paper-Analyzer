import json
import re

from query_pipeline.app.schemas.generation import GeneratedAnswer


VALID_CLAIM_TYPES = {"fact", "comparison", "interpretation", "uncertainty", "definition"}


def parse_generated_answer(
    raw: str, fallback_source_ids: list[str] | None = None
) -> GeneratedAnswer:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            match_json = re.search(r"(\{.*\})", text, re.DOTALL)
            if match_json:
                text = match_json.group(1).strip()

    fallback_ids = fallback_source_ids if fallback_source_ids else ["S1"]
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            claims = data.get("claims")
            if isinstance(claims, list):
                sanitized_claims = []
                for claim in claims:
                    if isinstance(claim, str):
                        sanitized_claims.append({
                            "text": claim,
                            "source_ids": fallback_ids,
                            "claim_type": "fact",
                            "confidence": 1.0,
                        })
                    elif isinstance(claim, dict):
                        c_text = claim.get("text", "")
                        if not c_text:
                            continue
                        c_sources = claim.get("source_ids")
                        if not c_sources:
                            c_sources = fallback_ids
                        c_type = claim.get("claim_type", "fact")
                        if c_type not in VALID_CLAIM_TYPES:
                            c_type = "fact"
                        c_conf = claim.get("confidence", 1.0)
                        try:
                            c_conf = max(0.0, min(1.0, float(c_conf)))
                        except (ValueError, TypeError):
                            c_conf = 1.0
                        sanitized_claims.append({
                            "text": str(c_text),
                            "source_ids": list(c_sources),
                            "claim_type": c_type,
                            "confidence": c_conf,
                        })
                data["claims"] = sanitized_claims
            if "uncertainties" in data and not isinstance(data["uncertainties"], list):
                data["uncertainties"] = []
        return GeneratedAnswer.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Generator returned invalid JSON or schema") from exc
