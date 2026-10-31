from __future__ import annotations

from pathlib import Path
import sys


def resource_root() -> Path:
    """Read-only resources independent of cwd, also in PyInstaller 5/6 onedir."""
    packaged = getattr(sys, "_MEIPASS", None)
    return Path(packaged) if packaged else Path(__file__).resolve().parents[2]


def default_official_root() -> Path:
    return resource_root() / "schemas" / "official"


def default_preview_root() -> Path:
    return resource_root() / "config" / "preview"
