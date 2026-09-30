"""Fonts that travel with the app, so Sinhala looks the same on every computer.

Noto Sans Sinhala (SIL Open Font License, see assets/fonts/OFL.txt) is loaded from the app's own folder every time it
starts. Nothing has to be installed on the PC for that. (The installer also installs it for the current user when it
is missing, so other programs can use it too.)
"""
from __future__ import annotations

from ..core import paths

BUNDLED_FILES = ("NotoSansSinhala-Regular.ttf", "NotoSansSinhala-Bold.ttf")
SINHALA_FAMILY = "Noto Sans Sinhala"


def load_bundled_fonts() -> list[str]:
    """Register the bundled fonts with Qt. Returns the family names that were loaded."""
    from PySide6.QtGui import QFontDatabase

    families: list[str] = []
    folder = paths.resource_path("assets/fonts")
    for name in BUNDLED_FILES:
        font_id = QFontDatabase.addApplicationFont(str(folder / name))
        if font_id >= 0:
            for fam in QFontDatabase.applicationFontFamilies(font_id):
                if fam not in families:
                    families.append(fam)
    return families
