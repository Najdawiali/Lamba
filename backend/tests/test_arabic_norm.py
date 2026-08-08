from app.services.arabic_norm import normalize_arabic, normalize_query


def test_normalize_arabic_tashkeel():
    raw = "شَايٌ أَخْضَرُ"
    normalized = normalize_arabic(raw)
    assert normalized == "شاي اخضر"


def test_normalize_arabic_tatweel():
    raw = "شـاي أخـضـر"
    normalized = normalize_arabic(raw)
    assert normalized == "شاي اخضر"


def test_normalize_arabic_alef_variants():
    raw = "أحمد إبراهيم آدم"
    normalized = normalize_arabic(raw)
    assert normalized == "احمد ابراهيم ادم"


def test_normalize_arabic_taa_marbouta_option():
    raw = "قهوة طحينة"
    without_taa = normalize_arabic(raw, normalize_taa_marbouta=False)
    with_taa = normalize_arabic(raw, normalize_taa_marbouta=True)
    assert without_taa == "قهوة طحينة"
    assert with_taa == "قهوه طحينه"


def test_normalize_query_empty():
    assert normalize_query("") == ""
    assert normalize_query(None) == ""
