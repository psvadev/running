const STRAVA_TOKEN_URL = 'https://www.strava.com/oauth/token';

// Only the deployed app may use this Worker as its Strava token-exchange proxy.
// Note: CORS only blocks browser callers (another site embedding this URL) — a
// server-side script ignores it. That's the accepted limit here: a public static
// page can't authenticate itself (any shared secret is visible in view-source).
const ALLOWED_ORIGINS = ['https://psvadev.github.io'];

function corsHeaders(origin) {
  const headers = {
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
  }
  return headers;
}

function jsonResponse(body, status = 200, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(origin) },
  });
}

async function callStrava(params, origin) {
  let res;
  try {
    res = await fetch(STRAVA_TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    return jsonResponse({ error: 'Could not reach Strava' }, 502, origin);
  }
  let data;
  try {
    data = await res.json();
  } catch {
    return jsonResponse({ error: 'Invalid response from Strava' }, 502, origin);
  }
  if (!res.ok) {
    return jsonResponse({ error: data.message || 'Strava rejected the request' }, 400, origin);
  }
  return jsonResponse(data, 200, origin);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin');

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== 'POST') {
      return jsonResponse({ error: 'Not found' }, 404, origin);
    }

    const { pathname } = new URL(request.url);

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: 'Invalid JSON body' }, 400, origin);
    }

    if (pathname === '/exchange') {
      const { client_id, code } = body;
      if (!client_id || !code) return jsonResponse({ error: 'Missing client_id or code' }, 400, origin);
      return callStrava({
        client_id,
        client_secret: env.STRAVA_CLIENT_SECRET,
        code,
        grant_type: 'authorization_code',
      }, origin);
    }

    if (pathname === '/refresh') {
      const { client_id, refresh_token } = body;
      if (!client_id || !refresh_token) return jsonResponse({ error: 'Missing client_id or refresh_token' }, 400, origin);
      return callStrava({
        client_id,
        client_secret: env.STRAVA_CLIENT_SECRET,
        refresh_token,
        grant_type: 'refresh_token',
      }, origin);
    }

    return jsonResponse({ error: 'Not found' }, 404, origin);
  },
};
