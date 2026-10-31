# Organizace, měsíční importy a historie

Výchozí okno nyní vede uživatele přes organizaci, měsíc, import a kontrolu až
k případnému **pracovnímu** XML. Registrace organizace v této aplikaci je pouze
lokální nastavení; neprovádí registraci u ČSSZ. Aplikace nepřiděluje skutečné
identifikátory zaměstnancům a nepodává hlášení. Finální export zůstává blokovaný.

## Postup v GUI

1. Přidejte skutečný název zaměstnavatele, IČO a desetimístný VS přidělený
   zaměstnavateli/mzdové účtárně. Úvodní nuly jsou součástí hodnoty. DIČ a ID
   datové schránky jsou volitelná lokální metadata, nepřenášejí se automaticky
   do domnělých XML elementů. Další povinné údaje úplného JMHZ musí pokrýt
   dokončený generátor; registr zatím není jejich kompletním datovým slovníkem.
2. Načtěte společný profil číslovaných položek JSON nebo ověřený offline ZIP.
   Pro první přípravu slouží
   [`workforce.template.json`](../config/payroll/workforce.template.json)
   a [hlavička bez osobních/mzdových hodnot](../config/payroll/workforce.headers.csv).
   Čísla položek, vzorec a vazba `income_amount` na 190 jsou **pracovní zástupné
   definice**. Nejdříve je upravte podle skutečného mzdového programu.
   Nepoužité zdroje z profilu odstraňte; deklarovaný zdroj vyžaduje přítomnost
   hlavičky, i když buňka může být prázdná. Nemá-li export IČO/VS, odstraňte
   jejich metadata a správnost výběru organizace kontrolujte ručně.
3. Vyberte organizaci v přehledu a měsíc `26-09` nebo `2026-09`.
   Přehled ukazuje stav posledního importu, všechny importované PP, počet
   nálezů a poslední interní verzi přípravy. Nekontrolovaná data nemají nulu chyb,
   ale stav „nekontrolováno“. Interní verze neznamená odeslané/přijaté podání.
4. Importujte vlastní soubor této organizace. Data i snímek profilu se uloží
   lokálně. Měsíc všech řádků musí souhlasit s výběrem. Mapuje-li profil IČO/VS
   exportu, musejí také souhlasit; jinak se celý import odmítne. Pokud export
   identifikaci zaměstnavatele neobsahuje, aplikace nemůže prokázat, od koho
   soubor pochází: výběr správné organizace musí zkontrolovat obsluha.
5. Spusťte kontrolu. Uvidíte PP, párování, primární PP, řádkové výsledky,
   stavy příjmu a konkrétní požadavky na doplnění. Informativní celkové součty
   uvádějí počet neznámých řádků; neznámý příjem se nezmění na nulu.
6. Historie umožňuje otevřít kterýkoliv starší import. Nový import stejného
   měsíce vždy přidá další verzi dat od indexu 0. I totožný soubor vytvoří nový
   záznam s vlastním UUID; hash umožňuje dohledat shodný obsah. Nic se tiše nepřepisuje.
   „Historie kontrol / XML“ zobrazí uložené nálezy, jednotlivé řádkové výpočty,
   součty a pracovní XML vybraného importu bez přepočtu novější logikou.
7. Interní verzi přípravy lze výslovně zapsat po poslední kontrole posledního
   importu bez nálezů. Číslování 0, 1, 2… navazuje samostatně pro každý měsíc
   a organizaci. Opakování nebo mezera se odmítnou. Nálezy včetně nevyřešené
   identifikace a metodiky nulového příjmu zápis blokují. Tato evidence není
   odesláním, tvorbou GUID ani opravným podáním JMHZ.

Tlačítko pracovního XML nabízí nový skutečný `bezPriznaku` pro doložený rozsah
HPP/DPČ/DPP a zachovává původní `jinyPrijem`. Kontroluje VS, měsíc a konkrétní XSD;
pracovní rozsah a omezení jsou v [návodu generátoru](employee-generator.md).
**HPP/DPP/DPČ se nesmějí vydávat za `jinyPrijem`**. Nepokryté případy zůstávají
blokované nebo výslovně označené k metodickému přezkumu. Finální export je blokovaný.
Pracovní XML se uchovává jen u vlastní organizace a lze ho explicitně zapsat
do její složky `drafts/` bez přepsání existujícího souboru.

Původní nástroje otevřou pouze vybraný snímek importu, s názvem organizace/měsícem
v titulku a kontrolou kontextu hlavičky. Nový import v těchto nástrojích prochází
organizační službou. Změna organizace, měsíce nebo vybraného importu zavře staré
okno a vymaže předchozí náhledy. Nízkourovňová stará API/CLI zůstávají pro zpětnou
kompatibilitu; sama nepředstavují víceorganizační evidenci. Pro běžnou práci
více zaměstnavatelů používejte nové hlavní okno nebo `OrganizationWorkspace`.

## Oddělení dat a identifikátorů

```text
<uživatelská AppData>/workspace/
  registry.sqlite3                    # organizace a odkazy na společné/odlišné profily
  definition-packages/<id>/<version>/ # pasivní definice, bez mzdových řádků
  organizations/<organization-uuid>/
    workspace.sqlite3                # pouze importy, kontroly, verze a XML této organizace
    drafts/<draft-uuid>.draft.xml     # explicitně uložené pracovní soubory
```

Každé veřejné čtení nebo změna mzdové historie vyžaduje ID organizace. Import
jiné organizace nejde otevřít přes cizí ID; každá databáze má i kontrolu vlastníka
a odmítne databázi zkopírovanou od jiné organizace. Cesty se tvoří z ověřeného UUID,
nikoliv z názvu, IČO, RČ nebo názvu souboru. Symlinky datových adresářů/databází
se odmítají. Interní UUID importu, řádku, osoby v zakázce, PP a pracovního XML
jsou odvozená z vlastního UUID organizace. Nejsou to oficiální GUID JMHZ.
Stejné interní číslo PP nebo OIČ/RČ ve dvou organizacích data nepropojí.

Každý import obsahuje původní řádky, příznaky číselných buněk XLSX, hash zdroje
a neměnný snímek profilu/odkaz na konkrétní balíček. Každá kontrola přidává nový
záznam, včetně součtů, nálezů a identifikačního/ohlašovacího posouzení. Přepsání
společného profilu ovlivní až příští importy. Tlačítkem profilu organizace lze
nastavit výjimku; „Použít společný profil“ ji zruší pro budoucí importy.
Historická kontrola používá původní definici. Je-li původní balíček poškozen nebo
odstraněn, kontrola se zastaví; nesáhne tiše po nové verzi.

Na rozdíl od původního samostatného analyzátoru tento workflow po explicitním
importu **trvale ukládá osobní a mzdová data lokálně**. Databáze ani pracovní
XML nejsou šifrované. Oddělení organizací v aplikaci nenahrazuje oprávnění OS
a nezakazuje správci stejného uživatelského účtu číst soubory. Použijte chráněný
účet/disk a zálohujte jednotlivé organizace i jejich přesné definice.
Diagnostické zprávy a bezpečný report neobsahují OIČ, RČ, jména, narození ani
částky. Podrobné zdrojové náhledy, součty a XML jsou soukromá pracovní data,
nikoliv diagnostický protokol. Síť a telemetrie se nepoužívají.

Párování a primární PP nyní zohledňují jen PP ve vlastním importu organizace.
Neúplný export může primární PP určit nesprávně. Více VS téhož IČO vyžaduje
samostatný metodický přezkum případných souhrnů na úrovni IČO; jednotlivé
organizace se k tomu automaticky neslévají.

## Co zbývá dodat a ověřit

- Skutečné, strukturálně věrné anonymizované exporty více organizací včetně
  IČO/VS, více PP jedné osoby a prázdných/absentujících položek.
- Čísla/význam položek, vzorce, zaokrouhlování, kontrolní částky a zdroj
  celkového příjmu; lokální kategorie HPP/DPP/DPČ a skutečné oficiální kódy činností
  nejsou automaticky totéž.
- Úplnost exportu, trvání zaměstnání, práce/absence, pojištění a registrace.
- Doložený postup párování při neexistenci OIČ i RČ, účinnost a původ definic,
  referenční výstupy a životní cyklus oficiálních GUID/podání.
- Dokončení generátoru HPP/DPP/DPČ se souhrnnou a pojistnou částí a metodickými
  kontrolami, navazující Qt5 adaptér a skutečná přejímka na Win7 SP1 x86 i W11.

Podklady pro cizince a nulové příjmy jsou podrobně v
[metodických důkazech](workforce-evidence.md); nejde o potvrzení oficiálního
původu nebo účinnosti celé sady.
