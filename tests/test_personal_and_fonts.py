"""AutoSend is a personal app (one user, never shared) and carries its own Sinhala font."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
from autosend.ui import fonts, theme

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / "installer" / "AutoSend.iss").read_text(encoding="utf-8-sig")


# ------------------------------------------------------------------ fonts
def test_bundled_font_files_and_licence_are_present():
    d = ROOT / "assets" / "fonts"
    for name in (*fonts.BUNDLED_FILES, "OFL.txt", "README.txt"):
        assert (d / name).is_file(), name
    assert "SIL OPEN FONT LICENSE" in (d / "OFL.txt").read_text(encoding="utf-8", errors="ignore").upper()


def test_bundled_font_loads_and_covers_every_sinhala_conjunct_part():
    assert fonts.load_bundled_fonts() == [fonts.SINHALA_FAMILY]
    assert QFontDatabase.WritingSystem.Sinhala in QFontDatabase.writingSystems(fonts.SINHALA_FAMILY)
    fm = QFontMetricsF(QFont(fonts.SINHALA_FAMILY, 12))
    needed = {"ka": 0x0D9A, "ra": 0x0DBB, "ya": 0x0DBA, "virama": 0x0DCA, "ZWJ": 0x200D, "ae-pilla": 0x0DD0,
              "long ae-pilla": 0x0DD1, "aa-pilla": 0x0DCF, "i-pilla": 0x0DD2, "kombuva": 0x0DD9, "ma": 0x0DB8}
    missing = [n for n, cp in needed.items() if not fm.inFontUcs4(cp)]
    assert not missing, missing


def test_sinhala_shapes_from_the_bundled_font_alone():
    """A conjunct (ක් + ZWJ + ර) must come out as one shaped cluster, not letters side by side."""
    fonts.load_bundled_fonts()
    f = QFont(fonts.SINHALA_FAMILY, 20)
    fm = QFontMetricsF(f)
    apart = fm.horizontalAdvance("ක") + fm.horizontalAdvance("ර")
    joined = fm.horizontalAdvance("ක්‍ර")
    assert 0 < joined < apart * 1.2                       # shaped as one cluster (not a virama and a letter beside each other)


def test_the_app_prefers_its_own_sinhala_font_over_windows_ones():
    for fams in (theme.UI_FAMILIES, ):
        assert fams.index(fonts.SINHALA_FAMILY) < fams.index("Nirmala UI")
    fams = theme.mono_message_font().families()
    assert fams.index(fonts.SINHALA_FAMILY) < fams.index("Nirmala UI")


def test_fonts_are_packaged_with_the_app():
    spec = (ROOT / "autosend.spec").read_text(encoding="utf-8")
    assert '"assets/fonts"' in spec


# ------------------------------------------------------- installer: personal
def setup_value(key):
    m = re.search(rf"^{key}=(.*)$", ISS, re.M)
    return m.group(1).strip() if m else None


def test_installer_is_per_user_with_no_way_to_make_it_shared():
    assert setup_value("PrivilegesRequired") == "lowest"
    assert setup_value("PrivilegesRequiredOverridesAllowed") is None           # no "install for all users" choice
    assert setup_value("DisableDirPage") == "yes"                                # nobody can point it at a shared folder
    assert setup_value("DefaultDirName").startswith("{localappdata}")            # inside the person's own profile


def test_installer_uses_only_this_users_places():
    shared = ("{commonpf", "{autopf", "{commonappdata}", "{commondesktop}", "{commonprograms}", "{autodesktop}",
              "{autoprograms}", "{group}", "{commonstartup}", "{commonfonts}", "{commondocs}")
    code = re.sub(r"^\s*;.*$", "", ISS, flags=re.M)                              # ignore comments
    assert not [s for s in shared if s in code]
    assert "{userdesktop}" in code and "{userprograms}" in code and "{userdocs}" in code and "{autofonts}" in code


def test_font_is_installed_only_when_missing_and_removed_on_uninstall():
    lines = [l for l in ISS.splitlines() if "NotoSansSinhala" in l and l.lstrip().startswith("Source")]
    assert len(lines) == 2
    for l in lines:
        assert "FontInstall:" in l and "Check: NeedSinhalaFont" in l and "onlyifdoesntexist" in l
        assert "uninsneveruninstall" not in l                                    # so uninstall removes what we installed
    assert "InitializeSetup" in ISS and "FontRegistered('Noto Sans Sinhala')" in ISS


def test_app_data_is_per_user_and_removed_only_for_that_user():
    assert "{userappdata}\\{#AppName}" in ISS
    assert "HKLM" in ISS and ISS.count("HKLM") == 1                              # only to READ whether the font exists


def test_installer_only_runs_where_per_user_fonts_and_the_built_in_icu_library_exist():
    assert setup_value("MinVersion") == "10.0.17763"                            # Windows 10 version 1809
    assert setup_value("ArchitecturesAllowed") == "x64compatible"
