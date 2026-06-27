"""Debug-only stderr helpers."""

import os
import sys


def debug_log(message: str) -> None:
    """Print message to stderr when SCIP_CLI_DEBUG is set."""
    if os.environ.get("SCIP_CLI_DEBUG"):
        print(message, file=sys.stderr)
