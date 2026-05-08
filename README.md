# NMIT Library Management System

A full-stack Library Management System built with Flask and SQLite, featuring a stunning dark navy UI with gold accents.

## Features

- **Role-Based Authentication** — Admin and Student roles with secure login/registration
- **Admin Dashboard** — Overview stats (total books, available, active issues, overdue)
- **Book Management** — Full CRUD operations for the book catalog
- **User Management** — View and manage registered library members
- **Issue Tracking** — Track all book loans with filter tabs (All, Active, Overdue, Returned)
- **Library Catalog** — Browse and search books with real-time availability status
- **Borrow & Return** — Students can borrow available books and return them
- **My Books** — Students can track active loans and reading history

## Demo Credentials

| Role    | Email                | Password   |
|---------|---------------------|------------|
| Admin   | admin@library.com   | admin123   |
| Student | student@library.com | student123 |

## Tech Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** Jinja2 Templates, Vanilla CSS
- **Auth:** Session-based with Werkzeug password hashing
- **Production:** Gunicorn WSGI

## Quick Start

```bash
# Clone the repository
git clone <your-repo-url>
cd lmsproject

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Visit **http://localhost:5000** in your browser.

## Project Structure

```
lmsproject/
├── app.py                  # Main Flask application
├── wsgi.py                 # WSGI entry point (production)
├── requirements.txt        # Python dependencies
├── library.db              # SQLite database (auto-created)
├── static/
│   └── style.css           # Global stylesheet
├── templates/
│   ├── base.html           # Base layout with navbar
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── catalog.html        # Library catalog (browse & search)
│   ├── my_books.html       # Student's active loans & history
│   └── admin/
│       ├── dashboard.html  # Admin dashboard
│       ├── books.html      # Book management (CRUD)
│       ├── users.html      # User management
│       └── issues.html     # Issue records with filters
└── README.md
```

## Deployment

### Render

1. Push to GitHub
2. Create a new Web Service on Render
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn wsgi:app`

## License

MIT
