# JMHZ Converter

Lokální desktopový **prototyp** pro Windows, Python 3.12+, PySide6.
Obsahuje první analýzu, pracovní návrh CSV a základ aplikace. **Není dokončené P0
a nevytváří XML připravené k podání.** Dodané podklady 2026/2027 jsou evidované,
porovnané a jejich XSD se lokálně kompilují. Původ a účinnost celých sad stále
vyžadují doložený přezkum. Žádné smyšlené elementy JMHZ nejsou implementovány.

- [Analýza, CSV → interní model, součty, omezení a plán](docs/analysis.md)
- [Formát a příklady mapovacích pravidel](docs/mapping.md)
- [Syntetický CSV vstup](config/example.csv)
- [Sestavení a ověření na Windows](docs/windows.md)
- [Ruční import XSD a porovnání definic](docs/definitions.md)
- [Co ručně stáhnout z ČSSZ/MPSV](docs/manual-downloads.md)
- [Složka oficiálních podkladů a manifest](schemas/official/README.md)
- [Inventura a rozdíly dodaných verzí, účinnost a omezení](docs/official-comparison.md)
- [Příjem dokumentů a skutečná XSD validace přes UI/CLI](docs/official-intake.md)
- [Doložený pracovní podklad CSV → XML](docs/csv-jmhz-evidence.md)

## Spuštění

Windows PowerShell (z kořene repozitáře):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app
.venv\Scripts\python -m pytest -q
```

Linux / cloud:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cloud.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pytest -q
.venv/bin/python -m app
```

V cloudu bez displeje použijte pro testy `QT_QPA_PLATFORM=offscreen`.
Na Windows je nutné desktopové spuštění ověřit samostatně; zde byly ověřeny Linux
a Qt offscreen. Linuxová sestava PyInstaller nevytváří Windows EXE.

## Práce s prototypem

1. Na kartě Import dat vyberte CSV/XLSX, případně kódování a oddělovač CSV.
2. Prohlédněte textové hodnoty v náhledu. Identifikátor `000001` zůstane zachován.
3. Na kartě Mapování upravte deklarativní pravidla a případně uložte profil JSON.
4. V Kontrole dat zvolte očekávané období a spusťte kontrolu; dvojklik na nález
   otevře zdrojový řádek. Součty mají vlastní kartu.
5. V Definicích JMHZ lze importovat celý `schemas/official/manifest.json` nebo
   jednotlivá XSD, XLSX, ZIP, číselníky CSV a metodiku PDF/TXT/MD/JSON a porovnat
   dvě verze stejného typu. Původ zůstává NEOVĚŘEN;
   technická kontrola se eviduje odděleně. Význam metodiky a dopad na mapování
   nejsou automaticky vyhodnoceny.
6. V Generování XML lze vybrat dodaný XSD balíček a zkontrolovat XML soubor.
   Finální mzdový export je blokovaný; XSD úspěch sám není metodická validace.

CSV: UTF-8 (i BOM) nebo Windows-1250, oddělovače `; , TAB |`, čárka/tečka
v částkách, citování a vícerádkové buňky. Nekonzistentní tabulka je odmítnuta.
XLSX: aktivní list, textové hlavičky, částky jako text nebo číslo; vzorce,
datumové, logické a chybové buňky jsou odmítnuty. Identifikátory musejí být textové
už v Excelu: číselný zdroj pro employee_id vyvolá chybu mapování i při přejmenování
sloupce nebo skládání identifikátoru. Číselná nula částky se nezamění za prázdnou
buňku. Peníze se dále počítají přes Decimal, ale aplikace nemůže obnovit přesnost
nebo počáteční nuly ztracené před exportem v Excelu; pro plnou přesnost použijte text.
Limit vstupu 25 MiB a 100 000 záznamů; rozbalený XLSX nejvýše 100 MiB.
Velké soubory zpracovává aktuální UI synchronně; stránkování patří do další etapy.

## Ověřený rozsah a další práce

Testy pokrývají kódování/oddělovače, zachování nul, XLSX a odmítnutí vzorců,
vadné CSV, mapovací operace a profily, duplicity, chybějící údaje, období,
Decimal a součty, ruční import XSD, metadata/hash a strukturální diff, detekci
poškození uloženého obsahu, SQLite a průchod UI včetně knihovny definic.
XML testy používají syntetické XSD i dodaná skutečná XSD se synteticky generovaným
XML: ověřují kompilaci, správný i nesprávný měsíc, namespace a bezpečný resolver.
Nejde o ověření úplného mzdového podání nebo metodiky.
Jádro odmítá DTD a externí zdroje; finální generátor vždy vyvolá ExportBlocked.

Chybí zejména doložený přezkum původu a účinnosti sad, úplné mapování a metodická validace,
generátor úplného mzdového JMHZ,
metodické porovnání a dopad na mapování, nezávislé porovnání součtů pro
složené transformace, datumové transformace a ověření EXE na Windows.
P1 a P2 nejsou implementovány. Podrobný postup a otevřené otázky jsou v analýze.

## Soukromí

Aplikace neprovádí síťové požadavky, neodesílá data a neobsahuje telemetrii.
Data se drží v paměti; automaticky se ukládá pouze konfigurace profilů, bez
mzdových řádků. Výpisy parserů s možným osobním obsahem se nezobrazují do logů.
Používejte chráněný uživatelský účet, zabezpečený disk a syntetická testovací data.
