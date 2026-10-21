"""Stack PNGs into one labelled contact sheet: sheet.py out.png a.png b.png ..."""
import sys
from PIL import Image, ImageDraw
out, paths = sys.argv[1], sys.argv[2:]
ims = [Image.open(p).convert("RGB") for p in paths]
w = max(i.width for i in ims)
sheet = Image.new("RGB", (w, sum(i.height + 4 for i in ims)), (60, 0, 0))
y = 0
for p, im in zip(paths, ims):
    sheet.paste(im, (0, y))
    ImageDraw.Draw(sheet).text((6, y + 4), p.split("/")[-2] + " " + p.split("/")[-1], fill=(255, 80, 80))
    y += im.height + 4
sheet.save(out)
