#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, math, argparse, gc, json, requests
from pathlib import Path

def _add_path(p: str):
    p = os.path.abspath(p)
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)
_add_path("/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/bindings/python")

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageFont, ImageDraw

FONT_ROOTS = [
    "/home/pi_two/mlb-led-scoreboard/assets/fonts/patched",
    "/home_pi_two/mlb-led-scoreboard/assets/fonts".replace("_",""),
    "/home/pi_two/mlb-led-scoreboard/rpi-rgb-led-matrix/fonts",
    "/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/fonts",
    "/home/pi_two/rpi-rgb-led-matrix/fonts",
]
LABEL_BDFS = ["7x13.bdf","6x12.bdf","6x10.bdf","5x8.bdf"]

BACKEND_URL = os.environ.get("BACKEND_URL", "https://matrix-backend-lv4k.onrender.com")

def find_font_path(candidates):
    for root in FONT_ROOTS:
        for name in candidates:
            p = os.path.join(root, name)
            if os.path.exists(p):
                return p
    return None

def load_font(candidates):
    f = graphics.Font()
    p = find_font_path(candidates)
    if p:
        f.LoadFont(p); return f
    pf = find_font_path(["6x10.bdf"]) or find_font_path(["5x8.bdf"])
    if pf: f.LoadFont(pf)
    return f

def parse_args():
    ap = argparse.ArgumentParser(prog="MatrixClock")
    ap.add_argument("--brightness", type=int, default=None)
    ap.add_argument("--pixel-mapper", type=str, default=None)
    ap.add_argument("--hardware-mapping", type=str, default="adafruit-hat-pwm")
    ap.add_argument("--gpio-slowdown", type=int, default=2)
    return ap.parse_args()

def clear_canvas(canvas):
    black = graphics.Color(0,0,0)
    for y in range(64):
        graphics.DrawLine(canvas, 0, y, 63, y, black)

def polar_point(cx, cy, r, deg):
    a = math.radians(deg)
    return (cx + int(round(r*math.cos(a))), cy + int(round(r*math.sin(a))))

def draw_analog_clock(canvas, fnt):
    """Draw analog clock face with hour/minute hands"""
    cx, cy = 32, 32
    ring = graphics.Color(220, 230, 255)
    tick = graphics.Color(180, 190, 210)
    graphics.DrawCircle(canvas, cx, cy, 30, ring)
    for m in range(60):
        ang = m * 6
        r1 = 27 if m % 5 == 0 else 29
        r2 = 30
        x1,y1 = polar_point(cx, cy, r1, ang - 90)
        x2,y2 = polar_point(cx, cy, r2, ang - 90)
        c = ring if m % 5 == 0 else tick
        graphics.DrawLine(canvas, x1,y1, x2,y2, c)

    # Hour numbers
    white = graphics.Color(220, 230, 255)
    def tw(txt): return graphics.DrawText(canvas, fnt, -9999, -9999, white, txt)
    w12 = tw("12"); graphics.DrawText(canvas, fnt, 32 - w12//2, 14, white, "12")
    w3  = tw("3");  graphics.DrawText(canvas, fnt, 64 - 6 - w3,  35, white, "3")
    w6  = tw("6");  graphics.DrawText(canvas, fnt, 32 - w6//2,  61, white, "6")
    graphics.DrawText(canvas, fnt, 6, 35, white, "9")

    # Draw hands
    t = time.localtime()
    hour_angle = ((t.tm_hour % 12) + t.tm_min/60.0) * 30 - 90
    min_angle = (t.tm_min % 60) * 6 - 90

    hour_col = graphics.Color(255, 210, 120)
    min_col = graphics.Color(120, 200, 255)
    center_col = graphics.Color(255, 255, 255)

    # Minute hand
    mx, my = polar_point(cx, cy, 26, min_angle)
    graphics.DrawLine(canvas, cx, cy, mx, my, min_col)

    # Hour hand
    hx, hy = polar_point(cx, cy, 18, hour_angle)
    graphics.DrawLine(canvas, cx, cy, hx, hy, hour_col)

    # Center dot
    graphics.DrawCircle(canvas, cx, cy, 1, center_col)

def draw_digital_clock(canvas, fnt):
    """Draw digital clock using PIL for better font rendering"""
    # Create a PIL image for digital display
    img = Image.new("RGB", (64, 64), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    t = time.localtime()
    time_str = time.strftime("%I:%M", t)
    date_str = time.strftime("%m/%d", t)

    # Load larger font for time
    try:
        time_font = ImageFont.truetype("fonts/6x12.bdf", 12)
    except:
        try:
            time_font = ImageFont.truetype("/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/fonts/6x12.bdf", 12)
        except:
            time_font = ImageFont.load_default()

    # Draw time centered
    bbox = draw.textbbox((0, 0), time_str, font=time_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (64 - tw) // 2
    y = (64 - th) // 2 - 4
    draw.text((x, y), time_str, fill=(255, 255, 255), font=time_font)

    # Draw date below
    date_bbox = draw.textbbox((0, 0), date_str, font=time_font)
    dw = date_bbox[2] - date_bbox[0]
    dx = (64 - dw) // 2
    draw.text((dx, y + th + 4), date_str, fill=(150, 150, 150), font=time_font)

    # Copy to rgbmatrix canvas
    for y in range(64):
        for x in range(64):
            r, g, b = img.getpixel((x, y))
            if r > 0 or g > 0 or b > 0:
                graphics.SetPixel(canvas, x, y, r, g, b)

def fetch_clock_settings():
    """Fetch clock type setting from backend"""
    try:
        resp = requests.get(f"{BACKEND_URL}/clock-settings", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("clock_type", "digital")
    except Exception as e:
        pass
    return "digital"

def main():
    args = parse_args()
    opts = RGBMatrixOptions()
    opts.rows = 64; opts.cols = 64
    opts.hardware_mapping = args.hardware_mapping
    if args.brightness is not None:
        opts.brightness = max(0, min(100, int(args.brightness)))
    opts.gpio_slowdown = int(args.gpio_slowdown)
    opts.limit_refresh_rate_hz = 0
    if args.pixel_mapper:
        opts.pixel_mapper_config = args.pixel_mapper
    opts.drop_privileges = False

    matrix = RGBMatrix(options=opts)
    off = matrix.CreateFrameCanvas()
    fnt = load_font(LABEL_BDFS)

    last_hb = 0.0
    last_settings_fetch = 0.0
    clock_type = "digital"
    frame_ctr = 0

    try:
        while True:
            now = time.time()

            # Heartbeat
            if now - last_hb > 30.0:
                try:
                    with open("/tmp/matrix-heartbeat-3","w") as f:
                        f.write(str(now))
                except Exception:
                    pass
                last_hb = now

            # Fetch settings periodically (every 30 seconds)
            if now - last_settings_fetch > 30.0:
                clock_type = fetch_clock_settings()
                last_settings_fetch = now

            try:
                clear_canvas(off)
                if clock_type == "analog":
                    draw_analog_clock(off, fnt)
                else:
                    draw_digital_clock(off, fnt)
                off = matrix.SwapOnVSync(off)
            except Exception as e:
                sys.stderr.write(f"[clock] draw error: {e}\n")

            frame_ctr += 1
            if frame_ctr % 600 == 0:
                gc.collect()

            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
