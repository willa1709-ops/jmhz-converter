"""Explicit UNENCRYPTED organization backups. Streaming SQLite/ZIP, no overwrite.

The independently supplied archive hash establishes integrity, not encryption,
publisher identity or protection against an administrator controlling both copies.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from uuid import UUID
from zipfile import ZipFile, ZIP_DEFLATED

from app.core.organizations import database, dumps, now
from app.core.packages import load_package, safe_relative
from app.core.payroll import strict_json
from app.core.submission_plans import ensure_ledger

MAX_BYTES = 512 * 1024 * 1024


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def create_backup(workspace, organization_id, destination):
    org = workspace.organization(organization_id)
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Existující záloha se nepřepisuje.")
    with database(workspace.registry) as db:
        row = db.execute("SELECT definition FROM profiles WHERE scope=?", (organization_id,)).fetchone()
        if row is None:
            row = db.execute("SELECT definition FROM profiles WHERE scope='shared'").fetchone()
        current = strict_json(row[0]) if row else None
    with tempfile.TemporaryDirectory(dir=str(workspace.organization_directory(org.id)), prefix=".backup-") as temporary:
        root = Path(temporary)
        snapshot = root / "workspace.sqlite3"
        with workspace._data(org.id) as source, database(snapshot) as target:
            source.backup(target)
        with database(snapshot) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Databáze neprošla kontrolou integrity.")
            definitions = [strict_json(r[0]) for r in db.execute("SELECT definition FROM imports")]
        if current:
            definitions.append(current)
        files, packages = {"database/workspace.sqlite3": snapshot}, {}
        for definition in definitions:
            workspace._definition_profile(definition)
            if definition["kind"] != "pinned_package_manifest":
                continue
            key = (definition["directory"], definition["sha256"])
            if key in packages:
                continue
            checked = load_package(Path(key[0]), key[1])
            prefix = "definitions/" + checked.manifest["package_id"] + "/" + checked.manifest["version"]
            for relative in ["manifest.json"] + list(checked.manifest["files"]):
                archive_name = prefix + "/" + relative
                path = checked.directory / relative
                if archive_name in files and digest(files[archive_name]) != digest(path):
                    raise ValueError("Stejná verze definic má různý obsah.")
                files[archive_name] = path
            packages[key] = {"old_directory": key[0], "pin": key[1], "prefix": prefix}
        with database(workspace.registry) as db:
            ensure_ledger(db)
            plans = [dict(r) for r in db.execute("SELECT * FROM submission_plans WHERE organization_id=?", (org.id,))]
            claims = [dict(r) for r in db.execute("SELECT * FROM guid_claims WHERE organization_id=?", (org.id,))]
        metadata = {"organization": asdict(org), "current_definition": current, "packages": list(packages.values()),
                    "submission_plans": plans, "guid_claims": claims, "encryption": "none"}
        meta = root / "metadata.json"
        meta.write_text(dumps(metadata), encoding="utf-8")
        files["metadata.json"] = meta
        if len(files) > 4000 or sum(p.stat().st_size for p in files.values()) > MAX_BYTES:
            raise ValueError("Záloha překračuje podporovaný rozsah.")
        manifest = {"format_version": 1, "encryption": "none", "files": {n: digest(p) for n, p in files.items()}}
        created = False
        try:
            with destination.open("xb") as stream:
                created = True
                import os
                if os.name != "nt":
                    destination.chmod(0o600)
                with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", dumps(manifest).encode("utf-8"))
                    for name, path in files.items():
                        archive.write(str(path), name)
            if destination.stat().st_size > MAX_BYTES:
                raise ValueError("Záloha překračuje limit velikosti.")
        except Exception:
            if created:
                destination.unlink()
            raise
    return {"sha256": digest(destination), "encryption": "none", "organization_id": org.id}


def restore_backup(workspace, archive_path, approved_sha256):
    archive_path = Path(archive_path)
    if (not isinstance(approved_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", approved_sha256)
            or archive_path.stat().st_size > MAX_BYTES or digest(archive_path) != approved_sha256):
        raise ValueError("Záloha nesouhlasí s nezávisle uloženým hashem.")
    with tempfile.TemporaryDirectory(dir=str(workspace.root), prefix=".restore-") as temporary:
        root = Path(temporary)
        with ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > 4001 or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError("Nadlimitní záloha.")
            seen = set()
            for info in infos:
                name = safe_relative(info.filename)
                mode = info.external_attr >> 16
                if (name.casefold() in seen or info.is_dir() or info.flag_bits & 1 or
                        stat.S_IFMT(mode) and not stat.S_ISREG(mode)):
                    raise ValueError("Nepovolená struktura zálohy.")
                seen.add(name.casefold())
            if archive.getinfo("manifest.json").file_size > 1024 * 1024 or archive.getinfo("metadata.json").file_size > 2 * 1024 * 1024:
                raise ValueError("Nadlimitní metadata.")
            manifest = strict_json(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format_version") != 1 or manifest.get("encryption") != "none" or not isinstance(manifest.get("files"), dict):
                raise ValueError("Neznámý formát zálohy.")
            if set(manifest["files"]) | {"manifest.json"} != {i.filename for i in infos}:
                raise ValueError("Neúplná nebo pozměněná záloha.")
            for name, expected in manifest["files"].items():
                safe_relative(name)
                if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                    raise ValueError("Neplatný hash souboru.")
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if digest(target) != expected:
                    raise ValueError("Poškozený obsah zálohy.")
        meta = strict_json((root / "metadata.json").read_text(encoding="utf-8"))
        org = meta["organization"]
        identity = org["id"]
        if (str(UUID(identity)) != identity or not isinstance(org["name"], str) or not org["name"].strip()
                or not re.fullmatch(r"[0-9]{8}", org["ico"]) or not re.fullmatch(r"[0-9]{10}", org["variable_symbol"])):
            raise ValueError("Neplatná organizace v záloze.")
        destination = workspace.root / "organizations" / identity
        if destination.exists() or destination.is_symlink():
            raise ValueError("Existující datový prostor se nepřepisuje.")
        parent = destination.parent
        if parent.is_symlink():
            raise ValueError("Datový kořen nesmí být odkaz.")
        parent.mkdir(exist_ok=True)
        relocations = {}
        for entry in meta["packages"]:
            staged = root / safe_relative(entry["prefix"])
            checked = load_package(staged, entry["pin"])
            store = workspace.root / "definition-packages"
            target = store / checked.manifest["package_id"] / checked.manifest["version"]
            if any(p.is_symlink() for p in (store, target.parent, target)):
                raise ValueError("Úložiště definic nesmí být odkaz.")
            try:
                target.resolve().relative_to(workspace.root)
            except ValueError:
                raise ValueError("Úložiště definic uniká mimo kořen.") from None
            if target.exists():
                load_package(target, entry["pin"])
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                staged.rename(target)
            relocations[(entry["old_directory"], entry["pin"])] = str(target)

        def relocate(definition):
            if definition and definition["kind"] == "pinned_package_manifest":
                definition = dict(definition, directory=relocations[(definition["directory"], definition["sha256"])])
            if definition:
                workspace._definition_profile(definition)
            return definition

        snapshot = root / "database/workspace.sqlite3"
        with database(snapshot) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            if (db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or
                    [r[0] for r in db.execute("SELECT organization_id FROM owner")] != [identity] or
                    db.execute("SELECT 1 FROM imports WHERE organization_id<>? LIMIT 1", (identity,)).fetchone() or
                    db.execute("PRAGMA foreign_key_check").fetchone()):
                raise ValueError("Nesouhlasí vlastník, vazby nebo integrita databáze.")
            plan_ids = {p["id"] for p in meta["submission_plans"]}
            for plan in meta["submission_plans"]:
                if (plan["organization_id"] != identity or plan["base_id"] is not None and plan["base_id"] not in plan_ids
                        or not db.execute("SELECT 1 FROM drafts WHERE id=? AND import_id=?", (plan["draft_id"], plan["import_id"])).fetchone()):
                    raise ValueError("Návaznost plánů nepatří do obnovené organizace/importu.")
            for row in db.execute("SELECT id,definition FROM imports").fetchall():
                db.execute("UPDATE imports SET definition=? WHERE id=?", (dumps(relocate(strict_json(row["definition"]))), row["id"]))
            db.execute("CREATE TABLE IF NOT EXISTS restore_events (created_at TEXT, archive_sha256 TEXT, event TEXT)")
            db.execute("INSERT INTO restore_events VALUES (?,?,?)", (now(), approved_sha256, "definition_locations_relocated_content_unchanged"))
        current = relocate(meta["current_definition"])
        created = False
        try:
            with database(workspace.registry) as db:
                ensure_ledger(db)
                db.commit()
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM organizations WHERE id=? OR (ico=? AND variable_symbol=?)", (identity, org["ico"], org["variable_symbol"])).fetchone():
                    raise ValueError("Organizace již existuje; obnova ji nepřepisuje.")
                for claim in meta["guid_claims"]:
                    if claim["organization_id"] != identity or db.execute("SELECT 1 FROM guid_claims WHERE guid=?", (claim["guid"],)).fetchone():
                        raise ValueError("GUID v záloze koliduje s jinou evidencí.")
                    db.execute("INSERT INTO guid_claims VALUES (?,?,?,?,?)", tuple(claim[k] for k in ("guid", "organization_id", "period", "kind", "employment_id")))
                for plan in meta["submission_plans"]:
                    if plan["organization_id"] != identity:
                        raise ValueError("Plán patří jiné organizaci.")
                    db.execute("INSERT INTO submission_plans VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(plan[k] for k in ("id", "organization_id", "period", "revision_index", "mode", "base_id", "reason", "import_id", "draft_id", "plan", "created_at")))
                db.execute("INSERT INTO organizations VALUES (?,?,?,?,?)", (identity, org["name"], org["ico"], org["variable_symbol"], dumps(org["identifiers"])))
                if current:
                    db.execute("INSERT INTO profiles VALUES (?,?)", (identity, dumps(current)))
                destination.mkdir(mode=0o700)
                created = True
                snapshot.rename(destination / "workspace.sqlite3")
        except Exception:
            if created:
                shutil.rmtree(destination)
            raise
    return workspace.organization(identity)
