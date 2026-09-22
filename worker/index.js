// Cloudflare Worker: CORS-bypassing reverse proxy + streaming download for Twitter/X video URLs.
// Migrated from Vercel (api/proxy.py + api/download.js). Same paths/params as before.
const ALLOWED_HOSTS_RE = /^(video\.twimg\.com|video\.twimg-image\.cc|video\.twimg-com\.com|videy\.vedio\.cc|[a-z0-9-]+\.twimg-image\.cc|[a-z0-9-]+\.vedio\.cc|[a-z0-9-]+\.videy-com\.cc|[a-z0-9-]+\.twimg\.com|[a-z0-9-]+\.twimg-com\.com|[a-z0-9-]+\.akamaized\.net|[a-z0-9-]+\.fun800\.click|[a-z0-9-]+\.fun800\.cc|[a-z0-9-]+\.gofileapp\.com|[a-z0-9-]+\.io-d\.cc|api\.fxtwitter\.com|(www\.)?gofile\.beauty|[a-z0-9-]+\.slicedrive\.com|[a-z0-9-]+\.file-photo\.com)$/;
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': '*' };
const allowed = (u) => { try { const p = new URL(u); return (p.protocol === 'http:' || p.protocol === 'https:') && ALLOWED_HOSTS_RE.test(p.hostname); } catch { return false; } };
const up = (u, init = {}) => { const p = new URL(u); return fetch(u, { ...init, headers: { 'User-Agent': UA, Accept: '*/*', Referer: `${p.protocol}//${p.hostname}/`, ...(init.headers || {}) } }); };
const err = (code, msg) => new Response(msg, { status: code, headers: { 'Content-Type': 'text/plain', ...CORS } });

async function proxy(req) {
  const url = new URL(req.url);
  if (req.method === 'OPTIONS') return new Response(null, { status: 200, headers: CORS });
  if (req.method === 'POST' && url.searchParams.has('forward')) {
    const target = url.searchParams.get('url');
    if (!allowed(target)) return err(403, 'Host not allowed');
    const h = { 'Content-Type': req.headers.get('content-type') || 'application/json', Origin: new URL(target).origin };
    for (const k of ['x-token', 'x-shield-bypass']) { const v = req.headers.get(k); if (v) h[k] = v; }
    const r = await up(target, { method: 'POST', body: await req.arrayBuffer(), headers: h });
    return new Response(r.body, { status: r.status, headers: { 'Content-Type': r.headers.get('content-type') || 'application/json', ...CORS } });
  }
  if (req.method === 'POST') return segments(req);
  const target = url.searchParams.get('url');
  if (!target) return err(400, 'Missing url parameter');
  if (!allowed(target)) return err(403, 'Host not allowed');
  const r = await up(target);
  if (!r.ok) return err(r.status, r.statusText);
  let ct = r.headers.get('content-type') || 'application/octet-stream';
  const isM3u8 = target.endsWith('.m3u8') || ct.toLowerCase().includes('mpegurl');
  const isDownload = url.searchParams.has('download');
  if (isM3u8) {
    const base = target.slice(0, target.lastIndexOf('/') + 1);
    const text = (await r.text()).split('\n').map((l) => { const s = l.trim(); return s && !s.startsWith('#') && !s.startsWith('http') ? base + s : l; }).join('\n');
    const headers = { 'Content-Type': 'application/vnd.apple.mpegurl', ...CORS };
    if (isDownload) {
      headers['Content-Type'] = 'application/octet-stream';
      headers['Content-Disposition'] = `attachment; filename="${(url.searchParams.get('filename') || 'video.m3u8').replace(/"/g, '_')}"`;
    }
    return new Response(text, { headers });
  }
  const headers = { 'Content-Type': ct, ...CORS };
  if (isDownload) {
    headers['Content-Type'] = 'application/octet-stream';
    headers['Content-Disposition'] = `attachment; filename="${(url.searchParams.get('filename') || 'video.mp4').replace(/"/g, '_')}"`;
  }
  const cl = r.headers.get('content-length'); if (cl) headers['Content-Length'] = cl;
  return new Response(r.body, { headers });
}

async function segments(req) {
  const ct = req.headers.get('content-type') || '';
  let segs = [], filename = 'video.ts';
  if (ct.includes('application/json')) { const b = await req.json(); segs = b.segments || []; filename = b.filename || filename; }
  else { const f = await req.formData(); segs = f.getAll('segment'); filename = f.get('filename') || filename; }
  if (!segs.length) return err(400, 'No segments provided');
  if (!segs.every(allowed)) return err(403, 'Host not allowed');
  const responses = await Promise.all(segs.map((s) => up(s)));
  for (const r of responses) { if (!r.ok) return err(502, `Segment download failed: ${r.status}`); }
  const { readable, writable } = new TransformStream();
  (async () => { for (const r of responses) await r.body.pipeTo(writable, { preventClose: true }); await writable.close(); })();
  return new Response(readable, { headers: { 'Content-Type': 'application/octet-stream', 'Content-Disposition': `attachment; filename="${String(filename).replace(/"/g, '_')}"`, ...CORS } });
}

export default {
  async fetch(req, env) {
    const { pathname } = new URL(req.url);
    if (pathname === '/proxy' || pathname === '/api/proxy') return proxy(req);
    if (pathname === '/download' || pathname === '/api/download') {
      if (req.method === 'POST') return segments(req);
      const dlUrl = new URL(req.url);
      dlUrl.pathname = dlUrl.pathname.replace('/download', '/proxy');
      dlUrl.searchParams.set('download', '1');
      return proxy(new Request(dlUrl.toString(), req));
    }
    return env.ASSETS.fetch(req);
  },
};
