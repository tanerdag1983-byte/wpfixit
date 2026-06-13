# Deployment

## Frontend

Deploy `frontend/` as a Vite project on Vercel. Configure:

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Add the production URL to Supabase Auth redirect URLs and to the Google and
Microsoft provider allowlists. `frontend/vercel.json` preserves SPA routes and
adds baseline browser security headers.

## API

Create a Render Blueprint from `infrastructure/render.yaml`. Before the first
deploy, provide all variables marked `sync: false`. The pre-deploy command runs
`alembic upgrade head`; Render probes `/health`.

Set `WP_FIXPILOT_TRUSTED_HOSTS` to the API hostname only, and
`WP_FIXPILOT_CORS_ORIGINS` to the exact Vercel production and preview origins
that may call the API.

## Authentication

Enable Google and Microsoft Azure in Supabase Auth. Use the Supabase callback
URL in each provider console and add the frontend URL to Supabase's redirect
allowlist. The API verifies asymmetric access tokens through Supabase JWKS and
retains HS256 support for legacy projects.

Run before and after deployment:

```bash
python3 infrastructure/smoke_check.py
python3 infrastructure/smoke_check.py --api-url https://api.example.com
```
