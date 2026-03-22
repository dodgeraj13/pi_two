"""
64x64 Weather display for rpi-rgb-led-matrix.

Reads OpenWeatherMap by default. Supports:
- --brightness 0..100
- --pixel-mapper Rotate:0|90|180|270 (capital R)
- --hardware-mapping adafruit-hat-pwm (default)
- --gpio-slowdown 2 (default)
- --emulated (optional RGBMatrixEmulator)

Config precedence:
1) CLI args override
2) Environment variables (WEATHER_API_KEY, WEATHER_LOCATION, WEATHER_UNITS, WEATHER_PROVIDER)
3) Optional INI at ./weather.ini [Weather] { api_key, location, units }

Location formats accepted:
- "City,CC"  (e.g., "Los Angeles,US")
- ZIP (US only), or
- "lat,lon" (e.g., "34.05,-118.24")

Units: "imperial" (\u00B0F), "metric" (\u00B0C)
"""

import os, sys, time, math, argparse, json, configparser, inspect, requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ---- Add rpi-rgb-led-matrix Python binding path (your confirmed location) ----
def _add_path(p: str):
    p = os.path.abspath(p)
    if os.path.exists(p) and p not in sys.path:
        sys.path.append(p)
_add_path("/home/pi_two/rpi-spotify-matrix-display/rpi-rgb-led-matrix/bindings/python")
# -----------------------------------------------------------------------------

# -------------------------- CLI & Config --------------------------
def parse_args():
    ap = argparse.ArgumentParser(prog="MatrixWeatherDisplay", description="Show current weather on 64x64 LED matrix")
    ap.add_argument("--emulated", action="store_true", help="Use RGBMatrixEmulator instead of hardware")
    ap.add_argument("--brightness", type=int, default=None, help="Matrix brightness 0..100")
    ap.add_argument("--pixel-mapper", type=str, default=None, help="Pixel mapper string, e.g. Rotate:90")
    ap.add_argument("--hardware-mapping", type=str, default="adafruit-hat-pwm")
    ap.add_argument("--gpio-slowdown", type=int, default=2)
    ap.add_argument("--update-interval", type=int, default=300, help="Weather refresh seconds (default 300)")
    return ap.parse_args()

def load_config():
    cfg = configparser.ConfigParser()
    here = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    ini_path = os.path.join(here, "weather.ini")
    if os.path.exists(ini_path):
        cfg.read(ini_path)
    section = cfg["Weather"] if "Weather" in cfg else {}
    api_key = os.getenv("WEATHER_API_KEY") or section.get("api_key", "")
    location = os.getenv("WEATHER_LOCATION") or section.get("location", "Los Angeles,US")
    units = os.getenv("WEATHER_UNITS") or section.get("units", "imperial")
    provider = os.getenv("WEATHER_PROVIDER") or section.get("provider", "openweathermap")
    return {"api_key": api_key, "location": location, "units": units, "provider": provider}

# -------------------------- Weather fetchers --------------------------
def _is_numberlike(s: str) -> bool:
    try:
        float(s); return True
    except Exception:
        return False

def parse_location(loc: str):
    loc = (loc or "").strip()
    if "," in loc:
        a, b = [x.strip() for x in loc.split(",", 1)]
        if _is_numberlike(a) and _is_numberlike(b):  # lat,lon
            return {"lat": a, "lon": b}
        return {"q": loc}  # city,country
    return {"q": loc}

def get_openweather(api_key: str, location: str, units: str):
    if not api_key:
        raise RuntimeError("OpenWeatherMap requires WEATHER_API_KEY")
    base = "https://api.openweathermap.org/data/2.5/weather"
    params = {"appid": api_key, "units": units}
    params.update(parse_location(location))
    r = requests.get(base, params=params, timeout=8)
    r.raise_for_status()
    data = r.json()
    name = data.get("name") or location
    main = data.get("weather", [{}])[0].get("main", "")
    desc = data.get("weather", [{}])[0].get("description", main)
    temp = data.get("main", {}).get("temp")
    icon = data.get("weather", [{}])[0].get("icon", "")
    return {
        "location": name,
        "temp": temp,
        "condition": (desc or "").title(),
        "icon": icon,
        "ts": int(time.time()),
    }

def fetch_weather(cfg):
    provider = (cfg["provider"] or "openweathermap").lower()
    if provider in ("owm", "openweather", "openweathermap"):
        return get_openweather(cfg["api_key"], cfg["location"], cfg["units"])
    raise RuntimeError(f"Unsupported provider: {provider}")

# -------------------------- Drawing --------------------------
def try_font(pref: str, size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        pref,
    ]
    for p in candidates:
        try:
            if p and os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def icon_from_code(code: str):
    canvas = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    if not code:
        d.ellipse((4,4,10,10), fill=(200,200,200,255)); return canvas
    head = code[:2]
    if head == "01":
        d.ellipse((4,4,10,10), fill=(255,210,0,255))
        for k in range(8):
            a = k * (math.pi/4)
            x1 = 7 + int(6*math.cos(a)); y1 = 7 + int(6*math.sin(a))
            x2 = 7 + int(3*math.cos(a)); y2 = 7 + int(3*math.sin(a))
            d.line((x1,y1,x2,y2), fill=(255,210,0,255))
    elif head in ("02","03","04"):
        d.ellipse((3,7,11,12), fill=(200,200,220,255))
        d.ellipse((5,5,9,10), fill=(220,220,235,255))
    elif head in ("09","10"):
        d.ellipse((3,7,11,12), fill=(180,180,200,255))
        d.ellipse((5,5,9,10), fill=(200,200,220,255))
        d.line((5,12,5,14), fill=(80,150,255,255))
        d.line((8,12,8,14), fill=(80,150,255,255))
    elif head == "11":
        d.ellipse((3,7,11,12), fill=(180,180,200,255))
        d.ellipse((5,5,9,10), fill=(200,200,220,255))
        d.polygon([(7,8),(6,12),(8,12),(7,14),(10,10),(8,10)], fill=(255,220,0,255))
    elif head == "13":
        d.ellipse((3,7,11,12), fill=(200,200,220,255))
        d.ellipse((5,5,9,10), fill=(220,220,235,255))
        for x in (5,9):
            d.text((x,12), "*", fill=(230,230,255,255))
    elif head == "50":
        for y in (7,10,13):
            d.line((3,y,11,y), fill=(180,180,200,200))
    else:
        d.ellipse((4,4,10,10), fill=(200,200,200,255))
    return canvas

def _measure(draw: "ImageDraw.ImageDraw", text: str, font):
    try:
        bbox = draw.textbbox((0,0), text, font=font)
        return (bbox[2]-bbox[0], bbox[3]-bbox[1])
    except Exception:
        try:
            return font.getsize(text)
        except Exception:
            return (len(text)*6, 8)

def draw_frame(state, cfg, wdata):
    W, H = 64, 64
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background gradient
    top = (10, 20, 60); bot = (5, 10, 30)
    for y in range(H):
        t = y/(H-1)
        col = tuple(int(top[i]*(1-t) + bot[i]*t) for i in range(3))
        d.line((0,y,W,y), fill=col)

    # Title
    small = try_font("", 8)
    d.text((2, 2), "Weather", font=small, fill=(200,220,255))

    # Temp big
    big = try_font("", 28)
    if wdata and wdata.get("temp") is not None:
        temp = round(wdata["temp"])
        units = (cfg["units"] or "").lower()
        unit_glyph = "\u00B0F" if units.startswith("imp") else "\u00B0C"
        text = f"{temp}{unit_glyph}"
    else:
        text = "--\u00B0"
    tw, th = _measure(d, text, big)
    d.text(((W - tw)//2, 20), text, font=big, fill=(255,255,255))

    # Condition + icon
    info = (wdata.get("condition") if wdata else None) or "No data"
    info = info[:18]
    icon = icon_from_code(wdata.get("icon") if wdata else "")
    img.paste(icon, (4, 44), icon)
    d.text((20, 44), info, font=small, fill=(220,235,255))

    # City
    city = (wdata.get("location") if wdata else cfg["location"]) or ""
    if city:
        city = str(city)
        cw, ch = _measure(d, city, small)
        if cw <= 60:
            d.text((2, 12), city, font=small, fill=(160,190,240))

    return img

# -------------------------- Matrix loop --------------------------
def main():
    args = parse_args()
    cfg = load_config()

    is_emulated = bool(args.emulated)

    if is_emulated:
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
    else:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

    opts = RGBMatrixOptions()
    opts.rows = 64
    opts.cols = 64
    opts.hardware_mapping = args.hardware_mapping
    if args.brightness is not None:
        opts.brightness = max(0, min(100, int(args.brightness)))
    opts.gpio_slowdown = int(args.gpio_slowdown)
    opts.limit_refresh_rate_hz = 0
    if args.pixel_mapper:
        opts.pixel_mapper_config = args.pixel_mapper
    opts.drop_privileges = False

    matrix = RGBMatrix(options=opts)

    last_fetch = 0
    cache = None
    interval = max(30, int(args.update_interval))
    draw_sleep = 0.08

    try:
        while True:
            now = time.time()
            if now - last_fetch > interval or not cache:
                try:
                    cache = fetch_weather(cfg)
                except Exception as e:
                    sys.stderr.write(f"[weather] fetch failed: {e}\n")
                finally:
                    last_fetch = now

            frame = draw_frame({}, cfg, cache)
            matrix.SetImage(frame)
            time.sleep(draw_sleep)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
