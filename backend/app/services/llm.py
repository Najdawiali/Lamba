"""
LLMAdapter — Client for DeepInfra OpenAI chat completions API.
Used for category classification, query expansion, and query understanding.
"""

import logging
import json
import re
import httpx
from typing import Optional, Dict, Any, List
from app.config import settings
from app.services.http_pool import get_client

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

    async def _get_client(self, timeout: float = 15.0) -> httpx.AsyncClient:
        return get_client()

    async def complete_chat_full(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Send chat completion request and return the entire parsed JSON response payload."""
        if not self.api_key or "REPLACE" in self.api_key:
            logger.warning("DeepInfra API key missing for LLMAdapter.")
            return None

        url = f"{self.api_base}/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        try:
            client = await self._get_client(timeout=timeout)
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"LLMAdapter API call failed: {e}")
            return None

    async def complete_chat_raw(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        **kwargs: Any,
    ) -> Optional[str]:
        """Send chat completion request and return the raw message.content string without cleaning."""
        data = await self.complete_chat_full(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )
        if not data or not data.get("choices"):
            return None
        choice = data["choices"][0]
        message = choice.get("message", {})
        # Support content or reasoning_content
        return message.get("content") or message.get("reasoning_content") or ""

    async def complete_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 300,
        timeout: float = 15.0,
        **kwargs: Any,
    ) -> Optional[str]:
        """Send a chat completion request to DeepInfra API and return cleaned response text."""
        raw_content = await self.complete_chat_raw(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )
        if raw_content is None:
            return None
        return _clean_llm_response(raw_content)


llm_adapter = LLMAdapter()
