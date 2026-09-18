"""
LLMAdapter — Client for DeepInfra OpenAI chat completions API.
Used for real-time search understanding/expansion (Qwen3.6) and offline catalog enrichment (Gemma 4 31B).
"""

import asyncio
import logging
import json
import re
import httpx
from typing import Optional, Dict, Any, List
from app.config import settings
from app.services.http_pool import get_client, deepinfra_llm_breaker

logger = logging.getLogger(__name__)


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def _clean_llm_response(text: str) -> str:
    """Strip <think>...</think> blocks and markdown code fences from LLM text."""
    if not text:
        return ""
    # Remove closed <think>...</think> blocks first
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()
    # If a stray unclosed <think> tag remained at the end, clean it
    if "<think>" in cleaned.lower():
        cleaned = _UNCLOSED_THINK_RE.sub("", cleaned).strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


class LLMAdapter:
    def __init__(self) -> None:
        self.api_base = settings.deepinfra_api_base.rstrip("/")
        self.api_key = settings.deepinfra_api_key
        self.model = getattr(settings, "query_llm_model", "Qwen/Qwen3.6-35B-A3B")

    async def _post_with_retry(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Post request to LLM endpoint with retries and exponential backoff."""
        if not self.api_key or "REPLACE" in self.api_key:
            logger.warning("DeepInfra API key missing for LLMAdapter.")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if deepinfra_llm_breaker.should_skip():
            logger.warning("DeepInfra circuit breaker is OPEN. Skipping LLM API call.")
            return None

        client = get_client()
        for attempt in range(max_retries):
            if deepinfra_llm_breaker.should_skip():
                logger.warning("DeepInfra circuit breaker tripped during LLM retries. Aborting.")
                break
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
                resp.raise_for_status()
                deepinfra_llm_breaker.record_success()
                return resp.json()
            except httpx.HTTPStatusError as e:
                deepinfra_llm_breaker.record_failure()
                logger.warning(
                    f"LLMAdapter HTTP error (attempt {attempt + 1}/{max_retries}): "
                    f"{e.response.status_code} - {e.response.text}"
                )
                if e.response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1 and not deepinfra_llm_breaker.should_skip():
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                return None
            except Exception as e:
                deepinfra_llm_breaker.record_failure()
                logger.warning(f"LLMAdapter API call failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1 and not deepinfra_llm_breaker.should_skip():
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                return None
        return None

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        model: str | None = None,
        enable_thinking: bool = False,
        max_tokens: int = 300,
        timeout: float | None = None,
    ) -> str:
        """
        Generate completion for a given system and user prompt.
        Supports model selection (e.g. settings.offline_llm_model) and thinking control.
        """
        selected_model = model or getattr(settings, "query_llm_model", "Qwen/Qwen3.6-35B-A3B")

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Qwen models need enable_thinking control
        if "Qwen" in selected_model and not enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        # Gemma models don't use chat_template_kwargs
        # They use a different thinking control if needed

        url = f"{self.api_base}/openai/chat/completions"
        eff_timeout = (
            timeout
            if timeout is not None
            else (30.0 if ("31B" in selected_model or "gemma" in selected_model.lower()) else 15.0)
        )

        data = await self._post_with_retry(url, payload, timeout=eff_timeout)
        if not data or not data.get("choices"):
            return ""

        choice = data["choices"][0]
        message = choice.get("message", {})
        content = message.get("content") or message.get("reasoning_content") or ""
        return _clean_llm_response(content)

    async def complete_chat_full(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        model: Optional[str] = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Send chat completion request and return the entire parsed JSON response payload."""
        selected_model = model or self.model
        url = f"{self.api_base}/openai/chat/completions"
        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)
        return await self._post_with_retry(url, payload, timeout=timeout, max_retries=max_retries)

    async def complete_chat_raw(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        model: Optional[str] = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> Optional[str]:
        """Send chat completion request and return the raw message.content string without cleaning."""
        data = await self.complete_chat_full(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            model=model,
            max_retries=max_retries,
            **kwargs,
        )
        if not data or not data.get("choices"):
            return None
        choice = data["choices"][0]
        message = choice.get("message", {})
        return message.get("content") or message.get("reasoning_content") or ""

    async def complete_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        model: Optional[str] = None,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> Optional[str]:
        """Send a chat completion request to DeepInfra API and return cleaned response text."""
        raw_content = await self.complete_chat_raw(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            model=model,
            max_retries=max_retries,
            **kwargs,
        )
        if raw_content is None:
            return None
        return _clean_llm_response(raw_content)


llm_adapter = LLMAdapter()
