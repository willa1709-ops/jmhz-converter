from pathlib import Path
JMHZ_VARIANT = 'win11-x64'
common = Path(SPECPATH).parent / 'freeze_common.py'
exec(compile(common.read_text(encoding='utf-8'), str(common), 'exec'), globals())
