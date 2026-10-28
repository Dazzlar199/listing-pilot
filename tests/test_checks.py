from app import checks, meta


def test_bad_listing_is_caught():
    bad = meta._mock_listing(None)
    rules = {v.rule for v in checks.check_listing(bad, "Hearth & Clay")}
    for r in ["title.length", "title.chars", "title.repeat", "title.allcaps", "title.promo",
              "bullet.emoji", "bullet.guarantee", "description.contact", "search.asin", "search.brand"]:
        assert r in rules, r


def test_fixed_listing_passes():
    good = meta._mock_listing(["x"])
    fails = [v for v in checks.check_listing(good, "Hearth & Clay") if v.severity == "fail"]
    assert fails == [], [f.message for f in fails]


def test_search_terms_bytes():
    v = checks.check_search_terms("a" * 250, "Title")
    assert any(x.rule == "search.bytes" for x in v)
