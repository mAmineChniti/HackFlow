# HackFlow Demo Quick Start

## One-Command Demo Setup

```bash
cp .env.example .env
docker compose up --build
```

Then visit: http://localhost:8000

## Demo Login Credentials

**Password for ALL users:** `hackflow2026`

### Main Accounts
- **admin** - Full system access, Django admin, all dashboards
- **organizer** - Manage hackathons, review projects, sponsor pipeline  
- **judge** - View and judge accepted projects
- **mentor** - Provide advice and guidance to teams
- **student** - Team leader, submit projects, register for events

### Student Cohort
- **sarah** - Frontend developer, member of multiple teams
- **alex** - UI/UX Designer  
- **maya** - Data scientist, leads Green Innovators team
- **nour** - Backend developer
- **yassine** - Frontend developer, has pending invitation

## What's in the Demo?

### 5 Hackathons
- **HackFlow Challenge 2026** (active, registration open)
- **Smart Campus Sprint 2026** (ongoing, in progress)
- **ESPRIT AI Hackathon 2025** (completed, with winners)
- **CyberShield CTF 2027** (draft, not published)
- **HealthTech Sprint 2026** (cancelled)

### 8 Projects
- Various statuses: draft, submitted, under review, accepted, rejected, finalist, winner
- All categories covered: Web, Mobile, AI, IoT, Cyber, Green, Other
- Complete team assignments and audit history

### 9 Sponsors
- Full pipeline: prospect → contacted → negotiation → confirmed → refused
- Different tiers: Platinum, Gold, Silver, Bronze
- Email logs and status history

### 4 Teams
- **Code Crusaders** - Full team building campus navigation
- **Green Innovators** - IoT team with pending invitation
- **AI Pioneers** - Previous winners
- **Data Dynamos** - Small team looking for members

### 20+ Registrations
- Confirmed participants
- Waitlisted participants  
- Checked-in attendees

## Key URLs

- **Home:** http://localhost:8000/
- **Django Admin:** http://localhost:8000/admin/
- **Hackathons:** http://localhost:8000/hackathons/
- **Projects:** http://localhost:8000/projects/
- **Sponsors:** http://localhost:8000/sponsors/
- **Teams:** http://localhost:8000/teams/
- **User Profile:** http://localhost:8000/accounts/profile/

## Management Commands

```bash
# Seed/refresh all demo data
python manage.py seed_demo

# Reset passwords for existing demo users
python manage.py seed_demo --reset-passwords

# Skip regenerating images
python manage.py seed_demo --skip-media

# Run migrations
python manage.py migrate

# Create superuser (if needed)
python manage.py createsuperuser

# Run tests
python -m pytest --cov
```

## Testing Workflows

### As Organizer
1. Login as `organizer`
2. View hackathon dashboard
3. Review submitted projects
4. Accept/reject projects
5. Manage sponsor pipeline

### As Student  
1. Login as `student`
2. Register for active hackathon
3. View/edit draft project
4. Submit project for review
5. Check team memberships

### As Team Lead
1. Login as `maya` 
2. View "Green Innovators" team
3. Manage team members
4. Check pending invitations
5. View skill matching suggestions

### As Judge
1. Login as `judge`
2. View only accepted projects
3. Review project details
4. See audit trails

## Notes

- All demo data is idempotent - running seed_demo again refreshes data
- Generated images are created automatically (banners, logos)
- Docker Compose runs seeding automatically on startup when SEED_DEMO_DATA=True
- Database: PostgreSQL on port 5433 (to avoid conflict with local postgres)
- Passwords are hardcoded for simplicity - suitable for demos only

## Troubleshooting

**Port 8000 already in use?**
Change WEB_HOST_PORT in .env

**Database connection issues?**
Check PostgreSQL is running: `docker compose ps`

**Need fresh database?**
```bash
docker compose down -v
docker compose up --build
```

**Want empty database?**
Set SEED_DEMO_DATA=False in .env
