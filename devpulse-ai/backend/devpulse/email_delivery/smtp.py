from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

from devpulse.config import Settings
from devpulse.delivery_common import SendOutcome, guard_real_send


class SmtpTransport:
    def __init__(self, settings: Settings):
        self.s = settings

    def configured(self) -> list[str]:
        missing = []
        for name in ("smtp_host", "email_from", "smtp_username"):
            if not getattr(self.s, name):
                missing.append(name.upper())
        if not self.s.smtp_password.get_secret_value():
            missing.append("SMTP_PASSWORD")
        return missing

    def send(self, *, to: str, subject: str, html: str, text: str, message_id: str) -> SendOutcome:
        guard_real_send()
        msg = EmailMessage()
        msg["From"] = self.s.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = message_id
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        try:
            if self.s.smtp_security == "ssl":
                server = smtplib.SMTP_SSL(self.s.smtp_host, self.s.smtp_port, timeout=30, context=ctx)
            else:
                server = smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30)
                server.starttls(context=ctx)
            with server:
                server.login(self.s.smtp_username, self.s.smtp_password.get_secret_value())
                refused = server.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            return SendOutcome(ok=False, auth_error=True, error="Falha de autenticação SMTP")
        except smtplib.SMTPRecipientsRefused:
            return SendOutcome(ok=False, error="Destinatário recusado pelo servidor SMTP")
        except smtplib.SMTPSenderRefused:
            return SendOutcome(ok=False, error="Remetente recusado pelo servidor SMTP")
        except (smtplib.SMTPException, OSError) as e:
            return SendOutcome(ok=False, retryable=True, error=f"Falha temporária SMTP: {type(e).__name__}")
        if refused:
            return SendOutcome(ok=False, error="Servidor recusou o destinatário")
        # SMTP só confirma aceitação pelo servidor, não entrega na caixa de entrada.
        return SendOutcome(ok=True, provider_message_id=message_id, provider_status="accepted_by_smtp_server")
