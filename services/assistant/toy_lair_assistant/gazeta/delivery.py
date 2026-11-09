"""Email delivery of the PDF over Gmail SMTP with an app password."""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

HOST = "smtp.gmail.com"
PORT = 465


def build_message(sender: str, to: str, subject: str, body: str, pdf: bytes, filename: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if body:
        msg.set_content(body)
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return msg


def send_pdf(
    user: str,
    password: str,
    to: str,
    subject: str,
    body: str,
    pdf: bytes,
    filename: str,
    connect: Callable[..., Any] = smtplib.SMTP_SSL,
) -> None:
    msg = build_message(user, to or user, subject, body, pdf, filename)
    with connect(HOST, PORT, timeout=60) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
