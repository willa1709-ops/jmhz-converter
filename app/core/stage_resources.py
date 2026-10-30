"""Příprava hashově ověřených runtime XSD bez archivů, PDF nebo místní SQLite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import unicodedata

from app.core.resources import default_official_root
from app.core.schemas import is_below, registered_validator


def stage_schemas(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or is_below(destination, source):
        raise ValueError("Cíl musí být nový a mimo oficiální podklady.")
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("format_version") != 1:
        raise ValueError("Neznámý manifest.")
    selected = [r for r in manifest["documents"] if r["kind"] == "xsd"]
    if not selected:
        raise ValueError("Žádná XSD k přípravě.")
    seen = set()
    for record in selected:
        relative = record["file"]
        logical = PurePosixPath(relative)
        key = unicodedata.normalize("NFC", relative).casefold()
        if logical.is_absolute() or ".." in logical.parts or "\\" in relative or ":" in relative or key in seen:
            raise ValueError("Nejednoznačná nebo nepovolená cesta manifestu.")
        seen.add(key)
        path = (source / record["file"]).resolve()
        if not is_below(path, source) or path.suffix.lower() != ".xsd" or path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("XSD cesta uniká z podkladů.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Nesouhlasí hash XSD.")
    bundles_bytes = (source / "bundles.json").read_bytes()
    bundles = json.loads(bundles_bytes)["bundles"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(destination.parent), prefix=".jmhz-resources-") as temporary:
        staged = Path(temporary) / "official"
        staged.mkdir()
        for record in selected:
            target = staged / record["file"]
            if not is_below(target.resolve(), staged):
                raise ValueError("Cílová cesta uniká ze stagingu.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / record["file"]).read_bytes())
        runtime_manifest = {"format_version": 1, "documents": selected, "purpose": "runtime_xsd_subset_only",
                            "parent_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
        (staged / "manifest.json").write_text(json.dumps(runtime_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (staged / "bundles.json").write_bytes(bundles_bytes)
        for bundle in bundles:
            registered_validator(staged, bundle["id"])
        if destination.exists():
            raise ValueError("Cílový adresář mezitím vznikl.")
        staged.rename(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--official-root", type=Path, default=default_official_root())
    args = parser.parse_args()
    try:
        stage_schemas(args.official_root, args.output / "schemas" / "official")
        print("Runtime XSD připravena a zkompilována. Původ ani účinnost tím nepotvrzujeme.")
        return 0
    except Exception:
        parser.exit(2, "Příprava resources selhala: ověřte hashe, XSD a nový cílový adresář.\n")


if __name__ == "__main__":
    raise SystemExit(main())
