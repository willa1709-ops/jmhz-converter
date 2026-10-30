# Analýza JMHZ a rozhodnutí – 30. 10. 2026

Toto je historická analýza první etapy před dodáním podkladů. Aktuální stav,
skutečné verze a účinnost jsou v [porovnání dodaných dokumentů](official-comparison.md)
a [doloženém podkladu mapování](csv-jmhz-evidence.md).

## Stav ověření

Oficiální definice **nejsou ověřeny**. Pokus o HTTPS přístup přes spravovanou
proxy k `https://www.cssz.cz/`, `https://www.mpsv.cz/` a
`https://jmhz.mpsv.cz/` skončil 30. 10. 2026 odpovědí CONNECT 403.
Jde o síťové omezení tohoto prostředí, nikoliv důkaz, že dokumentace neexistuje.
Tyto adresy jsou výchozí místa rešerše, nikoliv potvrzené URL technických balíčků.
Povolení domén je uloženo v návrhu prostředí, ještě není aplikováno.

| Potřebný podklad | Verze / účinnost / hash | Stav |
| --- | --- | --- |
| XSD včetně všech importů a namespace | neznámé | nezískáno |
| Datový slovník a vazba na XML cesty | neznámé | nezískáno |
| Číselníky s dobou platnosti | neznámé | nezískáno |
| Logické kontroly mimo XSD | neznámé | nezískáno |
| Typy podání, opravy, pravidla agregace | neznámé | nezískáno |
| Historie verzí a oficiální testovací XML | neznámé | nezískáno |

Nelze proto určit úplný seznam oficiálně povinných, podmíněných ani volitelných
údajů nebo závazné XML mapování. Níže uvedené názvy jsou **interní návrh**, nikoliv
elementy JMHZ. Nepoužíváme domnělé sazby, číselníky ani vztahy mezi základy a příjmy.
Finální XML se nevytváří. Úspěšná místní kontrola neznamená připravenost k podání.

Po zpřístupnění: z oficiálního rozcestníku dohledat technický balíček, stáhnout
všechny jeho součásti, evidovat přesné zdrojové URL, čas získání UTC, vydavatele,
verzi, účinnost od/do a SHA-256 jednotlivých souborů. Ověřit odkazy, úplnost
závislostí XSD a oficiální příklady; ruční import je rovnocenná cesta.
Hash dokládá integritu souboru, sám nedokládá jeho oficiální původ.
Teprve poté doplnit skutečné XML cesty do tabulky mapování a implementovat adaptér.

## Návrh vstupu

Základ: jeden řádek za interního zaměstnance a měsíc v jednom souboru pro jednoho
zaměstnavatele a období. Povinnost níže platí jen pro pracovní profil `draft-0`.
Nevyžaduje zatím osobní identifikátory ani jména, která nejsou pro vývoj potřebná.
Syntetický soubor je v `config/example.csv`; lze přejmenovat zdrojové sloupce.

| CSV → interní údaj | Typ | Povinnost v návrhu | Cíl JMHZ |
| --- | --- | --- | --- |
| employee_id → employee_id | text, zachovat nuly | povinný technický klíč | neověřeno; není rodné číslo |
| period → period | YYYY-MM | povinný | neověřeno |
| income → income | Decimal, max. 2 desetinná místa | povinný pro ukázkové součty | neověřeno; přesnou definici příjmu doplnit |
| social_base → social_base | Decimal, max. 2 místa | volitelný, prázdný ≠ nula | neověřeno |
| health_base → health_base | Decimal, max. 2 místa | volitelný | neověřeno, relevanci pro JMHZ potvrdit |

Příjmové položky se nesmějí bez ověření sloučit do jediné částky pro skutečné
podání. Tento minimalistický soubor slouží pro vývoj importu, ne jako konečný
export mzdového systému. Identifikátory v XLSX musí být textové buňky; mapování
číselného zdroje na identifikátor odmítá, protože ztracené počáteční nuly již nelze obnovit.

## Co jeden plochý řádek nevyřeší

| Oblast | Návrh řešení po ověření definic |
| --- | --- |
| Více pracovních vztahů zaměstnance | vedlejší tabulka vztahů s klíčem employee_id + relationship_id; neagregovat naslepo |
| Nástupy, ukončení, přerušení a změny v měsíci | tabulka událostí s intervaly a vazbou na vztah |
| Opakované dílčí příjmy a časová příslušnost | tabulka částek podle typu, vztahu a období |
| Identita zaměstnavatele a hlavička podání | samostatná konfigurace zaměstnavatele a podání |
| Zahraniční identifikace, adresy, další opakované údaje | normalizované pomocné tabulky podle skutečného slovníku |
| Opravy a vazba na dřívější podání | odložený modul P1 podle oficiálních pravidel |

Před skutečným podáním je nutné ověřit granularitu oficiálního záznamu.
Současný prototyp odmítá duplicitu employee_id + period, neřeší více vztahů.

## Kontroly a součty

Implementované technické chyby: nejednoznačné/duplicitní hlavičky, nepravidelná
šířka CSV, chybějící povinný údaj, neznámý zdroj mapování, neplatný měsíc,
nesoulad s vybraným obdobím, duplicitní klíč, neplatná/neomezená částka,
více než dvě desetinná místa. Každá chyba má řádek, klíč, pole, popis a nápravu.
Záporná částka je varování: bez metodiky nelze určit, zda jde o legitimní korekci.
Informační nález vždy připomíná neověřenou definici.

Součty: počet řádků, počet různých neprázdných zaměstnanců, počet platných a
chybných řádků, součet income/social_base/health_base přes Decimal. U každé částky
uvést počet chybějících a neplatných hodnot; částečný součet není úplný součet.
Zdrojové součty sledovat podle původních sloupců, cílové podle mapování. Rozdíl
je aritmetický údaj, ne automatická chyba (např. záměrné zaokrouhlení).
Oficiální křížové kontroly, sazby a kontrolní součty čekají na metodiku.

## Architektura a postup

`importers` zachová surové texty a čísla řádků; `mapping` vyhodnocuje pouze
deklarativní operace, bez eval; `validation` vrací strukturované nálezy;
`calculations` počítá Decimal; `definitions` eviduje obsah a rozdíly verzí;
`storage` uchovává jen profily a metadata ve SQLite; `ui` orchestruje tyto služby.
Mzdové řádky se automaticky neukládají do databáze ani do logů.

1. Nyní: bezpečný základ CSV/XLSX, profily JSON a SQLite, validace, součty,
   české UI a testy. Žádná síťová komunikace v aplikaci.
2. Po získání podkladů: úplný slovník, rozdělení XSD/metodických pravidel,
   číselníky a účinnost, přezkum návrhu CSV se skutečným exportem.
3. Adaptér konkrétní oficiální verze: pořadí a namespace XML, typy podání,
   bezpečné lokální XSD resolverové závislosti, oficiální integrační příklady.
4. Dokončit správu definic v UI, porovnání struktur a dopadů na mapování,
   uživatelské kontroly zdrojových a cílových součtů, export protokolu.
5. Windows: test spuštění a PyInstaller na Windows, ověřit čistý stroj.
   P1 a P2 až po dokončení P0.

### Pokračování 30. 10. 2026

Opakované ověření: aktivní síťová politika stále nemá přidané domény a weby
ČSSZ/MPSV vracejí CONNECT 403. Oficiální rešerše zůstává otevřená.
Nezávisle na ní je nyní implementován [ruční import samostatných XSD a jejich
strukturální porovnání v UI](definitions.md), včetně lokálního uchování bajtů,
metadat a kontroly hashů. Každý import zůstává neověřený. Tento nástroj nemění
pracovní návrh CSV ani neověřuje oficiální metodická pravidla.

## Otevřené otázky

- Kde je aktuální kompletní oficiální technický balíček a jaká je jeho účinnost?
- Jaké jsou přesné kategorie částek, klíče zaměstnance a pracovního vztahu?
- Obsahuje budoucí mzdový export více vztahů a změny uvnitř měsíce?
- Jaký bude skutečný export a očekávané kontrolní součty mzdového systému?
- Jaké typy podání má první produkční verze podporovat?

Otázky neblokují vývoj technického základu; blokují produkční XML.
