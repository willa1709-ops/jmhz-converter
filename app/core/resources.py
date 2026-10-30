from __future__ import annotations

from pathlib import Path
import sys


def default_official_root() -> Path:
    """Read-only resources: source checkout or PyInstaller data directory."""
    packaged = getattr(sys, "_MEIPASS", None)
    root = Path(packaged) if packaged else Path(__file__).resolve().parents[2]
    return root / "schemas" / "official"
