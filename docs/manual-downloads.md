# Podklady k ručnímu stažení – JMHZ

Stav k 30. 10. 2026: kvůli síťové politice nebyly weby institucí v této relaci
přístupné. **Přesné názvy aktuálních souborů, přímé adresy ke stažení a verze nejsou
ověřené.** Níže jsou popisy hledaných dokumentů, nikoliv vymyšlené oficiální názvy.

Známé vstupní adresy institucí (nikoliv ověřené odkazy na konkrétní balíčky):

- ČSSZ: https://www.cssz.cz/
- ePortál ČSSZ: https://eportal.cssz.cz/
- MPSV: https://www.mpsv.cz/
- Kandidátní rozcestník JMHZ: https://jmhz.mpsv.cz/ — dostupnost zde neověřena.

Na oficiálním webu vyhledejte JMHZ / Jednotné měsíční hlášení zaměstnavatele a
technické podklady pro dodavatele mzdových systémů. Zkontrolujte, že odkazy vedou
na dokumenty publikované příslušnou institucí, a uložte i odkaz na stránku vydání.

| Co stáhnout (popis) | Přesný název / přímá URL | K čemu je potřeba |
| --- | --- | --- |
| Aktuální kompletní balíček XSD pro měsíční hlášení, včetně všech include/import | zatím neznámé | namespace, struktura, pořadí, typy, povinnost dle XSD |
| Datový slovník / technický popis položek měsíčního hlášení | zatím neznámé | význam polí a skutečná CSV → JMHZ vazba |
| Úplné číselníky k příslušné verzi | zatím neznámé | dovolené kódy, názvy, účinnost a podmíněná platnost |
| Metodika vyplnění měsíčního hlášení | zatím neznámé | podmínky povinnosti a věcné vazby mimo XSD |
| Seznam logických kontrol, chybových kódů a kontrolních vazeb | zatím neznámé | další validace a kontrolní součty |
| Popis standardního měsíčního podání a hlavičky/identifikace | zatím neznámé | zaměstnavatel, období, granularita zaměstnance a vztahů |
| Přehled vydání, změnové listy a účinnost jednotlivých verzí | zatím neznámé | výběr správné definice pro vykazovaný měsíc |
| Oficiální anonymizované testovací XML, příklady a očekávané výsledky | zatím neznámé | integrační testy generátoru a validátoru |

Stáhněte stávající verzi a pokud možno také předchozí verzi pro porovnání.
U každého souboru poznamenejte skutečný název, přesnou zdrojovou URL, datum
stažení, deklarovanou verzi a účinnost. SHA-256 dopočítá registr dokumentů.
Vydání, zdroj a obsah musí někdo věcně přezkoumat; úspěch parseru nestačí.
Není potřeba stahovat nebo připravovat opravná hlášení či registrace pro tento úkol.

## Když je číselník/metodika pouze v jiném formátu

CSV číselníky lze importovat jako UTF-8 tabulky s hlavičkou. U XLSX nebo PDF
číselníku uchovejte originál; jeho převod do CSV je odvozený dokument a musí mít
vlastní hash, vazbu na originál a přezkum. Takový převod se nesmí vydávat za originál.
Metodiky PDF lze archivovat; jejich textová interpretace a vykonávání pravidel
nejsou automatické. JSON pravidla se zatím pouze evidují a porovnávají, nespouštějí.

Kromě oficiálních dokumentů potřebujeme **syntetický vzorek skutečného mzdového
exportu**, včetně informace o více pracovních vztazích, definici částek a očekávaných
součtech. Pro základ importu není nutné poskytovat skutečné osobní údaje.
