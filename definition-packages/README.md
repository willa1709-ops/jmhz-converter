# Pracovní offline balíček k přezkumu

[`working-payroll-2027-1.0.zip`](working-payroll-2027-1.0.zip) obsahuje profil
číslovaných položek, explicitní pracovní vazby na `jinyPrijem` 2027 a runtime
obou dodaných XSD sad včetně jejich evidenčních metadat. Neobsahuje mzdové řádky,
osobní údaje ani spustitelný kód. Je vytvořen příkazem popsaným v
[postupu balíčků](../docs/offline-definition-packages.md).

**Stav: pracovní šablona vyžadující přezkum, nikoliv schválené mzdové mapování.**
Čísla 100/110/120/190/200, vzorec i vazby na částky XML jsou ilustrativní;
nemají doložený vztah ke skutečnému exportu. Původ a účinnost podkladů zůstávají
neověřené. Finální XML export je blokovaný. Nepoužívat k podání.

Výstup builderu pro kontrolu reprodukovatelnosti:

| Údaj | Hodnota |
| --- | --- |
| ID / verze | `working-payroll` / `1.0` |
| SHA-256 manifestu | `41a6a01f0b5d22f9909ac259f71faed287290437ee83925c9c94697dbe2f672f` |
| SHA-256 ZIPu | `48446fddebfc4423999cfd3cddc5fa0b25f4026dea43e1c68178a3a0f8ff2005` |

Tyto hashe jsou **kandidát k nezávislému schválení**. Jejich přítomnost v tomto
README neznamená přezkum vydavatele nebo metodiky. Před použitím na skutečných
datech nahradit zástupné mapování, zvýšit verzi a schválit obsah i pin mimo ZIP.
Loader žádné schválení z README automaticky nenačítá.

## Šablona pro organizační workflow

[`working-workforce-1.0.zip`](working-workforce-1.0.zip) přidává oproti starší
šabloně profil vstupů HPP/DPP/DPČ, alternativní identifikační údaje, stav
registrace, práci a příjem a identifikaci zaměstnavatele v souboru. Obsahuje
obě XSD runtime sady, ale **žádný nový XML generátor**. Původní balíček zůstává
nezměněný. Zástupná čísla položek a vzorec stále vyžadují skutečný mzdový export.

| Údaj | Kandidát k nezávislému schválení |
| --- | --- |
| SHA-256 manifestu | `541b7563f0146a4edcba889ac6aa1e9a3c83d48088f5c4df095729a9d72dbfab` |
| SHA-256 ZIPu | `21a29ddd6901098ebf9e9a82191cfd64ca0a155956846d2a82ae4083e32c7ea4` |

Vytvoření: `python -m app.core.packages build --profile config/payroll/workforce.template.json --package-id working-workforce --version 1.0 --official-root schemas/official --output working-workforce-1.0.zip`.
Nová metadata a organizační služba vyžadují tuto verzi aplikace; starší EXE
neznámá metadata bezpečně odmítne. Následné změny podporovaných čísel položek,
sloupců a vzorců lze distribuovat novou verzí balíčku bez další změny EXE.
