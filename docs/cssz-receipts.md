# Načítání protokolů ČSSZ

Aplikace podporuje **ruční offline import protokolu DIS `ProcessingResult`
`type="CSSZ_JMHZ"`, `version="1,0"`**. Umí samostatný XML element, doloženou
obálku GovTalk/ČSSZ a vnitřní ČSSZ Message. Nic nestahuje a nic neodesílá.
PDF a jiný/nepodporovaný XML formát uloží jako nevyhodnocenou přílohu.

## Postup

1. Vyberte organizaci, vykazovaný měsíc a **původní import**, ke kterému protokol
   patří. Musí existovat uložené pracovní XML; nepoužijte automaticky poslední
   opravený import místo skutečně odeslaných dat.
2. Klikněte **Protokoly ČSSZ…** a zvolte konkrétní uložené XML.
3. Pokud znáte vlastní ID odeslané zprávy (`vlastniIdPodani`), vyplňte jej pro
   přesné porovnání. Není to oficiální GUID měsíčního hlášení ani interní revize.
   Známý počet balíků zadejte výslovně; jinak ponechte „Nevím“.
4. Potvrďte, že soubor patří zvolené organizaci, měsíci a XML. Samotný
   `ProcessingResult` nemusí obsahovat VS/období ani GUID měsíčního hlášení;
   kontext nelze spolehlivě odhadnout z názvu souboru. Vazba je uživatelsky
   potvrzená, nikoliv kryptograficky ověřená.
5. **Načíst protokol XML / přílohu PDF…** provede kontrolu formátu a vazeb a uloží
   originál s SHA-256. Zvolte řádek historie pro přehled výsledku, obecných chyb,
   SOUHRN/PVPOJ a jednotlivých FORM (GUID, zdrojový řádek a interní PP, je-li vazba
   doložená). Texty jsou soukromý náhled, ne diagnostický log.
6. **Uložit původní XML / PDF…** umožní získat nezměněný originál, například po
   obnově zálohy. Vyžaduje nový soubor a chráněné umístění; nic neotevírá automaticky.

Protokoly se uchovávají v SQLite databázi dané organizace s vazbou na import
**a konkrétní XML**, nikoliv ve společném registru osob nebo diagnostických
souborech. Stejné bajty ke stejnému XML a se stejným kontextem nevytvoří duplicitu;
změněný kontext se odmítne, nová odpověď zůstává samostatným záznamem. Záloha a
obnova celé organizace zahrnuje originály i výsledky. Import staršího protokolu
nepřepíše automaticky „aktuální stav“ měsíčního hlášení.

## Doložená interpretace DIS

Podklad je dodaný archiv
`schemas/official/2027/mpsv-jmhz-protokoly-mh-v1.5.zip`, zejména dokument
`MPSV-JMHZ-protokoly MH_v1.5.docx`, sekce „Interpretace protokolu MH“.
Přibalený starší TXT obsahuje pracovní formulace i neplatný XML přepis;
parser jej neopravuje odhadem. Test zahrnuje skutečný XML vzorek z archivu,
syntetické hraniční případy a podporované namespace. Původ/účinnost dodaných
podkladů stále vyžadují doložený přezkum.

- Toplevel `result="OK"` znamená přijetí **do dalšího zpracování**. Pro navázání
  na vybrané XML se navíc kontroluje pokrytí jeho individuálních GUID.
- První `Item` s prázdnými `sqnr`/`identifier`/`subtype` představuje obecné
  kontroly. Jeho `ERROR` znamená zamítnutí celého dílčího podání, i když jsou
  jednotlivé formuláře uvedené jako OK.
- Další položky SOUHRN/PVPOJ reprezentují tyto části, FORM se páruje přes
  `sqnr` = původní `idFormulare`. Neznámý GUID nebo rozpor skutečně odeslaného
  OIČ/PPV odpovědi s XML se odmítá. Osoby se nepárují podle jména.
- Při kombinaci OK/ERROR jde o částečné přijetí DIS. Když jsou všechny formuláře
  chybné, dokument rozlišuje jeden balík (zamítnutí) a více balíků (částečné
  přijetí). Bez skutečného počtu balíků zůstane výsledek k přezkumu.
- Neznámý/rozporný stav a chybějící pokrytí se nesmějí změnit na úspěch.
  Počty a chybové kódy se uchovávají tak, jak přišly; nevymýšlí se chybějící kontroly.
- Nově vrácené OIČ/PPV se **neaplikují automaticky** do importu, registrace ani
  historie osob. Zůstávají v soukromém protokolu pro přezkum. U cizince bez
  odeslaných identifikátorů se neporovnává s metadaty, která XML skutečně neobsahovalo.

## Hranice ověření

**Protokol z DIS není protokol o kompletnosti cJMHZ ani potvrzení metodicky
správného úplného měsíčního hlášení.** Rozlišení dokládají Pravidla podání 1.4.6,
str. 94–96 (v dodaném textovém přepisu řádky přibližně 4751–4882).
Více oprav/storen může měnit měsíční stav jinak než výsledek jednotlivého podání;
program poslední načtený soubor neprohlásí za tento stav.

Protokolové XSD ani přesná XML struktura výsledku kompletnosti cJMHZ v dodaných
podkladech nejsou. Aplikace tedy **nepředstírá XSD validaci protokolu**, nevytváří
nové cJMHZ elementy a neoznačuje PDF za obsahově ověřené. Pro rozšíření dodejte
aktuální definici/strojové schéma a anonymizovaný XML protokol kompletnosti
(včetně obálky), ideálně také DIS chybový příklad z používaného kanálu.
Odpovědi APEP/VREP bez uvedeného ProcessingResult či jiné typy podání zůstávají přílohou.

XML parser odmítá DTD, externí entity/zdroje, nejednoznačné či duplicitní položky
formulářů a nadlimitní obsah (10 MiB, nejvýše 1500 individuálních FORM).
Přítomný podpis/timestamp **není ověřen**. SHA-256 dokládá shodu uložených bajtů,
nikoliv oficiální původ, pravost doručení nebo přijetí úřadem.
Běžná diagnostika nezahrnuje RČ/OIČ, mzdy ani texty chyb. Zobrazené protokoly,
originály a zálohy mohou obsahovat osobní údaje a **nejsou šifrované**.

Starší pracovní plány podání mají neměnný `receipt_status: not_recorded` z doby
vytvoření plánu. Nově načtené protokoly jsou oddělená historie u konkrétního XML;
původní plán se zpětně nepřepisuje ani nepovažuje za skutečné odeslání.
**Finální export zůstává blokovaný** bez ohledu na výsledek importu protokolu.

Ověření 19. 11. 2026: celá moderní sada 275 testů prošla (Linux, Python 3.12.14,
PySide6 6.12.0); kompatibilní sada společného jádra a Qt5 193 testů prošla
(Linux, Python 3.8.20, PySide2 5.15.2.1). Zahrnuje 20 testů protokolů, skutečný
XML vzorek z dodaného archivu, syntetické výsledky, bezpečnost parseru, izolaci,
neměnnost importu, zálohu/obnovu a GUI. Tato etapa nebyla spuštěna na Windows.
Po sloučení změn je pro instalovaný program potřeba nové sestavení EXE;
samotná aktualizace datových definic nové funkce kódu nepřidá.
