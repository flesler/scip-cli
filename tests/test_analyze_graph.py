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


class TestCycleTypeFiltering:
    def test_fetch_edges_skips_type_and_interface_symbols(self):
        from scip_cli.analyze.graph import fetch_file_edges

        b = AnalyzeDbBuilder()
        t_a = b.define_type("src/types/a.ts", "AType")
        t_b = b.define_type("src/types/b.ts", "BType")
        b.reference("src/types/a.ts", t_b)
        b.reference("src/types/b.ts", t_a)
        edges = fetch_file_edges(b.finish())
        assert edges == []

    def test_fetch_edges_keeps_runtime_symbols(self):
        from scip_cli.analyze.graph import fetch_file_edges

        b = AnalyzeDbBuilder()
        sym_b = b.define("src/runtime/b.ts", "runB")
        sym_a = b.define("src/runtime/a.ts", "runA")
        b.reference("src/runtime/a.ts", sym_b)
        b.reference("src/runtime/b.ts", sym_a)
        edges = fetch_file_edges(b.finish())
        assert ("src/runtime/a.ts", "src/runtime/b.ts") in edges
        assert ("src/runtime/b.ts", "src/runtime/a.ts") in edges

    def test_fetch_edges_skips_module_only_barrel_edges(self):
        from scip_cli.analyze.graph import fetch_file_edges

        b = AnalyzeDbBuilder()
        mod_a = b.define_module("src/barrel/a.ts")
        mod_b = b.define_module("src/barrel/b.ts")
        b.reference("src/barrel/a.ts", mod_b)
        b.reference("src/barrel/b.ts", mod_a)
        edges = fetch_file_edges(b.finish())
        assert edges == []
