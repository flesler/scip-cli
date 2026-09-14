"""Unit tests for analyze live-index heuristics."""

from scip_cli.analyze.live import is_low_signal_dead_file

from .analyze_db import AnalyzeDbBuilder


class TestAnalyzeLiveHeuristics:
    def test_is_low_signal_dead_file(self):
        b = AnalyzeDbBuilder()
        doc_id, _chunk_id = b.add_file("src/ui/widget.ts")
        b.define_module("src/ui/widget.ts")
        db = b.finish()
        assert is_low_signal_dead_file(db, doc_id)

        typed = AnalyzeDbBuilder()
        typed.define_module("src/ui/button.ts")
        typed.define_type("src/ui/button.ts", "ButtonProps")
        typed_db = typed.finish()
        typed_doc = typed_db.execute(
            "SELECT id FROM documents WHERE relative_path = ?", ("src/ui/button.ts",)
        ).fetchone()[0]
        assert is_low_signal_dead_file(typed_db, typed_doc)

        mixed = AnalyzeDbBuilder()
        mixed.define_module("src/lib/api.ts")
        mixed.define("src/lib/api.ts", "register")
        mixed_db = mixed.finish()
        mixed_doc = mixed_db.execute(
            "SELECT id FROM documents WHERE relative_path = ?", ("src/lib/api.ts",)
        ).fetchone()[0]
        assert not is_low_signal_dead_file(mixed_db, mixed_doc)

    def test_live_for_reuses_one_index_during_a_pass(self):
        from scip_cli.analyze.live import bind_live, live_for, reset_live

        db = AnalyzeDbBuilder().finish()
        token = bind_live(db)
        try:
            assert live_for(db) is live_for(db)
        finally:
            reset_live(token)

    def test_nested_bind_live_reuses_same_index(self):
        from scip_cli.analyze.live import bind_live, live_for, reset_live

        db = AnalyzeDbBuilder().finish()
        outer = bind_live(db)
        try:
            first = live_for(db)
            inner = bind_live(db)
            try:
                assert live_for(db) is first
            finally:
                reset_live(inner)
            assert live_for(db) is first
        finally:
            reset_live(outer)
        assert live_for(db) is not first

    def test_live_for_does_not_reuse_index_for_a_different_db(self):
        from scip_cli.analyze.live import bind_live, live_for, reset_live

        db = AnalyzeDbBuilder().finish()
        other = AnalyzeDbBuilder().finish()
        token = bind_live(db)
        try:
            bound = live_for(db)
            assert live_for(other) is not bound
        finally:
            reset_live(token)
