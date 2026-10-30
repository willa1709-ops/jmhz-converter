# Číslované mzdové položky, pracovní poměry a interní revize

Obecné jádro je nezávislé na XML i Qt. Jeden řádek znamená **jeden pracovní
poměr za jeden měsíc**. Dva PP téže osoby mají dvě vlastní interní čísla.
Příjmy se mezi těmito řádky neslévají. Následující profil je pracovní smlouva
aplikace, nikoliv definice JMHZ nebo potvrzený formát mzdového systému.

## Návrh vstupních sloupců

Hlavička bez smyšlených mzdových hodnot je v
[`numbered.headers.csv`](../config/payroll/numbered.headers.csv).
Názvy skutečného exportu se nastavují v
[`numbered.template.json`](../config/payroll/numbered.template.json).

| Sloupec šablony | Význam a co musí být potvrzeno |
| --- | --- |
| `internal_number` | Interní číslo konkrétního PP jako text číslic. Úvodní nuly se uchovají. Potvrdit rozsah a jedinečnost u zaměstnavatele. |
| `period` | Měsíc `26-09` nebo `2026-09`. Profil výslovně nastavuje století 2000 pro zkrácený rok. |
| `oic` | OIČ jako text, pokud ho export poskytuje. Pracovní strukturální kontrola očekává deset číslic. |
| `rc` | RČ jako text, pokud je dostupné; devět/deset číslic, volitelně lomítko za šestou číslicí. Nejde o potvrzení platnosti RČ. |
| `p100`, `p110`, `p120` | Zástupné zdrojové mzdové položky pro ukázku výpočtu. **Dodat skutečná čísla položek, jejich názvy a význam.** |
| `p190` | Zástupná exportovaná kontrolní částka tohoto řádku. Pokud taková položka neexistuje, odstraňte její kontrolu i mapování. |
| `p200` | Zástupná další částka pro pracovní adaptér 2027; skutečný zdroj je nutné určit. |
| `form_id` | Pouze pro pracovní XML: skutečné GUID formuláře, pravidla jeho tvorby/opakování musí být přezkoumána. |
| `id_ppv` | Pouze pro pracovní XML: skutečný identifikátor PPV; nelze ho bez doloženého pravidla zaměnit za interní číslo. |
| `activity_code` | Pouze pro pracovní XML: skutečný druh činnosti; dosavadní adaptér pokrývá jen `jinyPrijem` 11/13/14. |

Pro obecné výpočty nemusí profil obsahovat poslední tři XML údaje ani `p200`.
Musí obsahovat interní číslo, období a zdroj alespoň jednoho osobního identifikátoru.
Je-li v profilu uveden zdrojový sloupec, musí být v souboru přítomen; jeho buňka
může být prázdná, pokud ji příslušná funkce nepotřebuje. Chybějící OIČ i RČ
znamená chybu párování. Finanční vstup požadovaný výpočtem nebo kontrolou nesmí
být prázdný. Nepoužité položky se automaticky neinterpretují jako peníze.

OIČ, RČ, interní číslo i PPV musejí být v XLSX textové už před uložením.
Číselné buňky identifikátorů jsou odmítnuty. Aplikace neumí rekonstruovat nuly
nebo přesnost ztracenou v Excelu. Vzorce v XLSX se nevyhodnocují.

## Párování a primární PP

Stejné OIČ nebo stejné normalizované RČ propojí řádky do skupiny. Pokud libovolná
část propojené skupiny obsahuje více různých OIČ nebo více různých RČ, celá
skupina je chybná a nemá přiřazený primární PP. Kontrola proběhne před přidělením
skupin, včetně nepřímého propojení přes další řádky. Chybějící vazba mezi samotným
OIČ na jednom řádku a samotným RČ na jiném se nikdy nedovozuje odhadem.

Interní čísla se porovnávají číselně bez převodu identifikátoru na číslo:
`0002` je nižší než `10`, původní zápis zůstává. Dvě nejnižší čísla `001` a `1`
jsou nerozhodná; aplikace oznámí chybu, nerozhoduje počtem nul ani pořadím řádků.
Duplicitní shodné interní číslo v jednom měsíci blokuje dotčené skupiny.
Primární PP se pro nové období vypočte znovu z dodaných PP. **Export musí obsahovat
všechny PP dané osoby, které mají vstoupit do porovnání**; aplikace nezná vynechané PP.
Bez úplného exportu nelze potvrdit skutečný primární PP.

Skupiny `person-N` jsou pouze dočasná označení v rámci běhu, nikoliv uložená
identita nebo GUID. Strukturální kontrola klíčů nepotvrzuje totožnost, datum
narození, kontrolní číslici ani registraci osoby u úřadu.

## Výpočty a mapování

Číslo položky je textový klíč, například `"100"`; `"001"` a `"1"` jsou odlišné
položky. Profil přiřadí klíči libovolný skutečný název sloupce:

```json
{"items": {"100": {"column": "skutecna_hlavicka_exportu"}}}
```

Úplný profil musí mít všechny klíče jako dodaná šablona. Metadata lze číst
také přes `{"item":"100"}`, pokud export čísluje i identifikační údaje.
Identifikační sloupce OIČ/RČ nesmějí být finančním vstupem ani kontrolním součtem.

Výrazy podporují jen `item`, `calculation`, `add` a `subtract`. Odečítání je
první argument minus všechny další. Odkazy na jiné výpočty tvoří acyklický graf,
všechny listy čtou **tentýž řádek**. Nespouští se Python, makra ani textové výrazy.
Šablona ukazuje `(100 + 110) - 120`, kontrolované proti 190 s nulovou tolerancí.
**Čísla, vzorec ani vazba na položku XML 10535 nejsou potvrzené údaje mzdového
systému ani metodické pravidlo JMHZ.** Nahraďte je po ověření skutečného exportu.

Částky se čtou jako konečné desetinné hodnoty s čárkou nebo tečkou, nejvýše
32 číslic před a 8 za oddělovačem; bez oddělovačů tisíců a exponentu. Výpočet
používá `Decimal` s vlastní přesností a odmítá ztrátu přesnosti. Neprovádí
skryté zaokrouhlení ani nahrazení chybějící hodnoty nulou. Tolerance kontroly je
explicitní nezáporná částka. Jde o technické limity aplikace, nikoliv XSD pravidla.
Pracovní adaptér `jinyPrijem` nadále vyžaduje částky v přesnosti svého skutečného
XSD; obecný výsledek s desetinnou částí tedy může být pro tento adaptér odmítnut.

## Období, interní pořadí a GUID

`SubmissionContext` obsahuje měsíc a nezáporný `revision_index`: 0 je interní
řádná verze, 1 první další verze atd. Změna kontextu v dialogu zruší starý výsledek.
Volitelná `RevisionRegistry` eviduje pouze neosobní alias zaměstnavatele, měsíc,
pořadí, druh/hash definice a čas. Pořadí navazuje od nuly samostatně pro každý
alias a měsíc; přepis nebo přeskočení revize je odmítnuto. Analýza sama nic do
historie nezapisuje, zápis se vyžádá výslovně CLI parametrem.

Tato evidence nepotvrzuje odeslání/přijetí podání. Netvoří a neuchovává oficiální
GUID. Interní revize se nepromítá do typu JMHZ ani do změny/recyklace GUID.
Dosavadní pracovní XML adaptér zůstává u `typPodani=R` a explicitně dodaných GUID;
ani revize 1 z něho nedělá opravné podání. Opravná podání a registrace nejsou
implementované. Pro produkční použití je nutné doložit pravidla životního cyklu
podání a formulářů podle metodiky.

## Použití

V moderním GUI načtěte CSV/XLSX a na kartě Mapování otevřete **Číslované položky,
řádkové součty a primární PP**. Načtěte pracovní JSON nebo offline ZIP se samostatně
schváleným hashem manifestu, nastavte měsíc a interní revizi a spusťte kontrolu.
GUI nyní provádí obecnou analýzu; nový převod číslovaných položek na pracovní XML
je dostupný přes společné API a CLI. Původní XML náhled v hlavním okně je zachován.

```text
python -m app.core.payroll skutecny-export.csv --profile config/payroll/numbered.template.json --period 26-09 --revision 0
```

Volitelně přidejte `--record-revision local/jobs.sqlite3 --scope employer_a`.
Záznam se pořídí jen po úspěšné kontrole. `scope` má být neosobní alias, nikoliv
OIČ, RČ či jméno. Přepnutí měsíce vytvoří vlastní řadu od nuly. JSON diagnostika
obsahuje jen řádky, neprůhledné skupiny, příznaky a chyby, nikoliv osobní klíče
nebo částky. Identifikátory zůstávají v paměti pro párování; explicitní pracovní
XML obsahuje údaje nezbytné pro XML, není bezpečným diagnostickým logem.

Postup balíčků a pracovního XML je v [offline definicích](offline-definition-packages.md).
Finální XML export je nadále blokovaný v jádře i UI.

## Co dodat ze skutečného mzdového systému

1. Anonymizovaný strukturálně věrný export CSV/XLSX s více PP jedné osoby,
   hlavičkami, oddělovačem, kódováním a typy buněk. Při anonymizaci zachovat
   shody/rozpory identifikátorů a úvodní nuly; nedodávat skutečná RČ do GitHubu.
2. Význam a skutečná čísla mzdových položek, přesné vzorce, znaménka, měnu,
   jednotky, zaokrouhlování a význam prázdné/nulové hodnoty. Označit kontrolní
   částky exportu a zda představují řádek, osobu nebo celý soubor.
3. Potvrzení, že soubor obsahuje všechny relevantní PP za měsíc; definici
   jedinečnosti interního čísla a vztah interního čísla k oficiálnímu PPV.
4. Dostupnost OIČ/RČ a doložené pravidlo jejich vazby; skutečný zdroj a životní
   cyklus GUID, kódy činností a údaje hlavičky zaměstnavatele.
5. Schválenou vazbu skutečných položek na oficiální datový slovník a metodiku,
   přezkum původu/účinnosti XSD a referenční správný výstup ke srovnání.

Bez těchto podkladů lze prokázat technické chování obecné vrstvy a XSD shodu
syntetického pracovního XML, nikoliv věcnou správnost mzdového podání.
