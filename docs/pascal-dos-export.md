# Smlouva CSV pro Pascal/DOS

Mzdová databáze ani výpočetní jádro zdrojového systému se nemění. Converter čte
samostatné exportní soubory; neposílá změny zpět do DOSové aplikace. Čísla položek
a jejich význam musí dodat provozovatel mzdového systému. ID atributu JMHZ
není automaticky stejné číslo jako položka ve mzdách.

- Kódování **Windows-1250** je nyní výchozí volbou hlavního GUI. Jiné kódování
  lze vybrat výslovně, stará podpora UTF-8/XLSX zůstává. Nezaměňovat CP1250
  s DOS CP852/Kamenickým kódováním; převodník nepřepisuje zdrojové soubory.
- Výchozí oddělovač `;`, hlavička se skutečnými čísly/názvy položek, obvyklé
  CSV citování dvojitou uvozovkou. CRLF je podporované. Desetinná čárka/tečka
  se interpretuje přes Decimal, ne přes binární float.
- Jeden řádek = jeden PP za měsíc. Interní číslo PP je text, např. `000012`;
  uvozovky nenahrazují zachování nul už při exportu. Opakované číslo v jiné
  organizaci je jiné zaměstnání. Období je `26-09` nebo `2026-09`.
- Číslované hlavičky mohou být např. původní skutečná čísla položek, včetně
  nul. Nastaví se v profilu `items` → zdrojový sloupec; potvrzené výpočty se
  provádějí v rámci jednoho řádku. Žádná nová čísla položek se zde nepředepisují.
- Skutečná nula musí být `0`. Prázdná buňka, nepřítomný sloupec a nula nejsou
  totéž. Neexportovat nulu za neznámý údaj.
- Pro zaměstnavatelské části se dodá samostatný jednořádkový souhrnný CSV
  organizace/měsíce. Případně se použijí jen výslovně doložené součty katalogu.
  Z ostatních PP položek se daň/pojistné/číselníky neodhadují. Pokud takový
  export zatím není dostupný, aplikace vypíše chybějící podklady.

Potřebná metadata PP: identita zaměstnavatele a měsíce, textové číslo PP,
OIČ/RČ nebo doložená alternativa, skutečný PPV/GUID pro pracovní XML, oficiální
kód činnosti a další údaje podle vybraného scénáře. Tyto zdroje mohou být
číslovanými položkami, pokud to odpovídá skutečnému exportu. Hlavičky z
`config/conversion/*.headers.csv` jsou pouze kanonické návrhy, nikoliv tvrzení
o existujícím formátu Pascalové databáze.

Zvlášť ověřit text „Příliš žluťoučký“, dlouhá čísla a úvodní nuly, záporné
částky, citované oddělovače, prázdné hodnoty, více PP a cizince. Windows-1250
neumí všechny světové znaky. Již nahrazené znaky ve jménech nelze obnovit;
neprovádět automatickou transliteraci odhadem. Chybějící údaje je nutné doplnit
z doloženého zdroje, případně výslovně použít podporovaný UTF-8 import.

K dokončení vazeb dodat strukturálně věrné anonymizované PP i souhrnné CSV,
seznam čísel položek s názvy a jednotkami, potvrzené vzorce, pravidla pro prázdné
a nulové hodnoty a referenční měsíční součty. Zachovat shody/rozpory osobních
klíčů a nuly při anonymizaci. Skutečná RČ a mzdová data neukládat do GitHubu.
