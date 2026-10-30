"""Ruční import a porovnání lokálních definic a dokumentů."""
import json
from pathlib import Path
import sqlite3

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.definitions.library import DefinitionLibrary


class DefinitionsPage(QWidget):
    def __init__(self, database_path: Path | None = None):
        super().__init__()
        self.database_path = database_path
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ruční import XSD, XLSX, ZIP, číselníků a metodiky – původ a účinnost zadává uživatel.\n"
                                "Import neověřuje oficiální původ ani úplnost metodiky. XML export zůstává zablokovaný."))
        form = QFormLayout()
        self.kind = QComboBox()
        for label, value in [("XSD schéma", "xsd"), ("Číselník CSV/XLSX", "codelist"), ("Metodický dokument", "methodology"),
                             ("Datový slovník XLSX", "data_dictionary"), ("Katalog kontrol XLSX", "control_catalog"),
                             ("Datové scénáře XLSX", "scenarios"), ("Archiv ZIP", "archive")]:
            self.kind.addItem(label, value)
        form.addRow("Typ dokumentu", self.kind)
        self.source = QLineEdit()
        self.source.setPlaceholderText("https://… přesná adresa původního dokumentu")
        self.version = QLineEdit()
        self.effective_from = QLineEdit()
        self.effective_until = QLineEdit()
        form.addRow("Zdrojové URL", self.source)
        form.addRow("Verze", self.version)
        form.addRow("Účinnost od (YYYY-MM-DD, lze vynechat)", self.effective_from)
        form.addRow("Účinnost do (YYYY-MM-DD, lze vynechat)", self.effective_until)
        layout.addLayout(form)
        button = QPushButton("Ručně importovat dokument…")
        button.clicked.connect(self.choose_xsd)
        layout.addWidget(button)
        catalog = QPushButton("Načíst dokumenty z katalogu manifest.json…")
        catalog.clicked.connect(self.choose_catalog)
        layout.addWidget(catalog)
        self.inventory = QTableWidget()
        self.inventory.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory.setColumnCount(9)
        self.inventory.setHorizontalHeaderLabels(["Verze", "Původ", "Technická kontrola", "Typ", "Zdroj", "Získáno UTC", "Účinnost od", "Účinnost do", "SHA-256"])
        layout.addWidget(self.inventory)
        controls = QHBoxLayout()
        self.before = QComboBox()
        self.after = QComboBox()
        controls.addWidget(QLabel("Původní"))
        controls.addWidget(self.before)
        controls.addWidget(QLabel("Nová"))
        controls.addWidget(self.after)
        button = QPushButton("Porovnat dokumenty")
        button.clicked.connect(self.compare)
        controls.addWidget(button)
        layout.addLayout(controls)
        self.summary = QLabel("Metodická pravidla a dopad na interní CSV mapování nejsou vyhodnoceny.")
        layout.addWidget(self.summary)
        self.changes = QTableWidget()
        self.changes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.changes.setColumnCount(4)
        self.changes.setHorizontalHeaderLabels(["Změna", "Cesta ve schématu", "Původně", "Nově"])
        self.changes.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.changes)
        # No directory or DB is created until a user actually imports a definition.
        if self.path().exists():
            try:
                self.refresh()
            except (ValueError, OSError, sqlite3.Error):
                self.summary.setText("Knihovnu nelze načíst. Ověřte místní konfiguraci.")

    def path(self) -> Path:
        if self.database_path is not None:
            return self.database_path
        directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        return directory / "definitions.sqlite3"

    def library(self) -> DefinitionLibrary:
        return DefinitionLibrary(self.path())

    def refresh(self) -> None:
        entries = self.library().list_definitions()
        self.inventory.setRowCount(len(entries))
        self.before.clear()
        self.after.clear()
        for i, entry in enumerate(entries):
            a = entry.artifact
            technical_labels = {"standalone_xsd_valid": "Samostatné XSD platné", "dependencies_unchecked": "XSD závislosti neověřeny",
                                "csv_parsed": "CSV načteno", "json_parsed": "JSON načten", "text_decoded": "Text načten",
                                "retained_only": "Pouze archivováno", "not_checked": "Neprovedena",
                                "xlsx_read_not_validated": "XLSX načteno; obsah nevalidován", "zip_crc_checked": "ZIP CRC ověřeno; obsah nevalidován"}
            for j, value in enumerate([a.version, "NEOVĚŘENO", technical_labels.get(a.technical_status, "Neznámá"), a.kind, a.source_url, a.acquired_at,
                                       a.effective_from or "neznámá", a.effective_until or "neznámá", a.sha256]):
                self.inventory.setItem(i, j, QTableWidgetItem(value))
            label = f"{a.kind} {a.version} ({a.sha256[:12]})"
            self.before.addItem(label, entry.id)
            self.after.addItem(label, entry.id)
        if entries:
            self.after.setCurrentIndex(len(entries) - 1)
        self.inventory.resizeColumnsToContents()

    def import_path(self, path: Path) -> int:
        id_ = self.library().import_document(path, self.source.text().strip(), self.version.text().strip(), self.kind.currentData(),
                                            self.effective_from.text().strip() or None, self.effective_until.text().strip() or None)
        self.refresh()
        self.changes.setRowCount(0)
        self.summary.setText("Dokument uložen lokálně, původ NEOVĚŘEN. Technická kontrola je uvedena samostatně. Finální XML není povoleno.")
        return id_

    def choose_xsd(self) -> None:
        filters = {"xsd": "XSD (*.xsd)", "codelist": "Číselník (*.csv *.xlsx)", "methodology": "Metodika (*.pdf *.txt *.md *.json *.xlsx)",
                   "data_dictionary": "Slovník (*.xlsx)", "control_catalog": "Kontroly (*.xlsx)", "scenarios": "Scénáře (*.xlsx)", "archive": "ZIP (*.zip)"}
        path, _ = QFileDialog.getOpenFileName(self, "Import dokumentu", "", filters[self.kind.currentData()])
        if not path:
            return
        try:
            self.import_path(Path(path))
        except Exception:
            QMessageBox.warning(self, "Definice", "Import selhal. Limit 25 MiB na dokument (XSD 5 MiB); podporovány XSD, XLSX, ZIP, CSV, PDF/TXT/MD/JSON.\n"
                                "Ověřte formát, veřejné HTTPS URL bez query, verzi, data účinnosti a přístup k databázi.")

    def choose_catalog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Katalog oficiálních podkladů", "", "Manifest (manifest.json)")
        if not filename:
            return
        try:
            count = self.library().import_catalog(Path(filename).parent)
            self.refresh()
            self.summary.setText(f"Načteno položek katalogu: {count}. Původ zůstává NEOVĚŘEN; import neaktivuje XML export.")
        except Exception:
            try:
                self.refresh()
            except (ValueError, OSError, sqlite3.Error):
                self.inventory.setRowCount(0)
            QMessageBox.warning(self, "Katalog", "Import katalogu se nedokončil. Ověřte hashe, formáty a metadata.\n"
                                "Již zpracované položky mohou být v knihovně; opakování stejného importu je neduplikuje.")

    def compare(self) -> None:
        if self.before.currentData() is None or self.after.currentData() is None:
            self.summary.setText("Nejprve importujte definice pro porovnání.")
            return
        try:
            changes = self.library().compare(self.before.currentData(), self.after.currentData())
            self.changes.setRowCount(len(changes))
            labels = {"added": "Přidáno", "removed": "Odstraněno", "changed": "Změněno"}
            for i, change in enumerate(changes):
                for j, value in enumerate([labels[change.kind], change.path,
                                           json.dumps(change.before, ensure_ascii=False), json.dumps(change.after, ensure_ascii=False)]):
                    self.changes.setItem(i, j, QTableWidgetItem(value))
            self.changes.resizeColumnsToContents()
            self.summary.setText(f"Změny dokumentu: {len(changes)}. Význam metodiky a dopad na mapování nevyhodnoceny; původ neověřen.")
        except Exception:
            self.changes.setRowCount(0)
            self.summary.setText("Porovnání selhalo: ověřte dostupnost knihovny a integritu uložených XSD.")
