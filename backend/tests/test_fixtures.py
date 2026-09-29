import json
import os
import subprocess
import sys

from fastapi.testclient import TestClient

from reviewring import config, leakcheck
from reviewring.api.app import create_app
from reviewring.collect import Collector
from reviewring.demo import get_demo, list_demo
from reviewring.engine.analyze import analyze
from reviewring.exporter import FIXTURES_DIR, LeakFound, build_fixture, export_analysis, input_from_dict, write_fixture
from reviewring.fake_serp import FakeSerpApi
from reviewring.serp.gateway import Gateway
from reviewring.synth import World, ordinary_reviewers, plant_ring

from .fakes import FAKE_KEY

URL = "https://www.google.com/maps/place/T/data=!4m2!3m1!1s0x5eed:0x1"
H = {"X-ReviewRing": "1"}


def collected():
    w = World()
    ordinary_reviewers(w, 50)
    plant_ring(w, 10, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    gw = Gateway(secrets=config.Secrets(FAKE_KEY, None), client=FakeSerpApi(w), sleep=lambda s: None)
    c = Collector(gw, URL)
    out = c.run()
    return c.analysis_id, out.input


def test_exported_fixture_is_pseudonymized_and_passes_leak_check(tmp_path):
    analysis_id, inp = collected()
    from reviewring.report import store_report

    store_report(analysis_id, inp, "live")
    path = export_analysis(analysis_id, slug="t-case")  # writes into the repo's fixtures/ by default
    try:
        text = path.read_text()
        fixture = json.loads(text)
        assert "Invented Person" not in text and "Target business" not in text and "Invented Road" not in text
        assert fixture["input"]["target"]["title"] == "Dental clinic A"
        assert not leakcheck.check_paths([path])
        kept = [r["text"] for r in fixture["input"]["target_reviews"] if r["text"]]
        assert kept and all(len(t) <= 60 for t in kept)  # only ring template texts survive, truncated
    finally:
        path.unlink()


def test_rerun_from_fixture_matches_the_stored_report(tmp_path):
    _, inp = collected()
    fixture = build_fixture(inp, "x", title="x", salt_value="s")
    rerun = analyze(input_from_dict(fixture["input"]))
    assert json.loads(json.dumps(rerun, default=str)) == fixture["report"]
    assert fixture["report"]["level"]["level"] == analyze(inp)["level"]["level"]


def test_stock_phrases_same_when_rerun_from_fixture():
    w = World()
    ordinary_reviewers(w, 20)
    stock = "Good service and friendly staff, would recommend this place to others"
    for _ in range(12):  # unrelated accounts sharing a stock phrase
        cid = w.reviewer()
        w.personal_history(cid, "Pune", 8)
        w.review_target(cid, rating=4, text=stock)
    inp = w.build()
    before = analyze(inp)["signals"]["T4"]["stock_phrase_clusters"]
    fixture = build_fixture(inp, "x", title="x", salt_value="s")
    after = analyze(input_from_dict(fixture["input"]))["signals"]["T4"]["stock_phrase_clusters"]
    assert len(before) == len(after) == 1


def test_leak_blocks_export(tmp_path):
    _, inp = collected()
    fixture = build_fixture(inp, "leaky", title="Call 9876543210", salt_value="s")
    try:
        write_fixture(fixture, originals={}, directory=tmp_path)
    except LeakFound as exc:
        assert any(f.kind == "phone number" for f in exc.findings)
    else:
        raise AssertionError("expected the leak check to block the export")
    assert not (tmp_path / "leaky.json").exists()


def test_committed_fixtures_pass_leak_check_and_rerun():
    paths = sorted(FIXTURES_DIR.glob("*.json"))
    assert paths, "demo mode needs committed fixtures"
    assert not leakcheck.check_paths(paths, originals={})
    for p in paths:
        f = json.loads(p.read_text())
        rerun = json.loads(json.dumps(analyze(input_from_dict(f["input"])), default=str))
        assert rerun == f["report"], p.name


def test_demo_mode_on_fresh_checkout_without_keys(monkeypatch):
    items = list_demo()
    assert {i["level"] for i in items} >= {"High", "Low", "Elevated"}
    assert get_demo(items[0]["id"])["report"]["pseudonymized"] is True
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/health").json()["mode"] == "demo"  # no key: demo by default
        listing = c.get("/api/analyses").json()
        assert len(listing) == len(items)
        report = c.get(f"/api/analyses/{listing[0]['id']}").json()["report"]
        assert report["analysis"]["mode"] == "demo"
        assert c.get("/api/places/latest", params={"data_id": "0x1:0x2"}).json()["reason"] == "demo"


def test_leakcheck_cli_on_fixtures_dir():
    env = dict(os.environ)
    result = subprocess.run([sys.executable, "-m", "reviewring.leakcheck", str(FIXTURES_DIR)], capture_output=True,
                            text=True, env=env, check=False)
    assert result.returncode == 0, result.stderr
