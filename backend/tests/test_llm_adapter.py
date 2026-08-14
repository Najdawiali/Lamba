import asyncio
from unittest.mock import patch, AsyncMock
from app.services.llm import _clean_llm_response, LLMAdapter


def test_clean_llm_response_thinking_tags():
    raw = "<think>\nThinking about intent...\nCategory is product.\n</think>\n{\"intent\": \"product\", \"category_name\": \"Beverages\"}"
    cleaned = _clean_llm_response(raw)
    assert cleaned == '{"intent": "product", "category_name": "Beverages"}'


def test_clean_llm_response_markdown_fences():
    raw = "```json\n{\"intent\": \"service\", \"category_name\": \"Education & Tutoring\"}\n```"
    cleaned = _clean_llm_response(raw)
    assert cleaned == '{"intent": "service", "category_name": "Education & Tutoring"}'


def test_clean_llm_response_empty():
    assert _clean_llm_response("") == ""
    assert _clean_llm_response(None) == ""


async def test_llm_adapter_generate_qwen_thinking_disabled():
    """Verify Qwen models include chat_template_kwargs with enable_thinking=False."""
    with patch("app.services.llm.settings") as ms:
        ms.deepinfra_api_base = "https://api.deepinfra.com/v1"
        ms.deepinfra_api_key = "test-key"
        ms.query_llm_model = "Qwen/Qwen3.6-35B-A3B"
        ms.offline_llm_model = "google/gemma-4-31B-it"

        adapter = LLMAdapter()
        mock_response = {
            "choices": [{"message": {"content": '{"intent": "product"}'}}]
        }

        with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.generate(
                system_prompt="System",
                user_prompt="User",
                model="Qwen/Qwen3.6-35B-A3B",
                enable_thinking=False,
            )

            assert result == '{"intent": "product"}'
            mock_post.assert_called_once()
            call_payload = mock_post.call_args[0][1]
            assert call_payload["model"] == "Qwen/Qwen3.6-35B-A3B"
            assert call_payload.get("chat_template_kwargs") == {"enable_thinking": False}


async def test_llm_adapter_generate_gemma_offline_model():
    """Verify Gemma offline model does not have chat_template_kwargs and uses longer timeout."""
    with patch("app.services.llm.settings") as ms:
        ms.deepinfra_api_base = "https://api.deepinfra.com/v1"
        ms.deepinfra_api_key = "test-key"
        ms.query_llm_model = "Qwen/Qwen3.6-35B-A3B"
        ms.offline_llm_model = "google/gemma-4-31B-it"

        adapter = LLMAdapter()
        mock_response = {
            "choices": [{"message": {"content": "```json\n{\"type\": \"أخضر\"}\n```"}}]
        }

        with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.generate(
                system_prompt="Return JSON",
                user_prompt="شاي أخضر",
                model="google/gemma-4-31B-it",
                enable_thinking=False,
            )

            assert result == '{"type": "أخضر"}'
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_payload = mock_post.call_args[0][1]
            call_timeout = mock_post.call_args[1].get("timeout")
            assert call_payload["model"] == "google/gemma-4-31B-it"
            assert "chat_template_kwargs" not in call_payload
            assert call_timeout == 30.0
