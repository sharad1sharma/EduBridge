# EduBridge Engineering & Implementation Process (PROCESS.md)

This document records the architectural process, engineering decisions, and security implementations undertaken to complete the EduBridge Administrator Module.

---

## 1. Requirement & Architecture Analysis

The Master Prompt required an end-to-end, fully functional Administrator module for EduBridge, an educational web platform tailored for Indian B.Tech engineering curricula. Key requirements:
1. Strict server-side access control (only role `admin` can access any administration view or API).
2. Live database-backed analytics with Pie/Donut charts, Multi-line graphs, and Vertical Bar charts (per user voice instruction).
3. Student and Teacher lifecycle management with deliberate confirmation workflows.
4. Support for all 11 B.Tech engineering branches and subjects.
5. Daily practice assignments (10+ MCQs) and Weekly tests (25 MCQs + 5 coding exercises).
6. Admin-only scholarship management.
7. Learning resources, meetings, and notification monitoring.
8. A dedicated EduBridge Admin AI Assistant backed by direct database records.

---

## 2. Database Schema & Data Models (`dashboards/models.py`)

Created robust relational models with appropriate foreign keys, indexing, and cascade restrictions:
- `AcademicBranch`: 11 engineering disciplines (`CSE`, `IT`, `AIDS`, `ECE`, `EE`, `ME`, `CE`, `CHE`, `BT`, `AE`, `FYE`).
- `Subject`: Engineering subjects linked to branches and semesters with credit weighting.
- `Assessment`: Daily assignments and weekly tests with duration, total marks, and questions payload.
- `AssessmentAttempt`: Attempts by students, score tracking, submission timestamps, and tab-focus integrity counts.
- `LearningResource`: Notes, lab manuals, and video lectures.
- `Scholarship`: Strictly administered scholarship records with eligibility criteria and approaching deadline tracking.
- `Meeting`: Faculty-scheduled live lectures with participant counts and cancellation states.
- `PlatformNotification`: System dispatch logs with delivery status (`delivered`, `pending`, `failed`) and retry counters.
- `PlatformSetting`: Non-secret platform configurations.

---

## 3. UI/UX & Chart Engineering

Adhering to EduBridge's CSP (`style-src 'self'; script-src 'self'`):
- External charting CDNs are disallowed.
- **Pure SVG Visualizations**:
  - **Donut / Pie Chart**: Rendered using mathematical SVG circle dasharrays with legend chips for account security health.
  - **Multi-Series Line Graph**: Responsive SVG `<polyline>` with dual metric tracking (New student enrollments vs. assessment attempts over the last 7 days).
  - **Vertical Bar Chart**: Normalized vertical bar meters displaying student enrollment counts across semesters S1 through S8.
- Filter panels and CSV export triggers for Students, Faculty, Assessments, Scholarships, and Security Audit events.

---

## 4. Admin AI Assistant Engine (`dashboards/admin_ai.py`)

- **Domain Routing**: Analyzes user prompts into Student, Faculty, Academic/Assessment, Meeting, or Scholarship domains.
- **Direct Database Aggregation**: Executes real queries using Django ORM to aggregate counts, averages, and active records.
- **Safety Boundaries**: Strips internal sensitive fields (`password`, `pbkdf2` hashes, session keys).
- **Dedicated Console**: Built under `/administration/ai/` with quick prompt chips and interactive feedback.

---

## 5. Security & Access Verification

- **Default-Deny Middleware**: Checked via `AccessPolicyMiddleware` and `@role_required(...)`.
- **Automated Tests (`dashboards/tests/test_admin_suite.py` & `test_student_teacher_suite.py`)**:
  - Verified Students and Teachers receive HTTP 403 when attempting to access `/administration/` or `/administration/api/ai/`.
  - Verified Scholarship management is strictly Admin-only (students and teachers cannot create or edit scholarships).
  - Verified deliberate confirmation requirement (typing student public ID) for destructive deletions.
  - Verified AuditLog records sensitive administrative and academic events.
  - Verified CSV exports and metric calculations match database records.

---

## 6. Student & Teacher Modules Implementation

### Architecture & Security Policies:
1. **Concurrency-Safe Unique IDs**:
   - `accounts/services.py` allocates public IDs with format `S####` for students and `T####` for teachers using atomic `IdSequence` table locking.
   - Handles range exhaustion at 9999 by raising `RuntimeError("Available 4-digit ID range for {prefix} has been exhausted.")`.
2. **Strict Server-Side Isolation**:
   - Every protected view is wrapped with `@role_required(Role.STUDENT)` or `@role_required(Role.TEACHER)`.
   - `accounts.middleware._wants_json(request)` detects `/api/` paths and yields JSON `403 Forbidden` responses rather than HTML redirects.
3. **Assessment Player & Integrity Engine (`dashboards/student_views.py` & `assessment_player.js`)**:
   - Server-authoritative countdown timing: official remaining seconds computed from `Assessment.deadline` and attempt start time.
   - Periodic 20s autosave and instantaneous answer-selection synchronization to `/student/assessment/<id>/autosave/`.
   - Anti-cheat tab visibility change tracking (`visibilitychange` and `blur` events): logs focus losses and triggers automatic finalization if the teacher-configured threshold (`max_tab_switches_allowed`) is exceeded.
   - Automatic submission on deadline expiration without allowing duplicate result records.
4. **Curriculum Personalization**:
   - All 11 B.Tech engineering branches supported (`CSE`, `IT`, `AIDS`, `ECE`, `EE`, `ME`, `CE`, `CHE`, `BT`, `AE`, `FY`).
   - Dynamic subject catalogs, personalized learning resources, and branch-specific coding challenges.
5. **Teacher Authoring & Notification Dispatch**:
   - Daily assignments enforced with $\ge 10$ MCQs.
   - Weekly tests enforced with 25 MCQs and 5 branch-tailored coding/numerical problems.
   - Live lecture scheduling automatically creates and dispatches `PlatformNotification` records to all eligible students matching branch and semester.
6. **Student & Teacher AI Assistants**:
   - **EduBridge Student AI (`dashboards/student_ai.py`)**: Answers questions regarding pending assignments, upcoming exams, scheduled lectures, and personalized study roadmaps.
   - **EduBridge Teacher AI (`dashboards/teacher_ai.py`)**: Equips faculty with diagnostics on cohort performance, incomplete submissions, and topic weaknesses.
   - Zero-trust architecture: both AI engines strictly query only authorized records from the persistent database.

---

## 7. Verification & Acceptance Testing

The complete test suite of **82 automated tests** passes with 0 failures and 0 errors:

```bash
python manage.py test
```

```text
Ran 82 tests in 1.462s
OK
```

All student, teacher, and administrative features are connected directly to persistent database models, verified via automated test suites, and running live on the local development server.
