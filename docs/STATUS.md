# EduBridge status

Rule used here: a feature counts as done only if it is implemented **and** covered by passing tests.

## Implemented and tested (Phase 2 and the shell of Phase 3)
- Student self-signup with a server-generated unique student ID (`S1001`, ...); public signup cannot create privileged roles.
- Teacher accounts created by the administrator (`T1001`, ...), temporary password shown once, forced password change.
- One-time admin bootstrap command; refuses a second run and weak passwords.
- Sign in (username or email), sign out (POST only), password change, password reset by email link (1 hour), session rotation on login, idle session timeout.
- Rate limiting for sign-in, signup and reset requests.
- Server-enforced roles with default-deny policy; HTML routes return 403, API routes return JSON 401/403.
- Separate Student, Teacher and Administrator dashboards and navigation.
- Editable student and teacher profiles; student profile completion indicator; email change needs current password; link fields accept only http(s).
- Admin console: account list with search and filters, create teacher, suspend and reactivate (suspended users lose their session immediately), audit log, real counts and a students-by-branch chart.
- Audit trail for sign-ins, failures, denied access, profile changes and account actions (no passwords or tokens).
- Security headers: CSP, frame denial, no-store on private pages, referrer policy.
- Concurrency test: 8 threads creating 40 accounts produce 40 unique, contiguous IDs.

## Tests
54 tests: `python manage.py test`. They cover cross-role page and API access, anonymous access, tampering with cookies, headers, query strings and session data, default-deny for undeclared views, ID uniqueness (sequential, constraints, concurrent), bootstrap rules, signup, sign-in, throttling, CSRF, temporary passwords, password reset, profile rules and the admin console.
Not run: linting and type checking (none configured), production build (not applicable to this stack).

## Placeholders (visual only)
Dashboard cards labelled "Not available yet": assignments, tests, resources, scholarships, meetings, notifications, student directory, performance views, platform settings.

## Not started
Branches/subjects/enrollments, resources, scholarships, assessments and coding evaluation, meetings, notifications, the three AI assistants, analytics beyond basic counts, demo data, account deletion policy.

## Needs external credentials or services later
- SMTP provider (password reset in production, notification emails).
- Meeting provider or teacher-supplied URLs (Phase 7).
- LLM API key for the three assistants (Phase 8).
- A sandboxed code-execution service, or manual grading, for coding questions (Phase 6).
- Redis or Memcached for shared rate limiting; PostgreSQL for production.
