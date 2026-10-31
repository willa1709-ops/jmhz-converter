"""Výchozí UI: organizace → měsíc → import → kontrola → pracovní XML."""
from datetime import date
import json
from pathlib import Path

from app.ui.qt_compat import QtCore, QtWidgets, QT_API, enum, run
QStandardPaths, Qt = QtCore.QStandardPaths, QtCore.Qt
for _name in ("QMainWindow", "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QPushButton", "QLineEdit", "QTableWidget",
              "QTableWidgetItem", "QAbstractItemView", "QFileDialog", "QComboBox", "QPlainTextEdit", "QSpinBox", "QDialog",
              "QFormLayout", "QDialogButtonBox", "QInputDialog", "QTabWidget"):
    globals()[_name] = getattr(QtWidgets, _name)

from app.core.organizations import OrganizationWorkspace
from app.core.payroll import load_numbered_profile, strict_json
from app.core.periods import Period
from app.core.resources import default_official_root


class OrganizationsWindow(QMainWindow):
    def __init__(self, root=None):
        super().__init__()
        self.setWindowTitle("JMHZ Converter – organizace a měsíční importy")
        self.resize(1200, 850)
        root = root or Path(QStandardPaths.writableLocation(enum(QStandardPaths, "StandardLocation", "AppDataLocation"))) / "workspace"
        self.workspace = OrganizationWorkspace(Path(root))
        self.organization_id = self.imported = self.analysis = self.draft_id = None
        self.tools = None
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("Organizace → měsíc → import → kontrola → pracovní XML. Finální export ZABLOKOVÁN.\n"
                                "Importy a pracovní XML se ukládají lokálně odděleně pro každou organizaci; obsahují osobní údaje.\n"
                                "Pracovní XML HPP/DPČ/DPP: běžný formulář s jedním ELDP úsekem; úplnost podání neověřena."))
        controls = QHBoxLayout()
        self.period = QLineEdit(date.today().strftime("%Y-%m"))
        self.period.setMaximumWidth(130)
        self.period.editingFinished.connect(self.refresh)
        controls.addWidget(QLabel("Vykazovaný měsíc"))
        controls.addWidget(self.period)
        self.button(controls, "Obnovit přehled", self.refresh)
        self.button(controls, "Přidat organizaci…", self.add_organization)
        self.button(controls, "Společný profil JSON…", lambda: self.choose_profile(False))
        self.button(controls, "Offline definice ZIP…", self.choose_package)
        layout.addLayout(controls)
        csv_controls = QHBoxLayout()
        csv_controls.addWidget(QLabel("CSV z Pascalu/DOSu – kódování a oddělovač:"))
        self.csv_encoding = QComboBox()
        self.csv_encoding.addItems(["cp1250", "utf-8-sig", "auto"])
        self.csv_delimiter = QComboBox()
        self.csv_delimiter.addItems([";", "auto", ",", "\t", "|"])
        csv_controls.addWidget(self.csv_encoding)
        csv_controls.addWidget(self.csv_delimiter)
        self.button(csv_controls, "Nešifrovaná záloha…", self.choose_backup)
        self.button(csv_controls, "Obnovit novou organizaci…", self.choose_restore)
        layout.addLayout(csv_controls)
        self.organizations = QTableWidget()
        self.organizations.setEditTriggers(enum(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.organizations.setSelectionBehavior(enum(QAbstractItemView, "SelectionBehavior", "SelectRows"))
        self.organizations.setSelectionMode(enum(QAbstractItemView, "SelectionMode", "SingleSelection"))
        self.organizations.cellClicked.connect(self.select_row)
        self.organizations.setMaximumHeight(200)
        layout.addWidget(self.organizations)
        self.context = QLabel("Vyberte organizaci. Poslední verze znamená interní přípravu, nikoliv odeslané podání.")
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        actions = QHBoxLayout()
        self.button(actions, "Profil této organizace…", lambda: self.choose_profile(True))
        self.button(actions, "Použít společný profil", self.use_shared_profile)
        self.button(actions, "Import CSV/XLSX…", self.choose_import)
        self.button(actions, "Kontrola a výpočty", self.check)
        layout.addLayout(actions)
        actions = QHBoxLayout()
        self.button(actions, "Pracovní XML…", self.choose_xml)
        self.button(actions, "Celý měsíční paket…", self.choose_monthly)
        self.button(actions, "Historie kontrol / XML…", self.open_audit_history)
        self.button(actions, "Plán podání / opravy…", self.choose_plan)
        tools_button = self.button(actions, "Původní nástroje…", self.open_tools)
        tools_button.setEnabled(QT_API == "PySide6")
        tools_button.setToolTip("Starší doplňkové nástroje vyžadují moderní variantu; hlavní workflow je společný.")
        layout.addLayout(actions)
        history = QHBoxLayout()
        history.addWidget(QLabel("Historie importů (oprava dat není opravné podání)"))
        self.import_history = QComboBox()
        self.import_history.currentIndexChanged.connect(self.open_history)
        history.addWidget(self.import_history)
        self.import_history.setSizeAdjustPolicy(enum(QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"))
        self.import_history.setMinimumContentsLength(20)
        layout.addLayout(history)
        history = QHBoxLayout()
        self.bundle = QComboBox()
        self.official_root = default_official_root()
        for b in strict_json((self.official_root / "bundles.json").read_text(encoding="utf-8"))["bundles"]:
            self.bundle.addItem(b["id"], b["id"])
        self.bundle.currentIndexChanged.connect(self.invalidate_analysis)
        history.addWidget(QLabel("XSD k technické kontrole, účinnost nepotvrzena"))
        history.addWidget(self.bundle)
        layout.addLayout(history)
        self.pages = QTabWidget()
        self.rows = QTableWidget()
        self.errors = QTableWidget()
        for table in (self.rows, self.errors):
            table.setEditTriggers(enum(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.pages.addTab(self.rows, "Pracovní poměry a výpočty")
        self.pages.addTab(self.errors, "Požadavky na doplnění")
        self.totals = QPlainTextEdit()
        self.totals.setReadOnly(True)
        self.pages.addTab(self.totals, "Kontrolní součty")
        self.draft = QPlainTextEdit()
        self.draft.setReadOnly(True)
        self.pages.addTab(self.draft, "Pracovní XML")
        layout.addWidget(self.pages)
        revisions = QHBoxLayout()
        self.revision = QSpinBox()
        self.revision.setRange(0, 1_000_000)
        revisions.addWidget(QLabel("Interní pořadí přípravy (0, 1, …), oddělené od GUID"))
        revisions.addWidget(self.revision)
        self.button(revisions, "Zapsat interní verzi", self.record_version)
        layout.addLayout(revisions)
        revisions = QHBoxLayout()
        self.button(revisions, "Uložit pracovní XML v organizaci", self.write_draft)
        final = QPushButton("Finální export – blokováno")
        final.setEnabled(False)
        revisions.addWidget(final)
        layout.addLayout(revisions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.period.textChanged.connect(self.refresh)
        self.refresh()

    @staticmethod
    def button(layout, label, handler):
        button = QPushButton(label)
        button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    @staticmethod
    def fill(table, headers, rows):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def clear_data(self):
        self.imported = None
        self.invalidate_analysis()
        if self.tools:
            self.tools.close()
            self.tools = None
        self.status.clear()

    def invalidate_analysis(self, *args):
        self.analysis = self.draft_id = None
        for table in (self.rows, self.errors):
            table.setRowCount(0)
        self.totals.clear()
        self.draft.clear()
        if hasattr(self, "status"):
            self.status.clear()

    def selected_period(self):
        return Period.parse(self.period.text().strip())

    def refresh(self):
        self.clear_data()
        self.import_history.blockSignals(True)
        self.import_history.clear()
        self.import_history.blockSignals(False)
        try:
            overview = self.workspace.overview(self.selected_period())
            states = {"not_imported": "bez importu", "imported": "načteno, nekontrolováno",
                      "checked_with_findings": "kontrola s nálezy", "technically_checked": "technická kontrola bez nálezů"}
            self.fill(self.organizations, ["Organizace", "IČO", "VS", "Import", "Počet PP", "Chyby / požadavky", "Poslední interní verze"],
                      [[r["organization"].name, r["organization"].ico, r["organization"].variable_symbol, states[r["status"]], r["pp_count"],
                        "nekontrolováno" if r["error_count"] is None else r["error_count"], "—" if r["last_revision"] is None else r["last_revision"]] for r in overview])
            for i, r in enumerate(overview):
                self.organizations.item(i, 0).setData(enum(Qt, "ItemDataRole", "UserRole"), r["organization"].id)
            if self.organization_id:
                self.select_organization(self.organization_id)
        except Exception:
            self.organizations.setRowCount(0)
            self.context.setText("Neplatný kontext; vyberte měsíc YY-MM nebo YYYY-MM.")

    def select_row(self, row, column):
        self.select_organization(self.organizations.item(row, 0).data(enum(Qt, "ItemDataRole", "UserRole")))

    def select_organization(self, organization_id):
        self.clear_data()
        org = self.workspace.organization(organization_id)
        period = self.selected_period()
        self.organization_id = org.id
        self.context.setText(org.name + " | IČO " + org.ico + " | VS " + org.variable_symbol + " | " + period.iso)
        history = self.workspace.history(org.id, period)
        self.import_history.blockSignals(True)
        self.import_history.clear()
        for item in history["imports"]:
            self.import_history.addItem("Import {0} | {1}".format(item["import_index"], item["created_at"]), item["id"])
        self.import_history.setCurrentIndex(len(history["imports"]) - 1)
        self.import_history.blockSignals(False)
        self.revision.setValue(history["versions"][-1]["revision_index"] + 1 if history["versions"] else 0)
        self.open_history()

    def open_history(self, *args):
        self.clear_data()
        identity = self.import_history.currentData()
        if identity and self.organization_id:
            self.imported = self.workspace.get_import(self.organization_id, identity)
            if self.imported.period != self.selected_period():
                self.clear_data()
                return
            self.status.setText("Historický import {0}; profil a data jsou neměnný snímek. Spusťte novou kontrolu.".format(self.imported.import_index))

    def add_organization(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Skutečné údaje zaměstnavatele")
        form = QFormLayout(dialog)
        fields = {key: QLineEdit() for key in ("name", "ico", "variable_symbol", "dic", "data_box_id")}
        for key, label in [("name", "Název"), ("ico", "IČO (8 číslic)"), ("variable_symbol", "VS zaměstnavatele (10 číslic)"),
                           ("dic", "DIČ – volitelná metadata"), ("data_box_id", "Datová schránka – volitelná metadata")]:
            form.addRow(label, fields[key])
        buttons = QDialogButtonBox(enum(QDialogButtonBox, "StandardButton", "Ok") | enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if run(dialog) == enum(QDialog, "DialogCode", "Accepted"):
            try:
                org = self.workspace.register(fields["name"].text(), fields["ico"].text(), fields["variable_symbol"].text(),
                                              {k: fields[k].text() for k in ("dic", "data_box_id") if fields[k].text()})
                self.organization_id = org.id
                self.refresh()
            except Exception:
                self.status.setText("Organizaci nelze zapsat. Ověřte povinné formáty a duplicitu IČO/VS.")

    def choose_profile(self, specific):
        if specific and not self.organization_id:
            self.status.setText("Nejprve vyberte organizaci.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Pracovní profil číslovaných položek", "", "JSON (*.json)")
        if path:
            try:
                self.workspace.set_profile(load_numbered_profile(Path(path).read_text(encoding="utf-8")), self.organization_id if specific else None)
                self.status.setText("Profil uložen pro příští importy. Starší importy používají původní snímek.")
            except Exception:
                self.status.setText("Profil nelze přijmout. Ověřte formát, zdroje a podporované operace.")

    def use_shared_profile(self):
        if self.organization_id:
            self.workspace.clear_profile_override(self.organization_id)
            self.status.setText("Příští importy organizace použijí společný profil; historie zůstává.")

    def choose_package(self):
        from app.core.packages import install_package
        path, _ = QFileDialog.getOpenFileName(self, "Společné offline definice", "", "ZIP (*.zip)")
        if not path:
            return
        pin, ok = QInputDialog.getText(self, "Nezávisle schválený hash", "SHA-256 manifestu od správce definic:")
        if ok:
            try:
                package = install_package(Path(path), self.workspace.root / "definition-packages", pin.strip())
                self.workspace.set_profile(package_directory=package.directory, approved_sha256=pin.strip())
                self.status.setText("Společný balíček přijat vůči schválenému hashi. Původ a metodika tím nejsou potvrzené.")
            except Exception:
                self.status.setText("Offline balíček odmítnut. Ověřte pin, obsah a verzi logiky.")

    def choose_import(self):
        if not self.organization_id:
            self.status.setText("Nejprve vyberte organizaci a měsíc.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Nový import – historie se zachová", "", "CSV/XLSX (*.csv *.xlsx)")
        if path:
            self.import_path(Path(path))

    def import_path(self, path):
        self.clear_data()
        try:
            imported = self.workspace.import_file(self.organization_id, self.selected_period(), path, self.csv_encoding.currentText(), self.csv_delimiter.currentText())
            self.refresh()
            assert self.imported.id == imported.id
            self.status.setText("Uložen nový import {0}. Starší importy ani interní verze se nepřepisují.".format(imported.import_index))
            return imported
        except Exception:
            self.status.setText("Import nebyl přijat. Ověřte organizaci, měsíc, profil, identifikaci zaměstnavatele a CSV/XLSX.")
            return None

    def check(self):
        self.invalidate_analysis()
        if not self.imported or self.imported.period != self.selected_period():
            self.clear_data()
            self.status.setText("Vyberte import aktuální organizace a měsíce.")
            return
        try:
            self.analysis = self.workspace.analyze(self.organization_id, self.imported.id, self.official_root, self.bundle.currentData())
            assessments = {a.row: a for a in self.analysis.assessments}
            names = list(self.imported.profile["calculations"])
            income_labels = {"zero": "nula", "value": "známá hodnota", "blank": "prázdné", "absent_column": "chybí sloupec", "absent_value": "nepřítomný údaj", "invalid": "neplatné"}
            identity_labels = {"oic": "OIČ", "pending_oic": "čeká na OIČ – doplnit údaje", "alternative_xsd_valid": "alternativa IN01: XSD prošlo",
                               "rc_pairing_only": "RČ – jen lokální párování", "unresolved": "nutné doplnit identifikaci"}
            decisions = {"income_data_required": "doplnit příjem", "zero_income_review_required": "přezkoumat nulový příjem",
                         "include_zero_registered_no_work_candidate": "registrovaný bez práce/příjmu – ověřit nulový formulář",
                         "reporting_scope_review_required": "nutný přezkum scénáře"}
            self.fill(self.rows, ["Řádek", "Interní PP", "Typ", "Identifikace", "Primární PP", "Stav příjmu", "Vykázání"] + names,
                      [[r.number, r.metadata.get("internal_number", ""), assessments[r.number].employment_type,
                        identity_labels[assessments[r.number].identity_mode], "neurčen" if r.primary_pp is None else "ano" if r.primary_pp else "ne",
                        income_labels[assessments[r.number].income_state], decisions[assessments[r.number].reporting_decision]] +
                       ["neznámé" if r.calculations.get(n) is None else format(r.calculations[n], "f") for n in names] for r in self.analysis.payroll.rows])
            self.fill(self.errors, ["Řádek", "Pole", "Kód", "Požadavek", "Náprava"],
                      [[i.row or "hlavička", i.field, i.code, i.message, i.remedy] for i in self.analysis.issues])
            self.totals.setPlainText("Informativní součet známých řádkových výsledků, bez převodu neznámých na nulu:\n" + json.dumps(self.analysis.totals, ensure_ascii=False, indent=2))
            self.status.setText("Kontrola {0}: {1} nálezů. Všechny PP zachovány; finální export NE.".format(self.analysis.index, len(self.analysis.issues)))
        except Exception:
            self.invalidate_analysis()
            self.status.setText("Kontrola selhala. Ověřte integritu profilu/XSD a zdrojová data; identifikátory se nevypisují.")

    def record_version(self):
        try:
            if not self.analysis or not self.imported or self.imported.period != self.selected_period():
                raise ValueError("Chybí kontrola.")
            self.workspace.record_version(self.organization_id, self.imported.id, self.analysis.index, self.revision.value())
            self.refresh()
            self.status.setText("Interní verze přípravy zaznamenána. Nejde o odeslání ani opravné podání JMHZ.")
        except Exception:
            self.status.setText("Verzi nelze zapsat. Použijte poslední import a kontrolu bez nálezů a navazující pořadí od nuly.")

    def choose_xml(self):
        if not self.imported:
            self.status.setText("Nejprve vyberte import.")
            return
        scenario, ok = QInputDialog.getItem(self, "Pracovní XML", "Scénář:", ["HPP/DPČ/DPP – bezPriznaku", "Původní jinyPrijem"], 0, False)
        if not ok:
            return
        if scenario.startswith("HPP"):
            definition = self.imported.definition
            if definition["kind"] == "pinned_package_manifest":
                try:
                    from app.core.packages import load_package
                    package = load_package(Path(definition["directory"]), definition["sha256"])
                    profile = strict_json(package.read_entry("employee_profile"))
                    parameters, _ = QFileDialog.getOpenFileName(self, "Skutečné parametry podání", "", "JSON (*.json)")
                    if parameters:
                        self.prepare_employee_xml(profile, strict_json(Path(parameters).read_text(encoding="utf-8")))
                except Exception:
                    self.status.setText("Balíček nemá platný zaměstnanecký profil; zvolte ověřenou sadu pro tento scénář.")
                return
            profile, _ = QFileDialog.getOpenFileName(self, "Pracovní zaměstnanecký profil", "", "JSON (*.json)")
            if not profile:
                return
            parameters, _ = QFileDialog.getOpenFileName(self, "Skutečné parametry podání", "", "JSON (*.json)")
            if parameters:
                self.prepare_employee_xml_paths(Path(profile), Path(parameters))
            return
        paths = []
        for label in ("Pracovní konverzní profil jinyPrijem", "Pracovní vazby číslovaných položek", "Skutečné parametry podání"):
            path, _ = QFileDialog.getOpenFileName(self, label, "", "JSON (*.json)")
            if not path:
                return
            paths.append(Path(path))
        self.prepare_xml_paths(*paths)

    def prepare_employee_xml_paths(self, profile, parameters):
        try:
            self.prepare_employee_xml(strict_json(profile.read_text(encoding="utf-8")), strict_json(parameters.read_text(encoding="utf-8")))
        except Exception:
            self.draft_id = None
            self.draft.clear()
            self.status.setText("Zaměstnanecké XML nelze připravit; ověřte profil, hlavičku a aktuální kontext.")

    def prepare_employee_xml(self, profile, parameters):
        self.draft_id = None
        self.draft.clear()
        if not self.imported or self.imported.period != self.selected_period():
            raise ValueError("Chybí import aktuálního kontextu.")
        identity, result = self.workspace.prepare_employee_draft(self.organization_id, self.imported.id, profile, parameters, self.official_root)
        self.fill(self.errors, ["Řádek", "Pole", "Kód", "Požadavek", "Náprava"],
                  [[i.row or "hlavička", i.field, i.code, i.message, i.remedy] for i in result.issues + result.review_issues])
        if result.draft_xml:
            self.draft_id = identity
            self.draft.setPlainText(result.draft_xml.decode("utf-8"))
            self.pages.setCurrentWidget(self.draft)
        else:
            self.pages.setCurrentWidget(self.errors)
        self.status.setText("bezPriznaku | XSD: {0}; blokující nálezy {1}; otevřené metodické otázky {2}. Finální export NE.".format(
            "PROŠLO" if result.xsd_valid else "NEPROŠLO", len(result.issues), len(result.review_issues)))

    def choose_monthly(self):
        if not self.imported or self.imported.period != self.selected_period():
            self.status.setText("Nejprve vyberte organizaci, měsíc a import PP.")
            return
        paths = []
        for label, pattern in [("Zaměstnanecký profil", "JSON (*.json)"), ("Profil souhrnů zaměstnavatele", "JSON (*.json)"),
                               ("Souhrny zaměstnavatele – jeden řádek Windows-1250", "CSV (*.csv)"), ("Skutečná hlavička podání", "JSON (*.json)")]:
            path, _ = QFileDialog.getOpenFileName(self, label, "", pattern)
            if not path:
                return
            paths.append(Path(path))
        self.prepare_monthly_paths(*paths)

    def choose_backup(self):
        if not self.organization_id:
            self.status.setText("Nejprve vyberte organizaci.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Nešifrovaná záloha obsahuje citlivá data – zvolte chráněné umístění", "", "ZIP (*.zip)")
        if path:
            try:
                from app.core.backups import create_backup
                result = create_backup(self.workspace, self.organization_id, Path(path))
                self.status.setText("NEŠIFROVANÁ záloha vytvořena. Hash uložte nezávisle: " + result["sha256"])
            except Exception:
                self.status.setText("Záloha nevytvořena. Ověřte přístup, integritu definic a nový cílový soubor; nic se nepřepisuje.")

    def choose_restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Obnova samostatné organizace – bez přepsání existujících dat", "", "ZIP (*.zip)")
        if not path:
            return
        pin, ok = QInputDialog.getText(self, "Nezávislý hash zálohy", "SHA-256 uložený mimo archiv:")
        if ok:
            try:
                from app.core.backups import restore_backup
                org = restore_backup(self.workspace, Path(path), pin.strip())
                self.organization_id = org.id
                self.refresh()
                self.status.setText("Organizace obnovena bez přepsání ostatních. Úložiště ani archiv nejsou šifrované.")
            except Exception:
                self.status.setText("Obnova odmítnuta: ověřte hash, integritu, potřebné definice a nepřítomnost cílové organizace.")

    def choose_plan(self):
        if not self.imported or not self.draft_id:
            self.status.setText("Plán vyžaduje vybraný import a pracovní XML. Nejde o odeslání podání.")
            return
        from app.core.submission_plans import history, record_plan
        plans = history(self.workspace, self.organization_id, self.imported.period)
        dialog = QDialog(self)
        dialog.setWindowTitle("Pracovní návaznost – bez odeslání a bez tvorby opravného XML")
        layout = QFormLayout(dialog)
        layout.addRow(QLabel("GUID jsou převzata z explicitních vstupů XML. Revize neurčuje typ podání.\nPřijetí původního podání, účinnost a výjimky nejsou potvrzeny."))
        mode, reason, base = QComboBox(), QComboBox(), QComboBox()
        mode.addItem("R – řádný plán", "R")
        mode.addItem("O – opravný plán", "O")
        for label, key in [("Řádný návrh", "regular"), ("Oprava z iniciativy zaměstnavatele", "employer_initiated"),
                           ("Náhrada nepropustně vadné součásti", "rejected_component"), ("Oprava souhrnu/pojistné části", "summary_or_insurance")]:
            reason.addItem(label, key)
        base.addItem("Bez návaznosti", None)
        for item in plans:
            base.addItem("Revize {0}, režim {1}".format(item["revision_index"], item["mode"]), item["id"])
        revision = QSpinBox()
        revision.setRange(0, 1_000_000)
        revision.setValue(len(plans))
        for label, widget in [("Výslovný režim plánu", mode), ("Důvod dle metodiky", reason), ("Původní plán", base), ("Interní pořadí plánu", revision)]:
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(enum(QDialogButtonBox, "StandardButton", "Ok") | enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if run(dialog) == enum(QDialog, "DialogCode", "Accepted"):
            try:
                record_plan(self.workspace, self.organization_id, self.imported.id, self.draft_id, revision.value(), mode.currentData(), base.currentData(), reason.currentData())
                self.status.setText("Pracovní plán uložen. XML zůstává řádným pracovním návrhem; oprava ani odeslání nebyly provedeny.")
            except Exception:
                self.status.setText("Návaznost odmítnuta. Ověřte pořadí, původní organizaci/měsíc, důvod a vazby GUID; revize není automatická oprava.")

    def prepare_monthly_paths(self, employee_profile, monthly_profile, employer_csv, parameters):
        self.draft_id = None
        self.draft.clear()
        try:
            from app.core.input import read_csv
            if not self.imported or self.imported.period != self.selected_period():
                raise ValueError("Chybí kontext.")
            profile = strict_json(monthly_profile.read_text(encoding="utf-8"))
            employer_id = self.workspace.import_employer_table(self.organization_id, self.imported.id, read_csv(employer_csv, "cp1250", ";"), profile)
            identity, result = self.workspace.prepare_monthly_draft(self.organization_id, self.imported.id, employer_id,
                strict_json(employee_profile.read_text(encoding="utf-8")), strict_json(parameters.read_text(encoding="utf-8")), self.official_root)
            self.fill(self.errors, ["Řádek", "Pole", "Kód", "Požadavek", "Náprava"],
                      [[i.row or "zaměstnavatel", i.field, i.code, i.message, i.remedy] for i in result.issues + result.review_issues])
            if identity:
                self.draft_id = identity
                self.draft.setPlainText(result.draft_xml.decode("utf-8"))
                self.pages.setCurrentWidget(self.draft)
            else:
                self.pages.setCurrentWidget(self.errors)
            self.status.setText("Souhrn + PVPOJ + PP | XSD {0}, blokující {1}, k přezkumu {2}. Finální export NE.".format(result.xsd_valid, len(result.issues), len(result.review_issues)))
        except Exception:
            self.status.setText("Měsíční paket nevytvořen. Ověřte organizaci, měsíc, souhrny Windows-1250, mapování a hlavičku.")

    def prepare_xml_paths(self, conversion, bindings, parameters):
        self.draft_id = None
        self.draft.clear()
        try:
            if not self.imported or self.imported.period != self.selected_period():
                raise ValueError("Chybí import kontextu.")
            identity, result = self.workspace.prepare_draft(self.organization_id, self.imported.id,
                strict_json(conversion.read_text(encoding="utf-8")), strict_json(bindings.read_text(encoding="utf-8")),
                strict_json(parameters.read_text(encoding="utf-8")), self.official_root)
            self.draft_id = identity
            self.draft.setPlainText(result.draft_xml.decode("utf-8"))
            self.status.setText("Pracovní jinyPrijem prošel XSD; uložen jen u vybrané organizace. Metodika neúplná, finální export NE.")
        except Exception:
            self.status.setText("Pracovní XML nevytvořeno. Ověřte VS, měsíc, identifikaci a scénář. Úplný HPP/DPP/DPČ generátor dosud chybí; jinyPrijem jej nenahrazuje.")

    def write_draft(self):
        try:
            if not self.imported or not self.draft_id or self.imported.period != self.selected_period():
                raise ValueError("Chybí pracovní XML.")
            self.workspace.write_draft(self.organization_id, self.imported.id, self.draft_id)
            self.status.setText("Pracovní XML zapsáno do datového prostoru této organizace. Soubor se nepřepisuje; nejde o finální export.")
        except Exception:
            self.status.setText("Pracovní XML nelze uložit nebo už existuje. Žádný soubor nebyl přepsán.")

    def open_audit_history(self):
        if not self.imported or self.imported.period != self.selected_period():
            self.status.setText("Vyberte import aktuální organizace a měsíce.")
            return
        org, identity = self.organization_id, self.imported.id
        checks = self.workspace.analysis_history(org, identity)
        drafts = self.workspace.draft_history(org, identity)
        dialog = QDialog(self)
        dialog.setWindowTitle(self.context.text() + " – neměnná historie vybraného importu")
        dialog.resize(1050, 700)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Vyberte uloženou kontrolu nebo pracovní XML. Výsledky se znovu nepřepočítávají.\n"
                                "Částky a XML jsou soukromá pracovní data; historie nepotvrzuje odeslání ani správnost podání."))
        tabs = QTabWidget()
        check_table, draft_table = QTableWidget(), QTableWidget()
        for table in (check_table, draft_table):
            table.setEditTriggers(enum(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.fill(check_table, ["Kontrola", "Čas UTC", "Počet nálezů"], [[r["analysis_index"], r["created_at"], r["error_count"]] for r in checks])
        self.fill(draft_table, ["Interní UUID", "Čas UTC", "SHA-256"], [[r["id"], r["created_at"], r["sha256"]] for r in drafts])
        tabs.addTab(check_table, "Kontroly a výpočty")
        tabs.addTab(draft_table, "Pracovní XML")
        layout.addWidget(tabs)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        layout.addWidget(preview)

        def show_check(row, column):
            try:
                snapshot = self.workspace.analysis_snapshot(org, identity, checks[row]["analysis_index"])
                lines = ["Uložené požadavky a chyby:"]
                lines.extend("Řádek {0}: {1} {2}".format(i["row"] or "hlavička", i["message"], i["remedy"]) for i in snapshot["report"]["issues"])
                lines.append("Uložené řádkové výpočty: " + json.dumps(snapshot["calculations"], ensure_ascii=False, indent=2))
                lines.append("Uložené součty známých hodnot: " + json.dumps(snapshot["totals"], ensure_ascii=False, indent=2))
                if snapshot.get("employee_validation"):
                    lines.append("Kontrola zaměstnaneckého XML: " + json.dumps(snapshot["employee_validation"], ensure_ascii=False, indent=2))
                if snapshot.get("monthly_validation"):
                    lines.append("Kontrola všech částí paketu: " + json.dumps(snapshot["monthly_validation"], ensure_ascii=False, indent=2))
                preview.setPlainText("\n".join(lines))
            except Exception:
                preview.setPlainText("Uložená kontrola není dostupná; žádné údaje jiné organizace se nenačítají.")

        def show_draft(row, column):
            try:
                xml = self.workspace.draft_bytes(org, identity, drafts[row]["id"]).decode("utf-8")
                validation = self.workspace.draft_validation(org, identity, drafts[row]["id"])
                preview.setPlainText(json.dumps(validation, ensure_ascii=False, indent=2) + "\n\n" + xml)
            except Exception:
                preview.setPlainText("Uložené pracovní XML není dostupné nebo nesouhlasí jeho hash.")

        check_table.cellClicked.connect(show_check)
        draft_table.cellClicked.connect(show_draft)
        tabs.currentChanged.connect(lambda *args: preview.clear())
        run(dialog)

    def open_tools(self):
        if QT_API != "PySide6":
            self.status.setText("Hlavní workflow Qt5 je dostupný; doplňkové starší nástroje vyžadují moderní variantu.")
            return
        if not self.imported or self.imported.period != self.selected_period():
            self.status.setText("Nejprve vyberte import aktuální organizace a měsíce.")
            return
        from app.ui.main_window import MainWindow
        if self.tools:
            self.tools.close()
        # Old tools inspect only the selected snapshot. New imports go through the organization service.
        org = self.workspace.organization(self.organization_id)
        self.tools = MainWindow(on_import=self.import_path, organization_context=(org.variable_symbol, self.imported.period),
                                xml_scenario_allowed="employment_type" not in self.imported.profile["metadata"])
        self.tools.setWindowTitle(self.context.text() + " – původní nástroje nad vybraným importem")
        self.tools.set_source(self.imported.source)
        self.tools.show()

    def closeEvent(self, event):
        if self.tools:
            self.tools.close()
        super().closeEvent(event)
