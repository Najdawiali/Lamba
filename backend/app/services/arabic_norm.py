"""
Arabic text normalization & Arabizi transliteration.

Single source of truth used by:
  - app.services.embedding (before encoding queries & items)
  - app.api.search_v1     (before building tsquery / lexical predicates)
  - scripts.backfill_search_terms (when populating search_terms)

Normalization breakdown:
  1. Strip tashkeel (diacritics)
  2. Unify alef forms (إ أ آ ا → ا)
  3. Alef maksura → ya (ى → ي)
  4. Unify hamza carriers (ؤ ئ → ء)
  5. Strip tatweel / kashida (ـ)
  6. Collapse whitespace

Arabizi → Arabic:
  Common digit-to-letter conversions used in informal chat (3→ع, 7→ح, etc.)
  so queries like "shay" / "3asal" can match catalog items written in Arabic.

References:
  - CAMeL Tools (pip install camel-tools) — more thorough, but heavier
  - PyArabic — alternative
  - The subset below is hand-rolled to stay dependency-free and deterministic.
"""

from __future__ import annotations

import re
import unicodedata

# ── Compiled regexes (compiled once for performance) ────────────────
_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670]")    # Tashkeel + dagger alef
_ALEF_RE = re.compile(r"[إأآا]")
_ALEF_MAKSURA_RE = re.compile(r"ى")
_HAMZA_CARRIERS_RE = re.compile(r"[ؤئ]")
_TATWEEL_RE = re.compile(r"\u0640+")                     # Kashida
_TAA_MARBOUTA_RE = re.compile(r"ة")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_arabic(text: str | None, normalize_taa_marbouta: bool = False) -> str:
    """
    Normalize Arabic script text for canonical matching.

    Args:
        text: Raw input, possibly None or mixed Arabic/Latin.
        normalize_taa_marbouta: If True, convert Taa Marbouta (ة) to Ha (ه).

    Returns:
        Lowercased, normalized string with diacritics stripped, alef forms
        unified, alef-maksura → ya, hamza-carriers → bare hamza, tatweel
        removed, and whitespace collapsed to single spaces.
    """
    if not text:
        return ""

    # NFKC normalization handles a lot of presentation forms and ligatures
    text = unicodedata.normalize("NFKC", text)

    text = _DIACRITICS_RE.sub("", text)
    text = _ALEF_RE.sub("ا", text)
    text = _ALEF_MAKSURA_RE.sub("ي", text)
    text = _HAMZA_CARRIERS_RE.sub("ء", text)
    text = _TATWEEL_RE.sub("", text)
    if normalize_taa_marbouta:
        text = _TAA_MARBOUTA_RE.sub("ه", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    return text.lower()


# ── Casual Dialect Synonyms (Zero-Latency Fast Fallback) ─────────────
_CASUAL_DIALECT_DICT: dict[str, str] = {
    "رز": "ارز",
    "أرز": "ارز",
    "ارز": "ارز",
    "جاج": "دجاج",
    "توم": "ثوم",
    "بتنجان": "باذنجان",
    "بتنجانه": "باذنجان",
    "بندورة": "بندورة",
    "بندوره": "بندورة",
    "طماطم": "بندورة",
    "زهرة": "زهرة",
    "زهره": "زهرة",
    "قرنبيط": "زهرة",
    "بطاطا": "بطاطا",
    "بطاطس": "بطاطا",
    "خبز": "خبز",
    "عيش": "خبز",
    "كوسا": "كوسا",
    "كوسى": "كوسا",
    "حليب": "حليب",
    "لبن": "لبن",
    "جبنة": "جبنة",
    "جبنه": "جبنة",
    "بيض": "بيض",
    "زيت": "زيت",
    "شاي": "شاي",
    "قهوة": "قهوة",
    "قهوه": "قهوة",
    "عصير": "عصير",
    "سمنة": "سمنة",
    "سمنه": "سمنة",
    "زبدة": "زبدة",
    "زبده": "زبدة",
    "سكر": "سكر",
    "ملح": "ملح",
    "عسل": "عسل",
}


# ── Arabizi (Franco-Arabic) → Arabic ────────────────────────────────
_ARABIZI_DICT: dict[str, str] = {
    # Dairy & Eggs / الألبان والبيض
    "7aleeb": "حليب",
    "7alib": "حليب",
    "haleeb": "حليب",
    "halib": "حليب",
    "laban": "لبن",
    "labneh": "لبنة",
    "labna": "لبنة",
    "jebneh": "جبنة",
    "jebna": "جبنة",
    "jibnah": "جبنة",
    "jibna": "جبنة",
    "zabadi": "زبادي",
    "qashtah": "قشطة",
    "qashta": "قشطة",
    "kashta": "قشطة",
    "samneh": "سمنة",
    "samna": "سمنة",
    "zebdeh": "زبدة",
    "zibda": "زبدة",
    "baid": "بيض",
    "baidh": "بيض",
    "bayd": "بيض",
    "baydh": "بيض",

    # Beverages / المشروبات
    "3aseer": "عصير",
    "aseer": "عصير",
    "asir": "عصير",
    "shai": "شاي",
    "shay": "شاي",
    "chai": "شاي",
    "qahwah": "قهوة",
    "qahwa": "قهوة",
    "kahwa": "قهوة",
    "kahwah": "قهوة",
    "water": "ماء",
    "mai": "ماء",
    "miah": "مياه",
    "may": "ماء",
    "cola": "كولا",
    "pepsi": "بيبسي",
    "nescafe": "نسكافيه",
    "espresso": "اسبرسو",
    "karkadeh": "كركديه",
    "yansoon": "يانسون",
    "yansun": "يانسون",
    "meramiyyeh": "مرامية",
    "maramieye": "مرامية",
    "na3na3": "نعناع",
    "nana": "نعناع",

    # Cooking Essentials & Oil / مستلزمات الطبخ والزيوت
    "zayt": "زيت",
    "zeit": "زيت",
    "zait": "زيت",
    "zaytoon": "زيتون",
    "zeitoun": "زيتون",
    "zaytun": "زيتون",
    "mil7": "ملح",
    "mel7": "ملح",
    "sukkar": "سكر",
    "sokar": "سكر",
    "sokkar": "سكر",
    "tahini": "طحينة",
    "taheena": "طحينة",
    "taheenah": "طحينة",
    "3asal": "عسل",
    "asal": "عسل",
    "korkom": "كركم",
    "kurkum": "كركم",
    "kammoun": "كمون",
    "kamoun": "كمون",
    "kuzbara": "كزبرة",
    "kozbara": "كزبرة",
    "somaq": "سماق",
    "sumac": "سماق",
    "summaq": "سماق",
    "qerfeh": "قرفة",
    "qirfa": "قرفة",
    "za3fran": "زعفران",
    "zafran": "زعفران",
    "za3tar": "زعتر",
    "zatar": "زعتر",

    # Produce & Vegetables / الخضار والفواكه
    "khodra": "خضار",
    "khodhar": "خضار",
    "fawakeh": "فواكه",
    "fawaki": "فواكه",
    "basal": "بصل",
    "basaleh": "بصلة",
    "thoum": "ثوم",
    "tom": "ثوم",
    "toom": "ثوم",
    "batata": "بطاطا",
    "bandora": "بندورة",
    "bandorah": "بندورة",
    "tomat": "طماطم",
    "khiyar": "خيار",
    "khyar": "خيار",
    "tuffa7": "تفاح",
    "tofa7": "تفاح",
    "tofah": "تفاح",
    "bortoqal": "برتقال",
    "burtuqal": "برتقال",
    "mouz": "موز",
    "mozz": "موز",
    "3enab": "عنب",
    "enab": "عنب",
    "rumman": "رمان",
    "roman": "رمان",
    "mishmish": "مشمش",
    "khoo5": "خوخ",
    "khoch": "خوخ",
    "battee5": "بطيخ",
    "batikh": "بطيخ",
    "batih": "بطيخ",
    "shamam": "شمام",
    "tin": "تين",
    "teen": "تين",
    "tamr": "تمر",
    "tamer": "تمر",
    "kosa": "كوسا",
    "koosa": "كوسا",
    "betenjan": "باذنجان",
    "batenjan": "باذنجان",
    "zahra": "زهرة",
    "zahrah": "زهرة",
    "malfoof": "ملفوف",
    "sabane5": "سبانخ",
    "sbane5": "سبانخ",
    "bamyeh": "بامية",
    "bamia": "بامية",
    "jazar": "جزر",
    "felfel": "فلفل",
    "filfil": "فلفل",

    # Grains & Legumes / الحبوب والبقوليات
    "ruz": "ارز",
    "roz": "ارز",
    "aruzz": "ارز",
    "3ads": "عدس",
    "ads": "عدس",
    "freekeh": "فريكة",
    "frikeh": "فريكة",
    "burghul": "برغل",
    "borghol": "برغل",
    "ful": "فول",
    "foul": "فول",
    "7ommos": "حمص",
    "hommos": "حمص",
    "hummus": "حمص",

    # Meat & Poultry / اللحوم والدواجن
    "dajaj": "دجاج",
    "jaj": "دجاج",
    "la7m": "لحم",
    "la7me": "لحم",
    "la7meh": "لحم",
    "samak": "سمك",
    "kebab": "كباب",
    "kabab": "كباب",
    "kofta": "كفتة",
    "kufta": "كفتة",
    "shawarma": "شاورما",
    "mansaf": "منسف",
    "jameed": "جميد",

    # Bakery & Sweets / المخبوزات والحلويات
    "khobz": "خبز",
    "khubz": "خبز",
    "ka3k": "كعك",
    "kaak": "كعك",
    "manaqeesh": "مناقيش",
    "manakish": "مناقيش",
    "fatayer": "فطاير",
    "sfeeha": "صفيحة",
    "kunafa": "كنافة",
    "knafeh": "كنافة",
    "baklava": "بقلاوة",
    "baqlawa": "بقلاوة",
    "ma3moul": "معمول",
    "maamoul": "معمول",
    "harissa": "هريسة",
    "hareesa": "هريسة",
    "basbousa": "بسبوسة",
    "qatayef": "قطايف",
    "shokolata": "شوكولاتة",
    "chocolate": "شوكولاتة",
    "biskot": "بسكويت",
    "biscuit": "بسكويت",
    "chips": "شيبس",
    "kakao": "كاكاو",

    # Household & Care / المنظفات والعناية
    "sabon": "صابون",
    "saboon": "صابون",
    "khardal": "خردل",
    "ketchup": "كاتشاب",
    "mayonnaise": "مايونيز",
    "creme": "كريمة",
    "cream": "كريمة",

    # Services / الخدمات (Jordanian Dialect Terms)
    "7laqa": "حلاقة",
    "hlaqa": "حلاقة",
    "hlaq": "حلاقة",
    "halaka": "حلاقة",
    "ghaseel": "غسيل",
    "ghasil": "غسيل",
    "gasil": "غسيل",
    "sayara": "سيارة",
    "sayarah": "سيارة",
    "sayyara": "سيارة",
    "tanzif": "تنظيف",
    "tanzeef": "تنظيف",
    "tanzeefah": "تنظيف",
    "khiyata": "خياطة",
    "kheyata": "خياطة",
    "khyata": "خياطة",
    "dars": "دروس",
    "daroos": "دروس",
    "madraseh": "مدرسة",
    "madrasa": "مدرسة",
    "ta3leem": "تعليم",
    "taleem": "تعليم",
    "tasleeh": "تصليح",
    "taslih": "تصليح",
    "sbakeh": "سباكة",
    "sbakah": "سباكة",
    "kahraba": "كهرباء",
    "kahraba3": "كهرباء",
    "mokayyef": "مكيف",
    "takyeef": "تكييف",
    "tajmeel": "تجميل",
    "masaj": "مساج",
    "massage": "مساج",
    "3elaj": "علاج",
    "ilaj": "علاج",
    "ta2jeer": "تأجير",
    "tajeer": "تأجير",
    "tawseel": "توصيل",
    "tawsil": "توصيل",
    "qiyada": "قيادة",
    "qeyadah": "قيادة",
    "siyana": "صيانة",
    "seyana": "صيانة",
    "tastheer": "تصليح",
}

def is_arabizi_word(word: str) -> bool:
    w = word.lower().strip()
    if not w:
        return False
    if w in _ARABIZI_DICT:
        return True
    
    # Must contain both a letter and an Arabizi digit (2-9)
    has_letter = any(c.isalpha() for c in w)
    has_digit = any(c in "23456789" for c in w)
    return has_letter and has_digit

def _contains_arabic(text: str) -> bool:
    for char in text:
        if '\u0600' <= char <= '\u06FF':
            return True
    return False

def _transliterate_arabizi_word(word: str) -> str:
    word_cleaned = word.lower().strip()
    if not word_cleaned:
        return ""
    if word_cleaned in _ARABIZI_DICT:
        return _ARABIZI_DICT[word_cleaned]

    # Rule-based replacement
    res = word_cleaned
    res = res.replace("3'", "غ")
    res = res.replace("7'", "خ")
    res = res.replace("5'", "خ")
    res = res.replace("6'", "ط")
    res = res.replace("9'", "ض")
    res = res.replace("2'", "ء")
    res = res.replace("kh", "خ")
    res = res.replace("gh", "غ")
    res = res.replace("sh", "ش")
    res = res.replace("ch", "ش")
    res = res.replace("th", "ث")

    res = res.replace("ee", "ي")
    res = res.replace("oo", "و")
    res = res.replace("aa", "ا")
    res = res.replace("ou", "و")
    res = res.replace("ei", "ي")
    res = res.replace("ay", "ي")

    res = res.replace("3", "ع")
    res = res.replace("7", "ح")
    res = res.replace("5", "خ")
    res = res.replace("6", "ط")
    res = res.replace("9", "ص")
    res = res.replace("2", "ء")
    res = res.replace("8", "ق")
    res = res.replace("4", "ش")

    mapping = {
        "b": "ب", "p": "ب",
        "t": "ت",
        "j": "ج", "g": "ج",
        "d": "د",
        "r": "ر",
        "z": "ز",
        "s": "س", "c": "ك",
        "f": "ف", "v": "ف",
        "k": "ك",
        "l": "ل",
        "m": "م",
        "n": "ن",
        "h": "ه",
        "w": "و",
    }

    final_chars = []
    i = 0
    while i < len(res):
        char = res[i]
        if '\u0600' <= char <= '\u06FF':
            final_chars.append(char)
        elif char in mapping:
            final_chars.append(mapping[char])
        elif char == 'a':
            if i == 0:
                final_chars.append("ا")
            elif i == len(res) - 1:
                final_chars.append("ة")
            else:
                final_chars.append("ا")
        elif char in ('i', 'y', 'e'):
            final_chars.append("ي")
        elif char in ('o', 'u'):
            final_chars.append("و")
        i += 1

    out = "".join(final_chars)
    collapsed = []
    for c in out:
        if not collapsed or c != collapsed[-1]:
            collapsed.append(c)
        elif c in ("ي", "و", "ا", "ل", "ب", "ت", "ر", "س", "م", "ن"):
            if c in ("ي", "و", "ا"):
                pass
            else:
                collapsed.append(c)
    return "".join(collapsed)

def arabizi_to_arabic(text: str | None) -> str:
    """
    Convert Arabizi / Franco-Arabic words in the input text to Arabic script.
    Preserves English words and brands, and maps Arabic slang numbers (3, 7, etc.)
    and phonetics.
    """
    if not text:
        return ""
    
    words = text.split()
    processed_words = []
    for word in words:
        match = re.match(r"^([^\w\d]*)(.*?)([^\w\d]*)$", word)
        if match:
            pfx, core, sfx = match.groups()
            if not core:
                processed_words.append(word)
                continue
            
            if _contains_arabic(core):
                processed_words.append(word)
            elif is_arabizi_word(core):
                arabic_word = _transliterate_arabizi_word(core)
                processed_words.append(f"{pfx}{arabic_word}{sfx}")
            else:
                processed_words.append(word)
        else:
            processed_words.append(word)
            
    return " ".join(processed_words)


def apply_casual_dialect(text: str | None) -> str:
    """Map common casual/Levantine words (رز -> ارز, جاج -> دجاج, etc.) to canonical terms."""
    if not text:
        return ""
    words = text.split()
    converted = []
    for w in words:
        norm_w = normalize_arabic(w)
        if norm_w in _CASUAL_DIALECT_DICT:
            converted.append(_CASUAL_DIALECT_DICT[norm_w])
        elif w in _CASUAL_DIALECT_DICT:
            converted.append(_CASUAL_DIALECT_DICT[w])
        else:
            converted.append(w)
    return " ".join(converted)


def normalize_query(text: str | None) -> str:
    """
    Full query-time normalization pipeline:
      Arabizi → Arabic, Casual Dialect → Formal, then Arabic normalize, then lowercase collapse.

    Use this on every user query before embedding AND before building the
    tsvector/tsquery lexical predicate.
    """
    if not text:
        return ""
    arabicized = arabizi_to_arabic(text)
    dialect_mapped = apply_casual_dialect(arabicized)
    return normalize_arabic(dialect_mapped)