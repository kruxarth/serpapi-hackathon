"""CLI checkpoint flow with a fake SerpApi client: probe, then reuse at collection."""

import pytest

from reviewring import cli, config
from reviewring.serp import catalog
from reviewring.serp.gateway import Gateway

from .fakes import DATA_ID, FAKE_KEY, FakeClient, history, reviews_page

URL = f"https://www.google.com/maps/place/X/data=!4m2!3m1!1s{DATA_ID}!8m2!3d18.52!4d73.85"


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient(
        account={
            "total_searches_left": 240,
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 0,
            "plan_renewal_date": "2026-10-05",
        }
    )
    secrets = config.Secrets(FAKE_KEY, None)

    def factory(*args, **kwargs):
        kwargs.setdefault("secrets", secrets)
        kwargs.setdefault("client", client)
        kwargs.setdefault("sleep", lambda s: None)
        return Gateway(*args, **kwargs)

    monkeypatch.setattr(cli, "Gateway", factory)
    return client


def test_probe_requires_yes(fake, capsys):
    assert cli.main(["probe", URL]) == 2
    assert fake.calls == []
    assert "at most 2 search" in capsys.readouterr().out


def test_probe_then_reuse(fake, capsys):
    page1 = reviews_page(0, 8, "t1")
    fake.push(page1, lambda p: history(p["contributor_id"]))
    assert cli.main(["probe", URL, "--yes"]) == 0
    out = capsys.readouterr().out
    assert '"plan_renewal_date": "2026-10-05"' in out
    assert FAKE_KEY not in out
    assert len(fake.calls) == 2
    picked = min((r for r in page1["reviews"] if r["rating"] == 5), key=lambda r: r["user"]["reviews"])
    assert fake.calls[1]["contributor_id"] == picked["user"]["contributor_id"]

    # Re-running costs nothing, and the collection step reuses page 1 (identical request keys).
    assert cli.main(["probe", URL, "--yes"]) == 0
    assert "at most 0 search" in capsys.readouterr().out
    assert len(fake.calls) == 2
    gw = Gateway(mode="offline")
    pages = gw.fetch_pages(DATA_ID, 88)
    assert pages.responses[0].request.key == catalog.reviews_page(DATA_ID).key
    assert pages.responses[0].from_cache
    assert gw.lookup_cache(catalog.contributor_history(fake.calls[1]["contributor_id"])) is not None


def test_probe_dry_run_spends_nothing(fake, capsys):
    assert cli.main(["probe", URL, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Would request" in out and fake.calls == []


def test_dry_run_command(fake, capsys):
    assert cli.main(["dry-run", URL]) == 0
    out = capsys.readouterr().out
    assert "Estimate: 16-34 searches" in out
    assert fake.calls == []


def test_ledger_and_purge(capsys, isolated):
    assert cli.main(["ledger"]) == 0
    assert "empty" in capsys.readouterr().out
    assert cli.main(["purge-data"]) == 2
    assert cli.main(["purge-data", "--yes"]) == 0
    assert not (isolated / "data").exists()


def test_budget_offline(capsys):
    assert cli.main(["budget", "--offline"]) == 0
    assert "250 searches left this month" in capsys.readouterr().out


def test_budget_live_strips_email(fake, capsys):
    assert cli.main(["budget"]) == 0
    out = capsys.readouterr().out
    assert "example.invalid" not in out and FAKE_KEY not in out
    assert "total_searches_left: 240" in out


def test_checkpoint_flow_probe_then_collect_reuses_responses(monkeypatch, capsys):
    from reviewring.fake_serp import FakeSerpApi
    from reviewring.synth import World, ordinary_reviewers, plant_ring

    w = World()
    ordinary_reviewers(w, 50)
    plant_ring(w, 8, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    server = FakeSerpApi(w)
    secrets = config.Secrets(FAKE_KEY, None)

    def factory(*args, **kwargs):
        kwargs.setdefault("secrets", secrets)
        kwargs.setdefault("client", server)
        kwargs.setdefault("sleep", lambda s: None)
        return Gateway(*args, **kwargs)

    monkeypatch.setattr(cli, "Gateway", factory)
    url = "https://www.google.com/maps/place/T/data=!4m2!3m1!1s0x5eed:0x1"
    assert cli.main(["probe", url, "--yes"]) == 0
    probe_calls = [dict(c) for c in server.calls]
    assert len(probe_calls) == 2

    assert cli.main(["collect", url]) == 2  # shows the estimate, spends nothing without --yes
    assert len(server.calls) == 2
    out = capsys.readouterr().out
    assert "Estimate:" in out and "1 of 6 pages cached" in out

    assert cli.main(["collect", url, "--yes"]) == 0
    keys = [tuple(sorted(c.items())) for c in server.calls]
    assert len(keys) == len(set(keys)), "the probe's responses were fetched again"
    out = capsys.readouterr().out
    analysis_id = next(line.split(": ")[1] for line in out.splitlines() if line.startswith("Analysis id"))
    assert cli.main(["resume", analysis_id, "--yes"]) == 1  # finished: needs --force
    n = len(server.calls)
    assert cli.main(["resume", analysis_id, "--yes", "--force"]) == 0
    assert len(server.calls) == n  # everything is cached
    assert cli.main(["cancel", analysis_id]) == 1  # nothing running
