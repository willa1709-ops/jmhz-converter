import re

from app.calculations import MONEY_FIELDS, decimal_value
from app.models import Dataset, Finding, Severity


def validate(data: Dataset, expected_period: str | None = None) -> list[Finding]:
    findings = [Finding(Severity.INFO, None, "", "definition", "Definice JMHZ není ověřena; nejde o kontrolu podání.",
                        "Doplňte oficiální podklady a jejich pravidla.")]
    seen: dict[tuple[str, str], int] = {}
    duplicates: set[int] = set()
    by_number = {r.number: r for r in data.rows}
    for row in data.rows:
        values = row.values
        key = (values.get("employee_id", ""), values.get("period", ""))
        def report(field: str, message: str, remedy: str, severity: Severity = Severity.ERROR) -> None:
            findings.append(Finding(severity, row.number, key[0], field, message, remedy))
        for field in ("employee_id", "period", "income"):
            if not values.get(field, "").strip():
                report(field, "Chybí povinný údaj pracovního profilu.", "Doplňte hodnotu nebo mapování.")
        if len(key[0]) > 100 or any(ord(c) < 32 for c in key[0]):
            report("employee_id", "Neplatný technický identifikátor.", "Použijte text do 100 znaků bez řídicích znaků.")
        if key[1] and not re.fullmatch(r"[1-9][0-9]{3}-(0[1-9]|1[0-2])", key[1]):
            report("period", "Neplatné období.", "Použijte YYYY-MM.")
        if expected_period and key[1] != expected_period:
            report("period", "Období neodpovídá vybranému měsíci.", "Ověřte soubor a vybrané období.")
        if all(key):
            if key in seen:
                report("employee_id", "Duplicitní zaměstnanec a měsíc.", "Odstraňte duplicitu nebo vyřešte více vztahů samostatně.")
                duplicates.add(seen[key])
            else:
                seen[key] = row.number
        for field in MONEY_FIELDS:
            raw = values.get(field, "").strip()
            if not raw:
                continue
            try:
                value = decimal_value(raw)
                if value.as_tuple().exponent < -2:
                    report(field, "Částka má více než dvě desetinná místa.", "Ověřte přesnost; případné zaokrouhlení nastavte výslovně.")
                if value < 0:
                    report(field, "Záporná částka – ověřte případnou korekci.", "Zkontrolujte zdroj a metodiku.", Severity.WARNING)
            except ValueError:
                report(field, "Neplatná částka.", "Použijte číslo s čárkou nebo tečkou, bez tisícových oddělovačů.")
    for number in sorted(duplicates):
        row = by_number[number]
        findings.append(Finding(Severity.ERROR, number, row.values["employee_id"], "employee_id",
                                "Duplicitní zaměstnanec a měsíc.", "Ověřte všechny výskyty klíče."))
    return findings
