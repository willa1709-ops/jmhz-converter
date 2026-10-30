"""Technická konzistence vstupu a výslovný stav nedokončené metodiky."""
from __future__ import annotations

from datetime import datetime
import re

from app.core.models import Issue

HEADER_FIELDS = ("submission_id", "employer_variable_symbol", "year", "month", "filled_at")
FINAL_BLOCKERS = ("origin_review_missing", "effective_scope_unconfirmed", "payroll_mapping_unconfirmed",
                  "methodological_rules_incomplete", "coverage_limited_to_jinyPrijem")


def check_header(parameters: dict):
    issues, header = [], {}
    if not isinstance(parameters, dict) or set(parameters) - set(HEADER_FIELDS):
        return header, [Issue(None, "parameters", "invalid_header", "Neplatné položky konfigurace podání.", "Použijte přesný formát parameters.template.json.")]
    for field in HEADER_FIELDS:
        value = parameters.get(field)
        if (isinstance(value, bool) or value is None or not isinstance(value, (str, int)) or not str(value).strip()
                or (field in {"submission_id", "employer_variable_symbol", "filled_at"} and not isinstance(value, str))):
            issues.append(Issue(None, field, "missing_header", "Chybí skutečný údaj hlavičky.", "Vyplňte konfiguraci podání; hodnoty se nevytvářejí odhadem."))
        else:
            header[field] = str(value).strip()
    if issues:
        return header, issues
    if not re.fullmatch(r"[0-9]{4}", header["year"]) or not re.fullmatch(r"(?:0?[1-9]|1[0-2])", header["month"]):
        issues.append(Issue(None, "period", "invalid_period", "Neplatné období konfigurace.", "Použijte rok YYYY a měsíc 1–12."))
    try:
        datetime.fromisoformat(header["filled_at"].replace("Z", "+00:00"))
        if "T" not in header["filled_at"]:
            raise ValueError("Missing time")
    except ValueError:
        issues.append(Issue(None, "filled_at", "invalid_datetime", "Neplatné datum a čas vyplnění.", "Doplňte skutečný čas ISO 8601 včetně T a času."))
    return header, issues


def check_records(records, header):
    issues, form_ids, ppvs = [], set(), set()
    expected = "{0}-{1:02d}".format(header["year"], int(header["month"]))
    for row, values in records:
        if values["period"] != expected:
            issues.append(Issue(row, "period", "period_mismatch", "Období řádku neodpovídá podání.", "Vyberte správný soubor a konfiguraci období."))
        if values["activity_code"] not in {"11", "13", "14"}:
            issues.append(Issue(row, "activity_code", "unsupported_scenario", "Profil jinyPrijem nepokrývá tento druh činnosti.", "Zvolte jiný, dosud neimplementovaný scénář; nepřejmenovávejte činnost.", "formJinyPrijem.xsd_annotation"))
        key = (values["ik_mpsv"], values["id_ppv"])
        if values["form_id"] in form_ids:
            issues.append(Issue(row, "form_id", "duplicate_form_id", "Duplicitní GUID formuláře ve vstupní zakázce.", "Doplňte správnou identitu formuláře."))
        if key in ppvs:
            issues.append(Issue(row, "id_ppv", "duplicate_source_record", "Duplicitní formulář nebo PPV ve vstupní zakázce.", "Pracovní profil očekává jeden řádek za PPV a měsíc; vyřešte duplicitu."))
        form_ids.add(values["form_id"])
        ppvs.add(key)
    return issues
