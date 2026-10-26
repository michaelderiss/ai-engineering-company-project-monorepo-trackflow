from __future__ import annotations

import json
import logging
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmailDeliveryError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _log_reset_link_fallback(recipient: str, reset_url: str) -> None:
    """Print the reset link so local/dev flows still work without SMTP/Resend."""
    print(
        "\n[TrackFlow password reset fallback]\n"
        f"  recipient : {recipient}\n"
        f"  link      : {reset_url}\n",
        file=sys.stderr,
    )


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    sender = os.getenv("RESEND_FROM_EMAIL")
    expiry_minutes = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30"))
    if not api_key or not sender:
        logger.warning("Resend email configuration missing; using console fallback for %s", recipient)
        _log_reset_link_fallback(recipient, reset_url)
        return

    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": "Reset your TrackFlow password",
            "text": (
                "We received a request to reset your TrackFlow password. "
                f"Use this link within the next {expiry_minutes} minutes: {reset_url}\n\n"
                "If you did not request this, you can ignore this email."
            ),
        }
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise EmailDeliveryError("Resend rejected the email request.")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise EmailDeliveryError("Could not deliver the password reset email.") from exc