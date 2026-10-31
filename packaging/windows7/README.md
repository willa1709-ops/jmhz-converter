# Windows 7 SP1 x86 – testovací GUI distribuce

**Windows EXE zatím nebylo sestaveno ani spuštěno.** Jde o připravený postup,
nikoliv potvrzení kompatibility Win7. Win7 je nepodporovaný systém, testovat pouze
syntetická data. DB a zálohy nejsou šifrované, finální export je blokovaný.

Použijte [aktuální úplný návod](../../docs/windows-preview-build.md),
[český první start](../../docs/first-run-windows.md) a
[přejímací seznam](../../docs/windows-acceptance.md).

- Oddělený Python 3.8.10 **x86** na Win7 SP1; `build.ps1` volá společný bezpečný
  builder s `JMHZ-Converter-Win7-x86.spec`. Výsledkem je celá one-folder distribuce
  s `JMHZ-Converter-Win7-x86.exe`, žádná instalace Pythonu na cíli.
- `requirements-candidate.txt` obsahuje všech 19 přesně připnutých Windows,
  runtime, build a test distribucí. Další balíček nebo novější verze se odmítá.
- `wheels-candidate.json` a `wheels-evidence.json` zachycují skutečně stažené
  win32/univerzální wheels a shodu jejich hashů s metadaty PyPI; pin musí projít
  nezávislým přezkumem. Neprokazují spuštění DLL na Win7.
- `pe-wheel-evidence.json` pokrývá statickou kontrolu 28 vybraných hlavních
  Qt/Core/Widgets/shiboken/lxml/VC binárek a GUI pluginů. Nezahrnuje celý EXE.
  Wheel obsahuje také nepotřebné WinRT komponenty; spec je vylučuje a finální
  audit je odmítá. Celý výsledný EXE/DLL musí projít kontrolou a spuštěním na Win7.
  Volitelné ANGLE/software-GL/shader DLL se nepřebírají; Qt startup adaptér používá
  raster widgets a systémový desktop OpenGL. Jeho skutečný běh na Win7 je neověřený.
- Společné jádro a GUI Qt5 byly ověřeny na **Linux Pythonu 3.8.20**. To není
  stejný OS ani patch Pythonu jako kandidátní Windows instalátor 3.8.10.

Neinstalujte moderní `pyproject.toml` nebo `requirements.txt` do 3.8. Historické
samostatné konzolové pokusy nejsou aktuální cestou k požadovanému GUI. Externí
verzované definice se instalují mimo EXE do uživatelského prostoru; staré sady
se zachovávají. Neznámá mzda se nedoplňuje nulou a žádný build neodblokuje podání.
