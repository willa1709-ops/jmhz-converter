# CSV/XLSX → pracovní JMHZ XML: první implementovaný scénář

Tato etapa po PR #2 implementuje **jinyPrijem pro činnosti 11, 13, 14** v
balíčcích `jmhz-1.4.3.6` a `jmhz-1.5.0.3`. Nejde o automatické řešení běžných
pracovních poměrů ani dokončené P0. Volba scénáře je výslovná, nepředpokládá se
podle částky nebo názvu zaměstnance. Identifikace v této větvi je pouze IK MPSV + ID PPV.

## Doložení XML adaptéru

- Oba `formJinyPrijem.xsd` výslovně uvádějí činnosti 11, 13, 14 a posloupnost
  identifikace, volitelná souhrnná data, příjem. Souhrnná data zatím neimplementujeme.
- Identifikace obsahuje `ikMpsv` (ID 10051) a `idPpv` (ID 10228), dle skutečné
  alternativy identifikace v `formCommonTypes.xsd`. Alternativa jméno/datum narození
  je ve schématu, ale tento pracovní profil ji ještě nepodporuje.
- Hlavička podání odpovídá `jmhzPodani.xsd`, hlavička formuláře jeho verzi a
  `form.xsd`. Implementováno je pouze řádné podání/formulář `R`.
- U 1.4.3.6 se generuje `formulareOsob/formularOsoby`, hlavička v namespace
  podání a payload ve form/1.0. U 1.5.0.3 je obálka `formulareZamestnani`,
  formulář i jeho hlavička ve form/2027. Namespace, pořadí a platnost ověřují skutečná XSD.
- ID 10535 je ve starém XML `prijem.dan.zakladDane`, v novém
  `prijem.dan.prijem`. Nový dan blok vyžaduje také `prijemPar6` (ID 10555).
  Stejné ID mezi verzemi samo nezaručuje stejný význam částky ve mzdovém exportu.
- Cílové typy uvedených částek jsou nezáporná celá čísla do 14 číslic.
  Používá se Decimal, nikoli float ani automatické zaokrouhlení. `123,00` lze
  přesně normalizovat na `123`; `123,45` se odmítne, nikoli změní na jinou částku.
- Atribut XML `verze` přebírá skutečné `XSD/@version`: u starého balíčku `1.4.3`,
  ač jeho historie obsahuje patch 1.4.3.6; u nového `1.5.0.3`. Rozpor se neskrývá.

Zdroje: [balíčky a hashe](../schemas/official/bundles.json),
[strojový podklad se zdrojovými buňkami](../schemas/official/analysis/mapping-evidence-2027.json),
[účinnost a zjištěné rozpory](official-comparison.md). Původ a účinnost celých sad
stále vyžadují přezkum. Žádná implementovaná cesta nepotvrzuje připravenost k podání.

## Potřebné sloupce: k potvrzení podle skutečného exportu

Pracovní profil očekává jeden řádek za **PPV a měsíc**, ne sloučenou částku za
více vztahů zaměstnance. CSV z mzdového systému zatím nebylo dodáno; názvy
zdrojových sloupců níže jsou návrh a lze je přemapovat v JSON profilu.

| Sloupec | Obsah a oficiální vazba | Je nutné doplnit / potvrdit |
| --- | --- | --- |
| `form_id` | skutečný GUID formuláře, ID 10012 | kde vzniká a jak se udržuje identita formuláře; nevyplňuje se testovacím GUID |
| `period` | YYYY-MM, kontrola shody s hlavičkou | který exportní sloupec určuje vykazované období |
| `activity_code` | skutečný druh činnosti, pro tento profil 11/13/14 | zda export skutečně obsahuje tento scénář; není dovoleno přepsat běžný pracovní poměr na 11 |
| `ik_mpsv` | desetimístný textový identifikátor, ID 10051 | dostupnost v exportu a validita; tato etapa neimplementuje jeho metodické ověření modulo 11 |
| `id_ppv` | textový identifikátor zaměstnání, 1–22 číslic, ID 10228 | rozlišení více PPV; nesmí se zaměnit za interní employee_id |
| `tax_income_10535` | částka konkrétního atributu ID 10535 | přesný zdroj a význam částky podle verze, nikoli automaticky původní obecné income |
| `tax_income_10555` | příjem dle § 6 odst. 4, ID 10555 | povinný vstup tohoto profilu pouze pro 2027, včetně výslovné nuly, pokud je skutečně správná |

Povinnost `tax_income_10535` ve starém **pracovním profilu** je vstupní smlouva
tohoto omezeného převodu, nikoli tvrzení, že všechny větve starého XSD jej vždy
vyžadují. Prázdná hodnota se nikdy nepovažuje za nulu. Každé nezadané pole musí
opravit export nebo uživatel na základě skutečných údajů. Identifikátory jsou text,
v XLSX se jejich číselný původ odmítá i při přejmenování zdrojového sloupce.

Současně potřebujeme konfiguraci společnou pro podání:

| Klíč JSON | Co dodat |
| --- | --- |
| `submission_id` | skutečný GUID podání, ID 10001 |
| `employer_variable_symbol` | desetimístný VS zaměstnavatele jako text, ID 10221 |
| `year`, `month` | skutečné období, ID 10011 a 10010; shoda všech řádků |
| `filled_at` | skutečný čas vyplnění ISO 8601, ID 10005; nic se nedoplňuje systémovým časem bez zadání |

`config/conversion/parameters.template.json` má proto hodnoty **null** a CSV
šablony obsahují pouze hlavičky. Syntetické mzdy/identifikátory jsou výhradně
v automatizovaných testech, nikoliv v připravené uživatelské konfiguraci.

## Spuštění

Vyplňte kopii parametrů, připravte vlastní CSV podle skutečného exportu a případně
přejmenujte zdrojové sloupce v kopii profilu. Profil neobsahuje libovolné XML
cesty nebo spustitelné výrazy. Původní `config/mapping.draft.json` zůstává pro
původní pětisloupcový prototyp; není novým profilem oficiálního konverzního scénáře.

```bash
.venv/bin/python -m app.core VLASTNI_CSV --profile config/conversion/jiny-prijem-2027.json --parameters VLASTNI_PARAMETRY_JSON
```

Pro starou sadu zvolte `jiny-prijem-2026.json`. Pro výslovné uložení pouze
pracovního souboru přidejte `--draft-output CESTA.draft.xml`. Existující soubor se
nepřepíše. CLI přijímá i `.xlsx` přes stejný společný importer; ostatní vstupy
čte jako CSV. Funguje bez Qt a bez internetu; výchozí XSD najde v checkoutu nebo
PyInstaller datovém adresáři. Nezávisí na pracovním adresáři. Cestu lze výslovně
změnit `--official-root`. Kód 0 znamená technicky platné pracovní XML, nikoli podání;
1 jsou nálezy dat, 2 chyba vstupu/konfigurace/prostředí.

V moderním UI načtěte CSV/XLSX, na kartě **Generování XML** zvolte tlačítko
pracovního převodu a vyberte konverzní profil a parametry. Výstup je pouze náhled.
Používá vlastní konverzní profil; původní Kontrola dat/Mapování zůstávají
pětisloupcovým prototypem. Provedením neplatného převodu nebo načtením nového
souboru se předchozí pracovní XML zneplatní.

## Přesný stav ověření a zbylé blokátory

Vstupní kontroly hlídají chybějící sloupce/hodnoty, období, podporovaný scénář,
textové identifikátory, částky, duplicitu v pracovní zakázce a limit 1500 formulářů.
Neimplementuje se automatické dělení do balíků. Struktura i skalární typy se
ověřují proti skutečnému celému XSD, včetně samostatné kontroly hlavičky a každého
zdrojového řádku. Nálezy vracejí řádek, pole, kód, popis a nápravu bez soukromých hodnot.

Úplná metodika není hotová: chybí modulo 11, souhrnná/pojistná část, další scénáře,
podmínky číselníků, agregační pravidla a potvrzení skutečného mzdového mapování.
Povinnosti mimo XSD se neodhadují. Výsledek proto vždy uvádí
`methodological_validation=incomplete`, `official_origin=unverified`,
`submission_ready=false`. `export_final` vždy odmítá zápis, i kdyby někdo změnil
výsledný příznak. Samotné úspěšné XSD nikdy finální export neodemkne.

Jádro je otestovatelné samostatně pod Pythonem 3.8; to neprokazuje Win7 x86 GUI
nebo EXE. Viz [návrh legacy varianty](windows7-design.md) a
[kandidátní sestavení](../packaging/windows7/README.md).
