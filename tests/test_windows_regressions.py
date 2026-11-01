"""Windows failures reproduced on Linux too; also run in the Python 3.8 set."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile, ZipInfo

import pytest
from lxml import etree

from app.core.periods import Period, RevisionRegistry, SubmissionContext
from app.core.schemas import BundleValidator, decode_local_schema_url, registered_validator
from app.definitions.archives import zip_inventory
from app.definitions.intake import normalize_uploads, unpack_archives

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "schemas/official"


@pytest.fixture
def cp1250_default(monkeypatch):
    # Path.read_text uses encoding='locale' on newer Python and None on 3.8.
    original = Path.open

    def open_with_windows_default(path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding in {None, "locale"}:
            encoding = "cp1250"
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", open_with_windows_default)


def test_repeated_unicode_intake_with_cp1250_default(tmp_path, cp1250_default):
    root = tmp_path / "Podklady Žluťoučký"
    (root / "2027").mkdir(parents=True)
    source = root / "2027/https___developers.mpsv.cz_assets_documents_00000000-0000-4000-8000-000000000001_Žluťoučký balíček.zip"
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("Žluťoučký/typy.xsd", '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')
    source.write_bytes(stream.getvalue())
    before = normalize_uploads(root)
    assert before["documents"][0]["original_document_name"] == "Žluťoučký balíček.zip"
    assert normalize_uploads(root) == before
    first = unpack_archives(root, tmp_path / "stage")
    assert first[0]["container_chain"] == ["Žluťoučký/typy.xsd"]
    assert unpack_archives(root, tmp_path / "stage") == first
    assert hashlib.sha256((root / before["documents"][0]["file"]).read_bytes()).hexdigest() == before["documents"][0]["sha256"]


@pytest.mark.parametrize("cohort", ["2026", "2027"])
def test_official_xsd_unicode_paths_hashes_and_cli_with_cp1250_default(tmp_path, monkeypatch, cp1250_default, capsys, cohort):
    from app.xml.__main__ import main
    bundle = next(b for b in json.loads((OFFICIAL / "bundles.json").read_text(encoding="utf-8"))["bundles"]
                  if b["cohort_label"] == cohort)
    target = tmp_path / "Žluťoučký balíček #1 %25" / "official"
    # Copy only the real XSD tree and unchanged manifests, preserving all names.
    shutil.copytree(OFFICIAL / bundle["root"], target / bundle["root"])
    for name in ("manifest.json", "bundles.json"):
        shutil.copyfile(OFFICIAL / name, target / name)
    validator = registered_validator(target, bundle["id"])
    assert validator.resolver.loaded == bundle["compiled_dependencies"]
    xml = ('<jmhz xmlns="' + bundle["namespace"] + '"><hlavicka>'
           '<idPodani>00000000-0000-4000-8000-000000000001</idPodani><typPodani>R</typPodani>'
           '<variabilniSymbol>0000000000</variabilniSymbol><mesic>1</mesic><rok>' + cohort + '</rok>'
           '<datumVyplneni>2026-10-30T12:00:00</datumVyplneni></hlavicka></jmhz>').encode("utf-8")
    assert validator.validate(xml).xsd_valid
    document = tmp_path / "synthetic.xml"
    document.write_bytes(xml)
    monkeypatch.setattr(sys, "argv", ["app.xml", str(document), "--schema", str(target / bundle["entry"]),
                        "--bundle-root", str(target / bundle["root"]), "--manifest", str(target / "manifest.json")])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["submission_ready"] is False
    hashes = dict(bundle["compiled_dependencies"])
    hashes.pop("formCommonTypes.xsd")
    with pytest.raises((ValueError, etree.XMLSchemaParseError)):
        BundleValidator(target / bundle["entry"], target / bundle["root"], hashes)
    with (target / bundle["root"] / "formCommonTypes.xsd").open("ab") as handle:
        handle.write(b"\n<!-- modified -->")
    with pytest.raises((ValueError, etree.XMLSchemaParseError)):
        registered_validator(target, bundle["id"])


@pytest.mark.parametrize("url", ["file://server/share/types.xsd", "file:////server/share/types.xsd",
                                "%5C%5Cserver%5Cshare%5Ctypes.xsd", "file:///C:/bundle/types.xsd?other=1",
                                "https://example.invalid/types.xsd"])
def test_windows_schema_urls_keep_network_and_query_restrictions(url):
    with pytest.raises(ValueError):
        decode_local_schema_url(url, windows=True)


def test_revision_database_closes_on_read_write_and_rollback(tmp_path, tracked_sqlite_connections):
    path = tmp_path / "revize.sqlite3"
    registry = RevisionRegistry(path)
    registry.record("synthetic", SubmissionContext(Period(2027, 1), 0), "0" * 64)
    with pytest.raises(ValueError):
        registry.record("synthetic", SubmissionContext(Period(2027, 1), 0), "0" * 64)
    registry.record("synthetic", SubmissionContext(Period(2027, 1), 1), "0" * 64)
    # Retained Python connection objects must not hold a Windows file handle.
    renamed = path.with_name("moved.sqlite3")
    path.rename(renamed)
    renamed.unlink()


def test_small_screen_czech_controls_and_large_fonts_remain_reachable(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
    from app.ui.qt_compat import QtCore, QtWidgets, dispose_window
    from app.ui.organizations_window import OrganizationsWindow
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = OrganizationsWindow(tmp_path / "workspace")
    try:
        window.show()
        for points in (9, 12, 16):
            font = window.font()
            font.setPointSize(points)
            window.setFont(font)
            window.resize(1024, 600)
            application.processEvents()
            assert window.minimumSizeHint().width() <= 1024
            assert window.width() <= 1024
            assert window.scroll.horizontalScrollBar().maximum() == 0
            assert window.pages.usesScrollButtons()
            # Scrolling reaches the final action even at large fonts/short height.
            final = next(b for b in window.findChildren(QtWidgets.QPushButton) if b.text() == "Finální export – blokováno")
            assert not final.isEnabled()
            window.scroll.ensureWidgetVisible(final)
            application.processEvents()
            bounds = QtCore.QRect(final.mapTo(window.scroll.viewport(), QtCore.QPoint()), final.size())
            assert window.scroll.viewport().rect().contains(bounds)
    finally:
        dispose_window(window)


@pytest.mark.parametrize("name", ["a\\evil", "good\x00evil"])
def test_zip_rejects_raw_header_even_when_windows_zipinfo_sanitizes_it(monkeypatch, name):
    import zipfile
    stream = BytesIO()
    item = ZipInfo(name)
    item.filename = name  # Preserve the exact adversarial name in the ZIP header.
    with ZipFile(stream, "w") as zipped:
        zipped.writestr(item, "bad")
    content = stream.getvalue()
    # Reproduce the Windows constructor on Linux, including when reading a ZIP.
    monkeypatch.setattr(zipfile.os, "sep", "\\")
    assert ZipInfo("a\\evil").filename == "a/evil"
    with ZipFile(BytesIO(content)) as zipped:
        item = zipped.infolist()[0]
        assert item.orig_filename == name
        assert item.filename != name
    with pytest.raises(ValueError, match="cestu"):
        zip_inventory(content)
