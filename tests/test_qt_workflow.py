"""Run this file unchanged under Python 3.8/Qt5 and modern Python/Qt6."""
import os
import csv
import json
from lxml import etree
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.qt_compat import QtWidgets, QT_API, dispose_window
from app.ui.organizations_window import OrganizationsWindow
from app.core.models import SourceRow, SourceTable
from test_employee_xml import case
from test_monthly_packet import employer_case


_APPLICATION = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_shared_gui_import_checks_monthly_xml_history_and_shutdown(tmp_path):
    data = case(2027)
    window = OrganizationsWindow(tmp_path / "workspace")
    org = window.workspace.register("Synthetic", "00000001", "0000000001")
    window.workspace.set_profile(data[0])
    imported = window.workspace.import_table(org.id, data[3].period, SourceTable(tuple(data[2]), (SourceRow(2, data[2]),)))
    window.period.setText(imported.period.iso)
    window.refresh()
    window.select_organization(org.id)
    window.check()
    assert window.rows.rowCount() == 1
    window.prepare_employee_xml(data[1], data[4])
    assert "bezPriznaku" in window.draft.toPlainText()
    monthly, employer = employer_case(2027)
    paths = [tmp_path / name for name in ("employee.json", "monthly.json", "employer.csv", "parameters.json")]
    for path, value in ((paths[0], data[1]), (paths[1], monthly), (paths[3], data[4])):
        path.write_text(json.dumps(value), encoding="utf-8")
    with paths[2].open("w", encoding="cp1250", newline="") as stream:
        writer = csv.DictWriter(stream, employer.columns, delimiter=";")
        writer.writeheader()
        writer.writerow(employer.rows[0].values)
    window.prepare_monthly_paths(*paths)
    assert window.draft_id
    packet = etree.fromstring(window.draft.toPlainText().encode("utf-8"))
    assert [etree.QName(node).localname for node in packet][1:3] == ["souhrn", "PVPOJ"]
    assert len(window.workspace.draft_history(org.id, imported.id)) == 2
    assert window.csv_encoding.currentText() == "cp1250"
    window.show()
    _APPLICATION.processEvents()
    window.resize(1024, 720)
    _APPLICATION.processEvents()
    assert window.minimumSizeHint().width() <= 1024
    assert QT_API in {"PySide2", "PySide6"}
    dispose_window(window)
