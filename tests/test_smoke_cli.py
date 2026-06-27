"""CLI integration smoke tests against the bundled sample TypeScript project."""

import sqlite3
import subprocess

import pytest

HELPER_FILE = "src/helper.ts"
FN_GREET = "greet"
CLASS_WIDGET = "Widget"


def _run(cli: str, root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [cli, *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
class TestSmokeCLI:
    def test_version(self, smoke_cli, indexed_sample_project):
        result = _run(smoke_cli, indexed_sample_project, "--version")
        assert result.returncode == 0
        assert "scip-cli" in result.stdout

    def test_skill_outputs_markdown(self, smoke_cli, indexed_sample_project):
        result = _run(smoke_cli, indexed_sample_project, "skill")
        assert result.returncode == 0
        assert "Quick Decision Guide" in result.stdout

    def test_search_returns_results(self, smoke_cli, indexed_sample_project):
        result = _run(smoke_cli, indexed_sample_project, "search", "greet", "--limit", "3")
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_symbols_by_path(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "symbols",
            HELPER_FILE,
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_symbols_by_bare_filename(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "symbols",
            "helper.ts",
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_rdeps_with_importers(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "rdeps",
            HELPER_FILE,
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert "consumer.ts" in result.stdout or "widget.ts" in result.stdout

    def test_refs_paths_only(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "refs",
            FN_GREET,
            "--paths-only",
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert ".ts" in result.stdout

    def test_search_paths_pipe_symbols(self, smoke_cli, indexed_sample_project):
        paths = _run(
            smoke_cli,
            indexed_sample_project,
            "search",
            FN_GREET,
            "--paths-only",
            "--limit",
            "3",
        )
        assert paths.returncode == 0
        first = paths.stdout.strip().splitlines()[0]
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "symbols",
            first,
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_code_function(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "code",
            FN_GREET,
            "--limit",
            "1",
        )
        assert result.returncode == 0
        assert HELPER_FILE in result.stdout
        assert "function greet" in result.stdout

    def test_members_class(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "members",
            CLASS_WIDGET,
            "--names-only",
            "--limit",
            "5",
        )
        assert result.returncode == 0
        assert "run" in result.stdout

    def test_missing_symbol_exits_nonzero(self, smoke_cli, indexed_sample_project):
        result = _run(
            smoke_cli,
            indexed_sample_project,
            "code",
            "__scip_cli_missing_symbol_xyz__",
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_cache_db_exists_and_queryable(self, indexed_sample_project):
        from scip_cli.cache import get_cache_dir

        cache = get_cache_dir(indexed_sample_project) / "index.db"
        assert cache.is_file()
        conn = sqlite3.connect(cache)
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        symbols = conn.execute("SELECT COUNT(*) FROM global_symbols").fetchone()[0]
        conn.close()
        assert docs >= 3
        assert symbols >= 3
