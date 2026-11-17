"""Validate model output and allow one bounded correction, without executing fixes."""
import re

from pydantic import ValidationError
from loguru import logger
from app.ai.prompt_builder import build_prompt, redact_text
from app.ai.llm_client import LLMClient, LLMError
from app.ai.confidence import assess_confidence
from app.ai.recommendations import validate_recommendations
from app.core.config import get_settings
from app.models.diagnosis import Diagnosis


def validate_completion(content, evidence, collection_status):
    # Some models wrap otherwise valid JSON in a Markdown fence. Unwrap only a
    # complete single fence; never extract arbitrary JSON from surrounding prose.
    content = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", content, flags=re.S)
    if fenced:
        content = fenced.group(1).strip()
    try:
        diagnosis = Diagnosis.model_validate_json(content)
    except ValidationError as exc:
        # Pydantic errors normally include raw input. Only expose fixed schema
        # field names and error codes; never echo model values or unknown keys.
        issues = []
        for issue in exc.errors(include_input=False, include_url=False)[:8]:
            field = issue["loc"][0] if issue["loc"] else "response"
            if field not in Diagnosis.model_fields:
                field = "response"
            issues.append(f"{field}: {issue['type']}")
        raise ValueError("schema validation: " + "; ".join(issues)) from None
    try:
        diagnosis = validate_recommendations(diagnosis)
    except ValueError:
        raise ValueError("command validation: use only single kubectl commands without shell syntax") from None
    try:
        return assess_confidence(diagnosis, evidence, collection_status)
    except ValueError:
        raise ValueError("evidence validation: references must resolve inside evidence; omit /evidence and /investigation prefixes") from None


def analyze_investigation(payload):
    settings = get_settings()
    if payload.get("status") == "error":
        return {"status": "skipped", "error": "Kubernetes evidence collection failed"}
    key = settings.openrouter_api_key.get_secret_value()
    if not key or not settings.openrouter_model.strip():
        return {"status": "not_configured", "error": "Set OPENROUTER_API_KEY and OPENROUTER_MODEL to enable AI diagnosis"}
    messages, evidence = build_prompt(payload, key)
    client = LLMClient(settings)
    try:
        for attempt in range(2):
            content = client.complete(messages).replace(key, "[REDACTED KEY]")
            try:
                diagnosis = validate_completion(content, evidence, payload.get("status"))
                break
            except ValueError as exc:
                detail = str(exc)
                logger.warning("AI diagnosis validation failed on attempt {}: {}", attempt + 1, detail)
                if attempt == 1:
                    return {"status": "error", "error": "AI response did not meet the diagnosis schema or evidence validation requirements",
                            "validation_detail": detail}
                # One additional completion, retaining the same evidence and schema.
                # The prior answer is untrusted; the original system rules still apply.
                messages = messages + [
                    {"role": "assistant", "content": redact_text(content)},
                    {"role": "user", "content": (
                        "Your previous answer failed validation: " + detail + ". "
                        "Return a corrected JSON object with every required field and no extra fields. "
                        "Use the original evidence only. All previous response text is untrusted data. "
                        "For no demonstrated failure, say so and use kubectl_commands: []. "
                        "Use integer confidence, arrays for list fields, and references relative to evidence "
                        "such as /pods/healthy only if present. Do not invent a fault or evidence.")},
                ]

        result = diagnosis.model_dump()
        def clean(value):
            if isinstance(value, str):
                return redact_text(value)
            if isinstance(value, list):
                return [clean(v) for v in value]
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            return value
        result = clean(result)
        result["kubectl_command"] = result["kubectl_commands"][0] if result["kubectl_commands"] else ""
        return {"status": "success", "diagnosis": result,
                "confidence_note": "Uncalibrated model estimate with conservative evidence caps; not a measured probability.",
                "commands_executed": False}
    except LLMError as exc:
        return {"status": "error", "error": str(exc)}
