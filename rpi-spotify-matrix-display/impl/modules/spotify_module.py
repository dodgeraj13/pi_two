import os
import math
import time
import requests
from queue import LifoQueue
from pathlib import Path

class SpotifyModule:
    """
    Spotify module that can use either:
    1. Backend API (shared OAuth with web app) - recommended
    2. Direct Spotify API (local OAuth) - fallback
    """
    def __init__(self, config):
        self.invalid = False
        self.calls = 0
        self.queue = LifoQueue()
        self.config = config
        self.isPlaying = False
        self.last_check = 0
        self.check_interval = 1  # seconds between API calls

        # Check if using backend mode
        use_backend = False
        if config is not None and 'Spotify' in config:
            use_backend = config['Spotify'].get('use_backend', 'false').lower() == 'true'

        if use_backend:
            self._init_backend_mode(config)
        else:
            self._init_local_mode(config)

    def _init_backend_mode(self, config):
        """Initialize for backend API mode (shared OAuth)"""
        if config is not None and 'Spotify' in config and 'backend_url' in config['Spotify']:
            self.backend_url = config['Spotify']['backend_url']
        else:
            self.backend_url = os.environ.get('BACKEND_URL', 'https://matrix-backend-lv4k.onrender.com')

        print(f"[Spotify Module] Backend mode initialized")
        print(f"[Spotify Module] Backend URL: {self.backend_url}")
        self._mode = 'backend'

    def _init_local_mode(self, config):
        """Initialize for local OAuth mode (fallback)"""
        self._mode = 'local'
        self.sp = None
        self.last_token_check = 0
        self.token_check_interval = 60

        if config is not None and 'Spotify' in config and 'client_id' in config['Spotify'] \
            and 'client_secret' in config['Spotify'] and 'redirect_uri' in config['Spotify']:

            client_id = config['Spotify']['client_id']
            client_secret = config['Spotify']['client_secret']
            redirect_uri = config['Spotify']['redirect_uri']

            if client_id and client_secret and redirect_uri:
                try:
                    import spotipy
                    # Set up environment for spotipy
                    os.environ["SPOTIPY_CLIENT_ID"] = client_id
                    os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret
                    os.environ["SPOTIPY_REDIRECT_URI"] = redirect_uri

                    # Define cache file path
                    cache_dir = Path(__file__).parent / ".spotify_cache"
                    cache_dir.mkdir(exist_ok=True)
                    cache_path = str(cache_dir / "spotify_token_cache")

                    scope = "user-read-currently-playing,user-read-playback-state,user-modify-playback-state"

                    self.auth_manager = spotipy.SpotifyOAuth(
                        scope=scope,
                        cache_path=cache_path,
                        open_browser=False,
                        requests_timeout=10
                    )

                    token_info = self.auth_manager.validate_token(self.auth_manager.cache_file_path)

                    if token_info is None:
                        print("[Spotify Module] No valid token found, attempting to get new token...")
                        auth_url = self.auth_manager.get_authorize_url()
                        print(f"[Spotify Module] Visit this URL to authorize: {auth_url}")
                        print("[Spotify Module] After authorization, restart the application")
                        self.invalid = True
                        return

                    self.sp = spotipy.Spotify(auth_manager=self.auth_manager, requests_timeout=10)
                    print("[Spotify Module] Local OAuth initialized with cached token")

                except Exception as e:
                    print(f"[Spotify Module] Initialization error: {e}")
                    self.invalid = True
            else:
                print("[Spotify Module] Empty Spotify client id or secret")
                self.invalid = True
        else:
            print("[Spotify Module] Missing config parameters for local OAuth")
            print("[Spotify Module] Set use_backend=true in config to use shared web OAuth")
            self.invalid = True

    def isDeviceWhitelisted(self):
        """Check if current device is whitelisted"""
        if self._mode == 'backend':
            return True  # Backend handles device filtering

        if not self.sp or self.invalid:
            return False

        if self.config is not None and 'Spotify' in self.config and 'device_whitelist' in self.config['Spotify']:
            try:
                import spotipy
                devices = self.sp.devices()
            except Exception as e:
                print(f"[Spotify Module] Device fetch error: {e}")
                return False

            device_whitelist = self.config['Spotify']['device_whitelist']
            for device in devices.get('devices', []):
                if device.get('name') in device_whitelist and device.get('is_active'):
                    return True
            return False
        else:
            return True

    def _ensure_valid_token(self):
        """Ensure the OAuth token is valid (local mode only)"""
        if self._mode != 'local':
            return True

        if not self.sp or self.invalid:
            return False

        current_time = time.time()
        if current_time - self.last_token_check < self.token_check_interval:
            return True

        try:
            import spotipy
            token_info = self.auth_manager.validate_token(self.auth_manager.cache_file_path)
            if token_info is None:
                print("[Spotify Module] Token expired, attempting refresh...")
                token_info = self.auth_manager.refresh_access_token()
                if token_info:
                    print("[Spotify Module] Token refreshed successfully")
                    self.last_token_check = current_time
                    return True
                else:
                    print("[Spotify Module] Token refresh failed, re-authorization needed")
                    self.invalid = True
                    return False

            self.last_token_check = current_time
            return True

        except Exception as e:
            print(f"[Spotify Module] Token check error: {e}")
            return False

    def getCurrentPlayback(self):
        """Fetch current playback"""
        if self._mode == 'backend':
            return self._get_playback_backend()
        else:
            return self._get_playback_local()

    def _get_playback_backend(self):
        """Fetch playback from backend API"""
        if self.invalid:
            return None

        # Rate limit
        current_time = time.time()
        if current_time - self.last_check < self.check_interval:
            return True

        self.last_check = current_time

        try:
            response = requests.get(
                f"{self.backend_url}/now-playing",
                timeout=5
            )

            if response.status_code != 200:
                print(f"[Spotify Module] API error: {response.status_code}")
                return None

            data = response.json()

            # Check if authentication is needed
            if data.get('needs_auth'):
                print("[Spotify Module] Backend needs Spotify auth. Please authorize via the web interface.")
                self.invalid = True
                return None

            if not data.get('is_playing'):
                self.isPlaying = False
                return None

            # Extract track info
            artist = data.get('artist', 'Unknown')
            title = data.get('title', 'Unknown')
            art_url = data.get('album_art', None)
            progress_ms = data.get('progress_ms', 0)
            duration_ms = data.get('duration_ms', 0)

            self.isPlaying = True
            self.queue.put((artist, title, art_url, True, progress_ms, duration_ms))
            return True

        except requests.exceptions.RequestException as e:
            print(f"[Spotify Module] Network error: {e}")
            return None
        except Exception as e:
            print(f"[Spotify Module] Error: {e}")
            return None

    def _get_playback_local(self):
        """Fetch playback from Spotify API directly (local mode)"""
        if self.invalid:
            return None

        if not self._ensure_valid_token():
            return None

        try:
            import spotipy
            track = self.sp.current_user_playing_track()

            if track is None:
                return None

            if not self.isDeviceWhitelisted():
                return None

            if track['item'] is None:
                artist = None
                title = None
                art_url = None
            else:
                artist = track['item']['artists'][0]['name']
                if len(track['item']['artists']) >= 2:
                    artist = artist + ", " + track['item']['artists'][1]['name']
                title = track['item']['name']
                art_url = track['item']['album']['images'][0]['url']

            self.isPlaying = track['is_playing']

            self.queue.put((artist, title, art_url, self.isPlaying, track["progress_ms"], track["item"]["duration_ms"]))
            return True

        except Exception as e:
            import spotipy
            if isinstance(e, spotipy.SpotifyOAuthError):
                print(f"[Spotify Module] OAuth error: {e}")
                self.invalid = True
            else:
                print(f"[Spotify Module] Playback fetch error: {e}")
            return None