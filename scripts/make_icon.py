"""Generate the application icon (assets/fbosint.ico + .png) with Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parents[1] / "assets"
out.mkdir(exist_ok=True)
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=110, fill=(31, 58, 95, 255))
d.ellipse([110, 110, 330, 330], outline=(255, 255, 255, 255), width=40)
d.line([300, 300, 410, 410], fill=(79, 179, 255, 255), width=56)
d.ellipse([382, 382, 438, 438], fill=(79, 179, 255, 255))
img.save(out / "fbosint.png")
img.save(out / "fbosint.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon written to", out)
