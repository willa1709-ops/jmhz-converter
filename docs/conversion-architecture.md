# Společné jádro a platformní adaptéry

Nové `app/core/` používá minimum Python 3.8, nemá závislost na Qt ani StrEnum.
Žádný z těchto modulů se nezabývá automatickým stahováním definic. Moderní projekt
nadále vyžaduje Python 3.12 a PySide6; neinstaluje se beze změn jako celek na 3.8.

```mermaid
flowchart LR
    Input[CSV / XLSX] --> Reader[core.input]
    Reader --> Mapping[core.mapping]
    Mapping --> Checks[core.methodology: konzistence a stav]
    Checks --> XML[core.generation: verzovaný adaptér]
    XML --> XSD[core.schemas: lokální validace]
    XSD --> Result[pracovní výsledek / nálezy]
    Result --> UI[moderní GUI / CLI / budoucí Qt5 adaptér]
```

| Modul | Rozhraní a odpovědnost |
| --- | --- |
| `core.models` | datové třídy SourceRow/SourceTable, Issue, ConversionResult bez Qt |
| `core.input` | stávající logika CSV a XLSX přesunutá beze změny pravidel; moderní importery pouze adaptují staré modely |
| `core.mapping` | validovaný pracovní profil: pojmenované doménové vstupy → sloupce; přesná normalizace celočíselných částek Decimal |
| `core.methodology` | technická vstupní smlouva, shoda období a explicitní blokátory nedokončené metodiky |
| `core.generation` | skutečné QName/pořadí scénáře jinyPrijem podle konkrétních verzí; žádné UI a žádný zápis na disk |
| `core.schemas` / `core.xml_support` | původní zabezpečený parser a hashově ověřený resolver, přenositelné cesty/API pro 3.8 |
| `core.conversion` | orchestrace, samostatná XSD kontrola hlavičky a řádků, celková XSD validace, součty a neobejitelný blok finálního zápisu |
| `core.resources` | resource cesta ze zdrojů nebo PyInstaller datového adresáře |
| `core.__main__` | offline CLI, explicitní `.draft.xml`, žádný konečný export |
| `core.payroll` | číslo položky → sloupec; validovaný graf řádkových Decimal výpočtů a kontrol; bezpečný diagnostický report a CLI |
| `core.identities` | komponenty OIČ/RČ, blokování rozporů, číselné pořadí textových interních čísel, primární PP po měsících |
| `core.periods` | explicitní století, měsíc, interní revize a volitelná SQLite evidence oddělená od GUID |
| `core.payroll_conversion` | explicitní pracovní vazby číslovaných položek na původní `jinyPrijem`; nové příznaky `primarniPpv` podle skutečného XSD |
| `core.packages` | pasivní verzované ZIP mimo EXE, nezávislý pin manifestu, bezpečná instalace, kontrola souborů/API, zachování starších verzí |
| `core.organizations` | registr, profil společný/odlišný, fyzicky oddělené databáze, neměnné importy a kontroly, pořadí interních verzí a pracovní XML v organizaci |
| `core.workforce` | HPP/DPP/DPČ v lokálním modelu, požadavky identifikace/IN01 a podmíněné posouzení nulového příjmu bez vyřazování řádků |

Výchozí GUI je `ui.organizations_window`; staré `MainWindow` zůstává součástí
kontextových nástrojů. Všechny persistentní mzdové operace nového workflow
vyžadují organizaci a import/měsíc. Registry a profily neskladují mzdové řádky;
ty jsou v samostatné databázi každé organizace s kontrolou vlastníka. Interní
UUID jsou v prostoru organizace a nejsou oficiální GUID. Změna výběru v GUI
ruší náhledy a uzavírá staré kontextové nástroje.
`schemas.IdentityValidator` kontroluje skutečný typ identifikace z obou XSD,
nevytváří nové schéma JMHZ. Přípustnost IN01, párování bez klíčů, úplné
HPP/DPP/DPČ a účinnost nulových scénářů nejsou pro finální podání potvrzené.

Obecná mzdová analýza používá `prepare_payroll`; XML adaptér
`prepare_numbered_conversion` ji spustí před dosavadním převodem a při libovolném
nálezu XML nevytvoří. Původní `prepare_conversion` a jeho profily fungují nadále
bez požadavku na novou vrstvu. `primary_flags` jsou volitelné; nový adaptér je
předává pouze po jednoznačném vyřešení všech PP. Finální zápis zůstává blokovaný.

Původní veřejná rozhraní `app.importers`, `app.xml` a `app.xml.bundle` zůstala
zachována tenkými adaptéry. Přesun je cílený kvůli sdílení a kompatibilitě:
StrEnum z původních UI modelů se do jádra nedostává, Path.is_relative_to je
nahrazeno ekvivalentem dostupným v 3.8, anotace jsou odložené. Resolver nyní
správně převádí Windows file URI včetně mezer a nadále odmítá UNC/síťové cesty.

Moderní UI nový převod volá přes `prepare_conversion`, bez duplikace XML/částkových
pravidel. Budoucí Qt5 adaptér musí použít totéž API. Není správné jen zaměnit
import PySide6 za PySide2 v celé aplikaci: liší se enumy/API a původní moduly
nadále používají novější Python. Přechod legacy UI je samostatná další etapa.

Testy jádra lze spustit bez PySide obou generací:

```text
python -m pytest -q tests/test_conversion_core.py tests/test_numbered_payroll.py tests/test_organizations.py
```

Úspěch na Linux Python 3.8 + lxml 5.3.2 a moderním Pythonu dokládá kompatibilitu
jádra, nikoliv schopnost načíst Windows DLL nebo splnění metodiky JMHZ.
V odděleném 3.8 prostředí byly použity lxml 5.3.2, openpyxl 3.1.5 a pytest 7.4.4;
moderní prostředí a jeho uzamčené závislosti zůstávají oddělené.
