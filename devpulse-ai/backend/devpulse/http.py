from __future__ import annotations

import httpx

from devpulse.config import get_settings

MAX_BYTES = 5 * 1024 * 1024


def client(**kwargs) -> httpx.Client:
    s = get_settings()
    headers = {"User-Agent": s.http_user_agent, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
    headers.update(kwargs.pop("headers", {}))
    return httpx.Client(
        timeout=kwargs.pop("timeout", s.http_timeout_seconds),
        follow_redirects=True,
        headers=headers,
        **kwargs,
    )


def get_limited(c: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """GET que aborta respostas maiores que MAX_BYTES."""
    with c.stream("GET", url, **kwargs) as r:
        chunks, size = [], 0
        for chunk in r.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(f"Resposta maior que {MAX_BYTES} bytes")
            chunks.append(chunk)
        # iter_bytes() já descomprime: remove cabeçalhos de codificação para não decodificar de novo
        headers = [(k, v) for k, v in r.headers.multi_items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
        resp = httpx.Response(status_code=r.status_code, headers=headers, content=b"".join(chunks), request=r.request)
        return resp
