# Dodané a zbývající podklady JMHZ

Dodávka 2026/2027 je již v repozitáři. Není potřeba znovu dodávat shodné originály.
[Úplný přehled verzí a účinnosti](official-comparison.md) vysvětluje doložená data
i rozpory. [intake.json](../schemas/official/intake.json) obsahuje přesné původní
názvy, zdrojové URL rekonstruované z nahraných názvů a SHA-256 všech 13 souborů.
Ověření dostupnosti URL ani oficiálního původu tím není nahrazeno.

| Kategorie | Již dodáno |
| --- | --- |
| XSD podání | ZIP 1.4.3.6 a ZIP 1.5.0.3 s dalším vnořeným XSD ZIPem |
| Datový slovník | XLSX 1.4.1.6 a 1.5.0.3, včetně číselníkových listů |
| Katalog kontrol | XLSX 1.4.2.11 a 1.5.0.4 |
| Datové scénáře / interakce | XLSX 1.4.0.2 a 1.5.0.3 |
| Pokyny MH | PDF 1.4.14, 1.4.14 s revizemi a 1.5 |
| Pravidla podání a související procesy | PDF 1.4.6 |
| Výsledkové protokoly MH | ZIP 1.5; není příkladem vstupního měsíčního podání |

## Co ještě dodat nebo doložit

1. Potvrzení vydavatele a kompatibility konkrétních vydání v sadě. Doložit
   účinnost celé XSD/datové sady, nikoliv jen pojmenovat složku rokem. Titulní
   strany pokynů uvádějí 1.7.2025 a 1.1.2027; nejsou samy potvrzením každého souboru.
2. Vysvětlení nesouladu data publikace slovníku 1.4.1.6: starý sešit uvádí
   29.5.2026, historie nového pro stejné vydání 12.6.2026. Uchovat obě evidence.
3. Oficiální anonymizované příklady **vstupního měsíčního XML** a očekávané
   metodické výsledky. Dodaný protokol má jiný účel a není jejich náhradou.
4. Samostatnou definici EDV, pokud je pro integrační smlouvu vydaná zvlášť,
   a případné externí číselníky/vazby, které nejsou pokryty přiloženými listy.
   Jejich úplný potřebný soupis ještě není potvrzen, chybějící kódy nevymýšlíme.
5. Syntetický skutečný mzdový export: přesný význam částek, více PPV, identifikace
   zaměstnavatele a očekávané součty. Skutečné osobní údaje pro testy nejsou potřeba.

Oficiální rozcestníky pro dohledání doplnění: https://jmhz.mpsv.cz/,
https://developers.mpsv.cz/api-list/jednotne-mesicni-hlaseni-zamestnavatelu/documentation/4589f5c6-30e8-4e2b-b341-fe8481ad4e70
a https://www.cssz.gov.cz/pro-vyvojare-jmhz. Neprohlašujeme nové nepřečtené soubory
z těchto webů za ověřené.

[Postup načtení a registrace](official-intake.md) nyní podporuje originální XLSX
i ZIP. Stav technického čtení/CRC je oddělený od přezkumu původu a obsahu.
Opravná hlášení a registrace do této etapy nepatří.
