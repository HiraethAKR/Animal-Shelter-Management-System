## Animal Shelter Management System

A Flask web application for managing animal shelter operations end-to-end — built with **raw SQL** (no ORM) and an explicit **approval-queue** pattern so non-admin changes are reviewed before they hit the database.

### Public-facing
- Browse available animals with filters (species, status, sex)
- Submit adoption and foster applications
- Report rescues with photo uploads and location details
- View donation channels

### Staff-facing
- **Dashboard**: Stats, pending applications, and recent edit requests
- **Applications**: Review and approve/reject rescues, adoptions, and fosters
- **Rescue verification**: Link rescue reports to new or existing animal records
- **Medical records**: Track visits, treatments, and associated veterinarians
- **Admin controls**: Role-based access, staff account management, and an `Edit_Request` queue for all non-admin data changes

### Stack
- **Backend**: Flask, Python 3.12
- **Database**: MySQL via PyMySQL (parameterized queries, `DictCursor`, no ORM)
- **Frontend**: Jinja2 templates, plain CSS
- **Security**: bcrypt password hashing, session-based auth, CSRF-safe forms
