from __future__ import annotations

import hashlib

from devpulse.config import get_settings
from devpulse.source_connectors.base import ConnectorContext, ConnectorError, FetchResult, RawItem, SourceConnector
from devpulse.source_connectors.mailbox import fetch_from_sender
from devpulse.source_connectors.newsletter_parser import parse_newsletter
from devpulse.source_connectors.registry import register


@register("email_newsletter")
class EmailNewsletterConnector(SourceConnector):
    description = (
        "Newsletter recebida por e-mail. 'sender' é o REMETENTE da newsletter; a conta lida é a "
        "configurada em NEWSLETTER_MAILBOX_* no .env."
    )
    config_fields = {"sender": "Endereço do remetente", "lookback_days": "padrão 3", "max_messages": "padrão 5"}

    def validate_config(self, url, config):
        return [] if "@" in config.get("sender", "") else ["Informe config.sender (remetente da newsletter)"]

    def fetch(self, ctx: ConnectorContext) -> FetchResult:
        settings = get_settings()
        sender = ctx.source_config.get("sender")
        if not sender:
            raise ConnectorError("config.sender ausente")
        provider = ctx.source_config.get("mailbox_provider") or settings.newsletter_mailbox_provider
        messages = fetch_from_sender(
            settings,
            ctx.http,
            provider,
            sender,
            int(ctx.source_config.get("lookback_days", 3)),
            int(ctx.source_config.get("max_messages", 5)),
        )
        result = FetchResult()
        for msg in messages:
            stories = parse_newsletter(msg.html, msg.text)
            if not stories:
                result.warnings.append(f"Edição '{msg.subject}' sem matérias identificáveis")
            for st in stories:
                ext = hashlib.sha256(f"{msg.message_id}|{st.url}".encode()).hexdigest()[:40]
                result.items.append(
                    RawItem(
                        external_id=ext,
                        url=st.url,
                        title=st.title or msg.subject,
                        summary=st.context,
                        content="",
                        content_access="summary_only",
                        # Provisório: data da edição da newsletter (marcada como inferida).
                        # A data original do artigo é buscada depois, na extração do link.
                        published_at=msg.received_at,
                        reference_type="newsletter_mention",
                        raw={
                            "newsletter_subject": msg.subject,
                            "newsletter_received_at": msg.received_at.isoformat() if msg.received_at else None,
                            "newsletter_message_id": msg.message_id,
                            "published_at_origin": "newsletter_date",
                        },
                    )
                )
        if not messages:
            result.warnings.append("Nenhuma edição nova encontrada para o remetente")
        return result
