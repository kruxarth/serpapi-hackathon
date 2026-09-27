import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from reviewring import config, db
from reviewring.serp import catalog
from reviewring.serp.errors import BadRequest, BudgetRefused, InvalidApiKey, NoApiKey, NotCached, Paused
from reviewring.serp.gateway import Gateway, strip_account

from .fakes import DATA_ID, FAKE_KEY, FakeClient, history, http_error, reviews_page, timeout_error


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock()


def make(client=None, clock=None, **kw):
    secrets = config.Secrets(serpapi_key=FAKE_KEY, deepseek_key=None)
    return Gateway(secrets=secrets, client=client or FakeClient(), sleep=lambda s: None, clock=clock or Clock(), **kw)


def hist_req(cid="111"):
    return catalog.contributor_history(cid)


def ledger_rows():
    return db.connect().execute("SELECT * FROM ledger ORDER BY id").fetchall()


def test_cache_hit_makes_no_call():
    client = FakeClient().push(history("111"))
    gw = make(client)
    first = gw.fetch(hist_req())
    second = gw.fetch(hist_req())
    assert not first.from_cache and second.from_cache
    assert len(client.calls) == 1 and len(ledger_rows()) == 1


def test_api_key_never_stored():
    client = FakeClient().push(dict(history("111"), echo=f"weird {FAKE_KEY} echo"))
    gw = make(client)
    gw.fetch(hist_req())
    conn = db.connect()
    dump = json.dumps([dict(r) for r in conn.execute("SELECT * FROM raw_responses").fetchall()])
    dump += json.dumps([dict(r) for r in conn.execute("SELECT * FROM ledger").fetchall()])
    assert FAKE_KEY not in dump


def test_persist_before_parse_survives_parser_crash():
    client = FakeClient().push(history("111"))
    gw = make(client)
    resp = gw.fetch(hist_req())

    def broken_parser(body):
        raise ValueError("parser bug")

    with pytest.raises(ValueError):
        broken_parser(resp.body)
    again = make(FakeClient()).fetch(hist_req())  # a fresh gateway whose client would fail on any call
    assert again.from_cache and again.body == resp.body


def test_no_key():
    gw = Gateway(secrets=config.Secrets(None, None), client=None)
    with pytest.raises(NoApiKey):
        gw.fetch(hist_req())


def test_offline_mode_never_calls():
    client = FakeClient()
    gw = make(client, mode="offline")
    with pytest.raises(NotCached):
        gw.fetch(hist_req())
    assert client.calls == []


def test_dry_run_lists_planned_requests():
    client = FakeClient()
    gw = make(client, dry_run=True)
    with pytest.raises(NotCached):
        gw.fetch(hist_req("5"))
    result = gw.fetch_pages(DATA_ID, 88)
    assert client.calls == []
    assert result.missing_pages == 5 and not result.complete
    assert [p.cost for p in gw.planned] == [1] * 6
    assert gw.planned[1].request_key == catalog.reviews_page(DATA_ID).key
    assert gw.planned[2].request_key is None  # depends on page 1's token


def test_monthly_cap(monkeypatch, clock):
    monkeypatch.setitem(config.load_tunables()["budget"], "monthly_cap", 2)
    client = FakeClient(default=lambda p: history(p["contributor_id"]))
    gw = make(client, clock)
    gw.fetch(hist_req("1"))
    gw.fetch(hist_req("2"))
    with pytest.raises(BudgetRefused):
        gw.fetch(hist_req("3"))
    assert len(client.calls) == 2


def test_rolling_hour_pauses_and_says_when(monkeypatch, clock):
    monkeypatch.setitem(config.load_tunables()["budget"], "hourly_cap", 2)
    client = FakeClient(default=lambda p: history(p["contributor_id"]))
    gw = make(client, clock)
    gw.fetch(hist_req("1"))
    first_time = clock.now
    clock.advance(minutes=10)
    gw.fetch(hist_req("2"))
    clock.advance(minutes=10)
    with pytest.raises(Paused) as info:
        gw.fetch(hist_req("3"))
    assert info.value.reason == "hourly_limit"
    assert info.value.resume_at == first_time + timedelta(minutes=60)
    clock.advance(minutes=41)  # the first request has left the window
    gw.fetch(hist_req("3"))
    assert len(client.calls) == 3


def test_per_analysis_cap(monkeypatch):
    monkeypatch.setitem(config.load_tunables()["budget"], "per_analysis_cap", 1)
    gw = make(FakeClient(default=lambda p: history(p["contributor_id"])))
    gw.fetch(hist_req("1"), analysis_id="a1")
    with pytest.raises(BudgetRefused, match="Per-analysis"):
        gw.fetch(hist_req("2"), analysis_id="a1")
    gw.fetch(hist_req("2"), analysis_id="a2")


def test_account_numbers_are_stricter(clock):
    client = FakeClient(
        default=lambda p: history(p["contributor_id"]),
        account={
            "total_searches_left": 1,
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 0,
            "plan_renewal_date": "2026-10-05",
        },
    )
    gw = make(client, clock)
    account = gw.refresh_account()
    assert "api_key" not in account and "account_email" not in account
    assert FAKE_KEY not in json.dumps(account)
    gw.fetch(hist_req("1"))
    with pytest.raises(BudgetRefused):
        gw.fetch(hist_req("2"))


def test_strip_account():
    assert strip_account({"api_key": "k", "account_email": "e", "total_searches_left": 3}) == {"total_searches_left": 3}


def test_401_stops_everything_without_retry(caplog):
    client = FakeClient().push(http_error(401, "Invalid API key."))
    gw = make(client)
    with caplog.at_level(logging.DEBUG), pytest.raises(InvalidApiKey) as info:
        gw.fetch(hist_req())
    assert FAKE_KEY not in str(info.value) and FAKE_KEY not in caplog.text
    assert len(client.calls) == 1
    with pytest.raises(InvalidApiKey):
        gw.fetch(hist_req("2"))
    assert len(client.calls) == 1
    assert [r["status"] for r in ledger_rows()] == ["error"]


def test_429_pauses():
    client = FakeClient().push(http_error(429, "rate limited"))
    gw = make(client)
    with pytest.raises(Paused) as info:
        gw.fetch(hist_req())
    assert info.value.reason == "rate_limited" and info.value.resume_at is not None
    assert len(client.calls) == 1


def test_400_is_bad_request_not_retried():
    client = FakeClient().push(http_error(400, "Missing contributor_id"))
    with pytest.raises(BadRequest, match="Missing contributor_id"):
        make(client).fetch(hist_req())
    assert len(client.calls) == 1


def test_5xx_retried_once_after_delay_then_ok():
    sleeps = []
    client = FakeClient().push(http_error(503), history("111"))
    gw = Gateway(secrets=config.Secrets(FAKE_KEY, None), client=client, sleep=sleeps.append, clock=Clock())
    assert gw.fetch(hist_req()).status == "ok"
    assert sleeps == [30.0] and len(client.calls) == 2


def test_timeouts_twice_pause(caplog):
    client = FakeClient().push(timeout_error(), timeout_error())
    gw = make(client)
    with caplog.at_level(logging.DEBUG), pytest.raises(Paused) as info:
        gw.fetch(hist_req())
    assert info.value.reason == "upstream_error"
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in str(info.value)
    assert len(client.calls) == 2


def test_empty_result_is_billed_and_cached():
    empty = {"search_metadata": {"id": "e1"}, "error": "Google hasn't returned any results for this query."}
    client = FakeClient().push(empty)
    gw = make(client)
    assert gw.fetch(hist_req()).status == "empty"
    assert gw.fetch(hist_req()).from_cache
    assert [r["status"] for r in ledger_rows()] == ["empty"]
    assert gw.budget_status().ledger_month == 1


def test_error_body_not_cached():
    client = FakeClient().push({"search_metadata": {"id": "x"}, "error": "Invalid data_id"}, history("111"))
    gw = make(client)
    with pytest.raises(BadRequest):
        gw.fetch(hist_req())
    assert gw.fetch(hist_req()).status == "ok"
    assert gw.budget_status().ledger_month == 1  # errors aren't billed


def test_forced_refresh_adds_a_version():
    client = FakeClient().push(history("111", n=1), history("111", n=2))
    gw = make(client)
    gw.fetch(hist_req())
    refreshed = gw.fetch(hist_req(), force_refresh=True)
    assert refreshed.version == 2 and len(refreshed.body["reviews"]) == 2
    assert gw.fetch(hist_req()).version == 2
    versions = db.connect().execute("SELECT version FROM raw_responses ORDER BY version").fetchall()
    assert [v[0] for v in versions] == [1, 2]


# ---------------------------------------------------------------- pagination


def pages_client():
    return FakeClient().push(
        reviews_page(0, 8, "t1"),
        reviews_page(8, 20, "t2"),
        reviews_page(28, 20, "t3"),
        reviews_page(48, 20, "t4"),
        reviews_page(68, 20, "t5"),
    )


def test_pagination_fetches_all_pages():
    client = pages_client()
    result = make(client).fetch_pages(DATA_ID, 88)
    assert result.complete and len(result.responses) == 5
    assert "num" not in client.calls[0] and client.calls[1]["num"] == "20"
    assert client.calls[2]["next_page_token"] == "t2"


def test_pagination_checks_budget_for_all_pages_before_starting(monkeypatch):
    monkeypatch.setitem(config.load_tunables()["budget"], "hourly_cap", 4)
    client = pages_client()
    with pytest.raises(Paused):
        make(client).fetch_pages(DATA_ID, 88)
    assert client.calls == []


def test_pagination_stops_when_reviews_run_out():
    client = FakeClient().push(reviews_page(0, 8, "t1"), reviews_page(8, 5, None))
    gw = make(client)
    result = gw.fetch_pages(DATA_ID, 88)
    assert result.complete and len(result.responses) == 2
    assert gw._inflight == 0  # unused reserved slots are released


def test_pagination_failure_keeps_pages_and_resumes_from_cache():
    client = FakeClient().push(reviews_page(0, 8, "t1"), reviews_page(8, 20, "t2"), http_error(500), http_error(500))
    gw = make(client)
    partial = gw.fetch_pages(DATA_ID, 88)
    assert not partial.complete and len(partial.responses) == 2 and partial.missing_pages == 3
    assert "stopped after 2 pages" in partial.note
    client.push(reviews_page(28, 20, "t3"), reviews_page(48, 20, "t4"), reviews_page(68, 20, None))
    calls_before = len(client.calls)
    done = gw.fetch_pages(DATA_ID, 88)
    assert done.complete and len(done.responses) == 5
    assert len(client.calls) - calls_before == 3  # nothing requested twice
    assert client.calls[calls_before]["next_page_token"] == "t2"


def test_budget_inflight_counts_during_reservation(monkeypatch):
    monkeypatch.setitem(config.load_tunables()["budget"], "hourly_cap", 10)
    gw = make(FakeClient())
    with gw.reserve(4):
        assert gw.budget_status().hour_remaining == 6
    assert gw.budget_status().hour_remaining == 10
