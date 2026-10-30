# Mapování pracovního profilu

Hotový výchozí profil: [mapping.draft.json](../config/mapping.draft.json).
Lze jej načíst přímo v aplikaci; jde výslovně o pracovní, neověřené mapování.

Profil má `name`, `definition_version` a slovník `rules` s interními cíli
`employee_id`, `period`, `income`, `social_base`, `health_base`.
Verze `unverified-draft-0` není verzí oficiálního JMHZ. UI jiné verze odmítá.
Vazby na oficiální XML cesty jsou **neověřené**; viz [analýza](analysis.md).

Výchozí mapování přiřadí stejně pojmenovaný CSV sloupec. V aplikaci lze upravit
JSON pravidlo u každého pole, načíst a uložit celý profil. Neznámá operace,
chybějící zdroj nebo chybějící položka v lookup vyvolá nález na daném řádku.
Nezadaná povinná cílová položka je chyba validace.

| Operace | Tvar |
| --- | --- |
| Zdrojový sloupec | `{"op":"column","name":"mzda"}` |
| Konstanta | `{"op":"constant","value":"2026-09"}` |
| Součet více zdrojů | `{"op":"add","args":[{"op":"column","name":"mzda"},{"op":"column","name":"bonus"}]}` |
| Textové spojení | `{"op":"concat","separator":"-","args":[{"op":"column","name":"a"},{"op":"column","name":"b"}]}` |
| Normalizace Decimal | `{"op":"decimal","arg":{"op":"column","name":"mzda"}}` |
| Zaokrouhlení HALF_UP na haléře | `{"op":"round","arg":{"op":"column","name":"mzda"}}` |
| Číselníkový překlad | `{"op":"lookup","arg":{"op":"column","name":"kod"},"table":{"A":"01","B":"02"}}` |
| Podmínka | `{"op":"if_equal","left":{"op":"column","name":"kod"},"right":{"op":"constant","value":"A"},"then":{"op":"constant","value":"1"},"else":{"op":"constant","value":"0"}}` |

Hodnoty konstant i výsledky lookup jsou textové. Hloubka stromu je nejvýše 20.
Částky nemají oddělovače tisíců; čárka a tečka jsou desetinné oddělovače.
Nedochází k automatickému zaokrouhlení importovaných hodnot. Datumové transformace,
oficiální číselníky a vyhodnocení účinnosti jsou další etapa po získání podkladů.
Profil nesmí obsahovat skutečné osobní údaje v konstantách ani tajné klíče.

SQLite API (`app.storage.Store`) ukládá profily parametrizovanými dotazy.
UI současně ukládá profil do zvoleného JSON a konfigurační SQLite v uživatelském
adresáři Qt AppDataLocation. Soubory nejsou šifrované; chrání je práva účtu OS.

Součty zobrazují zdroj, cíl a rozdíl pro přímé mapování sloupce. U složených pravidel
není nezávislý zdrojový kontrolní základ dosud nakonfigurován, rozdíl se proto
nevyhodnocuje. Počty chybějících a neplatných hodnot musí zůstat viditelné.
