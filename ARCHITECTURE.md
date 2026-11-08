# SOM Student and Club Platform

## Current Architecture

- `main.html`: browser UI served by the Python application.
- `server.py`: local HTTP and JSON API; SQLite connections and existing member/report handlers.
- `schema.sql`: normalized target data model, role-permission catalog, constraints, indexes, and append-only audit table triggers.
- SQLite file and uploaded files live outside the web root under `%LOCALAPPDATA%\\YoshlarKengashi`.
- The current service binds to `127.0.0.1`. It is a local development baseline, not an internet-ready deployment.

## Roles and Authorization

Guests are anonymous and can only call explicitly public read endpoints. They do not receive a database role.

| Role | Allowed capabilities |
| --- | --- |
| Verified SOM student | Apply to clubs, submit a candidacy, cast one ballot in an open election, and manage own profile/preferences |
| Club coordinator | Manage plans, calendar events, tasks, and reports only for clubs where an active coordinator membership exists |
| Dean | Review student verification, submitted plans/reports, and election candidates; record decisions and feedback |
| Admin | Manage users, role assignments, clubs, settings, and system operations |

A role is not sufficient for club-scoped access: every coordinator request must also verify active membership in the requested club. The `role_permissions` table is the permission catalog; request handlers must enforce it server-side. Hiding a button in the browser is not authorization.

## Core Workflows

### Student verification

1. A user registers with account credentials, student number, faculty/group, and a required verification photo.
2. The account remains `pending_verification`; the photo is stored outside the public uploads directory.
3. A dean reviews the submission and records an approval/rejection plus a note.
4. Approval changes the account to `verified` and grants the `student` role. Rejection does not grant student permissions.
5. Verification images are never available from public gallery URLs. Retention and deletion periods must follow SOM policy; no retention period is assumed here.

The photo is evidence for manual dean review. The system does not perform face recognition or automatically infer student identity.

### Club plans, tasks, and reports

- A coordinator creates weekly/monthly plans and calendar events for an assigned club.
- Before changing an existing plan or report, the service writes the previous values to `plan_versions` or `report_versions` in the same database transaction.
- Dean decisions create immutable review rows and append an audit event; the current status is a projection of the latest decision.
- Reports without a linked club/plan remain valid for legacy data but do not influence club rankings.

### Audit trail

`audit_logs` is append-only at the SQLite layer. Each event should contain actor, action, entity, before/after snapshots, timestamp, request ID, previous hash, and entry hash. Hashes must be computed and appended in the same transaction. Do not write passwords, session tokens, verification-photo bytes, or private ballot choices into audit metadata.

### Secret elections

- Only verified students eligible for the election may vote while its status is `open` and the current time falls inside its voting window.
- In one transaction, insert the voter into `election_voters` (unique by election and user) and increment `election_tallies` for the chosen candidate.
- `election_tallies` stores only one aggregate count per candidate. It has no voter/user foreign key; the participation table says only that the student voted and cannot join a voter to a candidate choice. The legacy `election_ballots` table is not written by the current API.
- A ballot-cast audit event must not include voter ID, IP, candidate choice, or a request identifier that could re-identify the voter. Public results are aggregated counts after the election closes.
- Database operators can still inspect timing and backups. Stronger anonymity requires operational controls, delayed/batched ballot writes, restricted database access, and a documented election policy.

### Top clubs

The `club_rankings` view aggregates approved report scores only. The public top-three query should require at least three reviewed reports, then sort by average score descending, reviewed-report count descending, and club name ascending as a deterministic tie-break. Draft, rejected, and unreviewed reports do not count.

## Data Model

- `users`, `roles`, `permissions`, `user_roles`, `role_permissions`: credentials, account state, role grants, and permission catalog.
- `user_preferences`: per-user locale and notification settings.
- `student_verifications`: student number, faculty/group, private evidence photo, dean decision, and review note.
- `clubs`, `club_memberships`: club catalog and membership applications/assignments.
- `club_plans`, `plan_versions`, `plan_tasks`, `club_events`: period plans, immutable snapshots, task assignment, and calendar.
- `reports`, `report_versions`, `report_reviews`: report content, history, and dean evaluations.
- `elections`, `election_candidates`, `election_voters`, `election_tallies`: candidate approval, one-vote eligibility, and aggregate secret results. `election_ballots` remains an unused compatibility table.
- `audit_logs`: append-only, hash-linked security and business events.
- `system_settings`: non-secret system configuration. Secrets belong in environment/secret storage, not this table.
- `members`: legacy public roster retained for compatibility while student accounts and club memberships are introduced.

## Implementation Status

The expanded SQLite schema is loaded on startup and migrates existing member/report databases. Implemented backend flows include scrypt password hashes, revocable cookie sessions, CSRF checks, student verification submission and dean decisions, private verification-photo access, profile preferences/password change, club applications, coordinator-scoped plans/tasks/events, report review/version history, audit hash chaining, election candidate review, one-vote aggregate tallies, and published results. Public dashboard statistics, approved activity history, top-club ranking, and the SOM icon are connected.

This is still a local development product slice, not production-ready. The following work remains:

- Admin UI for user/role grants and role assignment beyond the first environment-bootstrapped admin; coordinator review controls for club membership applications.
- Full plan/task/report-review workflows in the browser. APIs enforce roles, but several existing page sections and forms are still prototype placeholders.
- Password reset, email verification, login rate limiting, profile-photo rendering, and recovery procedures.
- Lock down static files and upload access, add HTTPS/Secure cookies, security headers/CSP, stronger CSRF/origin checks, audit-chain verification, backups, restore drills, and retention/deletion policy.
- Confirm SOM's exact student-photo capture policy, identity fields, real club catalog, administrator roster, and hosting platform.
- Move the single-process local SQLite deployment to an operationally backed-up production database and private object storage before multi-user public hosting. Vote tallies are anonymous aggregates; deployment-level anonymity and election procedures still need institutional review.

Until these are implemented and reviewed, keep the service bound to localhost. Do not expose the current server to the public internet.
