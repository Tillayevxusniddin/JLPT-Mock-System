# JLPT Mock System – Backend API

Multi-tenant backend for the JLPT (Japanese Language Proficiency Test) mock exam platform (mikan.uz).  
Django REST API with PostgreSQL (schema-per-tenant), Redis, Celery, and WebSockets.

---

## Features

- **Multi-tenant:** Centers (organizations) with isolated tenant schemas; JWT + subdomain-aware auth
- **Roles:** Owner, Center Admin, Teacher, Student, Guest
- **Mock tests & quizzes:** N5–N1 levels; sections, question groups, listening/media; publish flow
- **Assignments:** Exam rooms and homework; group or individual; deadlines
- **Attempts:** Start/submit exams and homework; auto-grading; snapshots
- **Notifications:** REST + WebSocket (real-time)
- **Analytics:** Dashboards per role (owner, center admin, teacher, student)
- **Storage:** Local files or S3-compatible (e.g. MinIO, AWS) with optional private/signed URLs

---

## Tech stack

- **Django 4.2** + **Django REST Framework** + **drf-spectacular** (OpenAPI 3)
- **PostgreSQL** (multi-tenant via schemas)
- **Redis** (cache, Celery broker, Channels)
- **Celery** + **Celery Beat**
- **Daphne** (ASGI / WebSockets)
- **JWT** (Simple JWT), **django-cors-headers**, **django-axes**, **django-storages** (S3)

---

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 14+**
- **Redis 7+**

---

## Run on localhost

### 1. Clone and enter the project

```bash
git clone <repository-url>
cd jlpt_mock_system
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
# or: venv\Scripts\activate   # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

Copy the example env file and edit it with your values:

```bash
cp .env.example .env
# or, if your repo has env.example:  cp env.example .env
```

See [Environment variables](#environment-variables) and the comments in `.env.example` (or `env.example`) for what to set. For a minimal local run you need at least:

- `DJANGO_SECRET_KEY` – any long random string
- `POSTGRES_PASSWORD` – your PostgreSQL password
- `DB_NAME`, `DB_USER`, `DB_HOST`, `DB_PORT` – match your local Postgres

### 5. Database and tenant migrations

Create the database (if it does not exist), then run migrations:

```bash
# Create DB (example; use your postgres user)
psql -U postgres -c "CREATE DATABASE jlpt_mock_db;"

# Apply public schema migrations
python manage.py migrate

# Create tenant schemas and run tenant migrations (required for multi-tenant)
python manage.py migrate_tenants
```

### 6. (Optional) Create a superuser and first center

```bash
python manage.py createsuperuser
```

Then use the API or admin to create a Center; tenant migrations for that center are created automatically (or run `migrate_tenants` again).

### 7. Run the Django server

```bash
python manage.py runserver
```

API base: **http://127.0.0.1:8000/**  
- API v1: **http://127.0.0.1:8000/api/v1/**  
- Swagger UI: **http://127.0.0.1:8000/api/docs/**  
- Health: **http://127.0.0.1:8000/health/**

### 8. Run Redis (required for Celery and WebSockets)

Start Redis on the default port (e.g. `redis-server` or Docker).  
If your `.env` uses `REDIS_URL=redis://localhost:6379/0`, no change needed.

### 9. Run Celery worker (optional, for async tasks)

In a second terminal (with the same venv and `.env`):

```bash
celery -A config worker -l info
```

### 10. Run Celery Beat (optional, for scheduled tasks)

In a third terminal:

```bash
celery -A config beat -l info
```

### 11. Run Daphne (optional, for WebSockets)

For real-time notifications:

```bash
daphne -b 127.0.0.1 -p 8001 config.asgi:application
```

Then point WebSocket clients to `ws://127.0.0.1:8001/ws/...` (or proxy via Nginx in production).

---

## Environment variables

All supported keys are listed in **`.env.example`** with short comments. Copy `.env.example` to `.env` and fill in the values.

Summary:

| Key | Description | Local example |
|-----|-------------|----------------|
| `DJANGO_SECRET_KEY` | Django secret key | Long random string |
| `DJANGO_DEBUG` | Debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts | `localhost,127.0.0.1,.mikan.uz` |
| `DB_NAME` | PostgreSQL database name | `jlpt_mock_db` |
| `DB_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password | (required) |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Redis URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | Same as `REDIS_URL` or set explicitly |
| `CELERY_RESULT_BACKEND` | Celery results | Same as broker or set explicitly |
| `FRONTEND_URL_BASE` | Frontend base URL (emails, CORS) | `http://localhost:3000` |
| `USE_S3` | Use S3-compatible storage | `False` for local |
| (Optional) | Email, AWS, Axes, etc. | See `.env.example` |

Production: set `DJANGO_SETTINGS_MODULE=config.settings.production` (or use `config.settings.development` for local). Then configure `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `SECRET_KEY`/`DJANGO_SECRET_KEY`, and optional SSL/email/S3 as in `.env.example`.

---

## Project structure

```
jlpt_mock_system/
├── api/v1/              # API URL routing and router (viewsets)
├── apps/
│   ├── core/            # Middleware, tenant utils, auth, serializers
│   ├── authentication/  # User, JWT, login, registration
│   ├── centers/         # Centers, invitations, contact requests
│   ├── groups/          # Groups, memberships
│   ├── materials/       # Materials
│   ├── mock_tests/      # Mock tests, sections, questions, quizzes
│   ├── assignments/     # Exam and homework assignments
│   ├── attempts/        # Submissions, grading
│   ├── notifications/   # Notifications (REST + WebSocket)
│   ├── analytics/       # Dashboards
│   └── chat/            # Chat
├── config/              # Django settings, WSGI/ASGI, Celery, storage
├── deployment/          # Nginx, Gunicorn, Daphne, Celery systemd units
├── templates/           # Email templates
├── manage.py
├── requirements.txt
├── .env.example         # All env keys and descriptions
└── docker-compose.yml   # Full stack (DB, Redis, web, Daphne, Celery)
```

---

## API overview

- **Auth:** `/api/v1/auth/register/`, `/api/v1/auth/login/`, `/api/v1/auth/me/`, etc.
- **Centers:** `/api/v1/owner-centers/`, `/api/v1/center-admin-centers/`, invitations, guests
- **Groups:** `/api/v1/groups/`, `/api/v1/group-memberships/`
- **Materials:** `/api/v1/materials/`
- **Mock tests:** `/api/v1/mock-tests/`, sections, question-groups, questions, quizzes
- **Assignments:** `/api/v1/exam-assignments/`, `/api/v1/homework-assignments/`
- **Attempts:** `/api/v1/submissions/` (with custom actions for start/submit exam and homework)
- **Notifications:** `/api/v1/notifications/`
- **Analytics:** `/api/v1/analytics/owner/`, `center-admin/`, `teacher/`, `student/`
- **Docs:** `/api/docs/` (Swagger), `/api/schema/` (OpenAPI schema)

---

## Running with Docker

```bash
docker-compose up -d
```

This starts PostgreSQL, Redis, the web app (migrate + migrate_tenants + collectstatic + Gunicorn), Daphne, and Celery worker + beat. See `docker-compose.yml` and `deployment/README.md` for production-style deployment (systemd, Nginx).

---

## Testing

```bash
pytest
# or with coverage:
pytest --cov=apps --cov-report=html
```

---

## License

MIT.
