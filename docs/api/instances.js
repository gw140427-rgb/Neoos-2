export default async function handler(req, res) {
  // No hard-coded backend address: without NEOOS_BACKEND_URL the gateway fails
  // closed instead of silently calling a baked-in host.
  const BACKEND_URL = (process.env.NEOOS_BACKEND_URL || '').trim().replace(/\/+$/, '');
  const TOKEN = (process.env.NEOOS_API_TOKEN || '').trim();

  if (!BACKEND_URL) {
    res.setHeader('Cache-Control', 'no-store');
    return res.status(503).json({
      error: 'backend_not_configured',
      message: 'Set NEOOS_BACKEND_URL in the deployment environment.'
    });
  }

  // This gateway exposes read-only instance status. Mutations are blocked in both layers.
  if ((req.method || 'GET').toUpperCase() !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'method_not_allowed' });
  }

  const requestPath = req.url || '/api/instances';
  if (!requestPath.startsWith('/api/instances')) {
    return res.status(404).json({ error: 'not_found' });
  }

  const targetUrl = `${BACKEND_URL}${requestPath}`;
  const headers = { 'Accept': 'application/json' };
  if (TOKEN) {
    headers['Authorization'] = `Bearer ${TOKEN}`;
  }

  try {
    // redirect: 'error' keeps the bearer token from following a redirect elsewhere.
    const response = await fetch(targetUrl, { method: 'GET', headers: headers, redirect: 'error' });
    const contentType = response.headers.get('content-type') || '';
    res.setHeader('Cache-Control', 'no-store');
    if (contentType.includes('application/json')) {
      const data = await response.json();
      return res.status(response.status).json(data);
    }
    const text = await response.text();
    return res.status(response.status).send(text);
  } catch (err) {
    // The internal backend address and the SDK error text stay on the server.
    res.setHeader('Cache-Control', 'no-store');
    return res.status(502).json({
      error: 'backend_gateway_error',
      message: 'NeoOS 백엔드에 연결하지 못했습니다.'
    });
  }
}
