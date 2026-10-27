"""Shared email delivery for all ThrivePlan apps."""

from smtplib import SMTPException

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email

FIREBASE_RESET_URL = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
# Keep the public response identical for missing or suppressed accounts.
FIREBASE_PRIVATE_ERRORS = frozenset(
    {
        "EMAIL_NOT_FOUND",
        "USER_DISABLED",
        "TOO_MANY_ATTEMPTS_TRY_LATER",
    }
)


class MailDeliveryError(Exception):
    def __init__(self, message: str = "Email service is unavailable.") -> None:
        super().__init__(message)


def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> int:
    """Send one email through Django's configured backend; return 1 on acceptance."""
    validate_email(to)
    if reply_to is not None:
        validate_email(reply_to)
    if not subject.strip() or not text.strip():
        raise ValueError("Email subject and text are required.")
    if "\r" in subject or "\n" in subject:
        raise ValueError("Email subject must be a single line.")

    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[reply_to] if reply_to else None,
    )
    if html is not None:
        message.attach_alternative(html, "text/html")

    try:
        sent = message.send(fail_silently=False)
    except (SMTPException, OSError, ImproperlyConfigured):
        raise MailDeliveryError() from None
    if sent != 1:
        raise MailDeliveryError("Email was not accepted by the backend.")
    return sent


def send_password_reset_email(*, email: str) -> None:
    """Ask Firebase to send its hosted reset link without revealing account existence."""
    if not settings.FIREBASE_WEB_API_KEY:
        raise MailDeliveryError()

    try:
        response = requests.post(
            FIREBASE_RESET_URL,
            params={"key": settings.FIREBASE_WEB_API_KEY},
            json={"requestType": "PASSWORD_RESET", "email": email},
            timeout=(3.05, 10),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise MailDeliveryError() from None

    try:
        if not _reset_request_accepted(response):
            raise MailDeliveryError()
    finally:
        response.close()


def _reset_request_accepted(response: requests.Response) -> bool:
    if response.status_code == 200:
        return True
    if response.status_code != 400:
        return False

    try:
        error = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return False
    return isinstance(error, str) and error in FIREBASE_PRIVATE_ERRORS
