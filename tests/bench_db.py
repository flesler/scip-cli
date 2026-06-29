"""Scaled :memory: DB generator for query benchmarks.

Creates a realistic dependency graph (~1000 files, ~15K symbols, ~100K mentions)
to expose SQL performance differences that the tiny fixture hides.
"""

from __future__ import annotations

import random
import sqlite3

from .analyze_db import ANALYZE_SCHEMA


def scaled_bench_db(seed: int = 42) -> sqlite3.Connection:
    """Generate a deterministic scaled DB for benchmarks.

    Shape:
    - 1000 files across 20 modules
    - ~15 symbols per file (15K total)
    - Hub symbols referenced by 50+ files
    - 5-10 file cycles (2-4 files each)
    - ~10% dead exports (no external refs)
    - ~5% stale types (type symbols with 0 consumers)
    - Dense cross-file references (~100K mentions)
    """
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.executescript(ANALYZE_SCHEMA)

    # Create indexes for realistic query performance
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(relative_path);
        CREATE INDEX IF NOT EXISTS idx_mentions_symbol ON mentions(symbol_id, role);
        CREATE INDEX IF NOT EXISTS idx_mentions_chunk ON mentions(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_der_symbol ON defn_enclosing_ranges(symbol_id);
        CREATE INDEX IF NOT EXISTS idx_der_document ON defn_enclosing_ranges(document_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
    """)

    # Generate 1000 files across 20 modules
    modules = [f"src/module{i:02d}" for i in range(20)]
    files_per_module = 50
    all_files = []
    for module in modules:
        for j in range(files_per_module):
            all_files.append(f"{module}/file{j:03d}.ts")

    # Insert files with chunks
    doc_id = 1
    chunk_id = 1
    file_to_doc = {}
    for file_path in all_files:
        conn.execute(
            "INSERT INTO documents (id, relative_path) VALUES (?, ?)",
            (doc_id, file_path),
        )
        conn.execute(
            "INSERT INTO chunks (id, document_id, start_line, end_line) VALUES (?, ?, 0, 200)",
            (chunk_id, doc_id),
        )
        file_to_doc[file_path] = doc_id
        doc_id += 1
        chunk_id += 1

    # Generate symbols: ~15 per file
    sym_id = 1
    der_id = 1
    symbol_ids = []  # Track all symbol IDs for reference generation
    file_symbols = {}  # file_path -> list of (sym_id, symbol_str)

    for file_path in all_files:
        file_symbols[file_path] = []
        doc_id = file_to_doc[file_path]
        chunk_id = doc_id  # 1:1 mapping in our setup

        # 10 regular functions
        for i in range(10):
            symbol = f"scip-typescript npm test 1.0 {file_path}/`{file_path.split('/')[-1]}`/func{i}()."
            conn.execute(
                "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                (sym_id, symbol, f"func{i}"),
            )
            conn.execute(
                """
                INSERT INTO defn_enclosing_ranges
                (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
                VALUES (?, ?, ?, ?, 0, ?, 0)
                """,
                (der_id, doc_id, sym_id, i * 20, (i + 1) * 20 - 1),
            )
            # Definition mention
            conn.execute(
                "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
                (chunk_id, sym_id),
            )
            symbol_ids.append(sym_id)
            file_symbols[file_path].append((sym_id, symbol))
            sym_id += 1
            der_id += 1

        # 3 classes with methods
        for i in range(3):
            class_name = f"Class{i}"
            class_symbol = f"scip-typescript npm test 1.0 {file_path}/`{file_path.split('/')[-1]}`/{class_name}#"
            conn.execute(
                "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                (sym_id, class_symbol, class_name),
            )
            conn.execute(
                """
                INSERT INTO defn_enclosing_ranges
                (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
                VALUES (?, ?, ?, ?, 0, ?, 0)
                """,
                (der_id, doc_id, sym_id, 200 + i * 30, 200 + (i + 1) * 30 - 1),
            )
            conn.execute(
                "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
                (chunk_id, sym_id),
            )
            symbol_ids.append(sym_id)
            file_symbols[file_path].append((sym_id, class_symbol))
            sym_id += 1
            der_id += 1

            # 2 methods per class
            for j in range(2):
                file_label = file_path.split("/")[-1]
                method_symbol = f"scip-typescript npm test 1.0 {file_path}/`{file_label}`/{class_name}#method{j}()."
                conn.execute(
                    "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                    (sym_id, method_symbol, f"method{j}"),
                )
                conn.execute(
                    """
                    INSERT INTO defn_enclosing_ranges
                    (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
                    VALUES (?, ?, ?, ?, 0, ?, 0)
                    """,
                    (der_id, doc_id, sym_id, 200 + i * 30 + j * 10, 200 + i * 30 + (j + 1) * 10 - 1),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
                    (chunk_id, sym_id),
                )
                symbol_ids.append(sym_id)
                file_symbols[file_path].append((sym_id, method_symbol))
                sym_id += 1
                der_id += 1

        # 2 type symbols
        for i in range(2):
            type_symbol = f"scip-typescript npm test 1.0 {file_path}/`{file_path.split('/')[-1]}`/Type{i}#"
            conn.execute(
                "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
                (sym_id, type_symbol, f"Type{i}"),
            )
            conn.execute(
                """
                INSERT INTO defn_enclosing_ranges
                (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
                VALUES (?, ?, ?, ?, 0, ?, 0)
                """,
                (der_id, doc_id, sym_id, 300 + i * 10, 300 + (i + 1) * 10 - 1),
            )
            conn.execute(
                "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
                (chunk_id, sym_id),
            )
            symbol_ids.append(sym_id)
            file_symbols[file_path].append((sym_id, type_symbol))
            sym_id += 1
            der_id += 1

    conn.commit()

    # Create hub symbols (5 symbols referenced by 50+ files each)
    hub_sym_ids = []
    for i in range(5):
        hub_file = all_files[i]
        hub_symbol = f"scip-typescript npm test 1.0 {hub_file}/`{hub_file.split('/')[-1]}`/hubFunc{i}()."
        conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (sym_id, hub_symbol, f"hubFunc{i}"),
        )
        hub_doc_id = file_to_doc[hub_file]
        conn.execute(
            """
            INSERT INTO defn_enclosing_ranges
            (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
            VALUES (?, ?, ?, 0, 0, 10, 0)
            """,
            (der_id, hub_doc_id, sym_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
            (hub_doc_id, sym_id),
        )
        hub_sym_ids.append(sym_id)
        sym_id += 1
        der_id += 1

    conn.commit()

    # Generate cross-file references (~100K mentions)
    # Each file references 5-15 symbols from other files
    mention_count = 0
    for file_path in all_files:
        chunk_id = file_to_doc[file_path]
        num_refs = rng.randint(5, 15)

        # 30% chance to reference a hub
        if rng.random() < 0.3 and hub_sym_ids:
            hub_sym = rng.choice(hub_sym_ids)
            conn.execute(
                "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
                (chunk_id, hub_sym),
            )
            mention_count += 1

        # Reference symbols from other files
        for _ in range(num_refs):
            # Pick a random file to reference from
            ref_file = rng.choice(all_files)
            if ref_file == file_path:
                continue
            if not file_symbols[ref_file]:
                continue
            ref_sym_id, _ = rng.choice(file_symbols[ref_file])
            conn.execute(
                "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
                (chunk_id, ref_sym_id),
            )
            mention_count += 1

    conn.commit()

    # Create 5-10 file cycles (2-4 files each)
    num_cycles = rng.randint(5, 10)
    for _ in range(num_cycles):
        cycle_size = rng.randint(2, 4)
        cycle_files = rng.sample(all_files, cycle_size)
        # Each file in cycle references a symbol from the next
        for i in range(cycle_size):
            from_file = cycle_files[i]
            to_file = cycle_files[(i + 1) % cycle_size]
            if file_symbols[to_file]:
                to_sym_id, _ = file_symbols[to_file][0]
                from_chunk_id = file_to_doc[from_file]
                conn.execute(
                    "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
                    (from_chunk_id, to_sym_id),
                )

    conn.commit()

    # Mark ~10% of symbols as dead (no external refs) — already handled by random refs
    # Mark ~5% of types as stale (0 consumers) — already handled by random refs

    return conn
