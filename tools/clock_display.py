#!/usr/bin/env python3
# Simple digital clock using rgbmatrix + PIL
import sys, time, signal
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions

running = True
def handle_sigterm(a,b): 
    global running; running=False
signal.signal(signal.SIGTERM, handle_sigterm)

brightness = int(sys.argv[1]) if len(sys.argv) > 1 else 60
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.gpio_mapping = "adafruit-hat-pwm"
options.brightness = max(0, min(100, brightness))
options.hardware_mapping = "adafruit-hat-pwm"
options.gpio_slowdown = 2
matrix = RGBMatrix(options = options)

font = ImageFont.load_default()
while running:
    img = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(img)
    now = datetime.now().strftime("%-I:%M:%S")  # e.g., 7:05:12
    w, h = draw.textsize(now, font=font)
    draw.text(((64-w)//2, (64-h)//2), now, fill=(255,255,255), font=font)
    matrix.SetImage(img.convert('RGB'))
    time.sleep(0.2)
