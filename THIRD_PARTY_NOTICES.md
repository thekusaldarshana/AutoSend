# Third-party software in AutoSend

AutoSend's installer includes the following open-source components. Each keeps its own licence.

| Component | Used for | Licence |
|---|---|---|
| [Qt 6 / PySide6](https://pyside.org) | the window, buttons, tables and text editor | LGPL-3.0 |
| [neonize](https://github.com/krypton-byte/neonize) | Python bridge to the WhatsApp Web protocol | Apache-2.0 |
| [whatsmeow](https://github.com/tulir/whatsmeow) (compiled into neonize's native library) | the WhatsApp Web protocol itself | MPL-2.0 |
| [protobuf](https://github.com/protocolbuffers/protobuf) | message encoding | BSD-3-Clause |
| [openpyxl](https://openpyxl.readthedocs.io) and et_xmlfile | reading and writing Excel files | MIT |
| [segno](https://github.com/heuer/segno) | drawing the QR code | BSD-3-Clause |
| [Pillow](https://python-pillow.org) | image handling | MIT-CMU |
| [phonenumbers](https://github.com/daviddrysdale/python-phonenumbers) | pulled in by neonize | Apache-2.0 |
| [tqdm](https://tqdm.github.io) | pulled in by neonize | MPL-2.0 AND MIT |
| [Python](https://www.python.org) runtime | runs the app (bundled, so nothing needs installing) | PSF-2.0 |
| [PyInstaller](https://pyinstaller.org) | packaging the app | GPL-2.0-or-later with the bootloader exception, which allows the packaged app to be distributed under any licence |
| [Noto Sans Sinhala](https://github.com/notofonts/sinhala) v3.000 | Sinhala text, installed if the PC has no copy | SIL Open Font License 1.1 (`assets/fonts/OFL.txt`) |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | building the installer | Inno Setup License |

## Qt (LGPL-3.0)
AutoSend uses Qt through PySide6 as separate, unmodified DLL files in the install folder
(`_internal\PySide6`). You can replace them with another build of the same Qt version. The Qt source code is available from
<https://code.qt.io> and <https://pyside.org>.

## Not affiliated
AutoSend is an independent project. It is not affiliated with, endorsed by or connected to WhatsApp or Meta.
