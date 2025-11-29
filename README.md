# 🎯 JLPT Mock System - Backend API

Professional online JLPT (Japanese Language Proficiency Test) mock testing platform for language centers.

## 📋 Features

### 🔐 Multi-tenant Architecture

- **OWNER**: Platform administrator managing all centers
- **CENTERADMIN**: Language center administrators
- **TEACHER**: Test creators and graders
- **STUDENT**: Test takers

### 📚 JLPT Test Management

- Support for all levels (N5-N1)
- Simplified structure: **Level → Mondai → Question**
- 4-choice multiple-choice questions
- Real JLPT format and timing
- Image and audio support

### 🎓 Assignment System

- Group assignments (entire class)
- Individual assignments (specific students)
- Configurable settings (retakes, time limits, etc.)
- Automatic grading

### 📊 Analytics & Progress Tracking

- Student progress dashboards
- Organization-level statistics
- Teacher performance metrics
- Detailed attempt analysis

### 🔒 Security & Audit

- JWT authentication
- Role-based permissions
- Complete audit trail
- Secure multi-tenancy

## 🛠️ Tech Stack

- **Framework**: Django 4.2 + Django REST Framework
- **Database**: PostgreSQL
- **Cache**: Redis
- **Task Queue**: Celery + Celery Beat
- **Authentication**: JWT (Simple JWT)
- **API Docs**: drf-spectacular (OpenAPI 3)
- **Storage**: AWS S3 / Local

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/jlpt-mock-system.git
cd jlpt-mock-system
```

2. **Create virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Setup environment variables**

```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Run migrations**

```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Create superuser**

```bash
python manage.py createsuperuser
```

7. **Run development server**

```bash
python manage.py runserver
```

8. **Run Celery worker** (in another terminal)

```bash
celery -A config worker -l info
```

9. **Run Celery beat** (for periodic tasks)

```bash
celery -A config beat -l info
```

## 📁 Project Structure

```
jlpt_mock_system/
├── apps/
│   ├── core/              # Base models & utilities
│   ├── authentication/    # User management
│   ├── organizations/     # Multi-tenancy
│   ├── groups/           # Student groups
│   ├── invitations/      # Invitation system
│   ├── mock_tests/       # JLPT tests (Level→Mondai→Question)
│   ├── assignments/      # Test assignments
│   ├── attempts/         # Student attempts
│   ├── analytics/        # Statistics
│   └── audit/           # Audit logging
├── config/              # Django settings
├── media/              # User uploads
├── static/             # Static files
└── templates/          # Email templates
```

## 🔑 API Endpoints

### Authentication

- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - Login (get JWT tokens)
- `POST /api/auth/refresh/` - Refresh access token
- `POST /api/auth/logout/` - Logout

### Organizations

- `GET /api/organizations/` - List organizations (OWNER only)
- `POST /api/organizations/` - Create organization
- `GET /api/organizations/{id}/` - Organization details
- `PATCH /api/organizations/{id}/` - Update organization

### Groups

- `GET /api/groups/` - List groups
- `POST /api/groups/` - Create group
- `GET /api/groups/{id}/` - Group details
- `POST /api/groups/{id}/add-student/` - Add student to group

### Invitations

- `GET /api/invitations/` - List invitation codes
- `POST /api/invitations/` - Create invitation code
- `POST /api/invitations/use/` - Use invitation code

### Mock Tests

- `GET /api/mock-tests/` - List tests
- `POST /api/mock-tests/` - Create test
- `GET /api/mock-tests/{id}/` - Test details
- `POST /api/mock-tests/{id}/publish/` - Publish test

### Mondais

- `GET /api/mock-tests/{test_id}/mondais/` - List mondais
- `POST /api/mock-tests/{test_id}/mondais/` - Create mondai
- `GET /api/mondais/{id}/` - Mondai details

### Questions

- `GET /api/mondais/{mondai_id}/questions/` - List questions
- `POST /api/mondais/{mondai_id}/questions/` - Create question
- `GET /api/questions/{id}/` - Question details

### Assignments

- `GET /api/assignments/` - List assignments
- `POST /api/assignments/` - Create assignment
- `GET /api/assignments/{id}/` - Assignment details
- `GET /api/assignments/my-tasks/` - Student's tasks

### Attempts

- `GET /api/attempts/` - List attempts
- `POST /api/attempts/` - Start attempt
- `POST /api/attempts/{id}/submit/` - Submit attempt
- `GET /api/attempts/{id}/results/` - View results

### Analytics

- `GET /api/analytics/student-progress/` - Student progress
- `GET /api/analytics/organization-stats/` - Organization stats
- `GET /api/analytics/teacher-stats/` - Teacher statistics

## 🧪 Testing

Run tests:

```bash
pytest
```

With coverage:

```bash
pytest --cov=apps --cov-report=html
```

## 📝 Database Models

### Core Models

- **TimeStampedModel**: Base with `id`, `created_at`, `updated_at`
- **TenantBaseModel**: Multi-tenant base with `organization_id`

### Main Models

1. **User**: Custom user (OWNER, CENTERADMIN, TEACHER, STUDENT)
2. **Organization**: Language centers
3. **Group**: Student groups (N5, N4, etc.)
4. **InvitationCode**: Student invitation system
5. **MockTest**: JLPT test container
6. **Mondai**: Question sets (文字語彙, 文法, 読解, 聴解)
7. **Question**: Individual questions (4 choices)
8. **Choice**: Answer choices
9. **Assignment**: Test assignments
10. **Attempt**: Student test attempts
11. **Answer**: Student answers
12. **StudentProgress**: Progress tracking
13. **AuditLog**: Activity logging

## 🔄 Data Flow

1. **OWNER** creates **Organization** → **CENTERADMIN** account
2. **CENTERADMIN** creates **Groups** and **Teachers**
3. **CENTERADMIN** generates **InvitationCode**
4. **Students** use code to join
5. **TEACHER** creates **MockTest** (with Mondais and Questions)
6. **TEACHER** creates **Assignment** (to Group or Student)
7. **STUDENT** takes test (**Attempt** created)
8. **STUDENT** submits → auto-graded (**Answers** evaluated)
9. **TEACHER** reviews and gives feedback
10. **Analytics** updated automatically

## 🔐 Permissions

### OWNER

- Manage all organizations
- View platform-wide statistics
- Create/suspend organizations

### CENTERADMIN

- Manage own organization
- Create/manage teachers
- Create/manage groups
- Generate invitation codes
- View organization statistics

### TEACHER

- Create/manage mock tests
- Create assignments
- View student results
- Give feedback
- View assigned groups

### STUDENT

- View assigned tests
- Take tests
- View own results
- View progress

## 🌍 Environment Variables

See `.env.example` for all available configuration options.

Key settings:

- `SECRET_KEY`: Django secret key
- `DEBUG`: Debug mode (False in production)
- `DATABASE_URL`: PostgreSQL connection
- `REDIS_URL`: Redis connection
- `ALLOWED_HOSTS`: Allowed domains
- `CORS_ALLOWED_ORIGINS`: Frontend URLs

## 📦 Deployment

### Using Docker

```bash
docker-compose up -d
```

### Manual Deployment

1. Set `DEBUG=False`
2. Configure production database
3. Set up Redis
4. Configure AWS S3 for media files
5. Set up Nginx + Gunicorn
6. Configure SSL certificate
7. Set up Celery as systemd service

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License.

## 📧 Contact

- **Email**: support@jlptmock.com
- **Website**: https://jlptmock.com
- **Documentation**: https://docs.jlptmock.com

---

**Made with ❤️ for Japanese language learners worldwide 🇯🇵**
