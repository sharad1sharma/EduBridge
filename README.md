
<img width="1517" height="822" alt="Screenshot 2026-10-21 004611" src="https://github.com/user-attachments/assets/aaaf1075-1570-4e62-a9b6-513f01edac8c" />


# EduBridge — AI-Powered Educational Web Platform for B.Tech Students

EduBridge is a comprehensive, production-grade educational web application tailored for B.Tech engineering students in India across 11 disciplines (CSE, IT, AI & Data Science, ECE, Electrical, Mechanical, Civil, Chemical, Biotechnology, Aerospace, and First-Year Common Engineering).

---

## 🌟 Upgraded Core Features & Modules

### 1. Coding Resources & DSA Practice Hub (Student Mode)
- **Completely Replaced Embedded IDE**: The in-platform code compiler, editor, terminal, and internal runner have been completely decommissioned and upgraded to an external practice ecosystem.
- **Area A — DSA Questions & Curriculum Topics**:
  - Curated algorithmic practice library spanning 12 core categories: *Arrays and Strings, Searching and Sorting, Linked Lists, Stacks and Queues, Hashing, Recursion and Backtracking, Trees and Binary Search Trees, Graphs, Greedy Algorithms, Dynamic Programming, Two Pointers and Sliding Window, and Beginner Programming Problems*.
  - Every card features topic category, difficulty level (*Beginner, Easy, Medium, Hard*), verified external practice links (*LeetCode, HackerRank, GeeksforGeeks*), thumbnail visuals, and opens securely in a new tab (`target="_blank" rel="noopener noreferrer"`).
- **Area B — Online Compilers & Interpreters**:
  - Fast-access cloud execution environments for **Python, Java, and C**.
  - Verified platforms: *Programiz Online Compiler, OnlineGDB, Replit, and JDoodle*.
- **Student Access Control**: Read-only access. Students cannot author, edit, or delete institutional coding links.

### 2. Teacher & Admin Coding Resource Management
- **Curriculum Authoring Interface**: Teachers and Admins can create, edit, publish, unpublish, and archive external practice questions and online compilers.
- **Validation**: Backend URL validation (`URLValidator`), title, topic category, difficulty, platform name, and supported languages.
- **Publishing Workflow**: One-click toggling between `Draft` and `Published`. Published resources appear immediately in the Student Coding Hub; drafts and archived items are excluded.
- **Historical Integrity**: Soft-archive functionality preserves historical records and student assignment references.

### 3. Visual Thumbnails & Responsive Media
- **Topic Visuals**: Standardized aspect ratios, `object-fit: cover`, rounded cards, and responsive CSS grids for all learning resources and coding cards.
- **Graceful Fallbacks**: Integrated SVG fallbacks (`fallback-resource.svg`, `dsa-placeholder.svg`, `compiler-placeholder.svg`) ensuring zero broken images.

### 4. Advanced Visual Analytics System
- **Student Analytics (`/student/analytics/`)**: Displays all **5 graphical visualizations** directly before summary metric cards:
  - **Chart A**: Subject-Wise Performance (Bar Chart displaying actual assessment scores across all enrolled courses).
  - **Chart B**: Academic Performance Trajectory (Line Chart plotting score trends over time with timeframe filters).
  - **Chart C**: Academic Progress Doughnut Chart (Completed vs Pending syllabus tasks).
  - **Chart D**: Active Learning Time (Line/Area Chart of verified daily study minutes).
  - **Chart E**: Attendance Telemetry (Doughnut Chart of verified Present, Absent, and Late session rates).
- **Teacher Analytics (`/teacher/analytics/`)**:
  - **Mode A (My Teaching Analytics)**: Class average scores, evaluation trends, and subject-wise submission rates.
  - **Mode B (Student Analytics)**: Dual-mode support allowing instant search by Student ID (`S1001`) or cohort-wide aggregates across all authorized students.

### 5. Fixed Course Enrollment & Academic Diagnostics
- **Root Cause Resolved**: Fixed resolution logic that previously reported 0 enrolled subjects. Enrollment is now authoritatively calculated from explicit many-to-many enrollments, cohort curriculum matching, and active assessment/attendance records.
- **Personalized Recommendations**: Diagnostic improvement recommendations dynamically evaluate real assessment scores, attendance thresholds (<75%), and learning activity.

### 6. Institutional Attendance Management System
- **Multi-Role Tracking**:
  - **Student**: View personal attendance percentage, present/absent/late totals, subject breakdown, and history logs (strictly read-only).
  - **Teacher**: Authorized class roster marking (`/teacher/attendance/`), date selection, quick "Mark All Present" action, and real-time session rate calculations.
  - **Admin**: Cross-departmental attendance telemetry (`/administration/attendance/`), discrepancy resolution, and full modification audit trail.
- **Automatic Login Attendance Policy**:
  - Distinguishes between platform login activity and physical class attendance.
  - Automatically records deduplicated daily platform activity upon user login without fabricating class attendance.

---

## 🚀 Deterministic Demo Data

EduBridge includes a deterministic seed command that provisions a realistic, fully populated demonstration environment:

```bash
python manage.py seed_demo_data
```

### Pre-configured Demo Accounts:

| Role | Username | Password | Public ID | Key Data / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Student** | `student_rahul` | `Demo@12345` | `S1001` | Enrolled in 4 CSE subjects (CS301-CS304), 84% avg, 82% attendance |
| **Student** | `student_priya` | `Demo@12345` | `S1002` | Enrolled in 4 CSE subjects, completed tests |
| **Student** | `student_amit` | `Demo@12345` | `S1003` | ECE Student (EC201, CS301) |
| **Student (Suspended)** | `student_suspended` | `Demo@12345` | `S1009` | Deactivated account for testing admin controls |
| **Faculty / Teacher** | `prof_sharma` | `Demo@12345` | `T2001` | HOD CSE, Assigned to CS301, CS302 |
| **Faculty / Teacher** | `prof_verma` | `Demo@12345` | `T2002` | Associate Professor, Assigned to CS303, CS304 |
| **Administrator** | `admin` | `EduBridgeAdmin2026!` | `A0001` | Institutional Admin & AI Console |

---

## 🛠️ Local Development Setup

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- SQLite (default) or PostgreSQL

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/<your-username>/edubridge.git
cd edubridge

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed deterministic demo dataset
python manage.py seed_demo_data

# Run local development server
python manage.py runserver 127.0.0.1:8000
```

---

## ☁️ Render Deployment Guide

EduBridge is configured for seamless deployment as a **Render Web Service** using WhiteNoise and Gunicorn.

### 1. Deployment Files Included
- `render.yaml`: Declarative Render blueprint specifying service type, build command, start command, and environment variables.
- `build.sh`: Automated executable build script running dependency installation, static collection, migrations, and demo data seeding.
- `Procfile`: Gunicorn entrypoint definition (`web: gunicorn config.wsgi:application`).
- `.env.example`: Safe environment variable template with placeholders only.

### 2. Manual Render Web Service Setup
1. Create a new **Web Service** on [Render](https://render.com/).
2. Connect your GitHub repository.
3. Configure the following service settings:
   - **Environment**: `Python`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn config.wsgi:application`
4. In **Environment Variables**, add:
   - `DJANGO_SECRET_KEY`: `<generate-a-strong-secret-key>`
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: `.onrender.com`
   - `DJANGO_BEHIND_TLS_PROXY`: `True`
   - `DJANGO_SECURE_SSL_REDIRECT`: `True`
   - `DJANGO_SECURE_COOKIES`: `True`
   - `COHERE_API_KEY`: `<your-cohere-api-key>`
   - `COHERE_MODEL`: `command-a-03-2025`
   - `SEED_DEMO_DATA`: `true` (provisions realistic demo data automatically on first deployment)

---

## 🧪 Testing & Verification

Run the comprehensive automated test suite:

```bash
python manage.py test
```
