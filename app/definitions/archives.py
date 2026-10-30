"""Omezené lokální rozbalení ZIP, bez spuštění jeho obsahu."""
from io import BytesIO
from pathlib import Path, PurePosixPath
import hashlib
import re
import stat
import unicodedata
from zipfile import ZipFile

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_MEMBERS = 5000


def zip_inventory(content: bytes) -> list[dict]:
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP překračuje limit 25 MiB.")
    result, seen, total = [], set(), 0
    with ZipFile(BytesIO(content)) as archive:
        if len(archive.infolist()) > MAX_MEMBERS:
            raise ValueError("ZIP obsahuje příliš mnoho položek.")
        for item in archive.infolist():
            name = unicodedata.normalize("NFC", item.filename)
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or "\\" in name or "\x00" in name
                    or any(p in {".", ".."} or ":" in p or p.endswith((" ", "."))
                           or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts)
                    or ".." in name.split("/") or any(ord(c) < 32 for c in name)):
                raise ValueError("ZIP obsahuje nepovolenou cestu.")
            key = "/".join(parts).casefold()
            if key in seen:
                raise ValueError("ZIP obsahuje kolidující cesty.")
            seen.add(key)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                raise ValueError("ZIP obsahuje odkaz nebo speciální soubor.")
            if item.flag_bits & 1:
                raise ValueError("Šifrované ZIP nejsou podporovány.")
            total += item.file_size
            if total > MAX_EXPANDED_BYTES or item.file_size > MAX_EXPANDED_BYTES:
                raise ValueError("Rozbalený ZIP překračuje limit 100 MiB.")
            result.append({"member": item.filename, "path": "/".join(parts), "bytes": item.file_size,
                           "directory": item.is_dir()})
        paths = {r["path"].casefold(): r["directory"] for r in result}
        for record in result:
            if any(parent.as_posix().casefold() in paths and not paths[parent.as_posix().casefold()]
                   for parent in PurePosixPath(record["path"]).parents if parent.as_posix() != "."):
                raise ValueError("ZIP obsahuje kolizi souboru a adresáře.")
        # Reading verifies CRC. Bound sizes before decompressing any member.
        for record in result:
            if not record["directory"]:
                record["sha256"] = hashlib.sha256(archive.read(record["member"])).hexdigest()
    return result


def extract_zip(content: bytes, destination: Path) -> list[dict]:
    """Validate first, stage into an empty directory; never replace existing files."""
    inventory = zip_inventory(content)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Cílová složka musí být prázdná.")
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with ZipFile(BytesIO(content)) as archive:
        for record in inventory:
            target = root / record["path"]
            if not target.resolve().is_relative_to(root):
                raise ValueError("Cesta uniká z cílové složky.")
            if record["directory"]:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(archive.read(record["member"]))
    return inventory
