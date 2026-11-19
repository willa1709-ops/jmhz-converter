# Načítání protokolů ČSSZ a cJMHZ

Aplikace podporuje ruční offline import:

- DIS `ProcessingResult`, `type="CSSZ_JMHZ"`, `version="1,0"`: samostatný element,
  doloženou obálku GovTalk/ČSSZ a vnitřní ČSSZ Message.
- cJMHZ `ProtokolOZpracovani` v namespace
  `http://schemas.cssz.cz/JMHZ/ProtokolOZpracovani/2026`, ve struktuře pozorované
  ve třech dodaných vzorcích. Neznámé stavy se neodhadují.
- PDF a jiné/nepodporované XML jako nevyhodnocené přílohy.

Nic nestahuje, neodesílá a neodblokuje finální export.

## Postup

1. Vyberte organizaci, vykazovaný měsíc a **původní import**, ke kterému protokol
   patří. Musí existovat uložené pracovní XML. Nepoužívejte automaticky poslední
   opravený import místo skutečně odeslaných dat.
2. Klikněte **Protokoly ČSSZ…** a zvolte konkrétní uložené XML.
3. Vyplňte pouze volitelné pole odpovídající typu protokolu: u DIS vlastní ID
   zprávy `vlastniIdPodani`, u cJMHZ technické `idKonkretnihoPodani`.
   Tato pole nejsou zaměnitelná s GUID měsíčního hlášení `idPodani` ani interní
   revizí. Technické ID kopírujte přesně: vzorky mají délku 32 i 36 znaků,
   proto se nepřepisuje do formátu UUID. Počet balíků se používá pouze pro DIS;
   neznámý počet ponechte „Nevím“.
4. Potvrďte organizaci, měsíc a konkrétní XML. DIS nemusí obsahovat VS/období
   ani GUID měsíčního hlášení, kontext nelze odhadnout z názvu souboru.
   U podporovaného cJMHZ se VS, období a GUID MH navíc povinně porovnají.
   Tato vazba sama není kryptografickým ověřením původu.
5. **Načíst protokol XML / přílohu PDF…** uloží originál s SHA-256. Zvolte řádek
   historie. Karta **Nálezy / části podání** ukáže část, kód, typ, popis a doloženou
   vazbu na PP; **Údaje protokolu** obsahují další metadata a rozsah ověření.
6. **Uložit původní XML / PDF…** získá nezměněný originál například po obnově
   zálohy. Vyžaduje nový soubor v chráněném umístění; nic neotevírá automaticky.

Protokoly zůstávají v SQLite dané organizace s vazbou na import **a konkrétní
XML**, nikoliv ve společném registru osob nebo diagnostických souborech.
Opakované načtení stejných bajtů se stejným kontextem nevytvoří duplicitu;
změněný kontext se odmítne, nová odpověď zůstává samostatným záznamem.
Záloha a obnova organizace zahrnuje originály i výsledky. Import staršího
protokolu nepřepíše automaticky aktuální stav měsíčního hlášení.

## Doložená interpretace DIS

Podkladem je dodaný archiv `schemas/official/2027/mpsv-jmhz-protokoly-mh-v1.5.zip`,
zejména `MPSV-JMHZ-protokoly MH_v1.5.docx`, sekce „Interpretace protokolu MH“.
Starší TXT obsahuje pracovní formulace i neplatný XML přepis, který parser
neopravuje odhadem. Test zahrnuje skutečný XML vzorek archivu a syntetické případy.
Původ a účinnost dodaných podkladů stále vyžadují doložený přezkum.

- Toplevel `result="OK"` znamená přijetí **do dalšího zpracování**. Pro navázání
  na zvolené XML se navíc kontroluje pokrytí jeho individuálních GUID.
- První `Item` s prázdnými `sqnr`/`identifier`/`subtype` představuje obecné
  kontroly. Jeho ERROR zamítá celé dílčí podání, i když mají formuláře OK.
- SOUHRN/PVPOJ reprezentují tyto části. FORM se páruje přes `sqnr` = původní
  `idFormulare`. Cizí GUID nebo rozpor se skutečně odeslaným OIČ/PPV se odmítá.
- Kombinace OK/ERROR znamená částečné přijetí DIS. Jsou-li všechny formuláře
  chybné, dokument rozlišuje jeden balík (zamítnutí) a více balíků (částečné
  přijetí). Bez skutečného počtu balíků zůstane výsledek k přezkumu.
- Neznámý/rozporný stav nebo chybějící pokrytí nejsou úspěch. Počty a kódy se
  uchovávají tak, jak přišly; chybějící kontroly se nevymýšlejí.
- Nově vrácené OIČ/PPV se **neaplikují automaticky** do importu, registrace nebo
  historie osob. Zůstávají v soukromém protokolu. U cizince se neporovnávají
  s metadaty, která jeho původní XML kvůli identifikační alternativě neobsahovalo.

## Pozorovaný protokol o kompletnosti cJMHZ

Strukturu nyní dokládají tři uživatelem poskytnuté soubory stejného namespace.
Originály s identifikátory a texty chyb **nejsou v repozitáři**, testy používají
nezávisle vytvořená syntetická data. Namespace není důkaz původu ani účinnosti;
rok v namespace se nezaměňuje za vykazované období.

Čtou se `datumProtokolu`, `variabilniSymbol`, `idKonkretnihoPodani`, `datumPodani`,
`idPodani`, `mesic`, `rok`, `stavMH/kod`, `stavMH/nazev` a `chybySeznam/chyba`.
U nálezu se zachová `id`, `typChyby`, `castPodani`, volitelné `idFormulare`,
`kod` a `popis`. Popis je text, nikdy příkaz nebo zdroj mzdového vzorce.

Rozpoznané jsou pouze pozorované shodné dvojice:

| Kód | Název ve vzorcích |
| --- | --- |
| 4 | Hlášení je částečně přijato |
| 6 | Hlášení obsahuje propustné chyby |

Významy popisují také Pravidla podání 1.4.6, str. 28 (textový přepis přibližně
řádky 1222–1254). U propustných chyb dokument uvádí přijetí jako celku s chybami
k opravě; **nejde automaticky o zamítnutí**. Program nepřidává domnělý příznak
úplnosti. Neznámý kód, rozporná legenda či nová struktura zůstávají `unresolved`;
původní kód/název se soukromě zobrazí. Bezchybný úspěšný scénář nebyl dodán.

`stavMH` je nahlášený **stav měsíčního hlášení**. Neodvozuje se z něj výsledek
konkrétního podání nebo zamítnutí všech jeho PP. Seznam obsahuje nálezy,
nikoliv všechny výsledky všech formulářů. Formulář se páruje výhradně přes
explicitní `idFormulare`, i když `castPodani` říká `nezarazeno`. Chyba části
`form` bez GUID se na zaměstnance neodhadne. Více nálezů jednoho formuláře je
přípustných. Odkaz mimo zvolené XML zůstane nepřiřazený: může souviset s jinou
částí/revizí téhož MH. Jiné organizace se neprohledávají a z popisu se nevybírá
RČ/OIČ. Rozpor VS, období nebo měsíčního GUID import odmítne.

Bez nezávisle známého technického ID se netvrdí ověření konkrétní odeslané
zprávy. Ukládá se historické tvrzení protokolu; poslední načtený soubor se
neprohlásí za aktuální stav MH. Opravné XML ani změna GUID z něj nevznikají.

## Hranice ověření a ochrana dat

**DIS přijetí není kompletnost cJMHZ.** Rozlišení dokládají také Pravidla podání
1.4.6, str. 94–96. Více oprav/storen může měnit měsíční stav jinak než výsledek
jednotlivého podání.

Protokolové XSD nebylo dodáno: **XSD validace protokolu se nepředstírá**.
Přítomný podpis/timestamp není ověřen. SHA-256 dokládá shodu uložených bajtů,
nikoliv úřední původ, pravost doručení nebo přijetí. PDF není obsahově ověřené.
Pro další stavy/verze je třeba oficiální schéma/číselník nebo další doložený
protokol. Jiné typy odpovědí zůstávají nevyhodnocenou přílohou.

Parser odmítá DTD, externí entity/zdroje, nejednoznačná či duplicitní skalární
pole a nadlimitní obsah. Společný limit je 10 MiB a 30000 XML uzlů. DIS má limit
1500 individuálních FORM. cJMHZ má samostatný lokální limit 3000 nálezů; nejde
přitom o domnělý oficiální limit počtu chyb.

Běžná diagnostika neobsahuje RČ/OIČ, mzdy ani texty chyb. Soukromý náhled,
originály a zálohy mohou obsahovat osobní údaje a **nejsou šifrované**.
Starší pracovní plány uchovávají neměnný snímek `receipt_status: not_recorded`;
nově načtené protokoly mají vlastní historii. Plán se nepřepisuje a není dokladem
skutečného odeslání. **Finální export zůstává blokovaný.**

Po sloučení změn je pro instalovaný program potřeba nové sestavení EXE;
samotná aktualizace datových definic nové funkce kódu nepřidá.

## Výsledek ověření 19. 11. 2026

Celá moderní sada: **291 testů prošlo**, Linux Python 3.12.14 / PySide6 6.12.0.
Kompatibilní sada jádra a GUI: **209 testů prošlo**, Linux Python 3.8.20 /
PySide2 5.15.2.1. Obsahuje 16 nových testů cJMHZ a zachovaných 20 testů DIS,
izolaci VS/období/GUID, různé technické identifikátory, neznámé stavy, nejednoznačné
XML, nepřiřazené či opakované nálezy, zálohu/obnovu a společný GUI náhled.
Tři poskytnuté originály byly místně načteny bez výpisu osobních/mzdových údajů;
žádný originál není testovacím souborem nebo součástí distribuce. Prošly kontroly
hashů oficiálních podkladů a relativních odkazů. Windows běh této etapy nebyl
proveden; zabalený syntetický self-test je rozšířený i o cJMHZ a obnovu protokolu.
