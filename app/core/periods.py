"""Interní kontext zakázky: nezávislý na GUID a oficiálním typu podání."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class Period:
    year: int
    month: int

    def __post_init__(self):
        if type(self.year) is not int or type(self.month) is not int or not 1900 <= self.year <= 9999 or not 1 <= self.month <= 12:
            raise ValueError("Neplatné období.")

    @classmethod
    def parse(cls, value: str, century: int = 2000) -> Period:
        if type(century) is not int or century % 100 or not 1900 <= century <= 9900:
            raise ValueError("Neplatná politika století.")
        if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{2}|[0-9]{4})-[0-9]{2}", value):
            raise ValueError("Období musí být YY-MM nebo YYYY-MM.")
        y, m = value.split("-")
        return cls(int(y) + century if len(y) == 2 else int(y), int(m))

    @property
    def iso(self) -> str:
        return "{0:04d}-{1:02d}".format(self.year, self.month)


@dataclass(frozen=True)
class SubmissionContext:
    period: Period
    revision_index: int

    def __post_init__(self):
        if not isinstance(self.period, Period) or type(self.revision_index) is not int or not 0 <= self.revision_index <= 1_000_000:
            raise ValueError("Interní revize musí být nezáporné celé číslo.")


class RevisionRegistry:
    """Pouze metadata zakázek. Neukládá osoby, mzdy ani oficiální GUID."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS revisions (scope TEXT, period TEXT, revision INTEGER, definition_sha256 TEXT, definition_kind TEXT, created_at TEXT, PRIMARY KEY(scope,period,revision))")

    def record(self, scope: str, context: SubmissionContext, definition_sha256: str, definition_kind: str = "pinned_package_manifest") -> None:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", scope) or not re.fullmatch(r"[0-9a-f]{64}", definition_sha256):
            raise ValueError("Použijte neosobní alias a ověřený hash definic.")
        if definition_kind not in {"pinned_package_manifest", "local_working_profile"}:
            raise ValueError("Neznámý druh definice.")
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            maximum = db.execute("SELECT MAX(revision) FROM revisions WHERE scope=? AND period=?", (scope, context.period.iso)).fetchone()[0]
            expected = 0 if maximum is None else maximum + 1
            if context.revision_index != expected:
                raise ValueError("Revize musí navazovat od nuly; již evidovaná revize se nepřepisuje.")
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (scope, context.period.iso, context.revision_index,
                       definition_sha256, definition_kind, datetime.now(timezone.utc).isoformat()))
