/**
 * Vercel Edge Function: Download proxy with Content-Disposition header.
 * Ensures iOS Safari saves files directly to the Files app Downloads folder.
 *
 * GET  /download?url=...&filename=...  → stream-proxy a single URL
 * POST /download  (form: segment[], filename) → download HLS segments, concatenate, serve as TS
 */

export const config = { runtime: 'edge' };

const ALLOWED_RE =
  /^(video\.twimg\.com|video\.twimg-image\.cc|video\.twimg-com\.com|videy\.vedio\.cc|[a-z0-9-]+\.videy-com\.cc|[a-z0-9-]+\.twimg\.com|[a-z0-9-]+\.twimg-com\.com|[a-z0-9-]+\.akamaized\.net|[a-z0-9-]+\.fun800\.click|[a-z0-9-]+\.fun800\.cc|[a-z0-9-]+\.io-d\.cc|api\.fxtwitter\.com)$/;

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' +
  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

function isAllowed(url) {
  try {
    return ALLOWED_RE.test(new URL(url).hostname);
  } catch {
    return false;
  }
}

function safeName(f) {
  return (f || 'video.mp4').replace(/"/g, '_');
}

function dlHeaders(filename, extra) {
  return {
    'Content-Type': 'application/octet-stream',
    'Content-Disposition': `attachment; filename="${safeName(filename)}"`,
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': '*',
    ...extra,
  };
}

function errResp(code, msg) {
  return new Response(msg, {
    status: code,
    headers: {
      'Content-Type': 'text/plain',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': '*',
      },
    });
  }

  /* ── GET: stream-proxy a single video URL ── */
  if (req.method === 'GET') {
    const { searchParams } = new URL(req.url);
    const targetUrl = searchParams.get('url');
    const filename = searchParams.get('filename') || 'video.mp4';

    if (!targetUrl || !isAllowed(targetUrl)) {
      return errResp(400, 'Invalid or disallowed URL');
    }

    const upstream = await fetch(targetUrl, {
      headers: { 'User-Agent': UA, Accept: '*/*' },
    });

    if (!upstream.ok) {
      return errResp(upstream.status, 'Upstream error: ' + upstream.status);
    }

    const cl = upstream.headers.get('content-length');
    return new Response(upstream.body, {
      status: 200,
      headers: dlHeaders(filename, cl ? { 'Content-Length': cl } : {}),
    });
  }

  /* ── POST: download HLS segments, concatenate, serve ── */
  if (req.method === 'POST') {
    let segments, filename;

    const ct = req.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const json = await req.json();
      segments = json.segments || [];
      filename = json.filename || 'video.ts';
    } else {
      const form = await req.formData();
      segments = form.getAll('segment');
      filename = form.get('filename') || 'video.ts';
    }

    if (!segments.length) {
      return errResp(400, 'No segments provided');
    }

    for (const s of segments) {
      if (!isAllowed(s)) {
        return errResp(403, 'Disallowed segment host');
      }
    }

    // Start all fetches in parallel (get response objects)
    const responses = await Promise.all(
      segments.map((url) =>
        fetch(url, { headers: { 'User-Agent': UA } }).then((r) => {
          if (!r.ok) throw new Error('Segment ' + r.status);
          return r;
        })
      )
    );

    // Compute total Content-Length if all segments report it
    let totalSize = 0;
    let allHaveCL = true;
    for (const r of responses) {
      const cl = r.headers.get('content-length');
      if (cl) {
        totalSize += parseInt(cl, 10);
      } else {
        allHaveCL = false;
        break;
      }
    }

    // Stream segments in order
    const stream = new ReadableStream({
      async start(controller) {
        try {
          for (const resp of responses) {
            const reader = resp.body.getReader();
            for (;;) {
              const { done, value } = await reader.read();
              if (done) break;
              controller.enqueue(value);
            }
          }
          controller.close();
        } catch (e) {
          controller.error(e);
        }
      },
    });

    return new Response(stream, {
      status: 200,
      headers: dlHeaders(
        filename,
        allHaveCL ? { 'Content-Length': String(totalSize) } : {}
      ),
    });
  }

  return errResp(405, 'Method not allowed');
}
