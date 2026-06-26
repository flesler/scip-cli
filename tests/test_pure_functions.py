"""Tests for pure functions in scip_cli."""
import pytest
import sqlite3
import tempfile
from pathlib import Path
from scip_cli.lib import extract_leaf_name, infer_kind, escape_like, resolve_symbol, resolve_file, read_source_lines, detect_language, SymbolKind
from scip_cli.commands.search import parse_symbol, is_noisy_symbol


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
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert extract_leaf_name(s) == "useDictation"

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        assert extract_leaf_name(s) == "UseDictationOptions"

    def test_variable(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/someVar."
        assert extract_leaf_name(s) == "someVar"

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
        assert extract_leaf_name(s) == "onFallbackToRecording"

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
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert infer_kind(s) == SymbolKind.FUNCTION

    def test_method(self):
        s = "scip-typescript npm battler 1.0.0 src/`GameEngine.ts`/GameEngine#damageHero()."
        assert infer_kind(s) == SymbolKind.METHOD

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        assert infer_kind(s) == SymbolKind.CLASS

    def test_variable(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/someVar."
        assert infer_kind(s) == SymbolKind.VARIABLE

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
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


class TestParseSymbol:
    def test_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        path, name = parse_symbol(s)
        assert path == "src/hooks/useDictation.ts"
        assert name == "useDictation()"

    def test_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
        path, name = parse_symbol(s)
        assert path == "src/hooks/useDictation.ts"
        assert name == "UseDictationOptions#"

    def test_nested_path(self):
        s = "scip-typescript npm rovetia-app 1.2 src/components/ui/`btn.tsx`/Btn#"
        path, name = parse_symbol(s)
        assert path == "src/components/ui/btn.tsx"
        assert name == "Btn#"

    def test_no_backtick(self):
        assert parse_symbol("no-backticks-here") == ('?', '?')

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
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/"
        assert is_noisy_symbol(s) is True

    def test_type_literal_property(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#typeLiteral0:onFallbackToRecording."
        assert is_noisy_symbol(s) is True

    def test_function_parameter(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/isNotSupportedError().(err)"
        assert is_noisy_symbol(s) is True

    def test_normal_function(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation()."
        assert is_noisy_symbol(s) is False

    def test_normal_class(self):
        s = "scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/UseDictationOptions#"
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
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE global_symbols (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    display_name TEXT
                )
            """)
            conn.execute(
                "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
                ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc")
            )
            conn.commit()

            results = resolve_symbol(conn, "myFunc")
            assert len(results) == 1
            assert results[0][2] == "myFunc"
            conn.close()

    def test_exact_match_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE global_symbols (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    display_name TEXT
                )
            """)
            conn.execute(
                "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
                ("scip-typescript npm test 1.0 src/`test.ts`/MyClass#", "MyClass")
            )
            conn.commit()

            results = resolve_symbol(conn, "MyClass")
            assert len(results) == 1
            assert results[0][2] == "MyClass"
            conn.close()

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
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
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE global_symbols (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    display_name TEXT
                )
            """)
            conn.execute(
                "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
                ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc")
            )
            conn.execute(
                "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
                ("scip-typescript npm test 1.0 src/`test.ts`/MyClass#", "MyClass")
            )
            conn.commit()

            results = resolve_symbol(conn, "my", kind_filter="function")
            assert len(results) == 1
            assert results[0][2] == "myFunc"
            conn.close()

    def test_kind_filter_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE global_symbols (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT,
                    display_name TEXT
                )
            """)
            conn.execute(
                "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
                ("scip-typescript npm test 1.0 src/`test.ts`/myFunc().", "myFunc")
            )
            conn.commit()

            results = resolve_symbol(conn, "myFunc", kind_filter="class")
            assert len(results) == 0
            conn.close()


class TestResolveFile:
    def test_exact_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY,
                    relative_path TEXT
                )
            """)
            conn.execute(
                "INSERT INTO documents (relative_path) VALUES (?)",
                ("src/test.ts",)
            )
            conn.commit()

            results = resolve_file(conn, "src/test.ts")
            assert len(results) == 1
            assert results[0] == "src/test.ts"
            conn.close()

    def test_pattern_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY,
                    relative_path TEXT
                )
            """)
            conn.execute(
                "INSERT INTO documents (relative_path) VALUES (?)",
                ("src/test.ts",)
            )
            conn.execute(
                "INSERT INTO documents (relative_path) VALUES (?)",
                ("src/other.ts",)
            )
            conn.commit()

            results = resolve_file(conn, "test")
            assert len(results) == 1
            assert results[0] == "src/test.ts"
            conn.close()

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(db_path)
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
