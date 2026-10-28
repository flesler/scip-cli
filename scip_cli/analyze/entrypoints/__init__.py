"""CLI entrypoints that SCIP never links via import edges."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from ...project import Language, detect_language
from ...source import file_has_shebang
from . import golang as golang_entrypoints
from . import python as python_entrypoints
from . import rust as rust_entrypoints
from . import typescript as typescript_entrypoints
from .paths import canonical_rel

_DECLARED_LOADERS = {
    Language.TYPESCRIPT: typescript_entrypoints.declared_entrypoint_paths,
    Language.PYTHON: python_entrypoints.declared_entrypoint_paths,
    Language.GOLANG: golang_entrypoints.declared_entrypoint_paths,
    Language.RUST: rust_entrypoints.declared_entrypoint_paths,
}


class EntrypointIndex:
    """Declared CLI entrypoints (manifest + shebang) for one analyze pass."""

    _root: Path | None
    _declared_paths: set[str]
    _shebang_cache: dict[str, bool]

    def __init__(self, project_root: Path | None) -> None:
        self._root = project_root.resolve() if project_root is not None else None
        self._declared_paths = set()
        self._shebang_cache = {}
        if self._root is not None:
            lang = detect_language(self._root)
            if lang is not None:
                loader = _DECLARED_LOADERS.get(lang)
                if loader is not None:
                    self._declared_paths.update(loader(self._root))

    def is_entrypoint(self, relative_path: str) -> bool:
        if self._root is None:
            return False
        canonical = canonical_rel(relative_path)
        if canonical in self._declared_paths:
            return True
        if python_entrypoints.is_python_entrypoint_file(relative_path):
            return True
        if canonical in self._shebang_cache:
            return self._shebang_cache[canonical]
        has_shebang = file_has_shebang(self._root, relative_path)
        self._shebang_cache[canonical] = has_shebang
        return has_shebang


_CURRENT: ContextVar[EntrypointIndex | None] = ContextVar("scip_cli_entrypoint_index", default=None)


def bind_entrypoints(project_root: Path | str | None) -> object:
    root = Path(project_root) if project_root is not None else None
    return _CURRENT.set(EntrypointIndex(root))


def reset_entrypoints(token) -> None:
    _CURRENT.reset(token)


def is_entrypoint_path(relative_path: str) -> bool:
    index = _CURRENT.get()
    if index is None:
        return False
    return index.is_entrypoint(relative_path)


def entrypoints_bound() -> bool:
    return _CURRENT.get() is not None
