# EduBridge Setup & Deployment Guide

Requires Python 3.10 or newer (Django 5.2 LTS or 6.x installed via `requirements.txt`).

## Local Development Quickstart

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env               # Windows: copy .env.example .env

# 4. Run database migrations
python manage.py migrate

# 5. Populate complete B.Tech curriculum and demo users
python manage.py seed_data

# 6. Start the development server
python manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/>.

### Pre-Configured Test Accounts

- **Admin Account**:
  - Username: `admin`
  - Password: `EduBridgeAdmin2026!`
  - Console: <http://127.0.0.1:8000/administration/>
  - Admin AI: <http://127.0.0.1:8000/administration/ai/>

- **Teacher Account**:
  - Username: `prof_sharma`
  - Password: `EduBridgeTeacher2026!`
  - ID: `T1001`
  - Workspace: <http://127.0.0.1:8000/teacher/>

- **Student Account**:
  - Username: `jane_wick_099`
  - Password: `EduBridgeStudent2026!`
  - ID: `S1001` (B.Tech CSE, Sem 4)
  - Workspace: <http://127.0.0.1:8000/student/>

## Automated Test Suite

```bash
python manage.py test
```

The test suite runs 68 tests across authentication, default-deny security middleware, role boundaries, scholarship exclusivity, and analytical database reporting.

## Access Control Model

Every view declares an access policy from `accounts/access.py`:
- `@public`
- `@authenticated`
- `@role_required(Role.STUDENT)`
- `@role_required(Role.TEACHER)`
- `@role_required(Role.ADMIN)`

`AccessPolicyMiddleware` enforces this on the server before view execution. Any view lacking an explicit policy is rejected with a 500 error during development and 403 in production.
