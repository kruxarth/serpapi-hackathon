"""Per-review warning signs, the sieve, the AI-written opinion and the reviewing-spree signal."""

import json
from datetime import timedelta

from reviewring import config
from reviewring.engine.analyze import analyze
from reviewring.engine.signs import first_time_skew
from reviewring.exporter import input_from_dict, input_to_dict, pseudonymize_input
from reviewring.llm import LLMGateway, judge_texts, valid_cues
from reviewring.privacy import pseudonymize_report
from reviewring.synth import FETCHED, World, ordinary_reviewers, plant_ring

POLISHED = (
    "I recently used their services and I must say the experience was absolutely seamless. From start to finish the "
    "team demonstrated impeccable professionalism and attention to detail, and every item arrived in perfect "
    "condition. Overall, I can't recommend them enough for anyone looking for a stress-free move this year!"
)
TYPED = (
    "Booked them for shifting. Rajesh bhaiya and team came at 9am sharp, packing was good but they charged 1500 "
    "extra for the fridge which was not told before. One chair leg broke, they gave 500 rs adjustment after I "
    "complained. Overall ok."
)


class FakeTransport:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, messages, json_mode):
        assert json_mode and "json" in messages[0]["content"].lower()
        self.calls.append(json.loads(messages[1]["content"]))
        return self.reply(self.calls[-1]) if callable(self.reply) else self.reply


def gw(transport):
    return LLMGateway(mode="live", secrets=config.Secrets(None, None), transport=transport)


def by_text(report, text):
    return next(r for r in report["reviews"] if r["text"] == text)


# ---------------------------------------------------------------------- the AI-written opinion


def test_only_long_reviews_are_sent_and_cues_must_be_quoted():
    texts = {"r1": POLISHED, "r2": TYPED, "r3": "Very good service, highly recommended"}

    def reply(payload):
        items = []
        for it in payload["reviews"]:
            if "seamless" in it["text"]:
                cues = ["absolutely seamless", "impeccable professionalism and attention to detail"]
                items.append({"index": it["index"], "verdict": "ai_style", "cues": cues})
            else:
                items.append({"index": it["index"], "verdict": "ai_style", "cues": ["words that are not there"]})
        return json.dumps({"items": items})

    t = FakeTransport(reply)
    out = judge_texts(texts, gw(t), set())
    sent = [it["text"] for call in t.calls for it in call["reviews"]]
    assert len(sent) == 2 and not any(s.startswith("Very good service") for s in sent)  # too short to judge
    assert out["r1"]["verdict"] == "ai_style" and len(out["r1"]["cues"]) == 2
    assert out["r2"] == {"verdict": "unclear", "cues": [], "model": out["r2"]["model"]}  # invented cues: downgraded
    assert "r3" not in out


def test_quotes_crossing_a_scrubbed_name_count_but_are_not_shown():
    text = POLISHED + " Overall, Gold Movers is a truly seamless choice for every family moving homes."
    cues = ["absolutely seamless", "Overall, [business] [business] is a truly seamless choice"]
    t = FakeTransport(json.dumps({"items": [{"index": 0, "verdict": "ai_style", "cues": cues}]}))
    out = judge_texts({"r1": text}, gw(t), {"Gold", "Movers"})
    assert out["r1"]["verdict"] == "ai_style" and out["r1"]["cues"] == ["absolutely seamless"]


def test_texts_are_scrubbed_before_sending():
    text = POLISHED + " Call 9876543210 or see www.example.com, ask for Gold Movers."
    t = FakeTransport(json.dumps({"items": [{"index": 0, "verdict": "human_style", "cues": []}]}))
    judge_texts({"r1": text}, gw(t), {"Gold", "Movers"})
    sent = t.calls[0]["reviews"][0]["text"]
    assert "9876543210" not in sent and "example.com" not in sent and "Gold" not in sent


def test_valid_cues_tolerates_quotes_and_case_but_not_inventions():
    assert valid_cues(["“Absolutely Seamless”", "made up"], POLISHED) == ["Absolutely Seamless"]
    assert valid_cues("not a list", POLISHED) == []


def test_offline_gateway_never_calls():
    offline = LLMGateway(mode="offline", secrets=config.Secrets(None, "key"))
    assert judge_texts({"r1": POLISHED}, offline, set()) == {}


# ---------------------------------------------------------------------- signs and the sieve


def movers(burst=12):
    w = World(total_reviews=600)
    ordinary_reviewers(w, 40)
    t = FETCHED - timedelta(days=30)
    for i in range(burst):
        cid = w.reviewer(total=1, photos=0)
        w.histories[cid] = []
        w.review_target(cid, rating=5, when=t + timedelta(hours=i * 3), total=1, photos=0, text="Excellent service")
    chatbot = w.review_target(None, rating=5, text="Sure! Here's a review you can post: great team at [Business Name].")
    ai = w.review_target(None, rating=5, text=POLISHED, total=2)
    typed = w.review_target(None, rating=3, text=TYPED, total=30)
    return w, chatbot, ai, typed


def test_signs_in_sieve_order_and_defaults():
    w, chatbot, ai, typed = movers()
    inp = w.build()
    inp.text_judgements = {
        ai.review_id: {"verdict": "ai_style", "cues": ["absolutely seamless", "Overall, I can't recommend"]},
        typed.review_id: {"verdict": "human_style", "cues": []},
    }
    report = analyze(inp)
    sieve = report["sieve"]
    assert sieve["order"][:6] == [
        "chatbot_text",
        "copied_text",
        "voice_mismatch",
        "keyword_style",
        "first_time_burst",
        "linked_group",
    ]
    assert sieve["signs"]["first_time_burst"]["count"] >= 10
    assert sieve["signs"]["chatbot_text"]["count"] == 1 and sieve["signs"]["ai_style"]["count"] == 1
    assert by_text(report, POLISHED)["signs"] == ["ai_style"]
    assert by_text(report, POLISHED)["ai"]["cues"] == ["absolutely seamless", "Overall, I can't recommend"]
    assert by_text(report, TYPED)["signs"] == []
    # Strong signs are set aside by default; the AI opinion and first-time accounts are kept.
    kept = [r for r in report["reviews"] if not set(sieve["set_aside_by_default"]) & set(r["signs"])]
    assert sieve["kept"]["count"] == len(kept) and report["ratings"]["kept_count"] == len(kept)
    assert "ai_style" not in sieve["set_aside_by_default"] and "first_time_account" not in sieve["set_aside_by_default"]
    assert sieve["ai"]["judged"] == 2 and sieve["ai"]["ai_style"] == 1
    assert any(e["kind"] == "ai_style" for e in report["evidence"])
    assert any("AI model's opinion" in c for c in report["caveats"])


def test_burst_reviews_also_carry_the_first_time_sign():
    w, *_ = movers()
    report = analyze(w.build())
    burst = [r for r in report["reviews"] if "first_time_burst" in r["signs"]]
    assert burst and all("first_time_account" in r["signs"] for r in burst)
    assert all(r["signs"].index("first_time_burst") < r["signs"].index("first_time_account") for r in burst)


def test_ring_members_get_linked_group_and_copied_text():
    w = World()
    ordinary_reviewers(w, 20)
    members = plant_ring(w, 6, cities=["Jaipur", "Kochi", "Lucknow"], m=4)
    report = analyze(w.build())
    rows = [r for r in report["reviews"] if r["contributor_id"] in members]
    assert all("linked_group" in r["signs"] for r in rows)
    assert any("copied_text" in r["signs"] for r in rows)


def test_first_time_skew_compares_five_star_with_other_reviews():
    w = World()
    for i in range(20):
        w.review_target(None, rating=5, total=1 if i < 12 else 30)
    for i in range(10):
        w.review_target(None, rating=w.rng.choice((2, 3, 4)), total=1 if i < 1 else 30)
    skew = first_time_skew(w.build().target_reviews)
    assert skew["flagged"] and skew["five_star_first_time"] == 12 and skew["other_first_time"] == 1
    report = analyze(w.build())
    assert any(e["kind"] == "first_time_skew" for e in report["evidence"])


def test_first_time_skew_ignores_a_normal_share_of_first_time_accounts():
    w = World()
    for i in range(70):
        w.review_target(None, rating=5, total=1 if i < 14 else 30)  # 20%, as on a real clean listing
    for _ in range(14):
        w.review_target(None, rating=4, total=30)
    assert not first_time_skew(w.build().target_reviews)["flagged"]


def test_first_time_skew_needs_enough_reviews():
    w = World()
    for _ in range(4):
        w.review_target(None, rating=5, total=1)
    for _ in range(4):
        w.review_target(None, rating=3, total=30)
    assert not first_time_skew(w.build().target_reviews)["flagged"]


# ---------------------------------------------------------------------- reviewing spree (A9)


def spree_world(ratings=5, cities=("Mumbai", "Jaipur", "Goa", "Kochi", "Hyderabad", "Kolkata")):
    w = World(target_city="Delhi NCR", target_type="Hotel")
    ordinary_reviewers(w, 10, home="Delhi NCR")
    cid = w.reviewer(total=14, photos=0)
    for j, city in enumerate(list(cities) * 2):
        rating = ratings if isinstance(ratings, int) else ratings[j % len(ratings)]
        w.add_history(cid, w.place(city, "Hotel"), rating, days_ago=20 + j * 2, precision="week")
    w.review_target(cid, rating=5)
    return w, cid


def test_reviewing_spree_is_context_only():
    w, cid = spree_world()
    report = analyze(w.build())
    reviewer = next(r for r in report["reviewers"] if r["contributor_id"] == cid)
    a9 = next(b for b in reviewer["badges"] if b["code"] == "A9")
    assert a9["places"] >= 8 and len(a9["areas"]) >= 3
    assert "review_spree" in next(r for r in report["reviews"] if r["contributor_id"] == cid)["signs"]
    assert report["level"]["level"] == "Low"  # never raises the level


def test_presentation_mode_handles_a_spree_badge():
    w, cid = spree_world()
    report = analyze(w.build())
    shown = pseudonymize_report(report, salt_value="s")
    badge = next(b for r in shown["reviewers"] for b in r["badges"] if b["code"] == "A9")
    assert (
        isinstance(badge["places"], int)
        and badge["from"] != next(b for r in report["reviewers"] for b in r["badges"] if b["code"] == "A9")["from"]
    )  # dates shifted


def test_travellers_with_mixed_ratings_are_not_a_spree():
    w, cid = spree_world(ratings=(5, 3, 4, 2))
    report = analyze(w.build())
    reviewer = next(r for r in report["reviewers"] if r["contributor_id"] == cid)
    assert all(b["code"] != "A9" for b in reviewer["badges"])


# ---------------------------------------------------------------------- privacy


def test_presentation_mode_scrubs_ai_cues_and_hides_texts():
    w, _, ai, _ = movers()
    inp = w.build()
    inp.text_judgements = {ai.review_id: {"verdict": "ai_style", "cues": ["call 9876543210 now", "x" * 90]}}
    report = analyze(inp)
    shown = pseudonymize_report(report, salt_value="s")
    row = next(r for r in shown["reviews"] if r["ai"])
    assert row["text"] is None and "9876543210" not in json.dumps(row["ai"]) and len(row["ai"]["cues"][1]) <= 60
    assert row["signs"] == ["ai_style"]


def test_fixture_input_carries_hashed_judgements():
    w, _, ai, _ = movers()
    inp = w.build()
    inp.text_judgements = {ai.review_id: {"verdict": "ai_style", "cues": ["absolutely seamless"], "model": "m"}}
    pseudo = pseudonymize_input(inp, "s")
    assert ai.review_id not in pseudo.text_judgements and len(pseudo.text_judgements) == 1
    assert all(r.text is None or r.text != POLISHED for r in pseudo.target_reviews)  # real texts are dropped
    again = input_from_dict(json.loads(json.dumps(input_to_dict(pseudo), default=str)))
    assert again.text_judgements == pseudo.text_judgements
    assert analyze(again)["sieve"]["signs"]["ai_style"]["count"] == 1
    kept = pseudonymize_input(inp, "s", keep_texts=True)  # synthetic worlds keep their invented texts
    assert any(r.text == POLISHED for r in kept.target_reviews)


# ---------------------------------------------------------------------- written like a search ad


def keyword_world(n_keyword=6):
    w = World(target_city="Pune", target_type="Packers and movers")
    w.target.title = "Om Shanti Packers and Movers"
    w.target.address = "Shop 4, Hadapsar, Pune, Maharashtra 411028"
    ordinary_reviewers(w, 30, home="Pune")
    phrases = [
        "Most trusted and reliable Packers And Movers In Hadapsar, Pune. Very happy with the service.",
        "I recently used Om Shanti Packers and Movers, Hadapsar, Pune for my home relocation and it was smooth.",
        "If you are looking for packers and movers in Pune go for them, careful packing and on time.",
    ]
    ids = []
    for i in range(n_keyword):
        cid = w.reviewer(total=3, photos=0)
        w.personal_history(cid, "Pune", 2)
        ids.append(w.review_target(cid, rating=5, text=phrases[i % 3]).review_id)
    return w, ids


def test_search_ad_phrasing_needs_several_accounts():
    from reviewring.engine.textstyle import keyword_phrase, name_tokens, place_tokens

    w, ids = keyword_world()
    names, places = name_tokens(w.target), place_tokens(w.target)
    assert keyword_phrase("The movers reached Pune on time and the team was polite.", names, places) is None
    assert keyword_phrase("Shifted from Hadapsar to Baner. Packers were careful.", names, places) is None
    assert keyword_phrase("Thanks to the packers and new team", names, places) is None
    report = analyze(w.build())
    rows = [r for r in report["reviews"] if r["review_id"] in ids]
    assert all("keyword_style" in r["signs"] and r["keyword_phrase"] for r in rows)
    assert report["signals"]["T10"]["flagged"] and report["level"]["level"] == "Elevated"
    assert "keyword_style" in report["sieve"]["set_aside_by_default"]
    one, ids1 = keyword_world(n_keyword=1)
    lone = next(r for r in analyze(one.build())["reviews"] if r["review_id"] == ids1[0])
    assert "keyword_style" not in lone["signs"]  # one customer writing it means nothing


def test_keyword_reviewers_are_opened_first():
    from reviewring.engine.features import compute_text_features
    from reviewring.engine.priority import score_reviews
    from reviewring.engine.target_signals import detect_bursts

    w, ids = keyword_world()
    inp = w.build()
    plain = score_reviews(inp.target_reviews, detect_bursts(inp.target_reviews), compute_text_features(inp))
    boosted = score_reviews(inp.target_reviews, detect_bursts(inp.target_reviews), compute_text_features(inp), set(ids))
    score = lambda cands: next(c for c in cands if c.review_id == ids[0])  # noqa: E731
    assert score(boosted).parts.get("keyword_style") == 2 and score(boosted).score == score(plain).score + 2


# ---------------------------------------------------------------------- not in the reviewer's own voice


def voice_world():
    w = World(target_city="Bengaluru", target_type="Packers and movers")
    ordinary_reviewers(w, 15, home="Bengaluru")
    cid = w.reviewer(total=5, photos=2)
    for t in ["food is tasty good and higenic staff is good", "nice miting and company", "bahut badiya office hai"]:
        w.add_history(cid, w.place("Bengaluru", "Restaurant"), 5, text=t)
    script = (
        "The house shifting went smoothly. Everything arrived damage free, packed neatly, and the team handled "
        "fragile items with care. Highly reliable and reasonably priced."
    )
    r = w.review_target(cid, rating=5, text=script)
    w.expand(cid)
    return w, cid, r


def test_voice_mismatch_needs_a_quote_from_each_side():
    from reviewring.llm import judge_voices

    w, cid, _ = voice_world()
    inp = w.build()

    def reply(payload):
        items = []
        for it in payload["items"]:
            good = "nice miting" in " ".join(it["other_reviews"])
            items.append(
                {
                    "index": it["index"],
                    "verdict": "different_voice",
                    "here": "Everything arrived damage free" if good else "not in the text",
                    "elsewhere": "nice miting and company" if good else "nor this",
                }
            )
        return json.dumps({"items": items})

    t = FakeTransport(reply)
    out = judge_voices(inp, gw(t), set())
    assert out[cid]["verdict"] == "different_voice" and out[cid]["here"] == "Everything arrived damage free"
    others = [o for c, o in out.items() if c != cid]
    assert all(o["verdict"] == "unclear" for o in others)  # invented quotes are not evidence
    sent = t.calls[0]["items"]
    assert all("contributor" not in json.dumps(it) for it in sent)


def test_voice_mismatch_sign_report_and_privacy():
    w, cid, r = voice_world()
    inp = w.build()
    inp.voice_judgements = {
        cid: {
            "verdict": "different_voice",
            "here": "Everything arrived damage free",
            "elsewhere": "nice miting and company",
            "model": "m",
        }
    }
    report = analyze(inp)
    row = next(x for x in report["reviews"] if x["review_id"] == r.review_id)
    assert row["signs"][0] == "voice_mismatch" and row["voice"]["others"]
    assert report["sieve"]["voice"]["different_voice"] == 1
    assert any(e["kind"] == "voice_mismatch" for e in report["evidence"])
    shown = pseudonymize_report(report, salt_value="s")
    srow = next(x for x in shown["reviews"] if x.get("voice"))
    assert srow["voice"]["others"] == [] and srow["voice"]["here"] == "Everything arrived damage free"
    pseudo = pseudonymize_input(inp, "s")
    assert cid not in pseudo.voice_judgements and len(pseudo.voice_judgements) == 1
    again = input_from_dict(json.loads(json.dumps(input_to_dict(pseudo), default=str)))
    assert analyze(again)["sieve"]["signs"]["voice_mismatch"]["count"] == 1
