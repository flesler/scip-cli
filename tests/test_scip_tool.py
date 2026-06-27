"""Tests for scip binary resolution."""

from scip_cli.scip_tool import _platform_archive, parse_scip_version


class TestParseScipVersion:
    def test_parses_tagged_version(self):
        assert parse_scip_version("scip version v0.8.1") == (0, 8, 1)

    def test_rejects_unrelated_tool(self):
        assert parse_scip_version("SCIP Optimization Suite 8.0") is None


class TestPlatformArchive:
    def test_returns_known_archive_name(self):
        name = _platform_archive()
        assert name.startswith("scip-")
        assert name.endswith(".tar.gz")
