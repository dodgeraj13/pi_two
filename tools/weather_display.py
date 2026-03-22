#!/usr/bin/env python3
# Placeholder weather face; replace with your API logic anytime.
import sys, time, signal
from PIL import Image, ImageDraw, ImageFont
from rgbmatrix import RGBMatrix, RGBMatrixOptions

running=True
def handle_sigterm(a,b):
    global running; running=False
signal.signal(signal.SIGTERM, handle_sigterm)

brightness = int(sys.argv[1]) if len(sys.argv)>1 else 60
options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.gpio_mapping = "adafruit-hat-pwm"
options.brightness = max(0, min(100, brightness))
options.hardware_mapping = "adafruit-hat-pwm"
options.gpio_slowdown = 2
matrix = RGBMatrix(options = options)

font = ImageFont.load_default()
t=0
while running:
    img = Image.new("RGB",(64,64))
    d = ImageDraw.Draw(img)
    # fake temp + icon
    temp = 72 + ((t//5)%5)  # cycles 72..76
    icon = "?" if (t//20)%2==0 else "?"
    d.text((2,8), f"{icon}", fill=(255,255,0))
    d.text((2,36), f"{temp}°F", fill=(255,255,255), font=font)
    matrix.SetImage(img.convert('RGB'))
    time.sleep(0.5)
    t+=1
