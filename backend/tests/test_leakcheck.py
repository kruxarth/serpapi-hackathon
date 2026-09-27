import json

from reviewring import leakcheck
from reviewring.serp import catalog

from .fakes import FakeClient, reviews_page
from .test_gateway import make


def kinds(obj, originals=None):
    return {f.kind for f in leakcheck.check_object(obj, "f.json", originals or {})}


def test_clean_fixture_passes():
    obj = {
        "places": [{"title": "Dental clinic A", "area": "Pune", "lat": 18.52}],
        "reviews": [{"text": "[text not included: 84 characters]", "text_hash": "ab12cd", "iso_date": "2026-09-20"}],
        "reviewers": [{"name": "Reviewer 3", "contributor_hash": "9f8e7d6c5b4a"}],
    }
    assert kinds(obj) == set()


def test_detects_urls_emails_phones_pins():
    assert "URL" in kinds({"t": "see https://lh3.googleusercontent.com/x"})
    assert "URL" in kinds({"t": "maps.app.goo.gl/abc"})
    assert "email address" in kinds({"t": "mail a.b@example.org"})
    assert "phone number" in kinds({"text": "call 98765 43210 now"})
    assert "phone number" in kinds({"text": "+91-9876543210"})
    assert "PIN code" in kinds({"area": "Kothrud, Pune 411038"})
    assert "PIN code" not in kinds({"text_hash": "411038"})


def test_detects_originals_from_cache():
    gw = make(FakeClient().push(reviews_page(0, 8, None)))
    gw.fetch(catalog.reviews_page("0x1:0x2"))
    originals = leakcheck.originals_from_cache()
    assert "Invented Clinic" in originals["business title"]
    assert "9003" in originals["contributor id"]
    found = kinds({"text": "They loved invented clinic!", "who": "Invented Person 2"}, originals)
    assert {"original business title", "original reviewer name"} <= found


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"a": "Business A"}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"a": "https://www.google.com/maps/place/x"}))
    assert leakcheck.main([str(good)]) == 0
    assert leakcheck.main([str(tmp_path)]) == 1
