# Campus Resource Conflict Resolver

A web application built with **Django** and **MySQL** that manages campus reservations (rooms, labs, seminar halls, projectors, equipment), detects overlapping bookings using half-open time intervals, and provides status tracking and approval workflows.

---

## Tech Stack
- **Backend:** Python 3.14, Django 5.2 (LTS)
- **Database:** MySQL Server 8.0 (UTF-8 `utf8mb4_unicode_ci`)
- **Database Driver:** `mysqlclient` / `PyMySQL`
- **Frontend (Upcoming Phases):** HTML5, Bootstrap 5, Django Templates

---

## Project Structure
```text
campus_resource_conflict_resolver/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── campus_resolver/             # Django project configuration
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── resources/                   # Resource models, blocks, admin, seed command
│   ├── models.py
│   ├── admin.py
│   ├── tests.py
│   └── management/commands/seed_data.py
├── bookings/                    # Booking and conflict detection logic
│   ├── models.py
│   ├── services.py              # Half-open interval conflict detection & audit trail
│   ├── admin.py
│   └── tests.py
├── dashboard/                   # User and Admin dashboards
├── templates/                   # Base and app templates
└── static/                      # Static CSS, JS, and images
```

---

## Phase 1, 2, 3 & 4 Completed Deliverables

### Phase 1: Environment and Project Setup
1. **Virtual Environment**: Python venv configured and activated.
2. **Dependencies Installed**: Django, mysqlclient, pymysql, cryptography, python-dotenv.
3. **MySQL Database**: `campus_resolver` created with `utf8mb4` character set. Dedicated user `campus_app` configured.
4. **Environment Configuration**: `.env` and `.env.example` setup with secure variable loading.
5. **Initial Migrations**: Executed successfully for auth, admin, sessions, contenttypes.
6. **Administrator Created**: Superuser `admin` initialized.

### Phase 2: Relational Models & ORM
1. **Resource Model**:
   - `name`, `resource_type` (Choices: Lab, Classroom, Seminar Hall, Projector, Equipment, Other), `location`, `capacity`, `description`, `is_active`.
   - Database indexes on `resource_type`, `is_active`, `location`.
2. **ResourceBlock Model**:
   - Represents maintenance periods and unavailable time windows.
   - Half-open interval start/end validation.
3. **Booking Model**:
   - `user` (FK to User), `resource` (FK to Resource), `start_time`, `end_time`, `purpose`, `status` (PENDING, APPROVED, REJECTED, CANCELLED).
   - Compound index on `(resource, start_time, end_time)` and index on `status`.
   - Model validation: `start_time < end_time` and active resource constraint.
4. **BookingHistory Model**:
   - Audit trail tracking status transitions: `booking`, `changed_by`, `old_status`, `new_status`, `changed_at`, `remarks`.
5. **Core Conflict Detection Service (`bookings/services.py`)**:
   - Implements half-open time interval logic `[start, end)`.
   - Overlap rule: `start_time < requested_end AND end_time > requested_start`.
   - Pending and Approved bookings block slots; Cancelled and Rejected bookings do not block.
   - Consecutive / adjacent slots (e.g. 10:00–11:00 and 11:00–12:00) are cleanly permitted.
6. **Django Admin Integration**:
   - Registered models with search, filters, inline history audit logs, and list displays.

### Phase 3: Authentication and Permissions
1. **Registration & Role Assignment**:
   - Registration form with server-side duplicate username and duplicate email checks.
   - Password confirmation and Django password validators (`validate_password`).
   - Role selection (`Student`, `Faculty Member`) automatically adds the user to the corresponding Django `Group`.
   - Default role groups (`Student`, `Faculty`, `Resource Manager`) initialized via `python manage.py init_roles`.
2. **Login, Logout & Password Management**:
   - Bootstrap 5 styled login view (`CampusLoginView`) with session management and flash alerts.
   - Secure logout (`logout_view`) clearing session with feedback message.
   - Password change forms and confirmation views (`CampusPasswordChangeView`, `CampusPasswordChangeDoneView`).
3. **Role-Aware Access Control & Permissions**:
   - Custom decorators: `@admin_or_staff_required`, `@role_required(['Faculty', 'Resource Manager'])`.
   - Object-level authorization checks:
     - Normal users can only view and cancel their own bookings.
     - Administrators and Resource Managers can review, approve, and reject reservations.
   - Custom `403.html` template for graceful permission-denied feedback.
4. **Responsive Bootstrap 5 UI & Navigation**:
   - Responsive navbar displaying real-time authentication state, username, and role badge (`Admin`, `Manager`, `Faculty`, `Student`).
   - Central role-aware dashboard (`dashboard_home`) showing admin metrics (resources, pending approvals) or student/faculty metrics (user reservations).

### Phase 4: Resources and Availability
1. **Resource Browsing & Search (`/resources/`)**:
   - Search by keyword (`name`, `description`, `location`).
   - Filtering by `category/resource_type`, `location`, `min_capacity`, and active status.
   - Responsive cards with category badges, capacity, and status badges.
   - Paginated display preserving filter query arguments.
2. **Date-Specific Availability & Resource Details (`/resources/<id>/`)**:
   - Detailed resource specifications, equipment facilities, and capacity.
   - Interactive date-picker availability calendar.
   - Real-time schedule display showing all confirmed/pending bookings and maintenance blocks for that specific day.
   - Clear indicators for open slots vs occupied half-open intervals `[start, end)`.
3. **Authorized Resource Management**:
   - `/resources/create/` and `/resources/<id>/edit/`: Restricted to administrators and resource managers with input validation.
   - `/resources/<id>/block/`: Allows scheduling maintenance blackout periods.
4. **Booking Forms & Conflict Validation (`/bookings/book/`)**:
   - Validates that `start_time < end_time` and enforces minimum duration.
   - Validates that resource is active.
   - Real-time conflict engine: Blocks overlapping booking requests with existing pending/approved slots or maintenance windows.
   - Permitted adjacent booking slots: consecutive reservations (e.g. 10:00–11:00 followed by 11:00–12:00) succeed without false positives.
   - Auto-assigns logged-in user, sets status `PENDING`, and logs initial creation in `BookingHistory`.
5. **Personal Reservations & Cancellation (`/bookings/my-bookings/`)**:
   - Status filtering pills: All, Pending, Approved, Cancelled, Rejected.
   - Details view (`/bookings/<id>/`) showing complete reservation info and full audit trail timeline of status transitions.
   - Eligible cancellation workflow (`/bookings/<id>/cancel/`): Allows users to cancel their own pending/approved reservations with optional reason logging into `BookingHistory`.
6. **Automated Test Suite**:
   - 42 tests passing across models, services, auth, resource filtering, availability schedules, booking forms, conflict validation, and cancellations (`Ran 42 tests in 76.225s - OK`).

---

## Quickstart Guide

### 1. Activate Environment
```powershell
.\venv\Scripts\activate
```

### 2. Configure `.env`
Ensure your `.env` contains:
```env
DEBUG=True
SECRET_KEY=your-secret-key
DB_NAME=campus_resolver
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
```

### 3. Run Migrations & Seed Sample Data
```powershell
python manage.py migrate
python manage.py seed_data
```

### 4. Run Automated Tests
```powershell
python manage.py test
```

### 5. Start Development Server
```powershell
python manage.py runserver
```
Admin dashboard available at: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
- **Admin Username:** `admin`
- **Admin Password:** `admin123`
