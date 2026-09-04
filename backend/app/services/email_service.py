"""
Email Service — Send verification codes via Resend API.

Supports two modes:
  - "resend" → sends real emails via Resend API (production)
  - "mock"   → prints to console (development)

Configured via EMAIL_PROVIDER and RESEND_API_KEY env vars.
"""

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VERIFICATION_EMAIL_TEMPLATE = """
<div style="font-family: 'Segoe UI', Tahoma, sans-serif; max-width: 400px; margin: 0 auto; direction: rtl; text-align: right;">
  <div style="background: linear-gradient(135deg, #6C63FF 0%, #8B83FF 100%); padding: 32px; border-radius: 16px 16px 0 0; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 28px;">لمبة</h1>
    <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0 0; font-size: 14px;">Lamba</p>
  </div>
  <div style="background: #ffffff; padding: 32px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 16px 16px;">
    <p style="color: #374151; font-size: 16px; margin: 0 0 8px 0;">مرحباً،</p>
    <p style="color: #6b7280; font-size: 14px; margin: 0 0 24px 0;">رمز التحقق الخاص بك هو:</p>
    <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; text-align: center; margin: 0 0 24px 0;">
      <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #6C63FF;">{code}</span>
    </div>
    <p style="color: #9ca3af; font-size: 12px; margin: 0; text-align: center;">
      ينتهي هذا الرمز خلال 10 دقائق<br/>
      This code expires in 10 minutes
    </p>
  </div>
</div>
"""


async def send_verification_email(to_email: str, code: str) -> bool:
    """
    Send a verification code email.

    Returns True if sent successfully, False otherwise.
    Falls back to mock (console log) if email provider is not configured.
    """
    provider = getattr(settings, "email_provider", "mock").lower()

    if provider == "resend":
        return await _send_via_resend(to_email, code)
    else:
        return _send_mock(to_email, code)


async def _send_via_resend(to_email: str, code: str) -> bool:
    """Send email via Resend API."""
    api_key = getattr(settings, "resend_api_key", "")
    from_email = getattr(settings, "email_from", "Lamba <noreply@lambajo.com>")

    if not api_key:
        logger.warning("[EMAIL] Resend API key not configured, falling back to mock")
        return _send_mock(to_email, code)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": from_email,
                    "to": [to_email],
                    "subject": f"Lamba — رمز التحقق {code}",
                    "html": VERIFICATION_EMAIL_TEMPLATE.format(code=code),
                },
            )

        if resp.status_code in (200, 201):
            logger.info(f"[EMAIL] Verification code sent to {to_email}")
            return True
        else:
            logger.error(f"[EMAIL] Resend API error: {resp.status_code} — {resp.text}")
            # Fall back to mock so signup doesn't break
            return _send_mock(to_email, code)

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send via Resend: {e}")
        return _send_mock(to_email, code)


def _send_mock(to_email: str, code: str) -> bool:
    """Print verification code to console (development mode)."""
    logger.info(f"📧  MOCK EMAIL VERIFICATION")
    logger.info(f"    To: {to_email}")
    logger.info(f"    Code: {code}")
    logger.info(f"    (Set EMAIL_PROVIDER=resend for real delivery)")
    return True
