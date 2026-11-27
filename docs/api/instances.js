// NeoOS Cloud gateway for the Podroid VPS API.
//
// The browser talks only to this function; the node address and API token stay
// in the deployment environment. Without NEOOS_BACKEND_URL it fails closed.
//
// Allowed surface:
//   GET    /api/instances                    -> list + live stats
//   POST   /api/instances                    -> create a guest container
//   POST   /api/instances/{id}/start|stop|reboot|exec
//   DELETE /api/instances/{id}               -> destroy (protected ids refused)

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

function bodyText(req) {
  if (req.body !== undefined && req.body !== null) {
    return typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
  }
  return '';
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

  let text = '';
  if (method === 'POST') {
    text = bodyText(req);
    if (COLLECTION.test(path) && !validCreateBody(text)) {
      return res.status(400).json({
        error: 'invalid_payload',
        message: 'name(2~64자), os(ubuntu|debian|alpine), volume_gb(1~64)만 허용됩니다.'
      });
    }
    const contentType = String((req.headers && req.headers['content-type']) || '');
    if (!/^application\/json(;|$)/i.test(contentType)) {
      return res.status(415).json({ error: 'unsupported_media_type' });
    }
  }

  const headers = { Accept: 'application/json' };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  if (text) headers['Content-Type'] = 'application/json';
  const init = { method, headers, redirect: 'error', body: text || undefined };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 55 * 1000);
  init.signal = controller.signal;

  try {
    const response = await fetch(`${BACKEND_URL}${path}`, init);
    const responseText = await response.text();
    const localFallback = () => res.status(503).json({
      error: 'backend_not_configured',
      message: 'Podroid 백엔드에 연결할 수 없어. 콘솔이 로컬 엔진으로 전환합니다.'
    });
    if (!response.ok || !responseText.trim()) return localFallback();
    try {
      JSON.parse(responseText);
    } catch (err) {
      return localFallback();
    }
    res.setHeader('Content-Type', 'application/json');
    return res.status(response.status).send(responseText);
  } catch (err) {
    const timedOut = err && (err.name === 'AbortError' || err.name === 'TimeoutError');
    return res.status(timedOut ? 504 : 502).json({
      error: timedOut ? 'backend_timeout' : 'backend_gateway_error',
      message: timedOut ? '백엔드 응답이 너무 늦었습니다.' : 'Podroid 백엔드에 연결하지 못했습니다.'
    });
  } finally {
    clearTimeout(timer);
  }
}
