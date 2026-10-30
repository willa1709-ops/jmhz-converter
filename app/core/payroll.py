"""Obecné číslované položky a přesné výpočty v jednom řádku. Python 3.8+."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, Inexact, Rounded, localcontext
import json
import re
from typing import Optional

from app.core.identities import EmploymentIdentity, canonical_identifier, numeric_key, pair_employments
from app.core.models import Issue
from app.core.periods import Period, SubmissionContext

LOGIC_API = 1
META_FIELDS = {"internal_number", "period", "oic", "rc", "form_id", "id_ppv", "activity_code"}


def strict_json(text: str):
    def reject_constant(_):
        raise ValueError("Neplatné JSON číslo.")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicitní klíč JSON.")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def decimal_input(value: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("Částka musí být text.")
    value = value.strip()
    if not re.fullmatch(r"[+-]?[0-9]{1,32}(?:[.,][0-9]{1,8})?", value):
        raise ValueError("Neplatná konečná částka nebo nepodporovaná přesnost.")
    return Decimal(value.replace(",", "."))


def load_numbered_profile(text: str) -> dict:
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Profil je příliš velký.")
    p = strict_json(text)
    required = {"format_version", "profile_id", "profile_version", "period_century", "items", "metadata", "calculations", "controls"}
    if not isinstance(p, dict) or set(p) != required or type(p["format_version"]) is not int or p["format_version"] != 1:
        raise ValueError("Neznámý formát profilu.")
    if not isinstance(p["profile_id"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", p["profile_id"]):
        raise ValueError("Neplatné ID profilu.")
    if not isinstance(p["profile_version"], str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", p["profile_version"]):
        raise ValueError("Neplatná verze profilu.")
    Period.parse("00-01", p["period_century"])
    if not isinstance(p["items"], dict) or not 1 <= len(p["items"]) <= 2048:
        raise ValueError("Neplatná sada položek.")
    for key, source in p["items"].items():
        if not re.fullmatch(r"[0-9]{1,12}", key) or not isinstance(source, dict) or set(source) != {"column"} or not isinstance(source["column"], str) or not source["column"].strip():
            raise ValueError("Položky mají číselné ID a název zdrojového sloupce.")

    def source_column(ref):
        if not isinstance(ref, dict):
            raise ValueError("Neplatný odkaz.")
        if set(ref) == {"column"} and isinstance(ref["column"], str) and ref["column"].strip():
            return ref["column"]
        if set(ref) == {"item"} and isinstance(ref["item"], str) and ref["item"] in p["items"]:
            return p["items"][ref["item"]]["column"]
        raise ValueError("Neplatný zdroj metadat.")

    meta = p["metadata"]
    if not isinstance(meta, dict) or set(meta) - META_FIELDS or not {"internal_number", "period"} <= set(meta) or not ({"oic", "rc"} & set(meta)):
        raise ValueError("Chybí metadata PP, období nebo identifikační zdroj.")
    for ref in meta.values():
        source_column(ref)
    private_columns = {source_column(meta[k]) for k in ("oic", "rc") if k in meta}
    calculations = p["calculations"]
    if not isinstance(calculations, dict) or len(calculations) > 512:
        raise ValueError("Neplatné výpočty.")
    for name in calculations:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
            raise ValueError("Neplatné ID výpočtu.")
    visited = [0]

    def validate_expr(expr, stack, depth):
        visited[0] += 1
        if visited[0] > 10000 or depth > 16 or not isinstance(expr, dict):
            raise ValueError("Příliš složitý výpočet.")
        if set(expr) == {"item"} and isinstance(expr["item"], str) and expr["item"] in p["items"]:
            if p["items"][expr["item"]]["column"] in private_columns:
                raise ValueError("Identifikační sloupec nesmí vstoupit do finančních výpočtů.")
        elif set(expr) == {"calculation"} and isinstance(expr["calculation"], str) and expr["calculation"] in calculations:
            name = expr["calculation"]
            if name in stack:
                raise ValueError("Cyklus ve výpočtu.")
            validate_expr(calculations[name], stack + (name,), depth + 1)
        elif set(expr) == {"op", "args"} and expr["op"] in ("add", "subtract") and isinstance(expr["args"], list) and 2 <= len(expr["args"]) <= 64:
            for child in expr["args"]:
                validate_expr(child, stack, depth + 1)
        else:
            raise ValueError("Nepodporovaná operace nebo odkaz.")
    for name, expr in calculations.items():
        validate_expr(expr, (name,), 0)
    if not isinstance(p["controls"], list) or len(p["controls"]) > 512:
        raise ValueError("Neplatné kontroly součtů.")
    for check in p["controls"]:
        if (not isinstance(check, dict) or set(check) != {"calculation", "item", "tolerance"}
                or not isinstance(check["calculation"], str) or not isinstance(check["item"], str)
                or check["calculation"] not in calculations or check["item"] not in p["items"]):
            raise ValueError("Neplatná kontrola součtu.")
        if p["items"][check["item"]]["column"] in private_columns or decimal_input(check["tolerance"]) < 0:
            raise ValueError("Neplatný kontrolní zdroj nebo tolerance.")
    return p


@dataclass(frozen=True)
class PayrollRow:
    number: int
    period: Period
    metadata: dict = field(repr=False)
    items: dict = field(repr=False)
    calculations: dict = field(repr=False)
    person_group: Optional[str] = None
    primary_pp: Optional[bool] = None


@dataclass(frozen=True)
class PayrollResult:
    context: SubmissionContext
    rows: tuple
    issues: tuple
    submission_ready: bool = False

    def safe_report(self) -> dict:
        return {"period": self.context.period.iso, "internal_revision": self.context.revision_index,
                "record_count": len(self.rows), "issues": [asdict(i) for i in self.issues],
                "rows": [{"row": r.number, "person_group": r.person_group, "primary_pp": r.primary_pp} for r in self.rows],
                "submission_ready": False}


def prepare_payroll(source, profile: dict, context: SubmissionContext) -> PayrollResult:
    from dataclasses import replace
    profile = load_numbered_profile(json.dumps(profile))
    if len(source.rows) * (len(profile["items"]) + len(profile["calculations"]) + len(profile["metadata"])) > 1_000_000:
        return PayrollResult(context, (), (Issue(None, "input", "work_limit", "Zakázka překračuje limit pracovních buněk.", "Zmenšete zakázku pro paměťové limity x86."),))
    issues, rows, identities = [], [], []
    if len({r.number for r in source.rows}) != len(source.rows):
        raise ValueError("Nejednoznačná čísla zdrojových řádků.")
    if not source.rows:
        issues.append(Issue(None, "input", "empty_input", "Chybí řádky pracovních poměrů.", "Doplňte skutečný export."))
    meta_columns = {k: (v["column"] if "column" in v else profile["items"][v["item"]]["column"]) for k, v in profile["metadata"].items()}
    required_columns = set(meta_columns.values()) | {v["column"] for v in profile["items"].values()}
    if required_columns - set(source.columns):
        issues.append(Issue(None, "columns", "missing_columns", "Chybí sloupce definované profilem.", "Ověřte mapování čísel položek na exportní hlavičky."))
        return PayrollResult(context, (), tuple(issues))
    for source_row in source.rows:
        def issue(field_name, code, message):
            issues.append(Issue(source_row.number, field_name, code, message, "Ověřte a doplňte skutečný údaj ve zdroji."))
        metadata, invalid = {}, False
        for key, column in meta_columns.items():
            raw = source_row.values.get(column)
            if raw is not None and not isinstance(raw, str):
                raw = None
                invalid = True
                issue("metadata", "metadata_type", "Metadata musí být textová.")
            metadata[key] = raw.strip() if raw else ""
            if key in {"oic", "rc", "internal_number", "id_ppv"} and column in source_row.numeric_columns:
                invalid = True
                metadata[key] = ""
                issue("identity", "numeric_identifier", "Identifikátor byl v XLSX číselný; nelze obnovit počáteční nuly.")
        try:
            period = Period.parse(metadata["period"], profile["period_century"])
        except ValueError:
            period, invalid = context.period, True
            issue("period", "invalid_period", "Neplatné vykazované období řádku.")
        if period != context.period:
            invalid = True
            issue("period", "period_mismatch", "Řádek patří do jiného období zakázky.")
        try:
            numeric_key(metadata["internal_number"])
        except ValueError:
            invalid = True
            issue("internal_number", "invalid_internal_number", "Chybí textové interní číslo PP nebo neobsahuje pouze číslice.")
        for kind in ("oic", "rc"):
            try:
                metadata[kind] = canonical_identifier(metadata.get(kind, ""), kind)
            except ValueError:
                invalid = True
                metadata[kind] = None
                issue("identity", "identity_format", "Identifikační údaj má neplatný formát.")
        if not (metadata["oic"] or metadata["rc"]):
            invalid = True
            issue("identity", "missing_identity", "Chybí OIČ i RČ pro párování pracovních poměrů.")
        identities.append(EmploymentIdentity(source_row.number, period, metadata["internal_number"], metadata["oic"], metadata["rc"], invalid))
        items = {key: source_row.values.get(ref["column"]) for key, ref in profile["items"].items()}
        memo = {}

        def calculate(name):
            if name not in memo:
                try:
                    memo[name] = evaluate(profile["calculations"][name])
                except (ValueError, ArithmeticError):
                    memo[name] = None
                    issue("calculation:" + name, "calculation_input", "Výpočet nemá všechny platné vstupy nebo překračuje přesnost.")
            if memo[name] is None:
                raise ValueError("Výpočet je neúplný.")
            return memo[name]

        def evaluate(expr):
            if "item" in expr:
                return decimal_input(items[expr["item"]])
            if "calculation" in expr:
                return calculate(expr["calculation"])
            args = [evaluate(a) for a in expr["args"]]
            value = args[0]
            for arg in args[1:]:
                value = value + arg if expr["op"] == "add" else value - arg
            return value

        with localcontext() as decimal_context:
            decimal_context.prec = 128
            decimal_context.traps[Inexact] = True
            decimal_context.traps[Rounded] = True
            for name in profile["calculations"]:
                try:
                    calculate(name)
                except (ValueError, ArithmeticError):
                    pass
            for check in profile["controls"]:
                value = memo.get(check["calculation"])
                if value is None:
                    continue
                try:
                    expected = decimal_input(items[check["item"]])
                    if (value - expected).copy_abs() > decimal_input(check["tolerance"]):
                        issue("control:" + check["calculation"], "control_mismatch", "Kontrolní součet zdroje nesouhlasí s výpočtem tohoto řádku.")
                except (ValueError, ArithmeticError):
                    issue("control:" + check["calculation"], "control_input", "Kontrolní součet chybí nebo nemá platný číselný formát.")
        rows.append(PayrollRow(source_row.number, period, metadata, items, memo))
    assignments, pairing_issues = pair_employments(identities)
    issues.extend(pairing_issues)
    rows = [replace(r, person_group=assignments[r.number].person_group, primary_pp=assignments[r.number].primary_pp)
            if r.number in assignments else r for r in rows]
    return PayrollResult(context, tuple(rows), tuple(issues))


def main() -> int:
    import argparse
    from pathlib import Path
    from app.core.input import read_csv, read_xlsx
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--profile", type=Path)
    choice.add_argument("--package", type=Path)
    parser.add_argument("--trusted-manifest-sha256")
    parser.add_argument("--period", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--record-revision", type=Path)
    parser.add_argument("--scope")
    parser.add_argument("--parameters", type=Path)
    parser.add_argument("--draft-output", type=Path)
    args = parser.parse_args()
    try:
        import hashlib
        if args.package:
            from app.core.packages import load_package
            package = load_package(args.package, args.trusted_manifest_sha256 or "")
            profile, fingerprint, kind = package.profile, package.manifest_sha256, "pinned_package_manifest"
        else:
            if args.trusted_manifest_sha256:
                raise ValueError("Hash balíčku nelze použít pro lokální profil.")
            raw_profile = args.profile.read_text(encoding="utf-8")
            profile = load_numbered_profile(raw_profile)
            fingerprint, kind = hashlib.sha256(raw_profile.encode("utf-8")).hexdigest(), "local_working_profile"
        context = SubmissionContext(Period.parse(args.period, profile["period_century"]), args.revision)
        table = read_xlsx(args.input) if args.input.suffix.lower() == ".xlsx" else read_csv(args.input)
        conversion = None
        if args.parameters:
            if not args.package or "conversion_profile" not in package.manifest["entry_points"]:
                raise ValueError("XML pracovní převod vyžaduje ověřený konverzní balíček.")
            from app.core.payroll_conversion import prepare_numbered_conversion
            points = package.manifest["entry_points"]
            prepared = prepare_numbered_conversion(table, profile, context,
                strict_json(package.read_entry("conversion_profile")),
                strict_json(package.read_entry("bindings")),
                strict_json(args.parameters.read_text(encoding="utf-8")), package.directory / points["official_root"])
            result, conversion = prepared.payroll, prepared.conversion
        else:
            result = prepare_payroll(table, profile, context)
        if args.draft_output:
            if not args.parameters or not args.draft_output.name.lower().endswith(".draft.xml"):
                raise ValueError("Zapisovat lze jen výslovný pracovní soubor po XSD kontrole.")
            if conversion is not None and conversion.draft_xml is not None:
                with args.draft_output.open("xb") as handle:
                    handle.write(conversion.draft_xml)
        if bool(args.record_revision) != bool(args.scope):
            raise ValueError("Evidence revize potřebuje databázi i neosobní scope.")
        if args.record_revision and not result.issues and (not args.parameters or conversion is not None and conversion.xsd_valid):
            from app.core.periods import RevisionRegistry
            RevisionRegistry(args.record_revision).record(args.scope, context, fingerprint, kind)
        report = result.safe_report()
        if args.parameters:
            report["xsd_valid"] = bool(conversion and conversion.xsd_valid)
            report["conversion_issues"] = [asdict(i) for i in conversion.issues] if conversion else []
            report["methodological_validation"] = "incomplete"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if result.issues or args.parameters and not (conversion and conversion.xsd_valid) else 0
    except Exception:
        parser.exit(2, "Zpracování položek selhalo; ověřte profil, kontext a vstup. Identifikátory se nevypisují.\n")


if __name__ == "__main__":
    raise SystemExit(main())
