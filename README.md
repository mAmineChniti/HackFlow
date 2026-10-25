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

The generated `static/css/output.css` is served by Django/WhiteNoise and is
committed to the repository, so CI and the Docker/Render deployment do not need
Node. Rebuild it (`npm run css:build`) and commit the result whenever you add or
change Tailwind classes in templates or Python view strings.

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
python -m pytest --cov --cov-report=term-missing
# or: python manage.py test
```

CI runs the same suite against PostgreSQL and uploads `coverage.xml` as an
artifact. Tests do not require Redis: without `REDIS_URL`, the AI endpoints use
the synchronous fallback, and the async tests mock the Celery enqueue call.

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

Every external AI call goes through the single client in `core/groq.py`, so
there is only one provider, key, model and timeout policy to maintain. The
sponsor recommender is local TF-IDF/cosine similarity (scikit-learn) and makes
no network call.

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
   - `hackflow-worker` Celery worker (smallest paid compute plan)
   - `hackflow-postgres` managed PostgreSQL database
   - `hackflow-redis` Render Key Value instance (cache + Celery broker)
4. Render injects `DATABASE_URL` and `REDIS_URL` into both the web service and
   the worker.
5. Set `GROQ_API_KEY` once on the web service when prompted; the worker reads
   the same value through `fromService`.
6. In the Render dashboard, add the SMTP variables (`EMAIL_HOST`,
   `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `DEFAULT_FROM_EMAIL`) so verification and password-reset emails are
   delivered. Without `EMAIL_HOST`, Django prints them to the service logs.
7. Render's external hostname is added to `ALLOWED_HOSTS` automatically. If you
   attach a custom domain, add it to `DJANGO_ALLOWED_HOSTS` (comma-separated).
   Avoid setting `DJANGO_ALLOWED_HOSTS=*` in production.

The web service runs `python manage.py migrate` and `collectstatic` once via
`docker-entrypoint.sh`; the worker sets `RUN_MIGRATIONS=0` and
`RUN_COLLECTSTATIC=0` to avoid racing the web container.

Render Key Value is free, but Render does **not** offer free background
workers. The Blueprint therefore uses the smallest paid compute plan for
`hackflow-worker` so Celery/Redis async AI is actually deployed (the BNF
“Performance & asynchronisme” requirement). For a zero-cost demo, remove the
worker service, set `AI_ASYNC_ENABLED=False` on the web service, and AI calls
will run synchronously; the same Redis + worker stack also runs locally or on
a VPS with `docker compose up --build`.

Free web services also have an ephemeral filesystem: uploaded sponsor logos are
lost on redeploy. Use external object storage (or a paid persistent disk) if you
need durable media.

Render's free PostgreSQL instance expires 30 days after creation. If the
grading/demo happens later, upgrade the database plan or point `DATABASE_URL`
at an external managed PostgreSQL before the defense. Free web services also
spin down after inactivity, so expect a cold start on the first request.

For an external PostgreSQL (Neon, Supabase, RDS, Aiven), set `DATABASE_URL` to its
connection string instead. Use `DB_SSL_REQUIRE=True` when the provider requires SSL.
