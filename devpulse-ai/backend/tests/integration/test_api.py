import pytest
from fastapi.testclient import TestClient

from devpulse.scheduler.pipeline import run_edition

from .conftest import add_story, make_source
from .test_edition import new_run, seed_news

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db):
    from devpulse.main import create_app

    return TestClient(create_app())


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "senha-de-teste-123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth(client):
    assert client.get("/api/sources").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "errada"}).status_code == 401


def test_create_and_list_source(client, auth):
    body = {"slug": "go-blog", "name": "The Go Blog", "connector_type": "rss", "url": "https://go.dev/blog/feed.atom",
            "category": "desenvolvimento", "priority_tier": 1}
    r = client.post("/api/sources", json=body, headers=auth)
    assert r.status_code == 201, r.text
    assert client.post("/api/sources", json=body, headers=auth).status_code == 409
    bad = client.post("/api/sources", json={**body, "slug": "x2", "connector_type": "github_releases", "config": {}}, headers=auth)
    assert bad.status_code == 422
    listed = client.get("/api/sources", headers=auth).json()
    assert [s["slug"] for s in listed] == ["go-blog"]
    sid = listed[0]["id"]
    assert client.post(f"/api/sources/{sid}/toggle", headers=auth).json()["enabled"] is False


def test_dashboard_news_scripts_deliveries(client, auth, db):
    seed_news(db)
    run_edition(db, new_run(db), collect=False, transports={}, verify_links=False)
    dash = client.get("/api/dashboard", headers=auth).json()
    assert dash["collected_today"] == 6 and dash["scripts_today"] >= 1 and dash["next_runs"]
    news = client.get("/api/news", params={"q": "Kubernetes"}, headers=auth).json()
    assert news["total"] == 1 and news["items"][0]["published_at"]
    detail = client.get(f"/api/news/{news['items'][0]['id']}", headers=auth).json()
    assert detail["references"] and "related" in detail
    scripts = client.get("/api/scripts", headers=auth).json()
    sid = scripts[0]["id"]
    full = client.get(f"/api/scripts/{sid}", headers=auth).json()
    assert full["scenes"] and full["fact_checks"] and full["media_assets"]
    md = client.get(f"/api/scripts/{sid}/markdown", headers=auth)
    assert md.headers["content-type"].startswith("text/markdown") and "## 3. Roteiro cronometrado" in md.text
    assert client.post(f"/api/scripts/{sid}/status", json={"status": "recorded"}, headers=auth).json()["status"] == "recorded"
    pkg = full["package"]
    pkg["scenes"][0]["speech"] = "Fala editada manualmente."
    edited = client.put(f"/api/scripts/{sid}", json={"package": pkg}, headers=auth).json()
    assert edited["edited_manually"] and edited["scenes"][0]["speech"] == "Fala editada manualmente."
    assert "Fala editada manualmente." in edited["markdown"]
    deliveries = client.get("/api/deliveries", headers=auth).json()
    assert {d["channel"] for d in deliveries} == {"email", "whatsapp"}


def test_settings_roundtrip_and_validation(client, auth, enable_channels):
    s = client.get("/api/settings", headers=auth).json()
    assert s["editable"]["daily_script_limit"] == 3 and "integrations" in s
    # segredos nunca saem pela API (só a indicação de configurado/ausente)
    assert enable_channels.smtp_password.get_secret_value() not in str(s)
    assert enable_channels.whatsapp_access_token.get_secret_value() not in str(s)
    r = client.put("/api/settings", json={"edition_main_time": "07:30", "whatsapp_recipient": "+5598988887777"}, headers=auth)
    assert r.status_code == 200 and r.json()["editable"]["edition_main_time"] == "07:30"
    assert client.put("/api/settings", json={"daily_script_limit": 9}, headers=auth).status_code == 422


def test_manual_run_request(client, auth):
    r = client.post("/api/runs/edition", headers=auth)
    assert r.status_code == 202 and r.json()["status"] == "pending"
