"""Výslovný adaptér obecných položek na dosavadní pracovní jinyPrijem."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import json

from app.core.conversion import prepare_conversion
from app.core.mapping import load_profile
from app.core.models import SourceRow, SourceTable
from app.core.payroll import load_numbered_profile, prepare_payroll


def validate_bindings(bindings, numbered, conversion):
    if not isinstance(bindings, dict) or set(bindings) != set(conversion["columns"]):
        raise ValueError("Vazby musí pokrýt přesně pole konverzního profilu.")
    identity_roles = {"ik_mpsv": "oic", "id_ppv": "id_ppv", "form_id": "form_id", "activity_code": "activity_code"}
    for target, ref in bindings.items():
        if target == "period":
            if ref != {"context": "period"}:
                raise ValueError("Období konverze musí odpovídat kontextu zakázky.")
        elif target in identity_roles:
            if ref != {"metadata": identity_roles[target]} or identity_roles[target] not in numbered["metadata"]:
                raise ValueError("Identifikátory mají výslovné zdroje; interní číslo/revize nejsou GUID.")
        else:
            if not isinstance(ref, dict) or not ((set(ref) == {"calculation"} and isinstance(ref["calculation"], str) and ref["calculation"] in numbered["calculations"])
                                               or (set(ref) == {"item"} and isinstance(ref["item"], str) and ref["item"] in numbered["items"])):
                raise ValueError("Částka musí odkazovat na číslovanou položku nebo řádkový výpočet.")
            if "item" in ref:
                column = numbered["items"][ref["item"]]["column"]
                for key in ("oic", "rc"):
                    if key in numbered["metadata"]:
                        meta = numbered["metadata"][key]
                        private = meta.get("column") or numbered["items"][meta["item"]]["column"]
                        if column == private:
                            raise ValueError("Identifikátor není mzdová částka.")


@dataclass(frozen=True)
class NumberedConversion:
    payroll: object
    conversion: object = field(default=None, repr=False)


def prepare_numbered_conversion(source, numbered, context, conversion, bindings, parameters, official_root):
    numbered = load_numbered_profile(json.dumps(numbered))
    conversion = load_profile(json.dumps(conversion))
    validate_bindings(bindings, numbered, conversion)
    payroll = prepare_payroll(source, numbered, context)
    if payroll.issues:
        return NumberedConversion(payroll)
    rows, flags = [], {}
    for row in payroll.rows:
        values = {}
        for target, ref in bindings.items():
            if "context" in ref:
                value = context.period.iso
            elif "metadata" in ref:
                value = row.metadata.get(ref["metadata"])
            elif "item" in ref:
                value = row.items.get(ref["item"])
            else:
                value = row.calculations.get(ref["calculation"])
            values[conversion["columns"][target]] = format(value, "f") if isinstance(value, Decimal) else value or ""
        rows.append(SourceRow(row.number, values))
        flags[row.number] = row.primary_pp
    table = SourceTable(tuple(conversion["columns"].values()), tuple(rows))
    result = prepare_conversion(table, conversion, parameters, official_root, primary_flags=flags)
    return NumberedConversion(payroll, result)
