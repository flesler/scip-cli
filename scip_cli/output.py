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


def warn_ambiguous(name, matches, context="symbol"):
    """Print warning if multiple matches found."""
    if len(matches) <= 1:
        return
    label = _ambiguous_label(matches[0])
    print(
        f"Ambiguous {context} '{name}' ({len(matches)} matches). Using first match: {label}",
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
    """Resolve per-definition line cap for def output (0 = unlimited)."""
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


def format_def_body(lines, start_line, end_line, max_lines=None, max_chars=None):
    """Format definition source with optional truncation for agent-safe output."""
    if lines is None:
        return "(could not read source)", False, start_line, end_line

    max_lines = DEFAULT_MAX_DEF_LINES if max_lines is None else max_lines
    max_chars = DEFAULT_MAX_DEF_CHARS if max_chars is None else max_chars

    if max_lines == 0 and max_chars == 0:
        body = "".join(lines).rstrip("\n")
        return body, False, start_line, end_line

    selected = list(lines)
    truncated = False

    if max_lines > 0 and len(selected) > max_lines:
        selected = selected[:max_lines]
        truncated = True

    body = "".join(selected).rstrip("\n")

    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars].rstrip("\n") + "\n..."
        truncated = True

    shown_end = start_line + len(selected) - 1 if selected else start_line
    return body, truncated, start_line, shown_end


def print_def_truncation_notice(
    rel_path,
    start_line,
    end_line,
    shown_start,
    shown_end,
):
    """Print stderr guidance when a definition body was truncated."""
    total = end_line - start_line + 1
    shown = shown_end - shown_start + 1
    omitted = total - shown
    if omitted <= 0:
        return
    print(
        f"# Warning: definition truncated for '{rel_path}' "
        f"(showing lines {shown_start + 1}-{shown_end + 1} of "
        f"{start_line + 1}-{end_line + 1}; {omitted} lines omitted). "
        f"Use `scip-cli code --max-lines 0 <symbol>` or Read the file with offset/limit.",
        file=sys.stderr,
    )
