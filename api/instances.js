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

  const BACKEND_URL = (process.env.NEOOS_BACKEND_URL || '').trim().replace(/\/+$/, '');
  const TOKEN = (process.env.NEOOS_API_TOKEN || '').trim();

  if (!BACKEND_URL) {
    return res.status(503).json({
      error: 'backend_not_configured',
      message: 'Set NEOOS_BACKEND_URL in the deployment environment.'
    });
  }

  const method = (req.method || 'GET').toUpperCase();
  const rawPath = (req.url || '/api/instances').split('?')[0];
  const path = rawPath.replace(/\/+$/, '') || '/';

  if (method === 'OPTIONS') {
    // Same-origin console needs no preflight; this only keeps cross-origin
    // probes from being answered with a confusing 405.
    res.setHeader('Allow', 'GET, POST, DELETE, OPTIONS');
    return res.status(204).end();
  }

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
  }

  const headers = { Accept: 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const init = { method: method, headers: headers, redirect: 'error' };
  if (bodyText) {
    headers['Content-Type'] = (req.headers && req.headers['content-type']) || 'application/json';
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
