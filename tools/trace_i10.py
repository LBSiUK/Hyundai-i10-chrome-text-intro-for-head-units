"""Trace ref/i10-plain.png into assets/i10.svg with smooth outlines.

Upscale 4x, blur, then threshold, so potrace sees a smooth edge instead of
the stair-steps of the 600 px source.
"""
import subprocess, sys
from PIL import Image, ImageFilter

src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("L")
im = im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
im = im.filter(ImageFilter.GaussianBlur(5))
im = im.point(lambda v: 0 if v < 128 else 255).convert("1")
bmp = out.replace(".svg", ".bmp")
im.save(bmp)
subprocess.run(["potrace", "-s", "-t", "40", "-a", "1.2", "-O", "0.8", "-o", out, bmp], check=True)
