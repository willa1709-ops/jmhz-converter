# Windows distribuce

Aktuální cesta k testovací aplikaci je
[oddělený offline build Win7 SP1 x86 / Win11 x64](windows-preview-build.md),
[český návod k prvnímu spuštění](first-run-windows.md) a
[krátká ruční přejímka](windows-acceptance.md).

Používají se dva sledované PyInstaller specs, úplné platformní sady závislostí
a celé one-folder distribuce. Výstupem po skutečném sestavení mají být
`JMHZ-Converter-Win7-x86.exe` a `JMHZ-Converter-Win11-x64.exe` se všemi DLL.
Samotný EXE soubor se nepřenáší. Linux PyInstaller nevytváří Windows EXE.

**Windows EXE zatím sestavené ani otestované nejsou.** Zdrojové i zabalené
Linuxové ověření není přejímkou Windows. Testovat pouze syntetická data;
DB i zálohy jsou nešifrované, finální podání blokované. Starší ruční příkaz
s `--name JMHZ-Converter` nenahrazuje nové kontrolované sestavovací postupy.
