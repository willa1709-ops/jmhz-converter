# Technický návrh Windows 7 SP1 x86 a moderní Windows

Návrh před změnou platformy, 30. 10. 2026. Hlavní cílový počítač má Windows 7
SP1 **32-bit**. Současný projekt vyžaduje Python 3.12 a PySide6; tato kombinace
není cestou pro tento počítač. Moderní závislosti ani fungující UI se nesnižují.

Aktualizace 31. 10.: hlavní organizační workflow nyní má sdílený Qt5/Qt6 adaptér
ověřený na Linux Pythonu 3.8/3.12. Kandidátní onedir GUI build pro oba Windows,
úplné hashové wheelhouse vstupy a cílová přejímka jsou v
[novém postupu](windows-preview-build.md). Windows EXE zatím nebyly sestavené.

## Dvě běhové varianty a společné jádro

| Součást | Windows 7 SP1 x86 – kandidát k ověření | Windows 10/11 x64 – stávající varianta |
| --- | --- | --- |
| Python | **3.8.10 x86**, poslední 3.8 s běžným Windows instalátorem; Linux test jádra může používat 3.8.20 | 3.12+ |
| Qt / binding | **PySide2 5.15.2.1 / Qt 5.15.2**, existuje win32 wheel pro CPython 3.8 | PySide6 6.12.0 |
| lxml | **5.3.2**, existuje cp38-win32 wheel; načtení jeho DLL na Win7 musí projít testem | 6.1.3 |
| openpyxl | **3.1.5**, Python >=3.8, univerzální Python wheel | 3.1.5 |
| PyInstaller | **5.13.2**, existuje win32 wheel; dokumentace uvádí Win7 jako „should work“, oficiální podporu až Win8+ | 6.22.3 |
| Test runner | pytest 7.4.4 pro Python 3.8 | pytest 9.2.0 |

Tato tabulka není tvrzením, že Windows EXE už funguje. Dostupný win32 wheel
potvrzuje architekturu/Python ABI, nikoliv kompatibilitu všech importovaných DLL
s Windows 7. Verze jsou izolovaný kandidátní profil; žádná se automaticky
neinstaluje do moderního prostředí. Starší stack již nemá běžnou podporu;
konkrétní zbytkové riziko a případné opravy závislostí patří do rozhodnutí o nasazení.

Nové `app/core/` nesmí importovat Qt, `app.models` se StrEnum, moderní UI ani
automatické síťové aktualizace. Odděluje mapování, metodický stav, stavbu XML
a lokální XSD validaci. Zachová syntaxi/API dostupné v Pythonu 3.8. Moderní
služby ho volají přes adaptéry; pozdější Qt5 UI musí používat stejné jádro,
nikoliv kopii finančních nebo XML pravidel. Hotový Qt5 adaptér zatím není součástí návrhu.

Pro společný resolver jsou důvodem malé cílené změny: odstranění závislosti na
Path.is_relative_to (3.9) a vyhodnocovaných nových anotacích. Přesunutí doprovodí
zachování původního importního API a existujících testů. Ostatní moderní moduly
se bez potřeby plošně nepřepisují. Celá současná aplikace tedy zatím není portem na 3.8.

## Windows sestavení a offline provoz

Sestavovat na odděleném **32bitovém Pythonu** v kontrolovaném Windows prostředí,
nejlépe na skutečném Win7 SP1 x86 nebo jeho VM. Linux PyInstaller nevytvoří
Windows EXE. Použít ověřené offline wheels, zaznamenat SHA-256 všech vstupů a
architekturu každého DLL. PySide2 vyžaduje také odpovídající shiboken2.

Nejprve portable `--onedir`: celou složku lze zkopírovat bez instalace Pythonu.
Teprve po přejímacích testech zkoušet `--onefile`; tento režim rozbaluje knihovny
do TEMP, takže „jeden EXE“ neznamená nulové pomocné soubory za běhu. Nepoužívat UPX
ani Qt WebEngine. Použít Qt Widgets a dostupný softwarový renderer dle cílového GPU.

SP1 samotný nemusí stačit: dokumentace Pythonu 3.8 výslovně vyžaduje na Windows 7
**KB2533623** a upozorňuje na Microsoft C runtime / UCRT. Potřebné x86 redistributables
musí být buď přítomné, nebo licenčně a technicky správně distribuované se sestavou.
Nelze nyní slíbit, že na neaktualizovaném SP1 nebude potřeba žádný systémový doplněk.

Do portable varianty zabalit pouze runtime, Qt platform plugin `qwindows`,
společné jádro a konkrétní XSD/manifests. Originální PDF/XLSX archivy mohou být
vedle programu; pro samotný převod nejsou jejich kancelářské prohlížeče potřeba.
Žádné pip, Python ani přístup na internet nemá být za běhu vyžadován.
XSD resolver nadále nesmí stahovat závislosti ze sítě.

32bitový adresní prostor vyžaduje měření RAM na skutečném exportu, omezení
velikosti zakázek a později stránkovaný náhled. Dnešní limity 25 MiB/100 000
řádků nejsou potvrzeným kapacitním slibem pro x86.
Pro první test použít krátkou cestu např. `C:\JMHZ`; Windows 7 má také omezení
délky cest, zejména u rozbalování onefile do TEMP. Dlouhé cesty se nesmí předem prohlásit za podporované.

## Co prokáže připravenost legacy sestavy

1. Jádro a skutečná dodaná XSD projdou pod Pythonem 3.8 i moderním Pythonem.
2. Čistý Win7 SP1 x86 bez Pythonu načte všechny DLL a Qt pluginy; totéž po
   přenosu sestavy na druhý účet a do cesty s českými znaky.
3. Offline import CSV/XLSX, profily, nálezy a součty dávají shodné výsledky
   s moderní variantou, včetně chybějících hodnot a zablokovaného finálního exportu.
4. Ověřit paměť, TEMP, přístupová práva, výpadek zápisu a shodné hashe XSD.
5. Zaznamenat verze OS aktualizací, CRT, wheel/DLL hashů a výsledky přejímky.

V této linuxové relaci se ověřuje jádro, nikoliv Win7, jeho grafické UI ani EXE.
Neověřená sestava se nevydá jako hotový program pro hlavní pracovní počítač.

Další etapa doplnila číslované položky, párování PP, Decimal výpočty, kontext revizí
a offline verzované balíčky do téhož jádra pro Python 3.8. Bezpečný ZIP helper
má odložené anotace a přenositelné kontroly cest; nevyžaduje Qt ani moderní UI
modely. Nový dialog je zatím adaptér PySide6. Testy jádra zahrnují externí sady
a oba skutečné XSD, ale nadále běží na Linuxu x64. Neprokazují paměťové limity
x86 ani běh Windows DLL. Obecná analýza má navíc limit milionu pracovních buněk;
ten nenahrazuje měření skutečného exportu na cílovém počítači.
Definice se instalují do zapisovatelné složky uživatele mimo EXE/TEMP a vybírají
výslovnou verzí a hashem; není nutné přestavovat EXE při pouhé změně podporovaných
mapování. Změna aplikační logiky stále vyžaduje nové sestavení a přejímku.

Organizační služba, samostatné SQLite databáze a posouzení identifikační
alternativy také používají jádro bez Qt pro Python 3.8. Nové výchozí přehledové
okno je zatím PySide6. Zachování testů jádra není dokončením Qt5 UI nebo
otestováním souborových oprávnění/DLL na Win7 SP1 x86 či Windows 11.

## Zdroje ověřené při návrhu

- CPython 3.8 Windows dokumentace: https://raw.githubusercontent.com/python/cpython/v3.8.10/Doc/using/windows.rst
- Python 3.8.10 release (instalátory): https://www.python.org/downloads/release/python-3810/
- Qt 5.15 platformní dokumentace: https://raw.githubusercontent.com/qt/qtdoc/5.15/doc/src/platforms/supported-platforms.qdoc
- Tabulka Qt 5.15 uvádějící Windows 7 x86/x64: https://raw.githubusercontent.com/qt/qtdoc/5.15/doc/src/platforms/supported-platforms.qdocinc
- PyInstaller 5.13.2 README: https://raw.githubusercontent.com/pyinstaller/pyinstaller/v5.13.2/README.rst
- PyInstaller runtime poznámky: https://raw.githubusercontent.com/pyinstaller/pyinstaller/v5.13.2/doc/usage.rst
- Metadata a seznam artefaktů: https://pypi.org/pypi/PySide2/5.15.2.1/json,
  https://pypi.org/pypi/lxml/5.3.2/json, https://pypi.org/pypi/openpyxl/3.1.5/json,
  https://pypi.org/pypi/pyinstaller/5.13.2/json.

Zdrojový CPython dokument, PyInstaller README/poznámky a PyPI metadata byly
skutečně načteny. Release URL Pythonu je doplňkový oficiální odkaz; její obsah
v této relaci nebyl samostatně stažen. Provozní kompatibilitu DLL tyto odkazy nenahrazují.
