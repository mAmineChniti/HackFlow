# HackFlow

[![codecov](https://codecov.io/gh/mAmineChniti/HackFlow/branch/master/graph/badge.svg)](https://codecov.io/gh/mAmineChniti/HackFlow)

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

The `web` container runs the production Gunicorn command from the `Dockerfile`
(no `runserver`). Code is baked into the image, so rebuild after changes with
`docker compose up -d --build`. Uploaded media is persisted in the `media_data`
volume.

Before exposing the stack publicly, set `DJANGO_DEBUG=False`, a unique
`DJANGO_SECRET_KEY`, and your host in `DJANGO_ALLOWED_HOSTS` /
`DJANGO_CSRF_TRUSTED_ORIGINS`, then terminate TLS in front of the stack.
For that reason the web and PostgreSQL ports are bound to `127.0.0.1`; run
Nginx/Caddy on the host and proxy public traffic to `127.0.0.1:8000`.

The database container is published on host port `5433` by default so it does not
clash with a local PostgreSQL on `5432`. Override with `POSTGRES_HOST_PORT` in
`.env`. Inside Compose, the web service always connects to `db:5432`.

Migrations, `collectstatic` and the demo seeder run automatically through
`docker-entrypoint.sh`. Seeding is enabled by default because this project is a
demo; set `SEED_DEMO_DATA=False` for an empty database (see below).

## Demo data

`seed_demo` creates a complete, idempotent demo site: one account per role, a
small student cohort, five hackathons in different states, registrations with a
waitlist and check-ins, projects in every status/category with teams, mentor
advice and audit history, nine sponsors across every tier/status, and generated
banner/logo images. Running it again refreshes the demo records without creating
duplicates.

`cp .env.example .env` already contains the demo defaults:

```ini
SEED_DEMO_DATA=True
DEMO_ADMIN_PASSWORD=HackFlowAdmin2026!
DEMO_PASSWORD=HackFlowDemo2026!
```

These are public, demo-only values. Both passwords are at least 12 characters.
Replace them with your own values before exposing a deployment that should not
be openly accessible. The web container runs `python manage.py seed_demo` after
migrate/collectstatic; the Celery worker does not seed. The entrypoint also
treats an unset `SEED_DEMO_DATA` as `True`, so production demonstrations seed
unless explicitly disabled. For a manual local run:

```bash
python manage.py seed_demo                 # uses the two env vars above
python manage.py seed_demo --reset-passwords
python manage.py seed_sponsors             # sponsor-only demo/reset command
```

Demo sign-ins:

| Username | Password | Role | Useful for |
| --- | --- | --- | --- |
| `admin` | `HackFlowAdmin2026!` | Administrator / superuser | Django admin, every dashboard, full review/export access |
| `organizer` | `HackFlowDemo2026!` | Organizer (staff) | Hackathon dashboard, project reviews, sponsor pipeline |
| `judge` | `HackFlowDemo2026!` | Judge / jury | Judging and project views |
| `mentor` | `HackFlowDemo2026!` | Mentor | Mentor dashboard and advice |
| `student` | `HackFlowDemo2026!` | Student | Team lead views, registrations and submissions |
| `sarah`, `alex`, `maya`, `nour`, `yassine` | `HackFlowDemo2026!` | Students | Different teams, statuses, waitlist and check-in demos |

On Render, enter `DEMO_ADMIN_PASSWORD` and `DEMO_PASSWORD` as the two secret
environment variables. Use the values above for a quick demo, or replace both
and update the credentials you hand to the jury. The README passwords only apply
when the environment uses those exact values.

Generated files live under `media/` and are gitignored. On Render's ephemeral
filesystem they are recreated by the startup seeder after a restart. Demo
accounts are privileged: rotate the passwords or set `SEED_DEMO_DATA=False`
after a public demo.

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

The Docker entrypoint seeds automatically. Without Docker, load the demo
dataset manually after migrating:

```bash
python manage.py seed_demo
```

It uses the `DEMO_ADMIN_PASSWORD` / `DEMO_PASSWORD` values from `.env`; the
defaults in `.env.example` match the demo credentials above.

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

Password-reset and verification emails use the console backend when `EMAIL_HOST`
is unset, so links are printed in the `runserver` or Render logs. To send real
email, set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
and `DEFAULT_FROM_EMAIL` (SMTP with TLS is selected automatically). Set
`EMAIL_BACKEND` explicitly if you use an API or another backend.

Run the test suite with a PostgreSQL test database:

```bash
python -m pytest --cov --cov-report=term-missing
# or: python manage.py test
```

CI runs the same suite against PostgreSQL and uploads `coverage.xml` to
[Codecov](https://codecov.io/gh/mAmineChniti/HackFlow); no coverage ZIP or
artifact is produced. The upload uses GitHub OIDC (`id-token: write`), so enable
the Codecov GitHub App/OIDC integration for the repository. If your Codecov
organization requires a token instead, add a `CODECOV_TOKEN` secret and switch
`use_oidc` off in `.github/workflows/ci.yml`. Tests do not require Redis: without
`REDIS_URL`, the AI endpoints use the synchronous fallback, and the async tests
mock the Celery enqueue call.

## Management commands

The only project shell script kept is `scripts/start-render.sh`. Data and account
tasks use Django management commands:

```bash
python manage.py seed_demo                 # full demo site (idempotent)
python manage.py seed_demo --reset-passwords
python manage.py seed_sponsors             # sponsor-only demo data
python manage.py ai_benchmark              # AI classifier + rubric metrics
python manage.py ai_benchmark --json       # machine-readable metrics
python manage.py ai_benchmark --remote     # benchmark the configured Groq model
python manage.py changepassword <username>
python manage.py migrate
python manage.py collectstatic --noinput
```

The command itself has no hardcoded fallback passwords: values come from
`DEMO_ADMIN_PASSWORD` / `DEMO_PASSWORD` (or `--admin-password` / `--password`).
The public demo values above live in `.env.example`; replace them for a
non-demo deployment.

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

### Sponsor permissions

`SPONSORS_USE_PROFILE_ROLE=True` maps `accounts.Profile.role` to the sponsor
permission set (organizer/admin can manage the pipeline, students/judges cannot).
Docker Compose and `render.yaml` enable it for the demo; set it yourself for a
bare-metal run. `SPONSORS_USE_GROUP_ROLES` stays `False` unless you deliberately
want Django-group-based sponsor permissions.

### Environment inventory

Every variable read by the project is documented in `.env.example`. Runtime-only
variables such as `PORT`, `GUNICORN_*`, `RUN_MIGRATIONS`, `RUN_COLLECTSTATIC`,
and `RENDER_EXTERNAL_*` are listed there as deployment-only and normally come
from Compose/Render rather than a committed `.env`.

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

### AI evaluation metrics (rubric 5.2)

Sign in as `organizer` or `admin` and open `/projects/ai/metrics/`, or run the
terminal report:

```bash
python manage.py ai_benchmark
python manage.py ai_benchmark --json
```

The page and command present evidence for both metric sub-criteria:

- **Classification (precision / recall / F1):** the category detector is
  evaluated on a 25-example, hand-labelled validation set covering all seven
  categories. The current local run reports **96.0% accuracy** and **0.964 macro
  F1**, with per-class precision/recall/F1, confidence distribution and a full
  confusion matrix. The known ambiguous `EcoShop` example is shown as the single
  error instead of hiding it.
- **Generative review (qualitative rubric):** project scoring has no single
  numeric ground truth, so the page justifies quality against relevance,
  groundedness, actionability and consistency. Automated structural checks
  report schema completeness, valid score range, determinism and the average
  score, plus a representative review with strengths and improvement areas.
- **Performance:** every real AI call is timed in the Django cache. The page
  shows p50/p95 latency by operation, success rate, call source and recent call
  history. The local fallback benchmark is reproducible without a Groq key.
- **Asynchronism:** with `REDIS_URL` and `AI_ASYNC_ENABLED=True`, the project
  evaluation endpoint returns **HTTP 202** with a task id, a Celery worker makes
  the long Groq call and the browser polls the status endpoint. Without a
  broker, the same endpoint falls back to a synchronous response, and the page
  shows which mode is active.

The dashboard runs the free, deterministic local fallback by default so it works
without a key and the same numbers can be reproduced. To evaluate the actual
Groq model on the same labelled set (network calls may incur cost or rate
limits):

```bash
python manage.py ai_benchmark --remote
```

For the live demo: sign in as organizer, open a project, click **Evaluate with
AI**, then refresh the metrics page. If `GROQ_API_KEY` is unset, the UI and
metrics still work through the local fallback; the page labels the source so
the jury can distinguish remote from fallback runs. The metrics buffer keeps
only operation/source/mode/duration metadata for the latest 200 calls; it never
stores prompts, project descriptions, API keys or user data.

Get your API key at: https://console.groq.com/keys

Placeholder values will be rejected and fallback to standard templates.

## Deploy to Render

1. Push the repository to GitHub.
2. Render Dashboard → New → Blueprint → select the repo (`render.yaml` is detected).
3. Approve the resources:
   - `hackflow` web service (Docker, free plan, health check at `/health/`)
   - `hackflow-postgres` managed PostgreSQL database (free plan)
   - `hackflow-redis` Render Key Value instance (free plan; cache + Celery broker)
4. Render generates `DJANGO_SECRET_KEY` and injects `DATABASE_URL`, `REDIS_URL`,
   `RENDER_EXTERNAL_HOSTNAME`, and `RENDER_EXTERNAL_URL`.
5. Enter the three prompted secrets:
   - `GROQ_API_KEY` — AI email generation and project analysis.
   - `DEMO_ADMIN_PASSWORD` — use `HackFlowAdmin2026!` to match the documented
     demo credentials, or a new 12+ character value.
   - `DEMO_PASSWORD` — use `HackFlowDemo2026!` to match the documented demo
     credentials, or a new 12+ character value.
6. The Blueprint already sets `SEED_DEMO_DATA=True`,
   `SPONSORS_USE_PROFILE_ROLE=True`, `SERVE_MEDIA=True`, `DJANGO_DEBUG=False`,
   the security/HSTS flags, Celery settings, and the free-plan Gunicorn sizing.
   You do not need to enter those manually.
7. For email on a paid service, add the SMTP variables (`EMAIL_HOST`,
   `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `EMAIL_USE_TLS` / `EMAIL_USE_SSL`, and `DEFAULT_FROM_EMAIL`). Set
   `EMAIL_BACKEND` only if you use an API or another backend. Free web services
   block outbound SMTP ports (25/465/587), so leave `EMAIL_HOST` unset for the
   free demo: Django prints verification and password-reset emails to the
   service logs.
8. Render's external hostname is added to `ALLOWED_HOSTS` and
   `CSRF_TRUSTED_ORIGINS` automatically. If you attach a custom domain, add it
   to both `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`
   (comma-separated). Avoid setting `DJANGO_ALLOWED_HOSTS=*` in production.

Required manual values: `GROQ_API_KEY`, `DEMO_ADMIN_PASSWORD`, `DEMO_PASSWORD`.
Blueprint-managed values: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`,
`REDIS_URL`, `SEED_DEMO_DATA`, `SPONSORS_USE_PROFILE_ROLE`, `SERVE_MEDIA`, the
Celery/Gunicorn settings, and the security flags. Optional values: SMTP,
custom-domain hosts/CSRF origins, AI model/rate limits, and Celery timeouts.
Every variable read by the project is documented in `.env.example`.

The web service runs `python manage.py migrate`, `collectstatic`, and (when
`SEED_DEMO_DATA=True`) `python manage.py seed_demo` via `docker-entrypoint.sh`,
then `scripts/start-render.sh` starts Gunicorn and a Celery worker in the same
container.

Render does **not** offer free background workers. To keep the Blueprint at
$0, the Celery worker is co-located with Gunicorn on the free web instance
(1 Gunicorn worker + 1 solo Celery worker, sized for 512 MB). The async AI
flow is still real: `POST /projects/<slug>/ai-analyze/` returns `202` with a
status URL, the worker runs the Groq call, and the browser polls the status
endpoint. Trade-offs: the worker stops when the free service spins down after
15 minutes without traffic (the next request starts both again), and the free
Key Value instance is in-memory, so queued tasks/cache are lost if it restarts.
On a paid plan, move Celery to a dedicated `type: worker` service and remove the
worker startup from `scripts/start-render.sh`.

Free web services also have an ephemeral filesystem: uploaded sponsor logos are
lost on redeploy, restart, or spin-down. The `media_data` volume only applies to
`docker-compose.yml`; Render ignores Compose. Render sets `SERVE_MEDIA=True` so
Django serves `/media/` while the instance is alive, but files still disappear
on restart. With `SEED_DEMO_DATA=True`, startup regenerates the demo banners and
logos automatically. Use external object storage (R2, S3, Supabase Storage) for
durable user uploads.

Render's free PostgreSQL instance expires 30 days after creation. If the
grading/demo happens later, upgrade the database plan or point `DATABASE_URL`
at an external managed PostgreSQL before the defense. Free web services also
spin down after inactivity, so expect a cold start on the first request.

For an external PostgreSQL (Neon, Supabase, RDS, Aiven), set `DATABASE_URL` to its
connection string instead. Use `DB_SSL_REQUIRE=True` when the provider requires SSL.
