# Ruční přejímka Windows 11 – opravy PR #10

Výchozí commit: c0d9806 (main po PR #9). Pouze syntetická data.

## Zjištěné příčiny a očekávané chování

1. Obnova: předání vybrané cesty a nezávislého SHA-256 do jádra i obnova do
   prázdného registru fungují v regresních testech. Konkrétní příčinu původního
   odmítnutí bez původního ZIP/hash nelze určit (nesprávný ZIP zůstává možností).
   Prokázaná chyba GUI: úspěch i obecná chyba byly jen ve stavovém textu dole
   v posuvném okně, tedy mohly být mimo obrazovku; výjimka se nerozlišovala.
   Nyní je výsledek v modálním hlášení, očekávané validační odmítnutí má konkrétní
   důvod. Neočekávané chyby mají bezpečné hlášení o čtení/struktuře/zápisu.
   Další prokázaná chyba: selhání po instalaci definic zanechávalo novou sadu.
   Při selhání se nyní odstraní pouze sady vytvořené tímto pokusem.
   Registr se vrací transakcí, nově vytvořený datový adresář se odstraní.
   Původní organizace ani existující definice se nepřepisují.
2. Revize: samostatný nástroj „Číslované mzdové položky“ počítá s revizí jen
   ve výpočtovém kontextu; nezapisuje organizační historii. To je očekávané.
   V hlavním okně vyberte organizaci, měsíc a poslední import, spusťte
   „Kontrola a výpočty“, nastavte interní pořadí a stiskněte „Zapsat interní
   verzi“. První záznam je 0, další 1 atd. Vyžaduje poslední kontrolu bez nálezů.
   Přehled zobrazuje uloženou verzi, nikoli číslo z pracovního kalkulátoru.
   Změna revize nemění GUID ani režim R/O; plány mají samostatnou evidenci.
3. Plány: bez vybraného importu a pracovního XML se dialog záměrně neotevřel,
   ale vysvětlení bylo opět jen dole ve stavovém textu. Navíc načtení historie
   a sestavení dialogu nebylo chráněno obsluhou výjimek. Nyní se chybějící
   kontext/XML i chyba otevření oznamují viditelně. Kontroluje se aktuální
   organizace/měsíc a dostupnost XML. Platné explicitní GUID, identity PP,
   návaznost, důvod a pořadí se ověřují při ukládání plánu; odmítnutí má důvod.

## Ruční ověření na skutečném Windows 11 x64

Tento postup ještě musí být proveden na Windows 11 s Pythonem 3.12.10:

1. Založte dvě syntetické organizace a importy ve dvou měsících; proveďte
   kontroly, uložte interní verze 0/1 a pracovní XML. Vytvořte pracovní plán R.
2. Vytvořte ZIP zálohu. SHA-256 uložte nezávisle mimo archiv. V novém prázdném
   registru zvolte přesnou cestu ZIP a tento hash. Očekávejte dialog úspěchu,
   organizaci v přehledu, shodné importy, kontroly, verze, XML, definice a plány.
3. Zkuste jiný hash, jiný ZIP a opakovanou obnovu stejné organizace. Očekávejte
   viditelné odmítnutí bez přepsání nebo částečné organizace. Zkontrolujte druhou
   organizaci a jiný měsíc. Ověřte i české znaky a mezery v cestě ZIP.
4. V samostatném kalkulátoru spočítejte revize 0/1: organizační přehled se tím
   nemění. Potom použijte výše popsaný hlavní workflow: uložená verze se změní.
5. Klikněte na Plán bez importu a bez XML: musí se ukázat konkrétní hlášení i
   při okně 1024×720 a zvýšeném DPI. Vytvořte XML s explicitními GUID, otevřete
   dialog, zrušte jej, znovu otevřete a uložte plán. Ověřte odmítnutí chybné
   návaznosti/pořadí a neměnnost XML. Přepněte měsíc/organizaci a ověřte izolaci.
6. Ověřte, že finální export zůstává blokovaný. Žádný plán neodesílá podání ani
   nevytváří opravné XML.

## Omezení a samostatný návrh SHA-256

Kontrola celého ZIP proti nezávislému hashi i manifest jednotlivých souborů
zůstávají povinné. Samostatný budoucí návrh: umožnit načíst hash z uživatelem
výslovně vybraného nezávislého souboru a zobrazit cestu zálohy před potvrzením.
Hash automaticky odvozený z právě vybraného ZIP ani manifest uvnitř ZIP nesmí
nahrazovat nezávislé ověření. Tento návrh zde není implementován.

Obnova je ošetřena pro běžné výjimky; nejde o novou garanci atomického zotavení
po výpadku napájení mezi filesystemem a SQLite. Není měněno schéma, metodika,
Pascal/DOS jádro ani uživatelská historie. Windows 7 x86 vyžaduje samostatnou
přejímku na skutečném systému; kontrola syntaxe Python 3.8 a společné Qt API
nenahrazují běh na Windows 7.

## Automatické ověření

Linux x64, Python 3.12.14, PySide6/Qt6 offscreen: `python -m pytest -q`
— 255 passed, 0 failed, 0 skipped. Původní sada před přidáním nových regresí:
250 passed. Nové testy zahrnují skutečné volání GUI obnovy (cesta s českými znaky,
hash, kolize), záznam verzí 0/1, předpoklady plánu, chybu otevření, uložení a
odmítnutí duplicitního plánu. Testy obnovy navíc simulují selhání přesunu databáze,
ověřují rollback registru/datového adresáře a odstranění nově instalovaných definic.
Stávající testy pokrývají zachování XML, historie, definic a izolaci GUID/plánů.
Všechny změněné Python soubory prošly `ast.parse(feature_version=(3,8))`;
`git diff --check` bez chyb. Běh Python 3.8/Qt5 nebyl v tomto prostředí proveden.
