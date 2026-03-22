import numpy as np, requests, math, time, threading
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO

class SpotifyScreen:
    def __init__(self, config, modules, fullscreen):
        self.modules = modules

        self.font = ImageFont.truetype("fonts/tiny.otf", 5)

        self.canvas_width = 64
        self.canvas_height = 64
        self.title_color = (255,255,255)
        self.artist_color = (255,255,255)
        self.play_color = (255, 255, 255)

        self.full_screen_always = fullscreen

        self.current_art_url = ''
        self.current_art_img = None
        self.current_title = ''
        self.current_artist = ''

        # For smooth fade transitions
        self.previous_art_img = None
        self.fade_progress = 1.0  # 1.0 = fully showing new image, 0.0 = showing old image
        self.fade_speed = 0.15  # How much to blend per frame (lower = slower fade)
        self.fade_steps = 0  # Count steps for consistent fade timing
        self.target_fade_steps = 10  # Total fade steps (higher = smoother but slower)

        self.title_animation_cnt = 0
        self.artist_animation_cnt = 0
        self.last_title_reset = math.floor(time.time())
        self.last_artist_reset = math.floor(time.time())
        self.scroll_delay = 4

        self.paused = True
        self.paused_time = math.floor(time.time())
        self.paused_delay = 5

        self.is_playing = False

        self.last_fetch_time = math.floor(time.time())
        self.fetch_interval = 1
        self.spotify_module = self.modules['spotify']

        self.response = None
        self.thread = threading.Thread(target=self.getCurrentPlaybackAsync)
        self.thread.start()

    def getCurrentPlaybackAsync(self):
        # delay spotify fetches
        time.sleep(3)
        while True:
            self.response = self.spotify_module.getCurrentPlayback()
            time.sleep(1)

    def generate(self):
        if not self.spotify_module.queue.empty():
            self.response = self.spotify_module.queue.get()
            self.spotify_module.queue.queue.clear()
        return self.generateFrame(self.response)

    def generateFrame(self, response):
        # determine state
        if response is not None:
            artist, title, art_url, self.is_playing, progress_ms, duration_ms = response

            # load/update album art if URL changed
            if art_url != self.current_art_url:
                # Start fade transition
                if self.current_art_img is not None:
                    self.previous_art_img = self.current_art_img
                    self.fade_progress = 0.0
                    self.fade_steps = 0

                self.current_art_url = art_url
                try:
                    resp = requests.get(art_url, timeout=5)
                    img = Image.open(BytesIO(resp.content))
                    self.current_art_img = img.resize((self.canvas_width, self.canvas_height), Image.LANCZOS)
                except Exception as e:
                    print(f"[spotify_player] Failed to load album art: {e}")
                    # Keep previous image if load fails
                    if self.previous_art_img:
                        self.current_art_img = self.previous_art_img
                        self.fade_progress = 1.0

            # Update fade progress
            if self.fade_progress < 1.0 and self.previous_art_img is not None:
                self.fade_steps += 1
                self.fade_progress = min(1.0, self.fade_steps / self.target_fade_steps)
                if self.fade_progress >= 1.0:
                    # Fade complete, clear previous
                    self.previous_art_img = None

            # start with black bg
            frame = Image.new("RGB", (self.canvas_width, self.canvas_height), (0, 0, 0))

            # Draw with fade transition
            if self.fade_progress < 1.0 and self.previous_art_img is not None and self.current_art_img is not None:
                # Blend old and new images
                # Create blended image using alpha composite
                old_alpha = int(255 * (1 - self.fade_progress))
                new_alpha = int(255 * self.fade_progress)

                # Paste old image with reduced opacity
                frame.paste(self.previous_art_img, (0, 0))

                # Blend new image on top
                blend_frame = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
                blend_frame.paste(self.current_art_img, (0, 0))
                blend_frame.putalpha(new_alpha)
                frame = Image.alpha_composite(frame.convert("RGBA"), blend_frame).convert("RGB")
            elif self.current_art_img:
                frame.paste(self.current_art_img, (0, 0))

            # if playing, draw progress bar
            if self.is_playing and duration_ms:
                draw = ImageDraw.Draw(frame)
                bar_y = self.canvas_height - 1
                play_w = int((progress_ms / duration_ms) * self.canvas_width)
                # background bar
                draw.line((0, bar_y, self.canvas_width, bar_y), fill=(50,50,50))
                # progress
                draw.line((0, bar_y, play_w, bar_y), fill=self.play_color)

            return (frame, self.is_playing)

        # no response at all: still show last art (or blank)
        frame = Image.new("RGB", (self.canvas_width, self.canvas_height), (0, 0, 0))
        if self.current_art_img:
            frame.paste(self.current_art_img, (0, 0))
        return (frame, False)


def drawPlayPause(draw, is_playing, color):
    x = 10
    y = -16
    if not is_playing:
        draw.line((x+45,y+19,x+45,y+25), fill = color)
        draw.line((x+46,y+20,x+46,y+24), fill = color)
        draw.line((x+47,y+20,x+47,y+24), fill = color)
        draw.line((x+48,y+21,x+48,y+23), fill = color)
        draw.line((x+49,y+21,x+49,y+23), fill = color)
        draw.line((x+50,y+22,x+50,y+22), fill = color)
    else:
        draw.line((x+45,y+19,x+45,y+25), fill = color)
        draw.line((x+46,y+19,x+46,y+25), fill = color)
        draw.line((x+49,y+19,x+49,y+25), fill = color)
        draw.line((x+50,y+19,x+50,y+25), fill = color)
