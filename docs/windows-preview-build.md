# Testovací Windows distribuce – sestavení a ověření

**Windows EXE v Codexu nevznikly a nebyly na Windows spuštěny.** K dispozici je
Linux x64, Python 3.12.14/Qt6 a Python 3.8.20/Qt5. Není dostupný Windows host,
Wine ani PowerShell. Připravený builder běh mimo odpovídající Windows odmítne.
Sestava je i po úspěšném autotestu označená `test_build_not_accepted`, dokud
neproběhne přejímka na čistém cíli bez Pythonu.

## Přesné oddělené platformy

| Součást | Win7 SP1 x86 | Win11 x64 |
| --- | --- | --- |
| Python pro build | 3.8.10 32-bit | 3.12.10 64-bit |
| Qt vazba | PySide2/shiboken2 5.15.2.1 | PySide6-Essentials/shiboken6 6.12.0 |
| Qt | 5.15.2 | 6.12.0 |
| lxml | 5.3.2 | 6.1.3 |
| openpyxl / et-xmlfile | 3.1.5 / 2.0.0 | 3.1.5 / 2.0.0 |
| PyInstaller / hooks-contrib | 5.13.2 / 2023.10 | 6.22.3 / 2026.9 |
| pip / setuptools | 25.0.1 / 69.5.1 | 25.0.1 / 84.2.1 |
| pytest | 7.4.4 | 9.2.0 |

Úplné, výhradně přesně připnuté sady včetně všech Windows/test/build závislostí:
[Win7](../packaging/windows7/requirements-candidate.txt),
[Win11](../packaging/windows11/requirements-candidate.txt). Nepoužívat moderní
`pyproject.toml`/`requirements.txt` pro Win7. Společné jádro zůstává Python 3.8;
platformní konfigurace nejsou přidané do mzdových výpočtů.

Moderní sada instaluje QtWidgets z **Essentials**, nikoliv metabalík PySide6,
který nově vyžaduje také nepotřebné Addons/WebEngine/Pdf. Spec explicitně přidává
`PySide6.support.deprecated`, protože upstream hook kontroluje verzi metabalíku.
Win7 sestava vylučuje Qt6 i staré doplňkové moderní modely; hlavní workflow je společný.

Celé Windows wheel sady byly skutečně staženy na Linuxu bez instalace Windows
binárek a jejich SHA-256 porovnány s metadaty PyPI. Záznamy:
[Win7 manifest](../packaging/windows7/wheels-candidate.json),
[Win7 URL/hash evidence](../packaging/windows7/wheels-evidence.json),
[Win11 manifest](../packaging/windows11/wheels-candidate.json),
[Win11 URL/hash evidence](../packaging/windows11/wheels-evidence.json).
Jde o kandidátní integritu/dostupnost, ne o potvrzení běhu nebo nezávislé schválení původu.

[Statická PE evidence Win7](../packaging/windows7/pe-wheel-evidence.json)
pokrývá 28 vybraných hlavních Qt/Core/Widgets/shiboken/lxml/VC binárek a GUI pluginů.
V celém wheelu se nacházejí i nepoužívané `Qt5Bluetooth.dll`, `vccorlib140.dll`
a WinRT audio/position pluginy s novějšími API. Tyto součásti se nesmějí dostat
do Win7 distribuce; spec vylučuje nepoužívané moduly a finální audit je odmítá.
Evidence nezahrnuje všechny pluginy ani výsledný EXE; konečný audit a běh na Win7
jsou nadále povinné.
Win7 spec navíc omezuje Qt DLL na Core/Gui/Widgets a pluginy na `qwindows`,
`qoffscreen` a Vista styl; nepoužívané Direct2D/WinRT/image backends se nepřibalují.
Přítomnost skutečného `qwindows.dll` se kontroluje samostatně.
Přibalený `d3dcompiler_47.dll` deklaruje OS header 10.0. Proto Win7 sestava
nepřebírá volitelné ANGLE/software-GL/shader DLL z wheelu. Samostatný Qt startup
adaptér volí raster widgets a systémový desktop OpenGL; aplikace nepoužívá
QtQuick ani OpenGL widgets. Tato politika musí být otestována na skutečném Win7;
statická kontrola nenahrazuje ověření systémových grafických knihoven/ovladačů.

## Jednorázová příprava a přenos offline

Na kontrolovaném podporovaném Windows připravit každou sadu zvlášť. Python
instalátory dodavatele: [3.8.10 x86](https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe),
[3.12.10 x64](https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe).
Ověřit jejich původ/podpis/hash, nic nestahovat z neznámých DLL webů.

```powershell
py -3.8-32 -m venv C:\JMHZBuild\venv7
C:\JMHZBuild\venv7\Scripts\python -m pip download --only-binary=:all: --no-deps --dest C:\JMHZBuild\wheels7 -r packaging\windows7\requirements-candidate.txt
C:\JMHZBuild\venv7\Scripts\python packaging\wheel_inventory.py verify C:\JMHZBuild\wheels7 packaging\windows7\wheels-candidate.json --approved-sha256 SCHVALENY_HASH
```

Pro W11 použít `py -3.12-64`, `venv11`, `wheels11` a soubory `windows11`.
Sady obsahují všechny tranzitivní závislosti, proto `--no-deps`; žádný volně
plovoucí balíček se nepřidává. Manifest leží **mimo** wheelhouse. Přezkoumat
záznamy URL/hashe a schválit pin manifestu nezávisle; nenahrazovat pin náhodným
hashem neznámého archivu. Případný nový wheel/release vyžaduje nový přezkum
celé přesné platformní sady, ne tichou změnu jednoho souboru.
`.gitattributes` chrání bajty oficiálních souborů, syntetické CP1250/CRLF sady
i připnutých wheel manifestů před Windows `core.autocrlf` konverzí.

Na sestavovacím Win7 SP1 x86 vytvořit čistý build venv Pythonu 3.8.10; na W11
venv Pythonu 3.12.10 x64. Přenést ověřený instalátor, sadu wheels/manifest a čistý
zdrojový Git commit. Build potřebuje také Git kompatibilní s hostitelským OS.
Výstup musí být **mimo checkout**. Pro samotný cílový počítač nejsou Python ani Git potřeba.
Win7 potřebuje SP1, KB2533623 a příslušné CRT/UCRT x86; jejich skutečný stav je
nutné ověřit, tento seznam není zárukou kompatibility každé DLL. Potom odpojit síť.

## Oddělené sestavovací skripty a specs

Z kořene zdrojů (cesty upravit, nikoliv čísla verzí):

```powershell
& .\packaging\windows7\build.ps1 -Python C:\JMHZBuild\venv7\Scripts\python.exe -Wheelhouse C:\JMHZBuild\wheels7 -WheelManifest C:\zdroje\jmhz-converter\packaging\windows7\wheels-candidate.json -ApprovedSha256 SCHVALENY_HASH -Output C:\JMHZBuild\output7
& .\packaging\windows11\build.ps1 -Python C:\JMHZBuild\venv11\Scripts\python.exe -Wheelhouse C:\JMHZBuild\wheels11 -WheelManifest C:\zdroje\jmhz-converter\packaging\windows11\wheels-candidate.json -ApprovedSha256 SCHVALENY_HASH -Output C:\JMHZBuild\output11
```

Win7 wrapper je napsaný pro PowerShell 2; oba lze spustit z libovolné pracovní
složky absolutní cestou. Pokud firemní execution policy skript nepovolí,
použít stejný Python přímo s `packaging\build_windows.py --variant win7-x86`
(nebo `win11-x64`) a argumenty `--wheelhouse`, `--wheel-manifest`,
`--approved-sha256`, `--output`. Execution policy se automaticky nemění.

[Win7 spec](../packaging/windows7/JMHZ-Converter-Win7-x86.spec) a
[Win11 spec](../packaging/windows11/JMHZ-Converter-Win11-x64.spec) sdílejí jen
[mechanismus balení](../packaging/freeze_common.py). Builder kontroluje OS/SP,
přesný Python/bitnost, čistý commit/venv, nezávislý hash a **přesnou úplnou sadu
wheels bez přídavných distribucí**. Připnutý pip i všechny závislosti se instalují
`--no-index --no-deps --require-hashes`; následuje kontrola celé instalace,
`pip check`, platformní testy a kompilace hashově ověřených XSD.

Balení **one-folder**, windowed, bez UPX. Ze vstupních dat se kopírují jen
runtime XSD/manifesty a explicitní syntetická sada `config/preview`.
Žádná skutečná SQLite DB, mzdy, XLSX, PDF ani ZIP archivy oficiálních podkladů.
Knihovní `base_library.zip` je součást Python runtime, nikoliv archiv mzdových dat.
XSD jsou technicky hashově ověřená, původ a účinnost zůstávají k doloženému přezkumu.

Po sestavení se kontroluje bitnost PE souborů, deklarované OS/subsystem verze,
smíchání Qt5/Qt6 a známé přímé importy novějších Windows API. Delay importy jsou
v reportu k přezkumu. Statická kontrola není důkaz, že DLL skutečně běží na Win7.
**Přesná kopie EXE/DLL** se poté spustí z dočasné cesty s mezerami/diakritikou,
mimo checkout a z jiné pracovní složky; provede `--self-test` s dočasnými daty.
Při neúspěchu se distribuce nepředává jako hotová.

## Výstupy a vydání

Výstupní ZIP obsahuje celou onedir složku s požadovaným EXE:
`JMHZ-Converter-Win7-x86.exe` nebo `JMHZ-Converter-Win11-x64.exe`, český
`CTETE-NEJDRIVE.md`, `Spustit-ukazku.cmd`, `synthetic-data`, přejímací seznam,
`build-report.json` a `SHA256SUMS.txt`. Report uvádí commit, všechny verze,
skutečný OS/bitnost, pin wheels, statickou PE kontrolu a výsledek kopie EXE.
Builder vypíše SHA-256 ZIP a inventory pro oddělené bezpečné předání.
`verify_distribution.py` ověří celou složku vůči nezávislému pinu inventory.

Žádný binární soubor necommitovat. Po skutečném sestavení a kontrole lze ZIP
připojit k testovacímu GitHub Release či artefaktu schváleného Windows runneru.
V tomto prostředí není Windows runner ani vytvořený artefakt. GitHub-hosted
Windows Server není přejímka Win7/W11; Win7 navíc nepodporuje moderní Node
runtime běžných GitHub Actions. Nepřidáváme zdánlivě funkční Win7 workflow.

SOURCE_DATE_EPOCH/PYTHONHASHSEED omezují variabilitu, ale bitově identická EXE
mezi VM/cestami nejsou prokázaná. Ručně otestovat čistý cíl bez Pythonu,
[krátký přejímací seznam](windows-acceptance.md) a
[český první start](first-run-windows.md). Velikost/RAM/čas x86 se musí změřit.
ACL skript ani šifrování nejsou tímto ověřené; používají se pouze syntetická data.

## Skutečně provedené ověření 31. 10. 2026

- Linux Python 3.12.14 / PySide6 6.12.0 / lxml 6.1.3 / openpyxl 3.1.5 /
  pytest 9.2.0: **236 testů prošlo**.
- Linux Python 3.8.20 / PySide2 5.15.2.1 / Qt 5.15.2 / lxml 5.3.2 /
  openpyxl 3.1.5 / pytest 7.4.4: **160 testů společného jádra a GUI prošlo**.
- Úplné Windows wheels: 19 win32/univerzálních, 18 amd64/univerzálních;
  staženo, porovnáno s PyPI hashy, offline resolver dry-run obou sad prošel.
- Samostatné čisté Linuxové prostředí jen s Qt Essentials bez metabalíku
  PySide6/WebEngine: PyInstaller 6.22.3 vytvořil **Linux ELF**, jehož zabalený
  `--self-test` prošel z `/tmp` mimo checkout. Výsledek `frozen: true` se vztahuje
  pouze k tomuto Linuxovému experimentu, viz
  [evidence](../packaging/linux-smoke-evidence.json). Linuxový artefakt se nevydává
  jako Windows sestava a není commitovaný.
- Kontrola hashů oficiálních souborů, relativních dokumentačních odkazů
  a `git diff --check` prošly; žádné původní oficiální podklady se neměnily.
- Checkout s `core.autocrlf=true` zachoval přesné bajty všech 26 chráněných
  souborů syntetické sady a wheel manifestů.

**Neprovedeno:** Windows build, Windows spuštění/čistá přejímka bez Pythonu,
PowerShell wrapper/ACL na Windows, provozní kapacitní test x86 a potvrzení
skutečných DLL/patchů/ovladačů. Žádný Windows EXE/ZIP artefakt není k dispozici.
