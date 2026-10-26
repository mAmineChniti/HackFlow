# HackFlow — Open Audit Questions

These questions cannot be resolved from the code alone. Each requires a product-owner or
architect decision because the answer materially affects the recommended implementation.

---

## Q-001 — Judge scoring model

**Question:** Should judges score projects independently (per-criterion rubric, per-judge), or
should they simply confirm / adjust the single organizer score that already exists on
`projects.Project.score`?

**Why it matters:** The current data model has one `score` integer (1–10) set by organizers. Any
judge evaluation feature must decide between:
- Adding a `JudgeEvaluation` model (FK to Project + Judge + Hackathon, per-criterion scores),
  which enables conflict-of-interest detection and transparent score breakdowns.
- Reusing the existing `score` field, which means judges overwrite or average with organizer input.

**Affects:** BIZ-001 remediation, `projects/models.py`, `projects/services.py`, `projects/views.py`.

---

## Q-002 — Solo project submissions

**Question:** Must a participant be part of a team before they can create or submit a project, or
are solo submissions allowed?

**Why it matters:** Currently a student can create a project with no team at all. If solo
submissions are intentional, the `Project → Team` FK (BIZ-004) must be optional. If a team is
always required, the project creation view needs an eligibility check against
`TeamMember.objects.filter(user=request.user, team__hackathon=...)`.

**Affects:** BIZ-004 remediation, `projects/views.py:project_create`.

---

## Q-003 — Mandatory Project → Hackathon link

**Question:** Should every project be required to reference a specific `Hackathon` record, or
should standalone / cross-event projects be allowed?

**Why it matters:** `Project.hackathon` is currently a free-text `CharField` (default
`"HackFlow 2026"`). Migrating it to a FK is the foundation for scoped dashboards, deadline
inheritance, and judge/mentor scoping. If the FK is made non-nullable, all existing demo data
must be migrated, and the project creation form must require a hackathon selection.

**Affects:** BIZ-003, BIZ-004, BIZ-008 remediation.

---

## Q-004 — Organizer scope on the project dashboard

**Question:** Should an organizer see only projects linked to their own hackathons, or should
all organizers see all projects across the platform?

**Why it matters:** The current `project_admin_dashboard` shows every project to every organizer.
If scope should be limited (organizer A should not see organizer B's projects), this requires the
`Project → Hackathon FK` (Q-003) plus a queryset filter in `projects/views.py`.

**Affects:** `projects/views.py:project_admin_dashboard`, BIZ-003.

---

## Q-005 — Waitlist auto-promotion: silent or notified?

**Question:** When a confirmed participant unregisters and the first waitlisted participant is
automatically promoted to confirmed, should:
(a) an email be sent automatically (current email function exists but is commented out), or
(b) the organizer must manually approve the promotion before the email is sent?

**Why it matters:** Option (a) is already partially implemented (`send_waitlist_promoted_email`
in `hackathons/emails.py` and the promotion logic in `unregister_participant`). Option (b) would
require a manual organizer action and a new approval interface.

**Affects:** BIZ-005 / FLOW-003 remediation, `hackathons/views.py:unregister_participant`.

---

## Q-006 — Relationship between teams.Team and projects.ProjectMember

**Question:** Are `teams.Team` (hackathon-level) and `projects.ProjectMember` (project-level)
meant to be two phases of the same team, or entirely independent structures?

**Proposed interpretations:**
- **Phase model:** `teams.Team` is used during the formation/registration phase; at submission
  time, the team is "promoted" to a `Project` and `TeamMember` records become `ProjectMember`
  records automatically.
- **Independent model:** A hackathon team and a project team are separate concepts; a project
  can have a different membership than the registered team (e.g., partial team submits a
  project, or a solo participant joins someone else's project).

**Why it matters:** Determines whether to unify the two models, add a FK from Project to Team,
or leave them independent.

**Affects:** BIZ-004, ARCH-002 remediation.

---

## Q-007 — Permanent French sponsor pipeline values

**Question:** Are the French status values in the sponsor pipeline (`confirmé`, `négociation`,
`contacté`, `refusé`, `financier`, `matériel`, `prix`, `mentors`) intended to be permanent
database codes, or is there a planned migration to English values?

**Why it matters:** `AGENTS.md` explicitly requires keeping these French codes as stored values
and only translating the displayed label. If this is a long-term requirement, it should be
documented as a conscious architectural decision (e.g., a comment in `sponsors/models.py`).
If an eventual migration to English codes is planned, the approach changes.

**Affects:** `sponsors/models.py`, `sponsors/migrations/`, all template comparisons.

---

## Q-008 — participant_badge access for non-registered users

**Question:** Should the `/hackathons/<slug>/badge/` endpoint be:
(a) accessible only to registered participants (return 404 or redirect for others), or
(b) accessible to organizers as a preview/admin tool (current behavior but with fabricated data)?

**Why it matters:** The current fallback in `participant_badge` constructs a fake
`HackathonRegistration` object in memory with `university="ESPRIT"` — this creates a badge
showing false information. TECH-012 proposes returning a 404 for non-registered users, but
if organizers need a badge preview tool, it should be implemented explicitly rather than
using fabricated data.

**Affects:** TECH-012 remediation, `hackathons/views.py:participant_badge`.

---

## Q-009 — SEED_DEMO_DATA default in production

**Question:** Is it intentional that `SEED_DEMO_DATA` defaults to `True` when the environment
variable is unset (including in Docker deployments that do not set it explicitly)?

**Why it matters:** A fresh deployment without explicit `SEED_DEMO_DATA=False` will seed demo
accounts with the publicly documented password `hackflow2026`. This is stated in the README
as intentional for the demo, but poses a security risk if the variable is accidentally omitted
in a production deployment.

**Affects:** `docker-entrypoint.sh`, `README.md`, deployment security posture.

---

## Q-010 — Check-in authorization: judges only or also mentors?

**Question:** Should assigned mentors be able to scan QR codes and check in participants at
the venue, or should check-in be restricted to organizers and judges only?

**Why it matters:** The view docstring for `organizer_checkin` says "Accessible to organizers,
judges, mentors, and staff" but the `is_authorized` condition only grants access to the
organizer, staff, superuser, and judges — mentors are excluded. Either the docstring or the
code is wrong.

**Affects:** BIZ-009 remediation, `hackathons/views.py:organizer_checkin` and `toggle_checkin`.
