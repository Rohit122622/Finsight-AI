"""
FinSentry AI — Centralized backend email service (SMTP).

SECURITY INVARIANTS:
  - SMTP credentials are read ONLY from backend environment settings.
  - Credentials/passwords are NEVER logged or included in exceptions surfaced to callers.
  - The PDF password is NEVER placed in the email body or attachment.
  - Recipient is supplied by the backend (authenticated user record), never the frontend.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Optional

from core.config import get_settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """Raised when SMTP settings are incomplete."""


class EmailService:
    """Minimal, dependency-light SMTP sender with TLS/STARTTLS."""

    def is_configured(self) -> bool:
        return get_settings().is_smtp_configured()

    def send_email_with_attachment(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        attachment_bytes: bytes,
        attachment_filename: str,
        attachment_mime: tuple[str, str] = ("application", "pdf"),
    ) -> str:
        """
        Send an email with a single binary attachment. Returns a safe Message-ID on success.

        Raises EmailNotConfiguredError if SMTP is not configured, or the underlying
        SMTP exception (sanitized) on delivery failure. Never logs credentials.
        """
        settings = get_settings()
        if not settings.is_smtp_configured():
            raise EmailNotConfiguredError(
                "SMTP is not configured (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD required)."
            )
        if not to_email:
            raise ValueError("A recipient email address is required.")

        from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
        from_name = settings.SMTP_FROM_NAME or "FinSentry AI"

        # A generated Message-ID lets us correlate submission in logs (safe, non-secret).
        message_id = make_msgid(domain="finsentry.ai")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg["Message-ID"] = message_id
        msg.set_content(body_text)

        maintype, subtype = attachment_mime
        msg.add_attachment(
            attachment_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=attachment_filename,
        )

        host, port = settings.SMTP_HOST, settings.SMTP_PORT
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    refused = server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    server.ehlo()
                    if settings.SMTP_USE_TLS:
                        server.starttls()
                        server.ehlo()
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    refused = server.send_message(msg)
        except smtplib.SMTPException as exc:
            # Log only the exception type — never credentials or the message body.
            logger.error("SMTP delivery failed to recipient (type=%s)", type(exc).__name__)
            raise

        # send_message returns a dict of refused recipients (empty means accepted for all).
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)

        return message_id


email_service = EmailService()


# ---------------------------------------------------------------------------
# Email content builders (no password ever included)
# ---------------------------------------------------------------------------

def build_comparison_email() -> tuple[str, str]:
    """Return (subject, body) for the comparison report email."""
    subject = "FinSentry AI — Your Comparison Report"
    body = (
        "Hello,\n\n"
        "Your requested FinSentry AI comparison report is attached as a "
        "password-protected PDF.\n\n"
        "The attachment is encrypted and cannot be opened without the PDF password. "
        "To open the PDF, retrieve your report password from your authenticated "
        "FinSentry report page (Reveal Password). The attached file is the same "
        "encrypted document available via the Download PDF button in the app.\n\n"
        "— FinSentry AI"
    )
    return subject, body


def build_report_email() -> tuple[str, str]:
    """Return (subject, body) for the financial report email."""
    subject = "FinSentry AI — Your Financial Report"
    body = (
        "Hello,\n\n"
        "Your requested FinSentry AI financial report is attached as a "
        "password-protected PDF.\n\n"
        "The attachment is encrypted and cannot be opened without the PDF password. "
        "To open the PDF, retrieve your report password from your authenticated "
        "FinSentry report page (Reveal Password). The attached file is the same "
        "encrypted document available via the Download PDF button in the app.\n\n"
        "— FinSentry AI"
    )
    return subject, body
