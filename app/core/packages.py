"""Offline neměnné balíčky. Důvěra začíná nezávisle schváleným hashem manifestu."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from app.core.mapping import load_profile
from app.core.payroll import LOGIC_API, load_numbered_profile, strict_json
from app.core.payroll_conversion import validate_bindings
from app.core.schemas import is_below, registered_validator
from app.core.stage_resources import stage_schemas
from app.definitions.archives import extract_zip, zip_inventory

ALLOWED_SUFFIXES = {".json", ".xsd", ".csv", ".txt", ".md", ".pdf", ".xlsx", ".zip"}


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or value != unicodedata.normalize("NFC", value):
        raise ValueError("Neplatná cesta balíčku.")
    parts = value.split("/")
    if any(not p or p in {".", ".."} or ":" in p or "\\" in p or p.endswith((" ", "."))
           or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts) or any(ord(c) < 32 for c in value):
        raise ValueError("Nepovolená cesta balíčku.")
    return value


def parse_manifest(content: bytes, approved_sha256: str) -> dict:
    if not isinstance(approved_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", approved_sha256) or len(content) > 128 * 1024 or hashlib.sha256(content).hexdigest() != approved_sha256:
        raise ValueError("Manifest není schválen nezávislým hashem.")
    m = strict_json(content.decode("utf-8"))
    if not isinstance(m, dict) or set(m) != {"format_version", "package_id", "version", "logic_api", "files", "entry_points"}:
        raise ValueError("Neznámý manifest balíčku.")
    if type(m["format_version"]) is not int or m["format_version"] != 1 or type(m["logic_api"]) is not int or m["logic_api"] != LOGIC_API:
        raise ValueError("Balíček vyžaduje jinou logiku aplikace.")
    if not isinstance(m["package_id"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", m["package_id"]):
        raise ValueError("Neplatné ID balíčku.")
    if not isinstance(m["version"], str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,3}", m["version"]):
        raise ValueError("Neplatná verze balíčku.")
    if not isinstance(m["files"], dict) or not 1 <= len(m["files"]) <= 2000:
        raise ValueError("Neplatný seznam souborů.")
    seen = set()
    for path, digest in m["files"].items():
        safe_relative(path)
        if path == "manifest.json" or path.casefold() in seen or PurePosixPath(path).suffix.lower() not in ALLOWED_SUFFIXES or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Nepovolený soubor nebo hash.")
        seen.add(path.casefold())
    points = m["entry_points"]
    allowed = {"numbered_profile", "conversion_profile", "bindings", "official_root", "employee_profile"}
    if not isinstance(points, dict) or "numbered_profile" not in points or set(points) - allowed:
        raise ValueError("Neplatné vstupní body.")
    for kind, path in points.items():
        safe_relative(path)
        if kind != "official_root" and (path not in m["files"] or not path.endswith(".json")):
            raise ValueError("Chybí vstupní bod.")
    if bool(points.get("conversion_profile")) != bool(points.get("bindings")) or ("conversion_profile" in points and "official_root" not in points):
        raise ValueError("Konverzní balíček musí mít vazby a úplný XSD root.")
    if "employee_profile" in points and "official_root" not in points:
        raise ValueError("Zaměstnanecký balíček vyžaduje úplný XSD root.")
    return m


@dataclass(frozen=True)
class CheckedPackage:
    directory: Path
    manifest_sha256: str
    manifest: dict

    def read_entry(self, name: str) -> str:
        """Recheck a passive JSON entry immediately before its use."""
        relative = self.manifest["entry_points"][name]
        path = self.directory / relative
        if any(p.is_symlink() for p in (path,) + tuple(path.parents) if p != self.directory.parent):
            raise ValueError("Symlinky v balíčku nejsou povoleny.")
        if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("Neplatný vstupní bod balíčku.")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != self.manifest["files"].get(relative):
            raise ValueError("Vstupní bod byl po ověření změněn.")
        return content.decode("utf-8")

    @property
    def profile(self):
        return load_numbered_profile(self.read_entry("numbered_profile"))


def load_package(directory: Path, approved_sha256: str) -> CheckedPackage:
    directory = directory.resolve()
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not stat.S_ISREG(manifest_path.stat().st_mode) or manifest_path.stat().st_size > 128 * 1024:
        raise ValueError("Neplatný soubor manifestu.")
    manifest = parse_manifest(manifest_path.read_bytes(), approved_sha256)
    actual, total = set(), 0
    for parent, directories, files in os.walk(str(directory), followlinks=False):
        for name in directories + files:
            p = Path(parent) / name
            if p.is_symlink():
                raise ValueError("Symlinky v balíčku nejsou povoleny.")
        for name in files:
            p = Path(parent) / name
            relative = p.relative_to(directory).as_posix()
            if relative == "manifest.json":
                continue
            actual.add(relative)
            size = p.stat().st_size
            total += size
            if not stat.S_ISREG(p.stat().st_mode) or relative not in manifest["files"] or size > 25 * 1024 * 1024 or total > 100 * 1024 * 1024:
                raise ValueError("Neznámý nebo nadlimitní soubor balíčku.")
            if hashlib.sha256(p.read_bytes()).hexdigest() != manifest["files"][relative]:
                raise ValueError("Soubor balíčku nesouhlasí s manifestem.")
    if actual != set(manifest["files"]):
        raise ValueError("Neúplný balíček.")
    result = CheckedPackage(directory, approved_sha256, manifest)
    numbered = result.profile
    points = manifest["entry_points"]
    if "official_root" in points:
        official = directory / points["official_root"]
        bundles = strict_json((official / "bundles.json").read_text(encoding="utf-8"))["bundles"]
        for bundle in bundles:
            registered_validator(official, bundle["id"])
    if "conversion_profile" in points:
        conversion = load_profile(result.read_entry("conversion_profile"))
        bindings = strict_json(result.read_entry("bindings"))
        validate_bindings(bindings, numbered, conversion)
    if "employee_profile" in points:
        from app.core.employee_schema import EmployeeContract
        from app.core.employee_xml import load_employee_profile
        profile = load_employee_profile(result.read_entry("employee_profile"))
        load_employee_profile(result.read_entry("employee_profile"), numbered, EmployeeContract(official, profile["bundle_id"]))
    return result


def install_package(archive_path: Path, store: Path, approved_sha256: str) -> CheckedPackage:
    if archive_path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Balíček je příliš velký.")
    content = archive_path.read_bytes()
    inventory = zip_inventory(content)
    with ZipFile(BytesIO(content)) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > 128 * 1024:
            raise ValueError("Manifest je příliš velký.")
        manifest = parse_manifest(archive.read(info), approved_sha256)
    names = {r["path"] for r in inventory if not r["directory"]}
    if names != set(manifest["files"]) | {"manifest.json"} or any(r["member"] != r["path"] for r in inventory if not r["directory"]):
        raise ValueError("Archiv obsahuje nevyjmenované soubory nebo nekanonické cesty.")
    store = store.resolve()
    destination = store / manifest["package_id"] / manifest["version"]
    if not is_below(destination.resolve(), store):
        raise ValueError("Úložiště balíčku uniká mimo kořen.")
    store.mkdir(parents=True, exist_ok=True)
    # Validate the new archive even when its immutable version is already installed.
    with tempfile.TemporaryDirectory(dir=str(store), prefix=".incoming-") as temporary:
        staged = Path(temporary) / "payload"
        extract_zip(content, staged)
        load_package(staged, approved_sha256)
        if destination.exists():
            return load_package(destination, approved_sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.rename(destination)
    return load_package(destination, approved_sha256)


def build_package(profile: dict, output: Path, package_id: str, version: str, official_root: Path = None,
                  conversion_profile: dict = None, bindings: dict = None, employee_profile: dict = None) -> dict:
    profile = load_numbered_profile(json.dumps(profile))
    if output.exists():
        raise ValueError("Existující balíček se nepřepisuje.")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        points = {"numbered_profile": "profiles/numbered.json"}
        (root / "profiles").mkdir()
        (root / points["numbered_profile"]).write_bytes(canonical_json(profile))
        if official_root is not None:
            stage_schemas(official_root, root / "schemas" / "official")
            points["official_root"] = "schemas/official"
        if conversion_profile is not None or bindings is not None:
            conversion_profile = load_profile(json.dumps(conversion_profile))
            validate_bindings(bindings, profile, conversion_profile)
            points.update({"conversion_profile": "profiles/conversion.json", "bindings": "profiles/bindings.json"})
            (root / points["conversion_profile"]).write_bytes(canonical_json(conversion_profile))
            (root / points["bindings"]).write_bytes(canonical_json(bindings))
        if employee_profile is not None:
            from app.core.employee_xml import load_employee_profile
            employee_profile = load_employee_profile(json.dumps(employee_profile))
            points["employee_profile"] = "profiles/employee.json"
            (root / points["employee_profile"]).write_bytes(canonical_json(employee_profile))
        files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
        manifest = {"format_version": 1, "package_id": package_id, "version": version, "logic_api": LOGIC_API, "files": files, "entry_points": points}
        data = canonical_json(manifest)
        manifest_sha256 = hashlib.sha256(data).hexdigest()
        parse_manifest(data, manifest_sha256)
        (root / "manifest.json").write_bytes(data)
        load_package(root, manifest_sha256)
        stream = BytesIO()
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                info = ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        content = stream.getvalue()
        zip_inventory(content)
        with output.open("xb") as handle:
            handle.write(content)
    return {"manifest_sha256": manifest_sha256, "archive_sha256": hashlib.sha256(content).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--profile", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--package-id", required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--official-root", type=Path)
    build.add_argument("--conversion-profile", type=Path)
    build.add_argument("--bindings", type=Path)
    build.add_argument("--employee-profile", type=Path)
    install = sub.add_parser("install")
    install.add_argument("archive", type=Path)
    install.add_argument("--store", type=Path, required=True)
    install.add_argument("--trusted-manifest-sha256", required=True)
    check = sub.add_parser("verify")
    check.add_argument("directory", type=Path)
    check.add_argument("--trusted-manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_package(load_numbered_profile(args.profile.read_text(encoding="utf-8")), args.output, args.package_id, args.version,
                                   args.official_root, strict_json(args.conversion_profile.read_text(encoding="utf-8")) if args.conversion_profile else None,
                                   strict_json(args.bindings.read_text(encoding="utf-8")) if args.bindings else None,
                                   strict_json(args.employee_profile.read_text(encoding="utf-8")) if args.employee_profile else None)
            print(json.dumps(result))
        else:
            package = install_package(args.archive, args.store, args.trusted_manifest_sha256) if args.command == "install" else load_package(args.directory, args.trusted_manifest_sha256)
            print(json.dumps({"package_id": package.manifest["package_id"], "version": package.manifest["version"], "integrity": "verified_against_independent_pin", "official_origin": "unverified"}))
        return 0
    except Exception:
        parser.exit(2, "Balíček nebyl schválen nebo je neplatný; nebyla povolena jiná logika ani neověřený obsah.\n")


if __name__ == "__main__":
    raise SystemExit(main())
