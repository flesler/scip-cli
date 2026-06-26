"""Project root detection and language identification."""
import os
from pathlib import Path


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

    Returns: 'typescript' (TypeScript/JavaScript via scip-typescript), 'python', or None.
    """
    root = Path(project_root)
    if (root / "package.json").exists():
        return "typescript"
    if (root / "tsconfig.json").exists():
        return "typescript"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    return None
