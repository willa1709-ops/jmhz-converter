"""Lokální registr dokumentů v schemas/official; bez síťové komunikace."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from app.definitions.library import DefinitionLibrary


def register(root: Path, path: Path, source: str, version: str, kind: str,
             effective_from: str | None = None, effective_until: str | None = None) -> dict:
    root, path = root.resolve(), path.resolve()
    relative = path.relative_to(root)
    if not relative.parts or not path.is_file():
        raise ValueError("Dokument musí být soubor uvnitř schemas/official.")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"format_version": 1, "documents": []}
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("documents"), list):
        raise ValueError("Neznámý formát existujícího manifestu; nebyl změněn.")
    library = DefinitionLibrary(root / ".catalog.sqlite3")
    id_ = library.import_document(path, source, version, kind, effective_from, effective_until)
    document = library.get(id_).artifact.as_dict()
    document["file"] = relative.as_posix()
    # Technical validation and origin review are independent facts.
    document["origin_review"] = {"status": "unverified", "reviewer": None, "reviewed_at": None, "evidence": None}
    if hashlib.sha256(path.read_bytes()).hexdigest() != document["sha256"]:
        raise ValueError("Soubor se během registrace změnil; manifest nebyl uložen.")
    existing = next((d for d in manifest["documents"] if d["file"] == document["file"] and d["sha256"] == document["sha256"] and d["version"] == document["version"] and d["source_url"] == document["source_url"]), None)
    if existing is not None:
        return existing
    manifest["documents"].append(document)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, prefix=".manifest-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(manifest_path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return document


def verify(root: Path) -> list[str]:
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Neznámý formát manifestu.")
    failures = []
    for entry in manifest["documents"]:
        path = (root / entry["file"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            failures.append(f"Chybějící nebo nepovolená cesta: {entry['file']}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            failures.append(f"Nesouhlasí SHA-256: {entry['file']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("schemas/official"))
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("register")
    command.add_argument("file", type=Path)
    command.add_argument("--source", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--kind", choices=["xsd", "codelist", "methodology"], required=True)
    command.add_argument("--effective-from")
    command.add_argument("--effective-until")
    sub.add_parser("verify")
    args = parser.parse_args()
    try:
        if args.command == "register":
            record = register(args.root, args.file, args.source, args.version, args.kind, args.effective_from, args.effective_until)
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return 0
        failures = verify(args.root)
        for failure in failures:
            print(failure)
        if not failures:
            print("Kontrola hashů dokončena. Neprokazuje oficiální původ ani úplnost definic.")
        return int(bool(failures))
    except Exception:
        # Parser errors can contain document data; don't print their raw text.
        parser.exit(2, "Registrace/kontrola selhala. Ověřte cestu, metadata a podporovaný formát dokumentu.\n")


if __name__ == "__main__":
    raise SystemExit(main())
