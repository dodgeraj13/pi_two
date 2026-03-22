#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Authentication Module with PKCE flow and token caching.
Provides stable, persistent authentication suitable for headless devices.
"""

import os
import json
import hashlib
import base64
import secrets
import time
import webbrowser
import http.server
import socketserver
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Thread

# OAuth2 constants
TOKEN_CACHE_FILE = ".spotify_token_cache.json"
DEFAULT_REDIRECT_PORT = 8080
AUTH_TIMEOUT = 300  # seconds


class SpotifyAuthPKCE:
    """
    Handles Spotify OAuth2 authentication using PKCE flow.
    Automatically caches and refreshes tokens.
    """

    def __init__(self, client_id, client_secret, redirect_uri=None, cache_path=None, scope=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or f"http://localhost:{DEFAULT_REDIRECT_PORT}/callback"
        self.cache_path = Path(cache_path) if cache_path else Path(__file__).parent / TOKEN_CACHE_FILE
        self.scope = scope or "user-read-currently-playing,user-read-playback-state,user-modify-playback-state"

        self.token_cache = {}
        self._load_cached_token()

    def _generate_pkce_pair(self):
        """Generate PKCE code verifier and challenge."""
        code_verifier = secrets.token_urlsafe(32)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=")
        return code_verifier, code_challenge.decode()

    def _load_cached_token(self):
        """Load token from cache file if valid."""
        try:
            if self.cache_path.exists():
                with open(self.cache_path, 'r') as f:
                    self.token_cache = json.load(f)

                # Check if token is still valid (with 5 min buffer)
                if self._is_token_valid():
                    print(f"[SpotifyAuth] Loaded cached token from {self.cache_path}")
                    return True
                else:
                    print("[SpotifyAuth] Cached token expired, will refresh or re-auth")
                    # Try to refresh if we have a refresh token
                    if 'refresh_token' in self.token_cache:
                        return self._refresh_access_token()
        except Exception as e:
            print(f"[SpotifyAuth] Error loading cache: {e}")

        self.token_cache = {}
        return False

    def _save_token_cache(self):
        """Save token to cache file."""
        try:
            self.token_cache['saved_at'] = time.time()
            with open(self.cache_path, 'w') as f:
                json.dump(self.token_cache, f, indent=2)
            print(f"[SpotifyAuth] Token saved to {self.cache_path}")
        except Exception as e:
            print(f"[SpotifyAuth] Error saving cache: {e}")

    def _is_token_valid(self):
        """Check if access token is still valid (with 5 min buffer)."""
        if not self.token_cache.get('access_token'):
            return False

        expires_at = self.token_cache.get('expires_at', 0)
        # Add 5 minute buffer for safety
        return time.time() < (expires_at - 300)

    def _refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        try:
            url = "https://accounts.spotify.com/api/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + base64.b64encode(
                    f"{self.client_id}:{self.client_secret}".encode()
                ).decode()
            }
            body = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": self.token_cache['refresh_token']
            })

            req = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

                self.token_cache['access_token'] = data['access_token']
                self.token_cache['expires_at'] = time.time() + data['expires_in']
                if 'refresh_token' in data:
                    self.token_cache['refresh_token'] = data['refresh_token']

                self._save_token_cache()
                print("[SpotifyAuth] Token refreshed successfully")
                return True

        except Exception as e:
            print(f"[SpotifyAuth] Refresh failed: {e}")
            return False

    def get_authorize_url(self, code_verifier, code_challenge):
        """Generate the authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": self.scope,
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)

    def _start_callback_server(self, state, code_verifier, auth_result_queue):
        """Start a local HTTP server to catch the OAuth callback."""

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                if 'code' in params:
                    auth_code = params['code'][0]
                    received_state = params.get('state', [None])[0]

                    if received_state == state:
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        success_html = """
                            <html>
                                <body style="font-family: Arial; text-align: center; padding: 50px;">
                                    <h2 style="color: #1DB954;">Spotify Authenticated!</h2>
                                    <p>You can close this window now.</p>
                                </body>
                            </html>
                        """
                        self.wfile.write(success_html.encode())
                        auth_result_queue.put(auth_code)
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"State mismatch")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"No code in callback")

                # Shutdown server after handling request
                Thread(target=self.server.shutdown, daemon=True).start()

            def log_message(self, format, *args):
                pass  # Suppress logging

        # Parse port from redirect_uri
        port = int(self.redirect_uri.split(":")[2].split("/")[0])

        with socketserver.TCPServer(("localhost", port), CallbackHandler) as httpd:
            httpd.handle_request()
            httpd.server_activate()

    def authenticate(self, open_browser=True):
        """
        Perform the full OAuth PKCE flow.
        Returns True if successful, False otherwise.
        """
        # Generate PKCE values
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(16)

        auth_result_queue = []

        # Start callback server in background
        server_thread = Thread(
            target=self._start_callback_server,
            args=(state, code_verifier, auth_result_queue),
            daemon=True
        )
        server_thread.start()

        # Build auth URL
        auth_url = self.get_authorize_url(code_verifier, code_challenge)

        print(f"[SpotifyAuth] Open this URL in your browser:")
        print(auth_url)

        if open_browser:
            webbrowser.open(auth_url)

        # Wait for callback (with timeout)
        auth_code = None
        start_time = time.time()
        while time.time() - start_time < AUTH_TIMEOUT:
            time.sleep(0.5)
            # Check if server thread completed
            if not server_thread.is_alive() and hasattr(self, '_auth_code'):
                auth_code = self._auth_code
                break

        if not auth_code:
            print("[SpotifyAuth] Authentication timeout")
            return False

        # Exchange code for token
        try:
            token_url = "https://accounts.spotify.com/api/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + base64.b64encode(
                    f"{self.client_id}:{self.client_secret}".encode()
                ).decode()
            }
            body = urllib.parse.urlencode({
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier
            })

            req = urllib.request.Request(token_url, data=body.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

                self.token_cache = {
                    'access_token': data['access_token'],
                    'refresh_token': data.get('refresh_token'),
                    'expires_at': time.time() + data['expires_in'],
                    'scope': data.get('scope', self.scope)
                }

                self._save_token_cache()
                print("[SpotifyAuth] Authentication successful!")
                return True

        except Exception as e:
            print(f"[SpotifyAuth] Token exchange failed: {e}")
            return False

    def get_access_token(self):
        """
        Get a valid access token, refreshing if necessary.
        Returns None if not authenticated.
        """
        if not self.token_cache.get('access_token'):
            return None

        if not self._is_token_valid():
            if 'refresh_token' in self.token_cache:
                if self._refresh_access_token():
                    return self.token_cache['access_token']
            return None

        return self.token_cache['access_token']

    def is_authenticated(self):
        """Check if we have a valid token."""
        return self.get_access_token() is not None

    def clear_cache(self):
        """Clear the token cache."""
        self.token_cache = {}
        if self.cache_path.exists():
            self.cache_path.unlink()
        print("[SpotifyAuth] Cache cleared")


def create_spotify_auth_manager(config, cache_path=None):
    """
    Factory function to create an authenticated Spotify manager.
    Uses spotipy if available, falls back to raw OAuth.
    """
    client_id = config.get('Spotify', 'client_id', fallback='')
    client_secret = config.get('Spotify', 'client_secret', fallback='')
    redirect_uri = config.get('Spotify', 'redirect_uri', fallback='')

    if not all([client_id, client_secret, redirect_uri]):
        print("[SpotifyAuth] Missing credentials in config")
        return None

    # Try spotipy first (simpler)
    try:
        import spotipy

        # Use spotipy's OAuth with custom cache path
        scope = "user-read-currently-playing,user-read-playback-state,user-modify-playback-state"

        # spotipy.SpotifyOAuth handles token caching automatically
        # but we need to point it to our cache location
        if cache_path:
            os.environ["SPOTIPY_CLIENT_ID"] = client_id
            os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret
            os.environ["SPOTIPY_REDIRECT_URI"] = redirect_uri

            # Create auth manager with cache file path
            auth_manager = spotipy.SpotifyOAuth(
                scope=scope,
                cache_path=str(cache_path),
                open_browser=False
            )

            # Force token load/refresh
            token_info = auth_manager.validate_token(auth_manager.cache_file_path)
            if token_info is None:
                print("[SpotifyAuth] Getting new token...")
                token_info = auth_manager.get_access_token(check_cache=True)
                if not token_info:
                    # Manual PKCE flow
                    auth_manager.get_authorize_url()
                    return None

            sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=10)
            print("[SpotifyAuth] Using spotipy with cached tokens")
            return sp

    except Exception as e:
        print(f"[SpotifyAuth] spotipy setup failed: {e}")

    # Fallback to raw PKCE implementation
    auth = SpotifyAuthPKCE(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        cache_path=cache_path
    )

    if not auth.is_authenticated():
        print("[SpotifyAuth] Not authenticated, starting PKCE flow...")
        if auth.authenticate(open_browser=True):
            print("[SpotifyAuth] PKCE authentication successful")
        else:
            print("[SpotifyAuth] PKCE authentication failed")
            return None

    return auth
