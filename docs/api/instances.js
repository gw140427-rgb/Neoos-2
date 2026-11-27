// NeoOS Cloud gateway for the Podroid VPS API.
//
// The browser only ever talks to this function; the phone's address and the
// API token stay in the deployment environment. Without NEOOS_BACKEND_URL the
// gateway fails closed instead of calling a baked-in host.
//
// Allowed surface (anything else is blocked here, before Docker is reached):
//   GET    /api/instances                    -> list + live stats
//   POST   /api/instances                    -> create a container
//   POST   /api/instances/{id}/start|stop|reboot
//   POST   /api/instances/{id}/exec          -> one-shot web terminal
//   DELETE /api/instances/{id}               -> destroy (protected ids refused)
//
// Container creation can pull an image on first use, so the function asks for
// a longer budget than the default.

export const config = { maxDuration: 60 };

// Same shape the backend accepts: 2..64 chars, alphanumeric first character.
const SLUG = '[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}';
const COLLECTION = /^\/api\/instances$/;
const ITEM = new RegExp('^/api/instances/' + SLUG + '$');
const ACTION = new RegExp('^/api/instances/' + SLUG + '/(start|stop|reboot|exec)$');

const KNOWN_PATHS = [COLLECTION, ITEM, ACTION];
const ROUTES = [
  { method: 'GET', path: COLLECTION },
  { method: 'POST', path: COLLECTION },
  { method: 'POST', path: ACTION },
  { method: 'DELETE', path: ITEM }
];

function allowedMethods(path) {
  const methods = ROUTES.filter((route) => route.path.test(path)).map((route) => route.method);
  return Array.from(new Set(methods)).concat('OPTIONS').join(', ');
}

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept');
  res.setHeader('Access-Control-Max-Age', '86400');
}

function validCreateBody(text) {
  let body;
  try {
    body = JSON.parse(text || '{}');
  } catch (err) {
    return null;
  }
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  if (typeof body.name !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$/.test(body.name)) return null;
  if (!['ubuntu', 'debian', 'alpine'].includes(body.os)) return null;
  if (body.instance_type !== undefined && (typeof body.instance_type !== 'string' || body.instance_type.length > 32)) return null;
  if (body.volume_gb !== undefined && (!Number.isInteger(body.volume_gb) || body.volume_gb < 1 || body.volume_gb > 64)) return null;
  return body;
}

async function readRequestBody(req) {
  // Vercel parses JSON bodies into req.body; a raw stream is still possible.
  if (req.body !== undefined && req.body !== null) {
    if (typeof req.body === 'string') return req.body;
    if (Buffer.isBuffer(req.body)) return req.body.toString('utf8');
    try {
      return JSON.stringify(req.body);
    } catch (err) {
      return '';
    }
  }
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 64 * 1024) throw new Error('body_too_large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  cors(res);

  const method = (req.method || 'GET').toUpperCase();
  if (method === 'OPTIONS') {
    res.setHeader('Allow', 'GET, POST, DELETE, OPTIONS');
    return res.status(204).end();
  }

  const BACKEND_URL = (process.env.NEOOS_BACKEND_URL || '').trim().replace(/\/+$/, '');
  const TOKEN = (process.env.NEOOS_API_TOKEN || '').trim();

  if (!BACKEND_URL) {
    return res.status(503).json({
      error: 'backend_not_configured',
      message: 'Set NEOOS_BACKEND_URL in the deployment environment.'
    });
  }

  const rawPath = (req.url || '/api/instances').split('?')[0];
  const path = rawPath.replace(/\/+$/, '') || '/';

  if (!KNOWN_PATHS.some((known) => known.test(path))) {
    return res.status(404).json({ error: 'not_found' });
  }

  const route = ROUTES.find((candidate) => candidate.method === method && candidate.path.test(path));
  if (!route) {
    res.setHeader('Allow', allowedMethods(path));
    return res.status(405).json({ error: 'method_not_allowed' });
  }

  let bodyText = '';
  if (method === 'POST') {
    try {
      bodyText = await readRequestBody(req);
    } catch (err) {
      return res.status(413).json({ error: 'body_too_large' });
    }
    if (COLLECTION.test(path)) {
      if (!validCreateBody(bodyText)) {
        return res.status(400).json({
          error: 'invalid_payload',
          message: 'name(2~64자), os(ubuntu|debian|alpine), volume_gb(1~64)만 허용됩니다.'
        });
      }
    }
    const contentType = String((req.headers && req.headers['content-type']) || '');
    if (!/^application\/json(;|$)/i.test(contentType)) {
      return res.status(415).json({ error: 'unsupported_media_type' });
    }
  }

  const headers = { Accept: 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const init = { method: method, headers: headers, redirect: 'error' };
  if (bodyText) {
    headers['Content-Type'] = 'application/json';
    init.body = bodyText;
  }

  // Never let a slow docker pull hold the function past its own budget.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 55 * 1000);
  init.signal = controller.signal;

  try {
    // redirect: 'error' keeps the bearer token from following a redirect elsewhere.
    const response = await fetch(`${BACKEND_URL}${path}`, init);
    const contentType = response.headers.get('content-type') || '';
    const text = await response.text();
    if (contentType.includes('application/json')) {
      try {
        return res.status(response.status).json(JSON.parse(text));
      } catch (err) {
        return res.status(502).json({
          error: 'backend_gateway_error',
          message: '백엔드 응답을 해석하지 못했습니다.'
        });
      }
    }
    return res.status(response.status).send(text);
  } catch (err) {
    // The internal backend address and the SDK error text stay on the server.
    const timedOut = err && (err.name === 'AbortError' || err.name === 'TimeoutError');
    return res.status(timedOut ? 504 : 502).json({
      error: timedOut ? 'backend_timeout' : 'backend_gateway_error',
      message: timedOut
        ? '백엔드 응답이 너무 늦었습니다.'
        : 'NeoOS 백엔드에 연결하지 못했습니다.'
    });
  } finally {
    clearTimeout(timer);
  }
}
