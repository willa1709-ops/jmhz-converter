"""Omezený JSON strom operací, nikdy Python eval."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, localcontext
import json
from pathlib import Path
from typing import Any

from app.calculations import decimal_value
from app.models import Dataset, Finding, Row, Severity

DRAFT_VERSION = "unverified-draft-0"
FIELDS = ("employee_id", "period", "income", "social_base", "health_base")


def evaluate(expr: dict[str, Any], values: dict[str, str], depth: int = 0,
             forbidden_columns: frozenset[str] = frozenset()) -> str:
    if depth > 20 or not isinstance(expr, dict):
        raise ValueError("Neplatné nebo příliš hluboké mapování.")
    op = expr.get("op")
    def child(node: dict[str, Any]) -> str:
        return evaluate(node, values, depth + 1, forbidden_columns)
    if op == "column":
        name = expr["name"]
        if name in forbidden_columns:
            raise ValueError("Identifikátor musí být textovou buňkou již ve zdroji.")
        if name not in values:
            raise ValueError("Zdrojový sloupec neexistuje.")
        return values[name].strip()
    if op == "constant":
        if not isinstance(expr["value"], str):
            raise ValueError("Konstanta musí být text.")
        return expr["value"]
    if op == "concat":
        return expr.get("separator", "").join(child(x) for x in expr["args"])
    if op == "if_equal":
        return child(expr["then"] if child(expr["left"]) == child(expr["right"]) else expr["else"])
    if op == "lookup":
        key = child(expr["arg"])
        if key not in expr["table"] or not isinstance(expr["table"][key], str):
            raise ValueError("Hodnota není v mapovacím číselníku.")
        return expr["table"][key]
    if op in {"add", "round", "decimal"}:
        with localcontext() as context:
            context.prec = 50
            if op == "add":
                return str(sum((decimal_value(child(x)) for x in expr["args"]), decimal_value("0")))
            number = decimal_value(child(expr["arg"]))
            if op == "round":
                number = number.quantize(decimal_value("0.01"), rounding=ROUND_HALF_UP)
            return format(number, "f")
    raise ValueError("Nepodporovaná operace mapování.")


@dataclass(frozen=True)
class Profile:
    name: str
    definition_version: str
    rules: dict[str, dict[str, Any]]

    @classmethod
    def default(cls) -> "Profile":
        return cls("Pracovní návrh", DRAFT_VERSION, {f: {"op": "column", "name": f} for f in FIELDS})

    def dumps(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)

    @classmethod
    def loads(cls, text: str) -> "Profile":
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {"name", "definition_version", "rules"}:
            raise ValueError("Neplatný profil.")
        if not all(isinstance(data[k], str) and data[k] for k in ("name", "definition_version")):
            raise ValueError("Chybí název nebo verze profilu.")
        if not isinstance(data["rules"], dict) or set(data["rules"]) - set(FIELDS):
            raise ValueError("Neznámá cílová pole.")
        return cls(**data)

    def save(self, path: Path) -> None:
        path.write_text(self.dumps(), encoding="utf-8")


def map_dataset(data: Dataset, profile: Profile) -> tuple[Dataset, list[Finding]]:
    rows, findings = [], []
    for row in data.rows:
        values = {}
        for field in FIELDS:
            if field not in profile.rules:
                values[field] = ""
                continue
            try:
                values[field] = evaluate(profile.rules[field], row.values,
                                         forbidden_columns=row.numeric_columns if field == "employee_id" else frozenset())
            except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError):
                values[field] = ""
                findings.append(Finding(Severity.ERROR, row.number, row.values.get("employee_id", ""), field,
                                        "Mapování nelze vyhodnotit.", "Opravte pravidlo nebo zdrojový sloupec; identifikátory v XLSX musí být text."))
        rows.append(Row(row.number, values))
    return Dataset(FIELDS, tuple(rows)), findings
