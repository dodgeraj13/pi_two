#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, math, argparse, gc

def _add_path(p: str):
    p = os.path.abspath(p)
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)
_add_path("/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/bindings/python")

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

FONT_ROOTS = [
    "/home/pi_two/mlb-led-scoreboard/assets/fonts/patched",
    "/home_pi_two/mlb-led-scoreboard/assets/fonts".replace("_",""),
    "/home/pi_two/mlb-led-scoreboard/rpi-rgb-led-matrix/fonts",
    "/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/fonts",
    "/home/pi_two/rpi-rgb-led-matrix/fonts",
]
LABEL_BDFS = ["7x13.bdf","6x12.bdf","6x10.bdf","5x8.bdf"]

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
    ap = argparse.ArgumentParser(prog="MatrixAnalogClock")
    ap.add_argument("--brightness", type=int, default=None)
    ap.add_argument("--pixel-mapper", type=str, default=None)   # e.g. Rotate:90
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

def draw_face(canvas):
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

def draw_labels(canvas, fnt):
    white = graphics.Color(220, 230, 255)
    def tw(txt): return graphics.DrawText(canvas, fnt, -9999, -9999, white, txt)
    w12 = tw("12"); graphics.DrawText(canvas, fnt, 32 - w12//2, 14, white, "12")
    w3  = tw("3");  graphics.DrawText(canvas, fnt, 64 - 6 - w3,  35, white, "3")
    w6  = tw("6");  graphics.DrawText(canvas, fnt, 32 - w6//2,  61, white, "6")
    graphics.DrawText(canvas, fnt, 6, 35, white, "9")

def draw_hands(canvas, hour, minute):
    cx, cy = 32, 32
    hour_col   = graphics.Color(255, 210, 120)
    minute_col = graphics.Color(120, 200, 255)
    center_col = graphics.Color(255, 255, 255)
    minute_angle = (minute % 60) * 6
    hour_angle   = ((hour % 12) + minute/60.0) * 30
    ma = minute_angle - 90
    ha = hour_angle   - 90
    min_len = 26
    hr_len  = 18
    mx,my = polar_point(cx, cy, min_len, ma)
    hx,hy = polar_point(cx, cy, hr_len,  ha)
    graphics.DrawLine(canvas, cx, cy, hx, hy, hour_col)    # hour
    graphics.DrawLine(canvas, cx, cy, mx, my, minute_col)  # minute
    graphics.DrawCircle(canvas, cx, cy, 1, center_col)     # center cap

def draw_frame(off, fnt):
    clear_canvas(off)
    draw_face(off)
    draw_labels(off, fnt)
    t = time.localtime()
    draw_hands(off, t.tm_hour, t.tm_min)

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
    off = matrix.CreateFrameCanvas()   # <-- create ONCE and reuse
    fnt = load_font(LABEL_BDFS)

    last_hb = 0.0
    frame_ctr = 0
    try:
        while True:
            now = time.time()
            if now - last_hb > 30.0:
                try:
                    with open("/tmp/matrix-heartbeat-3","w") as f:
                        f.write(str(now))
                except Exception:
                    pass
                last_hb = now

            try:
                draw_frame(off, fnt)
                off = matrix.SwapOnVSync(off)  # <-- reuse returned buffer
            except Exception as e:
                sys.stderr.write(f"[clock] draw error: {e}\n")

            frame_ctr += 1
            if frame_ctr % 600 == 0:    # every ~5 minutes at 0.5s/frame
                gc.collect()

            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
