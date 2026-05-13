#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Map mode display (mode 9).

Shows:
  - Scrolling destination name
  - Current temperature at destination (large)
  - Low / High temps
  - Estimated drive time (via OSRM — free, no key)

Env vars:
  MAP_ADDRESS_A   origin address  (e.g. "San Francisco, CA")
  MAP_ADDRESS_B   destination     (e.g. "Los Angeles, CA")
  WEATHER_API_KEY OpenWeatherMap API key
  WEATHER_UNITS   imperial | metric   (default: imperial)
"""

import os, sys, time, requests

# ── Matrix binding path ───────────────────────────────────────────────────────
_HOME = os.getenv("HOME", "/home/pi_two")
for _p in [
    f"{_HOME}/rpi-spotify-matrix-display/rpi-rgb-led-matrix/bindings/python",
    f"{_HOME}/rpi-rgb-led-matrix/bindings/python",
]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.append(_p)

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# ── Env ───────────────────────────────────────────────────────────────────────
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
WEATHER_UNITS   = os.getenv("WEATHER_UNITS", "imperial")
MAP_ADDRESS_A   = os.getenv("MAP_ADDRESS_A", "").strip()
MAP_ADDRESS_B   = os.getenv("MAP_ADDRESS_B", "").strip()

HEARTBEAT_FILE     = "/tmp/matrix-heartbeat-9"
HEARTBEAT_INTERVAL = 30   # seconds
UPDATE_INTERVAL    = 300  # re-fetch every 5 minutes
SCROLL_DELAY       = 0.05 # seconds between scroll ticks (≈20fps)

# ── APIs ──────────────────────────────────────────────────────────────────────
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM      = "http://router.project-osrm.org/route/v1/driving"
OWM       = "https://api.openweathermap.org/data/2.5/weather"


def geocode(address: str):
    """Return (lat, lon, short_city_name) or None."""
    try:
        r = requests.get(NOMINATIM, params={
            "q": address, "format": "json", "limit": 1, "addressdetails": 1,
        }, headers={"User-Agent": "matrix-map-display/1.0"}, timeout=10)
        hits = r.json()
        if hits:
            d    = hits[0]
            addr = d.get("address", {})
            city = (addr.get("city") or addr.get("town") or addr.get("village")
                    or addr.get("county") or d["display_name"].split(",")[0])
            return float(d["lat"]), float(d["lon"]), city.strip()
    except Exception as e:
        print(f"[map] geocode error '{address}': {e}", flush=True)
    return None


def get_drive_time(lat_a, lon_a, lat_b, lon_b):
    """Return drive duration in seconds via OSRM, or None."""
    try:
        url = f"{OSRM}/{lon_a:.6f},{lat_a:.6f};{lon_b:.6f},{lat_b:.6f}?overview=false"
        r = requests.get(url, timeout=15)
        d = r.json()
        if d.get("code") == "Ok":
            return d["routes"][0]["duration"]
    except Exception as e:
        print(f"[map] routing error: {e}", flush=True)
    return None


def get_weather(lat, lon, units="imperial"):
    """Return {temp, tmin, tmax, condition} or None."""
    if not WEATHER_API_KEY:
        return None
    try:
        r = requests.get(OWM, params={
            "lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": units,
        }, timeout=10)
        d    = r.json()
        main = d.get("main", {})
        w    = (d.get("weather") or [{}])[0]
        return {
            "temp":      round(main.get("temp", 0)),
            "tmin":      round(main.get("temp_min", 0)),
            "tmax":      round(main.get("temp_max", 0)),
            "condition": (w.get("description") or w.get("main") or "").title(),
        }
    except Exception as e:
        print(f"[map] weather error: {e}", flush=True)
    return None


def fmt_duration(secs):
    if secs is None:
        return "N/A"
    h = int(secs) // 3600
    m = (int(secs) % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"


# ── Fonts ─────────────────────────────────────────────────────────────────────
def _font_roots():
    h = _HOME
    return [
        f"{h}/mlb-led-scoreboard/assets/fonts/patched",
        f"{h}/mlb-led-scoreboard/assets/fonts",
        f"{h}/mlb-led-scoreboard/rpi-rgb-led-matrix/fonts",
        f"{h}/rpi-spotify-matrix-display/rpi-rgb-led-matrix/fonts",
        f"{h}/rpi-rgb-led-matrix/fonts",
        "/usr/share/fonts/truetype",
    ]


def load_font(candidates):
    f = graphics.Font()
    for root in _font_roots():
        for name in candidates:
            p = os.path.join(root, name)
            if os.path.exists(p):
                f.LoadFont(p)
                return f
    # last-resort: load any 5x8
    for root in _font_roots():
        p = os.path.join(root, "5x8.bdf")
        if os.path.exists(p):
            f.LoadFont(p)
            return f
    return f


# ── Helpers ───────────────────────────────────────────────────────────────────
def clear_canvas(canvas):
    black = graphics.Color(0, 0, 0)
    for y in range(64):
        graphics.DrawLine(canvas, 0, y, 63, y, black)


def text_w(canvas, font, text):
    """Measure text width by drawing off-screen (returns pixel count)."""
    return graphics.DrawText(canvas, font, -9999, -9999, graphics.Color(0, 0, 0), text)


def draw_centered(canvas, font, y, color, text):
    w = text_w(canvas, font, text)
    x = max(0, (64 - w) // 2)
    graphics.DrawText(canvas, font, x, y, color, text)


def draw_line(canvas, y, r=40, g=40, b=50):
    graphics.DrawLine(canvas, 0, y, 63, y, graphics.Color(r, g, b))


# ── Scroller ──────────────────────────────────────────────────────────────────
class Scroller:
    """Smooth ping-pong text scroller."""
    def __init__(self, px_per_tick=1, pause_frames=25):
        self.offset     = 0
        self._dir       = 1
        self._pause     = pause_frames
        self._hold      = 0
        self._px        = px_per_tick
        self._last_tick = 0.0

    def tick(self, content_w, window_w, now):
        if content_w <= window_w:
            self.offset = 0
            return 0
        if now - self._last_tick < SCROLL_DELAY:
            return self.offset
        self._last_tick = now
        if self._hold > 0:
            self._hold -= 1
            return self.offset
        max_off = content_w - window_w + 2
        self.offset += self._dir * self._px
        if self.offset >= max_off:
            self.offset = max_off
            self._dir   = -1
            self._hold  = self._pause
        elif self.offset <= 0:
            self.offset = 0
            self._dir   = 1
            self._hold  = self._pause
        return self.offset


# ── Render ────────────────────────────────────────────────────────────────────
def draw_frame(canvas, fonts, data, scrollers, now):
    clear_canvas(canvas)

    f_large = fonts["large"]   # 10x20
    f_med   = fonts["med"]     # 7x13
    f_small = fonts["small"]   # 5x8

    dest    = data.get("dest_name", "…")
    dur     = data.get("duration")
    wx      = data.get("weather") or {}
    units   = data.get("units", "imperial")
    loading = data.get("loading", False)
    error   = data.get("error", "")

    unit_sym = "F" if "imp" in units else "C"

    # colours
    c_label = graphics.Color(130, 130, 160)
    c_dest  = graphics.Color(255, 200, 50)
    c_temp  = graphics.Color(255, 255, 255)
    c_lo    = graphics.Color( 80, 160, 255)
    c_hi    = graphics.Color(255, 110,  60)
    c_drive = graphics.Color( 80, 220, 120)
    c_err   = graphics.Color(255,  70,  70)

    # ── Row 1-8: "TO: [destination]" ─────────────────────────────────────
    graphics.DrawText(canvas, f_small, 1, 8, c_label, "TO:")
    dest_avail = 64 - 18
    dw = text_w(canvas, f_small, dest)
    sx = scrollers["dest"].tick(dw, dest_avail, now)
    graphics.DrawText(canvas, f_small, 17 - sx, 8, c_dest, dest)

    draw_line(canvas, 10)

    # ── Loading / error state ─────────────────────────────────────────────
    if loading:
        draw_centered(canvas, f_small, 26, c_label, "Loading")
        draw_centered(canvas, f_small, 36, c_label, "route...")
        return
    if error:
        draw_centered(canvas, f_small, 26, c_err, "No data")
        draw_centered(canvas, f_small, 36, c_err, "check addr")
        return

    # ── Rows 12-34: Big current temp ──────────────────────────────────────
    temp = wx.get("temp")
    if temp is not None:
        temp_str = str(temp)
        tw = text_w(canvas, f_large, temp_str)
        tx = max(0, (64 - tw) // 2)
        graphics.DrawText(canvas, f_large, tx, 32, c_temp, temp_str)
        # small degree + unit top-right of the number
        deg_x = min(tx + tw + 1, 57)
        graphics.DrawText(canvas, f_small, deg_x, 15, c_label, f"\xb0{unit_sym}")
    else:
        draw_centered(canvas, f_small, 25, c_label, "--")

    # ── Row 35-43: Low / High ─────────────────────────────────────────────
    draw_line(canvas, 35)
    tmin = wx.get("tmin")
    tmax = wx.get("tmax")
    if tmin is not None:
        graphics.DrawText(canvas, f_small, 1, 43, c_lo, f"L {tmin}")
    if tmax is not None:
        hi_str = f"H {tmax}"
        hw = text_w(canvas, f_small, hi_str)
        graphics.DrawText(canvas, f_small, 63 - hw, 43, c_hi, hi_str)

    # ── Row 45-63: Drive time ─────────────────────────────────────────────
    draw_line(canvas, 46)
    graphics.DrawText(canvas, f_small, 1, 54, c_label, "Drive:")
    dur_str = fmt_duration(dur)
    dw = text_w(canvas, f_med, dur_str)
    dx = max(0, (64 - dw) // 2)
    graphics.DrawText(canvas, f_med, dx, 63, c_drive, dur_str)


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    if not MAP_ADDRESS_A or not MAP_ADDRESS_B:
        print("[map] MAP_ADDRESS_A and MAP_ADDRESS_B must be set", flush=True)
        sys.exit(1)

    print(f"[map] from={MAP_ADDRESS_A!r}  to={MAP_ADDRESS_B!r}", flush=True)

    opts = RGBMatrixOptions()
    opts.rows             = 64
    opts.cols             = 64
    opts.hardware_mapping = "adafruit-hat-pwm"
    opts.gpio_slowdown    = 2
    opts.drop_privileges  = False
    matrix    = RGBMatrix(options=opts)
    offscreen = matrix.CreateFrameCanvas()

    fonts = {
        "large": load_font(["10x20.bdf", "9x18B.bdf", "9x18.bdf"]),
        "med":   load_font(["7x13B.bdf", "7x13.bdf",  "6x10.bdf"]),
        "small": load_font(["5x8.bdf",   "6x10.bdf"]),
    }
    scrollers = {"dest": Scroller()}

    data      = {"loading": True, "dest_name": MAP_ADDRESS_B}
    last_fetch = 0.0
    last_hb    = 0.0

    while True:
        now = time.time()

        # Heartbeat
        if now - last_hb >= HEARTBEAT_INTERVAL:
            try:
                with open(HEARTBEAT_FILE, "w") as fh:
                    fh.write(str(now))
            except Exception:
                pass
            last_hb = now

        # Fetch / refresh data
        if now - last_fetch >= UPDATE_INTERVAL:
            last_fetch = now
            try:
                geo_a = geocode(MAP_ADDRESS_A)
                geo_b = geocode(MAP_ADDRESS_B)
                if geo_a and geo_b:
                    la, lna, _     = geo_a
                    lb, lnb, name_b = geo_b
                    dur = get_drive_time(la, lna, lb, lnb)
                    wx  = get_weather(lb, lnb, WEATHER_UNITS)
                    data = {
                        "dest_name": name_b,
                        "duration":  dur,
                        "weather":   wx,
                        "units":     WEATHER_UNITS,
                        "loading":   False,
                        "error":     "" if wx else "weather err",
                    }
                    print(f"[map] {name_b} | drive={fmt_duration(dur)} | wx={wx}", flush=True)
                else:
                    data = {
                        "dest_name": MAP_ADDRESS_B,
                        "loading": False,
                        "error": "geocode failed",
                    }
                    print("[map] geocode failed", flush=True)
            except Exception as e:
                print(f"[map] fetch exception: {e}", flush=True)
                data["loading"] = False
                data.setdefault("error", str(e))

        draw_frame(offscreen, fonts, data, scrollers, now)
        offscreen = matrix.SwapOnVSync(offscreen)
        time.sleep(0.05)  # ~20fps for smooth scrolling


if __name__ == "__main__":
    main()
