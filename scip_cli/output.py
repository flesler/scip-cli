"""CLI output formatting helpers."""

import os
import sys

from .symbols import extract_file_path_from_symbol, extract_leaf_name

DEFAULT_MAX_DEF_LINES = 80
DEFAULT_MAX_DEF_CHARS = 32_000


def _ambiguous_label(match):
    """Short label for an ambiguous match (leaf name + optional file path)."""
    if isinstance(match, tuple) and len(match) > 1:
        symbol_or_path = match[1]
        if isinstance(symbol_or_path, str) and symbol_or_path.startswith("scip-"):
            leaf = extract_leaf_name(symbol_or_path)
            rel_path = extract_file_path_from_symbol(symbol_or_path)
            if rel_path:
                return f"{leaf} ({rel_path})"
            return leaf
        return symbol_or_path
    return match


def symbol_output_label(query_name: str, symbol_str: str, matches_for_query: int) -> str:
    """Label for a symbol block when multiple symbols are printed."""
    if matches_for_query > 1:
        return _ambiguous_label((None, symbol_str))
    return query_name


def maybe_print_symbol_header(label: str, show_header: bool) -> None:
    if show_header:
        print(label)


def warn_ambiguous(name, matches, context="symbol"):
    """Print warning if multiple matches found."""
    if len(matches) <= 1:
        return
    label = _ambiguous_label(matches[0])
    print(
        f"Ambiguous {context} '{name}' ({len(matches)} matches). Using first match: {label}",
        file=sys.stderr,
    )


def warn_ambiguous_refs(name, matches, db):
    """Print external ref counts when a symbol name resolves to multiple definitions."""
    if len(matches) <= 1:
        return
    from .queries import symbol_external_ref_count

    parts = []
    for sym_id, sym_str, _display in matches:
        label = _ambiguous_label((None, sym_str))
        count = symbol_external_ref_count(db, sym_id)
        parts.append(f"{label} ext_refs={count}")
    print(
        f"Ambiguous symbol '{name}' ({len(matches)} matches). Use --path to narrow. {'; '.join(parts)}",
        file=sys.stderr,
    )


def format_line_range(start_line, end_line, sep=":"):
    """Format a line range as a string, handling None values."""
    if start_line is not None and end_line is not None:
        return f"{start_line + 1}{sep}{end_line + 1}"
    if start_line is not None:
        return f"{start_line + 1}{sep}?"
    return "??"


def limit_and_warn(items, limit, label="results"):
    """Trim a list to limit and print a warning if truncated."""
    if len(items) > limit:
        print(f"# Warning: more than {limit} {label}, showing first {limit}", file=sys.stderr)
    return items[:limit]


def resolve_max_def_lines(cli_value=None):
    """Resolve per-definition line cap for code output (0 = unlimited)."""
    if cli_value is not None:
        if cli_value < 0:
            raise RuntimeError(f"--max-lines must be >= 0, got {cli_value}")
        return cli_value
    env = os.environ.get("SCIP_CLI_MAX_DEF_LINES")
    if env is not None:
        try:
            value = int(env)
            if value < 0:
                raise RuntimeError(f"SCIP_CLI_MAX_DEF_LINES must be >= 0, got {value}")
            return value
        except ValueError:
            raise RuntimeError(f"Invalid SCIP_CLI_MAX_DEF_LINES: expected an integer, got {env!r}") from None
    return DEFAULT_MAX_DEF_LINES


def format_def_body(lines, start_line, end_line, max_lines=None, max_chars=None, offset=0, line_numbers=False):
    """Format definition source with optional truncation for agent-safe output."""
    if lines is None:
        return "(could not read source)", False, start_line, end_line

    max_lines = DEFAULT_MAX_DEF_LINES if max_lines is None else max_lines
    max_chars = DEFAULT_MAX_DEF_CHARS if max_chars is None else max_chars

    if max_lines == 0 and max_chars == 0:
        body = "".join(lines).rstrip("\n")
        if line_numbers:
            body = _add_line_numbers(body, start_line)
        return body, False, start_line, end_line

    selected = list(lines)
    truncated = False

    # Apply offset first
    if offset > 0:
        selected = selected[offset:]
        start_line = start_line + offset

    if max_lines > 0 and len(selected) > max_lines:
        selected = selected[:max_lines]
        truncated = True

    body = "".join(selected).rstrip("\n")

    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars].rstrip("\n") + "\n..."
        truncated = True

    if line_numbers:
        body = _add_line_numbers(body, start_line)

    shown_end = start_line + len(selected) - 1 if selected else start_line
    return body, truncated, start_line, shown_end


def _add_line_numbers(body, start_line):
    """Prefix each line with its line number."""
    lines = body.split("\n")
    numbered = []
    for i, line in enumerate(lines):
        line_num = start_line + i + 1
        numbered.append(f"{line_num}|{line}")
    return "\n".join(numbered)


def print_def_truncation_notice(query_name, body_offset, lines_shown, def_body_lines):
    """Print stderr hint when a definition body was truncated."""
    next_offset = body_offset + lines_shown
    if next_offset >= def_body_lines:
        return
    at_line = body_offset + lines_shown
    print(
        (
            f"Warning: truncated at line {at_line}/{def_body_lines} of definition. "
            f"Continue: code --offset {next_offset} {query_name}"
        ),
        file=sys.stderr,
    )
