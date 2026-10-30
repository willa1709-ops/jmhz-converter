# Windows distribuce (postup k ověření)

Tento původní postup je pouze pro moderní Windows 10/11 x64. Pro hlavní počítač
**Windows 7 SP1 x86** platí samostatný [technický návrh](windows7-design.md)
a [kandidátní postup](../packaging/windows7/README.md). Windows 7 GUI/EXE zatím není ověřené.

Sestavovat přímo na Windows x64, Python 3.12+. PyInstaller není cross-kompilátor.
V této linuxové relaci nebylo Windows EXE sestaveno ani spuštěno.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m app
.venv\Scripts\python -m app.core.stage_resources build\modern-resources
.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --onedir --name JMHZ-Converter --paths . --add-data "build/modern-resources/schemas/official;schemas/official" app\__main__.py
```

Výsledek: `dist\JMHZ-Converter\JMHZ-Converter.exe` s celou složkou závislostí.
Resources krok připraví pouze hashově ověřená XSD a manifesty, bez lokální
SQLite a dokumentačních archivů. Cílová složka přípravy musí být nová; její
obsah se nikdy bez výslovného zásahu nepřepisuje. GUI i CLI používají stejný
resource lookup pro zdrojový checkout a PyInstaller data adresář.
Zkušební CSV se vybírá ručně, nemusí být součástí balíčku. Před distribucí ověřit
na čistém Windows účtu: otevření aplikace, import CSV/XLSX, zachování nul,
profil JSON, nález → řádek, přesné součty, přístup k AppData a blokaci XML.
Pro produkční distribuci doplnit podepisování a ověřit licence závislostí.
Žádná současná sestava se nesmí označit za produkční JMHZ převodník.
