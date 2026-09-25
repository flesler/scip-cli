#!/usr/bin/env python3
"""Generate tests/fixtures/incremental-bench (four tsconfig shards; bulk is large).

Regenerate after changing shard layout or file counts:

  python scripts/generate_incremental_bench_fixture.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "incremental-bench"

SMALL_PACKAGES = ("alpha", "beta", "gamma")
SMALL_FILES_PER_PKG = 4
BULK_MODULE_COUNT = 60

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true
  },
  "include": ["src/**/*.ts"]
}
"""


def _write_small_package(name: str) -> None:
    pkg = FIXTURE / "packages" / name
    src = pkg / "src"
    src.mkdir(parents=True, exist_ok=True)
    (pkg / "tsconfig.json").write_text(TSCONFIG + "\n", encoding="utf-8")
    (src / "index.ts").write_text(
        f'export const {name}Root = "{name}";\n',
        encoding="utf-8",
    )
    for index in range(1, SMALL_FILES_PER_PKG):
        stem = f"util{index}"
        body = (
            f'import {{ {name}Root }} from "./index";\n'
            f"export function {name}{index}(): string {{\n"
            f"  return `${{{name}Root}}-{index}`;\n"
            "}\n"
        )
        (src / f"{stem}.ts").write_text(body, encoding="utf-8")


def _write_bulk_package() -> None:
    pkg = FIXTURE / "packages" / "bulk"
    src = pkg / "src"
    modules = src / "modules"
    modules.mkdir(parents=True, exist_ok=True)
    (pkg / "tsconfig.json").write_text(TSCONFIG + "\n", encoding="utf-8")
    (src / "index.ts").write_text(
        'export { bulkSize } from "./meta";\n',
        encoding="utf-8",
    )
    (src / "meta.ts").write_text(
        f"export const bulkSize = {BULK_MODULE_COUNT};\n",
        encoding="utf-8",
    )
    for index in range(BULK_MODULE_COUNT):
        stem = f"module_{index:02d}"
        body = (
            f"export const {stem}_value = {index};\n"
            f"export function {stem}_fn(): number {{\n"
            f"  return {stem}_value;\n"
            "}\n"
        )
        (modules / f"{stem}.ts").write_text(body, encoding="utf-8")


def main() -> None:
    if FIXTURE.is_dir():
        import shutil

        shutil.rmtree(FIXTURE)
    FIXTURE.mkdir(parents=True)
    (FIXTURE / "package.json").write_text(
        '{"name": "incremental-bench", "version": "1.0.0", "private": true}\n',
        encoding="utf-8",
    )
    for name in SMALL_PACKAGES:
        _write_small_package(name)
    _write_bulk_package()
    print(f"Wrote incremental bench fixture to {FIXTURE}")
    print(f"  small shards: {len(SMALL_PACKAGES)} x {SMALL_FILES_PER_PKG} files")
    print(f"  bulk shard: {BULK_MODULE_COUNT + 2} files")


if __name__ == "__main__":
    main()
