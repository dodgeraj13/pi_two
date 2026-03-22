#!/usr/bin/env python3
# Shows a static image scaled to 64x64. Put your image at /home/pi_two/tools/picture.jpg
import sys, time, signal, os
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions

running=True
def handle_sigterm(a,b):
    global running; running=False
signal.signal(signal.SIGTERM, handle_sigterm)

brightness = int(sys.argv[1]) if len(sys.argv)>1 else 60
img_path = os.environ.get("MATRIX_PICTURE", "/home/pi_two/tools/picture.jpg")

options = RGBMatrixOptions()
options.rows = 64
options.cols = 64
options.gpio_mapping = "adafruit-hat-pwm"
options.brightness = max(0, min(100, brightness))
options.hardware_mapping = "adafruit-hat-pwm"
options.gpio_slowdown = 2
matrix = RGBMatrix(options = options)

if not os.path.exists(img_path):
    # simple color bars if no image
    img = Image.new("RGB",(64,64))
    for y in range(64):
        for x in range(64):
            img.putpixel((x,y),(x*4%256,y*4%256,(x+y)*2%256))
else:
    img = Image.open(img_path).convert("RGB").resize((64,64))

matrix.SetImage(img)
# keep the process alive until stopped (so controller can SIGTERM it)
while running:
    time.sleep(0.5)

