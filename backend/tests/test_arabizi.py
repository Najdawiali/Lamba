from app.services.arabic_norm import arabizi_to_arabic, is_arabizi_word


def test_arabizi_dictionary_lookups():
    assert arabizi_to_arabic("7aleeb") == "حليب"
    assert arabizi_to_arabic("7laqa") == "حلاقة"
    assert arabizi_to_arabic("ghaseel sayara") == "غسيل سيارة"
    assert arabizi_to_arabic("madraseh") == "مدرسة"
    assert arabizi_to_arabic("zayt zaytoon") == "زيت زيتون"
    assert arabizi_to_arabic("3asal") == "عسل"
    assert arabizi_to_arabic("knafeh") == "كنافة"
    assert arabizi_to_arabic("bandora") == "بندورة"


def test_is_arabizi_word():
    assert is_arabizi_word("7aleeb") is True
    assert is_arabizi_word("3asal") is True
    assert is_arabizi_word("حليب") is False
    assert is_arabizi_word("milk") is False
