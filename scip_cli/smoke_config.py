"""Load local monorepo smoke settings for gate benchmarks (paths are not versioned)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "scripts" / "smoke.local.json"
EXAMPLE_CONFIG_PATH = REPO_ROOT / "scripts" / "smoke.local.example.json"


@dataclass(frozen=True)
class SmokeConfig:
    root: Path
    touch_large: tuple[str, ...]


def smoke_config_path() -> Path:
    raw = os.environ.get("SCIP_CLI_SMOKE_CONFIG", "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_CONFIG_PATH


def load_smoke_config() -> SmokeConfig | None:
    path = smoke_config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    root_raw = data.get("root")
    if not isinstance(root_raw, str) or not root_raw.strip():
        return None
    touch_raw = data.get("touch_large", [])
    if isinstance(touch_raw, str):
        touch_paths = (touch_raw,)
    elif isinstance(touch_raw, list):
        touch_paths = tuple(str(item) for item in touch_raw if isinstance(item, str) and item.strip())
    else:
        touch_paths = ()
    if not touch_paths:
        return None
    return SmokeConfig(root=Path(root_raw).expanduser(), touch_large=touch_paths)


def smoke_config_hint() -> str:
    return (
        f"Copy {EXAMPLE_CONFIG_PATH.relative_to(REPO_ROOT)} to "
        f"{DEFAULT_CONFIG_PATH.relative_to(REPO_ROOT)} (gitignored) and set root + touch_large."
    )
