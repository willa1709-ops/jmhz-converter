"""Offline experimentální CSV → pracovní XML; žádný finální export."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from app.core.conversion import prepare_conversion
from app.core.input import read_csv, read_xlsx
from app.core.mapping import load_profile
from app.core.methodology import FINAL_BLOCKERS
from app.core.resources import default_official_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, default=default_official_root())
    parser.add_argument("--encoding", choices=["auto", "utf-8-sig", "cp1250"], default="auto")
    parser.add_argument("--delimiter", choices=["auto", ";", ",", "\t", "|"], default="auto")
    parser.add_argument("--draft-output", type=Path)
    args = parser.parse_args()
    try:
        if args.draft_output and not args.draft_output.name.lower().endswith(".draft.xml"):
            raise ValueError("Pracovní soubor musí končit .draft.xml.")
        profile = load_profile(args.profile.read_text(encoding="utf-8"))
        parameters = json.loads(args.parameters.read_text(encoding="utf-8"))
        if not isinstance(parameters, dict):
            raise ValueError("Parametry musí být objekt.")
        source = read_xlsx(args.input) if args.input.suffix.lower() == ".xlsx" else read_csv(args.input, args.encoding, args.delimiter)
        result = prepare_conversion(source, profile, parameters, args.official_root)
        if args.draft_output and result.draft_xml is not None:
            # Exclusive create: do not overwrite an existing user's draft.
            with args.draft_output.open("xb") as output:
                output.write(result.draft_xml)
        print(json.dumps({"record_count": result.record_count, "xsd_valid": result.xsd_valid,
                          "issues": [asdict(issue) for issue in result.issues],
                          "methodological_validation": result.methodological_validation,
                          "official_origin": result.official_origin, "submission_ready": False,
                          "final_export_blockers": FINAL_BLOCKERS}, ensure_ascii=False, indent=2))
        return 0 if result.xsd_valid else 1
    except Exception:
        parser.exit(2, "Konverzi nelze připravit. Ověřte vstupní cestu, CSV, profil, parametry a hashe podkladů.\n")


if __name__ == "__main__":
    raise SystemExit(main())
