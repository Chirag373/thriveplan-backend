from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from .mail import MailDeliveryError, send_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="hello@example.com",
)
class MailTests(SimpleTestCase):
    def test_plain_text_and_html_use_central_configuration(self):
        self.assertEqual(
            send_email(
                to="user@example.com",
                subject="Welcome",
                text="Hello",
                html="<p>Hello</p>",
                reply_to="support@example.com",
            ),
            1,
        )
        message = mail.outbox[0]
        self.assertEqual(message.from_email, "hello@example.com")
        self.assertEqual(message.to, ["user@example.com"])
        self.assertEqual(message.reply_to, ["support@example.com"])
        self.assertEqual(message.body, "Hello")
        self.assertEqual(message.alternatives[0].mimetype, "text/html")

    def test_invalid_input_never_sends(self):
        with patch("apps.common.mail.EmailMultiAlternatives.send") as send:
            for values in [
                {"to": "bad", "subject": "Hi", "text": "Hello"},
                {"to": "u@example.com", "subject": "Hi\nBcc: other@example.com", "text": "Hello"},
                {"to": "u@example.com", "subject": "Hi", "text": ""},
            ]:
                with self.assertRaises((ValidationError, ValueError)):
                    send_email(**values)
            send.assert_not_called()

    def test_delivery_errors_are_sanitized(self):
        with (
            patch(
                "apps.common.mail.EmailMultiAlternatives.send",
                side_effect=SMTPException("private provider data"),
            ),
            self.assertRaisesMessage(MailDeliveryError, "Email service is unavailable."),
        ):
            send_email(to="u@example.com", subject="Hi", text="Hello")

    def test_zero_messages_is_failure(self):
        with (
            patch("apps.common.mail.EmailMultiAlternatives.send", return_value=0),
            self.assertRaises(MailDeliveryError),
        ):
            send_email(to="u@example.com", subject="Hi", text="Hello")
