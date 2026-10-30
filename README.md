# JMHZ Converter

Lokální desktopový **prototyp** pro moderní Windows, Python 3.12+, PySide6.
Pro hlavní počítač Windows 7 SP1 x86 je připraven návrh oddělené varianty a
společné jádro pro Python 3.8; funkční Windows 7 GUI/EXE zatím není prokázané.
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
- [Návrh Windows 7 SP1 x86 vedle moderní varianty](docs/windows7-design.md)
- [Nový pracovní převod CSV/XLSX → XML a potřebné sloupce](docs/conversion-stage.md)
- [Společné jádro a platformní adaptéry](docs/conversion-architecture.md)
- [Číslované položky, více PP, řádkové výpočty a interní revize](docs/numbered-payroll.md)
- [Externí offline balíčky definic a jejich ověřování](docs/offline-definition-packages.md)
- [Organizace, měsíční importy, oddělená data a historie](docs/organizations.md)
- [Doložené alternativy identifikace cizinců a nulové příjmy](docs/workforce-evidence.md)

## Spuštění

Windows 10/11 x64 PowerShell (z kořene repozitáře; ne pro Windows 7):

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

Výchozí okno nyní nabízí registr organizací s IČO/VS a měsíční přehled.
Vyberte organizaci a měsíc, nastavte společný profil (případně výjimku pro
organizaci), importujte CSV/XLSX a spusťte kontrolu. Každá organizace má vlastní
databázi a historii; nový import nepřepisuje starší data. Období a identifikace
zaměstnavatele v exportu se kontrolují proti výběru. Nulové a neznámé příjmy
zůstávají v importu rozlišené. Podrobný postup a pracovní šablona pro
HPP/DPP/DPČ jsou v [návodu organizací](docs/organizations.md).
Úplný XML generátor těchto zaměstnání dosud chybí; scénář `jinyPrijem` je
nenahrazuje a finální export je blokovaný.

Původní nástroje lze otevřít nad vybraným importem; jejich pracovní postup zůstává:

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
   Nově lze také připravit pracovní XML scénáře jinyPrijem přes vlastní profil
   a parametry z `config/conversion/`; návod a chybějící vstupy jsou výše.
   Finální mzdový export je blokovaný; XSD úspěch sám není metodická validace.
7. V Mapování otevřete Číslované položky pro obecnou analýzu jednoho řádku za PP:
   pracovní JSON nebo ověřený offline ZIP, období, interní revize, párování a
   primární PP, přesné součty a porovnání s kontrolními částkami exportu.
   Čísla položek a vzorce v šabloně vyžadují potvrzení skutečným mzdovým exportem.
   Nové číslované mapování na pracovní XML lze použít přes CLI/API; návod je výše.

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
metodické porovnání a dopad na mapování, potvrzení čísel položek a vzorců ze
skutečného mzdového exportu, datumové transformace a ověření EXE na Windows.
P1 a P2 nejsou implementovány. Podrobný postup a otevřené otázky jsou v analýze.

## Soukromí

Aplikace neprovádí síťové požadavky, neodesílá data a neobsahuje telemetrii.
Nový organizační workflow po explicitním importu ukládá mzdové řádky, kontroly
a pracovní XML do samostatných lokálních databází organizací. Nejsou šifrované.
Starý samostatný analyzátor zůstává v paměti; jeho volitelná evidence revizí
ukládá jen metadata zakázek a hash definic. Výpisy parserů s možným osobním
obsahem se nezobrazují do logů. Výslovně uložené pracovní XML obsahuje osobní
údaje; není diagnostickým logem a je nutné ho chránit.
Používejte chráněný uživatelský účet, zabezpečený disk a syntetická testovací data.
