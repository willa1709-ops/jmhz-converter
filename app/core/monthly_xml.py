"""Všechny tři části pracovního měsíčního paketu, bez neověřeného dopočtu."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, localcontext
import json

from lxml import etree

from app.core.employee_schema import EmployeeContract
from app.core.employee_xml import load_employee_profile, normalized, prepare_employee_xml
from app.core.models import Issue
from app.core.payroll import decimal_input, strict_json
from app.core.xml_support import parse_local_xml

# Paths and equations are evidenced by the supplied dictionaries and catalog 4/7/9/11/12/13.
PV_IDS = {"10023": "pojistne/zakladZamestnavateleA", "10024": "pojistne/pojistneZamestnavateleA",
          "10025": "pojistne/zakladZamestnavateleB", "10026": "pojistne/pojistneZamestnavateleB",
          "10483": "pojistne/zakladZamestnavateleC", "10484": "pojistne/pojistneZamestnavateleC",
          "10027": "pojistne/pojistneZamestnavateleCelkem", "10028": "pojistne/pojistneZamestnance",
          "10029": "pojistne/pojistneCelkem", "10033": "pojistneUhrada",
          "10032": "slevaZamestnavatele/pojistneSleva", "10487": "slevyZamestnancu/pojistneSleva",
          "10545": "slevyZamestnancuOvoZel/pojistneSleva"}
DERIVATIONS = {"7": ("10023", "10478"), "9": ("10025", "10479"), "12": ("10028", "10370"),
               "11": ("10027", ("10024", "10026", "10484")), "13": ("10029", ("10027", "10028")),
               "4": ("10033", ("10029", "10032", "10487", "10545"))}


def load_monthly_profile(text, contracts=None):
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Příliš velký profil souhrnů.")
    p = strict_json(text)
    if (not isinstance(p, dict) or set(p) != {"format_version", "bundle_id", "status", "metadata", "items", "fields"}
            or type(p["format_version"]) is not int or p["format_version"] != 1
            or p["bundle_id"] not in {"jmhz-1.4.3.6", "jmhz-1.5.0.3"} or p["status"] != "working_unverified"
            or not isinstance(p["metadata"], dict) or set(p["metadata"]) != {"period", "employer_ico", "employer_variable_symbol"}
            or any(not isinstance(v, str) or not v.strip() for v in p["metadata"].values())
            or not isinstance(p["items"], dict) or not isinstance(p["fields"], dict) or not 1 <= len(p["fields"]) <= 256):
        raise ValueError("Neplatný pracovní profil zaměstnavatele.")
    import re
    if any(not re.fullmatch(r"[0-9]{1,12}", key) or not isinstance(v, str) or not v.strip() for key, v in p["items"].items()):
        raise ValueError("Neplatné číslované položky zaměstnavatele.")
    for path, ref in p["fields"].items():
        if isinstance(ref, dict) and "control_sum" in ref:
            code = ref["control_sum"]
            if (not isinstance(code, str) or code not in DERIVATIONS or set(ref) - {"control_sum", "compare_column"}
                    or path != "PVPOJ/" + PV_IDS[DERIVATIONS[code][0]]
                    or "compare_column" in ref and (not isinstance(ref["compare_column"], str) or not ref["compare_column"].strip() or ref["compare_column"] in p["metadata"].values())):
                raise ValueError("Odvození musí přesně odpovídat doložené kontrolní rovnici a cíli.")
            if contracts is not None and path not in contracts["PVPOJ"].fields:
                raise ValueError("Cíl není v oficiálním kontraktu.")
            continue
        if (not isinstance(path, str) or path.split("/")[0] not in {"souhrn", "PVPOJ"} or not isinstance(ref, dict)
                or len(ref) != 1 or set(ref) not in ({"column"}, {"item"}) or not isinstance(next(iter(ref.values())), str)):
            raise ValueError("Nepodporovaná vazba souhrnu.")
        column = ref.get("column") or p["items"].get(ref.get("item"))
        if not column or column in p["metadata"].values():
            raise ValueError("Položka musí mít vlastní deklarovaný zdroj; identifikátor není částka.")
        if contracts is not None and path not in contracts[path.split("/")[0]].fields:
            raise ValueError("Souhrnné pole není v příslušném skutečném XSD.")
    return p


@dataclass(frozen=True)
class MonthlyResult:
    draft_xml: object = field(repr=False)
    issues: tuple
    review_issues: tuple
    xsd_valid: bool
    record_count: int
    evidence: dict
    submission_ready: bool = False

    def safe_report(self):
        return {"issues": [asdict(i) for i in self.issues], "review_issues": [asdict(i) for i in self.review_issues],
                "xsd_valid": self.xsd_valid, "record_count": self.record_count, "evidence": self.evidence, "submission_ready": False}


def prepare_monthly_xml(source, numbered, employee_profile, context, parameters, employer_source, monthly_profile, official_root):
    employee_profile = load_employee_profile(json.dumps(employee_profile))
    contracts = {name: EmployeeContract(official_root, employee_profile["bundle_id"], name) for name in ("souhrn", "PVPOJ")}
    monthly_profile = load_monthly_profile(json.dumps(monthly_profile), contracts)
    if monthly_profile["bundle_id"] != employee_profile["bundle_id"] or len(employer_source.rows) != 1:
        raise ValueError("Souhrn musí být jeden záznam stejné sady definic.")
    from app.core.periods import Period
    raw = employer_source.rows[0].values
    if (Period.parse(raw.get(monthly_profile["metadata"]["period"], ""), numbered["period_century"]) != context.period
            or raw.get(monthly_profile["metadata"]["employer_variable_symbol"]) != str(parameters.get("employer_variable_symbol", ""))):
        raise ValueError("Souhrn a hlavička nemají stejný měsíc/VS.")
    employee = prepare_employee_xml(source, numbered, employee_profile, context, parameters, official_root)
    issues = list(employee.issues)
    reviews = [i for i in employee.review_issues if i.code != "coverage_incomplete"]
    evidence = dict(employee.evidence, packet_components=["souhrn", "PVPOJ", "employees"],
                    employer_control_ids=["4", "7", "9", "11", "12", "13"], rates="not_inferred", catalog_coverage="partial")

    def finding(field_name, code, message, review=False):
        (reviews if review else issues).append(Issue(None, field_name, code, message,
            "Doplňte skutečné souhrny z účetnictví/exportu a ověřte metodický podklad; prázdný údaj není nula.", "official_catalog_subset"))

    data, nodes = {}, {}
    row = employer_source.rows[0]
    for path, ref in monthly_profile["fields"].items():
        if "control_sum" in ref:
            continue
        column = ref.get("column") or monthly_profile["items"][ref["item"]]
        if column not in employer_source.columns:
            finding(path, "employer_column_missing", "Chybí deklarovaný sloupec zaměstnavatelského exportu.")
            continue
        raw = row.values.get(column)
        if raw is None or isinstance(raw, str) and not raw.strip():
            continue
        try:
            data[path] = normalized(raw, contracts[path.split("/")[0]].fields[path].base_type)
        except ValueError:
            finding(path, "employer_format", "Neplatná hodnota/preciznost souhrnné položky.")
    employee_root = parse_local_xml(employee.draft_xml) if employee.draft_xml else None
    employee_contract = EmployeeContract(official_root, employee_profile["bundle_id"])
    def pp_values(attribute):
        paths = [p for p in employee_contract.fields.values() if attribute in p.ids]
        if employee_root is None or len(paths) != 1:
            return None
        matches = employee_root.findall(".//" + "/".join("{" + employee_contract.namespace + "}" + part for part in paths[0].path.split("/")))
        if len(matches) != employee.record_count:
            return None
        try:
            return [decimal_input(n.text) for n in matches]
        except ValueError:
            return None
    pending = {path: ref for path, ref in monthly_profile["fields"].items() if "control_sum" in ref}
    evidence["derived_control_ids"] = [ref["control_sum"] for ref in pending.values()]
    with localcontext() as dc:
        dc.prec = 128
        while pending:
            progress = False
            for path, ref in list(pending.items()):
                code = ref["control_sum"]
                _, source_ids = DERIVATIONS[code]
                if isinstance(source_ids, str):
                    values = pp_values(source_ids)
                else:
                    try:
                        values = [decimal_input(data["PVPOJ/" + PV_IDS[id]]) for id in source_ids]
                    except (KeyError, ValueError):
                        values = None
                if values is None:
                    continue
                value = values[0] - sum(values[1:], Decimal(0)) if code == "4" else sum(values, Decimal(0))
                try:
                    data[path] = normalized(value, contracts["PVPOJ"].fields[path].base_type)
                    if "compare_column" in ref:
                        column = ref["compare_column"]
                        if column not in employer_source.columns or decimal_input(row.values.get(column)) != value:
                            finding(path, "derived_control_mismatch", "Doložený výpočet nesouhlasí s kontrolním součtem z mzdového systému.")
                except ValueError:
                    finding(path, "derived_control_input", "Kontrolní hodnota chybí nebo výsledek nelze zapsat beze ztráty přesnosti.")
                del pending[path]
                progress = True
            if not progress:
                for path in pending:
                    finding(path, "documented_sum_missing_data", "Doložený součet nemá všechny skutečné vstupy. Neznámá částka není nula.")
                break
    for name, contract in contracts.items():
        try:
            nodes[name], missing = contract.construct({k: v for k, v in data.items() if k.startswith(name + "/")})
            for path in missing:
                finding(path, "employer_xsd_required", "Chybí povinný člen souhrnné nebo pojistné části.")
        except (ValueError, TypeError):
            finding(name, "employer_xml_text", "Souhrnnou část nelze bezpečně zapsat do XML.")
    for path, value in data.items():
        if path.endswith("/typKolektSmlouvy") and value not in {"0", "1", "2", "3", "4", "5"}:
            finding(path, "collective_code", "Hodnota kolektivní smlouvy není v doloženém číselníku.")
        if path.endswith("/formaVlastnictvi") and value not in {"1", "2", "3", "4"}:
            finding(path, "ownership_code", "Forma vlastnictví není v doloženém číselníku.")
    if context.period.month == 12 and not any(p.endswith("/formaVlastnictvi") for p in data):
        finding("10220", "december_ownership_required", "Pro prosincové hlášení chybí skutečná forma vlastnictví.")
    def amount(id):
        raw = data.get("PVPOJ/" + PV_IDS[id])
        try:
            return decimal_input(raw) if raw is not None else None
        except ValueError:
            return None
    with localcontext() as dc:
        dc.prec = 128
        for target, components, op, control in [("10027", ("10024", "10026", "10484"), "sum", "11"),
                    ("10029", ("10027", "10028"), "sum", "13"), ("10033", ("10029", "10032", "10487", "10545"), "subtract", "4")]:
            values = [amount(i) for i in components]
            if amount(target) is None or any(v is None for v in values):
                finding(target, "control_" + control + "_incomplete", "Kontrolní rovnice nemá všechny skutečné vstupy.", True)
            else:
                expected = sum(values, Decimal(0)) if op == "sum" else values[0] - sum(values[1:], Decimal(0))
                if amount(target) != expected:
                    finding(target, "control_" + control, "Dodaný součet zaměstnavatele nesouhlasí s doloženou rovnicí.")
    if employee.draft_xml:
        root = parse_local_xml(employee.draft_xml)
        employee_contract = EmployeeContract(official_root, employee_profile["bundle_id"])
        # Compare, never manufacture, the documented sums across the already selected PP.
        with localcontext() as dc:
            dc.prec = 128
            for target, attribute, control in [("10023", "10478", "7"), ("10025", "10479", "9"), ("10028", "10370", "12")]:
                paths = [p for p in employee_contract.fields.values() if attribute in p.ids]
                matches = root.findall(".//" + "/".join("{" + employee_contract.namespace + "}" + part for part in paths[0].path.split("/"))) if len(paths) == 1 else []
                if amount(target) is None or len(matches) != employee.record_count:
                    finding(target, "control_" + control + "_incomplete", "Chybí úplné podklady pro kontrolní součet přes PP.", True)
                else:
                    try:
                        expected = sum((decimal_input(n.text) for n in matches), Decimal(0))
                        if amount(target) != expected:
                            finding(target, "control_" + control, "Zaměstnavatelský součet neodpovídá dodaným hodnotám PP.")
                    except ValueError:
                        finding(target, "control_" + control, "Neplatný číselný podklad kontrolního součtu.")
        if not issues:
            root.insert(1, nodes["souhrn"])
            root.insert(2, nodes["PVPOJ"])
            xml = etree.tostring(root.getroottree(), encoding="UTF-8", xml_declaration=True, pretty_print=True)
            checked = contracts["PVPOJ"].validator.validate(xml)
            for error in checked.errors:
                finding("packet", "monthly_xsd_invalid", error)
            if not checked.xsd_valid:
                xml = None
        else:
            xml = None
    else:
        xml = None
    finding("methodology", "full_packet_review", "Všechny tři části jsou pracovní; úplný katalog, sazby, účinnost a přijetí podání nejsou prokázány.", True)
    return MonthlyResult(xml, tuple(issues), tuple(reviews), xml is not None, employee.record_count, evidence)
