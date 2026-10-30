# Opakování příjmu podkladů a XSD validace

Příkazy spouštějte z kořene projektu v připraveném Python prostředí. Na Windows
použijte `.venv\Scripts\python`, v cloudu `.venv/bin/python`. Analýza PDF navíc
využívá systémový `pdftotext` (Poppler); příkaz musí být dostupný v PATH.

## Inventura a zpracování

```bash
.venv/bin/python -m app.definitions.intake normalize
.venv/bin/python -m app.definitions.intake unpack
.venv/bin/python -m app.definitions.analyze
.venv/bin/python -m app.definitions.catalog verify
```

Normalizace rozpoznává pouze konkrétní nahraný vzor názvu
`https___developers.mpsv.cz_assets_documents_UUID_NAZEV`. Před přejmenováním
uloží původní jméno, rekonstruovanou URL a hash do `intake.json`; odmítne kolize.
Opakování už normalizované soubory nepřejmenuje znovu. Jiné vzory URL je nutné
evidovat výslovně, ne odhadovat. `original_downloaded_at` zůstává neznámé;
`acquired_at` katalogu je čas místní registrace, nikoli původního stažení.

Rozbalení ověří cesty, kolize názvů, typy souborů, CRC, počty a velikosti před
zápisem; odmítá symlinky, absolutní cesty a průchod `..`. Umí nejvýše tři úrovně
vnoření a omezuje rozbalené bajty. Existující odlišný obsah nepřepisuje. Plné
rozbalení zůstává v ignorované `local/official-extracted/`; publikované XSD cesty
a vnořené ZIPy jsou v `schemas/official/ROK/extracted/`. HTML/obrázky/protokoly
zůstávají zachované v originálech; AppleDouble metadata nejsou zdrojové XSD.

Analýza čte dodanou dvojici sad 2026/2027, konkrétní listy a nadpisy, ověřuje
hash originálů a vytváří `analysis/` a `bundles.json`. Není univerzálním
automatickým schvalovačem libovolné budoucí dokumentace. U změněného layoutu
se musí přezkoumat parser. Vzorce a makra se nespouštějí, originály se neukládají
zpět přes openpyxl. Varování o nepodporovaných Excel extensions se týkají čtené
reprezentace; testy kontrolují nezměněné hashe originálů.

Katalog přijímá XLSX i ZIP do 25 MiB; rozbalený archiv do 100 MiB, omezený počet
položek. Technické stavy `xlsx_read_not_validated` a `zip_crc_checked` znamenají
čtení/CRC, nikoliv věcnou validaci dokumentu. Samostatná XSD do 5 MiB mají vlastní
stav kompilace; XSD se závislostmi katalog eviduje jako `dependencies_unchecked`.
Kompilace konkrétního celého balíčku je samostatný krok validátoru.

## Načtení do aplikace

Na kartě **Definice JMHZ** zvolte **Načíst dokumenty z katalogu manifest.json…**
a vyberte `schemas/official/manifest.json`. Import nejprve ověří hashe všech
položek a poté je přenese do uživatelské SQLite knihovny. Opakování neduplikuje
stejný obsah/verzi/URL. Změna typu nebo souboru se neprovádí potichu. Pokud
zpracování některého formátu selže, již importované položky zůstávají viditelné.

Lze také importovat jeden dokument: typy **Datový slovník XLSX**, **Katalog
kontrol XLSX**, **Datové scénáře XLSX** nebo **Archiv ZIP**, dále stávající XSD,
číselníky a metodiku. Tabulka vždy odděluje **Původ** od **Technické kontroly**.
Všechny dodané dokumenty jsou nyní evidovány jako původ **NEOVĚŘENO**. Ruční
potvrzení názvu nebo SHA nemění tento fakt. URL z původního názvu je dohledatelný
kandidát zdroje; přezkum musí doložit skutečného vydavatele a souhlas obsahu.

## Funkční technická kontrola XML

Na kartě **Generování XML** vyberte konkrétní `jmhz-1.4.3.6` nebo `jmhz-1.5.0.3`
a zvolte **Vybrat XML a ověřit proti XSD…**. Finální export na stejné kartě je
nadále blokovaný. Použitá XSD se před kompilací kontrolují proti manifestu,
namespace a typy ověřuje lxml XMLSchema. Výsledek neobsahuje hodnoty osobních údajů.

Ekvivalentní CLI, pro XML vytvořené jiným generátorem nebo uložené při vývoji:

```bash
.venv/bin/python -m app.xml CESTA_K_XML --bundle-id jmhz-1.4.3.6
.venv/bin/python -m app.xml CESTA_K_XML --bundle-id jmhz-1.5.0.3
```

Návratové kódy: 0 = XSD prošlo, 1 = XML/XSD kontrola neprošla, 2 = kontrolu
nešlo připravit (chybějící/pozměněný soubor, chyba schématu, nepovolený zdroj).
Volba balíčku je výslovná; účinnost se neodvozuje ze složek a není garantována.
Pro jiné lokální balíčky existují `--schema`, `--bundle-root` a volitelný
`--manifest`; nelze je kombinovat s `--bundle-id`.

Resolver dovoluje jen lokální XSD uvnitř vybrané kořenové složky. Nepovoluje
síťové URL, jiné soubory mimo balíček ani DTD. Vzorky výsledkových protokolů
nevalidujte jako vstupní měsíční podání; jejich namespace a účel jsou odlišné.

```json
{"xsd_valid":true,"methodological_validation":"not_implemented","official_origin":"unverified","submission_ready":false}
```

Tato kombinace stavů je záměrná: lze mít XSD-platný dokument bez povinného
věcného obsahu. Aplikace ho neoznačuje za připravený k podání.
