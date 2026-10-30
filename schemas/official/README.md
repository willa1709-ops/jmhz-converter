# Ručně získané oficiální podklady

Tato složka je připravená pro skutečné dokumenty ČSSZ/MPSV. **Žádné oficiální
schéma zatím nebylo získáno.** Prázdný manifest není ověřenou definicí.
Syntetická testovací schémata do této složky nepatří.

Ukládejte celé balíčky po verzích do vlastních podadresářů, se zachováním relativních
cest XSD závislostí. Starší soubory nepřepisujte. Do složky nevkládejte mzdová data.
Seznam potřebných podkladů: [ruční stažení](../../docs/manual-downloads.md).

Po vložení každého dokumentu ho registrujte z kořene projektu:

```text
python -m app.definitions.catalog register schemas/official/VERZE/SOUBOR.xsd --kind xsd --version SKUTECNA_VERZE --source PRESNE_HTTPS_URL
python -m app.definitions.catalog verify
```

Velká písmena jsou zástupné hodnoty, nikoliv skutečné názvy nebo verze JMHZ.
Volitelně přidejte `--effective-from YYYY-MM-DD` a `--effective-until YYYY-MM-DD`
pouze pokud jsou účinnosti doloženy. Pro CSV číselník použijte `--kind codelist`,
pro metodický dokument `--kind methodology` (PDF, TXT, MD nebo JSON).
Na Windows použijte `.venv\Scripts\python`, v cloudu `.venv/bin/python`.

`manifest.json` eviduje relativní soubor, typ, verzi, zdroj, čas získání při
registraci UTC, účinnost, SHA-256 a oddělené výsledky:

- `status` a `origin_review.status`: původ je po importu vždy `unverified`.
  Pole reviewer/reviewed_at/evidence jsou připravena pro doložený lidský přezkum;
  aplikace oficiální původ sama nepotvrzuje a ruční změna JSON neodblokuje XML.
- `technical_status`: technický výsledek parseru. `standalone_xsd_valid` znamená
  úspěšnou kompilaci samostatného XSD 1.0; `dependencies_unchecked` pouze načtení
  XML struktury XSD se závislostmi, bez kompilace celého balíčku.
- `csv_parsed`, `json_parsed`, `text_decoded`: načtení formátu, nikoliv správnost
  nebo účinnost obsahu. PDF má `retained_only`: uložení a hash, bez validace PDF.

Nástroj uchovává také lokální archiv v ignorované `.catalog.sqlite3`. Manifest
umožňuje nezávislou kontrolu souborů; nikdy nevytváří ani nepřepisuje zdrojová XSD.
Soubor se nesmí mezi načtením a registrací měnit. Import nepřenáší žádná data na síť.
Úplnost XSD závislostí, oficiální původ a metodická pravidla se ověřují samostatně.
