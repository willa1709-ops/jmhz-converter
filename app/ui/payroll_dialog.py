"""Lokální přehled číslovaných položek a primárních PP, bez identifikátorů v diagnostice."""
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
                               QLineEdit, QSpinBox, QInputDialog, QTableWidget, QTableWidgetItem,
                               QAbstractItemView)

from app.core.packages import install_package
from app.core.payroll import load_numbered_profile, prepare_payroll
from app.core.periods import Period, SubmissionContext


class PayrollDialog(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source, self.profile, self.result = source, None, None
        self.setWindowTitle("Číslované mzdové položky – pracovní kontrola")
        self.resize(1100, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Jeden řádek = jeden PP. OIČ/RČ se používají jen pro párování v paměti.\n"
                                "Součty jsou řádkové, interní revize není GUID ani automatické opravné podání. Finální export NE."))
        buttons = QHBoxLayout()
        local = QPushButton("Načíst pracovní profil JSON…")
        local.clicked.connect(self.choose_profile)
        package = QPushButton("Nainstalovat ověřený offline ZIP…")
        package.clicked.connect(self.choose_package)
        buttons.addWidget(local)
        buttons.addWidget(package)
        layout.addLayout(buttons)
        self.profile_status = QLabel("Profil dosud nevybrán.")
        layout.addWidget(self.profile_status)
        context = QHBoxLayout()
        self.period = QLineEdit()
        self.period.setPlaceholderText("26-09 nebo 2026-09")
        self.revision = QSpinBox()
        self.revision.setRange(0, 1_000_000)
        context.addWidget(QLabel("Období"))
        context.addWidget(self.period)
        context.addWidget(QLabel("Interní revize"))
        context.addWidget(self.revision)
        run = QPushButton("Párovat a spočítat")
        run.clicked.connect(self.analyze)
        context.addWidget(run)
        layout.addLayout(context)
        self.summary = QLabel("Kontrola dosud neproběhla.")
        layout.addWidget(self.summary)
        self.rows = QTableWidget()
        self.rows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.rows)
        self.errors = QTableWidget()
        self.errors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.errors)
        self.period.textChanged.connect(self.invalidate)
        self.revision.valueChanged.connect(self.invalidate)

    def invalidate(self, *args):
        self.result = None
        self.rows.setRowCount(0)
        self.errors.setRowCount(0)
        self.summary.setText("Kontext/profil změněn; spusťte kontrolu znovu.")

    def load_profile_path(self, path: Path):
        self.invalidate()
        self.profile = load_numbered_profile(path.read_text(encoding="utf-8"))
        self.profile_status.setText("Lokální pracovní profil; původ a mzdové mapování nejsou potvrzené.")

    def choose_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Profil číslovaných položek", "", "JSON (*.json)")
        if path:
            try:
                self.load_profile_path(Path(path))
            except Exception:
                self.profile = None
                self.profile_status.setText("Profil nelze načíst. Ověřte formát, odkazy a podporované operace.")

    def choose_package(self):
        path, _ = QFileDialog.getOpenFileName(self, "Offline balíček definic", "", "ZIP (*.zip)")
        if not path:
            return
        approved, ok = QInputDialog.getText(self, "Nezávisle schválený hash", "SHA-256 manifestu od správce definic (ne pouze údaj ze ZIPu):")
        if ok:
            self.invalidate()
            self.profile = None
            try:
                store = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "definition-packages"
                package = install_package(Path(path), store, approved.strip())
                self.profile = package.profile
                self.profile_status.setText("Balíček ověřen vůči schválenému hashi; původ a metodika zůstávají předmětem přezkumu.")
            except Exception:
                self.profile_status.setText("Balíček nebyl přijat. Ověřte hash, verzi logiky, obsah a oprávnění k úložišti.")

    @staticmethod
    def fill(table, headers, rows):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def analyze(self):
        self.invalidate()
        if self.profile is None:
            self.summary.setText("Nejprve načtěte platný profil nebo ověřený balíček.")
            return
        try:
            context = SubmissionContext(Period.parse(self.period.text().strip(), self.profile["period_century"]), self.revision.value())
            self.result = prepare_payroll(self.source, self.profile, context)
            names = list(self.profile["calculations"])
            self.fill(self.rows, ["Řádek", "Interní PP", "Období", "Skupina", "Primární PP"] + names,
                      [[r.number, r.metadata.get("internal_number", ""), r.period.iso, r.person_group or "nespárováno",
                        "neurčen" if r.primary_pp is None else "ano" if r.primary_pp else "ne"] +
                       ["neplatné" if r.calculations.get(n) is None else format(r.calculations[n], "f") for n in names]
                       for r in self.result.rows])
            self.fill(self.errors, ["Řádek", "Pole", "Kód", "Problém", "Náprava"],
                      [[i.row or "hlavička", i.field, i.code, i.message, i.remedy] for i in self.result.issues])
            self.summary.setText("Období {0}, interní revize {1}; nálezy {2}. Finální export NE.".format(context.period.iso, context.revision_index, len(self.result.issues)))
        except Exception:
            self.result = None
            self.summary.setText("Kontrola selhala. Ověřte kontext a profil; identifikátory se do diagnostiky nevypisují.")
