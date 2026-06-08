[README.md](https://github.com/user-attachments/files/28692890/README.md)
# Spotify-Playlist-Extract
For those with large playlist, who want a list of their collection for any reason. 
# Spotify Playlist Extractor

Extract every track from any Spotify playlist into clean, usable lists — song names, Spotify links, YouTube links, CSV, and JSON. No third-party dependencies, pure Python 3.

---

## Features

- Extracts all tracks (handles playlists with 4000+ songs)
- Output: `Song Name - Artist` name list
- Output: Spotify links list
- Output: YouTube link resolver *(best-effort, no API key needed)*
- Output formats: `.txt`, `.csv`, `.json`
- Fully configurable via `config.json` or CLI flags
- Zero dependencies — pure Python 3 stdlib only

>  **YouTube note:** Links are found by scraping YouTube search results without an API key. Results are a best-effort match — covers, live versions, or wrong songs may appear. Accuracy is typically ~85–90% for well-known tracks.

---

## Setup

### 1. Get Spotify API credentials (free)

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Click **Create app**
3. Set any Redirect URI (e.g. `http://localhost`)
4. Copy your **Client ID** and **Client Secret**

### 2. Configure

Edit `config.json`:

```json
{
  "client_id": "your_client_id_here",
  "client_secret": "your_client_secret_here",
  "playlist_id": "https://open.spotify.com/playlist/6Jq2DDdkPMMZhE7hlERQP7"
}
```

Or generate a fresh config file:

```bash
python extractor.py --init
```

---

## Usage

### Basic (uses config.json)
```bash
python extractor.py
```

### Specify a playlist directly
```bash
python extractor.py --playlist https://open.spotify.com/playlist/6Jq2DDdkPMMZhE7hlERQP7
```

### Skip YouTube resolution (much faster)
```bash
python extractor.py --no-youtube
```

### Output only CSV
```bash
python extractor.py --format csv
```

### All formats
```bash
python extractor.py --format all
```

---

## Output files

All files are saved to the `output/` folder (configurable) with a timestamp:

| File | Contents |
|------|----------|
| `names_TIMESTAMP.txt` | `Song Name - Artist` (one per line) |
| `spotify_links_TIMESTAMP.txt` | Spotify URLs (one per line) |
| `youtube_links_TIMESTAMP.txt` | `Song Name - Artist → YouTube URL` |
| `playlist_TIMESTAMP.csv` | All data in CSV (title, artist, spotify_url, youtube_url) |
| `playlist_TIMESTAMP.json` | Full structured data in JSON |

---

## Configuration reference

| Key | Default | Description |
|-----|---------|-------------|
| `client_id` | `""` | Spotify app Client ID |
| `client_secret` | `""` | Spotify app Client Secret |
| `playlist_id` | `""` | Playlist ID or full Spotify URL |
| `output_dir` | `"output"` | Folder to save files |
| `youtube_search` | `true` | Whether to resolve YouTube links |
| `youtube_delay_seconds` | `1.0` | Delay between YouTube searches (be polite) |
| `output_formats` | `["txt","csv","json"]` | Which formats to save |
| `name_format` | `"{title} - {artist}"` | Template for name list entries |

### Custom name format examples

```json
"name_format": "{title} - {artist}"       →  Blinding Lights - The Weeknd
"name_format": "{artist}: {title}"         →  The Weeknd: Blinding Lights
"name_format": "{title}"                   →  Blinding Lights
```

---

## CLI flags

```
--playlist  <url or id>   Override playlist from config
--no-youtube              Skip YouTube link resolution
--format    <fmt>         txt | csv | json | all
--init                    Create a default config.json and exit
```

---

## Requirements

- Python 3.6+
- No pip installs needed

---

## Notes

- YouTube scraping uses no API key — it searches `youtube.com/results` and grabs the first video ID. This works reliably but may break if YouTube changes their page structure.
- Spotify's API paginates at 100 tracks per request. A 4000-track playlist takes ~40 requests.
- Be mindful of rate limits if running repeatedly. The script includes small delays between requests.
