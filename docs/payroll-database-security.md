# Plán zabezpečení lokálních mzdových databází

Stav k 31. 10. 2026: organizační SQLite, zdrojové snímky, hlavičky, pracovní XML,
žurnály a zálohy **nejsou šifrované aplikací**. Samostatné databáze a kontrola
vlastníka brání chybám v aplikaci, nejsou ochranou proti čtení souborů jiným
procesem pod stejným účtem nebo správcem počítače. Žádná následující fáze není
označena jako plně přijatá na Windows. Aktuální etapa implementuje konzistentní
nešifrované zálohy/obnovu, ochranné POSIX režimy nových složek a připravuje
samostatný Windows ACL skript. Šifrování ani jeho přejímka hotové nejsou.
Finální export je stále blokovaný nezávisle na zabezpečení.

## Rozsah a hrozby

Chránit je nutné registr organizací, zdrojové řádky, OIČ/RČ, alternativní
identifikační údaje, částky, podrobné výsledky kontrol, XML, parametry/GUID,
dočasné soubory, SQLite journal/WAL/SHM a zálohy. Citlivá mohou být i jména
souborů a umístění adresářů. Diagnostický report smí obsahovat jen technické
kódy, řádky, neprůhledná interní ID a hash definic, nikoliv zdrojové hodnoty.

| Hrozba | Opatření a omezení |
| --- | --- |
| Záměna zaměstnavatele v aplikaci | povinný organizační kontext, kontrola vlastníka DB/VS/měsíce, testy cizích ID a reset náhledů; tato část existuje |
| Odcizený disk nebo kopie zálohy | šifrování celého pracovního svazku a šifrované DB/zálohy; ověřit edici Windows a reálnou dostupnost ochrany |
| Jiný běžný uživatel PC | NTFS ACL jen pro určený účet/skupinu, chráněný pracovní adresář; otestovat i dědičnost a nové soubory |
| Malware nebo administrátor v přihlášené relaci | šifrování disku/DB samo nestačí; minimalizace oprávnění, aktualizace, izolovaný provoz, kontrolovaný přenos dat |
| Neúmyslný únik exportem | výslovný export, vlastní adresář organizace, ochrana cíle a záloh; XML potřebné pro podání zůstává citlivé |
| Poškození, ztráta klíče, výpadek proudu | ověřené obnovitelné zálohy, transakční migrace, oddělený recovery postup a test obnovy |

Windows 7 SP1 x86 nemá běžnou bezpečnostní podporu. Pro tuto variantu musí
přejímka výslovně zhodnotit OS, dostupnost aktualizací, kryptografický runtime,
fyzické zabezpečení a kompenzační opatření. Offline provoz snižuje některá
rizika, neodstraňuje rizika USB, lokálních účtů ani škodlivého procesu.

## Fáze 1: umístění a oprávnění

Zvolit jeden chráněný uživatelský datový kořen mimo EXE, instalační adresář,
sdílené složky a běžné synchronizované adresáře. Na Windows používat explicitní
ACL, nikoliv pouze `chmod`. Ověřit existující i nově vytvořené DB, journal, XML,
dočasné soubory a zálohy pod druhým účtem. Chybu nastavení ochrany zobrazit
jako nevyřešený stav, ne jako úspěšně zabezpečenou instalaci.

Registry, profily a manifesty nejsou úložiště hesel. Nezapisovat klíče/hesla do
JSON, SQLite, argumentů příkazové řádky, logů, GitHubu nebo balíčků definic.
Přezkoumat výpisy výjimek, crash dumpy, TEMP a náhledy. Na změnu uživatele,
organizace a období rušit staré náhledy. Zakázat nevyžádané diagnostické uploady.

## Fáze 2: výběr šifrovaného úložiště a klíčů

Provést samostatný technický pokus s udržovaným SQLCipher nebo komerčně
podporovaným SQLite SEE; ověřit licenci, všechny SQLite pomocné soubory,
ABI a skutečné DLL na Win7 x86 / Python 3.8 a na W11 x64 / Python 3.12+.
Pouhá dostupnost wheel není potvrzení kompatibility. Nezavádět neudržovanou
kryptografickou knihovnu jen proto, že jde spustit na starším OS.

Rozhraní úložiště má oddělit databázový engine a správu klíčů od mzdového jádra.
Použít náhodný klíč pro každý organizační datový prostor a samostatnou ochranu
registru. Zvolené řešení musí zajistit autentizaci/integritu, nejen zašifrování
bajtů. Vlastní šifra, XOR nebo domácí obal SQLite nejsou přijatelná náhrada.
Klíč nelze odvozovat z IČO, VS, UUID nebo hesla jednoduchým SHA-256.

Možný způsob lokálního uložení klíče je Windows DPAPI v uživatelském rozsahu,
po skutečném otestování obou OS. DPAPI nesmí být jediný recovery mechanismus:
přeinstalace OS nebo ztráta profilu může znemožnit přístup. Pokud bude potřeba
heslová přenositelnost, vybrat auditovanou KDF a parametry změřené na cílovém
x86 počítači, např. Argon2id, případně doloženou podporovanou alternativu.
Konkrétní engine, KDF a parametry zatím nejsou schválené ani implementované.

## Fáze 3: nedestruktivní migrace

1. Zavřít zápisy, zkontrolovat integritu zdrojové DB a úplnou zálohu v chráněném
   umístění. Zaznamenat organizaci, počty importů/kontrol/verzí/XML a hashe obsahu.
2. Vytvořit nový šifrovaný datový prostor, nekopírovat data přes nechráněné
   dočasné SQL dumpy. Přenést i parametry a podklady historie zaměstnaneckého XML.
3. Porovnat vlastníka, počty, zdrojové a XML hashe, vazby a reprezentativní
   výpočty. Otestovat otevření po restartu, chybné heslo/klíč a obnovu zálohy.
4. Až po ověření atomicky přepnout registr na nový formát. Zaznamenat verzi
   schématu a výsledek migrace, bez osobních údajů. Výpadek v každém kroku musí
   ponechat čitelnou původní nebo novou konzistentní sadu; bez tichého mazání.
5. Řízeně vypořádat původní plaintext DB, volné stránky, WAL/journal, TEMP,
   staré zálohy a pracovní XML. `DELETE`, `VACUUM` ani přepsání souboru nejsou
   univerzální důkaz bezpečného výmazu na SSD. Retence musí zohlednit staré kopie
   a skutečnou ochranu disku; neprohlásit data za odstraněná bez doložení.

Použít formát s verzí a odmítat neznámé/poškozené úložiště. Starší aplikace
nesmí šifrovanou sadu automaticky otevřít jako prázdnou DB nebo vytvořit vedle
ní novou plaintext historii. Klíče se nepřenášejí balíčky JMHZ definic.

## Fáze 4: zálohy, recovery a provoz

Zálohovat transakčně konzistentní snímky a přesné verze definic. Šifrovaná
záloha potřebuje oddělený způsob obnovy klíče; archiv s klíčem vedle DB není
dostatečná ochrana. Stanovit přístup, retenci a obnovu pro organizace odděleně.
Provést obnovu na čistém druhém počítači/účtu bez sítě. Změnu klíče testovat
včetně starších záloh a řízeného rušení přístupu. Bez recovery přejímky neslibovat
bezpečné přenesení na nový Windows profil.

Mzdové exporty a oficiální XML, které musí opustit DB, chránit samostatně.
Případný auditní řetězec musí mít autentizaci a řešit rollback; dnešní SHA-256
v téže databázi prokazuje kontrolní shodu, nikoliv odolnost proti správci,
který může přepsat současně obsah i hash. Automatické odesílání se nezavádí.

## Přejímací podmínky

- Na obou skutečných OS/architekturách prokázat načtení DLL, zamítnutí druhého
  účtu, správné ACL, obnovu po ztrátě profilu a šifrované zálohy bez sítě.
- Prohledat DB a pomocné soubory známými syntetickými identifikátory; nesmějí
  se objevit v chráněných souborech v plaintextu. Prověřit i registry a TEMP.
- Ověřit přerušení migrace, nedostatek místa, poškozený klíč/stránku,
  návrat staré zálohy, více organizací a neztracení historie.
- Změřit paměť/rychlost na Win7 x86; zkontrolovat logy, crash dumpy a instalační
  balíček. Neprovádět testy na skutečných osobních/mzdových údajích v GitHubu.
- Zapsat verze binárek a hashe, nevyřešená rizika, vlastníka schválení a
  postup podpory. Teprve tento záznam opravňuje označení „šifrované úložiště ověřeno“.
