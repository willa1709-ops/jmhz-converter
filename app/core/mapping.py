"""Pracovní mapování pojmenovaných vstupních sloupců, bez spouštění výrazů."""
from __future__ import annotations

from decimal import Decimal, localcontext
import json
import re

from app.core.models import Issue

SUPPORTED = {"jmhz-1.4.3.6", "jmhz-1.5.0.3"}
BASE_FIELDS = ("form_id", "period", "activity_code", "ik_mpsv", "id_ppv", "tax_income_10535")


def load_profile(text: str) -> dict:
    profile = json.loads(text)
    if not isinstance(profile, dict) or set(profile) != {"name", "bundle_id", "scenario", "status", "columns"}:
        raise ValueError("Neplatný konverzní profil.")
    if (not all(isinstance(profile[k], str) for k in ("name", "bundle_id", "scenario", "status"))
            or not profile["name"].strip()
            or profile["bundle_id"] not in SUPPORTED or profile["scenario"] != "jinyPrijem"
            or profile["status"] != "working_unverified"):
        raise ValueError("Podporován je pouze pracovní profil jinyPrijem konkrétního balíčku.")
    expected = set(BASE_FIELDS)
    if profile["bundle_id"] == "jmhz-1.5.0.3":
        expected.add("tax_income_10555")
    columns = profile["columns"]
    if not isinstance(columns, dict) or set(columns) != expected:
        raise ValueError("Profil musí mapovat všechny vstupy daného scénáře.")
    if any(not isinstance(value, str) or not value.strip() for value in columns.values()):
        raise ValueError("Zdroj každého pole musí být název sloupce, nikoliv hodnota.")
    return profile


def integer_amount(text: str) -> str:
    if len(text) > 40 or not re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        raise ValueError("Částka není nezáporné konečné číslo.")
    with localcontext() as context:
        context.prec = 50
        value = Decimal(text.replace(",", "."))
        if value != value.to_integral_value() or value >= Decimal(10) ** 14:
            raise ValueError("Oficiální cílový typ vyžaduje celé číslo do 14 číslic; nezaokrouhlujeme odhadem.")
        return format(value.quantize(Decimal(1)), "f")


def map_rows(source, profile: dict):
    mapped, issues = [], []
    for field, column in profile["columns"].items():
        if column not in source.columns:
            issues.append(Issue(None, field, "missing_column", "Chybí zdrojový sloupec profilu.", "Doplňte sloupec nebo upravte mapování."))
    if issues:
        return mapped, issues
    for row in source.rows:
        values = {}
        for field, column in profile["columns"].items():
            raw = row.values.get(column)
            if not isinstance(raw, str) or not raw.strip():
                issues.append(Issue(row.number, field, "missing_value", "Chybí hodnota pracovního konverzního profilu.", "Doplňte skutečný údaj; prázdná částka není nula."))
                continue
            if field in {"ik_mpsv", "id_ppv", "form_id"} and column in row.numeric_columns:
                issues.append(Issue(row.number, field, "numeric_identifier", "Identifikátor byl ve zdroji číselný.", "Exportujte identifikátor jako text se zachovanými nulami."))
                continue
            raw = raw.strip()
            try:
                values[field] = integer_amount(raw) if field.startswith("tax_income_") else raw
            except ValueError:
                issues.append(Issue(row.number, field, "amount_format", "Cílový typ vyžaduje celé nezáporné číslo do 14 číslic.", "Vyjasněte zdroj a pravidlo zaokrouhlení; automatické zaokrouhlení není povoleno.", "XSD_cislo14Type"))
        mapped.append((row.number, values))
    return mapped, issues
