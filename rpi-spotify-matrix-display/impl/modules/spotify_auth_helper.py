#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Authentication Helper Script

Run this script once to authenticate with Spotify and generate the token cache.
The token will be automatically refreshed on subsequent runs.

Usage:
    python spotify_auth_helper.py                    # Shows auth URL
    python spotify_auth_helper.py --code CODE        # Complete auth with code
"""

import os
import sys
import json
import base64
import configparser
import urllib.request
import urllib.parse
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Spotify OAuth Helper")
    parser.add_argument("--code", help="Authorization code from Spotify callback")
    parser.add_argument("--url", help="Full redirect URL containing the code")
    args = parser.parse_args()

    # Find config.ini
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent.parent
    config_path = repo_root / "config.ini"

    if not config_path.exists():
        print(f"Error: config.ini not found at {config_path}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(str(config_path))

    # Read Spotify credentials
    if 'Spotify' not in config:
        print("Error: [Spotify] section not found in config.ini")
        sys.exit(1)

    client_id = config.get('Spotify', 'client_id', fallback='')
    client_secret = config.get('Spotify', 'client_secret', fallback='')
    redirect_uri = config.get('Spotify', 'redirect_uri', fallback='')

    if not all([client_id, client_secret, redirect_uri]):
        print("Error: Missing Spotify credentials in config.ini")
        sys.exit(1)

    # Setup cache directory
    cache_dir = script_dir / ".spotify_cache"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / "spotify_token_cache"

    # Check for existing token
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                token_data = json.load(f)
            if 'access_token' in token_data:
                print("Valid token already exists!")
                print(f"Scopes: {token_data.get('scope', 'unknown')}")
                print()
                print("To re-authenticate, delete the cache:")
                print(f"  rm -rf {cache_dir}")
                sys.exit(0)
        except Exception as e:
            print(f"Could not read cache: {e}")

    # Generate authorization URL
    scope = "user-read-currently-playing,user-read-playback-state,user-modify-playback-state"
    auth_url = (
        "https://accounts.spotify.com/authorize?"
        f"client_id={client_id}"
        "&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&scope={urllib.parse.quote(scope, safe='')}"
    )

    if args.code:
        auth_code = args.code
    elif args.url:
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(args.url)
        params = parse_qs(parsed.query)
        if 'code' in params:
            auth_code = params['code'][0]
        else:
            print("Error: No 'code' parameter found in URL")
            sys.exit(1)
    else:
        # No code provided - show auth URL and exit
        print("=" * 60)
        print("Spotify Authentication Helper")
        print("=" * 60)
        print()
        print("STEP 1: Authorize the app")
        print("-" * 40)
        print()
        print("Paste this URL into your browser:")
        print()
        print(auth_url)
        print()
        print("Log in to Spotify and click 'Agree' to authorize.")
        print()
        print("After authorizing, copy the code from the redirect URL.")
        print("The page may show an error - that's OK!")
        print()
        print("STEP 2: Run this command with your code:")
        print("-" * 40)
        print()
        print(f"python {sys.argv[0]} --code YOUR_CODE_HERE")
        print()
        print("Or with the full URL:")
        print(f"python {sys.argv[0]} --url \"http://localhost:8080/callback?code=...\"")
        print()
        sys.exit(0)

    # Exchange code for token
    print("Exchanging code for token...")

    try:
        # Prepare token request
        token_url = "https://accounts.spotify.com/api/token"
        creds = f"{client_id}:{client_secret}"
        auth_header = "Basic " + base64.b64encode(creds.encode()).decode()

        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri
        }).encode()

        req = urllib.request.Request(
            token_url,
            data=data,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            token_data = json.loads(response.read().decode())

        # Save token to cache
        token_cache = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token'),
            'expires_in': token_data.get('expires_in'),
            'scope': token_data.get('scope', scope)
        }

        with open(cache_path, 'w') as f:
            json.dump(token_cache, f, indent=2)

        print()
        print("=" * 60)
        print("SUCCESS! Authentication complete!")
        print("=" * 60)
        print()
        print(f"Token saved to: {cache_path}")
        print()
        print("The token will auto-refresh on subsequent runs.")
        print()
        print("To deploy to Raspberry Pi:")
        print(f"  scp -r {cache_dir} pi@<pi-ip>:~/rpi-spotify-matrix-display/impl/modules/")
        print()

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"HTTP Error {e.code}: {error_body}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
