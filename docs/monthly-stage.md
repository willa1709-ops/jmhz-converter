# Měsíční paket, součty a pracovní návaznosti podání

Etapa navazuje na PR #6. Pracovní XML nyní obsahuje `hlavicka`, skutečný
`souhrn`, `PVPOJ` a individualizovanou část z konkrétní XSD sady 2026/2027.
**Přítomnost všech částí a XSD shoda nejsou potvrzením metodické správnosti
ani připravenosti k podání. Finální export zůstává blokovaný.**

## Zdroje a mapování

`souhrn.xsd` i `PVPOJ.xsd` dodaných sad mají po 11 a 19 koncových cestách.
Používá se stejný hashově ověřený kontrakt jako u zaměstnanců: pořadí, typy,
volitelné rodiče a povinnosti se neodvozují z názvů CSV. Původní dokumenty se
nemění. Nové pracovní profily jsou
[2026](../config/conversion/monthly-2026.json) a
[2027](../config/conversion/monthly-2027.json), včetně hlaviček bez částek.
Kanonické názvy `employer_...` nejsou domnělá čísla položek Pascalového systému.
Profil může místo sloupce použít skutečnou číslovanou položku přes `items` a
`{"item":"skutecne_cislo"}`; číslo musí být dodaný text číslic, nikoliv tento
zástupný řetězec.

Zaměstnavatelský export představuje **jeden řádek** se skutečným IČO, VS,
obdobím a dodanými souhrny. Jeho import se váže na konkrétní import PP a vlastní
organizaci/měsíc. Nesouhlas identifikace nebo období se odmítá. Nový souhrnný
import vždy zachová starší verzi. Definice, zdroje, parametry a bezpečný report
kontroly zůstávají v databázi této organizace.

Obě sady vyžadují daňový měsíční souhrn a pojistné celky/k úhradě. V roce 2027
je seznam kolektivních smluv přímo v souhrnu povinný; ve starší sadě je pod
ročními údaji. Neznámý stav se nesmí automaticky nahradit kódem „žádné“.
Číselníky kolektivní smlouvy (0–5) a formy vlastnictví (1–4) se kontrolují;
prosinec vyžaduje skutečnou formu vlastnictví (10220, pokyny 1.5, str. 23).
Více položek opakovaných seznamů stále vyžaduje rozšíření; nyní se konstruuje
jedna instance, stejně jako v předchozí zaměstnanecké etapě.

## Doložené součty

V obou originálních katalozích kontrol jsou explicitně uvedeny:

| Kontrola | Vztah |
| --- | --- |
| 7 | 10023 = součet 10478 za podporované běžné PP; zvláštní skupiny mají odlišné podmínky a nejsou tímto generátorem pokryté |
| 9 | 10025 = součet 10479 za příslušné PP |
| 12 | 10028 = součet 10370 za příslušné PP |
| 11 | 10027 = 10024 + 10026 + 10484 |
| 13 | 10029 = 10027 + 10028 |
| 4 | 10033 = 10029 − 10032 − 10487 − 10545 |

Standardně se skutečné hodnoty pouze porovnají. Chybějící operandy vytvoří
otevřený nález; nejsou nulové. Výslovná vazba
`{"control_sum":"12","compare_column":"kontrolni_soucet_ze_mzdy"}`
na přesném cíli `PVPOJ/pojistne/pojistneZamestnance` dovolí doložený součet
vypočítat a porovnat s exportem. Podporovány jsou pouze rovnice této tabulky,
žádné textové vzorce nebo automatické procentní sazby.

Odvození vyžaduje každý potřebný údaj: při chybějícím 10370 u jednoho PP se
zastaví, i když ostatní mají nulu. Výpočty používají přesný `Decimal`; zaokrouhlení
ani sazby pojistného se nevymýšlejí. Katalogové vzorce s parametrickými konstantami
se nespouštějí z Excelu. Jejich sazby, účinnost, zaokrouhlení a další podmínky
zatím zůstávají k přezkumu. Osobní souhrny na primárním PP se nadále neodvozují
automatickým součtem všech řádků osoby.

## GUI a historie

Vyberte organizaci a měsíc, import PP a `Celý měsíční paket…`. Zvolte zaměstnanecký
profil, profil souhrnů, jednořádkový souhrnný CSV Windows-1250 a skutečnou hlavičku.
Kontrola rozlišuje blokující chyby a otevřené metodické otázky. Náhled a historie
obsahují všechny tři části; nepřepisují jiný import nebo organizaci. Počet
nálezů v přehledu zahrnuje také měsíční kontrolu.

Offline balíček může obsahovat `monthly_profile` spolu s `employee_profile`,
číslovaným profilem a XSD. Všechny musí patřit ke stejné schválené sadě/pinu.
Builder používá `--monthly-profile`; staré balíčky i jejich historie zůstávají.
Změna zdrojových sloupců/podporovaných vazeb může být offline aktualizací dat;
nové rovnice nebo XML scénáře vyžadují novou aplikační logiku.

## Plány oprav a GUID

Základ pro implementovaný podrozsah je **Pravidla podání JMHZ a související
procesy 1.4.6**, str. 23–26, textový přepis řádky 1019–1024 a 1087–1123,
a kontroly 22/305/306. Dokument rozlišuje GUID měsíčního hlášení od technického
identifikátoru konkrétní zprávy v protokolu (str. 96). Tato aplikace je nesměšuje.

- Lokální plán R má explicitní GUID z připraveného XML. Nový import ani interní
  pořadí 1 automaticky nevytváří režim O nebo nové GUID.
- Pracovní plán O se musí vázat na existující plán vlastní organizace a měsíce
  a stejné GUID měsíčního hlášení.
- Oprava z iniciativy zaměstnavatele používá původní GUID součásti; náhrada
  nepropustně vadné součásti vyžaduje nové GUID formuláře. Důvod je výslovný,
  nevyvozuje se z čísel revize.
- Kontroluje se prokázaná vazba zaměstnání (OIČ/PPV a interní identita v organizaci),
  nikoliv jméno. GUID se porovnávají bez ohledu na velikost písmen a lokálně
  nelze použít stejné GUID pro jinou organizaci, měsíc, PP nebo typ vazby.

Tlačítko `Plán podání / opravy…` ukládá **pouze pracovní metadata návaznosti**.
Původní XML se nemění z R na O, opravné XML se tím nevytváří a nic se neodesílá.
Plán není dokladem přijetí původního podání. Stav protokolů zůstává
`not_recorded`, připravenost `unverified`. Interní pořadí plánu navazuje od nuly
pro organizaci/měsíc; starší pořadí importů, kontrol a příprav zůstávají zachovaná.
První důvod se vztahuje ke všem součástem zahrnutým v tomto pracovním plánu;
výběrové kombinace nahrazovaných/nezměněných součástí ještě nejsou implementované.

Storno, zamítnutí celého podání, protokoly DIS/cJMHZ, kombinace více důvodů,
nové PP v opravném podání a účinnost metodiky 2026 vůči 2027 vyžadují další práci.
Přesné automatické rozhodnutí o přidělení/opakování GUID pro tyto výjimky se
nepředstírá. Ani uložený plán a XSD shoda neodblokují finální export.

## Zálohy a obnova

`Nešifrovaná záloha…` vytvoří konzistentní SQLite snímek jedné organizace,
včetně importů PP/souhrnů, kontrol, XML, plánů a všech potřebných verzí definic.
Registry jiných organizací ani jejich řádky se do archivu nekopírují.
Data se streamují, limit je 512 MiB a 4000 souborů. Záloha se nepřepisuje.

SHA-256 archivu uložte **mimo archiv**. Obnova jej vyžaduje, kontroluje cesty,
CRC, hashe, databázi, vlastníka a vazby a odmítá přepsat existující organizaci
nebo kolidující GUID/definice. Obsah starých sad zůstává; mění se pouze fyzická
umístění jejich odkazů s auditním záznamem obnovy. Ostatní data a hashe zůstávají.
Po havárii procesu mezi přesunem souboru a zápisem registru může zůstat osiřelá
složka; opakovaná obnova ji nepřepíše. Původní archiv zachovejte a stav řešte
řízeně, nikoliv ručním slučováním cizích databází.

Archiv, DB i XML jsou **nešifrované**. Hash dokládá kontrolní shodu, ne autoritu
vydavatele nebo ochranu proti útočníkovi ovládajícímu současně archiv i pin.
Na POSIX se nové datové adresáře tvoří s 0700 a záloha s 0600. Pro Windows je
připraven [skript ACL](../packaging/configure-data-acl.ps1), který musí být skutečně
otestován. Šifrování, recovery klíče a ochrana proti škodlivému správci zůstávají
v [plánu zabezpečení](payroll-database-security.md).

## Co je nutné dodat před metodickým schválením

Skutečný anonymizovaný export Pascal/DOS včetně čísel položek, záznamů více PP,
souhrnů/pojistného a kontrolních součtů; význam prázdných hodnot; potřebné
počty úseků a stav práce/registrace; potvrzené případné sazby/zaokrouhlení;
správný referenční výstup a doklady účinnosti/původu. Nulový příjem, cizinci a
souběhy zachovávají všechna dřívější omezení popsaná v
[zaměstnaneckém generátoru](employee-generator.md). Kompletní struktura XML
neznamená kompletní pokrytí všech situací zaměstnavatele.

## Výsledek ověření této etapy

Dne 2026-10-31 v Linuxovém prostředí prošlo 229 testů celé moderní sady
(Python 3.12 / PySide6) a 153 testů společného jádra a GUI
(Python 3.8.20 / PySide2 5.15.2.1). Obě sady zahrnují skutečná XSD 2026/2027,
celý pracovní paket, součty, izolaci, pracovní návaznosti, obnovu definic
a průchod GUI včetně náhledu měsíčního XML. Příkazy:

```text
python -m pytest -q
python -m pytest -q tests/test_conversion_core.py tests/test_numbered_payroll.py tests/test_organizations.py tests/test_employee_xml.py tests/test_monthly_packet.py tests/test_backup_restore.py tests/test_qt_workflow.py tests/test_packaging_tools.py
```

Druhý příkaz používá samostatný Python 3.8, nikoliv moderní venv.
Kontrola katalogových hashů a `git diff --check` prošly. Jde o Linuxové
automatické ověření; žádné Windows EXE, skutečná mzdová data, podání nebo
Windows ACL tímto ověřeny nejsou.
