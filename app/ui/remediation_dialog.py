"""Organization/month correction ledger, shared Qt5/Qt6; no payroll editing."""
import json
from app.ui.qt_compat import QtWidgets, QtCore, enum, run
from app.core import remediation as tracking
from app.core.receipts import ReceiptError, OUTCOMES, receipt_history, receipt_detail


class RemediationDialog(QtWidgets.QDialog):
    def __init__(self, workspace, organization_id, period, parent=None):
        super().__init__(parent)
        self.workspace, self.org, self.period = workspace, organization_id, period
        self.setWindowTitle("Chyby a opravy – historie nálezů a odpovědí")
        self.resize(1000, 720)
        outer = QtWidgets.QVBoxLayout(self)
        self.scroll = QtWidgets.QScrollArea();self.scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget();self.scroll.setWidget(content);outer.addWidget(self.scroll)
        layout = QtWidgets.QVBoxLayout(content)
        label = QtWidgets.QLabel(workspace.organization(organization_id).name + ' | ' + period.iso)
        label.setTextFormat(enum(QtCore.Qt, 'TextFormat', 'PlainText'))
        label.setWordWrap(True);layout.addWidget(label)
        notice = QtWidgets.QLabel('Data opravte ve mzdovém systému a načtěte nový import / pracovní XML. Zde evidujete návaznosti.\n'
            'Zmizení chyby ani DIS přijetí nejsou automatické vyřešení. Uzavření je výslovný ruční přezkum.\n'
            'Evidence není opravné XML ani odeslání. Finální export je blokovaný; údaje a zálohy nejsou šifrované.')
        notice.setWordWrap(True);layout.addWidget(notice)
        self.show_linked = QtWidgets.QCheckBox('Zobrazit také výskyty navázané na původní nález')
        self.show_linked.toggled.connect(self.refresh);layout.addWidget(self.show_linked)
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(enum(QtWidgets.QAbstractItemView, 'EditTrigger', 'NoEditTriggers'))
        self.table.setSelectionBehavior(enum(QtWidgets.QAbstractItemView, 'SelectionBehavior', 'SelectRows'))
        self.table.setSelectionMode(enum(QtWidgets.QAbstractItemView, 'SelectionMode', 'ExtendedSelection'))
        self.table.cellClicked.connect(self.show_case);layout.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel('Interní oprava (nikoliv typ podání)'))
        self.run_choice = QtWidgets.QComboBox()
        self.run_choice.setSizeAdjustPolicy(enum(QtWidgets.QComboBox, 'SizeAdjustPolicy', 'AdjustToMinimumContentsLengthWithIcon'))
        self.run_choice.setMinimumContentsLength(20);row.addWidget(self.run_choice);layout.addLayout(row)
        buttons = QtWidgets.QGridLayout()
        for i, (label, action) in enumerate([
            ('Zapsat připravenou opravu…', self.prepare), ('Zaznamenat externí odeslání…', self.dispatch),
            ('Navázat již načtenou odpověď…', self.link), ('Ruční spárování výskytu…', self.link_occurrence),
            ('Uzavřít po přezkumu…', self.close_case), ('Znovu otevřít nález…', self.reopen_case), ('Poznámka k šetření…', self.add_note)]):
            button = QtWidgets.QPushButton(label);button.clicked.connect(action);buttons.addWidget(button, i//2, i%2)
        layout.addLayout(buttons)
        self.history = QtWidgets.QPlainTextEdit();self.history.setReadOnly(True);layout.addWidget(self.history)
        self.summary = QtWidgets.QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.status = QtWidgets.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.refresh()

    def refresh(self, *args):
        self.records = [c for c in tracking.cases(self.workspace, self.org, self.period) if self.show_linked.isChecked() or c['state'] != 'linked_occurrence']
        self.table.setColumnCount(5);self.table.setHorizontalHeaderLabels(['Kód', 'Část', 'Interní PP', 'Stav sledování', 'Původní popis'])
        self.table.setRowCount(len(self.records))
        for row, case in enumerate(self.records):
            s = case['snapshot']
            for col, value in enumerate((s['code'], s['part'], s['internal_number'], tracking.STATES[case['state']], s['message'])):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        self.table.resizeColumnsToContents();self.table.setColumnWidth(4, 380)
        previous = self.run_choice.currentData()
        self.run_records = tracking.runs(self.workspace, self.org, self.period)
        self.run_choice.clear()
        for item in self.run_records:
            self.run_choice.addItem('Oprava {0} | {1}'.format(item['run_index'], item['created_at']), item['id'])
        selected = self.run_choice.findData(previous)
        self.run_choice.setCurrentIndex(selected if selected >= 0 else len(self.run_records)-1)
        closed = sum(c['state'] == 'closed_by_review' for c in self.records)
        pending = sum(c['state'] not in {'closed_by_review', 'linked_occurrence'} for c in self.records)
        self.summary.setText('K dořešení {0} | uzavřeno ručním přezkumem {1}. Jde o lokální sledování, nikoliv potvrzení správného podání.'.format(pending, closed))
        self.history.clear()

    def selected_cases(self, single=False):
        indices = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not indices or single and len(indices) != 1:
            raise ReceiptError('Vyberte jeden nález.' if single else 'Vyberte nálezy, kterých se oprava týká.')
        return [self.records[i] for i in indices]

    def selected_run(self):
        identity = self.run_choice.currentData()
        item = next((r for r in self.run_records if r['id'] == identity), None)
        if item is None:
            raise ReceiptError('Nejprve zvolte evidovanou opravu.')
        return item

    def show_case(self, row, column):
        case = self.records[row]
        self.history.setPlainText(json.dumps({'puvodni_nalez': case, 'historie': tracking.case_history(self.workspace, self.org, case['id'])}, ensure_ascii=False, indent=2))

    def form(self, title):
        dialog = QtWidgets.QDialog(self);dialog.setWindowTitle(title);dialog.resize(650, 420)
        layout = QtWidgets.QFormLayout(dialog)
        return dialog, layout

    def note_and_confirm(self, dialog, form, confirmation):
        note = QtWidgets.QPlainTextEdit();note.setMaximumHeight(100)
        explanation = QtWidgets.QLabel(confirmation);explanation.setWordWrap(True)
        confirm = QtWidgets.QCheckBox('Potvrzuji výše uvedené.')
        form.addRow('Konkrétní popis opravy / ověření', note);form.addRow(explanation);form.addRow(confirm)
        buttons = QtWidgets.QDialogButtonBox(enum(QtWidgets.QDialogButtonBox, 'StandardButton', 'Ok') | enum(QtWidgets.QDialogButtonBox, 'StandardButton', 'Cancel'))
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        return note, confirm

    def accepted(self, dialog):
        return run(dialog) == enum(QtWidgets.QDialog, 'DialogCode', 'Accepted')

    def perform(self, action):
        try:
            action()
        except ReceiptError as error:
            self.status.setText(str(error))
        except Exception:
            self.status.setText('Operace se nezdařila. Ověřte kontext a integritu; soukromé údaje se nevypisují do logu.')

    def prepare(self):
        def action():
            cases = self.selected_cases()
            dialog, form = self.form('Záznam připravené opravy – bez změny mzdových dat')
            imports, drafts = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            for combo in (imports, drafts):
                combo.setSizeAdjustPolicy(enum(QtWidgets.QComboBox, 'SizeAdjustPolicy', 'AdjustToMinimumContentsLengthWithIcon'));combo.setMinimumContentsLength(18)
            for item in self.workspace.history(self.org, self.period)['imports']:
                imports.addItem('Import {0} | {1}'.format(item['import_index'], item['created_at']), item['id'])
            def reload(*args):
                drafts.clear()
                if imports.currentData():
                    for d in self.workspace.draft_history(self.org, imports.currentData()):
                        drafts.addItem(d['created_at'] + ' | ' + d['id'], d['id'])
                    drafts.setCurrentIndex(drafts.count()-1)
            imports.currentIndexChanged.connect(reload);imports.setCurrentIndex(imports.count()-1);reload()
            form.addRow('Opravený import', imports);form.addRow('Nové pracovní XML', drafts)
            note, confirm = self.note_and_confirm(dialog, form, 'Potvrzuji návaznost opravených dat a pracovních poměrů.')
            if self.accepted(dialog):
                identity = tracking.prepare_correction(self.workspace, self.org, self.period, [c['id'] for c in cases], imports.currentData(), drafts.currentData(), note.toPlainText(), confirm.isChecked())
                self.refresh();self.run_choice.setCurrentIndex(self.run_choice.findData(identity))
                self.status.setText('Příprava opravy zapsána. XML ani oficiální GUID nebyly změněny; nic se neodeslalo.')
        self.perform(action)

    def dispatch(self):
        def action():
            current = self.selected_run()
            dialog, form = self.form('Záznam skutečného odeslání mimo aplikaci')
            kind, reference = QtWidgets.QComboBox(), QtWidgets.QLineEdit()
            kind.addItem('DIS: vlastní ID zprávy', 'dis_processing_result');kind.addItem('cJMHZ: ID konkrétního podání', 'cjmhz_completeness')
            reference.setMaxLength(500);form.addRow('Druh ID očekávané odpovědi', kind);form.addRow('Přesné ID', reference)
            note, confirm = self.note_and_confirm(dialog, form, 'Potvrzuji, že jsem opravu skutečně odeslal mimo aplikaci.')
            if self.accepted(dialog):
                tracking.register_dispatch(self.workspace, self.org, current['id'], kind.currentData(), reference.text(), confirm.isChecked(), note.toPlainText())
                self.refresh();self.status.setText('ID zapsáno pro budoucí párování. Záznam není doklad doručení.')
        self.perform(action)

    def reply_form(self, title, current):
        dialog, form = self.form(title)
        replies = QtWidgets.QComboBox()
        replies.setSizeAdjustPolicy(enum(QtWidgets.QComboBox, 'SizeAdjustPolicy', 'AdjustToMinimumContentsLengthWithIcon'));replies.setMinimumContentsLength(18)
        self.reply_records = [r for r in receipt_history(self.workspace, self.org, current['import_id']) if r['draft_id'] == current['draft_id']]
        for r in self.reply_records:
            replies.addItem(r['created_at'] + ' | ' + OUTCOMES[r['outcome']], r['id'])
        form.addRow('Odpověď ke zvolenému opravenému XML', replies)
        return dialog, form, replies

    def link(self):
        def action():
            current = self.selected_run()
            dialog, form, replies = self.reply_form('Ruční ověření návaznosti celé odpovědi', current)
            note, confirm = self.note_and_confirm(dialog, form, 'Ověřil jsem, že jde o odpověď na tuto konkrétní opravu.')
            if self.accepted(dialog):
                tracking.link_reply(self.workspace, self.org, current['id'], current['import_id'], replies.currentData(), note.toPlainText(), confirm.isChecked())
                self.refresh();self.status.setText('Návaznost odpovědi zapsána. Chybějící nález se automaticky neuzavírá.')
        self.perform(action)

    def link_occurrence(self):
        def action():
            case, current = self.selected_cases(True)[0], self.selected_run()
            dialog, form, replies = self.reply_form('Ruční spárování nejednoznačného nálezu', current)
            findings = QtWidgets.QComboBox()
            findings.setSizeAdjustPolicy(enum(QtWidgets.QComboBox, 'SizeAdjustPolicy', 'AdjustToMinimumContentsLengthWithIcon'));findings.setMinimumContentsLength(18)
            def reload(*args):
                findings.clear()
                if replies.currentData():
                    report = receipt_detail(self.workspace, self.org, current['import_id'], replies.currentData())['report']
                    for index, item in tracking.findings(report):
                        findings.addItem('{0} | {1} | {2}'.format(index+1, item.get('error_code',''), item.get('form_guid','')), index)
            replies.currentIndexChanged.connect(reload);reload();form.addRow('Konkrétní výskyt v odpovědi', findings)
            note, confirm = self.note_and_confirm(dialog, form, 'Ověřil jsem, že jde o stejný nález; nepáruji jen podle názvu osoby.')
            if self.accepted(dialog):
                tracking.link_finding(self.workspace, self.org, case['id'], current['id'], current['import_id'], replies.currentData(), findings.currentData(), note.toPlainText(), confirm.isChecked())
                self.refresh();self.status.setText('Výskyt ručně navázán; důvod a původní historie zůstávají uložené.')
        self.perform(action)

    def close_case(self):
        def action():
            case, current = self.selected_cases(True)[0], self.selected_run()
            dialog, form, replies = self.reply_form('Uzavření konkrétní opravy po přezkumu', current)
            note, confirm = self.note_and_confirm(dialog, form, 'Ověřil jsem konkrétní opravu a odpověď; samotné zmizení chyby nestačí.')
            if self.accepted(dialog):
                tracking.close_after_review(self.workspace, self.org, case['id'], current['id'], current['import_id'], replies.currentData(), note.toPlainText(), confirm.isChecked())
                self.refresh();self.status.setText('Nález uzavřen ručním přezkumem. Nejde o automatické schválení celého podání.')
        self.perform(action)

    def reopen_case(self):
        def action():
            case = self.selected_cases(True)[0]
            note, ok = QtWidgets.QInputDialog.getMultiLineText(self, 'Znovuotevření nálezu', 'Důvod přezkumu:')
            if ok:
                tracking.reopen(self.workspace, self.org, case['id'], note);self.refresh()
        self.perform(action)

    def add_note(self):
        def action():
            case = self.selected_cases(True)[0]
            note, ok = QtWidgets.QInputDialog.getMultiLineText(self, 'Poznámka k šetření', 'Zjištění / ověřované podklady (soukromá evidence):')
            if ok:
                tracking.add_note(self.workspace, self.org, case['id'], note);self.refresh()
        self.perform(action)
