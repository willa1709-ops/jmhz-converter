from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from app.models import Row

MONEY_FIELDS = ("income", "social_base", "health_base")


def decimal_value(value: str) -> Decimal:
    text = value.strip()
    if len(text) > 30 or not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", text):
        raise ValueError("Částka musí být konečné desetinné číslo bez oddělovače tisíců.")
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Neplatná částka.") from exc


@dataclass(frozen=True)
class Total:
    value: Decimal
    missing: int
    invalid: int


def total(rows: tuple[Row, ...], field: str) -> Total:
    value, missing, invalid = Decimal(0), 0, 0
    # Input max 30 chars + up to 100k rows; avoid default precision rounding.
    from decimal import localcontext
    with localcontext() as context:
        context.prec = 50
        for row in rows:
            raw = row.values.get(field, "").strip()
            if not raw:
                missing += 1
                continue
            try:
                value += decimal_value(raw)
            except ValueError:
                invalid += 1
    return Total(value, missing, invalid)
