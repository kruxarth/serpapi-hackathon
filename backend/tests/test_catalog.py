"""Request-key canonicalization is frozen at M1: these hashes must never change."""

from reviewring.serp import catalog as c


def test_pinned_request_keys():
    pinned = {
        c.reviews_page("0x3BE7C1A2B3C4D5E6:0x1A2B3C4D5E6F7081"): (
            "ff136983da803161ec3700f01705c24a854381de03ef3e8c77e3049942539af6"
        ),
        c.reviews_page("0x3be7c1a2b3c4d5e6:0x1a2b3c4d5e6f7081", "tok123"): (
            "37c9dc46fb94c9450d1ea39d628e43525d1b1dcc682781f9be1a9e4372c75bad"
        ),
        c.contributor_history("104200000000000000001"): (
            "e6d7059b1f252530300dd5c3b142bc4289a63411e8f943db299e9137047c1440"
        ),
        c.place_by_cid("754378145412703429"): "4e3507c8858e88a13540b8cb040085f7bb9c8558e9b3e7848f78ac076826f038",
        c.place_by_place_id("ChIJinventedPlaceId000"): (
            "bbd817199772453e8f99a5331659849e2afcccbc0e58adafdee0c2fba8a7bd53"
        ),
        c.place_search("Invented  Dental Clinic, Pune"): (
            "aa972038f33d44d2181d84ceedf6bb3b0573cf4d52912094877adf2a096d3682"
        ),
    }
    for req, key in pinned.items():
        assert req.key == key, req.canonical()


def test_page_params():
    first = c.reviews_page("0xA:0xB")
    assert first.params == {"data_id": "0xa:0xb", "hl": "en", "sort_by": "newestFirst"}
    assert "num" not in first.params
    later = c.reviews_page("0xa:0xb", "t")
    assert later.params["num"] == "20" and later.params["next_page_token"] == "t"
    assert c.contributor_history("42").params["num"] == "200"


def test_key_never_includes_api_key():
    req = c.reviews_page("0xa:0xb")
    assert "api_key" not in req.canonical()


def test_data_cid_from_data_id():
    assert c.data_cid_from_data_id("0x3bae1d8b1f0d3c4b:0xa7816ed27a464c5") == "754378145412703429"
    assert c.data_cid_from_data_id("0X3BAE1D8B1F0D3C4B:0XA7816ED27A464C5") == "754378145412703429"
