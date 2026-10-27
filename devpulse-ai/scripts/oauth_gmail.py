#!/usr/bin/env python3
"""Obtém o GMAIL_REFRESH_TOKEN (escopo somente leitura) para a caixa que recebe as newsletters.

Uso (no seu computador, fora do container):
    python3 scripts/oauth_gmail.py --client-id XXX --client-secret YYY

Pré-requisito: no Google Cloud Console, ative a Gmail API e crie um "ID do cliente OAuth"
do tipo "App para computador". O script abre um servidor em 127.0.0.1 só para receber o código.
"""
import argparse
import http.server
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    redirect = f"http://127.0.0.1:{a.port}/"
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": a.client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
    })
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            result.update(q)
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Autorização recebida. Pode fechar esta aba.".encode())

        def log_message(self, *args):
            pass

    print("Abra no navegador e autorize com a conta que RECEBE as newsletters:\n", url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", a.port), Handler) as srv:
        srv.handle_request()
    if result.get("state") != state or "code" not in result:
        raise SystemExit(f"Autorização falhou: {result.get('error', 'resposta inválida')}")
    data = urllib.parse.urlencode({
        "code": result["code"], "client_id": a.client_id, "client_secret": a.client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data) as r:
        token = json.load(r)
    print("\nAdicione ao .env (não compartilhe):\nGMAIL_REFRESH_TOKEN=" + token["refresh_token"])


if __name__ == "__main__":
    main()
