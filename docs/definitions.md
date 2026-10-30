# Lokální knihovna definic

Na kartě **Definice JMHZ** lze ručně načíst XSD, číselník CSV a metodiku PDF/TXT/MD/JSON. Aplikace sama
nic nestahuje. Uživatel uvede přesné veřejné HTTPS URL původního dokumentu a
jeho verzi; účinnost od/do je volitelná, neznámá účinnost se nevymýšlí.
URL nesmí obsahovat přihlašovací údaje, query parametry ani fragment.

1. Vyberte typ, vyplňte metadata a zvolte **Ručně importovat dokument…**.
2. V seznamu zkontrolujte zdroj, verzi, účinnost, čas získání UTC a SHA-256.
3. Importujte druhou verzi stejného typu, vyberte původní a novou a spusťte porovnání.

Každá importovaná definice má stav **NEOVĚŘENO**. Ruční zadání URL ani kontrolní
hash nepotvrzuje oficiální původ nebo účinnost. Import neaktivuje definici pro
konverzi a **neodblokuje finální XML**. Metodická a logická pravidla mimo XSD
nejsou součástí tohoto porovnání; jejich úplnost se nesmí předpokládat.

## Uchování a bezpečnost

Soubor `definitions.sqlite3` v uživatelském Qt AppDataLocation uchovává původní
bajty dokumentu, metadata a normalizovaný strukturální přehled. Zápis je transakční.
Původní soubor lze po importu přesunout; knihovna na něm nezávisí. Stejný hash,
verze a URL nezaloží nový záznam a nezmění původní metadata. Chybně zadané údaje
je nyní třeba řešit novým importem s opravenou verzí nebo URL; editor není hotov.

Před porovnáním se ověří hash uloženého obsahu a z tohoto obsahu se znovu odvodí
struktura. To zachytí náhodné poškození obsahu; není to digitální podpis ani
ochrana proti útočníkovi, který může současně upravit soubor a jeho metadata.
Databázi chrání práva uživatelského účtu a případné šifrování disku.

Limit: 5 MiB, 50 000 XML uzlů. Parser odmítá DTD a externí zdroje. U samostatného
XSD 1.0 proběhne kompilace schématu. U include/import/redefine/override se pouze
načte struktura a uvede stav „XSD závislosti neověřeny“: neprohlašujeme platnost
celého balíčku. Žádné závislosti se automaticky nečtou z disku ani ze sítě.
Jejich kompilaci doplní lokální resolver kompletního balíčku.
Síťová adresa v metadatech se nikdy automaticky nenavštěvuje.

**Původ** a **Technická kontrola** jsou v UI oddělené sloupce. Úspěšná kompilace
samostatného XSD nepotvrzuje jeho oficiální původ ani správnost pro konkrétní období.
Ručně vložené soubory v projektu lze navíc evidovat manifestem ve
[schemas/official](../schemas/official/README.md); jeho registr a knihovna v UI
jsou oddělené. Ze složky lze soubor kdykoliv vybrat pro import v UI, synchronizace
obou evidencí není automatická.

Číselník CSV musí být UTF-8 pravidelná tabulka s jedinečnou neprázdnou hlavičkou.
Sloupce se nepřejmenovávají a nepředpokládá se oficiální význam prvního sloupce.
Porovnává se obsah a pořadí řádků, ne věcná platnost kódů. Načtený číselník se
automaticky nezapojí do pracovního mapování bez určení jeho významu.
Metodické JSON/TXT/MD dokumenty se porovnávají jako data/text, nic se z nich nespouští.
U PDF se archivují bajty a hash a detekuje změna obsahu; PDF parser ani výklad
metodiky není implementován. Stav „Pouze archivováno“ neznamená validní PDF.

## Co porovnání znamená

Přehled zahrnuje atributy, text a pořadí XML uzlů XSD, tedy např. `minOccurs`,
`maxOccurs`, `type`, omezení délky, rozsahy, vzory, enumerace, skupiny a strukturu.
Známé QName atributy se rozbalí na namespace; samotné přejmenování prefixu typu
nevytváří změnu. Výchozí min/maxOccurs se normalizuje na 1.

Cesty popisují **uzly schématu**, nejsou to cesty výstupního JMHZ XML. Pořadí
sourozenců je součástí klíče; vložení uzlu může vykázat i posun dalších uzlů.
Jde o strukturální porovnání, nikoliv důkaz sémantické kompatibility. Změny
anotací nebo prefixů v XPath výrazech mohou být zobrazeny jako technické rozdíly.

Dopad na současné mapování nelze automaticky určit: pracovní pole CSV nejsou
dosud propojena s ověřenými oficiálními XML cestami. UI tuto skutečnost uvádí.
Oficiální XSD, kompletní číselníky, metodika a testovací XML stále chybějí.

Testy knihovny používají pouze syntetická XSD a adresy `example.invalid`.
