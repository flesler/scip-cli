"""Tests for analyze graph helpers."""

from scip_cli.analyze.graph import find_longer_cycles

from .analyze_db import AnalyzeDbBuilder


class TestFindLongerCycles:
    def test_three_node_cycle(self):
        edges = [("a.ts", "b.ts"), ("b.ts", "c.ts"), ("c.ts", "a.ts")]
        lines = find_longer_cycles(edges, max_depth=8, limit=10)
        assert len(lines) == 1
        assert "a.ts" in lines[0]
        assert "b.ts" in lines[0]
        assert "c.ts" in lines[0]

    def test_two_node_skipped(self):
        edges = [("a.ts", "b.ts"), ("b.ts", "a.ts")]
        assert find_longer_cycles(edges, max_depth=8, limit=10) == []

    def test_mini_codebase_no_long_cycles(self):
        b = AnalyzeDbBuilder()
        sym_x = b.define("src/cycle/a.ts", "alpha")
        sym_y = b.define("src/cycle/b.ts", "beta")
        b.reference("src/cycle/a.ts", sym_y)
        b.reference("src/cycle/b.ts", sym_x)
        from scip_cli.analyze.graph import fetch_file_edges

        edges = fetch_file_edges(b.finish())
        assert find_longer_cycles(edges, max_depth=8, limit=10) == []
