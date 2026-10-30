"""Moderní adaptéry společných CSV/XLSX importérů ke stávajícím modelům UI."""
from pathlib import Path

from app.core.input import read_csv as _read_csv, read_xlsx as _read_xlsx
from app.models import Dataset, Row


def _adapt(data) -> Dataset:
    return Dataset(data.columns, tuple(Row(row.number, row.values, row.numeric_columns) for row in data.rows))


def read_csv(path: Path, encoding: str = "auto", delimiter: str = "auto") -> Dataset:
    return _adapt(_read_csv(path, encoding, delimiter))


def read_xlsx(path: Path) -> Dataset:
    return _adapt(_read_xlsx(path))
