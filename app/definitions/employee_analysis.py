"""Reproducible employee evidence from verified original workbooks and XSD.

This is an authoring tool, not runtime payroll rule evaluation. Excel formulas
are preserved as text and are never executed.
"""
import hashlib
import json
from pathlib import Path
import re

from app.core.employee_schema import EmployeeContract
from app.core.employee_xml import IMPLEMENTED_CONTROLS
from app.definitions.workbooks import table_records


def analyze(root: Path, destination: Path):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["documents"]
    destination.mkdir(parents=True, exist_ok=True)
    result = {}
    for year, bundle in [("2026", "jmhz-1.4.3.6"), ("2027", "jmhz-1.5.0.3")]:
        sources = [r for r in manifest if r["file"].startswith(year + "/") and r["kind"] in {"data_dictionary", "control_catalog", "methodology", "scenarios"}]
        for record in sources:
            if hashlib.sha256((root / record["file"]).read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("Source document does not match catalog hash.")
        dictionary = next(r for r in sources if r["kind"] == "data_dictionary")
        controls = next(r for r in sources if r["kind"] == "control_catalog")
        dictionary_rows = table_records((root / dictionary["file"]).read_bytes(), "SLOVNÍK", 2)
        control_rows = table_records((root / controls["file"]).read_bytes(), "MH", 1)
        contract = EmployeeContract(root, bundle)
        fields = []
        attribute_ids = {"10005", "10010", "10011", "10239", "10495", "10502"}
        for particle in contract.fields.values():
            attribute_ids.update(particle.ids)
            fields.append({"path": particle.path, "ids_in_annotation": particle.ids, "xsd_type": particle.type_name,
                           "base_type": particle.base_type, "local_min_occurs": particle.minimum, "local_max_occurs": particle.maximum,
                           "xsd_file": particle.file, "xsd_line": particle.line})
        dictionary_evidence = {}
        for id in sorted(attribute_ids):
            if id not in dictionary_rows:
                continue
            row = dictionary_rows[id]
            dictionary_evidence[id] = {"sheet": row["sheet"], "row": row["row"], "fields":
                {k: v for k, v in row["fields"].items() if k in {"NÁZEV ATRIBUTU", "DATOVÝ TYP", "ČETNOST", "ČÍSELNÍK", "POZNÁMKA K ATRIBUTU"}
                 or k.startswith(("XSD MAPOVÁNÍ MH", "VÝPOČET -"))}}
        relevant = {}
        for id, row in control_rows.items():
            ids_cell = row["fields"].get("Seznam ID atributů, kterých se kontrola týká", {})
            if not attribute_ids.intersection(re.findall(r"\b10\d{3}\b", str(ids_cell.get("value", "")))):
                continue
            relevant[id] = {"source": {"sheet": row["sheet"], "row": row["row"], "fields": {k: v for k, v in row["fields"].items()
                if k in {"Název kontroly", "Detailní popis prováděné kontroly", "Seznam ID atributů, kterých se kontrola týká", "Kategorie kontroly"}
                or k.startswith(("Typ formuláře", "Propustnost / Nepropustnost kontrol na DIS"))}},
                            "implementation": "supported_subset_or_by_construction" if id in IMPLEMENTED_CONTROLS else "not_implemented",
                            "excel_formulas_executable": False}
        evidence = {"bundle_id": bundle, "status": "technical_evidence_origin_and_effectivity_unconfirmed",
                    "sources": sources, "fields": fields, "dictionary_attributes": dictionary_evidence, "related_controls": relevant,
                    "construction_scope": "one_occurrence_per_repeating_element_one_eldp_segment",
                    "limitations": ["local minOccurs does not imply global obligation through optional parents or choices",
                                    "primary-person totals require explicit primary-only mapping, not payroll-row aggregation",
                                    "zero scenario requires Pravidla 1.4.6 pages 16-18 facts, not just zero income",
                                    "control 134 and 368 interval endpoints need interpretation before implementation",
                                    "2027 control 388 scope versus required bezPriznaku XSD fields needs review",
                                    "employer summary, PVPOJ, external register checks and tax thresholds are incomplete"]}
        (destination / ("employee-" + year + ".json")).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result[year] = evidence
    left = {f["path"]: f for f in result["2026"]["fields"]}
    right = {f["path"]: f for f in result["2027"]["fields"]}
    difference = {"added_paths": sorted(set(right) - set(left)), "removed_paths": sorted(set(left) - set(right)),
                  "changed_paths": {p: {"2026": {k: left[p][k] for k in ("xsd_type", "base_type", "local_min_occurs")},
                                         "2027": {k: right[p][k] for k in ("xsd_type", "base_type", "local_min_occurs")}}
                                    for p in sorted(set(left) & set(right)) if any(left[p][k] != right[p][k] for k in ("xsd_type", "base_type", "local_min_occurs"))}}
    (destination / "employee-differences.json").write_text(json.dumps(difference, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {y: {"fields": len(e["fields"]), "related_controls": len(e["related_controls"])} for y, e in result.items()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-root", type=Path, default=Path("schemas/official"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.official_root, args.output)))
