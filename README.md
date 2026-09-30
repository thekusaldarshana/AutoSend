# AutoSend

Send personalised WhatsApp messages to a whole list, straight from your Excel sheet. A personal Windows app with a modern
interface, built for non-technical users. English interface, full Sinhala message support.

## What it does
- **Send** to the students you tick, or to a **List**, with a random, human-like rhythm (random pauses, random batch sizes,
  breaks, "typing…", daily limit, sending hours). Pause, stop and resume at any time. Nobody is ever messaged twice.
- **Quick send**: type a message and send it, without saving a template.
- **Students**: a live view of your Excel file. Add, edit and delete students and the changes are written back to the
  file (with a backup). Edit the Excel file yourself and the app updates by itself.
- **Lists**: fixed lists and smart lists (rules such as *Class is Grade 9 A* or *Amount is greater than 30000*), including
  non-student contacts and import from Excel/CSV.
- **Templates** and **Variables**: write messages exactly as they should look (line breaks, `*bold*`, Sinhala), with
  `{Name}`, `{Class}`, `{Amount}`... filled in per person. Optional photo.
- **History** with filters (period, class, result), sorting, clearing and Excel export.
- Light and dark mode, and support for Sinhala typing tools such as Helakuru.

## Install (for users)
1. Download `AutoSend-Setup-1.0.0.exe` from the [latest release](../../releases/latest) and run it.
2. Open AutoSend and follow the welcome steps: choose your Excel file, then scan the QR code with WhatsApp
   (*Linked devices → Link a device*).

Requirements: **Windows 10 (version 1809) or 11, 64-bit**. Nothing else has to be installed: Python, the Visual C++
runtime and the Sinhala font are all included. The installer is unsigned, so Windows SmartScreen may show a warning
the first time (*More info → Run anyway*).

AutoSend is a **personal app**. It installs for the current Windows user only (no administrator rights, no "all users"
option), and its data stays in that user's own `%APPDATA%\AutoSend`.

## Build from source (for developers)
```powershell
py -m venv .venv
.venv\Scripts\python -m pip install PySide6 neonize openpyxl segno pyinstaller pytest pefile
powershell -ExecutionPolicy Bypass -File build.ps1
```
`build.ps1` runs the tests, packages the app into `dist\AutoSend\`, checks that it starts, and builds the installer into
`installer\output\`. It needs [Inno Setup](https://jrsoftware.org/isinfo.php). Run from source with
`.venv\Scripts\python run_autosend.py`.

The version number lives in one place, `autosend/__init__.py`; the build stamps it on the app and the installer.

| Folder | Contents |
|---|---|
| `autosend/core` | logic without any UI: Excel, phone numbers, templating, pacing, database, WhatsApp link, sending |
| `autosend/ui` | screens, dialogs, theme, the Sinhala typing-tool fix |
| `installer` | Inno Setup script |
| `assets/fonts` | bundled Sinhala font and its licence |
| `tests` | automated tests (they use a fictional sample sheet, never a real student list) |

Useful settings for testing: `AUTOSEND_DATA=<folder>` uses another data folder, `AUTOSEND_SMOKE=<seconds>` makes the app
quit by itself and `AUTOSEND_START_PAGE=<page>` opens a given page.

## Licences
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). AutoSend is not affiliated with WhatsApp or Meta.
