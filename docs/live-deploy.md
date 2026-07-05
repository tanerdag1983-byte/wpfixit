# WP FixPilot Live Deploy

This project deploys as three pieces:

- Frontend: Vercel, root directory `frontend`
- Backend API: Render, Railway, Fly.io, or another Docker host, root/context `backend`
- Database and auth: Supabase

## 1. Supabase

Create a Supabase project and copy:

- Project URL
- Anon public key
- Postgres connection string

Enable Auth providers as needed:

- Google for app login
- Magic link email if you want passwordless email login

Add the production frontend URL to Supabase Auth redirect URLs:

- `https://<your-vercel-domain>/`
- `https://<your-custom-app-domain>/` if used

Run migrations against Supabase Postgres:

```bash
cd backend
WP_FIXPILOT_DATABASE_URL="<supabase-postgres-url>" alembic upgrade head
```

## 2. Backend Host

Deploy `backend/Dockerfile`.

Required environment variables:

```bash
WP_FIXPILOT_ENVIRONMENT=production
WP_FIXPILOT_DATABASE_URL=<supabase-postgres-url>
WP_FIXPILOT_FRONTEND_URL=https://<your-vercel-domain>
WP_FIXPILOT_CORS_ORIGINS=https://<your-vercel-domain>
WP_FIXPILOT_TRUSTED_HOSTS=<your-api-domain>,localhost,127.0.0.1
WP_FIXPILOT_SUPABASE_URL=<supabase-project-url>
WP_FIXPILOT_SUPABASE_ANON_KEY=<supabase-anon-key>
WP_FIXPILOT_SUPABASE_JWT_SECRET=<supabase-jwt-secret>
WP_FIXPILOT_ENCRYPTION_KEY=<fernet-key>
WP_FIXPILOT_GOOGLE_CLIENT_ID=<google-oauth-client-id>
WP_FIXPILOT_GOOGLE_CLIENT_SECRET=<google-oauth-client-secret>
WP_FIXPILOT_GOOGLE_REDIRECT_URI=https://<your-vercel-domain>/auth/google/callback
WP_FIXPILOT_FIRECRAWL_API_KEY=<firecrawl-api-key>
WP_FIXPILOT_FIRECRAWL_WEBHOOK_URL=https://<your-api-domain>/webhooks/firecrawl
WP_FIXPILOT_FIRECRAWL_WEBHOOK_SECRET=<random-secret>
```

Generate a Fernet encryption key locally:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

The container starts with:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## 3. Vercel

Import the GitHub repository into Vercel.

Use these build settings:

- Framework: Vite
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`

Required environment variables:

```bash
VITE_API_BASE_URL=https://<your-api-domain>
VITE_SUPABASE_URL=<supabase-project-url>
VITE_SUPABASE_ANON_KEY=<supabase-anon-key>
VITE_APP_NAME=WP FixPilot
VITE_PRIMARY_COLOR=#173b2d
VITE_ACCENT_COLOR=#d7ff54
```

Do not set `VITE_DEV_ACCESS_TOKEN` in production.

## 4. Google Cloud

Create an OAuth client for the production app.

Authorized JavaScript origins:

- `https://<your-vercel-domain>`
- `https://<your-custom-app-domain>` if used

Authorized redirect URIs:

- Supabase login callback shown in Supabase Auth provider settings
- `https://<your-vercel-domain>/auth/google/callback`

Enable APIs:

- Google Search Console API
- Google Analytics Admin API
- Google Analytics Data API

## 5. WordPress

Install the bridge plugin from:

```text
plugin/wp-fixpilot-bridge
```

Create a bridge secret in WordPress and add the connection in WP FixPilot.

## 6. Live Smoke Test

After deploy:

1. Open the Vercel app URL.
2. Log in through Supabase.
3. Create or select a project.
4. Connect WordPress and verify `/health` on the backend.
5. Start a crawl.
6. Generate recommendations.
7. Edit, approve, publish, and rollback one WordPress change.
8. Connect Search Console, sync, and confirm the Search Console tab shows live API data.
9. Connect GA4, sync, and confirm the GA4 tab shows live API data.
