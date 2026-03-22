#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, inspect, sys, math, time, configparser, argparse, warnings, traceback
from pathlib import Path
from PIL import Image

from apps_v2 import spotify_player
from modules import spotify_module


def main():
    canvas_width = 64
    canvas_height = 64

    # args
    parser = argparse.ArgumentParser(
        prog='RpiSpotifyMatrixDisplay',
        description='Displays album art of currently playing song on an LED matrix'
    )
    parser.add_argument('-f', '--fullscreen', action='store_true', help='Always display album art in fullscreen')
    parser.add_argument('-e', '--emulated', action='store_true', help='Run in a matrix emulator')
    args = parser.parse_args()

    is_emulated = args.emulated
    is_full_screen_always = args.fullscreen

    # locate this script directory and repo root
    currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    repo_root = Path(currentdir).parent

    # add absolute path to rgbmatrix python bindings
    rgb_bindings = repo_root / "rpi-rgb-led-matrix" / "bindings" / "python"
    if rgb_bindings.exists():
        sys.path.append(str(rgb_bindings))

    # config (use absolute path so services/agents work)
    config = configparser.ConfigParser()
    config_path = repo_root / "config.ini"
    parsed_configs = config.read(str(config_path))
    if len(parsed_configs) == 0:
        print(f"no config file found at {config_path}")
        sys.exit(1)

    # connect to Spotify and create display image
    modules = {'spotify': spotify_module.SpotifyModule(config)}
    app_list = [spotify_player.SpotifyScreen(config, modules, is_full_screen_always)]

    # switch matrix library import if emulated
    if is_emulated:
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
    else:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

    # setup matrix
    options = RGBMatrixOptions()
    options.hardware_mapping = config.get('Matrix', 'hardware_mapping', fallback='regular')
    options.rows = canvas_width
    options.cols = canvas_height
    options.brightness = 100 if is_emulated else config.getint('Matrix', 'brightness', fallback=100)
    options.gpio_slowdown = config.getint('Matrix', 'gpio_slowdown', fallback=1)
    options.limit_refresh_rate_hz = config.getint('Matrix', 'limit_refresh_rate_hz', fallback=0)
    # honor rotation / pixel mapper (e.g., "Rotate:90")
    options.pixel_mapper_config = config.get('Matrix', 'pixel_mapper_config', fallback='')
    options.drop_privileges = False

    matrix = RGBMatrix(options=options)

    shutdown_delay = config.getint('Matrix', 'shutdown_delay', fallback=600)  # seconds
    black_screen = Image.new("RGB", (canvas_width, canvas_height), (0, 0, 0))
    last_active_time = math.floor(time.time())
    last_frame = None  # cache of last successfully generated frame

    # main loop
    while True:
        try:
            frame, is_playing = app_list[0].generate()
            current_time = math.floor(time.time())

            if frame is not None:
                # got a fresh frame — cache it
                last_frame = frame
                if is_playing:
                    last_active_time = current_time

            # Decide what to show
            if is_playing:
                # actively playing: prefer fresh frame, else fall back to cache, else black
                frame_to_show = frame if frame is not None else (last_frame if last_frame is not None else black_screen)
            else:
                # paused or stopped: hold last art until shutdown_delay, then black
                within_hold_window = (current_time - last_active_time) < shutdown_delay
                if within_hold_window and last_frame is not None:
                    frame_to_show = last_frame
                else:
                    frame_to_show = black_screen

            matrix.SetImage(frame_to_show)
            time.sleep(0.08)

        except Exception:
            # Log the traceback so it shows up in journal/system logs,
            # but keep running so a transient issue doesn't kill the process.
            traceback.print_exc()
            time.sleep(1)


if __name__ == '__main__':
    try:
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        main()
    except KeyboardInterrupt:
        print('Interrupted with Ctrl-C')
        sys.exit(0)
