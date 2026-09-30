"""Generate assets/icon.png + icon.ico (green rounded square with a paper plane)."""
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath

app = QGuiApplication(sys.argv)
out = Path(__file__).resolve().parents[1] / "assets"
out.mkdir(exist_ok=True)
S = 512
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setRenderHint(QPainter.TextAntialiasing)
g = QLinearGradient(0, 0, S, S)
g.setColorAt(0, QColor("#22C55E")); g.setColorAt(1, QColor("#0A8F4C"))
path = QPainterPath(); path.addRoundedRect(QRectF(16, 16, S - 32, S - 32), 112, 112)
p.fillPath(path, g)
f = QFont(); f.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"]); f.setPixelSize(280)
p.setFont(f); p.setPen(QColor("white"))
p.drawText(QRectF(0, 0, S, S), Qt.AlignCenter, "")
p.end()
img.save(str(out / "icon.png"))
from PIL import Image
Image.open(out / "icon.png").save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
