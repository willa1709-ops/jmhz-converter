"""Private offline receipt viewer shared by Qt5 and Qt6."""
import json
from pathlib import Path

from app.ui.qt_compat import QtWidgets, QtCore, enum
from app.core.receipts import (OUTCOMES, ReceiptError, read_receipt, import_receipt,
                               receipt_history, receipt_detail, save_original)


class ReceiptsDialog(QtWidgets.QDialog):
    def __init__(self, workspace, organization_id, import_id, selected_draft=None, parent=None):
        super().__init__(parent)
        self.workspace, self.organization_id, self.import_id = workspace, organization_id, import_id
        self.selected_receipt = None
        imported = workspace.get_import(organization_id, import_id)
        org = workspace.organization(organization_id)
        self.setWindowTitle("Protokoly ČSSZ – soukromá evidence odpovědí")
        self.resize(900, 650)
        layout = QtWidgets.QVBoxLayout(self)
        context = QtWidgets.QLabel(org.name + " | " + imported.period.iso + " | vybraný import")
        context.setTextFormat(enum(QtCore.Qt, "TextFormat", "PlainText"))
        context.setWordWrap(True)
        layout.addWidget(context)
        notice = QtWidgets.QLabel("DIS: přijetí do dalšího zpracování není potvrzení úplnosti měsíčního hlášení.\n"
            "cJMHZ: zobrazuje se stav hlášení uvedený v XML; výsledek jednotlivého podání se z něj neodvozuje.\n"
            "Původ ani podpis protokolu se neověřují. PDF a neznámé XML se ukládají jako nevyhodnocené přílohy.\n"
            "Protokoly mohou obsahovat osobní údaje. DB a zálohy nejsou šifrované. Finální export zůstává blokovaný.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QtWidgets.QFormLayout()
        self.drafts = QtWidgets.QComboBox()
        self.drafts.setSizeAdjustPolicy(enum(QtWidgets.QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"))
        self.drafts.setMinimumContentsLength(20)
        for draft in workspace.draft_history(organization_id, import_id):
            self.drafts.addItem(draft["created_at"] + " | " + draft["id"], draft["id"])
        if selected_draft:
            self.drafts.setCurrentIndex(self.drafts.findData(selected_draft))
        elif self.drafts.count():
            self.drafts.setCurrentIndex(self.drafts.count() - 1)
        self.reference = QtWidgets.QLineEdit()
        self.reference.setMaxLength(500)
        self.reference.setPlaceholderText("Volitelné: skutečné vlastní ID odeslané zprávy; není GUID měsíčního hlášení")
        self.concrete_reference = QtWidgets.QLineEdit()
        self.concrete_reference.setMaxLength(500)
        self.concrete_reference.setPlaceholderText("Volitelné idKonkretnihoPodani – přesný text; není GUID měsíčního hlášení")
        self.batch_count = QtWidgets.QSpinBox()
        self.batch_count.setRange(0, 100000)
        self.batch_count.setSpecialValueText("Nevím – neodvozovat")
        form.addRow("Konkrétní odeslané pracovní XML", self.drafts)
        form.addRow("DIS: vlastní ID zprávy", self.reference)
        form.addRow("cJMHZ: ID konkrétního podání", self.concrete_reference)
        form.addRow("Počet balíků původního dílčího ePodání", self.batch_count)
        layout.addLayout(form)
        self.confirm = QtWidgets.QCheckBox("Potvrzuji organizaci, období a vybrané XML pro tuto odpověď.")
        layout.addWidget(self.confirm)
        self.drafts.currentIndexChanged.connect(lambda *args: self.confirm.setChecked(False))
        button = QtWidgets.QPushButton("Načíst protokol XML / přílohu PDF…")
        button.clicked.connect(self.choose_file)
        layout.addWidget(button)
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(enum(QtWidgets.QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.table.setSelectionBehavior(enum(QtWidgets.QAbstractItemView, "SelectionBehavior", "SelectRows"))
        self.table.cellClicked.connect(self.show_detail)
        layout.addWidget(self.table)
        self.tabs = QtWidgets.QTabWidget()
        self.findings = QtWidgets.QTableWidget()
        self.findings.setEditTriggers(enum(QtWidgets.QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.tabs.addTab(self.findings, "Nálezy / části podání")
        self.detail = QtWidgets.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.tabs.addTab(self.detail, "Údaje protokolu")
        layout.addWidget(self.tabs)
        save_button = QtWidgets.QPushButton("Uložit původní XML / PDF…")
        save_button.clicked.connect(self.save_selected)
        layout.addWidget(save_button)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self):
        self.selected_receipt = None
        if hasattr(self, "detail"):
            self.detail.clear()
            self.findings.setRowCount(0)
        self.records = receipt_history(self.workspace, self.organization_id, self.import_id)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Čas načtení", "Druh", "Výsledek / rozsah", "SHA-256"])
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            for col, text in enumerate((record["created_at"], record["kind"], OUTCOMES[record["outcome"]], record["sha256"])):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def choose_file(self):
        if not self.confirm.isChecked() or not self.drafts.currentData():
            self.status.setText("Nejprve zvolte konkrétní XML a potvrďte kontext; VS/období nemusí být v protokolu uvedeny.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Protokol zpracování – offline import", "", "XML/PDF (*.xml *.pdf)")
        if path:
            self.import_path(Path(path))

    def import_path(self, path):
        try:
            identity = import_receipt(self.workspace, self.organization_id, self.import_id, self.drafts.currentData(), read_receipt(path),
                context_confirmed=self.confirm.isChecked(), expected_reference=self.reference.text() or None,
                batch_count=self.batch_count.value() or None, expected_concrete_id=self.concrete_reference.text() or None)
            self.refresh()
            row = next(i for i, record in enumerate(self.records) if record["id"] == identity)
            self.show_detail(row, 0)
            self.status.setText("Protokol uložen v organizaci. Opakované načtení stejných bajtů nepřepisuje historii. Finální export NE.")
            return identity
        except ReceiptError as error:
            self.status.setText(str(error))
        except Exception:
            self.status.setText("Protokol nelze načíst nebo uložit. Ověřte kontext, formát a integritu; osobní údaje se nevypisují do logu.")
        return None

    def show_detail(self, row, column):
        try:
            data = receipt_detail(self.workspace, self.organization_id, self.import_id, self.records[row]["id"])
            report = data["report"]
            text = OUTCOMES[report["outcome"]] + "\n"
            if report["kind"] == "cjmhz_completeness":
                text += "Stav měsíčního hlášení je převzatý z XML, původ/podpis nejsou ověřené.\nStav konkrétního podání a jednotlivých PP se z něj neodvozuje. Finální export NE.\n\n"
            else:
                text += "Nejde o potvrzení úplnosti měsíčního hlášení nebo připravenosti k podání.\n\n"
            text += json.dumps(data, ensure_ascii=False, indent=2)
            if len(text) > 250000:
                text = text[:250000] + "\n[Náhled zkrácen; originál je uchován v databázi organizace.]"
            self.detail.setPlainText(text)
            items = report.get("items", [])
            self.findings.setColumnCount(7)
            self.findings.setHorizontalHeaderLabels(["Část / rozsah", "GUID formuláře", "Interní PP", "Kód", "Typ / výsledek", "Popis", "Vazba"])
            self.findings.setRowCount(len(items))
            for i, item in enumerate(items):
                values = (item.get("part_as_received", item["subtype"]), item.get("form_guid", ""), item.get("internal_number", ""),
                          item.get("error_code", ""), item.get("error_type", item.get("result", "")), item.get("message", ""), item.get("link_status", ""))
                for col, value in enumerate(values):
                    self.findings.setItem(i, col, QtWidgets.QTableWidgetItem(str(value)))
            self.findings.resizeColumnsToContents()
            self.findings.setColumnWidth(5, 380)
            self.tabs.setCurrentWidget(self.findings if items else self.detail)
            self.selected_receipt = self.records[row]
        except Exception:
            self.selected_receipt = None
            self.findings.setRowCount(0)
            self.detail.setPlainText("Protokol není dostupný v tomto kontextu nebo neprošel kontrolou integrity.")

    def save_selected(self):
        if not self.selected_receipt:
            self.status.setText("Nejprve vyberte uložený protokol.")
            return
        extension = ".pdf" if self.selected_receipt["kind"] == "pdf_attachment" else ".xml"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Originál může obsahovat osobní údaje – chráněné umístění", "protokol-" + self.selected_receipt["id"] + extension)
        if path:
            try:
                save_original(self.workspace, self.organization_id, self.import_id, self.selected_receipt["id"], path)
                self.status.setText("Původní soubor uložen beze změny. Není šifrovaný; podpis ani původ se tím nepotvrzují.")
            except Exception:
                self.status.setText("Originál se nepodařilo uložit. Ověřte integritu a nový cílový soubor; nic existujícího se nepřepisuje.")
