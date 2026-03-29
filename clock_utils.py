#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared analog clock drawing logic for Pi display scripts.
Used by clock_display.py (matrix graphics) and spotify_player.py (PIL images)
"""

import math

# Clock drawing constants - adjust these to change all clocks
CLOCK_CENTER = (32, 32)  # Center of 64x64 canvas
CLOCK_RADIUS = 30
NUM_TICKS = 12  # Number of tick marks (hourly)

# Colors (RGB)
RING_COLOR = (220, 230, 255)
TICK_COLOR = (102, 102, 102)  # #666
NUMBER_COLOR = (204, 204, 204)  # #ccc
HOUR_HAND_COLOR = (255, 210, 120)  # #ffd78c
MINUTE_HAND_COLOR = (120, 200, 255)  # #78c8ff
CENTER_COLOR = (255, 255, 255)

# Hand lengths
HOUR_HAND_LENGTH = 18
MINUTE_HAND_LENGTH = 26

# Hand widths
HOUR_HAND_WIDTH = 3
MINUTE_HAND_WIDTH = 2

# Center dot radius
CENTER_DOT_RADIUS = 2


def polar_point(cx, cy, r, deg):
    """Convert polar to cartesian coordinates"""
    a = math.radians(deg)
    return (cx + int(round(r * math.cos(a))), cy + int(round(r * math.sin(a))))


def get_hand_angles(hour, minute):
    """Get the angles for hour and minute hands in degrees (0 = right, 90 = down)"""
    hour_angle = ((hour % 12) + minute / 60.0) * 30 - 90
    minute_angle = (minute % 60) * 6 - 90
    return hour_angle, minute_angle