"""Configurable SMS delivery.

Provider credentials are read from the environment/settings and are never
logged or rendered. When no provider is configured the send is recorded as
failed with a clear reason rather than silently succeeding.
"""
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


def sms_configured():
    """Return True if the SMS provider has minimum required credentials."""
    return bool(
        getattr(settings, "SMS_API_URL", "")
        and getattr(settings, "SMS_API_KEY", "")
    )


def send_sms(to_number, message):
    """Send an SMS message.

    Returns ``(ok, detail)`` where *ok* is ``True`` when the provider
    responded with a 2xx status, otherwise ``False`` and a short detail
    string.
    """
    if not to_number:
        return False, "No phone number"
    if not sms_configured():
        return False, "SMS provider not configured"
    payload = {"to": to_number, "message": message}
    sender = getattr(settings, "SMS_SENDER", "")
    if sender:
        payload["from"] = sender
    body = urlencode(payload).encode("utf-8")
    req = Request(getattr(settings, "SMS_API_URL"), data=body)
    req.add_header(
        "Authorization", f"Bearer {getattr(settings, 'SMS_API_KEY', '')}"
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                return True, ""
            return False, f"HTTP {resp.status}"
    except Exception as exc:
        logger.warning("SMS send failed: %s", exc)
        return False, str(exc)