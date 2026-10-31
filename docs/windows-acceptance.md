# Krátká přejímka Windows sestav

Vyplnit **samostatně** pro Win7 SP1 x86 a Win11 x64. Zatím žádná Windows přejímka
neproběhla. Pouze syntetická data; DB/zálohy nejsou šifrované. Win7 je nepodporovaný
OS s dodatečným bezpečnostním rizikem. Síť má být odpojená, účet bez administrátora.

Záznam: OS/build/SP/KB/CRT, RAM/CPU, DPI/rozlišení, commit, SHA-256 ZIP a
SHA256SUMS, přesné verze z build-report.json, tester/datum, výsledek/odchylky.

- [ ] Čistý cíl bez Pythonu: celá správná onedir složka se spustí offline bez
  chyb DLL/qwindows. Zkontrolovat x86/x64 a Win7 SP1/KB2533623/UCRT/CRT x86.
- [ ] Spustit z jiné pracovní složky, přes zástupce a z cesty s mezerami/diakritikou;
  runtime XSD/profily se najdou. Nemazat/copy jen EXE.
- [ ] `--self-test --report NOVY_SOUBOR`: návrat 0, passed, frozen=true, správná
  Qt vazba; nezmění běžná AppData. Chybný/existující report se nepřepíše.
- [ ] `Spustit-ukazku.cmd`: TEST A/B, správný měsíc, A 3 PP/B 2 PP; stejný interní
  PP ve dvou firmách nepropojí data. Změna firmy/měsíce vyčistí starý náhled.
- [ ] CP1250/středník, úvodní nuly, řádkové součty 300/200, HPP/DPČ/DPP,
  dvě PP téže osoby, cizinec bez RČ, nula zachovaná. Vyzkoušet volbu kódování/oddělovače.
- [ ] Chybný CSV: nesouhlas a prázdno vyvolají konkrétní nálezy, žádné převádění
  neznámé částky na nulu. Varianta čekající na OIČ neodblokuje metodiku.
- [ ] Pracovní XML obou sad 2026/2027: souhrn/PVPOJ/PP, XSD kontrola a zobrazení
  otevřených otázek; finální export stále nepřístupný.
- [ ] Reimport zachová historii; B umožní čistou interní revizi 1 po 0, u A se
  otevřený nulový scénář neobchází. Revize není oficiální opravné podání.
- [ ] Záloha/obnova jedné organizace do nového prostoru zachová XML/součty/historii;
  špatný hash/existující organizace odmítnuty. Offline definice dvou verzí zachovány
  (automatický test), žádná síť ani přibalené skutečné DB.
- [ ] Použitelné okno při 1024×720, DPI 100/125/150 %, ovládání klávesnicí,
  otevření/zavření dialogů a aplikace po XML bez pádu. Změřit RAM a čas x86;
  velké exporty zatím nejsou kapacitně potvrzené.
  Na Win7 ověřit také rasterový provoz bez volitelných ANGLE/shader DLL
  a se systémovými grafickými knihovnami/ovladači cílového počítače.
- [ ] Zkontrolovat, že běžné diagnostické výstupy neobsahují RČ/OIČ/mzdy; pracovní
  XML/DB jsou naopak citlivé a nejsou diagnostickým logem. Ověřit účet/práva ACL.

Při chybě uchovat build-report a obecný popis kroku; nezasílat skutečné mzdové
DB/XML. Označit sestavu jako nepřijatou. Zapsat výsledek pro oba systémy do PR
nebo vydání; teprve poté lze tvrdit konkrétní Windows provozní kompatibilitu.
