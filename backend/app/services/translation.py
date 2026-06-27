import urllib.parse
import urllib.request
import json
import logging

logger = logging.getLogger(__name__)

def translate_ar_to_en(text: str) -> str:
    """
    Translates Arabic text to English using Google's public translation API.
    If translation fails or input is not Arabic, returns the original text.
    """
    if not text:
        return text
        
    # Check if text contains Arabic characters
    # Arabic unicode range is roughly 0x0600 - 0x06FF
    has_arabic = any(0x0600 <= ord(char) <= 0x06FF for char in text)
    if not has_arabic:
        return text
        
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=ar&tl=en&dt=t&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            # The structure of the response is nested lists: [[[translated_text, original_text, ...], ...], ...]
            translated_sentences = []
            if data and data[0]:
                for part in data[0]:
                    if part and part[0]:
                        translated_sentences.append(part[0])
            if translated_sentences:
                translated_text = "".join(translated_sentences)
                logger.info(f"Translated: '{text}' -> '{translated_text}'")
                return translated_text
    except Exception as e:
        logger.error(f"Translation failed for '{text}': {e}")
        
    return text


def translate_en_to_ar(text: str) -> str:
    """
    Translates English text to Arabic using Google's public translation API.
    If translation fails or input contains Arabic, returns the original text.
    """
    if not text:
        return text
        
    # Check if text already contains Arabic characters
    has_arabic = any(0x0600 <= ord(char) <= 0x06FF for char in text)
    if has_arabic:
        return text
        
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ar&dt=t&q=" + urllib.parse.quote(text)
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            translated_sentences = []
            if data and data[0]:
                for part in data[0]:
                    if part and part[0]:
                        translated_sentences.append(part[0])
            if translated_sentences:
                translated_text = "".join(translated_sentences)
                logger.info(f"Translated (EN->AR): '{text}' -> '{translated_text}'")
                return translated_text
    except Exception as e:
        logger.error(f"Translation to Arabic failed for '{text}': {e}")
        
    return text
