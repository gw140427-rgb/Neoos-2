export default async function handler(req, res) {
  const BACKEND_URL = process.env.NEOOS_BACKEND_URL || 'http://3.27.117.86:8080';
  const TOKEN = process.env.NEOOS_API_TOKEN || 'neoos-vps-api-token-2026-sydney-secure-production-gw';

  // Construct target URL
  const targetUrl = `${BACKEND_URL}${req.url}`;

  try {
    const fetchOptions = {
      method: req.method,
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
    return res.status(502).json({
      error: 'backend_gateway_error',
      message: err.message,
      target: targetUrl
    });
  }
}
