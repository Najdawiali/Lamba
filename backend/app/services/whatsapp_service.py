"""
WhatsApp verification codes through Meta's WhatsApp Cloud API.

Codes are sent with an AUTHENTICATION template (Meta supplies the wording, plus a
"Copy code" button). Only Jordanian mobile numbers are accepted: Lamba serves Jordan,
and it keeps every phone in one canonical form (+9627XXXXXXXX), so sign-up, sign-in and
password reset all match the same account however the user types the number.

Never logs the code itself, and logs only the last 4 digits of the phone number.

Command-line test (sends one random code):
    docker compose run --rm --no-deps api python -m app.services.whatsapp_service 0791234567
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_JO_MOBILE = re.compile(r"\+9627[789]\d{7}")


def normalize_jo_mobile(raw: str | None) -> str | None:
    """
    '0791234567', '791234567', '+962 79 123 4567', '00962791234567', '9620791234567'
    -> '+962791234567'. Returns None if it isn't a Jordanian mobile number.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("9620"):          # country code plus the local leading 0
        digits = "962" + digits[4:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "962" + digits[1:]
    elif len(digits) == 9:
        digits = "962" + digits
    candidate = "+" + digits
    return candidate if _JO_MOBILE.fullmatch(candidate) else None


def _payload(phone_e164: str, code: str, lang: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": phone_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.whatsapp_template_name,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                # The "Copy code" button of an authentication template takes the code too
                {"type": "button", "sub_type": "url", "index": "0",
                 "parameters": [{"type": "text", "text": code}]},
            ],
        },
    }


async def send_verification_code(phone_e164: str, code: str, lang: str | None = None) -> bool:
    """Send a verification code on WhatsApp. Returns True when Meta accepted the message. Never raises."""
    if not (settings.whatsapp_access_token and settings.whatsapp_phone_number_id):
        logger.error("WhatsApp verification is not configured (token or phone number id missing)")
        return False
    url = (f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
           f"{settings.whatsapp_phone_number_id}/messages")
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    tail = phone_e164[-4:]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=_payload(phone_e164, code, lang or settings.whatsapp_template_lang),
                                     headers=headers)
    except httpx.HTTPError as exc:
        logger.error("WhatsApp send to ...%s failed: %r", tail, exc)
        return False
    if resp.status_code == 200:
        logger.info("WhatsApp verification code sent to ...%s", tail)
        return True
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    logger.error("WhatsApp send to ...%s rejected (HTTP %s): code=%s %s",
                 tail, resp.status_code, err.get("code"), err.get("message") or resp.text[:200])
    return False


if __name__ == "__main__":
    import asyncio
    import secrets
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m app.services.whatsapp_service <jordanian mobile> [ar|en]")
    number = normalize_jo_mobile(sys.argv[1])
    if not number:
        raise SystemExit(f"'{sys.argv[1]}' is not a Jordanian mobile number")
    test_code = "".join(secrets.choice("0123456789") for _ in range(6))
    ok = asyncio.run(send_verification_code(number, test_code, sys.argv[2] if len(sys.argv) > 2 else None))
    print(f"{'SENT' if ok else 'FAILED'}: code {test_code} to ...{number[-4:]}")
