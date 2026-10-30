# Kandidátní sestavení pro Windows 7 SP1 x86

Toto je ověřovací postup, **ne hotová Windows 7 sestava**.
[Technický návrh a zdroje](../../docs/windows7-design.md) popisují verze,
KB2533623, UCRT, DLL a přejímku. Moderní `requirements.txt` ani pyproject se nemění.

Na odděleném Windows sestavovacím stroji připravte Python 3.8.10 **x86** a
wheelhouse všech závislostí. Přesný výstup resolveru včetně tranzitivních balíčků
je před distribucí nutné uzamknout a ověřit jejich hashe; kandidátní requirements
nejsou úplný platformní lock. Pip pro Python 3.8 musí být kompatibilní (např. 25.0.1).

```powershell
py -3.8-32 -m venv .venv-win7
.venv-win7\Scripts\python -m pip install --no-index --find-links wheelhouse -r packaging\windows7\requirements-candidate.txt
.venv-win7\Scripts\python -m pytest -q tests\test_conversion_core.py tests\test_numbered_payroll.py
```

Neinstalovat tento projekt pomocí `pip install .` do 3.8: balíček moderního UI
má záměrně `requires-python >=3.12`. Testy a sdílený CLI modul se pouštějí přímo
ze zdrojového checkoutu. PySide2 je kandidát pro pozdější Qt5 adaptér; aktuální
PySide6 GUI na této konfiguraci neběží.

Po úspěšné přejímce jádra lze jako první pokus sestavit **konzolové jádro**:

```powershell
.venv-win7\Scripts\python -m app.core.stage_resources build\win7-resources
.venv-win7\Scripts\python -m PyInstaller --noconfirm --clean --onedir --console --name JMHZ-Core-Win7 --paths . --add-data "build/win7-resources/schemas/official;schemas/official" app\core\__main__.py
```

Příkaz PyInstaller zatím nebyl proveden na Windows. Příprava resources se ověřuje
na obou verzích Pythonu: kopíruje pouze XSD a manifesty, kontroluje hashe a znovu
kompiluje oba balíčky. Nekopíruje SQLite, PDF, XLSX ani ZIP. Cíl musí být nový.
Sestava pak obsahuje oba XSD balíčky a manifest,
které jádro hledá v PyInstaller data adresáři, nikoliv podle aktuálního pracovního
adresáře. Ověřte přiložené hashe a DLL; resources se za běhu nepřepisují.
Nesmí přitom chybět žádná použitá XSD závislost nebo manifest.

Výsledek `dist\JMHZ-Core-Win7\` se kopíruje celý na cílový stroj bez Pythonu.
Nejde zatím o Qt5 desktopovou aplikaci. CLI potřebuje explicitní CSV, konverzní
profil a vyplněné parametry; připravuje pouze `.draft.xml`, finální export neumí.
Připojení k internetu za běhu není potřebné. `--onefile` a Qt5 GUI jsou další
ověřovací kroky, nikoliv alternativní neověřený produkční příkaz.

[wheel-evidence.json](wheel-evidence.json) zaznamenává pouze ověřenou dostupnost
vybraných win32/univerzálních artefaktů a hashe z PyPI metadata. Neprokazuje stažení
nebo úspěšné načtení těchto Windows DLL v této linuxové relaci.

## Kandidát konzole číslovaných položek s externími definicemi

Po stejných přejímacích kontrolách lze samostatně vyzkoušet nový vstupní bod:

```powershell
.venv-win7\Scripts\python -m PyInstaller --noconfirm --clean --onedir --console --name JMHZ-Payroll-Win7 --paths . app\core\payroll.py
```

Tato varianta dostává profil, vazby i skutečná XSD z
[externího ZIPu](../../docs/offline-definition-packages.md) instalovaného mimo EXE.
Ověřenou sadu nejprve připraví správce nástrojem `app.core.packages`; konzole
na cílovém PC ji při použití `--package` a `--trusted-manifest-sha256` znovu ověří.
Příkazy `python -m app.core.payroll ...` z návodu pak nahradí
`JMHZ-Payroll-Win7.exe ...`. Externí sady ani databázi neukládat do interního
PyInstaller/TEMP adresáře; změna definice musí zachovat předchozí verzi.
Ani tento sestavovací příkaz nebyl otestován na Windows a nepředstavuje hotové
GUI nebo potvrzení kompatibility Win7 x86. Závislosti se zde nemění.
