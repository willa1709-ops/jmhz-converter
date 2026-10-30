# Dodané podklady JMHZ: inventura, účinnost a rozdíly

Navazující etapa po sloučení PR #2 přidává omezený pracovní převod zaměstnaneckého
formuláře `jinyPrijem`; viz [aktuální konverze a zbylé blokátory](conversion-stage.md).
Níže je zachovaný report příjmu podkladů, nikoliv tvrzení o dokončeném P0.

Kontrola dodávky z `main` (`4e47731`) dne 30. 10. 2026. Původní složky `2026`
a `2027` jsou **označením dodávky**, nikoliv automatickým důkazem účinnosti.
Původ dokumentů zůstává neověřený; obsah byl přečten z lokálně dodaných souborů.

## Inventura a původ

- 13 originálů: 6 XLSX, 4 PDF, 3 ZIP. Všechny byly prohlédnuty; README nejsou
  datové definice. Původní názvy a hashe jsou v [intake.json](../schemas/official/intake.json).
- URL v názvu byla převedena na bezpečný ASCII název souboru. Bajty originálů
  se nezměnily: SHA-256 před/po je shodné u všech 13 souborů. URL jsou rekonstruované
  z nahraných názvů, nikoliv potvrzené novým stažením. Datum původního stažení není známo.
- 3 ZIPy a 1 vnořený ZIP byly zkontrolovány včetně CRC a bezpečně rozbaleny.
  [extraction.json](../schemas/official/extraction.json) eviduje každý člen,
  jeho velikost, hash a cestu. AppleDouble `__MACOSX/._*` není považováno za XSD.
- Do verzovaného úložiště se publikovalo 42 XSD a vnořený ZIP se zachováním
  interních cest. Všechny obrázky, HTML, DOCX a příklady protokolů jsou zachovány
  v originálních ZIPech a plně rozbaleny v ignorované `local/official-extracted/`;
  neprovádí se jejich spuštění ani automatické otevření.
- [manifest.json](../schemas/official/manifest.json) obsahuje 56 registrovaných
  položek. Ověření kontroluje hashe, nikoliv oficiální původ nebo úplnost práva.
  Git atributy zachovávají bajty těchto souborů také při checkoutu na Windows.

## Skutečně nalezené verze a data

| Podklad | Dodávka 2026 | Dodávka 2027 | Důkaz a omezení |
| --- | --- | --- | --- |
| XSD balíček podání | 1.4.3.6 | 1.5.0.3 | historie v externím `jmhzPodani.xsd`: 03.08.2026 / 12.10.2026. Jsou to data změn, ne potvrzené počátky účinnosti. Staré XSD má stále `@version="1.4.3"`, patch 1.4.3.6 je v historii; oba údaje se uchovávají. |
| Datový slovník | 1.4.1.6 | 1.5.0.3 | list Verze!A8:B8 uvádí 29.5.2026; nová verze A12:B12 uvádí 14.10.2026. Datum publikace není účinnost. Nový slovník navíc v historii uvádí pro stejné starší vydání 1.4.1.6 datum 12.6.2026: rozpor není opravován odhadem. |
| Katalog kontrol | 1.4.2.11 | 1.5.0.4 | Titulní strana!B9. Katalog obsahuje historické změny i parametrické konstanty podle měsíců; nesmí se přidělit jednotná sazba pouze podle verze sešitu. |
| Datové scénáře | 1.4.0.2 | 1.5.0.3 | Verze!A3:B3 = 9.3.2026 / A7:B7 = 14.10.2026; data publikace. |
| Pokyny MH | 1.4.14 + samostatný soubor s revizemi | 1.5 | titulní strana výslovně „Platné pro období od 1.7.2025“ / „Platné pro období od 1.1.2027“. Tato deklarovaná účinnost je zapsaná u příslušných PDF, nikoliv automaticky u celé sady. |
| Pravidla podání a související procesy | 1.4.6 | nedodáno samostatné vydání | verze na titulní straně. Účinnost celého dokumentu nepotvrzena; obsah zahrnuje i témata mimo aktuální rozsah. |
| Protokoly MH | nedodáno | 1.5 | názvy uvnitř ZIP včetně DOCX. Jde o formát výsledkového protokolu, **ne** o vstupní XSD podání a **ne** o použitelný integrační příklad správného podání. |

PDF s revizemi má na titulní straně překrytý text `Verze 1.4.13Verze 1.4.14`.
Je evidováno odděleně s upozorněním, nikoli vydáváno za novou verzi.
Pokyny 1.5 v historii na straně 2 uvádějí výchozí 1.4.14 s datem 5.10.2026,
zatímco historie dodaných čistých 1.4.14 uvádí 25.9.2026. Také tato odlišnost
vyžaduje vyjasnění vydavatelem; nepřepisujeme podle ní žádný originál ani účinnost.
Dokumenty 1.4.14 také obsahují historické legislativní výhrady. Zjištění jejich
obsahu samo neprokazuje aktuální právní platnost všech uvedených vět.

Výsledek: účinnost **pokynů** je doložena jejich titulními stranami; účinnost
**celých XSD/datových sad** není dosud nezávisle potvrzena. `bundles.json` proto
ponechává účinnost nevyplněnou a dovoluje jen výslovnou volbu konkrétního balíčku.
Automatický výběr podle názvu složky nebo data publikace by byl nesprávný.

## Rozdíly datového modelu

Strojové výsledky: [differences.json](../schemas/official/analysis/differences.json)
a [xsd-differences.json](../schemas/official/analysis/xsd-differences.json).

| Oblast | Výsledek |
| --- | --- |
| Celý slovník | 442 → 454 atributů; 27 přidáno, 15 odstraněno, 364 společných ID má změněnou alespoň jednu hodnotu/metadatový sloupec. Nejde o 364 nových validačních pravidel. |
| Slovník označený MĚSÍČNÍ | 234 → 245 atributů; 21 přidáno, 10 odstraněno. Ne všechny jsou vstupními údaji zaměstnance; jsou zde i hlavičky, souhrny a serverem doplňovaná metadata. |
| Katalog kontrol, list MH | 203 → 221 záznamů s ID; 19 přidáno, 1 odstraněno (ID 109), 202 společných ID má rozdílný text nebo metadata. Změny popisů/formulí nejsou automaticky vykonávány. |
| Interakce | 37 → 43; nové IN38–IN43, změněn text IN03. Matice ostatních scénářů jsou zachovány v originálech; samotné ID interakce nepopisuje všechny změny jejich buněk. |
| Číselníkové listy slovníku | 46 → 45; odstraněn list CIS GFŘ pracoviště; u 8 společných listů se liší obsah/pořadí. Není to samo o sobě důkaz zrušení daného oficiálního číselníku. |
| XML namespace podání | `http://schemas.cssz.cz/JMHZ/podani/1.0` → `http://schemas.cssz.cz/JMHZ/podani/2027` |
| Obálka formulářů | `formulareOsob/formularOsoby` → `formulareZamestnani` a odkaz na `form:formularZamestnani`; mění se i namespace hlavičky formuláře. |
| Typy | přibyl samostatný `simpleTypes.xsd`; přesuny a přejmenování elementů nelze řešit pouhou záměnou namespace. |

Nové měsíční atributy dle slovníku: 10550–10555, 10565, 10566, 10570, 10571,
10575, 10577, 10579, 10580, 10582–10587 a 10589. Odstraněné z této části:
10267, 10292–10296, 10310, 10347, 10416 a 10418. Například ID 10555 zavádí
samostatný příjem z PPV podle § 6 odst. 4; pracovní `income` se na něj nesmí
automaticky přesměrovat bez vyjasnění významu zdrojové částky.

Číselníkové listy se změnou: CIS Druh zaměstnání, CIS Důvod pro volný přístup na,
CIS Důvod ukončení služ. poměru, CIS Klasif. postavení v zaměstn, CIS Obce,
CIS Typ Odloženého příjmu, CIS Typ akce, CIS Zdravotní pojišťovny. Jde o názvy
listů omezené Excelem; delší odkaz na číselník ve slovníku nemusí být doslovně
stejný název listu. Úplnost všech referencí ještě vyžaduje věcný přezkum.

## Co je nyní funkční

Import originálních XLSX/ZIP do katalogu i UI s pravdivými technickými stavy,
normalizace a dohledatelnost, vnořené rozbalení, extrakce slovníků/kontrol/interakcí/
číselníků, podklad mapování a porovnání verzí. Obě vstupní XSD se kompilují
s lokálními závislostmi (14 / 15 schémat) a validují XML přes UI i CLI.
Testy generují syntetickou hlavičku skutečného XSD a ověřují úspěch, nesprávný
měsíc, cizí namespace, DTD, únik cesty i změněný hash. Taková hlavička není
úplné mzdové podání: právě proto výsledek odděluje XSD od metodiky a připravenosti.

## Co stále chybí

- Doložený lidský přezkum oficiálního původu a kompatibility vydání, potvrzení
  účinnosti celých sad a vyřešení rozdílných dat v historii slovníků.
- Produkční profil převodu skutečného mzdového exportu, zaměstnavatelská hlavička,
  model více PPV/opakovaných údajů a agregace za zaměstnance. Pracovní profil
  zůstává označený `unverified-draft-0`.
- Přepis a ověření metodických pravidel včetně závislostí číselníků, účinnosti
  parametrických konstant a nezávislých kontrolních součtů. Vzorce XLSX se nevykonávají.
- Kompletní generátor mzdového XML a doložené integrační příklady měsíčního
  podání s očekávanými metodickými výsledky. Protokol z dodaného ZIP není náhradou.
- Ověření Windows EXE a distribuce XSD balíčků s aplikací. Ve vývojovém checkoutu
  jsou dostupné; PyInstaller balení dat ještě není doplněno.

Finální export proto zůstává blokovaný. Opravná hlášení a registrace nejsou implementovány.
