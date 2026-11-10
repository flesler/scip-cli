"""Catalog stays aligned with CHECK_KEYS used by parse_checks."""

from scip_cli.analyze.check_catalog import CHECK_CATALOG, CHECK_KEYS, SLOP_CHECK_BUNDLE
from scip_cli.analyze.sections import parse_checks


def test_check_keys_match_catalog():
    catalog_keys = {doc.key for doc in CHECK_CATALOG}
    assert catalog_keys == CHECK_KEYS
    assert "one_line_exports" in CHECK_KEYS
    assert parse_checks(["dead_exports", "one_line_exports"]) == {"dead_exports", "one_line_exports"}


def test_slop_bundle_names_are_valid():
    for name in SLOP_CHECK_BUNDLE.split(","):
        assert name in CHECK_KEYS
