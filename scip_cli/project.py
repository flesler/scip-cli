"""Project root detection and language identification."""
import os
from enum import Enum
from pathlib import Path


class Language(str, Enum):
    """Supported project languages."""
    TYPESCRIPT = "typescript"
    PYTHON = "python"

    @classmethod
    def values(cls):
        return [lang.value for lang in cls]


def find_project_root(start_dir=None):
    """Walk up from start_dir (or cwd) to find project root."""
    markers = ["package.json", "tsconfig.json", "pyproject.toml", "setup.py"]
    d = Path(start_dir or os.getcwd()).resolve()
    while d != d.parent:
        if any((d / m).exists() for m in markers):
            return d
        d = d.parent
    return None


def detect_language(project_root):
    """Detect language from project markers.

    Returns: Language enum value or None.
    """
    root = Path(project_root)
    if (root / "package.json").exists():
        return Language.TYPESCRIPT.value
    if (root / "tsconfig.json").exists():
        return Language.TYPESCRIPT.value
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return Language.PYTHON.value
    return None
