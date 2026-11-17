import time
import httpx
from loguru import logger
from app.core.config import get_settings


class LLMError(Exception):
    """Sanitized error suitable for API clients. Never includes upstream bodies."""


class LLMClient:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    def complete(self, messages):
        settings = self.settings
        token = settings.openrouter_api_key.get_secret_value()
        if not token or not settings.openrouter_model.strip():
            raise LLMError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL in your private environment")
        attempts = min(2, max(0, settings.llm_max_retries)) + 1
        timeout = min(30, max(1, settings.llm_timeout_seconds))
        body = {"model": settings.openrouter_model, "messages": messages, "temperature": 0,
                "max_tokens": min(4000, max(300, settings.llm_max_tokens)),
                "response_format": {"type":"json_object"}, "stream": False}
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(5, timeout)),
                          transport=self.transport, follow_redirects=False) as client:
            for attempt in range(attempts):
                try:
                    # Do not log headers, request data, provider responses, or exception text.
                    response = client.post(self.URL, json=body,
                                           headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"})
                except (httpx.TimeoutException, httpx.TransportError):
                    logger.warning("OpenRouter transport failure, attempt {}", attempt+1)
                    if attempt+1 == attempts:
                        raise LLMError("OpenRouter request timed out or could not connect") from None
                else:
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            choice = data["choices"][0]
                            content = choice["message"]["content"]
                            if choice.get("finish_reason") not in {"stop", None} or not isinstance(content, str) or len(content) > 32000:
                                raise ValueError("Incomplete or oversized completion")
                            return content
                        except (ValueError, TypeError, KeyError, IndexError):
                            raise LLMError("OpenRouter returned an invalid or incomplete completion") from None
                    retryable = response.status_code in {408, 429, 500, 502, 503, 504}
                    logger.warning("OpenRouter HTTP status {}, attempt {}", response.status_code, attempt+1)
                    if not retryable or attempt+1 == attempts:
                        hint = {401:"Check the OpenRouter API key", 403:"OpenRouter access denied",
                                402:"Check OpenRouter credits", 400:"Check model support for JSON mode and request parameters"}.get(response.status_code, "OpenRouter service request failed")
                        raise LLMError(f"{hint} (HTTP {response.status_code})")
                # Bounded exponential backoff; never honor an unbounded Retry-After.
                time.sleep(min(2, 0.5 * 2**attempt))
        raise LLMError("OpenRouter service request failed")
