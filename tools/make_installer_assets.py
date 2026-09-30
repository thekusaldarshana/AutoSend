"""Starter Excel + branded wizard images for the Inno Setup installer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from autosend.core.excel import write_starter_workbook

out = ROOT / "installer"
out.mkdir(exist_ok=True)
write_starter_workbook(str(out / "Students.xlsx"))

icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")

def gradient(w, h, c1, c2):
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            t = (x / w * 0.35 + y / h * 0.65)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return im

def font(sz, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except OSError:
            pass
    return ImageFont.load_default()

# big side image 164x314 (shown at 100% DPI; Inno scales for higher DPI)
W, H = 328, 628
big = gradient(W, H, (10, 143, 76), (34, 197, 94))
ic = icon.resize((150, 150), Image.LANCZOS)
big.paste(ic, ((W - 150) // 2, 120), ic)
d = ImageDraw.Draw(big)
d.text((W // 2, 320), "AutoSend", font=font(44, True), fill="white", anchor="mm")
d.text((W // 2, 372), "WhatsApp messages,\nautomated", font=font(24), fill=(230, 255, 240), anchor="mm", align="center")
big.resize((164, 314), Image.LANCZOS).save(out / "wizard_big.bmp")

# small header image 55x58
small = Image.new("RGB", (110, 116), "white")
ic2 = icon.resize((96, 96), Image.LANCZOS)
small.paste(ic2, (7, 10), ic2)
small.resize((55, 58), Image.LANCZOS).save(out / "wizard_small.bmp")
print("installer assets ok")
