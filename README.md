# HackFlow

Hackathon and challenge platform built with Django 5.2, PostgreSQL, Tailwind CSS,
django-cotton, and shadcn-django components.

## Quickstart (Docker + PostgreSQL)

```bash
cp .env.example .env
docker compose up --build
```

- App: http://localhost:8000 (change `WEB_HOST_PORT` in `.env` if 8000 is taken)
- Admin: http://localhost:8000/admin/
- Health: http://localhost:8000/health/
- Sign up: http://localhost:8000/accounts/signup/
- Sign in: http://localhost:8000/accounts/login/
- PostgreSQL: `localhost:5433` (`hackflow` / `hackflow` / `hackflow`)

The URLs above assume the default port `8000`; replace it with your
`WEB_HOST_PORT` if you change it.

The database container is published on host port `5433` by default so it does not
clash with a local PostgreSQL on `5432`. Override with `POSTGRES_HOST_PORT` in
`.env`. Inside Compose, the web service always connects to `db:5432`.

Migrations and `collectstatic` run automatically through `docker-entrypoint.sh`.

## Local (no Docker)

Requires Python 3.10+ and PostgreSQL 16+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the local role/database once (the role needs CREATEDB for tests).
createdb -U postgres hackflow 2>/dev/null || true
psql -U postgres -c "CREATE ROLE hackflow LOGIN PASSWORD 'hackflow' CREATEDB;" 2>/dev/null || true
psql -U postgres -c "ALTER DATABASE hackflow OWNER TO hackflow;" 2>/dev/null || true

cp .env.example .env
python manage.py migrate
python manage.py runserver
```

The local `.env.example` points at `127.0.0.1:5432`. To use the Docker database
from the host instead, set `POSTGRES_PORT=5433`.

### Full `DATABASE_URL`

Instead of the split `POSTGRES_*` variables, you can set a single URL (Render does
this automatically):

```bash
export DATABASE_URL=postgresql://hackflow:hackflow@127.0.0.1:5432/hackflow
python manage.py migrate
```

`DB_SSL_REQUIRE=True` adds `sslmode=require`; `DB_CONN_MAX_AGE` and
`DB_CONN_HEALTH_CHECKS` control persistent connections.

## Frontend assets

Templates use the shadcn-django components copied into `templates/cotton/`.
Icons come from [Lucide](https://lucide.dev/) through `cotton-icons`, so they
stay consistent and can be dropped in anywhere Cotton components work:

```html
<c-lucideicon.arrow-right class="size-4" />
```

The custom HackFlow prompt logo and brand social marks remain local SVGs because
Lucide does not ship brand icons.

Tailwind CSS is compiled with the standalone v4 CLI:

```bash
npm install
npm run css:build   # one-off production build
npm run css:watch   # rebuild on template changes
```

The generated `static/css/output.css` is served by Django/WhiteNoise.

## Authentication

Custom `accounts` app built on Django's auth views: email-or-username login,
email verification, password reset/change, account settings and account
deletion.

Signup only offers the non-privileged roles (`student`, `judge`, `mentor`).
The `organizer` and `admin` roles — which can see every draft, review projects
and export all team data — are granted by an administrator through the Django
admin (`Profiles`), and the global role is read-only on the account settings
page.

| Route | Purpose |
| --- | --- |
| `/accounts/signup/` | Register (username, email, password) |
| `/accounts/login/` | Sign in with email **or** username |
| `/accounts/logout/` | POST-only sign out |
| `/accounts/profile/` | Account settings: profile details + verification status |
| `/accounts/password/change/` | Change password while signed in |
| `/accounts/delete/` | Permanently delete the account (password confirmation) |
| `/accounts/verify-email/<uidb64>/<token>/` | Verify an email address |
| `/accounts/verify-email/resend/` | POST-only resend, throttled per account |
| `/accounts/password-reset/` | Request a reset link |
| `/accounts/password-reset/done/` | "Check your inbox" page |
| `/accounts/password-reset/confirm/<uidb64>/<token>/` | Set a new password |
| `/accounts/password-reset/complete/` | Confirmation page |

New signups are signed in immediately and receive a verification email.
Verification is non-blocking: unverified users can use HackFlow and see a
sitewide banner plus their status in the user menu. Changing an email address
resets verification and sends a fresh link. Verification and password-reset
links both expire after 3 days (`PASSWORD_RESET_TIMEOUT`).

Failed sign-ins are throttled per IP + username (`LOGIN_MAX_ATTEMPTS`,
default 5, for `LOGIN_LOCKOUT_SECONDS`, default 900). Verification resends are
throttled per account (`EMAIL_VERIFICATION_RESEND_COOLDOWN`, default 60
seconds). These use Django's cache; the default local-memory cache is
per-process, so configure a shared cache (for example Redis) when running
multiple production workers.

Password-reset and verification emails use the console backend in development,
so links are printed in the `runserver` output. To send real email, set
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and
`DEFAULT_FROM_EMAIL` (SMTP with TLS is the default).

Run the test suite with a PostgreSQL test database:

```bash
python manage.py test
```

## Utility Scripts

Utility scripts for development and testing are located in the `scripts/` directory:

```bash
# Set up test accounts with various roles (refuses to run when DEBUG is off)
TEST_ACCOUNT_PASSWORD='at-least-12-chars' python scripts/setup_test_accounts.py

# Reset the admin password
TEST_ADMIN_PASSWORD='at-least-12-chars' python scripts/reset_admin.py

# List all users (read-only)
python scripts/list_users.py
```

Both password environment variables are required and must be at least 12
characters — the scripts have no default passwords, because they create
privileged accounts.

## Configuration

### Timezone

The default timezone is set to `Africa/Tunis`. To override for multi-region deployments:

```bash
export TIME_ZONE=UTC
```

### CORS Configuration

CORS support is disabled by default. To enable for API endpoints:

1. Uncomment `django-corsheaders` in `requirements.txt`
2. Add `'corsheaders.middleware.CorsMiddleware'` to `MIDDLEWARE` in `HackFlow/settings.py`
3. Uncomment `corsheaders` in `INSTALLED_APPS`
4. Set environment variables:
   ```bash
   CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
   CORS_ALLOW_CREDENTIALS=False
   ```

### AI Features

AI features use Groq API for both sponsors email generation and project analysis. Configure in `.env`:

```bash
GROQ_API_KEY=your_groq_api_key_here
AI_MODEL=openai/gpt-oss-120b
```

The project evaluation endpoints are throttled per user (`AI_RATE_LIMIT_MAX`
requests per `AI_RATE_LIMIT_WINDOW` seconds, default 20 per 60s) because each
call is billed. Set `AI_RATE_LIMIT_MAX=0` to disable the throttle.

Get your API key at: https://console.groq.com/keys

Placeholder values will be rejected and fallback to standard templates.

## Deploy to Render

1. Push the repository to GitHub.
2. Render Dashboard → New → Blueprint → select the repo (`render.yaml` is detected).
3. Approve the resources:
   - `hackflow` web service (Docker, health check at `/health/`)
   - `hackflow-postgres` managed PostgreSQL database
4. Render injects `DATABASE_URL` from the database into the web service.
5. In the Render dashboard, add the SMTP variables (`EMAIL_HOST`,
   `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `DEFAULT_FROM_EMAIL`) so verification and password-reset emails are
   delivered. Without `EMAIL_HOST`, Django prints them to the service logs.
6. Render's external hostname is added to `ALLOWED_HOSTS` automatically. If you
   attach a custom domain, add it to `DJANGO_ALLOWED_HOSTS` (comma-separated).
   Avoid setting `DJANGO_ALLOWED_HOSTS=*` in production.

For an external PostgreSQL (Neon, Supabase, RDS, Aiven), set `DATABASE_URL` to its
connection string instead. Use `DB_SSL_REQUIRE=True` when the provider requires SSL.
