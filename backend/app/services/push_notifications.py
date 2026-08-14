import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_push_notification(
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
):
    """Send a push notification via Expo. Fails gracefully if network is blocked."""
    if not push_token or not push_token.startswith("ExponentPushToken"):
        return

    payload = {
        "to": push_token,
        "title": title,
        "body": body,
        "sound": "default",
    }
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(EXPO_PUSH_URL, json=payload)
            if resp.status_code == 200:
                logger.info(f"[PUSH] Sent to {push_token[:20]}...")
            else:
                logger.warning(f"[PUSH] Failed: {resp.status_code}")
    except Exception as e:
        logger.warning(f"[PUSH] Network error (expected in dev): {e}")
