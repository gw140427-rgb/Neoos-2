import { timingSafeEqual } from 'node:crypto';

// Private owner console -> Podroid Docker API. This is intentionally
// single-owner access, not public multi-tenant authentication.
export const config = { maxDuration: 60 };

const SLUG = '[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}';
const COLLECTION = /^\/api\/instances$/;
const ITEM = new RegExp('^/api/instances/' + SLUG + '$');
const ACTION = new RegExp('^/api/instances/' + SLUG + '/(start|stop|reboot|pause|unpause|exec)$');
const ROUTES = [
  { method: 'GET', path: COLLECTION },
  { method: 'GET', path: new RegExp('^/api/instances/' + SLUG + '/logs$') },
  { method: 'POST', path: COLLECTION },
  { method: 'POST', path: ACTION },
  { method: 'DELETE', path: ITEM }
];

function safeEqual(left, right) {
  const a = Buffer.from(String(left || ''), 'utf8');
  const b = Buffer.from(String(right || ''), 'utf8');
  return a.length === b.length && a.length > 0 && timingSafeEqual(a, b);
}

function sendError(res, status, error, message) {
  return res.status(status).json({ error, message });
}

function allowedMethods(path) {
  const methods = ROUTES.filter((route) => route.path.test(path)).map((route) => route.method);
  return Array.from(new Set(methods)).concat('OPTIONS').join(', ');
}

async function readRequestBody(req) {
  if (req.body !== undefined && req.body !== null) {
    if (typeof req.body === 'string') return req.body;
    if (Buffer.isBuffer(req.body)) return req.body.toString('utf8');
    return JSON.stringify(req.body);
  }
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 16 * 1024) throw new Error('body_too_large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');

  const BACKEND_URL = (process.env.NEOOS_BACKEND_URL || '').trim().replace(/\/+$/, '');
  const BACKEND_TOKEN = (process.env.NEOOS_API_TOKEN || '').trim();
  const CONSOLE_TOKEN = (process.env.NEOOS_CONSOLE_TOKEN || '').trim();

  if (BACKEND_TOKEN.length < 32 || CONSOLE_TOKEN.length < 32) {
    return sendError(
      res,
      503,
      'gateway_not_configured',
      'Set NEOOS_API_TOKEN and NEOOS_CONSOLE_TOKEN to random secrets of at least 32 characters.'
    );
  }

  let backend;
  try {
    backend = new URL(BACKEND_URL);
  } catch (err) {
    return sendError(res, 503, 'backend_not_configured', 'Set NEOOS_BACKEND_URL to the HTTPS Podroid endpoint.');
  }
  if (backend.protocol !== 'https:' || !backend.hostname) {
    return sendError(res, 503, 'backend_not_configured', 'NEOOS_BACKEND_URL must use HTTPS.');
  }

  const suppliedConsoleToken = req.headers['x-neoos-console-token'] || '';
  if (!safeEqual(suppliedConsoleToken, CONSOLE_TOKEN)) {
    return sendError(res, 401, 'unauthorized', 'NeoOS 콘솔 접근 토큰을 확인해 줘.');
  }

  const method = (req.method || 'GET').toUpperCase();
  const rawPath = (req.url || '/api/instances').split('?')[0];
  const path = rawPath.replace(/\/+$/, '') || '/';

  if (method === 'OPTIONS') {
    res.setHeader('Allow', 'GET, POST, DELETE, OPTIONS');
    return res.status(204).end();
  }

  if (!ROUTES.some((route) => route.path.test(path))) {
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
      return sendError(res, 413, 'body_too_large', '요청 본문이 너무 커.');
    }
  }

  const headers = {
    Accept: 'application/json',
    Authorization: `Bearer ${BACKEND_TOKEN}`
  };
  const init = { method, headers, redirect: 'error' };
  if (bodyText) {
    headers['Content-Type'] = (req.headers && req.headers['content-type']) || 'application/json';
    init.body = bodyText;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 55 * 1000);
  init.signal = controller.signal;

  try {
    const target = new URL(path, backend);
    const response = await fetch(target, init);
    const contentType = response.headers.get('content-type') || '';
    const body = await response.text();
    if (contentType.includes('application/json')) {
      try {
        return res.status(response.status).json(JSON.parse(body));
      } catch (err) {
        return sendError(res, 502, 'backend_gateway_error', '백엔드 응답을 해석하지 못했습니다.');
      }
    }
    return res.status(response.status).send(body);
  } catch (err) {
    const timedOut = err && (err.name === 'AbortError' || err.name === 'TimeoutError');
    return sendError(
      res,
      timedOut ? 504 : 502,
      timedOut ? 'backend_timeout' : 'backend_gateway_error',
      timedOut ? 'Podroid 응답 시간이 초과됐어.' : 'NeoOS Podroid에 연결하지 못했어.'
    );
  } finally {
    clearTimeout(timer);
  }
}
