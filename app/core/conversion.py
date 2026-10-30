"""Orchestrace bez Qt. Metodická neúplnost nedovoluje finální export."""
from __future__ import annotations

from decimal import Decimal, localcontext
import json
from pathlib import Path

from app.core.generation import build_xml
from app.core.mapping import load_profile, map_rows
from app.core.methodology import check_header, check_records
from app.core.models import ConversionResult, Issue
from app.core.schemas import registered_validator


class FinalExportBlocked(ValueError):
    pass


def prepare_conversion(source, profile: dict, parameters: dict, official_root: Path, *, primary_flags=None) -> ConversionResult:
    # Validate also programmatically supplied dictionaries, not just files from the UI/CLI.
    profile = load_profile(json.dumps(profile))
    header, issues = check_header(parameters)
    mapped, mapping_issues = map_rows(source, profile)
    issues.extend(mapping_issues)
    if primary_flags is not None:
        if set(primary_flags) != {r.number for r in source.rows} or any(type(v) is not bool for v in primary_flags.values()):
            raise ValueError("Primární příznaky musí jednoznačně pokrývat všechny řádky.")
        for row, values in mapped:
            values["primary_pp"] = primary_flags[row]
    if not source.rows:
        issues.append(Issue(None, "records", "empty_input", "Vstup neobsahuje žádné záznamy.", "Načtěte neprázdný skutečný export."))
    if len(source.rows) > 1500:
        issues.append(Issue(None, "records", "packet_limit", "Tento profil nepřipravuje balíky nad 1500 formulářů.", "Rozdělení do balíků vyžaduje další implementaci.", "XSD_maxOccurs_1500"))
    if not issues:
        issues.extend(check_records(mapped, header))
    if issues:
        return ConversionResult(None, tuple(issues), len(source.rows), False)
    bundles = json.loads((official_root / "bundles.json").read_text(encoding="utf-8"))["bundles"]
    bundle = next(b for b in bundles if b["id"] == profile["bundle_id"])
    validator = registered_validator(official_root, profile["bundle_id"])
    header_result = validator.validate(build_xml(bundle, [], header))
    if not header_result.xsd_valid:
        issues = [Issue(None, "header", "xsd_invalid", e, "Ověřte hlavičku podání podle XSD.", "official_XSD") for e in header_result.errors]
        return ConversionResult(None, tuple(issues), len(source.rows), False)
    # Per-record XSD validation keeps source row references without logging private values.
    for row, values in mapped:
        result = validator.validate(build_xml(bundle, [(row, values)], header))
        for error in result.errors:
            issues.append(Issue(row, "xml", "xsd_invalid", error, "Ověřte délky, identifikátory a formáty podle XSD.", "official_XSD"))
    if issues:
        return ConversionResult(None, tuple(issues), len(source.rows), False)
    xml = build_xml(bundle, mapped, header)
    result = validator.validate(xml)
    if not result.xsd_valid:
        issues = [Issue(None, "xml", "xsd_invalid", e, "Ověřte strukturu celé zakázky.", "official_XSD") for e in result.errors]
        return ConversionResult(None, tuple(issues), len(source.rows), False)
    with localcontext() as context:
        context.prec = 50
        totals = {field: sum((Decimal(row[field]) for _, row in mapped), Decimal(0))
                  for field in profile["columns"] if field.startswith("tax_income_")}
    return ConversionResult(xml, (), len(source.rows), True, totals)


def export_final(result: ConversionResult, path: Path) -> None:
    # No boolean/profile flag can bypass an unfinished correctness review.
    raise FinalExportBlocked("Finální export není povolen: chybí ověřená metodika, úplné pokrytí a přezkum výstupu.")
