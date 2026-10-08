"""The home page's story data: real numbers, nothing that names a business or a person."""

import json

from reviewring import config
from reviewring.leakcheck import check_object
from reviewring.story_data import chatbot_excerpt

DATA = config.REPO_ROOT / "web" / "src" / "story" / "data.json"


def test_chatbot_excerpt_drops_the_name_even_when_cut_off():
    text = (
        "I'm unable to generate a review for you, but I can help you outline key points. "
        "Here's a template you can use: "
        "--- **Title: Enjoyable Stay at Hotel Golden Palms** **Rating: ⭐⭐⭐⭐⭐** **Overall Experience:** My stay at "
        "Hotel Golden Pal…"
    )
    out = chatbot_excerpt(text, {"Hotel", "Golden", "Palms"})
    assert "Golden" not in out and "Palms" not in out and "Pal" not in out.replace("[the hotel]", "")
    assert out.startswith("I'm unable to generate a review") and "[the hotel]" in out
    assert "Overall Experience" not in out  # cut at the rating line
    assert "\n---\n" in out


def test_committed_story_data_is_numbers_only():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert check_object(data, "story") == []
    text = json.dumps(data)
    for key in ("contributor_id", "review_id", "place_key", "title", "name"):
        assert f'"{key}"' not in text
    assert all(isinstance(r, int) for r in data["hotel"]["ratings"])
    assert all(d >= -1 for d in data["mover"]["days"])  # day offsets, never calendar dates


def test_generic_business_titles_are_not_leaks_but_distinctive_ones_are():
    originals = {"business title": {"New Delhi", "Best Packers And Movers", "Skin", "Shubh Yatra Movers"}}
    obj = {"text": "Best Packers And Movers in New Delhi, skin care", "other": "We used Shubh Yatra Movers"}
    findings = check_object(obj, "x", originals)
    assert [f.where for f in findings] == ["$.other"]
