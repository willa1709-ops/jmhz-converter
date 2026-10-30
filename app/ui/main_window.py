import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.calculations import MONEY_FIELDS, total
from app.importers import read_csv, read_xlsx
from app.mapping import DRAFT_VERSION, FIELDS, Profile, map_dataset
from app.models import Dataset, Finding, Severity
from app.storage import Store
from app.validation import validate
from app.ui.definitions_page import DefinitionsPage
from app.xml.bundle import registered_validator
from app.core.conversion import prepare_conversion
from app.core.mapping import load_profile as load_conversion_profile
from app.core.resources import default_official_root


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JMHZ Converter – pracovní prototyp")
        self.resize(1150, 780)
        self.source: Dataset | None = None
        self.findings: list[Finding] = []
        self.profile = Profile.default()
        self.generated_draft: bytes | None = None
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.import_page = self.page("Import dat")
        self.import_page.addWidget(QLabel("Data zůstávají na tomto počítači. Finální XML zatím není dostupné."))
        controls = QHBoxLayout()
        self.encoding = QComboBox()
        self.encoding.addItems(["auto", "utf-8-sig", "cp1250"])
        self.delimiter = QComboBox()
        self.delimiter.addItems(["auto", ";", ",", "\t", "|"])
        controls.addWidget(QLabel("Kódování CSV"))
        controls.addWidget(self.encoding)
        controls.addWidget(QLabel("Oddělovač CSV"))
        controls.addWidget(self.delimiter)
        button = QPushButton("Načíst CSV / XLSX…")
        button.clicked.connect(self.choose_input)
        controls.addWidget(button)
        self.import_page.addLayout(controls)
        self.import_page.addWidget(QLabel("XLSX: aktivní list, identifikátory jako text, částky textové nebo číselné, bez vzorců. Limit 25 MiB / 100 000 řádků."))
        self.preview = self.table()
        self.page("Náhled").addWidget(self.preview)

        mapping = self.page("Mapování")
        mapping.addWidget(QLabel("Interní pole pracovního profilu; vazba na oficiální JMHZ dosud není ověřena."))
        self.rules = QTableWidget(len(FIELDS), 2)
        self.rules.setHorizontalHeaderLabels(["Interní údaj", "Deklarativní pravidlo JSON"])
        self.rules.horizontalHeader().setStretchLastSection(True)
        mapping.addWidget(self.rules)
        self.profile_label = QLabel()
        mapping.addWidget(self.profile_label)
        buttons = QHBoxLayout()
        for label, handler in [("Načíst profil…", self.load_profile), ("Uložit profil…", self.save_profile),
                               ("Zkontrolovat", self.check)]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        mapping.addLayout(buttons)
        self.show_profile()

        checks = self.page("Kontrola dat")
        self.period = QLineEdit()
        self.period.setPlaceholderText("Očekávané období YYYY-MM (volitelné)")
        checks.addWidget(self.period)
        button = QPushButton("Zkontrolovat a přepočítat")
        button.clicked.connect(self.check)
        checks.addWidget(button)
        checks.addWidget(QLabel("Dvojklik na nález otevře příslušný zdrojový řádek."))
        self.errors = self.table()
        self.errors.cellDoubleClicked.connect(self.goto_row)
        checks.addWidget(self.errors)

        self.sums = QTextEdit()
        self.sums.setReadOnly(True)
        self.page("Kontrolní součty").addWidget(self.sums)
        xml = self.page("Generování XML")
        xml.addWidget(QLabel("Finální export ZABLOKOVÁN: úplný mzdový převod a metodická kontrola ještě nejsou hotové.\n"
                            "Původ a účinnost celých sad vyžadují přezkum. Úspěch XSD není připravenost k podání."))
        export = QPushButton("Vygenerovat finální XML")
        export.setEnabled(False)
        xml.addWidget(export)
        xml.addWidget(QLabel("Samostatná technická kontrola XML proti dodanému XSD.\n"
                            "Balíček vyberte výslovně; účinnost celé sady se neurčuje podle složky.\n"
                            "Úspěch XSD kontroly nepotvrzuje metodiku, původ ani připravenost k podání."))
        self.official_root = default_official_root()
        self.bundle_choice = QComboBox()
        bundle_index = self.official_root / "bundles.json"
        if bundle_index.is_file():
            try:
                for bundle in json.loads(bundle_index.read_text())["bundles"]:
                    self.bundle_choice.addItem(bundle["id"], bundle["id"])
            except (ValueError, KeyError, TypeError):
                self.bundle_choice.clear()
        xml.addWidget(self.bundle_choice)
        validate_xml = QPushButton("Vybrat XML a ověřit proti XSD…")
        validate_xml.clicked.connect(self.choose_xml_validation)
        validate_xml.setEnabled(self.bundle_choice.count() > 0)
        xml.addWidget(validate_xml)
        self.xml_validation_result = QTextEdit()
        self.xml_validation_result.setReadOnly(True)
        xml.addWidget(self.xml_validation_result)
        conversion = QPushButton("Pracovní CSV/XLSX → XML: zvolit konverzní profil a parametry…")
        conversion.clicked.connect(self.choose_conversion)
        xml.addWidget(conversion)
        xml.addWidget(QLabel("Experimentální scénář jinyPrijem (činnosti 11, 13, 14), vlastní profil z config/conversion.\n"
                            "Povinné skutečné vstupy doplňte podle dokumentace; původní profil pěti sloupců nestačí.\n"
                            "Výsledek je pouze náhled pracovního XML, finální export je blokovaný."))
        self.conversion_status = QLabel("Pracovní převod dosud neproveden.")
        xml.addWidget(self.conversion_status)
        self.draft_preview = QTextEdit()
        self.draft_preview.setReadOnly(True)
        xml.addWidget(self.draft_preview)
        self.definitions_page = DefinitionsPage()
        self.tabs.addTab(self.definitions_page, "Definice JMHZ")
        settings = self.page("Nastavení")
        settings.addWidget(QLabel("Bez síťové komunikace a telemetrie. Importovaná mzdová data se automaticky neukládají.\n"
                                 "Profily ukládejte bez osobních údajů a hesel.\n"
                                 "SQLite obsahuje pouze konfiguraci; nejde o šifrovaný trezor."))

    def page(self, name: str) -> QVBoxLayout:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.tabs.addTab(widget, name)
        return layout

    def choose_xml_validation(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "XML ke kontrole", "", "XML (*.xml)")
        if filename:
            self.validate_xml_path(Path(filename))

    def choose_conversion(self) -> None:
        if self.source is None:
            QMessageBox.information(self, "Pracovní převod", "Nejprve načtěte vstupní CSV nebo XLSX.")
            return
        profile, _ = QFileDialog.getOpenFileName(self, "Konverzní profil (config/conversion)", "", "JSON (*.json)")
        if not profile:
            return
        parameters, _ = QFileDialog.getOpenFileName(self, "Skutečné parametry podání", "", "JSON (*.json)")
        if parameters:
            self.prepare_conversion_paths(Path(profile), Path(parameters))

    def prepare_conversion_paths(self, profile: Path, parameters: Path) -> None:
        self.generated_draft = None
        self.draft_preview.clear()
        try:
            if self.source is None:
                raise ValueError("Chybí vstup.")
            result = prepare_conversion(self.source, load_conversion_profile(profile.read_text(encoding="utf-8")),
                                        json.loads(parameters.read_text(encoding="utf-8")), self.official_root)
            self.generated_draft = result.draft_xml
            self.conversion_status.setText("XSD: " + ("PROŠLO" if result.xsd_valid else "NEPROŠLO") +
                                           "; metodika neúplná, původ neověřen; finální export NE.")
            if result.draft_xml:
                self.draft_preview.setPlainText(result.draft_xml.decode("utf-8"))
            else:
                self.draft_preview.setPlainText("\n".join(f"Řádek {i.row or 'hlavička'} | {i.field}: {i.message} {i.remedy}" for i in result.issues))
        except Exception:
            self.conversion_status.setText("Pracovní převod nelze připravit. Ověřte profil, parametry a XSD podklady.")

    def validate_xml_path(self, path: Path) -> None:
        try:
            if path.stat().st_size > 25 * 1024 * 1024:
                raise ValueError("Příliš velké XML.")
            bundle_id = self.bundle_choice.currentData()
            validator = registered_validator(self.official_root, bundle_id)
            result = validator.validate(path.read_bytes())
            lines = [f"Balíček: {bundle_id}", "XSD: " + ("PROŠLO" if result.xsd_valid else "NEPROŠLO"),
                     "Metodická validace: neprovedena. Původ: neověřen. K podání: NE."]
            self.xml_validation_result.setPlainText("\n".join(lines + list(result.errors)))
        except Exception:
            self.xml_validation_result.setPlainText("Kontrolu nelze provést. Ověřte dostupnost souboru, limit 25 MiB a integritu XSD balíčku.")

    @staticmethod
    def table() -> QTableWidget:
        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        return table

    @staticmethod
    def fill(table: QTableWidget, headers: list[str], rows: list[list[str]]) -> None:
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(value))
        table.resizeColumnsToContents()

    def show_profile(self) -> None:
        self.profile_label.setText(f"Profil: {self.profile.name} | Definice: {self.profile.definition_version}")
        for i, field in enumerate(FIELDS):
            item = QTableWidgetItem(field)
            from PySide6.QtCore import Qt
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.rules.setItem(i, 0, item)
            self.rules.setItem(i, 1, QTableWidgetItem(json.dumps(self.profile.rules.get(field, {"op": "constant", "value": ""}), ensure_ascii=False)))

    def current_profile(self) -> Profile:
        rules = {field: json.loads(self.rules.item(i, 1).text()) for i, field in enumerate(FIELDS)}
        return Profile.loads(Profile(self.profile.name, self.profile.definition_version, rules).dumps())

    def choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Načíst data", "", "Mzdová data (*.csv *.xlsx)")
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path) -> None:
        try:
            source = read_xlsx(path) if path.suffix.lower() == ".xlsx" else read_csv(path, self.encoding.currentText(), self.delimiter.currentText())
            self.source = source
            self.generated_draft = None
            self.draft_preview.clear()
            self.fill(self.preview, list(source.columns), [[r.values[c] for c in source.columns] for r in source.rows])
            self.check()
            self.tabs.setCurrentIndex(1)
        except Exception:
            # No raw parser exceptions: they can include cell contents / personal data.
            QMessageBox.warning(self, "Import selhal", "Ověřte kódování, oddělovač, hlavičky a počet buněk.\n"
                                "XLSX nepodporuje vzorce, datumové a chybové buňky. Soubor musí obsahovat data a splnit limity.")

    def check(self) -> None:
        if self.source is None:
            return
        try:
            self.profile = self.current_profile()
            if self.profile.definition_version != DRAFT_VERSION:
                raise ValueError("Profil jiné verze.")
            mapped, errors = map_dataset(self.source, self.profile)
            self.findings = errors + validate(mapped, self.period.text().strip() or None)
            self.fill(self.errors, ["Úroveň", "Řádek", "Záznam", "Položka", "Problém", "Náprava"],
                      [[f.severity.value, str(f.row or ""), f.record_id, f.field, f.message, f.remedy] for f in self.findings])
            bad = {f.row for f in self.findings if f.severity == Severity.ERROR and f.row is not None}
            count = len(mapped.rows)
            employees = {r.values.get("employee_id") for r in mapped.rows} - {"", None}
            lines = [f"Záznamy: {count} | Zaměstnanci: {len(employees)} | Bez technické chyby: {count-len(bad)} | S chybou: {len(bad)}",
                     "Pouze technické kontroly pracovního profilu; podání JMHZ není ověřeno.",
                     "Součty zahrnují všechny číselně čitelné hodnoty včetně chybných/duplicitních řádků."]
            for field in MONEY_FIELDS:
                target = total(mapped.rows, field)
                lines.append(f"{field}: cíl {target.value}; chybí {target.missing}; neplatné {target.invalid}")
                rule = self.profile.rules.get(field, {})
                if rule.get("op") == "column":
                    source = total(self.source.rows, rule["name"])
                    lines.append(f"  Zdroj {source.value}; chybí {source.missing}; neplatné {source.invalid}; rozdíl {target.value-source.value}")
                else:
                    lines.append("  Složené pravidlo: zdrojový kontrolní základ není určen; rozdíl nevyhodnocen.")
            self.sums.setPlainText("\n".join(lines))
        except (ValueError, TypeError, KeyError):
            # Invalidate stale results if the new profile cannot be used.
            self.findings = []
            self.errors.setRowCount(0)
            self.sums.setPlainText("Kontrola neproběhla: opravte JSON mapování nebo verzi profilu.")
            QMessageBox.warning(self, "Mapování", "Neplatný JSON nebo nepodporovaná verze profilu.")

    def goto_row(self, index: int, column: int) -> None:
        if self.source is None or index >= len(self.findings):
            return
        number = self.findings[index].row
        for i, row in enumerate(self.source.rows):
            if row.number == number:
                self.tabs.setCurrentIndex(1)
                self.preview.selectRow(i)
                self.preview.scrollToItem(self.preview.item(i, 0))
                return

    def save_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Uložit profil", "mapping.json", "JSON (*.json)")
        if not path:
            return
        try:
            profile = self.current_profile()
            profile.save(Path(path))
            directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
            Store(directory / "config.sqlite3").save_profile(profile)
        except (ValueError, OSError, TypeError):
            QMessageBox.warning(self, "Profil", "Profil nelze uložit. Ověřte pravidla a přístup k souboru.")

    def load_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Načíst profil", "", "JSON (*.json)")
        if not path:
            return
        try:
            profile = Profile.loads(Path(path).read_text(encoding="utf-8"))
            if profile.definition_version != DRAFT_VERSION:
                raise ValueError("Jiná verze definice.")
            self.profile = profile
            self.show_profile()
            self.check()
        except (ValueError, OSError):
            QMessageBox.warning(self, "Profil", "Neplatný profil nebo nepodporovaná verze definice.")
