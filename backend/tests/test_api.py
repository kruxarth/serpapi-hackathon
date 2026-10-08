import json
import time

import pytest
from fastapi.testclient import TestClient

from reviewring import config
from reviewring.api.app import create_app
from reviewring.fake_serp import FakeSerpApi
from reviewring.serp.gateway import Gateway
from reviewring.synth import World, ordinary_reviewers, plant_ring

from .fakes import FAKE_KEY

URL = "https://www.google.com/maps/place/T/data=!4m2!3m1!1s0x5eed:0x1!8m2!3d18.5204!4d73.8567"
H = {"X-ReviewRing": "1"}


@pytest.fixture
def server():
    w = World()
    ordinary_reviewers(w, 40)
    plant_ring(w, 8, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    return FakeSerpApi(w)


@pytest.fixture
def client(server, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", FAKE_KEY)

    def factory(mode):
        return Gateway(
            mode="live" if mode == "live" else "offline",
            secrets=config.Secrets(FAKE_KEY, None),
            client=server,
            sleep=lambda s: None,
        )

    app = create_app(factory)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def wait_done(client, analysis_id, timeout=20):
    events = []
    with client.stream("GET", f"/api/analyses/{analysis_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_post_needs_custom_header_and_json(client):
    r = client.post("/api/analyses", json={"input": URL})
    assert r.status_code == 403
    r = client.post("/api/analyses", content=json.dumps({"input": URL}), headers={**H, "Content-Type": "text/plain"})
    assert r.status_code == 415
    r = client.put("/api/settings", json={"mode": "offline"})
    assert r.status_code == 403


def test_cors_preflight_only_for_web_app(client):
    evil = client.options(
        "/api/analyses",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-reviewring,content-type",
        },
    )
    assert evil.status_code == 400
    ok = client.options(
        "/api/analyses",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-reviewring,content-type",
        },
    )
    assert ok.status_code == 200


def test_dns_rebinding_host_rejected(client):
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


def test_health_and_settings_never_expose_keys(client):
    body = client.get("/api/health").json()
    assert body["serpapi_key_set"] is True and body["mode"] == "live"
    s = client.get("/api/settings").text
    assert FAKE_KEY not in s
    assert client.put("/api/settings", json={"mode": "nonsense"}, headers=H).status_code == 422


def test_budget_strips_account(client, server):
    body = client.get("/api/budget").json()
    assert body["mode"] == "live" and body["month_remaining"] == 250
    assert "api_key" not in json.dumps(body) and "email" not in json.dumps(body)


def test_full_analysis_flow(client, server):
    dry = client.post("/api/analyses", json={"input": URL, "dry_run": True}, headers=H).json()
    assert dry["estimate"]["min"] == 16 and not server.calls  # 6 review pages + 10 histories
    started = client.post("/api/analyses", json={"input": URL}, headers=H)
    assert started.status_code == 200, started.text
    aid = started.json()["analysis_id"]
    events = wait_done(client, aid)
    types = [e["type"] for e in events]
    assert types[0] == "queued" and types[-1] == "done"
    assert "expanding" in types and "finding_groups" in types
    assert events[-1]["searches_used"] == 32  # 3 review pages (48 reviews) + 25 histories + 4 voice picks

    full = client.get(f"/api/analyses/{aid}").json()
    assert full["status"] == "done" and full["report"]["level"]["level"] == "High"
    assert full["report"]["place"]["title"] == "Target business"

    shown = client.get(f"/api/analyses/{aid}?presentation=1").json()
    text = json.dumps(shown)
    assert "Target business" not in text and "Invented Person" not in text
    assert shown["report"]["place"]["title"] == "Dental clinic A"
    assert all(abs(p["lat"] * 100 - round(p["lat"] * 100)) < 1e-9 for p in shown["report"]["places"].values())

    latest = client.get("/api/places/latest", params={"url": URL}).json()
    assert latest["found"] and latest["summary"]["level"] == "High" and len(latest["summary"]["evidence"]) <= 3
    listing = client.get("/api/analyses").json()
    assert listing[0]["id"] == aid and listing[0]["level"] == "High"
    assert client.get("/api/places/latest", params={"data_id": "0xabc:0x1"}).json()["found"] is False


def test_cancel_and_resume(client, server):
    aid = client.post("/api/analyses", json={"input": URL}, headers=H).json()["analysis_id"]
    client.post(f"/api/analyses/{aid}/cancel", json={}, headers=H)
    events = wait_done(client, aid)
    assert events[-1]["type"] in ("cancelled", "done")
    if events[-1]["type"] == "cancelled":
        r = client.post(f"/api/analyses/{aid}/resume", json={}, headers=H)
        assert r.status_code == 200
        assert wait_done(client, aid)[-1]["type"] == "done"


def test_demo_mode_refuses_new_analyses(client):
    client.put("/api/settings", json={"mode": "demo"}, headers=H)
    r = client.post("/api/analyses", json={"input": URL}, headers=H)
    assert r.status_code == 409


def test_bad_input_is_a_clear_422(client):
    r = client.post("/api/resolve", json={"input": "https://www.google.com/maps/dir/A/B"}, headers=H)
    assert r.status_code == 422 and "directions" in r.json()["detail"]


def test_error_messages_never_leak_keys(client, server, monkeypatch):
    from .fakes import http_error

    def boom(params):
        raise http_error(500)

    monkeypatch.setattr(server, "search", boom)
    aid = client.post("/api/analyses", json={"input": URL}, headers=H).json()["analysis_id"]
    events = wait_done(client, aid)
    assert FAKE_KEY not in json.dumps(events)
    assert FAKE_KEY not in client.get(f"/api/analyses/{aid}").text
    time.sleep(0)


def test_list_per_place_keeps_the_newest_analysis_of_each_place(client, server):
    first = client.post("/api/analyses", json={"input": URL}, headers=H).json()["analysis_id"]
    wait_done(client, first)
    second = client.post("/api/analyses", json={"input": URL}, headers=H).json()["analysis_id"]
    wait_done(client, second)
    every = client.get("/api/analyses").json()
    one = client.get("/api/analyses?per_place=1").json()
    assert {first, second} <= {a["id"] for a in every}
    assert [a["id"] for a in one if a["id"] in (first, second)] == [second]
    assert one[0]["kept_mean"] is not None and one[0]["examined"] > 0
