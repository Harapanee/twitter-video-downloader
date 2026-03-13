"""Vercel serverless function: Download proxy with Content-Disposition.

GET  /download?url=...&filename=...  → proxy single URL with Content-Disposition
POST /download  (form: segment[]+filename) → download HLS segments, concatenate, serve
"""

from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import urllib.error
import re
import json
from concurrent.futures import ThreadPoolExecutor

ALLOWED_HOSTS_RE = re.compile(
    r'^(video\.twimg\.com'
    r'|video\.twimg-image\.cc'
    r'|video\.twimg-com\.com'
    r'|videy\.vedio\.cc'
    r'|[a-z0-9-]+\.videy-com\.cc'
    r'|[a-z0-9-]+\.twimg\.com'
    r'|[a-z0-9-]+\.twimg-com\.com'
    r'|[a-z0-9-]+\.akamaized\.net'
    r'|[a-z0-9-]+\.fun800\.click'
    r'|[a-z0-9-]+\.fun800\.cc'
    r'|[a-z0-9-]+\.io-d\.cc'
    r'|api\.fxtwitter\.com)$'
)

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


def _is_allowed(url):
    try:
        hostname = urllib.parse.urlparse(url).hostname or ''
        return bool(ALLOWED_HOSTS_RE.match(hostname))
    except Exception:
        return False


def _fetch_url(url):
    """Download a single URL and return its bytes."""
    parsed = urllib.parse.urlparse(url)
    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': '*/*',
        'Referer': f'{parsed.scheme}://{parsed.hostname}/',
    })
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read()
    resp.close()
    return data


class handler(BaseHTTPRequestHandler):

    def _send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def _send_error(self, code, msg):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self._send_cors()
        self.end_headers()
        self.wfile.write(msg.encode())

    def _send_download(self, data, filename):
        safe = filename.replace('"', '_')
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="{safe}"')
        self.send_header('Content-Length', str(len(data)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        url_list = params.get('url')
        filename = (params.get('filename') or ['video.mp4'])[0]

        if not url_list:
            self._send_error(400, 'Missing url parameter')
            return

        target_url = url_list[0]
        if not _is_allowed(target_url):
            self._send_error(403, 'Host not allowed')
            return

        try:
            data = _fetch_url(target_url)
        except urllib.error.HTTPError as e:
            self._send_error(e.code, str(e.reason))
            return
        except Exception as e:
            self._send_error(502, f'Upstream error: {e}')
            return

        self._send_download(data, filename)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        content_type = self.headers.get('Content-Type', '')

        segments = []
        filename = 'video.ts'

        if 'application/json' in content_type:
            try:
                obj = json.loads(body)
                segments = obj.get('segments', [])
                filename = obj.get('filename', filename)
            except Exception:
                self._send_error(400, 'Invalid JSON')
                return
        else:
            # application/x-www-form-urlencoded
            params = urllib.parse.parse_qs(body.decode('utf-8'))
            segments = params.get('segment', [])
            filename = (params.get('filename') or [filename])[0]

        if not segments:
            self._send_error(400, 'No segments provided')
            return

        for s in segments:
            if not _is_allowed(s):
                self._send_error(403, f'Host not allowed')
                return

        # Download all segments in parallel
        try:
            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(_fetch_url, segments))
        except Exception as e:
            self._send_error(502, f'Segment download failed: {e}')
            return

        # Concatenate
        total = sum(len(r) for r in results)
        merged = bytearray(total)
        offset = 0
        for r in results:
            merged[offset:offset + len(r)] = r
            offset += len(r)

        self._send_download(bytes(merged), filename)
