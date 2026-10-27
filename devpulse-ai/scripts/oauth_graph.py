#!/usr/bin/env python3
"""Obtém o GRAPH_REFRESH_TOKEN (Mail.Read delegado) via fluxo de código de dispositivo.

Uso:
    python3 scripts/oauth_graph.py --client-id XXX [--tenant consumers]

Pré-requisito: registre um aplicativo no Microsoft Entra ID, permita "fluxos de cliente público"
e adicione a permissão delegada Mail.Read.
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"


def post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--tenant", default="consumers")
    a = ap.parse_args()
    base = f"https://login.microsoftonline.com/{a.tenant}/oauth2/v2.0"
    dc = post(f"{base}/devicecode", {"client_id": a.client_id, "scope": SCOPE})
    print(dc.get("message", dc))
    while True:
        time.sleep(dc.get("interval", 5))
        tok = post(f"{base}/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                     "client_id": a.client_id, "device_code": dc["device_code"]})
        if "refresh_token" in tok:
            print("\nAdicione ao .env (não compartilhe):\nGRAPH_REFRESH_TOKEN=" + tok["refresh_token"])
            return
        if tok.get("error") not in ("authorization_pending", "slow_down"):
            raise SystemExit(f"Falhou: {tok.get('error_description', tok)}")


if __name__ == "__main__":
    main()
