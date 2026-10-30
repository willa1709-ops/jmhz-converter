# Identifikace cizinců a zaměstnání bez příjmu: doložený rozsah

Podklady jsou již uložené v repozitáři. Níže rozlišujeme obsah dokumentů,
technickou shodu XSD a dosud nedokončený metodický přezkum. Oficiální původ ani
účinnost celých sad tímto nepotvrzujeme. Aplikace nevyžaduje občanství ČR ani RČ
jako předpoklad importu a neztotožňuje osoby odhadem podle jména/narození.

## Identifikace a IN01

Dokument [MH – Pokyny k vyplnění měsíčního hlášení 1.5](../schemas/official/2027/mh-pokyny-k-vyplneni-mesicniho-hlaseni-1.5.pdf),
oddíly 3.2.1–3.2.2, tištěné strany 77–80, ID 10051, 10053, 10054, 10056,
10223 a 10228 (textový přepis řádky 3301–3443):

> „Atribut se neuvádí při interakci IN01 – Byla provedena registrace
> zaměstnance, ale zatím nebylo přiděleno IK MPSV.“

Příjmení, jméno, narození a nástup jsou popsány jako povinné při IN01 / při
identifikaci bez OIČ nebo PPV. Není to oprávnění vymyslet OIČ, RČ či PPV nebo
zaměnit interní číslo za PPV. Volba `pending_oic` v pracovním vstupu je výslovné
potvrzení již provedené registrace a čekání na přidělení, nikoliv automatický
důsledek prázdné buňky.

Skutečné `identifikaceType` v `formCommonTypes.xsd` obou sad obsahuje `xs:choice`:

1. `ikMpsv` + `idPpv`;
2. `prijmeni` + `jmeno` + `datumNarozeni` + `datumNastupu` + `druhCinnosti`.

Všechny členy druhé sekvence jsou v XSD povinné. RČ ani pas nejsou další
alternativou tohoto typu. U cizince s přiděleným OIČ není chybějící české RČ
chybou lokálního párování. Samotné RČ lze použít pro lokální propojení PP,
ale automaticky se tím nestane XML identifikací. Podle samotné alternativní
sekvence nelze prokázat, že dva zaměstnanecké řádky patří jedné osobě.

`IdentityValidator` kompiluje přímo uvedený typ z hashově ověřených skutečných
XSD v původním lokálním resolveru. Interní kontrolní obálka není element JMHZ
ani exportovaný formát. Testy používají obě sady a ověřují platnou alternativu,
chybějící datum a odmítnutí neplatného druhu činnosti. XSD kontrola nepotvrzuje
totožnost ani připravenost podání.

[Pravidla podání JMHZ a související procesy 1.4.6](../schemas/official/2026/pravidla-podani-jmhz-a-souvisejici-procesy-ver-1.4.6.pdf),
tištěná strana 95, přepis řádky 4814–4818, uvádí příjem identifikačních údajů
čekajícího zaměstnance na vstupu a dokončení protokolu až po ztotožnění/přidělení
OIČ. Z toho neplyne oprávnění lokálně automaticky spojovat osoby podle jména.

Pracovní metadata:

| Pole | Obsah |
| --- | --- |
| `employment_type` | interní kategorie `HPP`, `DPP`, `DPČ`/`DPC`; neurčuje automaticky XML scénář |
| `registration_status` | `registered`, `pending_oic`, `not_registered` nebo `unknown`; doložit skutečný stav |
| `given_name`, `surname` | skutečná jména, nejvýše 100 znaků dle metodiky |
| `birth_date`, `employment_start` | skutečná data ISO `YYYY-MM-DD` |
| `activity_code` | skutečná hodnota oficiálního číselníku, technicky kontrolovaná XSD |
| `id_ppv` | skutečný přidělený PPV, nikdy automaticky interní číslo |

Chybějící/nesprávné alternativní údaje vedou ke konkrétnímu požadavku na doplnění.
Bez registrace aplikace požaduje její doložení/provedení mimo aplikaci;
registraci sama neimplementuje. Při platné alternativě bez OIČ i RČ zůstává
řádek zachovaný a alternativa technicky posouzená, ale párování a primární PP
jsou nevyřešené. Není zatím implementován samostatně doložený náhradní postup
ztotožnění, takže takový záznam nemůže projít do finálního podání.

## Nulový příjem, prázdná a nepřítomná hodnota

Tatáž Pravidla 1.4.6, tištěná strana 16 (přepis řádky 663–666), výslovně uvádějí:

> „Měsíční hlášení (řádné, opravné) – řádný formulář s nulovými hodnotami“
>
> „řešení pro situace, kdy byl zaměstnanec, resp. PPV v JMHZ registrován, ale
> výkon práce v daném měsíci neprobíhal a ani nebyl zúčtován příjem ze závislé činnosti“

Tabulka pokračuje dalšími atributy včetně pojištění a dnů; nejde jen o nulový
příjem. Strany 14–16 současně popisují zvláštní nulové **opravné** hlášení pro
anulování nesprávně vykázaného měsíce. Tyto dvě situace nelze zaměňovat.
Nemoc, rodičovská nebo dohoda bez práce se bez dalších vstupů automaticky
nepřekládají na opravné podání, odhlášení nebo vyřazení.

Obecné jádro zachovává stavy `zero`, `value`, `blank`, `absent_value`,
`absent_column` a `invalid`. Scházející sloupec nebo hodnota nyní neodstraní PP
z výsledku. Chybějící výpočtový vstup zůstane neznámý a kontrola jej označí.

Pracovní posouzení pro explicitně registrované zaměstnání, doložené trvání
v daném měsíci, `work_performed=no` a skutečnou nulu označí **kandidáta** řádného
formuláře s nulovými hodnotami. V ostatních nulových případech požaduje přezkum.
Řádek zůstane v obou případech zachovaný. Pravidlo vychází ze starší dokumentace;
jeho účinnost pro vybranou sadu/měsíc, pojistné údaje a další podmínky musí
prokazatelně potvrdit přezkum. Proto zůstává metodický nález i blok finálního
exportu. Prázdný/nepřítomný příjem požaduje skutečný údaj a nikdy se nenahradí nulou.

Je nutné potvrdit, která skutečná mzdová položka znamená celý zúčtovaný příjem.
Šablonové mapování `income_amount` na 190 to nedokládá. Nulová daň nebo jediná
nulová složka mzdy automaticky neznamená zaměstnání bez příjmu.
