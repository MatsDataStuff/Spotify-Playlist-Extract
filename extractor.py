#!/usr/bin/env python3
"""
Spotify Playlist Extractor
--------------------------
Extracts all tracks from a Spotify playlist and optionally finds YouTube links.

Usage:
    python extractor.py
    python extractor.py --playlist <playlist_id_or_url>
    python extractor.py --no-youtube
    python extractor.py --format csv
"""

import os
import sys
import json
import time
import argparse
import re
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIG — edit these or use a config.json file
# ──────────────────────────────────────────────
DEFAULT_CONFIG = {
    "client_id": "",
    "client_secret": "",
    "playlist_id": "",
    "output_dir": "output",
    "youtube_search": True,
    "youtube_delay_seconds": 1.0,
    "output_formats": ["txt", "csv", "json"],
    "name_format": "{title} - {artist}",
}

CONFIG_FILE = "config.json"


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            file_cfg = json.load(f)
        cfg.update(file_cfg)
    return cfg


def save_default_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"  Created {CONFIG_FILE} — fill in your credentials and run again.")


def extract_playlist_id(value: str) -> str:
    """Accept full URL or bare ID."""
    match = re.search(r"playlist/([A-Za-z0-9]+)", value)
    return match.group(1) if match else value.strip()


def http_get(url: str, headers: dict = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def http_post_form(url: str, data: dict, headers: dict = None) -> dict:
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=encoded, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ──────────────────────────────────────────────
# SPOTIFY
# ──────────────────────────────────────────────

def get_spotify_token(client_id: str, client_secret: str) -> str:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = http_post_form(
        "https://accounts.spotify.com/api/token",
        {"grant_type": "client_credentials"},
        {"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    return data["access_token"]


def fetch_playlist_tracks(token: str, playlist_id: str):
    tracks = []
    url = (
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        f"?limit=100&fields=next,total,items(track(name,id,external_urls,artists))"
    )
    headers = {"Authorization": f"Bearer {token}"}
    total = None

    while url:
        data = http_get(url, headers)
        if total is None:
            total = data.get("total", "?")
            print(f"  Total tracks: {total}")

        for item in data.get("items", []):
            track = item.get("track")
            if not track or not track.get("name"):
                continue
            artists = ", ".join(a["name"] for a in track.get("artists", []))
            spotify_url = track.get("external_urls", {}).get("spotify", f"https://open.spotify.com/track/{track['id']}")
            tracks.append({
                "title": track["name"],
                "artist": artists,
                "spotify_url": spotify_url,
                "track_id": track["id"],
            })

        fetched = len(tracks)
        pct = int(fetched / total * 100) if isinstance(total, int) else "?"
        print(f"  Fetched {fetched}/{total} ({pct}%)", end="\r")
        url = data.get("next")
        if url:
            time.sleep(0.05)

    print()
    return tracks


# ──────────────────────────────────────────────
# YOUTUBE (scrape-based, no API key needed)
# ──────────────────────────────────────────────

def search_youtube(query: str) -> str | None:
    """
    Search YouTube without an API key by scraping the search results page.
    NOTE: This is a best-effort match — accuracy varies. Results may not be
    the exact version (could be a cover, live version, or wrong song).
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # extract first video ID from ytInitialData
        match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception:
        pass
    return None


def resolve_youtube_links(tracks: list, delay: float = 1.0):
    print(f"\n  ⚠  YouTube matching is best-effort — results may not be exact.")
    print(f"     Covers, live versions, or wrong songs can appear.\n")
    total = len(tracks)
    for i, track in enumerate(tracks):
        query = f"{track['title']} {track['artist']} official audio"
        yt = search_youtube(query)
        track["youtube_url"] = yt or ""
        pct = int((i + 1) / total * 100)
        status = "✓" if yt else "✗"
        print(f"  [{pct:3d}%] {status} {track['title'][:50]}", end="\r")
        time.sleep(delay)
    print()
    found = sum(1 for t in tracks if t.get("youtube_url"))
    print(f"  YouTube links found: {found}/{total}")
    return tracks


# ──────────────────────────────────────────────
# OUTPUT
# ──────────────────────────────────────────────

def format_name(track: dict, fmt: str) -> str:
    return fmt.format(
        title=track["title"],
        artist=track["artist"],
        id=track["track_id"],
    )


def save_outputs(tracks: list, cfg: dict, playlist_id: str):
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name_fmt = cfg.get("name_format", "{title} - {artist}")
    formats = cfg.get("output_formats", ["txt", "csv", "json"])
    saved = []

    if "txt" in formats:
        # Song names list
        path = os.path.join(out_dir, f"names_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Playlist: {playlist_id}\n")
            f.write(f"# Exported: {datetime.now().isoformat()}\n")
            f.write(f"# Total: {len(tracks)}\n\n")
            for t in tracks:
                f.write(format_name(t, name_fmt) + "\n")
        saved.append(path)

        # Spotify links list
        path = os.path.join(out_dir, f"spotify_links_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Playlist: {playlist_id}\n")
            f.write(f"# Exported: {datetime.now().isoformat()}\n\n")
            for t in tracks:
                f.write(t["spotify_url"] + "\n")
        saved.append(path)

        # YouTube links list (if available)
        if any(t.get("youtube_url") for t in tracks):
            path = os.path.join(out_dir, f"youtube_links_{stamp}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Playlist: {playlist_id}\n")
                f.write(f"# ⚠ YouTube links are best-effort — accuracy not guaranteed\n")
                f.write(f"# Exported: {datetime.now().isoformat()}\n\n")
                for t in tracks:
                    line = f"{format_name(t, name_fmt)} → {t.get('youtube_url', 'NOT FOUND')}"
                    f.write(line + "\n")
            saved.append(path)

    if "csv" in formats:
        path = os.path.join(out_dir, f"playlist_{stamp}.csv")
        with open(path, "w", encoding="utf-8") as f:
            has_yt = any(t.get("youtube_url") for t in tracks)
            header = "title,artist,spotify_url"
            if has_yt:
                header += ",youtube_url"
            f.write(header + "\n")
            for t in tracks:
                def esc(v): return '"' + str(v).replace('"', '""') + '"'
                row = f"{esc(t['title'])},{esc(t['artist'])},{esc(t['spotify_url'])}"
                if has_yt:
                    row += f",{esc(t.get('youtube_url', ''))}"
                f.write(row + "\n")
        saved.append(path)

    if "json" in formats:
        path = os.path.join(out_dir, f"playlist_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "playlist_id": playlist_id,
                "exported_at": datetime.now().isoformat(),
                "total": len(tracks),
                "tracks": tracks,
            }, f, indent=2, ensure_ascii=False)
        saved.append(path)

    return saved


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Spotify Playlist Extractor")
    parser.add_argument("--playlist", help="Playlist ID or full Spotify URL")
    parser.add_argument("--no-youtube", action="store_true", help="Skip YouTube link resolution")
    parser.add_argument("--format", choices=["txt", "csv", "json", "all"], default=None, help="Output format(s)")
    parser.add_argument("--init", action="store_true", help="Create a default config.json and exit")
    args = parser.parse_args()

    print("\n🎵  Spotify Playlist Extractor\n" + "─" * 40)

    if args.init:
        save_default_config()
        return

    cfg = load_config()

    # Override config with CLI args
    if args.playlist:
        cfg["playlist_id"] = extract_playlist_id(args.playlist)
    if args.no_youtube:
        cfg["youtube_search"] = False
    if args.format:
        cfg["output_formats"] = ["txt", "csv", "json"] if args.format == "all" else [args.format]

    # Validate
    missing = [k for k in ("client_id", "client_secret", "playlist_id") if not cfg.get(k)]
    if missing:
        print(f"  ✗ Missing config: {', '.join(missing)}")
        print(f"  Run: python extractor.py --init  to create config.json")
        sys.exit(1)

    playlist_id = extract_playlist_id(cfg["playlist_id"])

    # 1. Auth
    print("\n[1/3] Authenticating with Spotify...")
    try:
        token = get_spotify_token(cfg["client_id"], cfg["client_secret"])
        print("  ✓ Token obtained")
    except Exception as e:
        print(f"  ✗ Auth failed: {e}")
        sys.exit(1)

    # 2. Fetch tracks
    print(f"\n[2/3] Fetching tracks from playlist {playlist_id}...")
    try:
        tracks = fetch_playlist_tracks(token, playlist_id)
        print(f"  ✓ {len(tracks)} tracks loaded")
    except Exception as e:
        print(f"  ✗ Failed to fetch tracks: {e}")
        sys.exit(1)

    # 3. YouTube (optional)
    if cfg.get("youtube_search"):
        print(f"\n[3/3] Resolving YouTube links ({len(tracks)} searches)...")
        tracks = resolve_youtube_links(tracks, delay=cfg.get("youtube_delay_seconds", 1.0))
    else:
        print("\n[3/3] Skipping YouTube (--no-youtube)")

    # 4. Save
    print(f"\n💾  Saving output files...")
    saved = save_outputs(tracks, cfg, playlist_id)
    for path in saved:
        print(f"  ✓ {path}")

    print(f"\n✅  Done! {len(tracks)} tracks exported.\n")


if __name__ == "__main__":
    main()
