# Externí verzované definice bez změny EXE

Balíček je pasivní ZIP s kořenovým `manifest.json`, verzovaným profilem
číslovaných položek a volitelně explicitními vazbami na stávající XML adaptér
a uzavřeným XSD runtime z dodaných podkladů. Ukládá se mimo EXE a jeho dočasný
PyInstaller adresář, pod `<store>/<package_id>/<version>/`. Internet se nepoužívá.
Není nutné vyměnit EXE, pokud nová definice vystačí s podporovanými operacemi
`logic_api=1`. Nový XML scénář nebo druh výpočtu vyžaduje změnu aplikační logiky.

## Ověření a hranice důvěry

Správce nejprve přezkoumá původ dokumentů, účinnost a význam mapování. Po kontrole
obsahu schválí **SHA-256 přesných bajtů manifestu** a předá ho příjemci odděleně
od ZIPu důvěryhodným postupem. Instalátor tento hash vyžaduje; údaj načtený jen
ze samotného ZIPu není důkazem důvěryhodnosti. Vestavěný veřejný podpisový klíč
zatím není zaveden. Hash vytvořený builderem je kandidát k přezkumu, nikoliv
automatické schválení vydavatele nebo oficiálního původu.

Loader zkontroluje pin manifestu, jeho striktní formát, SHA-256 všech souborů,
přesný seznam souborů, API, profil, vazby a kompilaci XSD. Opakované načtení
instalované verze ověřuje vše znovu; čtení JSON vstupního bodu kontroluje hash
i bezprostředně před použitím. Ověření integrity se nesmí označit jako schválení
metodiky nebo původu. Ani ověřený balíček neodblokuje finální XML export.

ZIP odmítá traversal, absolutní/UNC cesty, odkazy, speciální soubory, kolize
velikosti písmen, vyhrazené názvy Windows, nepodporované soubory, šifrování,
neplatné CRC a překročení limitů. Manifest má nejvýše 128 KiB, ZIP 25 MiB,
instalovaný obsah 100 MiB, jednotlivý soubor 25 MiB a manifest nejvýše 2000 souborů.
Povoleny jsou jen pasivní JSON/XSD/CSV/TXT/MD/PDF/XLSX/ZIP; nic se neimportuje
jako Python, nespouští ani nestahuje. Vložený ZIP/XLSX/PDF není automaticky
metodicky validován; XSD resolver nadále zakazuje síť, DTD a únik mimo root.
Instalované soubory nesmějí být odkazy ani speciální soubory.

Instalace nejprve ověří dočasnou sadu a pak ji přemístí do cílové verze.
Stejný obsah lze znovu přijmout, **stejná verze s jiným obsahem se odmítá**.
Nová verze zachová starou a nevolí se automaticky podle nejvyššího čísla nebo
roku složky. Každá zakázka explicitně určuje verzi/pin. Volitelná evidence
interních revizí uloží hash použité definice; neukládá osobní data ani GUID.

Úložiště a schválené hashe chraňte oprávněními uživatelského účtu. Hash nepomůže,
pokud útočník současně ovládá aplikaci a způsob schvalování. Instalace sama
nenahrazuje přezkum dodavatele, zálohy starších sad nebo přejímku výstupu.

## Vytvoření a načtení

Příkazy se spouštějí z kořene zdrojů na počítači správce s Pythonem; nejsou
požadavkem na instalaci Pythonu na cílovém PC. Hotové EXE s tímto jádrem bude
moci stejný ZIP načíst přes GUI. Win7 EXE dosud nebylo sestaveno/otestováno.

Vytvoření balíčku pro obecné výpočty, bez XML:

```text
python -m app.core.packages build --profile config/payroll/numbered.template.json --package-id working-payroll --version 1.0 --output working-payroll-1.0.zip
```

Pro pracovní `jinyPrijem` 2027 lze vytvořit úplný externí runtime včetně dodaných
XSD, manifestu původu a konverzních vazeb:

```text
python -m app.core.packages build --profile config/payroll/numbered.template.json --package-id working-payroll --version 1.0 --official-root schemas/official --conversion-profile config/conversion/jiny-prijem-2027.json --bindings config/payroll/jiny-prijem-2027.bindings.json --output working-payroll-2027-1.0.zip
```

Builder vypíše `manifest_sha256` a `archive_sha256`. **Teprve po přezkumu** použijte
schválený první hash místo `SCHVALENY_HASH` (zástupný text není platný hash):

```text
python -m app.core.packages install working-payroll-2027-1.0.zip --store local/definition-packages --trusted-manifest-sha256 SCHVALENY_HASH
python -m app.core.packages verify local/definition-packages/working-payroll/1.0 --trusted-manifest-sha256 SCHVALENY_HASH
python -m app.core.payroll skutecny-export.csv --package local/definition-packages/working-payroll/1.0 --trusted-manifest-sha256 SCHVALENY_HASH --period 27-09 --revision 0
```

Pro pracovní XML přidejte `--parameters local/parameters.json --draft-output
local/vysledek.draft.xml`; parametry podle
[`parameters.template.json`](../config/conversion/parameters.template.json)
vyplňte skutečnými údaji. Cílová složka musí existovat. Zápis je pouze explicitní,
bez přepsání souboru a po XSD kontrole. Osobní/mzdová data v pracovním XML chraňte;
výstup diagnostiky CLI je neobsahuje. Název `.draft.xml` není finální export.
Sada 2027 se nesmí zvolit jen kvůli příkladu: účinnost musí odpovídat metodickému
přezkumu, který zatím není dokončen. Stejně je nutné potvrdit všechny pracovní
vazby na čísla mzdových položek.

Pro další definici zvyšte verzi balíčku i verzi změněného profilu, vytvořte nový
ZIP, přezkoumejte jej a předejte nový pin. Starý ZIP i instalovanou verzi zachovejte.
Originální dokumenty v katalogu `schemas/official/` se nepřepisují. `stage_schemas`
kopíruje pouze hashově ověřený XSD runtime, nevyžaduje kancelářské prohlížeče.
Originální XLSX/PDF/ZIP a jejich záznamy zůstávají v původním katalogu podkladů.

## Rozsah aktuální dodávky

Konkrétní pracovní balíček je v [`definition-packages/`](../definition-packages/README.md).
Jeho mapování je pouze přezkoumatelná šablona a nemá vydavatelské/metodické
schválení. Testy vytvářejí také dvě po sobě jdoucí verze, ověřují zachování
starší sady, odmítnutí kolizí/tamperingu a pracovní XML proti oběma skutečným XSD.
Převod stále pokrývá jen dosavadní `jinyPrijem`; ostatní scénáře se balíčkem
samy nepřidají. [Potřebné údaje skutečného exportu](numbered-payroll.md#co-dodat-ze-skutečného-mzdového-systému)
je nutné dodat před věcným ověřením.
