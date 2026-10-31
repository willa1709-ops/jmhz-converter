from pathlib import Path
JMHZ_VARIANT = 'win7-x86'
common = Path(SPECPATH).parent / 'freeze_common.py'
exec(compile(common.read_text(encoding='utf-8'), str(common), 'exec'), globals())
