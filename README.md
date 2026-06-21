# Animal Shelter Management System

A Flask web application for managing animal shelter operations end-to-end. Built with raw SQL via PyMySQL (parameterized queries, DictCursor, no ORM). Features an explicit approval-queue pattern: non-admin staff propose creates/updates; admins review and approve/reject via an `Edit_Request` table before changes hit the real tables.

## Features

- **Public** — Browse/filter animals, submit adoption/foster applications, report rescues with photo uploads, view donation channels.
- **Staff** (login required) — Review applications (rescue/adoption/foster), manage medical records (visits, treatments, vets), propose data edits.
- **Admin** (role-gated) — Approve/reject `Edit_Request` tickets, manage staff accounts (activate/deactivate, change roles), manage donation info, full CRUD without queue.

## Tech Stack

- Python 3.12, Flask, Jinja2
- MySQL (PyMySQL)
- Plain CSS
- bcrypt hashing, session-based auth

## Project Structure

```
animal_shelter/
├── run.py              # App entry point
├── schema.sql          # Database schema (13 tables)
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py     # App factory
│   ├── config.py
│   ├── db.py
│   ├── cli.py          # init-db, seed-demo
│   ├── services/
│   │   └── edit_apply.py   # Approval-queue handlers
│   ├── routes/
│   │   ├── public.py
│   │   ├── staff.py
│   │   ├── staff_auth.py
│   │   ├── staff_dashboard.py
│   │   ├── staff_admin.py
│   │   └── medical.py
│   ├── templates/
│   └── static/
```

## Local Setup

### Prerequisites

- Python 3.12+
- MySQL server running locally

### 1. Clone or download

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your database credentials:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Example `.env`:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=animal_shelter
SECRET_KEY=dev-secret-key-change-this-later
```

### 3. Create the database

In MySQL:

```sql
CREATE DATABASE animal_shelter;
```

### 4. Install dependencies

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 5. Initialize tables and seed demo data

```bash
flask --app run.py init-db
flask --app run.py seed-demo
```

### 6. Run

```bash
python run.py
```

Open http://localhost:5000

### Demo accounts (after seed-demo)

| Role  | Username    | Password     |
|-------|-------------|--------------|
| Admin | demo_admin  | DemoAdmin1!  |
| Staff | demo_staff  | DemoStaff1!  |

Pre-loaded demo data includes pending adoption/foster/rescue applications and one pending edit ticket for the admin approval queue.

## CLI Commands

| Command | Description |
|---------|-------------|
| `flask --app run.py init-db` | Create all tables from `schema.sql` |
| `flask --app run.py seed-demo` | Load demo accounts and sample data |
| `flask --app run.py seed-demo --force` | Clear and re-seed demo data |


## User Roles

- **Public** — Browse animals, submit adoption/foster/rescue applications, view donations.
- **Staff** — Review applications, manage medical records, propose edits (queued for admin).
- **Admin** — Approve/reject edit tickets, manage staff accounts, full CRUD without queue.
