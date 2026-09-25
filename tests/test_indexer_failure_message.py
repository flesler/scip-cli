"""Tests for indexer subprocess failure messaging."""

import subprocess

from scip_cli.indexing.runners import indexer_failure_message


class TestIndexerFailureMessage:
    def test_prefers_stderr(self):
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="stdout detail",
            stderr="stderr detail",
        )
        assert indexer_failure_message(result) == "stderr detail"

    def test_falls_back_to_stdout_when_stderr_empty(self):
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="error: no files got indexed",
            stderr="",
        )
        assert indexer_failure_message(result) == "error: no files got indexed"

    def test_default_when_both_streams_empty(self):
        result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        assert indexer_failure_message(result) == "indexing failed"
