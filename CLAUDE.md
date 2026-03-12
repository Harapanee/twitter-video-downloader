# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Twitter Video Downloader — a two-file web app that downloads videos from `video.twimg.com`, `video.twimg-image.cc`, and `videy.vedio.cc`. It runs as a local Python HTTP server that serves the frontend and proxies video requests to bypass CORS.

## Running

```bash
python3 server.py
# Open http://localhost:8888
```

Requires `ffmpeg` on PATH for server-side HLS→MP4 conversion (the `/convert` endpoint).

## Architecture

- **`server.py`** — Python stdlib HTTP server (no dependencies) on `127.0.0.1:8888`. Three endpoints:
  - `GET /` — serves `index.html` (static file handler)
  - `GET /proxy?url=<encoded_url>` — CORS-bypassing reverse proxy; validates hostname against `ALLOWED_HOSTS_RE` allowlist; rewrites relative URLs in `.m3u8` playlists to absolute
  - `POST /convert` — accepts JSON `{segments: [url, ...]}`, downloads TS segments, concatenates with ffmpeg, streams back MP4

- **`index.html`** — single-file SPA (HTML + CSS + JS, no build step). Uses:
  - **HLS.js** (CDN) for HLS playback with proxy URL rewriting via `xhrSetup`
  - **mux.js** (CDN) for client-side TS→MP4 transmuxing (fallback when server ffmpeg unavailable)
  - CORS proxy cascade (`corsproxy.io`, `allorigins.win`) as fallback when not using local server

- **Video loading flow**: URL input → validate against allowed hosts → if `twimg-image.cc`/`videy.vedio.cc`: fetch page HTML, parse `__NUXT_DATA__` for HLS playlist URL, parse master playlist for quality levels → HLS.js playback. If `video.twimg.com`: direct `<video>` src with blob fallback.

- **Download flow**: HLS videos → fetch segment playlist → either POST segment URLs to `/convert` (server ffmpeg) or download segments client-side and transmux with mux.js → trigger browser download. Direct videos → stream-download with progress.

## Key details

- UI text is in Japanese
- All proxied URLs are validated against `ALLOWED_HOSTS_RE` (server) and `ALLOWED_HOSTS` array (client)
- The server streams large responses in 64KB chunks
- No external Python dependencies — uses only stdlib modules
