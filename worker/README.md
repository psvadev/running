# Strava OAuth Worker

Stateless Cloudflare Worker handling the Strava OAuth token exchange (`/exchange`) and refresh (`/refresh`). Holds `STRAVA_CLIENT_SECRET` so it never has to live in `puls.html` or the browser.

## Option A — Cloudflare dashboard (no local tools, recommended if you don't already have Node/npm)

### 1. Register a Strava API app
- Go to https://www.strava.com/settings/api (log in with your Strava account)
- Create an app — name/website/callback domain can be anything reasonable; callback domain should match where `puls.html` is hosted (e.g. `psvadev.github.io`)
- Copy the **Client ID** and **Client Secret** it shows you

### 2. Create the Worker
- Go to https://dash.cloudflare.com (free account is fine) → **Workers & Pages** → **Create** → **Create Worker**
- Give it a name (e.g. `puls-strava-auth`) → **Deploy** (this creates a placeholder and its URL)

### 3. Paste in the real code
- On the worker's page, click **Edit code**
- Replace the default content with the full contents of [`index.js`](index.js) in this folder
- **Save and deploy**

### 4. Add the secret
- Worker's page → **Settings** → **Variables and Secrets** → **Add**
- Name: `STRAVA_CLIENT_SECRET`, type: **Secret** (encrypted), value: the Client Secret from step 1
- Save/deploy

### 5. Get the URL and wire it up
- The worker's overview page shows its live URL (e.g. `https://puls-strava-auth.<your-subdomain>.workers.dev`)
- In `puls.html` → **Innstillinger → Strava**, paste in the **Client ID** (step 1) and this **Worker URL**, then click "Koble til Strava"

### Redeploying after code changes
Repeat step 3 (Edit code → paste updated `index.js` → Save and deploy). The secret persists — no need to re-add it.

## Option B — CLI (`wrangler`), if you already have Node/npm installed

From this `worker/` folder:

```
npx wrangler login
npx wrangler secret put STRAVA_CLIENT_SECRET
npx wrangler deploy
```

- `wrangler login` — one-time, opens a browser to authorize your Cloudflare account.
- `wrangler secret put` — prompts you to paste the Strava app's Client Secret; stored in Cloudflare's environment, never committed to git.
- `wrangler deploy` — uploads `index.js`, prints the live URL.

Paste that URL into Innstillinger → Strava → Worker URL in the app.

### Redeploying after code changes
Just re-run `npx wrangler deploy` — the secret persists across deploys.
