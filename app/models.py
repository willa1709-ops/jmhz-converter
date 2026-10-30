from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "Chyba"
    WARNING = "Varování"
    INFO = "Informace"


@dataclass(frozen=True)
class Row:
    number: int
    values: dict[str, str]
    numeric_columns: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Dataset:
    columns: tuple[str, ...]
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    row: int | None
    record_id: str
    field: str
    message: str
    remedy: str
