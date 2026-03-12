#!/usr/bin/env python3
"""Local proxy server for Twitter Video Downloader.

Serves index.html and proxies video requests to bypass CORS restrictions.

Usage:
    python3 server.py
    # Open http://localhost:8888 in your browser
"""

import concurrent.futures
import http.server
import urllib.request
import urllib.parse
import urllib.error
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import partial

import requests
from requests.adapters import HTTPAdapter

PORT = 8888
BIND = '127.0.0.1'
CHUNK_SIZE = 262144
MAX_WORKERS = 10

# Allowed hostname patterns
ALLOWED_HOSTS_RE = re.compile(
    r'^(video\.twimg\.com'
    r'|video\.twimg-image\.cc'
    r'|video\.twimg-com\.com'
    r'|videy\.vedio\.cc'
    r'|[a-z0-9-]+\.twimg\.com'
    r'|[a-z0-9-]+\.twimg-com\.com'
    r'|[a-z0-9-]+\.akamaized\.net'
    r'|[a-z0-9-]+\.fun800\.click'
    r'|[a-z0-9-]+\.fun800\.cc'
    r'|api\.fxtwitter\.com)$'
)

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


def _make_session():
    """Create a requests.Session with connection pooling."""
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    s.headers.update({'User-Agent': USER_AGENT, 'Accept': '*/*'})
    return s

# Shared session for proxy requests (reuses TCP/TLS connections)
_proxy_session = _make_session()


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and proxies allowed URLs."""

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/proxy':
            self._handle_proxy(parsed)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/convert':
            self._handle_convert()
        else:
            self.send_error(404)

    def _handle_proxy(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        url_list = params.get('url')

        if not url_list:
            self.send_error(400, 'Missing url parameter')
            return

        target_url = url_list[0]

        # Validate the target URL
        try:
            target_parsed = urllib.parse.urlparse(target_url)
        except Exception:
            self.send_error(400, 'Invalid URL')
            return

        hostname = target_parsed.hostname or ''
        if not ALLOWED_HOSTS_RE.match(hostname):
            self.send_error(403, f'Host not allowed: {hostname}')
            return

        # Fetch the target URL with connection-pooled session
        try:
            resp = _proxy_session.get(
                target_url,
                headers={'Referer': f'{target_parsed.scheme}://{target_parsed.hostname}/'},
                timeout=30,
                stream=True,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            self.send_error(e.response.status_code if e.response else 502, str(e))
            return
        except Exception as e:
            self.send_error(502, f'Upstream error: {e}')
            return

        # Send response headers
        content_type = resp.headers.get('Content-Type', 'application/octet-stream')
        is_m3u8 = target_url.endswith('.m3u8') or 'mpegurl' in content_type.lower()

        if is_m3u8:
            # Rewrite relative URLs in m3u8 playlists to absolute URLs
            # so HLS.js resolves them correctly through the proxy
            body = resp.content
            base_url = target_url.rsplit('/', 1)[0] + '/'
            text = body.decode('utf-8')
            lines = text.split('\n')
            rewritten = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    if not stripped.startswith('http'):
                        stripped = base_url + stripped
                    rewritten.append(stripped)
                else:
                    rewritten.append(line)
            out = '\n'.join(rewritten).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Content-Length', str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(200)
            self.send_header('Content-Type', content_type)

            content_length = resp.headers.get('Content-Length')
            if content_length:
                self.send_header('Content-Length', content_length)

            self.end_headers()

            # Stream response body in chunks
            try:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _handle_convert(self):
        """Receive TS segment URLs as JSON, download them, convert to MP4 with ffmpeg."""
        if not shutil.which('ffmpeg'):
            self.send_error(500, 'ffmpeg not found')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except Exception:
            self.send_error(400, 'Invalid JSON')
            return

        segment_urls = data.get('segments', [])
        if not segment_urls:
            self.send_error(400, 'No segments provided')
            return

        # Validate all URLs
        for url in segment_urls:
            try:
                p = urllib.parse.urlparse(url)
                if not ALLOWED_HOSTS_RE.match(p.hostname or ''):
                    self.send_error(403, f'Host not allowed: {p.hostname}')
                    return
            except Exception:
                self.send_error(400, f'Invalid URL')
                return

        tmpdir = tempfile.mkdtemp(prefix='tvdl_')
        try:
            # Download all TS segments in parallel with connection reuse
            session = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=MAX_WORKERS,
                pool_maxsize=MAX_WORKERS,
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            session.headers.update({
                'User-Agent': USER_AGENT,
                'Accept': '*/*',
            })

            def _download_segment(args):
                i, url = args
                ts_path = os.path.join(tmpdir, f'seg{i:04d}.ts')
                resp = session.get(url, timeout=30, stream=True)
                resp.raise_for_status()
                with open(ts_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                return ts_path

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                ts_files = list(pool.map(_download_segment, enumerate(segment_urls)))

            session.close()

            # Create concat file for ffmpeg
            concat_path = os.path.join(tmpdir, 'concat.txt')
            with open(concat_path, 'w') as f:
                for ts_path in ts_files:
                    f.write(f"file '{ts_path}'\n")

            # Convert with ffmpeg
            mp4_path = os.path.join(tmpdir, 'output.mp4')
            result = subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', concat_path,
                '-c', 'copy',
                '-movflags', '+faststart',
                mp4_path,
            ], capture_output=True, timeout=120)

            if result.returncode != 0:
                sys.stderr.write(f'ffmpeg error: {result.stderr.decode()}\n')
                self.send_error(500, 'ffmpeg conversion failed')
                return

            # Send the MP4 file
            mp4_size = os.path.getsize(mp4_path)
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(mp4_size))
            self.end_headers()

            with open(mp4_path, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        except requests.HTTPError as e:
            self.send_error(e.response.status_code if e.response else 502, str(e))
        except Exception as e:
            self.send_error(502, f'Convert error: {e}')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def log_message(self, format, *args):
        path = args[0] if args else ''
        if '/proxy?' in str(path):
            # Show proxy requests with target URL
            sys.stderr.write(f'\033[36m[proxy]\033[0m {format % args}\n')
        else:
            sys.stderr.write(f'[static] {format % args}\n')


def main():
    handler = partial(ProxyHandler, directory='.')
    server = http.server.HTTPServer((BIND, PORT), handler)
    print(f'\033[1;32mTwitter Video Downloader Server\033[0m')
    print(f'  http://{BIND}:{PORT}')
    print(f'  Press Ctrl+C to stop\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.shutdown()


if __name__ == '__main__':
    main()
