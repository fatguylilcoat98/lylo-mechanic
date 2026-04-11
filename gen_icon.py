from PIL import Image, ImageDraw, ImageFont
import math

size = 1024
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

NAVY = (12, 22, 45)
BLUE_TOP = (30, 120, 230)
BLUE_MID = (22, 100, 210)
BLUE_BOT = (15, 70, 170)
SILVER = (210, 218, 230)
SILVER_LIGHT = (235, 240, 248)
SILVER_DARK = (145, 155, 175)
YELLOW = (245, 195, 45)
YELLOW_LIGHT = (255, 215, 80)
YELLOW_DARK = (200, 155, 20)
ORANGE = (240, 130, 42)
ORANGE_DARK = (200, 100, 25)
WHITE = (255, 255, 255)
DARK_TEXT = (20, 25, 40)

cx = 512
shield_top = 100
shield_w = 420
shield_h = 540

# ── Shield outline (navy) ──
def shield_pts(cx, top, w, h, inset=0):
    mid_y = top + h * 0.65
    bot_y = top + h
    r = 35
    w2 = w // 2 - inset
    pts = []
    for a in range(180, 271):
        rad = math.radians(a)
        pts.append((cx - w2 + r + r * math.cos(rad), top + inset + r + r * math.sin(rad)))
    for a in range(270, 361):
        rad = math.radians(a)
        pts.append((cx + w2 - r + r * math.cos(rad), top + inset + r + r * math.sin(rad)))
    pts.append((cx + w2, mid_y))
    pts.append((cx + w2 - 15, mid_y + (bot_y - inset - mid_y) * 0.5))
    pts.append((cx, bot_y - inset))
    pts.append((cx - w2 + 15, mid_y + (bot_y - inset - mid_y) * 0.5))
    pts.append((cx - w2, mid_y))
    return pts

# Navy border
draw.polygon(shield_pts(cx, shield_top - 14, shield_w + 28, shield_h + 20), fill=NAVY)

# Gradient shield fill
grad = Image.new('RGBA', (size, size), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(grad)
for y in range(shield_top, shield_top + shield_h):
    p = (y - shield_top) / shield_h
    if p < 0.35:
        t = p / 0.35
        r = int(BLUE_TOP[0]*(1-t) + BLUE_MID[0]*t)
        g = int(BLUE_TOP[1]*(1-t) + BLUE_MID[1]*t)
        b = int(BLUE_TOP[2]*(1-t) + BLUE_MID[2]*t)
    else:
        t = (p - 0.35) / 0.65
        r = int(BLUE_MID[0]*(1-t) + BLUE_BOT[0]*t)
        g = int(BLUE_MID[1]*(1-t) + BLUE_BOT[1]*t)
        b = int(BLUE_MID[2]*(1-t) + BLUE_BOT[2]*t)
    gdraw.line([(0, y), (size, y)], fill=(r, g, b, 255))

mask = Image.new('L', (size, size), 0)
mdraw = ImageDraw.Draw(mask)
mdraw.polygon(shield_pts(cx, shield_top, shield_w, shield_h), fill=255)

grad_masked = Image.composite(grad, Image.new('RGBA', (size, size), (0,0,0,0)), mask)
img = Image.alpha_composite(img, grad_masked)
draw = ImageDraw.Draw(img)

# Inner navy border line
sp = shield_pts(cx, shield_top, shield_w, shield_h)
for _ in range(4):
    draw.polygon(sp, outline=NAVY)

# ── Wrench ──
def rot_rect(cx, cy, w, h, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    hw, hh = w/2, h/2
    return [(cx + x*c - y*s, cy + x*s + y*c) for x, y in [(-hw,-hh),(hw,-hh),(hw,hh),(-hw,hh)]]

angle = -38
wcx = cx + 10
wcy = shield_top + shield_h * 0.42

# Navy outlines
for off in [7, 5, 3]:
    draw.polygon(rot_rect(wcx, wcy, 300+off*2, 52+off*2, angle), fill=NAVY)
    jx = wcx + 140*math.cos(math.radians(angle))
    jy = wcy + 140*math.sin(math.radians(angle))
    draw.polygon(rot_rect(jx, jy, 82+off*2, 72+off*2, angle), fill=NAVY)

# Handle
draw.polygon(rot_rect(wcx, wcy, 300, 52, angle), fill=SILVER)
draw.polygon(rot_rect(wcx, wcy, 270, 14, angle), fill=SILVER_LIGHT)
draw.polygon(rot_rect(wcx-3, wcy+16, 270, 8, angle), fill=SILVER_DARK)

# Bottom cap
bcx = wcx + 155*math.cos(math.radians(angle+180))
bcy = wcy + 155*math.sin(math.radians(angle+180))
draw.ellipse([bcx-30, bcy-30, bcx+30, bcy+30], fill=NAVY)
draw.ellipse([bcx-26, bcy-26, bcx+26, bcy+26], fill=SILVER)
draw.ellipse([bcx-14, bcy-14, bcx+14, bcy+14], fill=SILVER_LIGHT)

# Head joint
jx = wcx + 140*math.cos(math.radians(angle))
jy = wcy + 140*math.sin(math.radians(angle))
draw.polygon(rot_rect(jx, jy, 80, 70, angle), fill=SILVER)
draw.polygon(rot_rect(jx, jy, 55, 18, angle), fill=SILVER_LIGHT)

# Open jaw prongs
for poff in [-32, 32]:
    pa = angle + poff
    pcx = jx + 48*math.cos(math.radians(pa))
    pcy = jy + 48*math.sin(math.radians(pa))
    draw.polygon(rot_rect(pcx, pcy, 80, 32, pa), fill=NAVY)
    draw.polygon(rot_rect(pcx, pcy, 74, 26, pa), fill=SILVER)
    draw.polygon(rot_rect(pcx, pcy, 56, 8, pa), fill=SILVER_LIGHT)

# ── Check Engine Light ──
cel_x, cel_y = cx, shield_top + 115
cel_r = 42

draw.ellipse([cel_x-cel_r-5, cel_y-cel_r-5, cel_x+cel_r+5, cel_y+cel_r+5], fill=NAVY)
draw.ellipse([cel_x-cel_r, cel_y-cel_r, cel_x+cel_r, cel_y+cel_r], fill=YELLOW)
draw.ellipse([cel_x-cel_r+8, cel_y-cel_r+6, cel_x+cel_r-8, cel_y-2], fill=YELLOW_LIGHT)

# Engine block
eb = 16
draw.rounded_rectangle([cel_x-eb, cel_y-eb+4, cel_x+eb, cel_y+eb], radius=3, fill=NAVY)
draw.rounded_rectangle([cel_x-eb+3, cel_y-eb+7, cel_x+eb-3, cel_y+eb-3], radius=2, fill=YELLOW_DARK)
for i in range(-1, 2):
    bx = cel_x + i*10
    draw.rectangle([bx-4, cel_y-eb-1, bx+4, cel_y-eb+6], fill=NAVY)
draw.line([(cel_x+eb+1, cel_y+3), (cel_x+eb+10, cel_y-3)], fill=NAVY, width=4)
draw.line([(cel_x+eb+10, cel_y-3), (cel_x+eb+16, cel_y+1)], fill=NAVY, width=4)
draw.rectangle([cel_x-eb-8, cel_y-2, cel_x-eb, cel_y+6], fill=NAVY)

# ── LYLO Text ──
try:
    font_lylo = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 110)
    font_mech = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 34)
except:
    font_lylo = ImageFont.load_default()
    font_mech = font_lylo

text_y = shield_top + shield_h * 0.52
for dx in [-3, -2, 0, 2, 3]:
    for dy in [-1, 0, 1, 2, 3]:
        draw.text((cx+dx, text_y+dy), "LYLO", fill=NAVY, font=font_lylo, anchor="mt")
draw.text((cx, text_y), "LYLO", fill=WHITE, font=font_lylo, anchor="mt")

# ── MECHANIC Banner ──
banner_y = shield_top + shield_h - 30
banner_h = 55
banner_w = 300

draw.rounded_rectangle(
    [cx-banner_w//2-4, banner_y-4, cx+banner_w//2+4, banner_y+banner_h+4],
    radius=10, fill=NAVY
)
draw.rounded_rectangle(
    [cx-banner_w//2, banner_y, cx+banner_w//2, banner_y+banner_h],
    radius=8, fill=ORANGE
)
draw.rounded_rectangle(
    [cx-banner_w//2+6, banner_y+3, cx+banner_w//2-6, banner_y+banner_h//2-2],
    radius=4, fill=(255, 150, 60, 80)
)

for dx in [-2, 0, 2]:
    for dy in [1, 2]:
        draw.text((cx+dx, banner_y+banner_h//2+dy), "MECHANIC", fill=ORANGE_DARK, font=font_mech, anchor="mm")
draw.text((cx, banner_y+banner_h//2), "MECHANIC", fill=DARK_TEXT, font=font_mech, anchor="mm")

# ── Save ──
img.save("C:/Users/Stang/lylo-mechanic/mobile/assets/icon.png")

adaptive = Image.new("RGBA", (1024, 1024), (10, 12, 15, 255))
m = 60
sm = img.resize((size-m*2, size-m*2), Image.LANCZOS)
adaptive.paste(sm, (m, m), sm)
adaptive.save("C:/Users/Stang/lylo-mechanic/mobile/assets/adaptive-icon.png")

img.save("C:/Users/Stang/lylo-mechanic/mobile/assets/splash-icon.png")
print("Emblem icon generated!")
