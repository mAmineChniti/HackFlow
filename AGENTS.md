# HackFlow agent playbook

Project-specific working agreement for coding agents. Read this before making
changes. It exists so audits stay fast, consistent, and easy to review.

## 1. Project shape

HackFlow is a Django 5.2 hackathon and challenge platform.

- `HackFlow/` — settings, root URLs, WSGI/ASGI, Celery app.
- `accounts/` — custom user profiles, roles, signup, verification, password flows.
- `core/` — landing page, shared Groq client, shared fields and filters.
- `hackathons/` — events, registrations, AI content generation, certificates.
- `projects/` — teams, submissions, reviews, history, AI evaluation, exports.
- `sponsors/` — sponsor pipeline, sponsorships, recommendations, email tooling.
- `templates/` — all Django templates; Cotton components live in `templates/cotton/`.
- `assets/css/input.css` — Tailwind source.
- `static/css/output.css` — committed compiled CSS; rebuild it after class changes.
- `projects/services.py` and `sponsors/services.py` — business rules, permissions,
  and state transitions. Do not duplicate that logic in views or admin classes.

Use `.venv/bin/python` for Django commands. The repository `.env` is authoritative
for local settings unless a command explicitly overrides an environment variable.

## 2. Non-negotiable product rules

### Language

- All user-facing text must be English: templates, JavaScript strings, form
  labels/help text/placeholders, validation and flash messages, admin actions,
  exports, emails, and AI prompts/fallbacks.
- Persisted database values are data, not UI. Never translate or rename them just
  to improve English copy. Examples that must stay unchanged:
  - Sponsor pipeline: `confirmé`, `négociation`, `contacté`, `refusé`
  - Sponsor contribution: `financier`, `matériel`, `prix`, `mentors`
  - Sponsor sector codes: `sante`, `education`, `energie`, etc.
  - Project history: `soumis_a_nouveau`, `en_evaluation`, `accepte`, `refuse`,
    `finaliste`, `laureat`
  - Project member roles: `chef_de_projet`, `developpeur`, `designer`
- Translate the displayed label instead, through `get_*_display` or an explicit
  template mapping. Keep existing saved values and comparisons working.
- New UI dates should be English-formatted. Do not rewrite stored timestamps.
- French comments and docstrings may remain. Do not create a noisy translation-only
  diff for non-user-facing comments.

### Home page

The landing page must stay backed by real records wherever a model exists:

- Hackathon hero/catalogue: `hackathons.Hackathon`
- Registration state/counts: `hackathons.HackathonRegistration`
- Leaderboard/recent submissions: `projects.Project`
- Sponsor strip and platform counters: real querysets/DB values
- Hero and final CTAs: current featured event or hackathon catalogue

Event cards should expose real status, dates, registration deadline/state,
location/mode, prize, capacity, and confirmed-registration counts. Do not
re-introduce literal demo event, project, sponsor, or counter lists.

Challenges, testimonials, and the FAQ currently have no backing models. Their
sections remain placeholders. Do not describe them as live data or add new fake
records; replace them only when real models exist.

### AI

- Every external AI call goes through `core.groq.call_groq` and `core.groq`'s
  key/model/timeout handling. Do not add Anthropic, Gemini, OpenAI, or other
  provider clients.
- Keep graceful local fallbacks when Groq is not configured, rate-limited, or
  returns unusable JSON.
- Keep the Celery/Redis async path intact. Without a broker, the synchronous
  eager fallback must still work. Do not make AI endpoints block in production.
- Sponsor recommendations are local TF-IDF/cosine similarity and must not make a
  network call.

### Security and correctness

- Enforce permissions server-side; `projects/services.py` and
  `sponsors/services.py` are the source of truth for role and state rules.
- State changes must go through the service layer so history/audit rows stay
  complete. In particular, do not force project status changes directly from
  views or admin.
- Keep CSRF tokens on every POST form. Logout stays POST-only.
- Do not add `|safe` around user content or inject server data with `innerHTML`.
- Preserve confirmation prompts for destructive actions and accessible labels
  for icon-only controls.
- Never commit secrets, `.env`, real API keys, or production credentials.

## 3. Templates, Cotton, and frontend

- Keep templates under the root `templates/` directory. Prefer existing Cotton
  components and extend them rather than duplicating markup.
- Use `c-native_select` for real `<select>` / `<option>` controls. `c-select` is
  an Alpine-only component and does not accept native options correctly.
- Preserve all behavior-bearing attributes when converting HTML to Cotton:
  `name`, `id`, `for`, `value`, `type`, `method`, `action`, `hx-*`, `x-*`,
  `@click`, `data-*`, `onclick`, `role`, `aria-*`, `alt`, `title`, and `required`.
- Keep `{% csrf_token %}` and HTMX target/swap/trigger attributes exactly as
  intended. Run a smoke render after large template conversions.
- Use `c-lucideicon.*` for icons. Do not overwrite icon SVG content with
  `textContent` or `innerHTML`; update the surrounding UI through Alpine or
  normal DOM elements instead.
- Tables should use the existing Cotton table parts consistently, including
  header, row, head, cell, and empty-state components.
- Accessibility matters: one `h1` per page, meaningful heading order, labelled
  inputs, non-empty link text, `alt` text, focusable controls, and no empty links.
- Rebuild Tailwind after adding/changing classes:

```bash
npm run css:build
```

Commit the resulting `static/css/output.css`.

## 4. Python, models, and migrations

- Keep model `verbose_name`/`help_text`/choice labels English while preserving
  choice values and stored database codes.
- Generate migrations for model metadata/choice-label changes:

```bash
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py makemigrations --check --dry-run
```

- Commit generated migrations. Do not hand-edit old applied migrations.
- Do not run migrations against the maintainer's real database. For smoke tests,
  use an isolated SQLite database under `/tmp/opencode/`.
- Keep new Python code compatible with Python 3.10 and the configured 100-column
  Ruff line length.

## 5. Verification workflow

Before changing anything:

```bash
git status --short
git diff
```

Identify unrelated user/infrastructure work and leave it out of the audit diff.
Do not stage with `git add -A`; stage explicit paths.

Static checks (run these for every audit):

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
ruff check .
```

`ruff check .` is the CI gate. Format only Python files touched by the change:

```bash
ruff format path/to/changed_file.py
```

Do not run `ruff format` over the whole repository. The tree intentionally has
pre-existing unformatted files and the project does not enforce repo-wide
formatting yet. `.venv/bin/ruff` may not exist; use the global `ruff`.

Template smoke check:

```bash
.venv/bin/python manage.py shell -c "
from django.template.loader import get_template
paths = ['core/home.html', 'hackathons/detail.html', 'projects/project_detail.html']
for path in paths:
    get_template(path)
print('templates ok')
"
```

Rendered-page smoke check against throwaway SQLite:

```bash
mkdir -p /tmp/opencode
rm -f /tmp/opencode/hackflow-smoke.sqlite3
DATABASE_URL=sqlite:////tmp/opencode/hackflow-smoke.sqlite3 \
  .venv/bin/python manage.py migrate --noinput
DATABASE_URL=sqlite:////tmp/opencode/hackflow-smoke.sqlite3 \
  .venv/bin/python manage.py shell -c "
from django.test import Client
response = Client().get('/', HTTP_HOST='localhost')
print(response.status_code, len(response.content))
"
```

Pass `HTTP_HOST='localhost'` when using the Django test client: local
`ALLOWED_HOSTS` does not include `testserver`.

Unit tests: **do not run the full test suite unless the maintainer explicitly
asks.** The maintainer runs tests themselves. When tests are requested, use the
PostgreSQL configuration from `README.md`/CI; do not use Redis for the sync
fallback tests.

## 6. Audit checklist

1. Check working tree and separate unrelated changes.
2. Search for remaining user-facing French in templates and Python strings.
3. Check that persisted status/role/history values were not renamed.
4. Check dynamic home data and registration-aware event rendering.
5. Check Cotton conversions for lost `name`, `id`, `hx-*`, `x-*`, `onclick`,
   `aria-*`, `alt`, CSRF, and form semantics.
6. Check AI imports/calls and fallbacks; ensure only `core.groq` is used.
7. Check permission and state-transition paths still use the service layer.
8. Run Django checks, migration check, Ruff, template/render smoke tests.
9. Rebuild Tailwind and inspect the CSS diff.
10. Review `git diff --check` and `git diff --cached --stat`.
11. Stage only audit files, commit with a clear message, and push the feature
    branch when the task asks for completion.

Useful searches:

```bash
rg -n '[À-ÿŒœ]' templates
rg -n 'Gemini|gemini|Anthropic|anthropic|google\.generativeai|from openai|import openai' --glob '!node_modules/**' --glob '!AGENTS.md' .
rg -n 'DEMO_|demo_|Placeholder|placeholder' core templates/core
rg -n 'c-select|c-native_select' templates
rg -n 'textContent|innerHTML' templates
```

## 7. Known traps

- Groq model IDs may look like `openai/gpt-oss-120b`; that is the Groq-hosted
  model name, not an OpenAI API integration.
- Sponsor status/contribution values are French strings by design. New English
  labels do not change query filters or URL parameters.
- Project history `action` values are French codes; templates must compare the
  stored code, not the English label.
- `HackathonRegistration.Status` uses English values (`confirmed`, `waitlist`,
  `cancelled`); do not confuse these with sponsor pipeline values.
- Event registration counts on the home page should use confirmed registrations,
  not all registrations.
- Draft projects must not appear in public project counters, leaderboards, or
  recent-submission lists.
- `HackFlow/settings.py`, `.env.example`, deployment files, and `README.md` may
  contain unrelated in-progress infrastructure edits. Leave them uncommitted
  unless they are explicitly in scope.
- The local `.env` may point at PostgreSQL and may have a restricted
  `DJANGO_ALLOWED_HOSTS`; use a throwaway `DATABASE_URL` and `HTTP_HOST` for smoke
  renders.
- `GROQ_API_KEY` may be absent or invalid locally. AI pages must still render via
  local fallbacks, and a failed remote call must not break the response.
