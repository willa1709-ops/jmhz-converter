"""Executed by each checked-in platform .spec; never collects the whole repo."""
import os
from pathlib import Path

repo = Path(SPECPATH).resolve().parents[1]
legacy = JMHZ_VARIANT == "win7-x86"
name = "JMHZ-Converter-Win7-x86" if legacy else "JMHZ-Converter-Win11-x64"
staged = Path(os.environ["JMHZ_STAGE_DIR"]).resolve()
if not (staged / "schemas/official/manifest.json").is_file():
    raise ValueError("Build with packaging/build_windows.py and verified staged XSD.")
excluded = ["PySide6", "shiboken6"] if legacy else ["PySide2", "shiboken2"]
# Extra modern tools use models requiring Python 3.12. Shared GUI remains intact.
if legacy:
    excluded += ["app.ui.main_window", "app.ui.definitions_page", "app.models"]
    excluded += ["PySide2." + m for m in ("QtBluetooth", "QtNfc", "QtPositioning", "QtMultimedia",
                 "QtMultimediaWidgets", "QtWebEngine", "QtWebEngineCore", "QtWebEngineWidgets", "QtQuick", "QtQml")]
a = Analysis([str(repo / "app/__main__.py")], pathex=[str(repo)], binaries=[],
             datas=[(str(staged / "schemas/official"), "schemas/official"),
                    (str(staged / "config/preview"), "config/preview")],
             # Upstream hook gates this support module on the PySide6 meta
             # distribution; Essentials-only installs still need enum operators.
             hiddenimports=["app.platforms.preview"] + ([] if legacy else ["PySide6.support.deprecated"]), hookspath=[], runtime_hooks=[],
             excludes=excluded, noarchive=False)
if legacy:
    # QtGui's hook discovers all platform/image plugins from the wheel, including
    # backends this text/table application never uses. Keep the Win7 GUI subset.
    def keep_legacy_binary(entry):
        destination = entry[0].replace("\\", "/").lower()
        filename = destination.rsplit("/", 1)[-1]
        if filename in {"vccorlib140.dll", "libegl.dll", "libglesv2.dll", "opengl32sw.dll"} or filename.startswith("d3dcompiler_"):
            return False
        if filename.startswith("qt5") and filename.endswith(".dll"):
            return filename in {"qt5core.dll", "qt5gui.dll", "qt5widgets.dll"}
        if "/plugins/" in destination:
            return filename in {"qwindows.dll", "qoffscreen.dll", "qwindowsvistastyle.dll"}
        return True
    a.binaries = [entry for entry in a.binaries if keep_legacy_binary(entry)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=name,
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, getattr(a, "zipfiles", []), a.datas,
               strip=False, upx=False, name=name)
