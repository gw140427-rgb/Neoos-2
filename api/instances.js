export default async function handler(req, res) {
  const BACKEND_URL = (process.env.NEOOS_BACKEND_URL || '').replace(/\\/+$/, '');
  const TOKEN = (process.env.NEOOS_API_TOKEN || '').trim();

  if (!BACKEND_URL || TOKEN.length < 32) {
    return res.status(503).setHeader('Cache-Control', 'no-store').json({
      error: 'backend_not_configured',
      message: 'Set NEOOS_BACKEND_URL and a 32-character NEOOS_API_TOKEN in the deployment environment.'
    });
  }

  const method = (req.method || 'GET').toUpperCase();
  if (!['GET', 'POST', 'DELETE'].includes(method)) {
    return res.status(405).setHeader('Allow', 'GET, POST, DELETE').json({ error: 'method_not_allowed' });
  }

  const requestPath = req.url || '/api/instances';
  if (!requestPath.startsWith('/api/instances')) {
    return res.status(404).json({ error: 'not_found' });
  }
  const targetUrl = `${BACKEND_URL}${requestPath}`;

  try {
    const fetchOptions = {
      method,
      headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json'
      }
    };

    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method) && req.body) {
      fetchOptions.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    }

    const response = await fetch(targetUrl, fetchOptions);
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await response.json();
      return res.status(response.status).json(data);
    }
    const text = await response.text();
    return res.status(response.status).send(text);
  } catch (err) {
    return res.status(502).setHeader('Cache-Control', 'no-store').json({
      error: 'backend_gateway_error',
      message: 'The configured NeoOS backend could not be reached.'
    });
  }
}
