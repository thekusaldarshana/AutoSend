"""The version must read 1.0.0 everywhere, and stay identical everywhere."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autosend import __version__

RELEASE = "1.0.0"


def test_the_release_is_1_0_0():
    assert __version__ == RELEASE


def test_installer_default_matches():
    iss = (ROOT / "installer" / "AutoSend.iss").read_text(encoding="utf-8")
    assert re.search(r'#define AppVersion "([^"]+)"', iss).group(1) == __version__
    assert "AppVersion={#AppVersion}" in iss and "OutputBaseFilename=AutoSend-Setup-{#AppVersion}" in iss


def test_exe_file_properties_match():
    v = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    dotted = __version__ + ".0"
    assert f"filevers=({', '.join(dotted.split('.'))})" in v and f"prodvers=({', '.join(dotted.split('.'))})" in v
    assert re.findall(r"'(?:File|Product)Version', '([^']+)'", v) == [dotted, dotted]


def test_no_other_version_number_is_hard_coded_in_the_app():
    for f in (ROOT / "autosend").rglob("*.py"):
        if f.name == "__init__.py" and f.parent.name == "autosend":
            continue
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\b1\.[0-9]+\.[0-9]+\b", text), f"{f.name} hard-codes a version number"
