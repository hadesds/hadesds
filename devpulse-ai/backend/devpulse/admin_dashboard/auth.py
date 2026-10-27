"""Autenticação local do painel: usuário/senha do .env e token assinado com validade."""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from devpulse.config import get_settings

TOKEN_TTL = 12 * 3600
_bearer = HTTPBearer(auto_error=False)
_failures: dict[str, deque] = defaultdict(deque)


def _serializer() -> URLSafeTimedSerializer:
    key = get_settings().secret_key.get_secret_value()
    if len(key) < 32:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SECRET_KEY ausente ou curta (mínimo 32 caracteres)")
    return URLSafeTimedSerializer(key, salt="devpulse-admin")


def check_rate_limit(ip: str) -> None:
    q = _failures[ip]
    now = time.monotonic()
    while q and now - q[0] > 300:
        q.popleft()
    if len(q) >= 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas; aguarde alguns minutos")


def login(request: Request, username: str, password: str) -> str:
    s = get_settings()
    ip = request.client.host if request.client else "?"
    check_rate_limit(ip)
    expected = s.admin_password.get_secret_value()
    if len(expected) < 10:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ADMIN_PASSWORD ausente ou curta (mínimo 10 caracteres)")
    ok = hmac.compare_digest(username.encode(), s.admin_username.encode()) & hmac.compare_digest(
        password.encode(), expected.encode()
    )
    if not ok:
        _failures[ip].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha inválidos")
    return _serializer().dumps({"u": username})


def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária")
    try:
        data = _serializer().loads(creds.credentials, max_age=TOKEN_TTL)
    except SignatureExpired:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada") from None
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido") from None
    return data["u"]
