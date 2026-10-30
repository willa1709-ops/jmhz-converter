"""Evidence a obecný diff definic; neobsahuje domnělé schéma JMHZ."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Artifact:
    source_url: str
    version: str
    acquired_at: str
    effective_from: str | None
    effective_until: str | None
    sha256: str
    status: str = "unverified"
    technical_status: str = "not_checked"
    kind: str = "xsd"

    @classmethod
    def capture(cls, path: Path, source_url: str, version: str,
                effective_from: str | None = None, effective_until: str | None = None) -> "Artifact":
        if not source_url.startswith("https://") or not version:
            raise ValueError("Vyžadováno HTTPS zdrojové URL a verze.")
        return cls(source_url, version, datetime.now(timezone.utc).isoformat(), effective_from,
                   effective_until, hashlib.sha256(path.read_bytes()).hexdigest())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Change:
    path: str
    before: Any
    after: Any
    kind: str


def compare_definitions(old: dict[str, Any], new: dict[str, Any], prefix: str = "") -> list[Change]:
    """Diff normalizovaných slovníků včetně struktury, typů, povinnosti a pravidel.

    Neprovádí extrakci sémantiky z XSD; tu dodá adaptér ověřené verze.
    """
    result = []
    for key in sorted(old.keys() | new.keys()):
        path = f"{prefix}/{key}"
        if key not in old:
            result.append(Change(path, None, new[key], "added"))
        elif key not in new:
            result.append(Change(path, old[key], None, "removed"))
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            result.extend(compare_definitions(old[key], new[key], path))
        elif old[key] != new[key]:
            result.append(Change(path, old[key], new[key], "changed"))
    return result
