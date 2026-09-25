"""Tests for indexing performance tracing."""

from scip_cli.indexing.performance import enabled, flush_summary, metric, note, phase


def test_profiling_disabled_by_default(monkeypatch, capsys):
    monkeypatch.delenv("SCIP_CLI_INDEX_TIMING", raising=False)
    assert enabled() is False
    with phase("test"):
        pass
    assert "INDEX_TIMING" not in capsys.readouterr().err


def test_profiling_emits_phase_and_summary(monkeypatch, capsys):
    monkeypatch.setenv("SCIP_CLI_INDEX_TIMING", "1")
    assert enabled() is True
    with phase("apply_updates"):
        pass
    err = capsys.readouterr().err
    assert "INDEX_TIMING:apply_updates=" in err
    metric("shards_reused", 3)
    note("warm_ok")
    flush_summary()
    summary = capsys.readouterr().err
    assert "INDEX_TIMING:summary" in summary
    assert "shards_reused=3" in summary
    assert "notes=warm_ok" in summary
