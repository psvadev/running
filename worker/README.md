# Strava OAuth Worker

Stateless Cloudflare Worker handling the Strava OAuth token exchange (`/exchange`) and refresh (`/refresh`). Holds `STRAVA_CLIENT_SECRET` so it never has to live in `puls.html` or the browser.

## Deploy

From this `worker/` folder:

```
npx wrangler login
npx wrangler secret put STRAVA_CLIENT_SECRET
npx wrangler deploy
```

- `wrangler login` — one-time, opens a browser to authorize your Cloudflare account.
- `wrangler secret put` — prompts you to paste the Strava app's Client Secret; stored in Cloudflare's environment, never committed to git.
- `wrangler deploy` — uploads `index.js`, prints the live URL (e.g. `https://puls-strava-auth.<your-subdomain>.workers.dev`).

Paste that URL into Innstillinger → Strava → Worker URL in the app.

## Redeploying after code changes

Just re-run `npx wrangler deploy` — the secret persists across deploys, no need to set it again.
