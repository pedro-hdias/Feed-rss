"""Gera assets/icon.ico (símbolo de feed: ponto e dois arcos sobre fundo laranja).

Uso: pip install pillow && python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
ORANGE, WHITE = (230, 105, 0, 255), (255, 255, 255, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=48, fill=ORANGE)
cx, cy = 70, SIZE - 70                       # origem dos arcos (canto inferior esquerdo)
d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=WHITE)
for radius in (80, 140):
    d.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=270, end=360, fill=WHITE, width=26)

out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Gerado", out)
