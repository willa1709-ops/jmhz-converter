# Opravy po prvním skutečném testu Windows 11

Vstup: dodaný `jmhz-chyby.txt`, Python 3.12.10 x64, PySide6 6.12.0,
225 passed / 10 failed / 1 skipped na zdrojích po PR #8 (`54723da`).
Opravy nemění připnuté závislosti, oficiální dokumenty, XSD, jejich manifesty ani hashe.
Finální JMHZ export zůstává blokovaný v GUI i jádře.

## Příčiny a opravy

| Oblast | Prokázaná příčina | Oprava a regrese |
| --- | --- | --- |
| ZIP `a\\evil` | `ZipFile.writestr(str, ...)` vytvoří `ZipInfo`, který na Windows převede zpětné lomítko na `/`. Stejná úprava probíhá i při čtení; `filename` navíc zkracuje název u NUL. | Test zapíše přesný název přiřazením `ZipInfo.filename` až po konstrukci a ověří uložené `orig_filename`. Produkční validace kontroluje `orig_filename`. Regrese simulují Windows separátor i na Linuxu a odmítají zpětné lomítko i NUL před zápisem souborů. |
| České názvy a opakovaná normalizace | UTF-8 `intake.json` se znovu četl výchozí CP1250. Výsledkem byl změněný původní název a další přepis poškozeného textu. | Explicitní UTF-8 při čtení JSON v příjmu, analýze, knihovně, GUI, XML CLI i testech. Opakovaný příjem a rozbalení českých názvů jsou ověřeny se simulovanou CP1250. |
| XSD 2026 | Pomocná funkce testu četla `bundles.json` bez UTF-8. Česká část cesty `JMHZ_podání_1.4.3.6` se poškodila a `LocalSchemaResolver.read` správně odmítl neexistující soubor. | Opravené načítání indexu. Přímý pokus s původními bajty potvrzuje: UTF-8 cesta existuje, CP1250 cesta 2026 neexistuje. Resolver ani jeho hranice se neuvolňují. |
| XSD 2027 a CLI obou sad | ASCII cesta 2027 fungovala při přímé validaci. CLI četlo `manifest.json` jako CP1250 a skončilo na nedefinovaném bajtu `0x88` na pozici 2990. | XML CLI čte UTF-8. Obě skutečné sady se kopírují do cesty s diakritikou, mezerami, `#` a `%`; testují se API, CLI, přesná množina načtených závislostí, chybějící hash i pozměněná závislost. |
| Symlink | Windows účet bez potřebného oprávnění odmítl už vytvoření odkazu: WinError 1314. | Samostatný symlink test se přeskočí pouze pro WinError 1314 s výslovným důvodem. Přímý únik cesty a zachování neznámého manifestu se stále testují samostatně. Ostatní chyby vytváření odkazu test nepřeskočí. |
| SQLite | `with sqlite3.connect(...)` provede commit/rollback, ale nezavře spojení. Migrační test držel otevřenou DB při `unlink`; stejný vzor byl v konfiguraci, knihovně a registru revizí. | Společný transakční helper vždy volá `close()` ve `finally`, včetně chyb přípravy spojení. Přímá testovací spojení používají `closing` i transakční kontext. Regrese úmyslně drží reference na spojení, aby GC neskryl únik; prověřují i migraci, přejmenování/odstranění a rollback. |
| Qt GUI | Vodorovné řady dlouhých českých tlačítek vyžadovaly na Windows nejméně 1350 px. | Dvousloupcové ovládání, zalamování textu, posuvný obsah, posuvné záložky a počáteční velikost podle pracovní plochy. Test při 1024 × 600 a fontech 9/12/16 bodů kontroluje skutečnou šířku, nulový vodorovný posuv a dosažitelnost celého blokovaného exportního tlačítka. Qt5 zapíná podporu vysokého DPI před vytvořením QApplication. |
| Syntetická ukázka / `--self-test` | Navazující GUI kontrola minimální šířky zastavila celou přejímku. | Oba průchody fungují s opraveným GUI. Test z cizí pracovní složky nadále ověřuje izolaci dat a zákaz přepsání existujícího reportu. |
| Qt fonty | Generický plugin `offscreen` hledá adresář `PySide6/lib/fonts`; Windows wheels vlastní fonty nedodávají. | Windows testy a builder používají nativní plugin `windows` se systémovými fonty. Linux bez displeje nadále používá `offscreen`. CLI regrese odmítne výskyt `Cannot find font directory` ve stderr. Nativní Windows běh ještě vyžaduje potvrzení. |

## Ověření na Linuxu

- Původní úplná sada: **236 passed**.
- Opravená úplná sada: **250 passed**, Python **3.12.14**, PySide6/Qt **6.12.0**,
  lxml **6.1.3**, openpyxl **3.1.5**, Linux x64, `QT_QPA_PLATFORM=offscreen`.
- Společná sada vybraná Windows 7 builderem, včetně nových regresí:
  **172 passed**, Python **3.8.20**, PySide2 **5.15.2.1** / Qt **5.15.2**,
  lxml **5.3.2**, openpyxl **3.1.5**, Linux x64.
- GUI test při `QT_SCALE_FACTOR=1.5` prošel pod Qt6 i Qt5.
- Samostatný `--self-test` z `/tmp` prošel pod oběma Python/Qt variantami;
  reporty obsahují `status: passed` a `final_export: blocked`.
  Linuxový `offscreen` hlásí pouze nepodporované `propagateSizeHints()`;
  upozornění na chybějící fontový adresář se neobjevilo.
- `pip check` moderního prostředí a `git diff --check` prošly.
- Nové regrese byly spuštěny také na původním zdroji: **6 selhání a 1 chyba**
  reprodukují poškození Unicode, načítání manifestu, únik SQLite spojení,
  příliš široké GUI a kontrolu sanitizovaných ZIP názvů. Opravený zdroj je odstraní.

V úplné sadě žádný test neubyl: počet vzrostl z 236 na 250. Na Windows je
očekávané jedno původní přeskočení testu odmítnutí linuxového cross-buildu.
Bez oprávnění k symlinkům přibude jedno výslovně zdůvodněné přeskočení:
očekávaný výsledek je **248 passed / 2 skipped**, případně **249 passed / 1 skipped**
s dostupnými symlinky. Jde o očekávání, nikoliv výsledek naměřený na Windows.

## Co stále vyžaduje skutečný Windows 11

Zopakovat úplnou sadu na Pythonu 3.12.10 x64 s českou systémovou lokalizací,
bez vynuceného UTF-8 režimu. Potvrdit skutečné Windows zámky SQLite a chování
symlink testu bez administrátora/Developer Mode. Prověřit nativní `qwindows`,
české systémové fonty a nepřítomnost uvedeného fontového upozornění.
Ručně projít GUI při 1024 × 768 a škálování 100/125/150 %, posuvy, klávesovou
navigaci a všechny české popisky. Qt pracuje v logických pixelech; při vyšším
DPI je dostupná logická plocha menší a obsah se posouvá.

Poté vytvořit první testovací EXE existujícím Windows builderem a ověřit jeho
zkopírovaný `--self-test`, syntetickou ukázku, cesty s diakritikou i spuštění
na čistém Windows bez Pythonu. Linux testy nepotvrzují běh Windows EXE.
Python 3.8/Qt5 byl ověřen na Linuxu x64; skutečný Windows 7 SP1 x86 s Pythonem
3.8.10 a PE/CRT audit zůstávají samostatnou budoucí přejímkou.

## Opakování testů a sestavení

Pro opakování testů **není nutný nový venv ani nová sada závislostí**.
Stačí opravený čistý checkout a původní funkční prostředí Pythonu 3.12.10.
Není potřeba aktualizovat či znovu generovat XSD/manifesty nebo měnit hashe.
Pokud se dříve na Windows ručně spouštěla normalizace a přepsala `intake.json`,
použít čerstvý checkout originálních podkladů; poškozené texty nepřebírat.

Z kořene opravených zdrojů v PowerShellu (cestu k Pythonu upravit):

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
& C:\JMHZBuild\venv11\Scripts\python.exe -m pytest -q -rs
& C:\JMHZBuild\venv11\Scripts\python.exe -m app --self-test --report C:\JMHZBuild\self-test-opravy-01.json
```

Report musí mít nový název. Pro GUI se na Windows použije nativní plugin;
nenastavovat `QT_QPA_PLATFORM=offscreen`. Proměnné není nutné trvale měnit.

Pro **EXE build** nadále platí [přesný postup PR #8](windows-preview-build.md):
čistý checkout, výstup mimo něj, nový výstupní adresář a ověřený wheelhouse.
Původní čistý venv se schválenou sadou
`packaging/windows11/requirements-candidate.txt` lze použít znovu;
verze ani wheel manifest se nezměnily.
Pokud byl testovací venv instalován z obecného `requirements.txt` a obsahuje
metabalík PySide6/Addons/WebEngine/Pdf, pro distribuční build připravit
**nový oddělený venv** s kandidátní Essentials sadou. Builder nadbytečné balíčky
správně odmítá; tuto kontrolu neměnit. Nový OS ani jiné verze Pythonu nejsou
kvůli těmto opravám vyžadovány.

Finální export zůstává blokovaný i po úspěšném testovacím sestavení.
