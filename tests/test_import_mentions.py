"""Import mention synthesis (role=2) for import analyze checks on scip-typescript indexes."""

from __future__ import annotations

from scip_cli.analyze import file as file_checks
from scip_cli.indexing.import_mentions import synthesize_import_mentions

from .analyze_db import AnalyzeDbBuilder


def test_synthesize_enables_unused_and_single_use_imports(tmp_path):
    (tmp_path / "src/lib").mkdir(parents=True)
    (tmp_path / "src/lib/once.ts").write_text("export function onceFn() {}\n", encoding="utf-8")
    (tmp_path / "src/user.ts").write_text(
        "import { onceFn } from './lib/once.ts';\nexport function run() { onceFn(); }\n",
        encoding="utf-8",
    )
    b = AnalyzeDbBuilder()
    once = b.define("src/lib/once.ts", "onceFn")
    b.define("src/user.ts", "run")
    b.reference("src/user.ts", once)
    conn = b.finish()
    synthesize_import_mentions(conn, tmp_path)
    conn.commit()
    assert any("onceFn" in line for line in file_checks.single_use_imports(conn, "src/user.ts", limit=10))
