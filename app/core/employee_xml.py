"""Pracovní bezPriznaku pro doložený rozsah HPP/DPČ/DPP. Žádný finální export."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
import calendar
import json

from lxml import etree

from app.core.employee_schema import EmployeeContract
from app.core.generation import build_xml
from app.core.methodology import check_header
from app.core.models import Issue
from app.core.payroll import decimal_input, load_numbered_profile, prepare_payroll, strict_json
from app.core.workforce import assess_workforce
from app.core.xml_support import parse_local_xml

ACTIVITIES = {"HPP": frozenset(str(i) for i in range(1, 10)), "DPC": frozenset("ABCDEFGHIJ"),
              "DPP": frozenset(("T", "U", "V", "W", "X", "Y", "Z", "ZA", "ZB", "ZC"))}
IMPLEMENTED_CONTROLS = ("23", "43", "44", "58", "216", "248", "255", "260", "267", "282", "286", "299", "321", "332")
NUMERIC_TYPES = {"decimal", "integer", "nonNegativeInteger", "positiveInteger", "int", "long", "short", "byte", "unsignedInt", "unsignedLong", "unsignedShort", "unsignedByte"}


def load_employee_profile(text, numbered=None, contract=None):
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Zaměstnanecký profil je příliš velký.")
    p = strict_json(text)
    if (not isinstance(p, dict) or set(p) != {"format_version", "scenario", "bundle_id", "status", "fields"}
            or type(p["format_version"]) is not int or p["format_version"] != 1 or p["scenario"] != "bezPriznaku"
            or p["bundle_id"] not in {"jmhz-1.4.3.6", "jmhz-1.5.0.3"} or p["status"] != "working_unverified"
            or not isinstance(p["fields"], dict) or not 1 <= len(p["fields"]) <= 512):
        raise ValueError("Neplatný pracovní zaměstnanecký profil.")
    if contract is not None and contract.bundle["id"] != p["bundle_id"]:
        raise ValueError("Profil a kontrakt patří různým sadám.")
    for path, ref in p["fields"].items():
        if (not isinstance(path, str) or not path.startswith("bezPriznaku/") or path.startswith("bezPriznaku/identifikace/")
                or not isinstance(ref, dict) or set(ref) - {"column", "item", "calculation", "on"}):
            raise ValueError("Nepovolená cesta nebo vazba.")
        sources = set(ref) - {"on"}
        if len(sources) != 1 or any(not isinstance(ref[k], str) or not ref[k].strip() for k in sources):
            raise ValueError("Pole má právě jeden deklarativní zdroj.")
        if ("on" in ref and ref["on"] != "primary") or (path.startswith("bezPriznaku/souhrnDataZec/") and ref.get("on") != "primary"):
            raise ValueError("Osobní souhrn se mapuje výslovně jen na primární PP (kontrola 248).")
        if contract is not None and path not in contract.fields:
            raise ValueError("Cesta není v oficiálním XSD této sady.")
        if numbered is not None:
            if "item" in ref and ref["item"] not in numbered["items"] or "calculation" in ref and ref["calculation"] not in numbered["calculations"]:
                raise ValueError("Neznámá položka nebo řádkový výpočet.")
            column = ref.get("column") or (numbered["items"][ref["item"]]["column"] if "item" in ref else None)
            for key in ("oic", "rc", "given_name", "surname", "birth_date"):
                if key in numbered["metadata"]:
                    meta = numbered["metadata"][key]
                    private = meta.get("column") or numbered["items"][meta["item"]]["column"]
                    if column == private:
                        raise ValueError("Osobní identifikace není zdroj pracovních/mzdových polí.")
    return p


@dataclass(frozen=True)
class EmployeeResult:
    draft_xml: object = field(repr=False)
    issues: tuple
    review_issues: tuple
    record_count: int
    xsd_valid: bool
    evidence: dict
    methodological_validation: str = "partial"
    official_origin: str = "unverified"
    submission_ready: bool = False

    def safe_report(self):
        return {"record_count": self.record_count, "xsd_valid": self.xsd_valid, "issues": [asdict(i) for i in self.issues],
                "review_issues": [asdict(i) for i in self.review_issues], "evidence": self.evidence,
                "methodological_validation": "partial", "official_origin": "unverified", "submission_ready": False}


def normalized(raw, base):
    if not isinstance(raw, (str, Decimal)) or not str(raw).strip():
        raise ValueError("Hodnota chybí.")
    raw = format(raw, "f") if isinstance(raw, Decimal) else raw.strip()
    if base == "boolean":
        if raw.lower() not in {"1", "0", "true", "false", "ano", "ne"}:
            raise ValueError("Neplatný příznak.")
        return "true" if raw.lower() in {"1", "true", "ano"} else "false"
    if base in NUMERIC_TYPES or base == "digit_string":
        value = decimal_input(raw)
        if base != "decimal":
            if value != value.to_integral_value():
                raise ValueError("Celé číslo se nezaokrouhluje.")
            if base == "digit_string" and raw.isascii() and raw.isdigit():
                return raw
            with localcontext() as context:
                context.prec = 128
                return format(value.quantize(Decimal(1)), "f")
        return format(value, "f")
    return raw


def prepare_employee_xml(source, numbered, profile, context, parameters, official_root):
    numbered = load_numbered_profile(json.dumps(numbered))
    profile = load_employee_profile(json.dumps(profile))
    contract = EmployeeContract(official_root, profile["bundle_id"])
    profile = load_employee_profile(json.dumps(profile), numbered, contract)
    header, header_issues = check_header(parameters)
    payroll = prepare_payroll(source, numbered, context)
    assessments, workforce_issues = assess_workforce(source, payroll, numbered, official_root, profile["bundle_id"])
    issues, reviews = list(header_issues), []
    evidence = {"bundle_id": profile["bundle_id"], "scenario": "bezPriznaku", "scope": "one_eldp_segment_per_row",
                "implemented_control_ids": list(IMPLEMENTED_CONTROLS), "xsd_dependency_hashes": dict(contract.validator.resolver.loaded),
                "effectivity": "unconfirmed", "source_mapping": "working_unverified", "zero_scope": "Pravidla_1.4.6_p16-18_conditional"}

    def issue(row, path, code, message, basis="input_contract", review=False):
        (reviews if review else issues).append(Issue(row, path, code, message,
            "Doplňte/ověřte skutečný údaj, mapování a metodický podklad; hodnoty se neodhadují.", basis))

    pending = {a.row for a in assessments if a.identity_mode == "alternative_xsd_valid"}
    for item in payroll.issues:
        if item.row in pending and item.code in {"missing_identity", "identity_group_blocked"}:
            reviews.append(item)
        else:
            issues.append(item)
    for item in workforce_issues:
        if item.code in {"zero_income_methodology_review", "alternative_pairing_unresolved"}:
            reviews.append(item)
        else:
            issues.append(item)
    if len(source.rows) > 1500:
        issue(None, "records", "packet_limit", "Pracovní generátor nepřipravuje více než 1500 formulářů.")
        return EmployeeResult(None, tuple(issues), tuple(reviews), len(source.rows), False, evidence)
    if header_issues:
        return EmployeeResult(None, tuple(issues), tuple(reviews), len(source.rows), False, evidence)
    if header["year"] != str(context.period.year) or int(header["month"]) != context.period.month:
        issue(None, "period", "period_mismatch", "Hlavička neodpovídá kontextu organizace/měsíce.")
    counts = Counter(r.person_group for r in payroll.rows if r.person_group)
    internal_counts = Counter(r.metadata.get("internal_number") for r in payroll.rows)
    source_rows = {r.number: r for r in source.rows}
    assessed = {a.row: a for a in assessments}
    form_ids, ppvs, mapped = set(), set(), []
    for row in payroll.rows:
        meta, data = row.metadata, {}
        if internal_counts[meta.get("internal_number")] > 1:
            issue(row.number, "internal_number", "duplicate_internal_number", "Duplicitní interní číslo PP v zakázce; nelze rozlišit pracovní poměry.")
        kind = meta.get("employment_type", "").upper().replace("Č", "C")
        if meta.get("activity_code") not in ACTIVITIES.get(kind, ()):
            issue(row.number, "activity_code", "unsupported_activity", "Druh činnosti neodpovídá doloženému HPP/DPČ/DPP scénáři.", "CIS_Druh_cinnosti_and_bezPriznaku_annotation")
        if kind == "HPP" and meta.get("employment_detail") != "1":
            issue(row.number, "employment_detail", "specific_group_unconfirmed", "Pro běžný HPP potvrďte bližší určení 1 = Žádné; zvláštní skupiny nejsou tímto scénářem pokryté.")
        if meta.get("eldp_segments") != "1":
            issue(row.number, "eldp_segments", "segment_scope", "Doložte právě jeden ELDP úsek; rozdělení do více úseků zatím není implementované.")
        if meta.get("registration_status") not in {"registered", "pending_oic"}:
            issue(row.number, "registration_status", "registration_required", "Registrace zaměstnání není doložená.")
        identity = "bezPriznaku/identifikace/"
        if meta.get("oic") and meta.get("id_ppv"):
            data.update({identity + "ikMpsv": meta["oic"], identity + "idPpv": meta["id_ppv"]})
            key = (meta["oic"], meta["id_ppv"])
            if key in ppvs:
                issue(row.number, "id_ppv", "duplicate_ppv", "Duplicitní PPV jedné osoby v zakázce.")
            ppvs.add(key)
        elif row.number in pending:
            for tag, key in [("prijmeni", "surname"), ("jmeno", "given_name"), ("datumNarozeni", "birth_date"), ("datumNastupu", "employment_start"), ("druhCinnosti", "activity_code")]:
                data[identity + tag] = meta[key]
        else:
            issue(row.number, "identity", "identity_incomplete", "Chybí dvojice OIČ/PPV nebo doložená alternativa IN01.")
        if not meta.get("form_id") or meta["form_id"] in form_ids:
            issue(row.number, "form_id", "form_id_required_or_duplicate", "GUID formuláře chybí nebo se opakuje; interní UUID jej nenahrazuje.")
        form_ids.add(meta.get("form_id"))
        if row.primary_pp is None:
            issue(row.number, "primary_pp", "primary_unresolved", "Primární PP není prokázán; pracovní XML příznak neodhadne.", "control_332", review=True)
        for path, ref in profile["fields"].items():
            if ref.get("on") == "primary" and row.primary_pp is not True:
                continue
            column = ref.get("column") or (numbered["items"][ref["item"]]["column"] if "item" in ref else None)
            if column is not None and column not in source.columns:
                issue(row.number, path, "missing_column", "Chybí deklarovaný zdrojový sloupec zaměstnaneckého pole.")
                continue
            raw = row.calculations.get(ref["calculation"]) if "calculation" in ref else source_rows[row.number].values.get(column)
            if raw is None or isinstance(raw, str) and not raw.strip():
                # Blank optional values are omitted; required XSD/conditional fields are checked below.
                continue
            try:
                data[path] = normalized(raw, contract.fields[path].base_type)
            except ValueError:
                issue(row.number, path, "field_format", "Hodnota má nepodporovaný formát nebo přesnost; bez zaokrouhlování.")
        _method_checks(row, data, contract, context, header, counts, assessed[row.number], issue)
        try:
            payload, missing = contract.construct(data)
        except (ValueError, TypeError):
            issue(row.number, "xml", "xml_text_format", "Hodnotu nelze bezpečně zapsat do XML.")
            continue
        for path in missing:
            issue(row.number, path, "xsd_required", "Chybí povinný člen vybrané XSD struktury.", "official_XSD")
        mapped.append((row, payload))
    if profile["bundle_id"] == "jmhz-1.5.0.3":
        issue(None, "controls", "catalog_388_scope_review", "Kontrola 388 vyžaduje vyjasnění vztahu k povinným polím běžného formuláře v XSD 2027.", "control_388_vs_bezPriznaku_XSD", review=True)
    issue(None, "methodology", "coverage_incomplete", "Souhrnná a pojistná část zaměstnavatele, úplný katalog, účinnost a původ nejsou prokázány.", review=True)
    if issues:
        return EmployeeResult(None, tuple(issues), tuple(reviews), len(source.rows), False, evidence)
    try:
        xml = _packet(contract, header, mapped)
    except (ValueError, TypeError):
        issue(None, "xml", "xml_text_format", "Hlavičku nebo identifikaci nelze bezpečně zapsat do XML.")
        return EmployeeResult(None, tuple(issues), tuple(reviews), len(source.rows), False, evidence)
    result = contract.validator.validate(xml)
    if not result.xsd_valid:
        for row, payload in mapped:
            validation = contract.validator.validate(_packet(contract, header, [(row, payload)]))
            for error in validation.errors:
                issue(row.number, "xml", "xsd_invalid", error, "official_XSD")
        if not issues:
            issue(None, "xml", "xsd_invalid", "Celek neprošel skutečným XSD.", "official_XSD")
        xml = None
    return EmployeeResult(xml, tuple(issues), tuple(reviews), len(source.rows), result.xsd_valid, evidence)


def _packet(contract, header, records):
    from copy import deepcopy
    root = parse_local_xml(build_xml(contract.bundle, [], header))
    modern = contract.bundle["id"] == "jmhz-1.5.0.3"
    ns = contract.namespace if modern else contract.bundle["namespace"]
    container = etree.SubElement(root, "{" + contract.bundle["namespace"] + "}" + ("formulareZamestnani" if modern else "formulareOsob"))
    for row, payload in records:
        wrapper = etree.SubElement(container, "{" + ns + "}" + ("formularZamestnani" if modern else "formularOsoby"))
        head = etree.SubElement(wrapper, "{" + ns + "}hlavicka")
        etree.SubElement(head, "{" + ns + "}idFormulare").text = row.metadata["form_id"]
        etree.SubElement(head, "{" + ns + "}typFormulare").text = "R"
        if row.primary_pp is not None:
            etree.SubElement(head, "{" + ns + "}primarniPpv").text = "true" if row.primary_pp else "false"
        wrapper.append(deepcopy(payload))
    return etree.tostring(root.getroottree(), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def _method_checks(row, data, contract, context, header, counts, assessment, issue):
    def paths(id):
        return [p for p in data if id in contract.fields[p].ids]
    def value(id):
        matches = paths(id)
        return data[matches[0]] if len(matches) == 1 else None
    def number(id):
        v = value(id)
        try:
            return decimal_input(v) if v is not None else None
        except ValueError:
            return None
    def fail(code, field, text):
        issue(row.number, field, "control_" + code, text, "official_control_" + code)
    if row.primary_pp is True and not paths("10286"):
        fail("321", "10286", "Primární PP musí obsahovat doloženou souhrnnou vrstvu; údaje jiných PP se automaticky nesčítají.")
    if row.primary_pp is False and any(p.startswith("bezPriznaku/souhrnDataZec/") for p in data):
        fail("248", "souhrnDataZec", "Neprimární PP nesmí obsahovat osobní souhrnnou vrstvu.")
    try:
        start, end = date.fromisoformat(value("10354") or ""), date.fromisoformat(value("10355") or "")
        filled = datetime.fromisoformat(header["filled_at"].replace("Z", "+00:00")).date()
        if start > end or start > filled:
            fail("43", "10354", "Pojištění od musí předcházet konci a datu vyplnění.")
        if end < start or end > filled:
            fail("44", "10355", "Pojištění do musí následovat po začátku a nepřekročit datum vyplnění.")
        if any((v.year, v.month) != (context.period.year, context.period.month) for v in (start, end)):
            fail("299", "10354/10355", "Interval pojištění neleží ve vykazovaném měsíci.")
    except ValueError:
        issue(row.number, "10354/10355", "insurance_dates_required", "Doplňte skutečná data pojištění ve formátu YYYY-MM-DD.")
    days = number("10356")
    if days is not None and days > calendar.monthrange(context.period.year, context.period.month)[1]:
        fail("58", "10356", "Počet započtených dnů překračuje počet dnů měsíce.")
    for parent, children, code in [("10328", ("10329", "10330", "10331", "10332", "10333", "10334", "10335", "10336"), "267"),
                                    ("10268", ("10269", "10270", "10271", "10272", "10273", "10274") + (("10580",) if contract.bundle["id"] == "jmhz-1.5.0.3" else ()), "282"),
                                    ("10275", ("10276", "10278", "10277", "10279", "10280", "10471", "10472"), "286")]:
        if number(parent) == 0 and any(paths(i) for i in children):
            fail(code, parent, "Při nulovém celku nesmějí být uvedené rozkladové hodnoty; i vyplněná nula je údaj.")
    if number("10276") is not None and number("10279") is not None and number("10276") < number("10279"):
        fail("23", "10276", "Hodiny dovolené překračují hodiny s náhradou/nekrácením mzdy.")
    if any(paths(i) for i in ("10477", "10478", "10479", "10480")):
        values = [number(i) for i in ("10477", "10478", "10479", "10480")]
        with localcontext() as dc:
            dc.prec = 128
            if any(v is None for v in values) or values[0] != sum(values[1:], Decimal(0)):
                fail("216", "10477", "Vyměřovací základ neodpovídá úplnému řádkovému rozkladu; chybějící hodnoty nejsou nula.")
    if not paths("10535") or contract.bundle["id"] == "jmhz-1.5.0.3" and not paths("10555"):
        issue(row.number, "prijem/dan", "pilot_income_required", "Pracovní rozsah vyžaduje výslovné daňové příjmy; prázdný příjem nelze odhadnout.")
    if assessment.income_state == "zero":
        meta = row.metadata
        try:
            first = date(context.period.year, context.period.month, 1)
            last = date(context.period.year, context.period.month, calendar.monthrange(context.period.year, context.period.month)[1])
            active = date.fromisoformat(meta.get("employment_start", "")) <= first and (not meta.get("employment_end") or date.fromisoformat(meta["employment_end"]) >= last)
        except ValueError:
            active = False
        if not active or meta.get("registration_status") != "registered" or meta.get("work_performed") != "no" or counts.get(row.person_group, 0) != 1:
            issue(row.number, "zero_income", "zero_scope_unresolved", "Nula sama neurčuje vykázání: tento nulový scénář vyžaduje registrovaný celý měsíc bez práce a jediný PP osoby.")
            return
        zero_ids = ("10286", "10344", "10482", "10371", "10259", "10260", "10261", "10265", "10268", "10328", "10345", "10356", "10481", "10370", "10535")
        false_ids = ("10116", "10232", "10247", "10251", "10372", "10490", "10546")
        for id in zero_ids:
            if number(id) != 0:
                issue(row.number, id, "zero_document_value_required", "Doložený nulový formulář vyžaduje explicitní nulovou hodnotu tohoto atributu.", "Pravidla_1.4.6_p16-18")
        for id in false_ids:
            if value(id) not in {"false", "0"}:
                issue(row.number, id, "zero_document_flag_required", "Doložený nulový formulář vyžaduje explicitní příznak NE.", "Pravidla_1.4.6_p16-18")
        for id in ("10419", "10319", "10320"):
            if value(id) is None:
                issue(row.number, id, "zero_document_fact_required", "Doplňte skutečný příznak požadovaný tabulkou nulového formuláře; není odvozen z příjmu.", "Pravidla_1.4.6_p16-18")
        for id in ("10229", "10230", "10231"):
            if value(id) is None:
                issue(row.number, id, "zero_document_fact_required", "Doplňte skutečné místo výkonu práce požadované tabulkou nulového formuláře.", "Pravidla_1.4.6_p16-18")
        for id, expected in [("10354", first.isoformat()), ("10355", last.isoformat()), ("10241", first.isoformat()), ("10242", last.isoformat())]:
            if (id in {"10354", "10355"} or paths(id)) and value(id) != expected:
                issue(row.number, id, "zero_document_interval", "Doložený nulový scénář vyžaduje první/poslední den daného měsíce; datum se neopravuje odhadem.", "Pravidla_1.4.6_p16-18")
        if paths("10240") and number("10245") != 0:
            issue(row.number, "10245", "zero_eldp_base_required", "Při uvedeném kódu ELDP vyžaduje nulový scénář nulový vyměřovací základ.", "Pravidla_1.4.6_p16-18")


def main():
    import argparse
    from pathlib import Path
    from app.core.organizations import OrganizationWorkspace
    from app.core.resources import default_official_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--import-id", required=True)
    parser.add_argument("--employee-profile", type=Path)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, default=default_official_root())
    parser.add_argument("--write-draft", action="store_true")
    args = parser.parse_args()
    try:
        workspace = OrganizationWorkspace(args.workspace)
        imported = workspace.get_import(args.organization, args.import_id)
        if args.employee_profile:
            profile = strict_json(args.employee_profile.read_text(encoding="utf-8"))
        else:
            from app.core.packages import load_package
            definition = imported.definition
            if definition["kind"] != "pinned_package_manifest":
                raise ValueError("Chybí zaměstnanecký profil.")
            profile = strict_json(load_package(Path(definition["directory"]), definition["sha256"]).read_entry("employee_profile"))
        identity, result = workspace.prepare_employee_draft(args.organization, args.import_id, profile,
            strict_json(args.parameters.read_text(encoding="utf-8")), args.official_root)
        if args.write_draft and identity:
            workspace.write_draft(args.organization, args.import_id, identity)
        report = result.safe_report()
        report["draft_written"] = bool(identity and args.write_draft)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if result.xsd_valid else 1
    except Exception:
        parser.exit(2, "Pracovní zaměstnanecké XML nelze připravit. Ověřte organizaci, import, definice a hlavičku; citlivé hodnoty se nevypisují.\n")


if __name__ == "__main__":
    raise SystemExit(main())
