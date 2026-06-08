#!/usr/bin/env python3
"""
spotify playlist extractor
grabs all tracks from a playlist, optionally finds youtube links too

usage:
    python extractor.py
    python extractor.py --playlist <id or url>
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
from datetime import datetime


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


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    return cfg


def save_default_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"created {CONFIG_FILE} — fill in your credentials and run again")


def extract_playlist_id(value):
    m = re.search(r"playlist/([A-Za-z0-9]+)", value)
    return m.group(1) if m else value.strip()


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def http_post_form(url, data, headers=None):
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers=headers or {},
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


# --- spotify ---

def get_token(client_id, client_secret):
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = http_post_form(
        "https://accounts.spotify.com/api/token",
        {"grant_type": "client_credentials"},
        {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    return resp["access_token"]


def fetch_tracks(token, playlist_id):
    tracks = []
    url = (
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        f"?limit=100&fields=next,total,items(track(name,id,external_urls,artists))"
    )
    auth = {"Authorization": f"Bearer {token}"}
    total = None

    while url:
        data = http_get(url, auth)

        if total is None:
            total = data.get("total", "?")
            print(f"  found {total} tracks")

        for item in data.get("items", []):
            t = item.get("track")
            if not t or not t.get("name"):
                continue
            artists = ", ".join(a["name"] for a in t.get("artists", []))
            sp_url = t.get("external_urls", {}).get(
                "spotify", f"https://open.spotify.com/track/{t['id']}"
            )
            tracks.append({
                "title": t["name"],
                "artist": artists,
                "spotify_url": sp_url,
                "track_id": t["id"],
            })

        n = len(tracks)
        pct = int(n / total * 100) if isinstance(total, int) else "?"
        print(f"  {n}/{total} ({pct}%)", end="\r")

        url = data.get("next")
        if url:
            time.sleep(0.05)

    print()
    return tracks


# --- youtube ---

def yt_search(query):
    """
    scrapes youtube search results to find a video id — no api key needed.
    not perfect, might grab a cover or live version sometimes.
    """
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        m = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
    except Exception:
        pass
    return None


def resolve_youtube(tracks, delay=1.0):
    print("\n  heads up: youtube matching isn't perfect")
    print("  covers/live versions can slip through\n")

    total = len(tracks)
    for i, track in enumerate(tracks):
        query = f"{track['title']} {track['artist']} official audio"
        yt = yt_search(query)
        track["youtube_url"] = yt or ""
        pct = int((i + 1) / total * 100)
        mark = "+" if yt else "-"
        print(f"  [{pct:3d}%] {mark} {track['title'][:55]}", end="\r")
        time.sleep(delay)

    print()
    found = sum(1 for t in tracks if t.get("youtube_url"))
    print(f"  matched {found}/{total}")
    return tracks


# --- output ---

def fmt_name(track, template):
    return template.format(
        title=track["title"],
        artist=track["artist"],
        id=track["track_id"]
    )


def save(tracks, cfg, playlist_id):
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    template = cfg.get("name_format", "{title} - {artist}")
    formats = cfg.get("output_formats", ["txt", "csv", "json"])
    has_yt = any(t.get("youtube_url") for t in tracks)
    saved = []

    if "txt" in formats:
        p = os.path.join(out_dir, f"names_{stamp}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# playlist: {playlist_id}\n")
            f.write(f"# exported: {datetime.now().isoformat()}\n")
            f.write(f"# total: {len(tracks)}\n\n")
            for t in tracks:
                f.write(fmt_name(t, template) + "\n")
        saved.append(p)

        p = os.path.join(out_dir, f"spotify_links_{stamp}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# playlist: {playlist_id}\n")
            f.write(f"# exported: {datetime.now().isoformat()}\n\n")
            for t in tracks:
                f.write(t["spotify_url"] + "\n")
        saved.append(p)

        if has_yt:
            p = os.path.join(out_dir, f"youtube_links_{stamp}.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# playlist: {playlist_id}\n")
                f.write(f"# note: youtube links are best-effort, not guaranteed accurate\n")
                f.write(f"# exported: {datetime.now().isoformat()}\n\n")
                for t in tracks:
                    yt = t.get("youtube_url") or "not found"
                    f.write(f"{fmt_name(t, template)} -> {yt}\n")
            saved.append(p)

    if "csv" in formats:
        p = os.path.join(out_dir, f"playlist_{stamp}.csv")
        with open(p, "w", encoding="utf-8") as f:
            header = "title,artist,spotify_url"
            if has_yt:
                header += ",youtube_url"
            f.write(header + "\n")
            for t in tracks:
                def q(v):
                    return '"' + str(v).replace('"', '""') + '"'
                row = f"{q(t['title'])},{q(t['artist'])},{q(t['spotify_url'])}"
                if has_yt:
                    row += f",{q(t.get('youtube_url', ''))}"
                f.write(row + "\n")
        saved.append(p)

    if "json" in formats:
        p = os.path.join(out_dir, f"playlist_{stamp}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({
                "playlist_id": playlist_id,
                "exported_at": datetime.now().isoformat(),
                "total": len(tracks),
                "tracks": tracks,
            }, f, indent=2, ensure_ascii=False)
        saved.append(p)

    return saved


# --- main ---

def main():
    parser = argparse.ArgumentParser(description="spotify playlist extractor")
    parser.add_argument("--playlist", help="playlist id or spotify url")
    parser.add_argument("--no-youtube", action="store_true", help="skip youtube lookup")
    parser.add_argument("--format", choices=["txt", "csv", "json", "all"])
    parser.add_argument("--init", action="store_true", help="create a default config.json")
    args = parser.parse_args()

    print("\nspotify playlist extractor")
    print("-" * 30)

    if args.init:
        save_default_config()
        return

    cfg = load_config()

    if args.playlist:
        cfg["playlist_id"] = extract_playlist_id(args.playlist)
    if args.no_youtube:
        cfg["youtube_search"] = False
    if args.format:
        cfg["output_formats"] = ["txt", "csv", "json"] if args.format == "all" else [args.format]

    missing = [k for k in ("client_id", "client_secret", "playlist_id") if not cfg.get(k)]
    if missing:
        print(f"missing config: {', '.join(missing)}")
        print("run: python extractor.py --init")
        sys.exit(1)

    playlist_id = extract_playlist_id(cfg["playlist_id"])

    print("\n[1/3] getting spotify token...")
    try:
        token = get_token(cfg["client_id"], cfg["client_secret"])
        print("  ok")
    except Exception as e:
        print(f"  failed: {e}")
        sys.exit(1)

    print(f"\n[2/3] fetching tracks...")
    try:
        tracks = fetch_tracks(token, playlist_id)
        print(f"  loaded {len(tracks)} tracks")
    except Exception as e:
        print(f"  failed: {e}")
        sys.exit(1)

    if cfg.get("youtube_search"):
        print(f"\n[3/3] looking up youtube links ({len(tracks)} searches)...")
        tracks = resolve_youtube(tracks, delay=cfg.get("youtube_delay_seconds", 1.0))
    else:
        print("\n[3/3] skipping youtube")

    print("\nsaving files...")
    saved = save(tracks, cfg, playlist_id)
    for p in saved:
        print(f"  {p}")

    print(f"\ndone. {len(tracks)} tracks exported\n")


if __name__ == "__main__":
    main()
