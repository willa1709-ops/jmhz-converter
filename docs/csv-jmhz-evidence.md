# Podklad CSV → JMHZ XML z dodaných dokumentů

Toto je **pracovní podklad**, nikoliv aktivní produkční mapovací profil.
Originály a jejich verze shrnuje [porovnání](official-comparison.md).
Strojově čitelné podklady jsou v `schemas/official/analysis/`:

- `dictionary-2026.json` a `dictionary-2027.json`: všechny ID, původní názvy,
  texty a vzorce, list a buňky slovníku. Vzorce jsou inertní text.
- `controls-*.json`: kontroly s ID, zdrojovými buňkami, popisem, propustností,
  chybovou zprávou a případnými nevyhodnocenými vzorci.
- `interactions-*.json`, `parameters-*.json`, `codelists-*.json`: interakce,
  parametrické konstanty včetně období v hlavičkách a obsah číselníkových listů.
- `xsd-elements-*.json`: skutečné deklarace elementů, soubor, řádek, typ,
  min/maxOccurs a ID nalezená v dokumentaci XSD. Počet ID není počet vstupních CSV polí.
- `mapping-evidence-*.json`: spojení podle ID atributu pro řádky označené MĚSÍČNÍ:
  přesný text sloupce XSD MAPOVÁNÍ MH, zdrojová buňka, číselník, ID souvisejících
  kontrol a nalezené XSD deklarace. Je to důkazní index, nikoliv generátor XML cest.

Index propojuje dokumentovaná ID u 228 z 234 měsíčních atributů starší sady a
239 z 245 nové. Zbývajících šest položek jsou metadatové atributy bez uvedené
vstupní XML cesty: 10006, 10017–10020, 10470. Nesmějí se z nich vymyslet elementy.
Shoda ID dokládá společný odkaz dokumentů, nikoliv automaticky správný kontext
formuláře nebo povinnost pro každý pracovní vztah.

## Dopad na dnešní pracovní CSV

| Dnešní sloupec | Doložený kandidát / skutečná položka | Co je ještě nutné rozhodnout |
| --- | --- | --- |
| `employee_id` | interní klíč zdroje; žádná přímá oficiální XML položka se zde nepotvrzuje | oddělit osobu, pracovní vztah a identifikátory formuláře; nezaměnit za ID PPV, rodné číslo nebo GUID |
| `period` | slovník ID 10010 Měsíc → `hlavicka.mesic`, ID 10011 Rok → `hlavicka.rok` | explicitní rozdělení YYYY-MM; jde o hlavičku podání, nikoliv opakovanou libovolnou položku zaměstnance |
| `income` | není jednoznačný; např. ID 10286 má cestu `souhrnDataZec.prijmy.zuctovanoCelkem`, nové ID 10555 `prijem.dan.prijemPar6` | vysvětlit, co skutečný mzdový export částkou myslí; nezaměnit agregovaný příjem za konkrétní daňovou kategorii PPV |
| `social_base` | kandidát ID 10477 → `pojisteni.vymerovaciZaklad.castkaOdvodPojistneho` | potvrdit význam a úroveň PPV vs zaměstnanec; další základ ID 10478 má jiný účel a jinou cestu |
| `health_base` | dnešní pracovní součet; přímé mapování nepotvrzeno | nezaměnit zdravotní základ za ID 10371 Zdravotní pojištění, které reprezentuje jiný údaj |

Další doložené hlavičkové pole: ID 10221 Variabilní symbol →
`hlavicka.variabilniSymbol`; jeho hodnota musí přijít ze samostatné konfigurace
zaměstnavatele. Příkladné cesty výše jsou doslovným obsahem slovníku; úplné
kořenové cesty, namespace, formulářové kontexty a pořadí musí řešit adaptér
konkrétní XSD verze. Nelze je získat prostým spojením těchto textů tečkou.

Pokyny obou sad byly převedeny pomocí pdftotext na prohledávatelný text v
`analysis/` s původními oddělovači stran. Lze tak dohledat pravidlo k ID z
indexu, ale jeho lidská interpretace a implementace musí být samostatně
otestována. Revize PDF se uchovává vedle čistého dokumentu, ne jako nový zdroj pravdy.

## Co potřebujeme od mzdového exportu

Potvrdit slovní význam a granularitu všech částek, identifikaci více PPV,
zdroj zaměstnavatelské hlavičky a očekávané součty na syntetickém vzorku.
Jeden řádek za zaměstnance a měsíc může být prezentační pohled, ale pro různé
vztahy a opakované bloky XML vyžaduje doplňkové tabulky nebo jednoznačné rozšíření
formátu. Agregace bez metodiky by ztrácela údaje.

V této etapě se nemění `config/mapping.draft.json` ani se neaktivují vzorce z
metodik. Následující implementace musí mít vlastníky pravidel, odkazy na buňky/
strany dokumentace, doloženou účinnost a testy pozitivních i negativních případů.
