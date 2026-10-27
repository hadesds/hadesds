"""Leitura autorizada de caixas de e-mail, somente leitura e filtrada por remetente.

Provedores suportados:
* ``imap``  — IMAP sobre TLS, ``BODY.PEEK`` (não marca como lida).
* ``gmail`` — Gmail API, escopo ``gmail.readonly``, OAuth com refresh token.
* ``graph`` — Microsoft Graph, permissão delegada ``Mail.Read``, OAuth com refresh token.

Somente mensagens do remetente configurado são baixadas; nenhuma outra mensagem é lida.
"""
from __future__ import annotations

import base64
import email
import imaplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime

import httpx

from devpulse.config import Settings
from devpulse.source_connectors.base import ConnectorError
from devpulse.timeutil import utcnow


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    received_at: datetime | None
    html: str
    text: str
    sender: str


def _decode(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def parse_rfc822(raw: bytes) -> EmailMessage:
    msg: Message = email.message_from_bytes(raw)
    html, text = "", ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if part.get_content_type() == "text/html" and not html:
            html = decoded
        elif part.get_content_type() == "text/plain" and not text:
            text = decoded
    try:
        received = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    except (TypeError, ValueError):
        received = None
    return EmailMessage(
        message_id=(msg.get("Message-ID") or "").strip(),
        subject=_decode(msg.get("Subject")),
        received_at=received,
        html=html,
        text=text,
        sender=_decode(msg.get("From")),
    )


def _imap(settings: Settings, sender: str, since: datetime, limit: int) -> list[EmailMessage]:
    if not (settings.imap_host and settings.imap_username and settings.imap_password.get_secret_value()):
        raise ConnectorError("IMAP não configurado (IMAP_HOST/IMAP_USERNAME/IMAP_PASSWORD)")
    try:
        conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=30)
        conn.login(settings.imap_username, settings.imap_password.get_secret_value())
    except imaplib.IMAP4.error as e:
        raise ConnectorError("Falha de autenticação IMAP") from e
    try:
        conn.select(settings.imap_folder, readonly=True)
        crit = f'(FROM "{sender}" SINCE {since.strftime("%d-%b-%Y")})'
        typ, data = conn.search(None, crit)
        if typ != "OK":
            raise ConnectorError("Busca IMAP falhou")
        ids = data[0].split()[-limit:]
        out = []
        for mid in ids:
            typ, parts = conn.fetch(mid, "(BODY.PEEK[])")
            if typ == "OK" and parts and isinstance(parts[0], tuple):
                out.append(parse_rfc822(parts[0][1]))
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _oauth_token(http: httpx.Client, url: str, data: dict) -> str:
    resp = http.post(url, data=data)
    if resp.status_code >= 400:
        raise ConnectorError(f"Falha ao renovar token OAuth (HTTP {resp.status_code}); refaça a autorização")
    return resp.json()["access_token"]


def _gmail(settings: Settings, http: httpx.Client, sender: str, since: datetime, limit: int) -> list[EmailMessage]:
    if not (settings.gmail_client_id and settings.gmail_refresh_token.get_secret_value()):
        raise ConnectorError("Gmail API não configurada (GMAIL_CLIENT_ID/GMAIL_REFRESH_TOKEN)")
    token = _oauth_token(
        http,
        "https://oauth2.googleapis.com/token",
        {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret.get_secret_value(),
            "refresh_token": settings.gmail_refresh_token.get_secret_value(),
            "grant_type": "refresh_token",
        },
    )
    h = {"Authorization": f"Bearer {token}"}
    q = f"from:{sender} after:{int(since.timestamp())}"
    resp = http.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"q": q, "maxResults": limit}, headers=h
    )
    if resp.status_code >= 400:
        raise ConnectorError(f"Gmail API HTTP {resp.status_code}")
    out = []
    for m in resp.json().get("messages", []):
        r = http.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}", params={"format": "raw"}, headers=h
        )
        if r.status_code < 400:
            out.append(parse_rfc822(base64.urlsafe_b64decode(r.json()["raw"])))
    return out


def _graph(settings: Settings, http: httpx.Client, sender: str, since: datetime, limit: int) -> list[EmailMessage]:
    if not (settings.graph_client_id and settings.graph_refresh_token.get_secret_value()):
        raise ConnectorError("Microsoft Graph não configurado (GRAPH_CLIENT_ID/GRAPH_REFRESH_TOKEN)")
    data = {
        "client_id": settings.graph_client_id,
        "refresh_token": settings.graph_refresh_token.get_secret_value(),
        "grant_type": "refresh_token",
        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
    }
    if settings.graph_client_secret.get_secret_value():
        data["client_secret"] = settings.graph_client_secret.get_secret_value()
    token = _oauth_token(
        http, f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token", data
    )
    flt = f"from/emailAddress/address eq '{sender}' and receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    resp = http.get(
        "https://graph.microsoft.com/v1.0/me/messages",
        params={"$filter": flt, "$top": limit, "$select": "id,subject,receivedDateTime,body,internetMessageId,from"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code >= 400:
        raise ConnectorError(f"Microsoft Graph HTTP {resp.status_code}")
    out = []
    for m in resp.json().get("value", []):
        body = m.get("body") or {}
        is_html = body.get("contentType") == "html"
        out.append(
            EmailMessage(
                message_id=m.get("internetMessageId") or m["id"],
                subject=m.get("subject") or "",
                received_at=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")),
                html=body.get("content", "") if is_html else "",
                text="" if is_html else body.get("content", ""),
                sender=sender,
            )
        )
    return out


def fetch_from_sender(
    settings: Settings, http: httpx.Client, provider: str, sender: str, lookback_days: int, limit: int = 10
) -> list[EmailMessage]:
    since = utcnow() - timedelta(days=lookback_days)
    if provider == "imap":
        return _imap(settings, sender, since, limit)
    if provider == "gmail":
        return _gmail(settings, http, sender, since, limit)
    if provider == "graph":
        return _graph(settings, http, sender, since, limit)
    raise ConnectorError("Nenhuma caixa de e-mail configurada (NEWSLETTER_MAILBOX_PROVIDER=none)")
