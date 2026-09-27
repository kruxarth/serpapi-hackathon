import pytest
import requests

from reviewring.resolve import InputRefused, candidates_from_body, expand_short_link, parse_input, parse_maps_url

DID = "0x3be7c1a2b3c4d5e6:0x1a2b3c4d5e6f7081"
PLACE = (
    "https://www.google.com/maps/place/Invented+Clinic/@18.5000000,73.8000000,17z/"
    "data=!3m1!4b1!4m6!3m5!1s0x3be7c1a2b3c4d5e6:0x1a2b3c4d5e6f7081!8m2!3d18.5204303!4d73.8567437"
    "!16s%2Fg%2F11invented?entry=ttu"
)


def test_place_url_data_id_and_place_coords_not_viewport():
    r = parse_maps_url(PLACE)
    assert r.kind == "data_id" and r.cost == 0 and r.data_id == DID
    assert (r.lat, r.lng) == (18.5204303, 73.8567437)


def test_uppercase_hex_prefix_and_percent_encoding():
    url = "https://www.google.co.in/maps/place/X/data=!4m2!3m1!1s0X3BE7C1A2B3C4D5E6%3A0X1A2B3C4D5E6F7081"
    assert parse_maps_url(url).data_id == DID


def test_double_percent_encoding():
    url = "https://maps.google.com/maps?ftid=0x3be7c1a2b3c4d5e6%253A0x1a2b3c4d5e6f7081"
    assert parse_maps_url(url).data_id == DID


def test_ftid_parameter():
    r = parse_maps_url(f"https://maps.google.com/?ftid={DID}")
    assert r.kind == "data_id" and r.data_id == DID and r.lat is None


def test_several_coordinate_pairs_takes_the_one_after_8m2():
    url = (
        "https://www.google.com/maps/place/X/@10.0,70.0,15z/data=!3d11.1!4d71.1!4m5!3m4"
        f"!1s{DID}!8m2!3d19.0760!4d72.8777!3d1.0!4d2.0"
    )
    r = parse_maps_url(url)
    assert (r.lat, r.lng) == (19.0760, 72.8777)


def test_cid_url():
    r = parse_input("https://maps.google.com/?cid=754378145412703429")
    assert r.kind == "cid" and r.cid == "754378145412703429" and r.cost == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/maps/search/?api=1&query=x&query_place_id=ChIJinvented_Id-1",
        "https://www.google.com/maps/place/?q=place_id:ChIJinvented_Id-1",
        "https://www.google.com/maps/place/X/data=!4m2!3m1!1sChIJinvented_Id-1",
        "https://www.google.com/maps/place/?place_id=ChIJinvented_Id-1",
    ],
)
def test_place_id_only_urls(url):
    r = parse_input(url)
    assert r.kind == "place_id" and r.place_id == "ChIJinvented_Id-1" and r.cost == 1


def test_directions_url_refused():
    with pytest.raises(InputRefused, match="directions"):
        parse_input("https://www.google.com/maps/dir/A/B/")


def test_search_with_two_data_ids_refused():
    url = "https://www.google.com/maps/search/clinics/data=!1s0xaa:0xbb!1s0xcc:0xdd"
    with pytest.raises(InputRefused, match="several places"):
        parse_input(url)


def test_non_maps_refused():
    with pytest.raises(InputRefused):
        parse_input("https://example.com/maps/place/x")
    with pytest.raises(InputRefused):
        parse_input("https://www.google.com/search?q=clinic")


def test_name_and_city():
    r = parse_input("Invented Dental Clinic, Pune")
    assert r.kind == "name" and r.cost == 1


class FakeSession:
    def __init__(self, hops):
        self.hops = hops
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 10
        assert "Mozilla" in kwargs["headers"]["User-Agent"]
        resp = requests.Response()
        target = self.hops.get(url)
        if target is None:
            resp.status_code = 200
        else:
            resp.status_code = 302
            resp.headers["Location"] = target
        return resp


def test_short_link_follows_redirects():
    session = FakeSession({"https://maps.app.goo.gl/abc": PLACE})
    r = parse_input("https://maps.app.goo.gl/abc", session=session)
    assert r.data_id == DID and r.expanded_from == "https://maps.app.goo.gl/abc"


def test_short_link_consent_page():
    consent = "https://consent.google.com/ml?continue=" + requests.utils.quote(PLACE, safe="")
    session = FakeSession({"https://maps.app.goo.gl/abc": consent})
    assert parse_input("maps.app.goo.gl/abc", session=session).data_id == DID


def test_short_link_loop_detected():
    session = FakeSession(
        {
            "https://maps.app.goo.gl/a": "https://maps.app.goo.gl/b",
            "https://maps.app.goo.gl/b": "https://maps.app.goo.gl/a",
        }
    )
    with pytest.raises(InputRefused, match="loop"):
        expand_short_link("https://maps.app.goo.gl/a", session)


def test_short_link_too_many_redirects():
    hops = {f"https://maps.app.goo.gl/{i}": f"https://maps.app.goo.gl/{i + 1}" for i in range(20)}
    with pytest.raises(InputRefused, match="too many"):
        expand_short_link("https://maps.app.goo.gl/0", FakeSession(hops))


def test_candidates_from_lookup_bodies():
    single = {
        "place_results": {"title": "T", "data_id": "0xAA:0xBB", "gps_coordinates": {"latitude": 1, "longitude": 2}}
    }
    [c] = candidates_from_body(single)
    assert c.data_id == "0xaa:0xbb" and (c.lat, c.lng) == (1.0, 2.0)
    many = {"local_results": [{"title": str(i), "data_id": f"0x1:0x{i}"} for i in range(9)]}
    assert len(candidates_from_body(many)) == 5
