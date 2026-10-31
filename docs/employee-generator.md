# Pracovní generátor běžných zaměstnaneckých formulářů

Navazuje na PR #5. Generuje skutečný `bezPriznaku` podle dodaných XSD
1.4.3.6 / 1.5.0.3 jako individualizovanou část pracovního paketu JMHZ.
Není to kompletní podání: chybí souhrnná a pojistná část zaměstnavatele,
úplná metodická kontrola a doložení účinnosti/původu. **Finální export zůstává
nepodmíněně blokovaný.** XSD úspěch je technický výsledek, nikoliv povolení podání.

## Analýza podkladů 2026/2027

Reprodukovatelný nástroj čte originální datové slovníky a katalogy kontrol,
nejprve ověřuje jejich SHA-256 proti existujícímu katalogu a používá skutečný
hashově ověřený XSD resolver. Nevychází jen ze starých odvozených JSONů.
Vzorce Excelu uchovává jako text, nikdy je nespouští.

```text
python -m app.definitions.employee_analysis --official-root schemas/official --output docs/evidence
```

| Sada | Slovník / katalog kontrol | Listy kontraktu | Navázané kontroly |
| --- | --- | --- | --- |
| 2026, XSD 1.4.3.6 | 1.4.1.6 / 1.4.2.11 | 180 koncových cest | 154 |
| 2027, XSD 1.5.0.3 | 1.5.0.3 / 1.5.0.4 | 185 koncových cest | 169 |

Navázané kontroly jsou kandidáti podle ID atributů; ne všechny jsou bez dalších
podmínek použitelné pro konkrétní zaměstnání. Podrobné výstupy obsahují zdroj,
verzi, URL, SHA-256, list/řádek/buňku slovníku a kontroly, XSD cestu, typ a řádek:

- [Kontrakt a související pravidla 2026](evidence/employee-2026.json)
- [Kontrakt a související pravidla 2027](evidence/employee-2027.json)
- [Přesný rozdíl cest, typů a místních povinností](evidence/employee-differences.json)

`minOccurs` koncového pole není samo o sobě globální povinnost: rozhoduje také
volitelný rodič, větev `choice`, interakce a metodika. Konstrukce XML proto
čte celou strukturu konkrétního schématu včetně pořadí a dědičnosti typů.
Pro neznámou konstrukci se zastaví, nevymýšlí ekvivalentní elementy.

Ověřené strukturální rozdíly zahrnují:

- 2026 používá `formulareOsob/formularOsoby` a hlavičku v podacím namespace;
  2027 `formulareZamestnani/formularZamestnani` a hlavičku ve formulářovém namespace.
- V obou sadách je scénář `bezPriznaku` doložen pro činnosti 1–9 s bližším
  určením „Žádné“, A–J a T–ZC. Originální číselník přiřazuje 1–9 pracovním
  poměrům, A–J DPČ a T–ZC DPP. Rodina se nekonvertuje na jiný scénář podle částky.
- ID 10419 se přesouvá ze `souhrnDataZec/prohlaseniPoplatnika` do
  `souhrnDataZec/zalohaNaDan/prohlaseniPoplatnika`; 2027 přidává povinný 10579.
- ID 10535 mění cestu/význam z `prijem/dan/zakladDane` na `prijem/dan/prijem`;
  2027 obsahuje také `prijemPar6` (10555). Staré mzdové mapování nelze přejmenovat
  bez kontroly významu.
- 2027 vyžaduje v `bezPriznaku` příznaky slev 10490, 10546 a 10372; 2026 byly
  příslušné struktury/příznaky volitelné. Hodnoty NE se nevytvářejí automaticky.
- Řada starších číselných řetězců přechází na nezáporné číselné typy, mění se
  rozsahy/preciznost. Zaokrouhlení při překročení cílového typu se neprovádí.

### Rozsah metodických kontrol

Implementovaný podrozsah: 23 (dovolená versus hodiny s náhradou), 43/44
(interval a datum vyplnění), 58 (počet dnů měsíce), 216 (úplný řádkový rozklad
vyměřovacího základu), 248 (souhrn jen na primárním PP), 255/260 (primární PP
řešený společným párováním), 267/282/286 (neuvádění rozkladů při nulovém celku),
299 (měsíc pojištění), 321 (přítomnost souhrnu a povinností vybrané XSD větve)
a 332 (neprokázaný primární PP je otevřený metodický nález).
Podmíněné daňové a jiné povinnosti kontroly 321 nejsou tímto úplně pokryty.
Kontroly nejsou kopírovány jako vykonávané excelové vzorce.

Otevřené výklady:

- 134/368 uvádějí rozdíl dat bez vyjasnění inkluzivních hranic. Aplikace si
  nedosazuje vlastní `+1` a netvrdí úplnou implementaci.
- Kontrola 388 katalogu 2027 spojuje 10265/10268/10329/10345 se státním
  zástupcem, zatímco běžný XSD formulář některá z těchto polí vyžaduje. Je nutné
  potvrdit skutečný aplikační rozsah kontroly; generátor ponechává výslovný nález.
- DPP/DPČ daňové limity, součty přes více PP/VS, registrace, stav osoby,
  zvláštní slevy a další interakce vyžadují samostatné ověření. Pojistné ani
  daň se nyní z částek neodvozují neověřenými vzorci.

## Podporovaný pracovní rozsah

HPP, DPČ a DPP používají své doložené kódy a vlastní PP. Pro HPP musí být ve
zdroji `employment_detail=1` (číselník: Žádné). `eldp_segments=1` je výslovný
zdrojový fakt/potvrzení jediného ELDP úseku. Více úseků nelze slít do jednoho;
takový požadavek je zatím blokující. Ostatní opakující se struktury umí tato
etapa také pouze v jedné instanci, ne jako úplné seznamy dětí/úseků/rozpadů.

Mapování rozlišuje číslované mzdové položky a oficiální atributy JMHZ.
Zaměstnanecký profil dovoluje zdroj `item`, `calculation` (řádkový Decimal
výpočet) nebo `column`. Nepovoluje kód, konstanty místo neznámých hodnot ani
libovolné XML cesty mimo oficiální kontrakt. Identifikaci čte jen z metadat.
U souhrnné osobní vrstvy je povinné výslovné `on: primary`; poskytuje se
ověřený osobní souhrn ze zdroje. Program jej nevypočítává součtem PP odhadem.

[Profil 2026](../config/conversion/employee-2026.json) a
[profil 2027](../config/conversion/employee-2027.json) používají názvy připravených
kanonických sloupců `jmhz_<ID atributu>`. **Nejsou to potvrzená čísla položek
vašeho mzdového systému.** Nahraďte každou vazbu podle skutečného exportu.
Hlavičky bez mzdových hodnot jsou ve stejném adresáři. Pro číslovaný profil
ponechte jen skutečně známé zdroje, doplňte metadata `employment_detail`,
`eldp_segments` a skutečný zdroj celkového příjmu `income_amount`. Deklarovaný
sloupec musí existovat; prázdná volitelná hodnota se vynechá, povinná vyvolá chybu.
Data identifikátorů musejí být textová. Částky se přesně normalizují bez
zaokrouhlení; původní nuly identifikátorů zůstávají zachované.

### Cizinci

České RČ není předpokladem vykázání při přiděleném OIČ/PPV. Při doložené
registraci `pending_oic` se použije skutečná XSD alternativa příjmení, jméno,
narození, nástup a druh činnosti. Podrobné zdroje jsou v
[důkazech IN01](workforce-evidence.md).
S RČ lze PP lokálně párovat. Bez OIČ i RČ se PP podle jména automaticky nespojují:
lze připravit technicky platný **neúplný pracovní náhled** s identifikační
alternativou, ale bez odhadnutého příznaku primárního PP a s nálezem kontroly 332.
To není metodicky správné podání. Chybějící alternativa nebo rozporné klíče
pracovní náhled zablokují. Registrace sama není implementovaná.

### Zaměstnání bez příjmu

Nikdo se podle nuly nevyřazuje. Pro první doložený nulový scénář se požaduje
registrovaný PP po celý měsíc, výslovně žádný výkon práce a jediný PP dané osoby.
Skutečné hodnoty musí odpovídat tabulce Pravidel 1.4.6, str. 16–18: nulové
požadované částky/dny/hodiny, výslovné příznaky a celoměsíční intervaly. Hodnoty
se kontrolují, automaticky se **nedoplňují**. Skutečný stav prohlášení/ročního
zúčtování a místo práce nelze odvodit z nulové částky.

Nemoc, rodičovská, neodpracovaná dohoda, částečný měsíc a nulový PP v souběhu
s příjmovým PP nejsou bez dalších faktů stejný scénář. Neznámý příjem, práce
nebo rozsah vede k požadavku na doplnění; souběžná nulová varianta zatím není
implementovaná. Původ a účinnost starší tabulky pro sadu 2027 jsou otevřené,
takže i technicky správný nulový pracovní paket nese metodický nález.

## Použití a historie

V hlavním okně vyberte organizaci, měsíc a import. Tlačítko Pracovní XML nabídne
nové HPP/DPČ/DPP nebo původní `jinyPrijem`. Pro lokální pracovní profil vyberte
zaměstnanecký JSON a skutečné parametry podání. U ověřeného balíčku se profil
čte z jeho vstupního bodu `employee_profile`; CSV mapování, zaměstnanecký profil
i XSD musejí patřit stejné schválené sadě. Builder podporuje `--employee-profile`.

Nové kontroly i neúspěšné výsledky se ukládají k vlastní organizaci/importu.
Historie obsahuje profil, parametry, XSD hashe, blokující nálezy a otevřené
metodické otázky. Úspěšné pracovní XML se ukládá s kontrolním hashem; nikdy
nepřepisuje jiné organizace nebo starší verzi. Přehled zahrnuje také XML nálezy.
Pořadí přípravy ani interní UUID se nepoužívají jako GUID podání/formuláře.
GUID zůstávají explicitním vstupem s neověřeným životním cyklem; typ R je
pracovní řádný scénář, ne automatické opravné podání při interní revizi 1.

Pro společné jádro bez Qt je dostupné organizačně vázané CLI:

```text
python -m app.core.employee_xml --workspace C:\JMHZ\workspace --organization ORGANIZATION_UUID --import-id IMPORT_UUID --employee-profile config/conversion/employee-2026.json --parameters local/parameters.json
```

UUID a parametry zde jsou zástupné názvy pro existující vlastní záznamy.
U balíčku lze `--employee-profile` vynechat. `--write-draft` výslovně zapíše
soubor `.draft.xml` do datového prostoru organizace. Diagnostický JSON neobsahuje
osobní/mzdové hodnoty; úspěšný návrat znamená XSD úspěch, ne dokončenou metodiku.

## Stav dodávky

**Hotové:** skutečná konstrukce a XSD validace základních formulářů obou verzí,
uvedený podrozsah kontrol, identifikační alternativy, řádkové vazby/výpočty,
osobní souhrn jen na primárním PP, organizační historie, GUI/CLI a offline loader.

**Částečné:** nulové a cizinecké scénáře, jeden ELDP úsek a jedna instance
opakovaných struktur, podmíněné povinnosti a primární PP při chybějících klíčích.
Společné jádro je testované na Linuxu s Pythonem 3.8/3.12; to nepotvrzuje Windows DLL.

**Chybí:** skutečný anonymizovaný export a potvrzené mzdové položky/vzorce,
kompletní souhrn/PVPOJ a katalog kontrol, další úseky/interakce, výklady 134/368/388,
účinnost a původ, referenční správné podání a metodika GUID/oprav, přejímka
Win7 x86/W11 x64 a šifrované úložiště. [Plán zabezpečení](payroll-database-security.md)
je návrh, nikoliv tvrzení, že dnešní DB již jsou šifrované.
