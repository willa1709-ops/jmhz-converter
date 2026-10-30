import argparse
from dataclasses import asdict
import json
from pathlib import Path

from app.xml.bundle import BundleValidator, registered_validator


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokální XSD kontrola; není potvrzením připravenosti JMHZ k podání.")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--bundle-root", type=Path)
    parser.add_argument("--bundle-id")
    parser.add_argument("--official-root", type=Path, default=Path("schemas/official"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.bundle_id:
            if args.schema or args.bundle_root or args.manifest:
                raise ValueError("Vyberte jednu cestu konfigurace.")
            validator = registered_validator(args.official_root, args.bundle_id)
        elif args.schema and args.bundle_root:
            hashes = None
            if args.manifest:
                manifest_root = args.manifest.resolve().parent
                hashes = {}
                for item in json.loads(args.manifest.read_text())["documents"]:
                    path = (manifest_root / item["file"]).resolve()
                    if path.is_relative_to(args.bundle_root.resolve()) and path.suffix == ".xsd":
                        hashes[path.relative_to(args.bundle_root.resolve()).as_posix()] = item["sha256"]
            validator = BundleValidator(args.schema, args.bundle_root, hashes)
        else:
            raise ValueError("Zvolte --bundle-id nebo --schema a --bundle-root.")
        if args.xml.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("Nadlimitní soubor.")
        result = validator.validate(args.xml.read_bytes())
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0 if result.xsd_valid else 1
    except Exception:
        parser.exit(2, "Validátor nelze spustit: ověřte XSD balíček, hash, závislosti a vstupní cestu.\n")


if __name__ == "__main__":
    raise SystemExit(main())
