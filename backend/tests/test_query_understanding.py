from app.services.query_understanding import needs_llm


def test_needs_llm_simple_queries():
    assert needs_llm("حليب") is False
    assert needs_llm("شاي") is False
    assert needs_llm("7aleeb") is False
    assert needs_llm("زيت زيتون") is False


def test_needs_llm_complex_and_service_queries():
    assert needs_llm("اريد مدرسة لتعليم اللغة الفرنسية والإنجليزية") is True
    assert needs_llm("غسيل وتلميع سيارات متنقل أمام البيت") is True
    assert needs_llm("صيانة سباكة وكهرباء منازل") is True
    assert needs_llm("7laqa rajaliyah") is True
