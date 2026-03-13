// Vercel Edge Function: streaming download proxy with Content-Disposition
// Unlike Python serverless functions, Edge Functions support streaming (no 4.5MB limit)
export const config = { runtime: 'edge' };

const ALLOWED_HOSTS_RE = /^(video\.twimg\.com|video\.twimg-image\.cc|video\.twimg-com\.com|videy\.vedio\.cc|[a-z0-9-]+\.videy-com\.cc|[a-z0-9-]+\.twimg\.com|[a-z0-9-]+\.twimg-com\.com|[a-z0-9-]+\.akamaized\.net|[a-z0-9-]+\.fun800\.click|[a-z0-9-]+\.fun800\.cc|[a-z0-9-]+\.io-d\.cc|api\.fxtwitter\.com)$/;

const USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

function isAllowed(url) {
  try {
    return ALLOWED_HOSTS_RE.test(new URL(url).hostname);
  } catch { return false; }
}

function fetchUrl(url) {
  const parsed = new URL(url);
  return fetch(url, {
    headers: {
      'User-Agent': USER_AGENT,
      'Accept': '*/*',
      'Referer': `${parsed.protocol}//${parsed.hostname}/`,
    },
  });
}

export default async function handler(request) {
  // GET: proxy single URL with Content-Disposition (for direct video download)
  if (request.method === 'GET') {
    const url = new URL(request.url);
    const targetUrl = url.searchParams.get('url');
    const filename = url.searchParams.get('filename') || 'video.mp4';

    if (!targetUrl || !isAllowed(targetUrl)) {
      return new Response('Bad request', { status: 400 });
    }

    const resp = await fetchUrl(targetUrl);
    if (!resp.ok) {
      return new Response(`Upstream error: ${resp.status}`, { status: 502 });
    }

    const safeName = filename.replace(/"/g, '_');
    const headers = {
      'Content-Type': 'application/octet-stream',
      'Content-Disposition': `attachment; filename="${safeName}"`,
    };
    const cl = resp.headers.get('content-length');
    if (cl) headers['Content-Length'] = cl;

    return new Response(resp.body, { headers });
  }

  // POST: download HLS segments, concatenate, stream with Content-Disposition
  if (request.method === 'POST') {
    let segments, filename;

    const ct = request.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const body = await request.json();
      segments = body.segments || [];
      filename = body.filename || 'video.ts';
    } else {
      const formData = await request.formData();
      segments = formData.getAll('segment');
      filename = formData.get('filename') || 'video.ts';
    }

    if (!segments.length) {
      return new Response('No segments', { status: 400 });
    }

    for (const s of segments) {
      if (!isAllowed(s)) {
        return new Response('Host not allowed', { status: 403 });
      }
    }

    // Start all segment fetches in parallel (connections open simultaneously)
    const responses = await Promise.all(segments.map(url => fetchUrl(url)));

    for (const resp of responses) {
      if (!resp.ok) {
        return new Response('Segment download failed', { status: 502 });
      }
    }

    const safeName = filename.replace(/"/g, '_');

    // Stream concatenated segment bodies
    const stream = new ReadableStream({
      async start(controller) {
        try {
          for (const resp of responses) {
            const reader = resp.body.getReader();
            while (true) {
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
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${safeName}"`,
      },
    });
  }

  return new Response('Method not allowed', { status: 405 });
}
