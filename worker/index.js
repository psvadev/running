const STRAVA_TOKEN_URL = 'https://www.strava.com/oauth/token';

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders() },
  });
}

async function callStrava(params) {
  let res;
  try {
    res = await fetch(STRAVA_TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    return jsonResponse({ error: 'Could not reach Strava' }, 502);
  }
  let data;
  try {
    data = await res.json();
  } catch {
    return jsonResponse({ error: 'Invalid response from Strava' }, 502);
  }
  if (!res.ok) {
    return jsonResponse({ error: data.message || 'Strava rejected the request' }, 400);
  }
  return jsonResponse(data);
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    if (request.method !== 'POST') {
      return jsonResponse({ error: 'Not found' }, 404);
    }

    const { pathname } = new URL(request.url);

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: 'Invalid JSON body' }, 400);
    }

    if (pathname === '/exchange') {
      const { client_id, code } = body;
      if (!client_id || !code) return jsonResponse({ error: 'Missing client_id or code' }, 400);
      return callStrava({
        client_id,
        client_secret: env.STRAVA_CLIENT_SECRET,
        code,
        grant_type: 'authorization_code',
      });
    }

    if (pathname === '/refresh') {
      const { client_id, refresh_token } = body;
      if (!client_id || !refresh_token) return jsonResponse({ error: 'Missing client_id or refresh_token' }, 400);
      return callStrava({
        client_id,
        client_secret: env.STRAVA_CLIENT_SECRET,
        refresh_token,
        grant_type: 'refresh_token',
      });
    }

    return jsonResponse({ error: 'Not found' }, 404);
  },
};
