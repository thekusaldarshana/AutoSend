"""Write version_info.txt (the exe's file properties) from the one true version in autosend/__init__.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autosend import __version__

parts = [int(p) for p in __version__.split(".")]
parts += [0] * (4 - len(parts))
tup = ", ".join(str(p) for p in parts)
dotted = ".".join(str(p) for p in parts)

(ROOT / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'AutoSend'),
      StringStruct('FileDescription', 'AutoSend - WhatsApp messages, automated'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', 'AutoSend'),
      StringStruct('OriginalFilename', 'AutoSend.exe'),
      StringStruct('ProductName', 'AutoSend'),
      StringStruct('ProductVersion', '{dotted}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print("version_info.txt ->", dotted)
