# -*- coding: utf-8 -*-
"""NanoCode 图标：黑底白字 </> 紧凑聚拢版，逐字符紧排居中"""
import os
from PIL import Image, ImageDraw, ImageFont

S = 1024
img = Image.new("RGBA", (S, S), (11, 13, 17, 255))
d = ImageDraw.Draw(img)

font_path = None
for p in (r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\consola.ttf",
          r"C:\Windows\Fonts\arialbd.ttf"):
    if os.path.isfile(p):
        font_path = p
        break
font = ImageFont.truetype(font_path, 580)

chars = ["<", "/", ">"]
glyphs = []
x_cursor = 0
GAP = -40  # 负间隙 = 字符往一起贴，更紧凑
for ch in chars:
    bbox = d.textbbox((0, 0), ch, font=font)
    w = bbox[2] - bbox[0]
    glyphs.append((ch, bbox, x_cursor))
    x_cursor += w + GAP
total_w = x_cursor - GAP
bbox_all = d.textbbox((0, 0), "".join(chars), font=font)
h = bbox_all[3] - bbox_all[1]
x = (S - total_w) // 2
y = (S - h) // 2 - bbox_all[1]
for ch, bbox, off in glyphs:
    d.text((x + off - bbox[0], y), ch, font=font, fill=(255, 255, 255, 255))

base = r"D:\CppIDE\icons"
for f in os.listdir(base):
    p = os.path.join(base, f)
    if os.path.isfile(p) and f != "ctps.ico":
        os.remove(p)
ico = os.path.join(base, "ctps.ico")
img.save(ico, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                   (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save(os.path.join(base, "ctps.png"))
print("glyph total width:", total_w, "/", S)
print("ICO:", os.path.getsize(ico), "bytes;  icons dir:", sorted(os.listdir(base)))
