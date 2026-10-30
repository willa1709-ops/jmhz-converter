from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class SourceRow:
    number: int
    values: Dict[str, str]
    numeric_columns: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class SourceTable:
    columns: Tuple[str, ...]
    rows: Tuple[SourceRow, ...]


@dataclass(frozen=True)
class Issue:
    row: Optional[int]
    field: str
    code: str
    message: str
    remedy: str
    basis: str = "input_contract"


@dataclass(frozen=True)
class ConversionResult:
    draft_xml: Optional[bytes]
    issues: Tuple[Issue, ...]
    record_count: int
    xsd_valid: bool
    totals: Dict[str, Decimal] = field(default_factory=dict)
    methodological_validation: str = "incomplete"
    official_origin: str = "unverified"
    submission_ready: bool = False
