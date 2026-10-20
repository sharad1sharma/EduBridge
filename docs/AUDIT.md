# Phase 1 audit and implementation plan

## What existed
No codebase was provided, only the master prompt, README.md and PROCESS.md, so there was no existing code to preserve, no existing routes, no data models, and no branding assets. This build starts from scratch.

## Stack chosen and why
- **Django (Python)** with server-rendered templates. It supplies PBKDF2 password hashing, signed sessions, CSRF protection, migrations, an ORM with constraints, and a test runner, which are the security-critical pieces of Phase 2.
- **SQLite** by default (zero setup), **PostgreSQL** via environment variables for production.
- No JavaScript framework yet. Assessment timers and autosave (Phase 6) will add a small amount of JS.

## Design decisions that go beyond the prompt
1. **Public signup creates students only.** Teachers also see student data, so teacher accounts are created by an administrator with a one-time temporary password and a forced change at first sign-in.
2. **Default-deny authorization.** A view with no declared access policy is refused, so a forgotten decorator fails closed.
3. **One admin, created by command.** `bootstrap_admin` prompts for the password, refuses to run twice, and serialises concurrent runs. There is no default or hardcoded admin credential.
4. **IDs** come from a locked counter row inside the same transaction that creates the user, backed by unique and check constraints (`S`/`T` prefix must match the role).
5. Django's built-in admin site is not installed, so there is a single privileged surface.

## Risks and gaps to be aware of (not yet addressed)
- No email verification at signup or on email change (email change does require the current password).
- Signup reveals whether a username or email is taken (needed for usable forms; mitigated by rate limiting).
- Rate-limit counters live in process memory by default.
- No multi-factor authentication for administrators.
- Audit log is append-only in application code only.
- Teacher temporary passwords are handed over out-of-band by the admin.
- Account deletion policy is not defined or implemented (suspend/reactivate only).

## Phase plan
| Phase | Scope | Status |
|---|---|---|
| 1 | Audit and plan | Done (this file) |
| 2 | Auth and role-based authorization | Done and tested |
| 3 | Separate dashboards | Shell done; feature widgets are placeholders |
| 4 | Branches, subjects, enrollments, teacher-student directory | Not started |
| 5 | Resources and scholarships | Not started |
| 6 | Assessments, timers, autosave, coding evaluation | Not started |
| 7 | Meetings and notifications | Not started |
| 8 | Student, Teacher and Admin AI assistants | Not started |
| 9 | Analytics and audit expansion | Audit log started |
| 10 | Final verification, demo data, docs | Not started |
