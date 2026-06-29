"""Project root detection and language identification."""

import os
from enum import Enum
from pathlib import Path


class Language(str, Enum):
    """Supported project languages."""

    TYPESCRIPT = "typescript"
    PYTHON = "python"
    GOLANG = "golang"
    RUST = "rust"


def find_project_root_and_language(start_dir=None):
    """Walk up from start_dir (or cwd) to find project root and detect language.

    Returns: (project_root, Language) tuple, or (None, None) if not found.
    """
    d = Path(start_dir or os.getcwd()).resolve()
    while d != d.parent:
        if (d / "package.json").exists() or (d / "tsconfig.json").exists():
            return d, Language.TYPESCRIPT
        if (d / "Cargo.toml").exists():
            return d, Language.RUST
        if (d / "pyproject.toml").exists() or (d / "setup.py").exists():
            return d, Language.PYTHON
        if (d / "go.mod").exists():
            return d, Language.GOLANG
        d = d.parent
    return None, None


def find_project_root(start_dir=None):
    """Walk up from start_dir (or cwd) to find project root."""
    root, _ = find_project_root_and_language(start_dir)
    return root


def detect_language(project_root):
    """Detect language from project markers.

    Returns: Language enum value or None.
    """
    _, lang = find_project_root_and_language(project_root)
    return lang
