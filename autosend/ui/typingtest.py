"""A small diagnostic: shows exactly which characters your keyboard delivers to the app."""
from __future__ import annotations

import unicodedata

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from . import theme
from .widgets import button, label


def describe(text: str) -> str:
    """One line per character: code, name."""
    rows = []
    for ch in text:
        if ch == "\n":
            rows.append("U+000A  (new line)")
            continue
        name = unicodedata.name(ch, "(unnamed)")
        rows.append(f"U+{ord(ch):04X}  {name}")
    return "\n".join(rows)


class TypingTestDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Typing test")
        self.setMinimumSize(720, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Typing test", "h2"))
        lay.addWidget(label("Type something here, especially the letters that go wrong. The list below shows exactly which "
                            "characters arrived. If a conjunct looks wrong, this tells us whether the keyboard sent the wrong "
                            "characters or the app drew them wrongly.", "muted", wrap=True))
        self.edit = QPlainTextEdit()
        self.edit.setFont(theme.mono_message_font(16))
        self.edit.setFixedHeight(120)
        self.edit.setPlaceholderText("Type here…")
        lay.addWidget(self.edit)
        self.count = label("", "h3")
        lay.addWidget(self.count)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(theme.mono_message_font(10))
        lay.addWidget(self.out, 1)
        row = QHBoxLayout()
        copy = button("Copy this list", "", "copy")
        copy.clicked.connect(self._copy)
        close = button("Close")
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.edit.textChanged.connect(self._update)
        self._update()
        self.edit.setFocus()

    def _update(self):
        t = self.edit.toPlainText()
        self.count.setText(f"{len(t)} character{'s' if len(t) != 1 else ''} received")
        self.out.setPlainText(describe(t))

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.edit.toPlainText() + "\n\n" + self.out.toPlainText())
