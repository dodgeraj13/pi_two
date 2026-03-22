# Spotify Authentication Setup Guide

This guide explains how to set up stable Spotify authentication for the Raspberry Pi matrix display.

## Overview

The authentication system uses:
- **OAuth2 PKCE flow** for secure token exchange
- **Persistent token caching** so you only authenticate once
- **Automatic token refresh** when tokens expire (every ~1 hour)

## Initial Setup (One-Time)

### Step 1: Configure Credentials

Edit `config.ini` with your Spotify API credentials:

```ini
[Spotify]
client_id = your_client_id
client_secret = your_client_secret
redirect_uri = http://localhost:8080/callback
```

Get your credentials from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

### Step 2: Run the Auth Helper

On your development machine (not the Pi), run:

```bash
cd impl/modules
python spotify_auth_helper.py
```

This will:
1. Print an authorization URL
2. Open your browser (or let you paste the URL manually)
3. Redirect to the callback URL after authorization
4. Save the token to `.spotify_cache/`

### Step 3: Deploy to Raspberry Pi

Copy the cache directory to your Pi:

```bash
# From your development machine
scp -r impl/modules/.spotify_cache pi@<pi-ip-address>:~/rpi-spotify-matrix-display/impl/modules/
```

### Step 4: Start the Display

SSH into your Pi and start the display:

```bash
cd ~/rpi-spotify-matrix-display
python impl/controller_v3.py
```

## How It Works

### Token Lifecycle

1. **Initial Auth**: You authorize once via the browser
2. **Token Storage**: Access + refresh tokens saved to `.spotify_cache/spotify_token_cache`
3. **Auto Refresh**: Tokens refresh automatically every ~60 seconds before expiry
4. **Persistent Cache**: Copy cache to Pi to avoid re-authenticating

### Token Refresh

The module checks token validity every 60 seconds:
- If token is expiring soon, it refreshes using the refresh token
- If refresh fails, it marks the module as invalid and logs an error

## Troubleshooting

### "No valid token found"

Run the auth helper again:
```bash
python impl/modules/spotify_auth_helper.py
```

### "Token refresh failed"

The refresh token may have expired or been revoked. Re-run the auth helper.

### "Scope missing"

Make sure your Spotify app has these scopes enabled:
- `user-read-currently-playing`
- `user-read-playback-state`
- `user-modify-playback-state`

### Testing on the Pi

To test authentication directly on the Pi:

```bash
cd ~/rpi-spotify-matrix-display
source .venv/bin/activate  # if using venv
python impl/modules/spotify_auth_helper.py
```

## File Structure

```
impl/modules/
├── spotify_module.py          # Main Spotify integration
├── spotify_auth.py            # PKCE authentication helper
├── spotify_auth_helper.py     # One-time auth script
└── .spotify_cache/            # Token cache (copy to Pi)
    └── spotify_token_cache
```

## Security Notes

- The token cache file contains your refresh token - treat it like a password
- Don't commit `.spotify_cache/` to version control (it's in .gitignore)
- If you suspect token compromise, delete the cache and re-authenticate
