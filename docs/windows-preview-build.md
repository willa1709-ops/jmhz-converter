# Dvě testovací Windows sestavy: postup a přejímka

**V Codexu nebyly sestaveny ani spuštěny Windows EXE.** Skutečné Qt5/PySide2
GUI prošlo testy na Linux Pythonu 3.8 a Qt6/PySide6 na Pythonu 3.12. To
nepotvrzuje Windows DLL, x86 kapacitu nebo přenositelnost EXE. Builder označuje
výstup `test_build_not_accepted` až do skutečné přejímky na cíli bez Pythonu.

## Přesné kandidátní verze

| Součást | Windows 7 SP1 x86 | Windows 11 x64 |
| --- | --- | --- |
| Build Python | 3.8.10 **32-bit** | 3.12.10 **64-bit** |
| GUI | PySide2/shiboken2 5.15.2.1, Qt 5.15.2 | PySide6 6.12.0, Qt 6.12 |
| lxml | 5.3.2 | 6.1.3 |
| openpyxl | 3.1.5 | 3.1.5 |
| PyInstaller | 5.13.2 | 6.22.3 |
| pytest | 7.4.4 | 9.2.0 |
| pip | 25.0.1 | 25.0.1 |
| setuptools | 69.5.1 | 84.2.1 |

Jde o kandidáty, ne potvrzení Win7 kompatibility. Hlavní win32 artefakty
dokládá [wheel-evidence.json](../packaging/windows7/wheel-evidence.json).
Aktuální dostupnost hlavních win32/amd64 wheels, jejich URL a hashe z metadat
PyPI zachycuje [windows-availability.json](../packaging/windows-availability.json).
Ani tento záznam nepotvrzuje běh knihoven na cílovém systému.
Win7 potřebuje SP1, KB2533623 a odpovídající CRT/UCRT x86; skutečné DLL a stav
aktualizací je nutné ověřit. Starý OS/runtime má zbytková rizika i bez sítě.
Tranzitivní závislosti musí být zachyceny **pro příslušnou Windows platformu**,
nikoliv převzaty z linuxového locku.

Hlavní workflow nyní sdílí `ui.qt_compat` a převodní jádro. Výběr organizace,
měsíce, import, kontrola, XML, historie/plány a zálohy fungují pod Qt5 i Qt6.
Jen starší doplňkové nástroje s moderními modely jsou v Qt5 vypnuté.
Na Linuxu byl ověřen základní rozměr 1024×720; skutečné DPI/Windows se musí otestovat.

## Úplný offline wheelhouse

Na kontrolovaném Windows počítači použijte odpovídající Python/architekturu.
Pro přípravu Win7 wheels může být použit podporovaný síťový Windows s Pythonem
3.8.10 x86; resolver tak vidí správnou architekturu i Windows podmínky.

```powershell
py -3.8-32 -m venv C:\JMHZBuild\venv7
C:\JMHZBuild\venv7\Scripts\python -m pip download --only-binary=:all: --dest C:\JMHZBuild\wheels7 -r packaging\windows7\requirements-candidate.txt
C:\JMHZBuild\venv7\Scripts\python packaging\wheel_inventory.py capture C:\JMHZBuild\wheels7 C:\JMHZBuild\wheels7-manifest.json
```

Pro W11 použít `py -3.12-64`, vlastní adresáře/venv a
`packaging\windows11\requirements-candidate.txt`. Wheelhouse musí být nový,
jen s wheels jedné platformy a jedné verze každé distribuce; manifest leží
**mimo** wheelhouse. Obsahuje přesné verze a SHA-256 všech tranzitivních wheels.
Výstup capture je kandidát: přezkoumat původ/hashe vůči důvěryhodným metadatům
dodavatele/PyPI a schválit hash manifestu odděleně. Hash vytvořený ze stejného
neznámého archivu není automatické schválení. Zachovat i ověřený instalátor Pythonu.

## Offline build na odpovídajícím Windows

Na Win7 SP1 x86 použít izolovaný Python 3.8.10 x86, na W11 Python 3.12.10 x64.
Přenést schválený wheelhouse/manifest a čistý zdrojový commit, odpojit síť:

```powershell
C:\JMHZBuild\venv7\Scripts\python packaging\build_windows.py --variant win7-x86 --wheelhouse C:\JMHZBuild\wheels7 --wheel-manifest C:\JMHZBuild\wheels7-manifest.json --approved-sha256 SCHVALENY_HASH --output C:\JMHZBuild\output7
```

Pro W11 obdobně `--variant win11-x64`, vlastní venv/sadu 11. Zástupný text
`SCHVALENY_HASH` nahradit skutečným nezávisle schváleným hashem. Výstupní
adresář musí být nový, nic se nemaže. Script kontroluje OS/Python/bitnost,
hashově připne pip, instaluje kompletní offline lock s `--require-hashes`,
spustí `pip check`, testy a kontrolu XSD, pak PyInstaller `--onedir --windowed`.
Linuxový běh builder odmítá; nepředstírá cross-build Windows EXE.

Kopíruje se celá `dist\JMHZ-Win7-x86` / `dist\JMHZ-Win11-x64`, včetně DLL,
Qt pluginů, XSD a pracovních profilů. Na cíli není potřeba instalace Pythonu,
ale mohou být nutné systémové runtime/aktualizace. Neotestovaný onefile se nevydává.
Úložiště je mimo EXE v uživatelských AppData; k přenosu historie slouží organizační záloha.
Sestava neobsahuje žádné skutečné mzdové DB/řádky.

`build-report.json` zaznamená commit, skutečný OS/Python/bitnost, pin wheels
a úplný pip freeze; `SHA256SUMS.txt` obsahuje výstupní hashe. SOURCE_DATE_EPOCH
a PYTHONHASHSEED snižují variabilitu, bitově shodné EXE mezi různými VM/cestami
zatím není prokázané. Nikdy nezaměňovat unit testy s čistou cílovou přejímkou.

## Data a povinná přejímka obou sestav

Pro vyhrazený lokální datový adresář lze ve Windows PowerShell 2/5.1 připravit
`packaging\configure-data-acl.ps1 -DataRoot C:\JMHZData`. Přestaví DACL pro
aktuální SID a SYSTEM; odmítá kořen disku, UNC a odkazy. Při selhání může být
změna částečná. Skript dosud nebyl spuštěn na Windows. Jde o ACL, nikoliv šifrování.

| Oblast | Přesný požadovaný test na Win7 x86 i W11 x64 |
| --- | --- |
| Čistý cíl | bez Pythonu, potvrzené SP/CRT/aktualizace, DLL/qwindows a bitnost, chybný/chybějící runtime |
| Přenos | celá onedir složka na druhý účet, mezery/české znaky v cestě, offline start, distribuční hashe |
| GUI | skutečný monitor, 1024×720 a DPI 100/125/150 %, klávesnice/dialogy, ukončení po XML, reset organizace/měsíce |
| DOS CSV | CP1250/CRLF/`;`, diakritika, číslované hlavičky, `000012`, čárka, citování, prázdno/nula/chybějící sloupec, nesprávné kódování |
| Zaměstnanci | HPP/DPČ/DPP, více PP osoby, cizinec bez RČ/čekající na OIČ, doložená nula a odmítnuté neznámé případy |
| Celý paket | skutečné XSD obou sad, správné pořadí souhrn/PVPOJ/PP, rovnice 4/7/9/11/12/13, nesoulad a chybějící operand bez náhrady nulou |
| Organizace | stejné číslo PP/klíče u dvou firem, cizí VS/měsíc/import odmítnuty, stará definice zachována, reimport nepoškodí historii |
| Návaznosti | interní revize není režim, původní GUID a důvod plánu, cizí GUID/plán odmítnut, žádné automatické opravné XML/odeslání |
| Definice | offline dvě verze, starší zachována, chybný pin/soubor/cesta odmítnuty, žádné stahování XSD |
| Obnova | druhý PC bez původních cest definic, stejné XML/součty/plány, nesprávný hash/existující organizace odmítnuty |
| Ochrana | druhý účet nesmí číst DB/zálohy; prověřit nové i existující soubory/journal/TEMP, chybná práva a readonly disk, plaintext omezení |
| Kapacita | RAM/čas skutečného největšího anonymizovaného exportu x86, plný disk, přerušená záloha/obnova; limity nejsou kapacitní záruka |
| Předání | finální export blokovaný, žádná telemetrie/síť nebo skutečná data v sestavě, známá metodická omezení |

Zaznamenat OS patch level, RAM/CPU/DPI, commit, wheel/DLL/EXE hashe a výsledky
včetně odchylek. Teprve tento záznam může potvrdit konkrétní testovací sestavu;
sám neodblokuje metodiku ani finální podání.
