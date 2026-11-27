export const config = { maxDuration: 30 };

const BACKEND = 'https://8091-agrbqrrn23duv6hcwf4exhnyre.instabox.tech';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const r = await fetch(BACKEND + '/health');
    const j = await r.json();
    return res.status(200).json(j);
  } catch (e) {
    return res.status(502).json({ ok: false, error: 'backend_unreachable' });
  }
}
