from lorex.metadata.model import MetadataLookup, normalize_lookup_key


def test_isbn13_is_preferred_and_punctuation_is_removed():
    lookup = MetadataLookup(
        title="Ignored Title",
        authors=("Ignored Author",),
        isbn13="978-0-06-327932-7",
        isbn10="0063279328",
        asin="b0secret",
    )

    assert normalize_lookup_key(lookup) == "lorex:metadata:v1:isbn13:9780063279327"


def test_isbn10_is_used_when_isbn13_is_absent():
    lookup = MetadataLookup(isbn10="0-06-327932-8")
    assert normalize_lookup_key(lookup) == "lorex:metadata:v1:isbn10:0063279328"


def test_asin_is_normalized_to_uppercase():
    lookup = MetadataLookup(asin=" b0abc12345 ")
    assert normalize_lookup_key(lookup) == "lorex:metadata:v1:asin:B0ABC12345"


def test_title_author_key_casefolds_and_collapses_whitespace():
    lookup = MetadataLookup(
        title="  Project   HAIL   Mary ",
        authors=("  Andy   WEIR ",),
    )
    assert normalize_lookup_key(lookup) == "lorex:metadata:v1:title-author:project hail mary|andy weir"


def test_cache_key_never_contains_provider_credentials():
    lookup = MetadataLookup(title="Book", authors=("Author",))
    key = normalize_lookup_key(lookup)
    assert "api" not in key
    assert "secret" not in key


def test_lookup_requires_at_least_one_stable_identity():
    try:
        normalize_lookup_key(MetadataLookup())
    except ValueError as exc:
        assert "identifier" in str(exc).lower() or "title" in str(exc).lower()
    else:
        raise AssertionError("empty lookup should be rejected")
