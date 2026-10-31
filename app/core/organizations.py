"""Offline organizace: společný registr, oddělené databáze a neměnná historie.

Žádné interní UUID tohoto modulu není oficiálním GUID JMHZ.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID, uuid4, uuid5

from app.core.models import SourceRow, SourceTable
from app.core.identities import numeric_key
from app.core.payroll import load_numbered_profile, prepare_payroll, strict_json
from app.core.periods import Period, SubmissionContext
from app.core.workforce import assess_workforce


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def database(path):
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    ico: str
    variable_symbol: str
    identifiers: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OrganizationImport:
    organization_id: str
    id: str
    period: Period
    import_index: int
    profile: dict = field(repr=False)
    definition: dict = field(repr=False)
    source: SourceTable = field(repr=False)


@dataclass(frozen=True)
class Analysis:
    organization_id: str
    import_id: str
    index: int
    payroll: object = field(repr=False)
    assessments: tuple = field(repr=False)
    issues: tuple = field(repr=False)
    totals: dict = field(repr=False)
    report: dict = field(repr=False)


class OrganizationWorkspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.registry = self.root / "registry.sqlite3"
        if self.registry.is_symlink():
            raise ValueError("Registr nesmí být symlink.")
        with database(self.registry) as db:
            db.execute("CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, name TEXT NOT NULL, ico TEXT NOT NULL, variable_symbol TEXT NOT NULL, identifiers TEXT NOT NULL, UNIQUE(ico,variable_symbol))")
            db.execute("CREATE TABLE IF NOT EXISTS profiles (scope TEXT PRIMARY KEY, definition TEXT NOT NULL)")

    def register(self, name, ico, variable_symbol, identifiers=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Doplňte název organizace.")
        if not isinstance(ico, str) or not re.fullmatch(r"[0-9]{8}", ico):
            raise ValueError("IČO musí být text osmi číslic; existence se tím nepotvrzuje.")
        if not isinstance(variable_symbol, str) or not re.fullmatch(r"[0-9]{10}", variable_symbol):
            raise ValueError("Doplňte skutečný desetimístný variabilní symbol zaměstnavatele.")
        identifiers = identifiers or {}
        if (not isinstance(identifiers, dict) or set(identifiers) - {"dic", "data_box_id"}
                or any(not isinstance(v, str) or len(v) > 100 for v in identifiers.values())):
            raise ValueError("Nepodporovaná doplňující metadata organizace.")
        org = Organization(str(uuid4()), name.strip(), ico, variable_symbol, dict(identifiers))
        try:
            with database(self.registry) as db:
                db.execute("INSERT INTO organizations VALUES (?,?,?,?,?)", (org.id, org.name, ico, variable_symbol, dumps(identifiers)))
        except sqlite3.IntegrityError:
            raise ValueError("Organizace s tímto IČO a VS již existuje.") from None
        return org

    def organizations(self):
        with database(self.registry) as db:
            rows = db.execute("SELECT * FROM organizations ORDER BY name,id").fetchall()
        return tuple(Organization(r["id"], r["name"], r["ico"], r["variable_symbol"], strict_json(r["identifiers"])) for r in rows)

    def organization(self, organization_id):
        if not isinstance(organization_id, str) or str(UUID(organization_id)) != organization_id:
            raise ValueError("Neplatná interní identita organizace.")
        with database(self.registry) as db:
            row = db.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()
        if row is None:
            raise ValueError("Organizace není registrovaná.")
        return Organization(row["id"], row["name"], row["ico"], row["variable_symbol"], strict_json(row["identifiers"]))

    def organization_directory(self, organization_id):
        org = self.organization(organization_id)
        directory = self.root / "organizations" / org.id
        try:
            directory.resolve().relative_to(self.root)
        except ValueError:
            raise ValueError("Datový prostor organizace uniká mimo kořen.") from None
        if any(p.is_symlink() for p in (directory, directory.parent)):
            raise ValueError("Datový prostor nesmí být symlink.")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        return directory

    @contextmanager
    def _data(self, organization_id):
        path = self.organization_directory(organization_id) / "workspace.sqlite3"
        if path.is_symlink():
            raise ValueError("Databáze nesmí být symlink.")
        with database(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS owner (organization_id TEXT PRIMARY KEY)")
            owners = [r[0] for r in db.execute("SELECT organization_id FROM owner")]
            if owners and owners != [organization_id]:
                raise ValueError("Databáze patří jiné organizaci.")
            if not owners:
                db.execute("INSERT INTO owner VALUES (?)", (organization_id,))
            db.execute("CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, period TEXT NOT NULL, import_index INTEGER NOT NULL, created_at TEXT NOT NULL, source_sha256 TEXT NOT NULL, profile TEXT NOT NULL, definition TEXT NOT NULL, source TEXT NOT NULL, record_count INTEGER, UNIQUE(organization_id,period,import_index))")
            db.execute("CREATE TABLE IF NOT EXISTS analyses (import_id TEXT NOT NULL REFERENCES imports(id), analysis_index INTEGER NOT NULL, created_at TEXT NOT NULL, error_count INTEGER NOT NULL, report TEXT NOT NULL, totals TEXT NOT NULL, calculations TEXT, PRIMARY KEY(import_id,analysis_index))")
            # Additive migration also preserves locally created early workspace snapshots.
            for table, column, sql_type in [("imports", "record_count", "INTEGER"), ("analyses", "calculations", "TEXT")]:
                if column not in {r[1] for r in db.execute("PRAGMA table_info(" + table + ")")}:
                    db.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + sql_type)
            db.execute("CREATE TABLE IF NOT EXISTS versions (organization_id TEXT NOT NULL, period TEXT NOT NULL, revision_index INTEGER NOT NULL, import_id TEXT NOT NULL REFERENCES imports(id), analysis_index INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(organization_id,period,revision_index))")
            db.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id), created_at TEXT NOT NULL, xml BLOB NOT NULL, sha256 TEXT NOT NULL)")
            if "validation" not in {r[1] for r in db.execute("PRAGMA table_info(drafts)")}:
                db.execute("ALTER TABLE drafts ADD COLUMN validation TEXT")
            db.execute("CREATE TABLE IF NOT EXISTS employee_checks (import_id TEXT NOT NULL, analysis_index INTEGER NOT NULL, profile TEXT NOT NULL, parameters TEXT NOT NULL, report TEXT NOT NULL, PRIMARY KEY(import_id,analysis_index), FOREIGN KEY(import_id,analysis_index) REFERENCES analyses(import_id,analysis_index))")
            db.execute("CREATE TABLE IF NOT EXISTS employer_imports (id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id), import_index INTEGER NOT NULL, created_at TEXT NOT NULL, source_sha256 TEXT NOT NULL, profile TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(import_id,import_index))")
            db.execute("CREATE TABLE IF NOT EXISTS monthly_checks (import_id TEXT NOT NULL, analysis_index INTEGER NOT NULL, employer_id TEXT NOT NULL REFERENCES employer_imports(id), profile TEXT NOT NULL, parameters TEXT NOT NULL, report TEXT NOT NULL, PRIMARY KEY(import_id,analysis_index), FOREIGN KEY(import_id,analysis_index) REFERENCES analyses(import_id,analysis_index))")
            db.commit()
            yield db

    def set_profile(self, profile=None, organization_id=None, package_directory=None, approved_sha256=None):
        scope = self.organization(organization_id).id if organization_id else "shared"
        if package_directory is not None:
            from app.core.packages import load_package
            package = load_package(Path(package_directory), approved_sha256)
            definition = {"kind": "pinned_package_manifest", "sha256": package.manifest_sha256, "directory": str(package.directory)}
        else:
            profile = load_numbered_profile(dumps(profile))
            definition = {"kind": "local_working_profile", "sha256": hashlib.sha256(dumps(profile).encode("utf-8")).hexdigest(), "profile": profile}
        with database(self.registry) as db:
            db.execute("INSERT OR REPLACE INTO profiles VALUES (?,?)", (scope, dumps(definition)))

    def clear_profile_override(self, organization_id):
        self.organization(organization_id)
        with database(self.registry) as db:
            db.execute("DELETE FROM profiles WHERE scope=?", (organization_id,))

    def profile(self, organization_id):
        self.organization(organization_id)
        with database(self.registry) as db:
            row = db.execute("SELECT definition FROM profiles WHERE scope=?", (organization_id,)).fetchone()
            if row is None:
                row = db.execute("SELECT definition FROM profiles WHERE scope='shared'").fetchone()
        if row is None:
            raise ValueError("Vyberte společný profil nebo profil této organizace.")
        definition = strict_json(row[0])
        return self._definition_profile(definition), definition

    @staticmethod
    def _definition_profile(definition):
        if definition["kind"] == "pinned_package_manifest":
            from app.core.packages import load_package
            return load_package(Path(definition["directory"]), definition["sha256"]).profile
        profile = load_numbered_profile(dumps(definition["profile"]))
        if hashlib.sha256(dumps(profile).encode("utf-8")).hexdigest() != definition["sha256"]:
            raise ValueError("Profil neodpovídá evidovanému hashi.")
        return profile

    def employment_uuid(self, organization_id, internal_number):
        self.organization(organization_id)
        numeric_key(internal_number)
        return str(uuid5(UUID(organization_id), "employment:" + internal_number))

    def import_table(self, organization_id, period, source, source_sha256=None):
        org = self.organization(organization_id)
        if not isinstance(period, Period) or not source.rows:
            raise ValueError("Import vyžaduje organizaci, měsíc a neprázdná data.")
        profile, definition = self.profile(organization_id)
        refs = profile["metadata"]
        def column(key):
            ref = refs[key]
            return ref.get("column") or profile["items"][ref["item"]]["column"]
        for row in source.rows:
            if Period.parse(row.values.get(column("period"), ""), profile["period_century"]) != period:
                raise ValueError("Období souboru nesouhlasí s vybraným měsícem; import nebyl uložen.")
            for key, expected in [("employer_ico", org.ico), ("employer_variable_symbol", org.variable_symbol)]:
                if key in refs and row.values.get(column(key), "").strip() != expected:
                    raise ValueError("Identifikace zaměstnavatele v souboru nesouhlasí s organizací.")
        payload = dumps({"columns": source.columns, "rows": [{"number": r.number, "values": r.values, "numeric_columns": sorted(r.numeric_columns)} for r in source.rows]})
        digest = source_sha256 or hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Neplatný hash importu.")
        with self._data(organization_id) as db:
            db.execute("BEGIN IMMEDIATE")
            index = db.execute("SELECT COALESCE(MAX(import_index),-1)+1 FROM imports WHERE organization_id=? AND period=?", (organization_id, period.iso)).fetchone()[0]
            identity = str(uuid5(UUID(organization_id), "import:{0}:{1}".format(period.iso, index)))
            db.execute("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?,?)", (identity, organization_id, period.iso, index, now(), digest, dumps(profile), dumps(definition), payload, len(source.rows)))
        return self.get_import(organization_id, identity)

    def import_file(self, organization_id, period, path, encoding="auto", delimiter="auto"):
        from app.core.input import read_csv, read_xlsx
        self.organization(organization_id)
        source = read_xlsx(path) if path.suffix.lower() == ".xlsx" else read_csv(path, encoding, delimiter)
        return self.import_table(organization_id, period, source, hashlib.sha256(path.read_bytes()).hexdigest())

    def get_import(self, organization_id, import_id):
        with self._data(organization_id) as db:
            row = db.execute("SELECT * FROM imports WHERE organization_id=? AND id=?", (organization_id, import_id)).fetchone()
        if row is None:
            raise ValueError("Import není dostupný v této organizaci.")
        raw = strict_json(row["source"])
        source = SourceTable(tuple(raw["columns"]), tuple(SourceRow(r["number"], r["values"], frozenset(r["numeric_columns"])) for r in raw["rows"]))
        return OrganizationImport(organization_id, row["id"], Period.parse(row["period"]), row["import_index"], strict_json(row["profile"]), strict_json(row["definition"]), source)

    def history(self, organization_id, period):
        with self._data(organization_id) as db:
            imports = db.execute("SELECT id,import_index,created_at,source_sha256 FROM imports WHERE organization_id=? AND period=? ORDER BY import_index", (organization_id, period.iso)).fetchall()
            versions = db.execute("SELECT revision_index,import_id,analysis_index,created_at FROM versions WHERE organization_id=? AND period=? ORDER BY revision_index", (organization_id, period.iso)).fetchall()
        return {"imports": [dict(r) for r in imports], "versions": [dict(r) for r in versions]}

    def analyze(self, organization_id, import_id, official_root=None, bundle_id=None):
        imported = self.get_import(organization_id, import_id)
        profile = self._definition_profile(imported.definition)
        if profile != imported.profile:
            raise ValueError("Definice se změnila; starý import nelze tiše přemapovat.")
        if imported.definition["kind"] == "pinned_package_manifest":
            from app.core.packages import load_package
            package = load_package(Path(imported.definition["directory"]), imported.definition["sha256"])
            if "official_root" in package.manifest["entry_points"]:
                official_root = package.directory / package.manifest["entry_points"]["official_root"]
        payroll = prepare_payroll(imported.source, profile, SubmissionContext(imported.period, 0))
        payroll = replace(payroll, rows=tuple(replace(r, person_group=str(uuid5(UUID(organization_id), import_id + ":" + r.person_group)))
                                              if r.person_group else r for r in payroll.rows))
        evidence = {}
        assessments, workforce_issues = assess_workforce(imported.source, payroll, profile, official_root, bundle_id, evidence)
        if official_root is not None and bundle_id:
            evidence["runtime_manifest_sha256"] = hashlib.sha256((official_root / "manifest.json").read_bytes()).hexdigest()
        issues = payroll.issues + workforce_issues
        report = payroll.safe_report()
        report.update({"organization_id": organization_id, "import_id": import_id, "issues": [asdict(i) for i in issues],
                       "internal_revision": None,
                       "validation_evidence": evidence,
                       "assessments": [{k: v for k, v in asdict(a).items() if k != "alternative"} for a in assessments]})
        for row, original in zip(report["rows"], payroll.rows):
            row["row_uuid"] = str(uuid5(UUID(organization_id), import_id + ":row:" + str(row["row"])))
            try:
                numeric_key(original.metadata["internal_number"])
                row["employment_uuid"] = str(uuid5(UUID(organization_id), "employment:" + original.metadata["internal_number"]))
            except ValueError:
                row["employment_uuid"] = None
        with localcontext() as context:
            context.prec = 128
            totals = {name: {"known_sum": format(sum((r.calculations[name] for r in payroll.rows if r.calculations.get(name) is not None), Decimal(0)), "f"),
                             "unknown_rows": sum(r.calculations.get(name) is None for r in payroll.rows)} for name in profile["calculations"]}
        with self._data(organization_id) as db:
            db.execute("BEGIN IMMEDIATE")
            index = db.execute("SELECT COALESCE(MAX(analysis_index),-1)+1 FROM analyses WHERE import_id=?", (import_id,)).fetchone()[0]
            calculations = {str(r.number): {k: format(v, "f") if v is not None else None for k, v in r.calculations.items()} for r in payroll.rows}
            db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?)", (import_id, index, now(), len(issues), dumps(report), dumps(totals), dumps(calculations)))
        return Analysis(organization_id, import_id, index, payroll, assessments, issues, totals, report)

    def analysis_history(self, organization_id, import_id):
        self.get_import(organization_id, import_id)
        with self._data(organization_id) as db:
            rows = db.execute("SELECT analysis_index,created_at,error_count FROM analyses WHERE import_id=? ORDER BY analysis_index", (import_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def analysis_snapshot(self, organization_id, import_id, analysis_index):
        self.get_import(organization_id, import_id)
        with self._data(organization_id) as db:
            row = db.execute("SELECT report,totals,calculations FROM analyses WHERE import_id=? AND analysis_index=?", (import_id, analysis_index)).fetchone()
            employee = db.execute("SELECT report FROM employee_checks WHERE import_id=? AND analysis_index=?", (import_id, analysis_index)).fetchone()
            monthly = db.execute("SELECT report FROM monthly_checks WHERE import_id=? AND analysis_index=?", (import_id, analysis_index)).fetchone()
        if row is None:
            raise ValueError("Kontrola není dostupná v této organizaci a importu.")
        return {"report": strict_json(row[0]), "totals": strict_json(row[1]), "calculations": strict_json(row[2]) if row[2] else {},
                "employee_validation": strict_json(employee[0]) if employee else None,
                "monthly_validation": strict_json(monthly[0]) if monthly else None}

    def draft_history(self, organization_id, import_id):
        self.get_import(organization_id, import_id)
        with self._data(organization_id) as db:
            rows = db.execute("SELECT id,created_at,sha256 FROM drafts WHERE import_id=? ORDER BY created_at,id", (import_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def overview(self, period):
        if not isinstance(period, Period):
            raise ValueError("Vyberte měsíc.")
        result = []
        for org in self.organizations():
            history = self.history(org.id, period)
            last = history["imports"][-1] if history["imports"] else None
            data = {"organization": org, "period": period.iso, "import_id": last["id"] if last else None,
                    "import_index": last["import_index"] if last else None, "status": "not_imported", "pp_count": 0,
                    "error_count": None, "last_revision": history["versions"][-1]["revision_index"] if history["versions"] else None}
            if last:
                with self._data(org.id) as db:
                    count = db.execute("SELECT record_count FROM imports WHERE id=? AND organization_id=?", (last["id"], org.id)).fetchone()[0]
                    analysis = db.execute("SELECT error_count,analysis_index FROM analyses WHERE import_id=? ORDER BY analysis_index DESC LIMIT 1", (last["id"],)).fetchone()
                    employee = db.execute("SELECT report FROM employee_checks WHERE import_id=? AND analysis_index=?", (last["id"], analysis[1])).fetchone() if analysis else None
                    monthly = db.execute("SELECT report FROM monthly_checks WHERE import_id=? AND analysis_index=?", (last["id"], analysis[1])).fetchone() if analysis else None
                data.update(status="imported", pp_count=count if count is not None else len(self.get_import(org.id, last["id"]).source.rows))
                if analysis:
                    employee_report = strict_json(monthly[0]) if monthly else strict_json(employee[0]) if employee else {}
                    count = analysis[0] + len(employee_report.get("issues", [])) + len(employee_report.get("review_issues", []))
                    data.update(status="checked_with_findings" if count else "technically_checked", error_count=count)
            result.append(data)
        return tuple(result)

    def record_version(self, organization_id, import_id, analysis_index, revision_index):
        imported = self.get_import(organization_id, import_id)
        if type(revision_index) is not int or revision_index < 0:
            raise ValueError("Neplatné interní pořadí.")
        with self._data(organization_id) as db:
            db.execute("BEGIN IMMEDIATE")
            latest_import = db.execute("SELECT id FROM imports WHERE organization_id=? AND period=? ORDER BY import_index DESC LIMIT 1", (organization_id, imported.period.iso)).fetchone()[0]
            latest = db.execute("SELECT analysis_index,error_count FROM analyses WHERE import_id=? ORDER BY analysis_index DESC LIMIT 1", (import_id,)).fetchone()
            if latest_import != import_id or latest is None or latest[0] != analysis_index or latest[1]:
                raise ValueError("Použijte poslední import a jeho poslední kontrolu bez nálezů.")
            employee = db.execute("SELECT report FROM employee_checks WHERE import_id=? AND analysis_index=?", (import_id, analysis_index)).fetchone()
            monthly = db.execute("SELECT report FROM monthly_checks WHERE import_id=? AND analysis_index=?", (import_id, analysis_index)).fetchone()
            employee = monthly or employee
            if employee:
                report = strict_json(employee[0])
                if report["issues"] or report["review_issues"]:
                    raise ValueError("Zaměstnanecká XML kontrola má nevyřešené nálezy.")
            expected = db.execute("SELECT COALESCE(MAX(revision_index),-1)+1 FROM versions WHERE organization_id=? AND period=?", (organization_id, imported.period.iso)).fetchone()[0]
            if revision_index != expected:
                raise ValueError("Interní pořadí musí navazovat od nuly; záznamy se nepřepisují.")
            db.execute("INSERT INTO versions VALUES (?,?,?,?,?,?)", (organization_id, imported.period.iso, revision_index, import_id, analysis_index, now()))

    def prepare_draft(self, organization_id, import_id, conversion_profile, bindings, parameters, official_root):
        from app.core.payroll_conversion import prepare_numbered_conversion
        org = self.organization(organization_id)
        imported = self.get_import(organization_id, import_id)
        if str(parameters.get("employer_variable_symbol", "")) != org.variable_symbol:
            raise ValueError("Variabilní symbol hlavičky neodpovídá organizaci.")
        if imported.definition["kind"] == "pinned_package_manifest":
            from app.core.packages import load_package
            package = load_package(Path(imported.definition["directory"]), imported.definition["sha256"])
            points = package.manifest["entry_points"]
            if ("conversion_profile" not in points or strict_json(package.read_entry("conversion_profile")) != conversion_profile
                    or strict_json(package.read_entry("bindings")) != bindings):
                raise ValueError("Použijte konverzní profil a vazby ze stejného schváleného balíčku.")
            official_root = package.directory / points["official_root"]
        analysis = self.analyze(organization_id, import_id, official_root, conversion_profile["bundle_id"])
        if any(a.employment_type in {"HPP", "DPP", "DPC"} for a in analysis.assessments):
            raise ValueError("Generátor úplného HPP/DPP/DPČ není dokončen; nelze jej nahradit scénářem jinyPrijem.")
        if analysis.payroll.issues or ("employment_type" in imported.profile["metadata"] and analysis.issues):
            raise ValueError("Kontrola má nálezy; pracovní XML není připraveno.")
        prepared = prepare_numbered_conversion(imported.source, imported.profile, SubmissionContext(imported.period, 0), conversion_profile, bindings, parameters, official_root)
        result = prepared.conversion
        if result is None or not result.xsd_valid or result.draft_xml is None:
            raise ValueError("Pracovní XML neprošlo kontrolou; nic nebylo uloženo.")
        identity = str(uuid5(UUID(organization_id), "draft:" + import_id + ":" + str(analysis.index)))
        with self._data(organization_id) as db:
            db.execute("INSERT INTO drafts (id,import_id,created_at,xml,sha256) VALUES (?,?,?,?,?)", (identity, import_id, now(), result.draft_xml, hashlib.sha256(result.draft_xml).hexdigest()))
        return identity, result

    def prepare_employee_draft(self, organization_id, import_id, profile, parameters, official_root):
        from app.core.employee_xml import load_employee_profile, prepare_employee_xml
        org = self.organization(organization_id)
        imported = self.get_import(organization_id, import_id)
        profile = load_employee_profile(dumps(profile))
        if str(parameters.get("employer_variable_symbol", "")) != org.variable_symbol:
            raise ValueError("Variabilní symbol hlavičky neodpovídá organizaci.")
        if self._definition_profile(imported.definition) != imported.profile:
            raise ValueError("Snímek profilu neodpovídá ověřené definici.")
        if imported.definition["kind"] == "pinned_package_manifest":
            from app.core.packages import load_package
            package = load_package(Path(imported.definition["directory"]), imported.definition["sha256"])
            if "employee_profile" not in package.manifest["entry_points"] or strict_json(package.read_entry("employee_profile")) != profile:
                raise ValueError("Použijte zaměstnanecký profil ze stejného schváleného balíčku.")
            official_root = package.directory / package.manifest["entry_points"]["official_root"]
        analysis = self.analyze(organization_id, import_id, official_root, profile["bundle_id"])
        result = prepare_employee_xml(imported.source, imported.profile, profile, SubmissionContext(imported.period, 0), parameters, official_root)
        report = result.safe_report()
        report["employee_profile_sha256"] = hashlib.sha256(dumps(profile).encode("utf-8")).hexdigest()
        report["definition_sha256"] = imported.definition["sha256"]
        report["runtime_manifest_sha256"] = hashlib.sha256((official_root / "manifest.json").read_bytes()).hexdigest()
        identity = str(uuid5(UUID(organization_id), "employee-draft:" + import_id + ":" + str(analysis.index))) if result.draft_xml else None
        with self._data(organization_id) as db:
            db.execute("INSERT INTO employee_checks VALUES (?,?,?,?,?)", (import_id, analysis.index, dumps(profile), dumps(parameters), dumps(report)))
            if identity:
                db.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?)", (identity, import_id, now(), result.draft_xml, hashlib.sha256(result.draft_xml).hexdigest(), dumps(report)))
        return identity, result

    def draft_validation(self, organization_id, import_id, draft_id):
        self.draft_bytes(organization_id, import_id, draft_id)
        with self._data(organization_id) as db:
            row = db.execute("SELECT validation FROM drafts WHERE id=? AND import_id=?", (draft_id, import_id)).fetchone()
        return strict_json(row[0]) if row[0] else {"legacy_draft": True, "submission_ready": False}

    def import_employer_table(self, organization_id, import_id, source, profile):
        from app.core.monthly_xml import load_monthly_profile
        imported = self.get_import(organization_id, import_id)
        org = self.organization(organization_id)
        profile = load_monthly_profile(dumps(profile))
        if len(source.rows) != 1:
            raise ValueError("Souhrn zaměstnavatele musí obsahovat právě jeden řádek.")
        row = source.rows[0]
        for field_name, expected in [("employer_ico", org.ico), ("employer_variable_symbol", org.variable_symbol)]:
            column = profile["metadata"][field_name]
            if column in row.numeric_columns or row.values.get(column) != expected:
                raise ValueError("Souhrn není doložen pro tuto organizaci; identifikátory musí být textové.")
        if Period.parse(row.values.get(profile["metadata"]["period"], ""), imported.profile["period_century"]) != imported.period:
            raise ValueError("Souhrn patří jinému měsíci.")
        payload = dumps({"columns": source.columns, "rows": [{"number": row.number, "values": row.values, "numeric_columns": sorted(row.numeric_columns)}]})
        with self._data(organization_id) as db:
            db.execute("BEGIN IMMEDIATE")
            index = db.execute("SELECT COALESCE(MAX(import_index),-1)+1 FROM employer_imports WHERE import_id=?", (import_id,)).fetchone()[0]
            identity = str(uuid5(UUID(organization_id), "employer:" + import_id + ":" + str(index)))
            db.execute("INSERT INTO employer_imports VALUES (?,?,?,?,?,?,?)", (identity, import_id, index, now(), hashlib.sha256(payload.encode("utf-8")).hexdigest(), dumps(profile), payload))
        return identity

    def prepare_monthly_draft(self, organization_id, import_id, employer_id, employee_profile, parameters, official_root):
        from app.core.monthly_xml import prepare_monthly_xml
        imported = self.get_import(organization_id, import_id)
        org = self.organization(organization_id)
        if str(parameters.get("employer_variable_symbol", "")) != org.variable_symbol:
            raise ValueError("Hlavička neodpovídá organizaci.")
        with self._data(organization_id) as db:
            row = db.execute("SELECT * FROM employer_imports WHERE id=? AND import_id=?", (employer_id, import_id)).fetchone()
        if row is None:
            raise ValueError("Souhrn není dostupný pro tuto organizaci a import.")
        profile, payload = strict_json(row["profile"]), strict_json(row["source"])
        if self._definition_profile(imported.definition) != imported.profile:
            raise ValueError("Definice importu se změnila.")
        if imported.definition["kind"] == "pinned_package_manifest":
            from app.core.packages import load_package
            package = load_package(Path(imported.definition["directory"]), imported.definition["sha256"])
            if (strict_json(package.read_entry("employee_profile")) != employee_profile
                    or strict_json(package.read_entry("monthly_profile")) != profile):
                raise ValueError("Profil nepatří ke schválenému balíčku.")
            official_root = package.directory / package.manifest["entry_points"]["official_root"]
        analysis = self.analyze(organization_id, import_id, official_root, employee_profile["bundle_id"])
        source = SourceTable(tuple(payload["columns"]), tuple(SourceRow(r["number"], r["values"], frozenset(r["numeric_columns"])) for r in payload["rows"]))
        result = prepare_monthly_xml(imported.source, imported.profile, employee_profile, SubmissionContext(imported.period, 0), parameters, source, profile, official_root)
        report = result.safe_report()
        report.update(definition_sha256=imported.definition["sha256"], employer_import_id=employer_id,
                      employee_profile_sha256=hashlib.sha256(dumps(employee_profile).encode()).hexdigest(),
                      monthly_profile_sha256=hashlib.sha256(dumps(profile).encode()).hexdigest())
        identity = str(uuid5(UUID(organization_id), "monthly:" + import_id + ":" + str(analysis.index))) if result.draft_xml else None
        with self._data(organization_id) as db:
            db.execute("INSERT INTO monthly_checks VALUES (?,?,?,?,?,?)", (import_id, analysis.index, employer_id, dumps(employee_profile), dumps(parameters), dumps(report)))
            if identity:
                db.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?)", (identity, import_id, now(), result.draft_xml, hashlib.sha256(result.draft_xml).hexdigest(), dumps(report)))
        return identity, result

    def draft_bytes(self, organization_id, import_id, draft_id):
        self.get_import(organization_id, import_id)
        with self._data(organization_id) as db:
            row = db.execute("SELECT xml,sha256 FROM drafts WHERE id=? AND import_id=?", (draft_id, import_id)).fetchone()
        if row is None or hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError("Pracovní XML není dostupné nebo nesouhlasí jeho hash.")
        return row[0]

    def write_draft(self, organization_id, import_id, draft_id):
        content = self.draft_bytes(organization_id, import_id, draft_id)
        target = self.organization_directory(organization_id) / "drafts"
        if target.is_symlink():
            raise ValueError("Adresář pracovního XML nesmí být symlink.")
        target.mkdir(exist_ok=True)
        path = target / (draft_id + ".draft.xml")
        with path.open("xb") as handle:
            handle.write(content)
        return path
