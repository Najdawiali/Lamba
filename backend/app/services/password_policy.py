"""
Password policy for new passwords (signup, reset) — never applied at sign-in.

Follows NIST SP 800-63B: a minimum length, a blocklist of common passwords, obvious
patterns and personal information are rejected; there are deliberately NO composition
rules ("one uppercase, one symbol"), which produce predictable passwords like Password1!.

Product rule: passwords use English-keyboard characters only (printable ASCII: letters,
digits, symbols, spaces). Arabic letters have look-alike variants (ي/ی, ك/ک) that
different keyboards produce, which would lock users out when they change phones.

Messages are bilingual (Arabic, then English) because the API doesn't know the UI language.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

MIN_LENGTH = 8
MAX_LENGTH = 72  # bcrypt's input limit (72 bytes = 72 characters, since passwords are ASCII)
_ENGLISH_ONLY = re.compile(r"[\x20-\x7E]+")  # printable ASCII: English letters, digits, symbols, space

# Weak for Lamba users specifically (also checked with trailing digits/symbols removed)
LOCAL_WEAK = {
    "lamba", "lambajo", "jordan", "amman", "irbid", "zarqa", "salt", "assalt", "alsalt", "aqaba",
    "karak", "madaba", "jerash", "ajloun", "mafraq", "tafila", "maan", "welcome", "merchant",
    "customer", "admin", "password", "qwerty", "iloveyou", "letmein",
}
_SEQUENCES = (
    "012345678901234567890", "098765432109876543210",
    "abcdefghijklmnopqrstuvwxyz", "zyxwvutsrqponmlkjihgfedcba",
    "qwertyuiop", "poiuytrewq", "asdfghjkl", "lkjhgfdsa", "zxcvbnm", "mnbvcxz",
    "1qaz2wsx3edc4rfv5tgb", "qazwsxedcrfvtgb",
)
_REPEATED_CHUNK = re.compile(r"(.{1,4})\1+")
_JO_MOBILE = re.compile(r"(\+|00)?(962)?0?7[789]\d{7}")
_TRAILING_JUNK = re.compile(r"[\W\d_]+$")

MSG = {
    "too_short": "كلمة المرور قصيرة: يجب ألا تقل عن 8 أحرف.\nPassword is too short: use at least 8 characters.",
    "not_english": "يجب أن تتكوّن كلمة المرور من أحرف إنجليزية وأرقام ورموز فقط.\n"
                   "Password can only contain English letters, numbers and symbols.",
    "too_long": "كلمة المرور طويلة جداً، الرجاء اختيار كلمة أقصر.\nPassword is too long. Please choose a shorter one.",
    "common": "كلمة المرور هذه شائعة وسهلة التخمين. اختر كلمة أخرى، مثلاً عبارة من عدة كلمات.\n"
              "This password is too common and easy to guess. Choose another, for example a phrase of several words.",
    "pattern": "كلمة المرور تتبع نمطاً سهل التخمين (مثل 12345678 أو رقم هاتف).\n"
               "This password follows an easy-to-guess pattern (like 12345678 or a phone number).",
    "personal": "يجب ألا تحتوي كلمة المرور على بريدك الإلكتروني أو اسمك.\nYour password must not contain your email or name.",
}


@lru_cache(maxsize=1)
def _common() -> frozenset[str]:
    path = Path(__file__).resolve().parent.parent / "data" / "common_passwords.txt"
    with open(path, encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if line.strip() and not line.startswith("#"))


def password_problem(password: str, *, email: str | None = None, name: str | None = None,
                     phone: str | None = None) -> tuple[str, str] | None:
    """Return (code, bilingual message) if the password is not acceptable, else None."""
    if len(password) < MIN_LENGTH:
        return "too_short", MSG["too_short"]
    if not _ENGLISH_ONLY.fullmatch(password):
        return "not_english", MSG["not_english"]
    if len(password) > MAX_LENGTH:
        return "too_long", MSG["too_long"]

    norm = password.strip().lower()
    compact = re.sub(r"[\s\-]", "", norm)
    core = _TRAILING_JUNK.sub("", norm)

    if norm in _common() or norm in LOCAL_WEAK or (core and (core in _common() or core in LOCAL_WEAK)):
        return "common", MSG["common"]
    if (len(set(compact)) <= 2 or _REPEATED_CHUNK.fullmatch(compact)
            or any(compact in seq for seq in _SEQUENCES) or _JO_MOBILE.fullmatch(compact)):
        return "pattern", MSG["pattern"]

    personal = set()
    if email:
        local = email.split("@", 1)[0].lower()
        personal |= {local} | set(re.split(r"[._+\-]", local))
    if name:
        personal |= set(name.lower().split())
    if phone:
        digits = re.sub(r"\D", "", phone)
        personal |= {digits[-9:]} if len(digits) >= 9 else set()
    if any(len(p) >= 4 and p in norm for p in personal):
        return "personal", MSG["personal"]
    return None
