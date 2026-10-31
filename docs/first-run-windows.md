# První spuštění testovacího JMHZ Converteru

Tato verze vytváří **pouze pracovní XML**. Finální podání je blokované.
Databáze, pracovní XML a zálohy **nejsou šifrované**. Pro celou přejímku použijte
výhradně přiložená syntetická data, žádný skutečný mzdový export.
Windows 7 je nepodporovaný systém se zvláštním bezpečnostním rizikem;
aplikace jeho ochranu ani aktualizace nenahrazuje.

## Co dostanete

Pro každý systém samostatný ZIP s celou složkou:

- Windows 7 SP1 **32-bit**: `JMHZ-Converter-Win7-x86/JMHZ-Converter-Win7-x86.exe`.
- Windows 11 **64-bit**: `JMHZ-Converter-Win11-x64/JMHZ-Converter-Win11-x64.exe`.

**Samotné EXE nestačí.** Rozbalte a přeneste celou složku včetně DLL, pluginů,
podsložek a manifestů. Na cíli se Python samostatně neinstaluje. Systémové
předpoklady SP1/CRT/UCRT musí ověřit sestavovatel; jejich absence je chyba
přejímky, nesmí se řešit stahováním neznámých DLL. Před spuštěním porovnejte
SHA-256 ZIP s nezávisle získaným údajem sestavovatele. Umístění může obsahovat
mezery a české znaky. Program nepotřebuje aktuální adresář nastavený na svou složku.

**V prostředí Codexu Windows ZIP/EXE zatím nevznikly. Tento návod popisuje jejich
připravené sestavení a následnou přejímku, nikoliv existující vydání.**

## Nejrychlejší ukázka

1. Spusťte `Spustit-ukazku.cmd` ve složce testovací sestavy. Vytvoří nový izolovaný
   adresář `%LOCALAPPDATA%\JMHZ-Converter-Preview\…`; běžná aplikační DB se nepoužije.
   Každé spuštění ukázky vytvoří novou sadu, nic existujícího nepřepisuje.
2. V titulku musí být **SYNTETICKÁ UKÁZKA**. Jsou předvyplněné TEST Organizace A/B,
   měsíce `2026-09`, `2026-10` (A) a `2027-09`. Přehled ukazuje import, počet PP,
   nálezy a interní revizi. A má 3 PP (dvě HPP téže testovací osoby + DPP bez příjmu),
   B má 2 PP (DPČ cizince bez RČ + DPP). Číslo `0002` se vyskytuje u obou organizací.
3. Vyberte organizaci, měsíc a historii importů; klikněte **Kontrola a výpočty**.
   U A je součet `row_total` 300, u B 200. Jde o umělé testovací částky,
   nikoliv potvrzení skutečných mzdových vzorců.
4. **Historie kontrol / XML… → Pracovní XML → řádek uloženého XML** zobrazí celý
   měsíční pracovní paket a jeho nálezy. XSD shoda neznamená správné podání.
5. Změňte organizaci nebo měsíc. Předchozí náhled se musí vyčistit.
   Volba `--demo-directory` záměrně vyžaduje nový adresář a neotevírá starou ukázku.
   Historii z ukázky lze přenést explicitní organizační zálohou.

U A zůstává otevřený přezkum nulového příjmu, proto **není zapsaná interní revize**.
U B je připravená revize 0. Úspěch XSD nesmí tyto kontroly obejít.

## Nový import a vlastní výběr voleb

Soubory ve `synthetic-data` jsou výhradně umělé. Čísla položek `910…` a `92…`
jsou testovací, nejsou potvrzenými čísly zdrojového mzdového programu ani
číselníkem JMHZ. OIČ tvoří úmyslné testovací řetězce číslic, RČ jsou prázdná;
jména mají označení TEST. Tyto soubory se nikdy nepodávají.

- Zvolte měsíc `2026-09`, organizaci B a **Společný profil JSON… →
  synthetic-data/2026-numbered.json**. Pak **Import CSV/XLSX… → b-2026-09-pp.csv**.
  Výchozí kódování je Windows-1250, oddělovač `;`; obě volby lze změnit.
  Nový import zachová starší. Kontrola má dva PP a přesný součet 200.
- Po kontrole B bez nálezů lze zapsat navazující interní revizi 1. Nejde o opravné
  podání, GUID se automaticky nemění. Nulový příjem, chybějící údaje a otevřené
  nálezy nesmějí být obejity.
- **Celý měsíční paket…**: postupně `2026-employee.json`, `2026-monthly.json`,
  `b-2026-09-employer.csv`, `b-2026-09-parameters.json`. Výsledkem je pracovní
  náhled s otevřenými metodickými otázkami. Pro rok 2027 použijte všechny soubory
  roku 2027. Výběr XSD v hlavním okně slouží samostatné technické kontrole;
  profil pro XML musí mít správný bundle.
- U A importujte `a-2026-09-errors.csv`: jedna částka chybí a kontrolní součet
  nesouhlasí. Program musí zobrazit nálezy a neznámou částku nenahradit nulou.
- `b-2027-09-pending-oic.csv` obsahuje cizince čekajícího na OIČ. Alternativa má
  pouze doložený pracovní rozsah a ponechává přezkum identity/primárního PP otevřený.

**Nešifrovaná záloha…** uloží jednu organizaci. SHA-256 uložte odděleně od ZIP.
**Obnovit novou organizaci…** vyžaduje hash a odmítá přepsat existující organizaci.
V ukázce můžete archiv znovu obnovit až do jiné nové ukázky/běžného prázdného
úložiště, kde tatáž organizace zatím není. Záloha obsahuje syntetická data,
historii a potřebné starší definice. Neupravujte ručně lokální SQLite soubory.

Běžné spuštění samotného EXE otevře prázdný registr v uživatelských AppData.
K registraci/měsíčnímu importu používejte nadále jen syntetickou sadu; skutečný
mzdový systém, jeho DB a výpočetní jádro se touto přejímkou nemění.

## Automatická kontrola EXE

Z PowerShellu spusťte EXE s plnou cestou, počkejte a otevřete JSON výsledek:

```powershell
$p = Start-Process -FilePath 'C:\JMHZ-Test\JMHZ-Converter-Win7-x86.exe' -ArgumentList '--self-test --report C:\JMHZ-Test\novy-report.json' -Wait -PassThru
$p.ExitCode
Get-Content 'C:\JMHZ-Test\novy-report.json'
```

Pro W11 změňte název EXE. Cílový report musí být nový; adresář musí existovat.
Test použije dočasná syntetická data a vlastní DB, bez přístupu do běžného
registru. Vyžaduje návratový kód 0, `status: passed`, `frozen: true` a správnou
Qt vazbu. Návrat 1 = kontrola selhala, 2 = chybný parametr/cíl reportu.
Ani `passed` nenahrazuje [ruční přejímku](windows-acceptance.md).
