"""Vercel serverless function: CORS-bypassing reverse proxy for video URLs.

GET  /proxy?url=...                          → proxy single URL
GET  /proxy?url=...&download=1&filename=...  → proxy with Content-Disposition
POST /proxy  (form: segment[]+filename)      → download HLS segments, concatenate, serve
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

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': '*',
}


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

    def _send_cors_headers(self):
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)

    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(message.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        url_list = params.get('url')
        download_mode = 'download' in params
        filename_list = params.get('filename')
        dl_filename = filename_list[0] if filename_list else 'video.mp4'

        if not url_list:
            self._send_error(400, 'Missing url parameter')
            return

        target_url = url_list[0]

        try:
            target_parsed = urllib.parse.urlparse(target_url)
        except Exception:
            self._send_error(400, 'Invalid URL')
            return

        if target_parsed.scheme not in ('http', 'https'):
            self._send_error(400, 'Only http and https URLs are allowed')
            return

        hostname = target_parsed.hostname or ''
        if not ALLOWED_HOSTS_RE.match(hostname):
            self._send_error(403, f'Host not allowed: {hostname}')
            return

        req = urllib.request.Request(target_url, headers={
            'User-Agent': USER_AGENT,
            'Accept': '*/*',
            'Referer': f'{target_parsed.scheme}://{target_parsed.hostname}/',
        })

        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            self._send_error(e.code, str(e.reason))
            return
        except Exception as e:
            self._send_error(502, f'Upstream error: {e}')
            return

        content_type = resp.headers.get('Content-Type', 'application/octet-stream')
        is_m3u8 = target_url.endswith('.m3u8') or 'mpegurl' in content_type.lower()

        body = resp.read()
        resp.close()

        if is_m3u8:
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
            body = '\n'.join(rewritten).encode('utf-8')
            content_type = 'application/vnd.apple.mpegurl'

        self.send_response(200)
        if download_mode:
            self.send_header('Content-Type', 'application/octet-stream')
            safe_name = dl_filename.replace('"', '_')
            self.send_header('Content-Disposition', f'attachment; filename="{safe_name}"')
        else:
            self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """Download HLS segments, concatenate, and serve with Content-Disposition."""
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length)
        content_type = self.headers.get('Content-Type', '')

        segments = []
        filename = 'video.ts'

        if 'application/json' in content_type:
            try:
                obj = json.loads(raw_body)
                segments = obj.get('segments', [])
                filename = obj.get('filename', filename)
            except Exception:
                self._send_error(400, 'Invalid JSON')
                return
        else:
            # application/x-www-form-urlencoded
            params = urllib.parse.parse_qs(raw_body.decode('utf-8'))
            segments = params.get('segment', [])
            filename = (params.get('filename') or [filename])[0]

        if not segments:
            self._send_error(400, 'No segments provided')
            return

        for s in segments:
            hostname = ''
            try:
                hostname = urllib.parse.urlparse(s).hostname or ''
            except Exception:
                pass
            if not ALLOWED_HOSTS_RE.match(hostname):
                self._send_error(403, f'Host not allowed: {hostname}')
                return

        # Download all segments in parallel
        try:
            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(_fetch_url, segments))
        except Exception as e:
            self._send_error(502, f'Segment download failed: {e}')
            return

        # Stream segments to response
        total_size = sum(len(r) for r in results)
        safe_name = filename.replace('"', '_')
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="{safe_name}"')
        self.send_header('Content-Length', str(total_size))
        self._send_cors_headers()
        self.end_headers()
        for data in results:
            self.wfile.write(data)
