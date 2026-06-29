"""Unit tests for indexer fallback logic."""

from unittest.mock import MagicMock, patch

import pytest

from scip_cli.indexing import (
    _install_via_go_install,
    _install_via_npx,
    _install_via_rustup,
    _run_indexer_command,
    run_indexer_with_fallback,
)


class TestRunIndexerCommand:
    """Tests for _run_indexer_command."""

    def test_success(self):
        """Binary found and succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result) as mock_run:
            success, result = _run_indexer_command("scip-typescript", ["index"], "/tmp", {})
            assert success is True
            assert result is mock_result
            mock_run.assert_called_once_with(["scip-typescript", "index"], "/tmp", env={})

    def test_not_found_in_stderr(self):
        """Binary found but stderr contains 'not found'."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "scip-typescript: not found"
        with patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result):
            success, result = _run_indexer_command("scip-typescript", ["index"], "/tmp", {})
            assert success is False
            assert result is mock_result

    def test_command_failed(self):
        """Binary found but command failed (not 'not found')."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some other error"
        with patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result):
            success, result = _run_indexer_command("scip-typescript", ["index"], "/tmp", {})
            assert success is True  # Command ran, just failed
            assert result is mock_result

    def test_file_not_found(self):
        """Binary not on PATH."""
        with patch("scip_cli.indexing.runners._run_subprocess", side_effect=FileNotFoundError):
            success, result = _run_indexer_command("scip-typescript", ["index"], "/tmp", {})
            assert success is False
            assert result is None


class TestInstallViaNpx:
    """Tests for _install_via_npx."""

    def test_with_version(self):
        """npx with version pinning."""
        mock_result = MagicMock()
        with patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result) as mock_run:
            result = _install_via_npx("@sourcegraph/scip-typescript", "0.4.0", ["index"], "/tmp", {})
            assert result is mock_result
            mock_run.assert_called_once_with(
                ["npx", "-y", "@sourcegraph/scip-typescript@~0.4.0", "index"],
                "/tmp",
                env={},
            )

    def test_without_version(self):
        """npx without version pinning."""
        mock_result = MagicMock()
        with patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result) as mock_run:
            result = _install_via_npx("@sourcegraph/scip-python", None, ["index"], "/tmp", {})
            assert result is mock_result
            mock_run.assert_called_once_with(
                ["npx", "-y", "@sourcegraph/scip-python", "index"],
                "/tmp",
                env={},
            )


class TestInstallViaGoInstall:
    """Tests for _install_via_go_install."""

    def test_already_installed_in_go_bin(self):
        """Binary already in ~/go/bin."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_result) as mock_run,
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = _install_via_go_install(
                "github.com/scip-code/scip-go/cmd/scip-go",
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                {},
            )
            assert result is mock_result
            # Should run from ~/go/bin without installing
            call_args = mock_run.call_args
            assert "scip-go" in call_args[0][0][0]
            assert "--output" in call_args[0][0]

    def test_needs_install(self):
        """Binary not in ~/go/bin, needs install at latest."""
        mock_install_result = MagicMock()
        mock_install_result.returncode = 0
        mock_run_result = MagicMock()
        mock_run_result.returncode = 0

        with (
            patch("scip_cli.indexing.runners._run_subprocess") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
        ):
            mock_run.side_effect = [mock_install_result, mock_run_result]
            result = _install_via_go_install(
                "github.com/scip-code/scip-go/cmd/scip-go",
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                {},
            )
            assert result is mock_run_result
            assert mock_run.call_count == 2
            install_cmd = mock_run.call_args_list[0][0][0]
            assert install_cmd[0] == "go"
            assert install_cmd[1] == "install"
            assert install_cmd[2].endswith("@latest")

    def test_needs_install_pinned_version(self):
        """Optional version pins go install when passed explicitly."""
        mock_install_result = MagicMock()
        mock_install_result.returncode = 0
        mock_run_result = MagicMock()
        mock_run_result.returncode = 0

        with (
            patch("scip_cli.indexing.runners._run_subprocess") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
        ):
            mock_run.side_effect = [mock_install_result, mock_run_result]
            result = _install_via_go_install(
                "github.com/scip-code/scip-go/cmd/scip-go",
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                {},
                version="0.2.7",
            )
            assert result is mock_run_result
            install_cmd = mock_run.call_args_list[0][0][0]
            assert install_cmd[2].endswith("@v0.2.7")

    def test_install_fails(self):
        """go install fails."""
        mock_install_result = MagicMock()
        mock_install_result.returncode = 1
        mock_install_result.stderr = "go: command not found"

        with (
            patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_install_result),
            patch("pathlib.Path.exists", return_value=False),
            pytest.raises(RuntimeError, match="Failed to install scip-go"),
        ):
            _install_via_go_install(
                "github.com/scip-code/scip-go/cmd/scip-go",
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                {},
            )


class TestInstallViaRustup:
    """Tests for _install_via_rustup."""

    def test_success(self):
        """rustup component add succeeds."""
        mock_install_result = MagicMock()
        mock_install_result.returncode = 0
        mock_run_result = MagicMock()
        mock_run_result.returncode = 0

        with patch("scip_cli.indexing.runners._run_subprocess") as mock_run:
            mock_run.side_effect = [mock_install_result, mock_run_result]
            result = _install_via_rustup(
                "rust-analyzer",
                "rust-analyzer",
                ["scip", "--output", "index.scip"],
                "/tmp",
                {},
            )
            assert result is mock_run_result
            assert mock_run.call_count == 2
            # First call: rustup component add
            assert mock_run.call_args_list[0][0][0][0] == "rustup"
            assert mock_run.call_args_list[0][0][0][1] == "component"
            assert mock_run.call_args_list[0][0][0][2] == "add"
            # Second call: run rust-analyzer
            assert mock_run.call_args_list[1][0][0][0] == "rust-analyzer"

    def test_install_fails(self):
        """rustup component add fails."""
        mock_install_result = MagicMock()
        mock_install_result.returncode = 1
        mock_install_result.stderr = "rustup: command not found"

        with (
            patch("scip_cli.indexing.runners._run_subprocess", return_value=mock_install_result),
            pytest.raises(RuntimeError, match="Failed to install rust-analyzer"),
        ):
            _install_via_rustup(
                "rust-analyzer",
                "rust-analyzer",
                ["scip", "--output", "index.scip"],
                "/tmp",
                {},
            )


class TestRunIndexerWithFallback:
    """Tests for run_indexer_with_fallback."""

    def test_binary_found(self):
        """Binary on PATH, no fallback needed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("scip_cli.indexing.runners._run_indexer_command", return_value=(True, mock_result)):
            result = run_indexer_with_fallback("scip-typescript", ["index"], "/tmp", env={})
            assert result is mock_result

    def test_npx_fallback(self):
        """Binary not found, falls back to npx."""
        mock_result = MagicMock()
        with (
            patch("scip_cli.indexing.runners._run_indexer_command", return_value=(False, None)),
            patch("scip_cli.indexing.runners._install_via_npx", return_value=mock_result) as mock_npx,
        ):
            result = run_indexer_with_fallback(
                "scip-typescript",
                ["index"],
                "/tmp",
                env={},
                npx_package="@sourcegraph/scip-typescript",
                npx_version="0.4.0",
            )
            assert result is mock_result
            mock_npx.assert_called_once()

    def test_go_install_fallback(self):
        """Binary not found, falls back to go install."""
        mock_result = MagicMock()
        with (
            patch("scip_cli.indexing.runners._run_indexer_command", return_value=(False, None)),
            patch("scip_cli.indexing.runners._install_via_go_install", return_value=mock_result) as mock_go,
        ):
            result = run_indexer_with_fallback(
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                env={},
                go_package="github.com/scip-code/scip-go/cmd/scip-go",
            )
            assert result is mock_result
            mock_go.assert_called_once()

    def test_rustup_fallback(self):
        """Binary not found, falls back to rustup."""
        mock_result = MagicMock()
        with (
            patch("scip_cli.indexing.runners._run_indexer_command", return_value=(False, None)),
            patch("scip_cli.indexing.runners._install_via_rustup", return_value=mock_result) as mock_rustup,
        ):
            result = run_indexer_with_fallback(
                "rust-analyzer",
                ["scip", "--output", "index.scip"],
                "/tmp",
                env={},
                rustup_component="rust-analyzer",
            )
            assert result is mock_result
            mock_rustup.assert_called_once()

    def test_no_fallback_available(self):
        """Binary not found, no fallback specified."""
        mock_error = MagicMock()
        with patch("scip_cli.indexing.runners._run_indexer_command", return_value=(False, mock_error)):
            result = run_indexer_with_fallback("scip-typescript", ["index"], "/tmp", env={})
            assert result is mock_error

    def test_fallback_priority(self):
        """Multiple fallbacks specified, go_package takes priority."""
        mock_result = MagicMock()
        with (
            patch("scip_cli.indexing.runners._run_indexer_command", return_value=(False, None)),
            patch("scip_cli.indexing.runners._install_via_go_install", return_value=mock_result) as mock_go,
            patch("scip_cli.indexing.runners._install_via_npx") as mock_npx,
        ):
            result = run_indexer_with_fallback(
                "scip-go",
                ["--output", "index.scip"],
                "/tmp",
                env={},
                npx_package="@sourcegraph/scip-go",
                go_package="github.com/scip-code/scip-go/cmd/scip-go",
            )
            assert result is mock_result
            mock_go.assert_called_once()
            mock_npx.assert_not_called()
