"""LLM gateway tests with recorded fake replies. No live DeepSeek call is ever made."""

import json

import pytest

from reviewring import config
from reviewring.engine.analyze import analyze
from reviewring.llm import (
    LLMGateway,
    LLMRefused,
    assert_safe,
    build_facts,
    forbidden_values,
    paraphrase_groups,
    summarize,
    validate_summary,
)
from reviewring.synth import World, ordinary_reviewers, plant_ring


class FakeTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages, json_mode):
        assert json_mode and "json" in messages[0]["content"].lower()
        self.calls.append(messages)
        return self.replies.pop(0)


def ring_report():
    w = World()
    ordinary_reviewers(w, 20)
    plant_ring(w, 8, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    return analyze(w.build())


def gw(transport):
    return LLMGateway(mode="live", secrets=config.Secrets(None, None), transport=transport)


def good_reply(facts):
    ids = [f["id"] for f in facts]
    return json.dumps(
        {
            "paragraphs": [
                f"[{ids[1]}] of [{ids[0]}] were examined.",
                f"The level is [{ids[3]}]. This is a pattern, not proof.",
            ]
        }
    )


def test_fact_ids_are_substituted():
    report = ring_report()
    facts = build_facts(report)
    t = FakeTransport(good_reply(facts))
    out = summarize(report, gw(t))
    assert out["source"] == "llm" and len(t.calls) == 1
    assert out["paragraphs"][0].startswith("the latest ")
    assert "[F" not in " ".join(out["paragraphs"])


@pytest.mark.parametrize(
    "text,problem",
    [
        ("See [F99].", "Unknown fact id"),
        ("About 30 reviews came from [F2].", "digit"),
        ("Twelve accounts reviewed [F1].", "number word 'twelve'"),
        ("They also reviewed places in Jaipur.", "place name 'Jaipur'"),
        ("These are fake reviews of [F1].", "'fake'"),
        ("The reviews look Paid for.", "'paid'"),
    ],
)
def test_validator_rejections(text, problem):
    facts = [{"id": "F1", "text": "x"}, {"id": "F2", "text": "y"}]
    problems = validate_summary([text], facts, set())
    assert any(problem.lower() in p.lower() for p in problems), problems


def test_validator_allows_whole_word_lookalikes_and_no_one():
    facts = [{"id": "F1", "text": "x"}]
    assert validate_summary(["An unpaid intern ordered scampi; no one else saw [F1]."], facts, set()) == []


def test_retry_then_template_fallback():
    report = ring_report()
    bad = json.dumps({"paragraphs": ["These 12 fake reviews."]})
    t = FakeTransport(bad, bad)
    out = summarize(report, gw(t))
    assert len(t.calls) == 2
    assert "problems_to_fix" in t.calls[1][1]["content"]  # the complaint goes back in the retry
    assert out["source"] == "template" and out["paragraphs"]


def test_retry_can_succeed():
    report = ring_report()
    facts = build_facts(report)
    t = FakeTransport(json.dumps({"paragraphs": ["It is 100% a scam."]}), good_reply(facts))
    assert summarize(report, gw(t))["source"] == "llm"


def test_cache_means_no_second_call():
    report = ring_report()
    t = FakeTransport(good_reply(build_facts(report)))
    summarize(report, gw(t))
    offline = LLMGateway(mode="offline", secrets=config.Secrets(None, None))
    out = summarize(report, offline)
    assert out["source"] == "llm" and len(t.calls) == 1


def test_no_key_uses_templates():
    report = ring_report()
    out = summarize(report, LLMGateway(mode="live", secrets=config.Secrets(None, None)))
    assert out["source"] == "template"


def test_pseudonymization_check_refuses_real_identities():
    report = ring_report()
    report["names"] = {report["reviewers"][0]["contributor_id"]: "Invented Realname"}
    forbidden = forbidden_values(report)
    with pytest.raises(LLMRefused):
        assert_safe('{"facts": ["Invented Realname reviewed"]}', forbidden)
    with pytest.raises(LLMRefused):
        assert_safe(json.dumps({"x": report["reviewers"][0]["contributor_id"]}), forbidden)
    with pytest.raises(LLMRefused):
        assert_safe('{"x": "https://www.google.com/maps/contrib/1"}', forbidden)
    assert_safe(json.dumps({"facts": build_facts(report)}), forbidden)  # the real payload is clean


def test_a8_never_flags_a_reviewer_on_its_own():
    w = World()
    ordinary_reviewers(w, 20)
    inp = w.build()
    ids = [r.review_id for r in inp.target_reviews[:5]]
    t = FakeTransport(json.dumps({"groups": [{"indices": [0, 1, 2, 3, 4], "reason": "same template"}]}))
    texts = {rid: next(r.text for r in inp.target_reviews if r.review_id == rid) for rid in ids}
    groups = paraphrase_groups(texts, gw(t), set())
    assert len(groups) == 5
    report = analyze(inp, paraphrase_groups=groups)
    a8 = [r for r in report["reviewers"] if any(b["code"] == "A8" for b in r["badges"])]
    assert a8, "A8 should be attached as context"
    assert all(r["label"] in ("no_flags", "not_checked") for r in a8)
    assert report["level"]["level"] == "Low"
