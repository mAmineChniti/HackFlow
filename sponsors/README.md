# Sponsors module

The `sponsors` Django app stores sponsor records and their partnerships with
hackathons. It includes public sponsor pages and staff-facing management
features.

## Features

- A public page lists partnerships whose status is confirmed.
- Staff users can manage sponsors and partnerships, filter the directory, and
  change partnership statuses through a dropdown with HTMX.
- Partnership statuses are Prospect, Contacted, Negotiation, Confirmed, and
  Rejected. Changes made through the status-change service are recorded in
  `StatusHistory`.
- Sponsor contact emails can be composed from built-in templates and sent
  through Django's configured email backend. Send results are stored in
  `SponsorEmailLog`.
- Sponsor recommendations use TF-IDF text features and cosine similarity from
  scikit-learn. The implementation excludes sponsors already linked to the
  selected hackathon and adds a score bonus for sponsors confirmed at another
  hackathon.
- Staff users can request an AI-assisted email draft through the Groq API
  when configured. The email generator uses a built-in template when no API
  key is configured or a request fails.
- Partnership data can be exported as an Excel workbook. The export rejects
  requests exceeding 5,000 rows.

## Data models

- `Sponsor`: name, logo, website, sector, description, and contact details.
- `Sponsorship`: a sponsor/hackathon relationship with tier, contribution
  type, amount, status, and notes. A sponsor can have at most one relationship
  with a given hackathon.
- `StatusHistory`: status transitions associated with a partnership. The
  Django admin disables adding, editing, and deleting these entries there.
- `SponsorEmailLog`: email content, sender, timestamp, and send result.

The public view selects confirmed partnerships; protected views use the
sponsors permission mixin. These application behaviors are not a legal or
regulatory compliance certification.

## Routes

All routes use the `/sponsors/` prefix:

| Route | Purpose |
|---|---|
| `/` | Public confirmed-sponsor page |
| `/dashboard/` | Staff dashboard |
| `/directory/` | Staff sponsor directory |
| `/new/` | Create a sponsor |
| `/<id>/` | Sponsor details |
| `/<id>/edit/` | Edit a sponsor |
| `/<id>/delete/` | Delete a sponsor |
| `/<id>/contact/` | Compose and send a sponsor email |
| `/<id>/ai-generate/` | Generate an email draft |
| `/recommendations/<hackathon_id>/` | Sponsor recommendations |
| `/sponsorships/new/` | Create a partnership |
| `/sponsorships/<id>/edit/` | Edit a partnership |
| `/sponsorships/<id>/delete/` | Delete a partnership |
| `/sponsorships/<id>/change-status/` | Change a status |
| `/export/excel/` | Export filtered partnership data |

Management routes require the permission assigned to the user's sponsor role.
The public sponsor page is accessible without login.

## Configuration

Set these optional variables in the project `.env` file:

```ini
GROQ_API_KEY=
AI_MODEL=openai/gpt-oss-120b
```

The shared Groq client and default model live in `core/groq.py`. Email delivery
uses Django's configured email backend; see the root `.env.example` for the
project's SMTP settings.

## Demo data

For the complete site demo (roles, hackathons, projects, sponsors, generated
media), use the project-wide idempotent seeder:

```bash
python manage.py seed_demo
```

`seed_demo` is also what the web container runs at startup when
`SEED_DEMO_DATA=True`. The sponsor-only command below remains useful for module
tests and isolated sponsor demos:

```bash
python manage.py seed_sponsors
```

The command creates a demo hackathon and five fictional sponsors. Every demo
sponsor name ends in `(demo)`, and the websites and email addresses use the
reserved `.example` domain. The command updates only records with those demo
names; existing sponsors without the suffix are not matched or modified.

To remove eligible tagged demo records before creating them again:

```bash
python manage.py seed_sponsors --reset
```

The reset only targets sponsors with the `(demo)` suffix and the specifically
named demo hackathon. It removes their matching demo partnerships and associated
status history. A tagged sponsor is kept if it still has other partnerships or
email logs, and a demo hackathon is kept if it still has partnerships. This
avoids deleting records referenced by non-demo activity. The command runs only
when `DEBUG=True`, unless `--force` is passed.

## Tests

Run the sponsor app tests with:

```bash
python manage.py test sponsors -v 2
```

## Connecting the future role system

1. Add or enable the role-source integration in `get_user_roles()` in `sponsors/permissions.py`.
2. The role-to-permission map is `ROLE_PERMISSIONS` in the same file.
3. Override the map through Django's `SPONSORS_ROLE_PERMISSIONS` setting when needed.
4. Filter sponsorships for organizer ownership in `sponsorships_visible_to()`.
5. Apply per-object ownership rules in `can_manage_sponsorship()`.
