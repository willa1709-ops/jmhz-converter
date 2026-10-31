"""Build-only strict dependency inventory and PE checks; not a Win7 guarantee."""
import importlib.metadata
from pathlib import Path
import re


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.+!-]+)", line)
        if not match or normalized(match[1]) in result:
            raise ValueError("Only unique exact versions are allowed in the platform dependency set.")
        result[normalized(match[1])] = match[2]
    return result


def check_wheels(manifest, required, legacy):
    actual = {normalized(w["name"]): w["version"] for w in manifest["wheels"]}
    if actual != required or len(actual) != len(manifest["wheels"]):
        raise ValueError("Wheelhouse must exactly equal the complete platform dependency set; no extra packages.")
    suffix = "win32.whl" if legacy else "win_amd64.whl"
    for wheel in manifest["wheels"]:
        name = wheel["filename"]
        if not (name.endswith(suffix) or name.endswith("-any.whl")):
            raise ValueError("Wheel belongs to a different target platform.")


def check_installed(required, before=False):
    actual = {normalized(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
    if set(actual) - set(required):
        raise ValueError("Use a fresh isolated build venv; unexpected distributions are installed.")
    if not before and actual != required:
        raise ValueError("Installed distributions differ from the exact platform set.")


def audit_binaries(directory, legacy):
    import pefile
    records = []
    newer_dlls = {"api-ms-win-core-path-l1-1-0.dll", "api-ms-win-core-winrt-l1-1-0.dll"}
    newer_symbols = {b"CreateFile2", b"GetSystemTimePreciseAsFileTime", b"SetThreadDescription", b"GetDpiForWindow"}
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".pdf", ".xlsx"}:
            raise ValueError("A user database/document was collected into the distribution.")
        if legacy and any(token in relative.casefold() for token in ("pyside6", "shiboken6", "qt6")):
            raise ValueError("A modern Qt library was collected into the legacy distribution.")
        if legacy and path.name.lower() in {"qt5bluetooth.dll", "vccorlib140.dll", "qtaudio_wasapi.dll", "qtposition_winrt.dll"}:
            raise ValueError("Unneeded WinRT component in Win7 distribution: " + relative)
        if legacy and (path.name.lower() in {"libegl.dll", "libglesv2.dll", "opengl32sw.dll"} or path.name.lower().startswith("d3dcompiler_")):
            raise ValueError("Optional GL/shader runtime outside the Win7 raster GUI: " + relative)
        if legacy and path.name.lower().startswith("qt5") and path.suffix.lower() == ".dll" and path.name.lower() not in {"qt5core.dll", "qt5gui.dll", "qt5widgets.dll"}:
            raise ValueError("Unexpected Qt module outside the Win7 GUI subset: " + relative)
        if legacy and "/plugins/" in ("/" + relative.lower()) and path.suffix.lower() == ".dll" and path.name.lower() not in {"qwindows.dll", "qoffscreen.dll", "qwindowsvistastyle.dll"}:
            raise ValueError("Unexpected Qt plugin outside the Win7 GUI subset: " + relative)
        if not legacy and any(token in relative.casefold() for token in ("pyside2", "shiboken2", "qt5")):
            raise ValueError("A legacy Qt library was collected into the modern distribution.")
        if path.suffix.lower() not in {".exe", ".dll", ".pyd"}:
            continue
        with pefile.PE(str(path), fast_load=True) as pe:
            if pe.FILE_HEADER.Machine != (0x14c if legacy else 0x8664):
                raise ValueError("Wrong PE architecture in distribution: " + relative)
            os_version = (pe.OPTIONAL_HEADER.MajorOperatingSystemVersion, pe.OPTIONAL_HEADER.MinorOperatingSystemVersion)
            subsystem_version = (pe.OPTIONAL_HEADER.MajorSubsystemVersion, pe.OPTIONAL_HEADER.MinorSubsystemVersion)
            if legacy and (os_version > (6, 1) or subsystem_version > (6, 1)):
                raise ValueError("A collected PE declares a newer minimum Windows version: " + relative)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"], pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
            imports = list(getattr(pe, "DIRECTORY_ENTRY_IMPORT", []))
            delayed = list(getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []))
            if legacy and any(entry.dll.decode("ascii").lower() in newer_dlls or any(i.name in newer_symbols for i in entry.imports) for entry in imports):
                raise ValueError("Direct import of a known post-Win7 API; target acceptance cannot proceed: " + relative)
            # Delay imports may have an explicit fallback. Record them for review.
            records.append({"file": relative, "machine": pe.FILE_HEADER.Machine,
                            "minimum_os_header": os_version, "minimum_subsystem_header": subsystem_version,
                            "imports": [i.dll.decode("ascii") for i in imports],
                            "delay_imports_review_required": [i.dll.decode("ascii") for i in delayed]})
    if not records:
        raise ValueError("No Windows PE binaries found; no EXE build is claimed.")
    return {"status": "static_checks_passed_not_a_runtime_guarantee", "binaries": records}
