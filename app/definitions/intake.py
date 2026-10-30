"""Normalizace nahraných názvů a dohledatelné rozbalení dodaných archivů."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote

from app.definitions.archives import extract_zip


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_uploads(root: Path) -> dict:
    root = root.resolve()
    index = root / "intake.json"
    records = json.loads(index.read_text()) if index.exists() else {"format_version": 1, "documents": []}
    pattern = re.compile(r"https___developers\.mpsv\.cz_assets_documents_([a-f0-9-]{36})_(.+)")
    planned = []
    for path in sorted(root.glob("20*/*")):
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Nahraný dokument nesmí být symlink mimo úložiště.")
        uuid, original_name = match.groups()
        ascii_name = unicodedata.normalize("NFKD", original_name).encode("ascii", "ignore").decode().lower()
        safe = re.sub(r"[^a-z0-9.]+", "-", ascii_name).strip("-.")
        if not safe or len(safe) > 160:
            raise ValueError("Název nelze bezpečně normalizovat.")
        target = path.with_name(safe)
        if target.exists() or any(t == target for _, t, _ in planned):
            raise ValueError("Normalizace by přepsala existující soubor.")
        record = {"original_path": path.relative_to(root).as_posix(), "file": target.relative_to(root).as_posix(),
                  "original_document_name": original_name, "sha256": digest(path),
                  "source_url": f"https://developers.mpsv.cz/assets/documents/{uuid}/{quote(original_name, safe='')}",
                  "source_url_basis": "reconstructed_from_uploaded_filename_not_remote_verified",
                  "original_downloaded_at": None, "origin_status": "unverified"}
        planned.append((path, target, record))
    # Persist the exact original names before any filesystem mutation.
    records["documents"].extend(r for _, _, r in planned)
    index.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for source, target, record in planned:
        source.rename(target)
        if digest(target) != record["sha256"]:
            raise ValueError("Hash po normalizaci nesouhlasí.")
    return records


def unpack_archives(root: Path, staging: Path) -> list[dict]:
    """All members staged; publish XSD trees and nested ZIPs, keep originals intact.

    HTML/images/protocol examples remain in original archives and in local staging.
    AppleDouble metadata is inventoried, never treated as an XML schema.
    """
    root, staging = root.resolve(), staging.resolve()
    intake = json.loads((root / "intake.json").read_text())
    published, archives = [], []
    budget = 0

    def visit(path: Path, source: dict, chain: list[str], target_base: Path, depth: int) -> None:
        nonlocal budget
        if depth > 3:
            raise ValueError("Překročena hloubka vnořených ZIP.")
        content = path.read_bytes()
        stage = staging / hashlib.sha256(content).hexdigest()
        if stage.exists():
            # Never delete an unknown nonempty directory to force a rerun.
            from app.definitions.archives import zip_inventory
            members = zip_inventory(content)
            if any(not (stage / m["path"]).is_file() or digest(stage / m["path"]) != m["sha256"]
                   for m in members if not m["directory"]):
                raise ValueError("Existující rozbalený obsah nesouhlasí s archivem.")
        else:
            members = extract_zip(content, stage)
        budget += sum(m["bytes"] for m in members)
        if budget > 200 * 1024 * 1024:
            raise ValueError("Součet vnořených archivů překračuje limit.")
        archives.append({"source_file": source["file"], "chain": chain, "sha256": hashlib.sha256(content).hexdigest(), "members": members})
        for member in members:
            if member["directory"] or "__MACOSX" in Path(member["path"]).parts or Path(member["path"]).name.startswith("._"):
                continue
            local = stage / member["path"]
            suffix = local.suffix.lower()
            if suffix not in {".xsd", ".zip"}:
                continue
            target = root / target_base / member["path"]
            if not target.resolve().is_relative_to(root):
                raise ValueError("Cílová cesta uniká z úložiště.")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and digest(target) != member["sha256"]:
                raise ValueError("Rozbalení by přepsalo odlišný soubor.")
            if not target.exists():
                target.write_bytes(local.read_bytes())
            published.append({"file": target.relative_to(root).as_posix(), "sha256": member["sha256"],
                              "source_file": source["file"], "source_url": source["source_url"],
                              "container_chain": chain + [member["member"]], "origin_status": "unverified"})
            if suffix == ".zip":
                visit(local, source, chain + [member["member"]], target.relative_to(root).with_suffix(""), depth + 1)

    for source in intake["documents"]:
        path = (root / source["file"]).resolve()
        if not path.is_relative_to(root) or digest(path) != source["sha256"]:
            raise ValueError("Zdrojový archiv je mimo úložiště nebo byl změněn.")
        if path.suffix == ".zip":
            visit(path, source, [], Path(source["file"]).parent / "extracted" / path.stem, 0)
    (root / "extraction.json").write_text(json.dumps({"archives": archives, "published": published}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return published


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["normalize", "unpack"])
    parser.add_argument("--root", type=Path, default=Path("schemas/official"))
    parser.add_argument("--staging", type=Path, default=Path("local/official-extracted"))
    args = parser.parse_args()
    result = normalize_uploads(args.root) if args.command == "normalize" else unpack_archives(args.root, args.staging)
    print("Dokumenty:", len(result["documents"]) if isinstance(result, dict) else len(result))


if __name__ == "__main__":
    main()
