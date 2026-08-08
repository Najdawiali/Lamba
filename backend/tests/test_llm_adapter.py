from app.services.llm import _clean_llm_response


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
