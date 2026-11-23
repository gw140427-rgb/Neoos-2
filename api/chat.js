export const config = { maxDuration: 60 };

const BACKEND = 'https://8091-agq4jaayolghua7jofmyvhd3a4.instabox.tech';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if ((req.method || '').toUpperCase() !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'method_not_allowed' });
  }
  try {
    const body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {});
    const r = await fetch(BACKEND + '/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Neo-Key': req.headers['x-neo-key'] || '',
      },
      body,
    });
    const text = await r.text();
    res.setHeader('Content-Type', 'application/json');
    return res.status(r.status).send(text);
  } catch (e) {
    return res.status(502).json({ error: 'backend_unreachable' });
  }
}
