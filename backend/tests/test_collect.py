import threading

import pytest

from reviewring import config, db
from reviewring.collect import Collector, CollectParams
from reviewring.fake_serp import FakeSerpApi
from reviewring.serp.gateway import Gateway
from reviewring.synth import World, ordinary_reviewers, plant_ring

from .fakes import FAKE_KEY

URL = "https://www.google.com/maps/place/Target/data=!4m2!3m1!1s0x5eed:0x1"


def gateway(server, **kw):
    return Gateway(secrets=config.Secrets(FAKE_KEY, None), client=server, sleep=lambda s: None, **kw)


def ring_world():
    w = World()
    ordinary_reviewers(w, 60)
    ring = plant_ring(w, 10, cities=["Jaipur", "Kochi", "Lucknow", "Kolkata"], m=5)
    return w, ring


def test_ring_business_runs_both_rounds():
    w, ring = ring_world()
    server = FakeSerpApi(w)
    events = []
    out = Collector(gateway(server), URL, on_event=events.append).run()
    assert out.status == "done" and not out.early_stop
    engines = [c["engine"] for c in server.calls]
    assert engines.count("google_maps_reviews") == 5
    assert engines.count("google_maps_contributor_reviews") == 29
    assert "google_maps" not in engines  # target coordinates came free from a history
    assert out.input.target.lat is not None
    assert {e.type for e in events} >= {"resolving", "fetching_reviews", "scoring", "expanding", "building_graph"}
    expanded = {e.contributor_id for e in out.input.expansions}
    assert len(expanded & set(ring)) >= 8


def test_clean_business_stops_early():
    w = World()
    ordinary_reviewers(w, 80)
    server = FakeSerpApi(w)
    out = Collector(gateway(server), URL).run()
    assert out.status == "done" and out.early_stop
    assert len(server.calls) == 19  # 5 pages + 8 + 2 + 4 voice picks


def test_pause_on_hourly_limit_then_resume_without_refetching(monkeypatch):
    monkeypatch.setitem(config.load_tunables()["budget"], "hourly_cap", 9)
    w, _ = ring_world()
    server = FakeSerpApi(w)
    c = Collector(gateway(server), URL)
    out = c.run()
    assert out.status == "paused" and out.resume_at is not None
    row = db.connect().execute("SELECT status FROM analyses WHERE id = ?", (c.analysis_id,)).fetchone()
    assert row["status"] == "paused"
    first_calls = [dict(x) for x in server.calls]
    monkeypatch.setitem(config.load_tunables()["budget"], "hourly_cap", 50)
    out2 = Collector(gateway(server), URL, analysis_id=c.analysis_id).run()
    assert out2.status == "done"
    keys = [tuple(sorted(x.items())) for x in server.calls]
    assert len(keys) == len(set(keys)), "a request was repeated"
    assert server.calls[: len(first_calls)] == first_calls


def test_cancel_keeps_cache():
    w, _ = ring_world()
    server = FakeSerpApi(w)
    cancel = threading.Event()

    def on_event(e):
        if e.type == "expanding":
            cancel.set()

    out = Collector(gateway(server), URL, on_event=on_event, cancel=cancel).run()
    assert out.status == "cancelled"
    n = len(server.calls)
    assert n >= 5
    out2 = Collector(gateway(server), URL).run()
    assert out2.status == "done"
    assert len(server.calls) - n <= 34 - 5


def test_private_profiles_are_marked():
    w = World()
    people = ordinary_reviewers(w, 9)
    server = FakeSerpApi(w, private=set(people[:3]))
    out = Collector(gateway(server), URL).run()
    statuses = {cid: c.status for cid, c in out.input.contributors.items()}
    assert sum(1 for s in statuses.values() if s == "private") == 3


def test_offline_mode_reports_missing():
    w, _ = ring_world()
    offline = Gateway(mode="offline", secrets=config.Secrets(None, None))
    c = Collector(offline, URL)
    out = c.run()
    assert out.status == "error" and "would cost 6 searches" in out.message
    # With the pages cached but no histories, offline mode still runs and reports what's missing.
    server = FakeSerpApi(w)
    gateway(server).fetch_pages("0x5eed:0x1", 88)
    c2 = Collector(offline, URL)
    out2 = c2.run()
    assert out2.status == "done"
    assert c2.state["missing"]["reviewer histories"] == 14
    assert all(x.status == "missing" for x in out2.input.contributors.values())


def test_stop_after_round1():
    w, _ = ring_world()
    server = FakeSerpApi(w)
    out = Collector(gateway(server), URL, CollectParams.from_config(stop_after_round1=True)).run()
    assert out.status == "done" and out.early_stop and len(server.calls) == 19


def test_name_search_needs_pick_then_continues():
    w = World()
    ordinary_reviewers(w, 12)
    server = FakeSerpApi(w)

    def two_results(params):
        return {"local_results": [{"title": "A", "data_id": "0x5eed:0x1"}, {"title": "B", "data_id": "0xbeef:0x2"}]}

    original = server._place
    server._place = lambda: two_results({})
    c = Collector(gateway(server), "Invented Dental, Pune")
    out = c.run()
    assert out.status == "needs_input" and len(out.candidates) == 2
    server._place = original
    out2 = Collector(
        gateway(server),
        "Invented Dental, Pune",
        CollectParams.from_config(pick="0x5eed:0x1"),
        analysis_id=c.analysis_id,
    ).run()
    assert out2.status == "done"
    assert [x["engine"] for x in server.calls].count("google_maps") == 1  # the search was cached


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setitem(config.load_tunables()["collection"], "history_concurrency", 3)


def test_live_view_events_carry_no_ids_or_names():
    w, ring = ring_world()
    server = FakeSerpApi(w)
    events = []
    Collector(gateway(server), URL, on_event=events.append).run()
    by_type = {}
    for e in events:
        by_type.setdefault(e.type, []).append(e)
    loaded = by_type["reviews_loaded"][0].data
    assert len(loaded["reviews"]) > 0 and all(len(row) == 3 for row in loaded["reviews"])
    picks = [p for e in by_type["picks"] for p in e.data["picks"]]
    histories = by_type["history"]
    assert len(picks) == 29 and len(histories) == 29
    assert {h.data["index"] for h in histories} == {p[0] for p in picks}
    assert any(e.data["pairs"] for e in by_type["links"])  # the planted ring links up
    text = repr([e.data for e in events])
    for cid in ring:
        assert cid not in text
