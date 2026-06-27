"""Tests for pure functions in scip_cli."""

import sqlite3
import tempfile
from pathlib import Path

from scip_cli.commands.refs import get_exact_refs
from scip_cli.commands.search import is_noisy_symbol, kind_to_display, parse_symbol
from scip_cli.output import format_def_body, format_line_range
from scip_cli.project import detect_language
from scip_cli.queries import resolve_file, resolve_symbol
from scip_cli.source import read_source_lines
from scip_cli.sql import escape_like
from scip_cli.symbols import SymbolKind, extract_leaf_name, infer_kind, kind_sql_clause


class TestDetectLanguage:
    def test_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        assert detect_language(tmp_path) == "typescript"

    def test_tsconfig_only(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        assert detect_language(tmp_path) == "typescript"

    def test_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert detect_language(tmp_path) == "python"

    def test_package_json_over_python(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert detect_language(tmp_path) == "typescript"


class TestExtractLeafName:
    def test_function(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/greet()."
        assert extract_leaf_name(s) == "greet"

    def test_class(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#"
        assert extract_leaf_name(s) == "WidgetOptions"

    def test_variable(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/someVar."
        assert extract_leaf_name(s) == "someVar"

    def test_type_literal_property(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#typeLiteral0:onVerbose."
        assert extract_leaf_name(s) == "onVerbose"

    def test_class_member_property(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#config."
        assert extract_leaf_name(s) == "config"

    def test_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert extract_leaf_name(s) == "damageHero"

    def test_getter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<get>aliveHeroes`()."
        assert extract_leaf_name(s) == "aliveHeroes"

    def test_setter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<set>value`()."
        assert extract_leaf_name(s) == "value"

    def test_constructor(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<constructor>`()."
        assert extract_leaf_name(s) == "<constructor>"


class TestInferKind:
    def test_function(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/greet()."
        assert infer_kind(s) == SymbolKind.FUNCTION

    def test_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert infer_kind(s) == SymbolKind.METHOD

    def test_class(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#"
        assert infer_kind(s) == SymbolKind.CLASS

    def test_variable(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/someVar."
        assert infer_kind(s) == SymbolKind.VARIABLE

    def test_type_literal_property(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#typeLiteral0:onVerbose."
        assert infer_kind(s) == SymbolKind.PROPERTY

    def test_getter(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<get>aliveHeroes`()."
        assert infer_kind(s) == SymbolKind.METHOD

    def test_constructor(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#`<constructor>`()."
        assert infer_kind(s) == SymbolKind.METHOD

    def test_python_method(self):
        s = "scip-python pip mypkg 1.0 src/module.py/MyClass#method()."
        assert infer_kind(s) == SymbolKind.METHOD


class TestKindHelpers:
    def test_kind_to_display_uses_value(self):
        assert kind_to_display(SymbolKind.CLASS) == "class"

    def test_kind_sql_clause_class(self):
        assert "LIKE '%#'" in kind_sql_clause("class")
        assert "NOT LIKE '%().'" in kind_sql_clause(SymbolKind.CLASS)

    def test_kind_sql_clause_function(self):
        clause = kind_sql_clause(SymbolKind.FUNCTION)
        assert "LIKE '%().'" in clause
        assert "NOT LIKE '%#%().'" in clause

    def test_kind_sql_clause_method(self):
        clause = kind_sql_clause("method")
        assert "LIKE '%#%'" in clause
        assert "LIKE '%().'" in clause

    def test_kind_sql_clause_property(self):
        assert "#typeLiteral" in kind_sql_clause(SymbolKind.PROPERTY)

    def test_kind_sql_clause_variable(self):
        clause = kind_sql_clause("variable")
        assert "LIKE '%.'" in clause
        assert "NOT LIKE '%().'" in clause

    def test_kind_sql_clause_unknown_kind(self):
        assert kind_sql_clause(SymbolKind.UNKNOWN) == ""


class TestParseSymbol:
    def test_function(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/greet()."
        path, name = parse_symbol(s)
        assert path == "src/helper.ts"
        assert name == "greet()"

    def test_class(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#"
        path, name = parse_symbol(s)
        assert path == "src/helper.ts"
        assert name == "WidgetOptions#"

    def test_nested_path(self):
        s = "scip-typescript npm sample-app 1.0 src/components/ui/`btn.tsx`/Btn#"
        path, name = parse_symbol(s)
        assert path == "src/components/ui/btn.tsx"
        assert name == "Btn#"

    def test_no_backtick(self):
        assert parse_symbol("no-backticks-here") == ("?", "?")

    def test_python_method(self):
        s = "scip-python pip mypackage 1.0 src/module.py/MyClass#method()."
        path, name = parse_symbol(s)
        assert path == "src/module.py"
        assert name == "MyClass#method()."

    def test_python_function(self):
        s = "scip-python pip mypackage 1.0 src/utils.py/helper()."
        path, name = parse_symbol(s)
        assert path == "src/utils.py"
        assert name == "helper()."


class TestIsNoisySymbol:
    def test_file_level(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/"
        assert is_noisy_symbol(s) is True

    def test_type_literal_property(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#typeLiteral0:onVerbose."
        assert is_noisy_symbol(s) is False

    def test_function_parameter(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/greet().(err)"
        assert is_noisy_symbol(s) is True

    def test_normal_function(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/greet()."
        assert is_noisy_symbol(s) is False

    def test_normal_class(self):
        s = "scip-typescript npm sample-app 1.0 src/`helper.ts`/WidgetOptions#"
        assert is_noisy_symbol(s) is False

    def test_normal_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert is_noisy_symbol(s) is False

    def test_python_method_not_noisy(self):
        s = "scip-python pip mypkg 1.0 src/module.py/MyClass#method()."
        assert is_noisy_symbol(s) is False


class TestEscapeLike:
    def test_escape_percent(self):
        assert escape_like("foo%bar") == "foo\\%bar"

    def test_escape_underscore(self):
        assert escape_like("foo_bar") == "foo\\_bar"

    def test_escape_both(self):
        assert escape_like("foo%_bar") == "foo\\%\\_bar"

    def test_no_escape_needed(self):
        assert escape_like("foobar") == "foobar"


class TestResolveSymbol:
    def test_exact_match_function(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc"),
        )
        conn.commit()

        results = resolve_symbol(conn, "myFunc")
        assert len(results) == 1
        assert results[0][2] == "myFunc"
        conn.close()

    def test_exact_match_class(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scip-typescript npm test 1.0 src/`test.ts`/MyClass#", "MyClass"),
        )
        conn.commit()

        results = resolve_symbol(conn, "MyClass")
        assert len(results) == 1
        assert results[0][2] == "MyClass"
        conn.close()

    def test_no_match(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.commit()

        results = resolve_symbol(conn, "nonexistent")
        assert len(results) == 0
        conn.close()

    def test_kind_filter(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc"),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scip-typescript npm test 1.0 src/`test.ts`/MyClass#", "MyClass"),
        )
        conn.commit()

        results = resolve_symbol(conn, "my", kind_filter="function")
        assert len(results) == 1
        assert results[0][2] == "myFunc"
        conn.close()

    def test_kind_filter_no_match(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc"),
        )
        conn.commit()

        results = resolve_symbol(conn, "myFunc", kind_filter="class")
        assert len(results) == 0
        conn.close()

    def test_qualified_class_method(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            (
                "scip-typescript npm test 1.0 src/`widget.ts`/Widget#run().",
                "onModuleInit",
            ),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            (
                "scip-typescript npm test 1.0 src/`other.module.ts`/OtherModule#onModuleInit().",
                "onModuleInit",
            ),
        )
        conn.commit()

        results = resolve_symbol(conn, "Widget.run")
        assert len(results) == 1
        assert "Widget#run" in results[0][1]
        conn.close()

    def test_qualified_excludes_parameters(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            (
                "scip-typescript npm test 1.0 src/`x.tsx`/Foo#setBar().",
                "setBar",
            ),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            (
                "scip-typescript npm test 1.0 src/`x.tsx`/Foo#setBar().(eventIds)",
                "eventIds",
            ),
        )
        conn.commit()

        results = resolve_symbol(conn, "Foo.setBar")
        assert len(results) == 1
        assert ").(" not in results[0][1]
        conn.close()


class TestFormatDefBody:
    def test_truncates_long_definitions(self):
        lines = [f"line {i}\n" for i in range(200)]
        body, truncated, shown_start, shown_end = format_def_body(lines, start_line=10, end_line=209, max_lines=80)
        assert truncated is True
        assert body.count("\n") == 79
        assert shown_start == 10
        assert shown_end == 89

    def test_unlimited_when_max_lines_zero(self):
        lines = ["a\n", "b\n", "c\n"]
        body, truncated, _, shown_end = format_def_body(lines, start_line=0, end_line=2, max_lines=0, max_chars=0)
        assert truncated is False
        assert body == "a\nb\nc"
        assert shown_end == 2

    def test_char_cap_truncates(self):
        lines = ["x" * 100 + "\n" for _ in range(10)]
        body, truncated, _, _ = format_def_body(lines, start_line=0, end_line=9, max_lines=0, max_chars=250)
        assert truncated is True
        assert body.endswith("...")


class TestResolveFile:
    def test_exact_match(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT
            )
        """)
        conn.execute("INSERT INTO documents (relative_path) VALUES (?)", ("src/test.ts",))
        conn.commit()

        results = resolve_file(conn, "src/test.ts")
        assert len(results) == 1
        assert results[0] == "src/test.ts"
        conn.close()

    def test_pattern_match(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT
            )
        """)
        conn.execute("INSERT INTO documents (relative_path) VALUES (?)", ("src/test.ts",))
        conn.execute("INSERT INTO documents (relative_path) VALUES (?)", ("src/other.ts",))
        conn.commit()

        results = resolve_file(conn, "test")
        assert len(results) == 1
        assert results[0] == "src/test.ts"
        conn.close()

    def test_bare_filename_prefers_non_test(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT
            )
        """)
        conn.execute(
            "INSERT INTO documents (relative_path) VALUES (?)",
            ("pkg/src/helper.ts",),
        )
        conn.execute(
            "INSERT INTO documents (relative_path) VALUES (?)",
            ("pkg/src/helper.test.ts",),
        )
        conn.commit()

        results = resolve_file(conn, "helper.ts")
        assert len(results) >= 1
        assert results[0] == "pkg/src/helper.ts"
        conn.close()

    def test_no_match(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT
            )
        """)
        conn.commit()

        results = resolve_file(conn, "nonexistent.ts")
        assert len(results) == 0
        conn.close()


class TestReadSourceLines:
    def test_read_all_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "test.ts"
            test_file.write_text("line1\nline2\nline3\n")

            lines = read_source_lines(project_root, "test.ts")
            assert len(lines) == 3
            assert lines[0] == "line1\n"
            assert lines[1] == "line2\n"
            assert lines[2] == "line3\n"

    def test_read_line_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "test.ts"
            test_file.write_text("line1\nline2\nline3\nline4\n")

            lines = read_source_lines(project_root, "test.ts", 1, 2)
            assert len(lines) == 2
            assert lines[0] == "line2\n"
            assert lines[1] == "line3\n"

    def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_file = project_root / "test.ts"
            test_file.write_text("content\n")

            # Try to escape project root
            lines = read_source_lines(project_root, "../outside.ts")
            assert lines is None

    def test_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            lines = read_source_lines(project_root, "nonexistent.ts")
            assert lines is None


class TestFormatLineRange:
    def test_both_defined(self):
        assert format_line_range(0, 10) == "1:11"
        assert format_line_range(9, 15) == "10:16"

    def test_only_start_defined(self):
        assert format_line_range(5, None) == "6:?"

    def test_neither_defined(self):
        assert format_line_range(None, None) == "??"
        assert format_line_range(None, 10) == "??"

    def test_custom_separator(self):
        assert format_line_range(0, 10, sep="-") == "1-11"
        assert format_line_range(None, None, sep="_") == "??"


class TestGetExactRefs:
    """Tests for get_exact_refs function in refs command."""

    def _create_test_db(self):
        """Create a test database with minimal schema."""
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                display_name TEXT
            );
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT
            );
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER,
                start_line INTEGER,
                end_line INTEGER
            );
            CREATE TABLE mentions (
                id INTEGER PRIMARY KEY,
                symbol_id INTEGER,
                chunk_id INTEGER,
                role INTEGER
            );
        """)
        return conn

    def test_no_symbol(self):
        """Test when symbol doesn't exist."""
        conn = self._create_test_db()
        refs = get_exact_refs(conn, 999, "/tmp", 10)
        assert refs == []
        conn.close()

    def test_no_mentions(self):
        """Test when symbol exists but has no references."""
        conn = self._create_test_db()
        conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (1, "scip-python test/test `test.py`/foo().", "foo"),
        )
        conn.commit()
        refs = get_exact_refs(conn, 1, "/tmp", 10)
        assert refs == []
        conn.close()

    def test_single_reference(self):
        """Test with a single reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = self._create_test_db()
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo():\n    pass\n\nfoo()\n")

            # Insert data
            conn.execute(
                "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                (1, "scip-python test/test `test.py`/foo().", "foo"),
            )
            conn.execute("INSERT INTO documents (id, relative_path) VALUES (?, ?)", (1, "test.py"))
            conn.execute("INSERT INTO chunks (id, document_id, start_line, end_line) VALUES (?, ?, ?, ?)", (1, 1, 3, 3))
            conn.execute("INSERT INTO mentions (symbol_id, chunk_id, role) VALUES (?, ?, ?)", (1, 1, 0))
            conn.commit()

            refs = get_exact_refs(conn, 1, tmpdir, 10)
            assert len(refs) == 1
            assert refs[0] == ("test.py", 4)  # Line 4 (1-indexed)
            conn.close()

    def test_max_refs_limit(self):
        """Test that max_refs limit is respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = self._create_test_db()
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("foo()\nfoo()\nfoo()\n")

            # Insert symbol
            conn.execute(
                "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                (1, "scip-python test/test `test.py`/foo().", "foo"),
            )
            conn.execute("INSERT INTO documents (id, relative_path) VALUES (?, ?)", (1, "test.py"))
            # Insert 3 mentions
            for i in range(3):
                conn.execute(
                    "INSERT INTO chunks (id, document_id, start_line, end_line) VALUES (?, ?, ?, ?)", (i + 1, 1, i, i)
                )
                conn.execute("INSERT INTO mentions (symbol_id, chunk_id, role) VALUES (?, ?, ?)", (1, i + 1, 0))
            conn.commit()

            # Limit to 2 refs
            refs = get_exact_refs(conn, 1, tmpdir, 2)
            assert len(refs) == 2
            conn.close()
