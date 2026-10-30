"""Doložené identifikační alternativy a konzervativní posouzení zaměstnání.

Nikdy nevyřazuje řádky, nevytváří identifikátory a neztotožňuje podle jména.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import calendar

from app.core.models import Issue
from app.core.payroll import input_state
from app.core.schemas import IdentityValidator

ALTERNATIVE_FIELDS = ("surname", "given_name", "birth_date", "employment_start", "activity_code")
IDENTITY_BASIS = "MH_1.5_3.2.1-3.2.2_IN01_and_official_identifikaceType"
ZERO_BASIS = "Pravidla_1.4.6_p16_registered_no_work_no_income_scope_review_required"


@dataclass(frozen=True)
class EmploymentAssessment:
    row: int
    employment_type: str
    identity_mode: str
    income_state: str
    reporting_decision: str
    required_fields: tuple
    retained: bool = True
    alternative: dict = field(default_factory=dict, repr=False)


def assess_workforce(source, payroll, profile, official_root=None, bundle_id=None, validation_evidence=None):
    """Only explicit source facts enable the documented conditional paths."""
    assessments, issues = [], []
    source_rows = {r.number: r for r in source.rows}
    refs = profile["metadata"]
    validator = IdentityValidator(official_root, bundle_id) if official_root is not None and bundle_id else None
    if validation_evidence is not None:
        validation_evidence.update({"bundle_id": bundle_id, "identity_component_schema_compiled": validator is not None,
                                    "xsd_dependency_hashes": dict(validator.resolver.loaded) if validator else {},
                                    "methodological_validation": "incomplete", "official_origin": "unverified"})
    for row in payroll.rows:
        meta, required = row.metadata, []
        kind = meta.get("employment_type", "").upper().replace("Č", "C")

        def issue(field_name, code, message, remedy, basis="input_contract"):
            issues.append(Issue(row.number, field_name, code, message, remedy, basis))

        if kind not in {"HPP", "DPP", "DPC"}:
            required.append("employment_type")
            issue("employment_type", "employment_type_required", "Chybí podporovaný typ pracovního poměru.", "Doplňte HPP, DPP nebo DPČ; jde o interní kategorii, nikoliv kód JMHZ.")
        registration = meta.get("registration_status")
        if "registration_status" in refs and registration not in {"registered", "pending_oic"}:
            required.append("registration_status")
            issue("registration_status", "registration_confirmation_required", "Registrace zaměstnání není potvrzena.",
                  "Doložte registraci mimo aplikaci a správný stav; pending_oic použijte jen po registraci při čekání na OIČ.", IDENTITY_BASIS)
        if registration == "pending_oic" and meta.get("oic"):
            issue("registration_status", "registration_status_conflict", "Stav čekání na OIČ odporuje vyplněnému OIČ.",
                  "Ověřte a aktualizujte stav registrace ve zdrojových datech.", IDENTITY_BASIS)
        mode, alternative = "unresolved", {}
        if meta.get("oic"):
            mode = "oic"
            if not meta.get("id_ppv"):
                required.append("id_ppv")
                issue("id_ppv", "ppv_required", "Chybí přidělené ID pracovněprávního vztahu.",
                      "Doplňte skutečné ID PPV z registrace; interní číslo PP jej nenahrazuje. Pokud dosud nebylo přiděleno, doložte přípustnost alternativní identifikace.", IDENTITY_BASIS)
        elif meta.get("registration_status") == "pending_oic":
            mode = "pending_oic"
            for key in ALTERNATIVE_FIELDS:
                value = meta.get(key, "")
                valid = isinstance(value, str) and bool(value.strip())
                if key in {"given_name", "surname"}:
                    valid = valid and len(value) <= 100
                if key in {"birth_date", "employment_start"}:
                    try:
                        valid = valid and date.fromisoformat(value).isoformat() == value
                    except (ValueError, TypeError):
                        valid = False
                if not valid:
                    required.append(key)
                    issue(key, "alternative_identity_required", "Chybí nebo není platný údaj alternativní identifikace IN01.",
                          "Doplňte " + key + " ze skutečných dokladů/exportu; potvrďte již provedenou registraci.", IDENTITY_BASIS)
            if not any(k in required for k in ALTERNATIVE_FIELDS):
                alternative = {k: meta[k] for k in ALTERNATIVE_FIELDS}
                if validator is None:
                    issue("identity", "identity_xsd_required", "Alternativa vyžaduje výslovnou volbu dodané XSD sady.",
                          "Vyberte ověřený balíček definic; účinnost musí projít samostatným přezkumem.", IDENTITY_BASIS)
                elif not validator.alternative(meta).xsd_valid:
                    issue("identity", "alternative_identity_xsd", "Alternativní identifikace neprošla skutečným XSD.",
                          "Ověřte datum, délky a oficiální druh činnosti; žádná hodnota se nedoplňuje odhadem.", IDENTITY_BASIS)
                else:
                    mode = "alternative_xsd_valid"
            if not meta.get("rc"):
                issue("identity", "alternative_pairing_unresolved", "Alternativa pro IN01 sama nedokládá shodu osoby mezi PP.",
                      "Doplňte přidělené OIČ/RČ nebo doložený metodicky přípustný postup ztotožnění; jméno nestačí.", IDENTITY_BASIS)
        elif meta.get("rc"):
            mode = "rc_pairing_only"
            issue("identity", "oic_or_in01_required", "RČ umožňuje lokální párování, ale samo nenahrazuje XML identifikaci.",
                  "Doplňte přidělené OIČ a PPV, nebo potvrzení registrace a údaje alternativy IN01.", IDENTITY_BASIS)
        else:
            required.extend(ALTERNATIVE_FIELDS)
            issue("identity", "registration_or_identity_required", "Chybí identifikace zaměstnance.",
                  "Doložte registraci a přidělené OIČ/PPV. Při čekání na OIČ doplňte pending_oic, jméno, příjmení, narození, nástup a druh činnosti.", IDENTITY_BASIS)
        ref = refs.get("income_amount")
        column = ref.get("column") or profile["items"][ref["item"]]["column"] if ref else None
        state = input_state(source_rows[row.number].values, column, source.columns) if column else "absent_column"
        decision = "reporting_scope_review_required"
        if state in {"absent_column", "absent_value", "blank", "invalid"}:
            required.append("income_amount")
            decision = "income_data_required"
            issue("income_amount", "income_unknown", "Příjem není známý; zaměstnání zůstává v importu.",
                  "Doplňte skutečnou hodnotu nebo doložené vysvětlení. Prázdný či nepřítomný údaj není nula.")
        elif state == "zero":
            decision = "zero_income_review_required"
            try:
                first = date(row.period.year, row.period.month, 1)
                last = date(row.period.year, row.period.month, calendar.monthrange(row.period.year, row.period.month)[1])
                start = date.fromisoformat(meta.get("employment_start", ""))
                end = date.fromisoformat(meta["employment_end"]) if meta.get("employment_end") else last
                active = start <= last and end >= first and end >= start
            except ValueError:
                active = False
            if active and meta.get("registration_status") == "registered" and meta.get("work_performed") == "no":
                decision = "include_zero_registered_no_work_candidate"
            issue("reporting", "zero_income_methodology_review", "Nulový příjem není důvodem k vyřazení zaměstnání.",
                  "Pro registrovaný PP bez práce a příjmu dokument popisuje řádný formulář s nulovými hodnotami; potvrďte účinnost, trvání PP, pojištění a další povinné údaje.", ZERO_BASIS)
        assessments.append(EmploymentAssessment(row.number, kind, mode, state, decision, tuple(required), alternative=alternative))
    return tuple(assessments), tuple(issues)
