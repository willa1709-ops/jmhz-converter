# Windows distribuce (postup k ověření)

Sestavovat přímo na Windows x64, Python 3.12+. PyInstaller není cross-kompilátor.
V této linuxové relaci nebylo Windows EXE sestaveno ani spuštěno.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m app
.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --onedir --name JMHZ-Converter --paths . app\__main__.py
```

Výsledek: `dist\JMHZ-Converter\JMHZ-Converter.exe` s celou složkou závislostí.
Zkušební CSV se vybírá ručně, nemusí být součástí balíčku. Před distribucí ověřit
na čistém Windows účtu: otevření aplikace, import CSV/XLSX, zachování nul,
profil JSON, nález → řádek, přesné součty, přístup k AppData a blokaci XML.
Pro produkční distribuci doplnit podepisování a ověřit licence závislostí.
Žádná současná sestava se nesmí označit za produkční JMHZ převodník.
