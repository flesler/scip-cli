"""Tests for multi-symbol code and refs."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scip_cli.commands import code, refs
from scip_cli.output import maybe_print_symbol_header, symbol_output_label


class TestSymbolOutputLabel:
    def test_single_match_uses_query_name(self):
        sym = "scip-typescript npm test 1.0 src/`a.ts`/greet()."
        assert symbol_output_label("greet", sym, 1) == "greet"

    def test_ambiguous_uses_path(self):
        sym = "scip-typescript npm test 1.0 src/`a.ts`/Foo#"
        assert symbol_output_label("Foo", sym, 2) == "Foo (src/a.ts)"


class TestMaybePrintSymbolHeader:
    def test_hidden_for_single(self, capsys):
        maybe_print_symbol_header("greet", show_header=False)
        assert capsys.readouterr().out == ""

    def test_shown_for_multi(self, capsys):
        maybe_print_symbol_header("greet", show_header=True)
        assert capsys.readouterr().out.strip() == "greet"


class TestMultiSymbolCode:
    def test_single_symbol_no_header(self, capsys):
        args = SimpleNamespace(
            symbol=["greet"],
            kind=None,
            limit=10,
            path=None,
            snippet=False,
            full=False,
            offset=0,
            line_numbers=False,
            max_lines=None,
        )
        with (
            patch("scip_cli.commands.code.setup", return_value=(MagicMock(), Path("/proj"))),
            patch("scip_cli.commands.code.path_scope_from_args", return_value=None),
            patch(
                "scip_cli.commands.code.resolve_symbol",
                return_value=[(1, "sym", "greet")],
            ),
            patch(
                "scip_cli.commands.code.resolve_def_location",
                return_value=("src/helper.ts", 4, 6),
            ),
            patch(
                "scip_cli.commands.code.read_source_lines",
                return_value=["export function greet() {\n", "  return 1;\n", "}\n"],
            ),
        ):
            code.main(args)

        out = capsys.readouterr().out.strip().splitlines()
        assert out[0].startswith("src/helper.ts:")
        assert out[0] != "greet"

    def test_multiple_symbols_with_headers(self, capsys):
        args = SimpleNamespace(
            symbol=["greet", "Widget.run"],
            kind=None,
            limit=10,
            path=None,
            snippet=True,
            full=False,
            offset=0,
            line_numbers=False,
            max_lines=None,
        )

        def fake_resolve(_db, name, *_args, **_kwargs):
            if name == "greet":
                return [(1, "sym-greet", "greet")]
            if name == "Widget.run":
                return [(2, "sym-run", "run")]
            return []

        with (
            patch("scip_cli.commands.code.setup", return_value=(MagicMock(), Path("/proj"))),
            patch("scip_cli.commands.code.path_scope_from_args", return_value=None),
            patch("scip_cli.commands.code.resolve_symbol", side_effect=fake_resolve),
            patch(
                "scip_cli.commands.code.resolve_def_location",
                side_effect=lambda _db, _root, sym_id, _sym: {
                    1: ("src/helper.ts", 4, 6),
                    2: ("src/widget.ts", 3, 5),
                }[sym_id],
            ),
            patch(
                "scip_cli.commands.code.read_source_lines",
                side_effect=lambda _root, path, start, _end: {
                    ("src/helper.ts", 4): ["export function greet() {\n"],
                    ("src/widget.ts", 3): ["  run() {\n"],
                }[(path, start)],
            ),
        ):
            code.main(args)

        lines = capsys.readouterr().out.strip().splitlines()
        assert lines[0] == "greet"
        assert lines[1].startswith("src/helper.ts:")
        assert lines[2] == "Widget.run"
        assert lines[3].startswith("src/widget.ts:")

    def test_partial_miss_still_prints(self, capsys):
        args = SimpleNamespace(
            symbol=["greet", "missing"],
            kind=None,
            limit=10,
            path=None,
            snippet=True,
            full=False,
            offset=0,
            line_numbers=False,
            max_lines=None,
        )

        def fake_resolve(_db, name, *_args, **_kwargs):
            if name == "greet":
                return [(1, "sym-greet", "greet")]
            return []

        with (
            patch("scip_cli.commands.code.setup", return_value=(MagicMock(), Path("/proj"))),
            patch("scip_cli.commands.code.path_scope_from_args", return_value=None),
            patch("scip_cli.commands.code.resolve_symbol", side_effect=fake_resolve),
            patch(
                "scip_cli.commands.code.resolve_def_location",
                return_value=("src/helper.ts", 4, 6),
            ),
            patch(
                "scip_cli.commands.code.read_source_lines",
                return_value=["export function greet() {\n"],
            ),
        ):
            code.main(args)

        captured = capsys.readouterr()
        assert "missing" in captured.err
        assert captured.out.startswith("src/helper.ts:")


class TestMultiSymbolRefs:
    def test_multiple_symbols_with_headers_on_stdout(self, capsys):
        args = SimpleNamespace(symbol=["greet", "Widget.run"], limit=10, path=None, paths_only=False)

        def fake_resolve(_db, name, *_args, **_kwargs):
            if name == "greet":
                return [(1, "sym-greet", "greet")]
            if name == "Widget.run":
                return [(2, "sym-run", "run")]
            return []

        with (
            patch("scip_cli.commands.refs.setup", return_value=(MagicMock(), Path("/proj"))),
            patch("scip_cli.commands.refs.path_scope_from_args", return_value=None),
            patch("scip_cli.commands.refs.resolve_symbol", side_effect=fake_resolve),
            patch(
                "scip_cli.commands.refs.get_exact_refs",
                side_effect=lambda _db, sym_id, *_args, **_kwargs: {
                    1: [("src/consumer.ts", 10)],
                    2: [("src/widget.ts", 20)],
                }[sym_id],
            ),
        ):
            refs.main(args)

        captured = capsys.readouterr()
        assert captured.err == ""
        lines = captured.out.strip().splitlines()
        assert lines == ["greet", "src/consumer.ts:10", "Widget.run", "src/widget.ts:20"]

    def test_paths_only_no_headers(self, capsys):
        args = SimpleNamespace(symbol=["greet", "Widget.run"], limit=10, path=None, paths_only=True)

        def fake_resolve(_db, name, *_args, **_kwargs):
            if name == "greet":
                return [(1, "sym-greet", "greet")]
            if name == "Widget.run":
                return [(2, "sym-run", "run")]
            return []

        with (
            patch("scip_cli.commands.refs.setup", return_value=(MagicMock(), Path("/proj"))),
            patch("scip_cli.commands.refs.path_scope_from_args", return_value=None),
            patch("scip_cli.commands.refs.resolve_symbol", side_effect=fake_resolve),
            patch(
                "scip_cli.commands.refs.get_exact_refs",
                side_effect=lambda _db, sym_id, *_args, **_kwargs: {
                    1: [("src/consumer.ts", 10)],
                    2: [("src/widget.ts", 20)],
                }[sym_id],
            ),
        ):
            refs.main(args)

        assert capsys.readouterr().out.strip().splitlines() == ["src/consumer.ts", "src/widget.ts"]
