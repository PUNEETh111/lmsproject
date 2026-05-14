"""
NMIT Library Management System
Flask Application Entry Point
"""
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, session, g)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nmit-library-secret-key-2026')
# Use /tmp for database if running on Render to ensure write permissions
if os.environ.get('RENDER'):
    app.config['DATABASE'] = '/tmp/library.db'
else:
    app.config['DATABASE'] = os.path.join(app.root_path, 'library.db')


# ─── Database Helpers ───────────────────────────────────────────────────────

def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database with schema and seed data."""
    db = get_db()
    
    # Create tables
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('admin', 'student', 'faculty')),
            provider TEXT NOT NULL DEFAULT 'Password',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            available INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            due_date TIMESTAMP NOT NULL,
            returned_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'returned', 'overdue')),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- View: Active Issues
        CREATE VIEW IF NOT EXISTS v_active_issues AS
        SELECT i.*, b.title as book_title, b.author as book_author, 
               u.name as user_name, u.email as user_email
        FROM issues i
        JOIN books b ON i.book_id = b.id
        JOIN users u ON i.user_id = u.id
        WHERE i.status = 'active';

        -- View: Issue History
        CREATE VIEW IF NOT EXISTS v_issue_history AS
        SELECT i.*, b.title as book_title, b.author as book_author,
               u.name as user_name, u.email as user_email
        FROM issues i
        JOIN books b ON i.book_id = b.id
        JOIN users u ON i.user_id = u.id
        ORDER BY i.issued_at DESC;
    ''')
    
    # Check if we need to seed
    try:
        user_count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if user_count == 0:
            # Seed admin user
            db.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Library Admin', 'admin@library.com',
                 generate_password_hash('admin123'), 'admin')
            )
            # Seed student user
            db.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('Demo Student', 'student@library.com',
                 generate_password_hash('student123'), 'student')
            )
            
            # Seed books
            books = [
                ('A Brief History of Time', 'Stephen Hawking', '9780553380163', 'Science'),
                ('The Selfish Gene', 'Richard Dawkins', '9780198788607', 'Science'),
                ('To Kill a Mockingbird', 'Harper Lee', '9780061120084', 'Fiction'),
                ('1984', 'George Orwell', '9780451524935', 'Fiction'),
                ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 'Fiction'),
                ('Sapiens: A Brief History of Humankind', 'Yuval Noah Harari', '9780062316097', 'History'),
                ('Guns, Germs, and Steel', 'Jared Diamond', '9780393317558', 'History'),
                ('Introduction to Algorithms', 'Thomas H. Cormen', '9780262033848', 'Engineering'),
                ('Clean Code', 'Robert C. Martin', '9780132350884', 'Engineering'),
                ('Calculus', 'Michael Spivak', '9780914098911', 'Mathematics'),
            ]
            for title, author, isbn, category in books:
                db.execute(
                    'INSERT OR IGNORE INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)',
                    (title, author, isbn, category)
                )
            
            # Seed one active issue (A Brief History of Time issued to Demo Student)
            student = db.execute('SELECT id FROM users WHERE email = ?', ('student@library.com',)).fetchone()
            book = db.execute('SELECT id FROM books WHERE isbn = ?', ('9780553380163',)).fetchone()
            if student and book:
                now = datetime.now()
                due = now + timedelta(days=14)
                db.execute(
                    'INSERT INTO issues (book_id, user_id, issued_at, due_date, status) VALUES (?, ?, ?, ?, ?)',
                    (book['id'], student['id'], now.strftime('%Y-%m-%d'), due.strftime('%Y-%m-%d'), 'active')
                )
                db.execute('UPDATE books SET available = 0 WHERE id = ?', (book['id'],))
            
            db.commit()
    except sqlite3.IntegrityError:
        # Already seeded by another worker
        pass
    except Exception as e:
        print(f"Database initialization error: {e}")


# ─── Auth Decorators ────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        # Verify user exists in database
        db = get_db()
        user = db.execute('SELECT id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if not user:
            session.clear()
            flash('Your session has expired. Please log in again.', 'info')
            return redirect(url_for('login'))
            
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('catalog'))
        return f(*args, **kwargs)
    return decorated_function


# ─── Context Processor ──────────────────────────────────────────────────────

@app.context_processor
def inject_user():
    """Inject current user data into all templates."""
    user = None
    if 'user_id' in session:
        try:
            db = get_db()
            user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            if user is None:
                # Stale session: user exists in cookie but not in database
                session.clear()
        except Exception as e:
            app.logger.error(f"Database error in inject_user: {e}")
            session.clear()
    return dict(current_user=user)


@app.route('/health')
def health():
    """Health check route to verify app is running and database is accessible."""
    try:
        db = get_db()
        db.execute('SELECT 1').fetchone()
        return jsonify(status='healthy', database='connected'), 200
    except Exception as e:
        return jsonify(status='unhealthy', error=str(e)), 500


# ─── Auth Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('user_role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('catalog'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_role'] = user['role']
            session['user_name'] = user['name']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('catalog'))
        
        flash('Invalid email or password.', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')
        
        if not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')
        
        if role not in ('student', 'faculty'):
            role = 'student'
        
        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')
        
        try:
            db.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
                (name, email, generate_password_hash(password), role)
            )
            db.commit()
            flash('Account created successfully! Please sign in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Admin Routes ───────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    total_books = db.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    available_books = db.execute('SELECT COUNT(*) FROM books WHERE available = 1').fetchone()[0]
    active_issues = db.execute("SELECT COUNT(*) FROM issues WHERE status = 'active'").fetchone()[0]
    overdue = db.execute(
        "SELECT COUNT(*) FROM issues WHERE status = 'active' AND due_date < date('now')"
    ).fetchone()[0]
    total_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_transactions = db.execute('SELECT COUNT(*) FROM issues').fetchone()[0]
    
    return render_template('admin/dashboard.html',
                           total_books=total_books,
                           available_books=available_books,
                           active_issues=active_issues,
                           overdue=overdue,
                           total_users=total_users,
                           total_transactions=total_transactions)


@app.route('/admin/books')
@admin_required
def admin_books():
    db = get_db()
    books = db.execute('SELECT * FROM books ORDER BY id').fetchall()
    return render_template('admin/books.html', books=books)


@app.route('/admin/books/add', methods=['POST'])
@admin_required
def admin_add_book():
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    isbn = request.form.get('isbn', '').strip()
    category = request.form.get('category', '').strip()
    
    if not all([title, author, isbn, category]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_books'))
    
    db = get_db()
    try:
        db.execute(
            'INSERT INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)',
            (title, author, isbn, category)
        )
        db.commit()
        flash('Book added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('A book with this ISBN already exists.', 'error')
    
    return redirect(url_for('admin_books'))


@app.route('/admin/books/edit/<int:book_id>', methods=['POST'])
@admin_required
def admin_edit_book(book_id):
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    isbn = request.form.get('isbn', '').strip()
    category = request.form.get('category', '').strip()
    
    if not all([title, author, isbn, category]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_books'))
    
    db = get_db()
    try:
        db.execute(
            'UPDATE books SET title=?, author=?, isbn=?, category=? WHERE id=?',
            (title, author, isbn, category, book_id)
        )
        db.commit()
        flash('Book updated successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('A book with this ISBN already exists.', 'error')
    
    return redirect(url_for('admin_books'))


@app.route('/admin/books/delete/<int:book_id>', methods=['POST'])
@admin_required
def admin_delete_book(book_id):
    db = get_db()
    # Check if book has active issues
    active = db.execute(
        "SELECT COUNT(*) FROM issues WHERE book_id = ? AND status = 'active'",
        (book_id,)
    ).fetchone()[0]
    
    if active > 0:
        flash('Cannot delete a book with active issues.', 'error')
    else:
        db.execute('DELETE FROM books WHERE id = ?', (book_id,))
        db.commit()
        flash('Book deleted successfully!', 'success')
    
    return redirect(url_for('admin_books'))


@app.route('/admin/users')
@admin_required
def admin_users():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY id').fetchall()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))
    
    db = get_db()
    # Check for active issues
    active = db.execute(
        "SELECT COUNT(*) FROM issues WHERE user_id = ? AND status = 'active'",
        (user_id,)
    ).fetchone()[0]
    
    if active > 0:
        flash('Cannot delete a user with active book issues.', 'error')
    else:
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
        flash('User deleted successfully!', 'success')
    
    return redirect(url_for('admin_users'))


@app.route('/admin/issues')
@admin_required
def admin_issues():
    db = get_db()
    issues = db.execute('''
        SELECT i.*, b.title as book_title, b.author as book_author,
               u.name as user_name, u.email as user_email
        FROM issues i
        JOIN books b ON i.book_id = b.id
        JOIN users u ON i.user_id = u.id
        ORDER BY i.issued_at DESC
    ''').fetchall()
    return render_template('admin/issues.html', issues=issues)


@app.route('/admin/issues/return/<int:issue_id>', methods=['POST'])
@admin_required
def admin_return_book(issue_id):
    db = get_db()
    issue = db.execute('SELECT * FROM issues WHERE id = ?', (issue_id,)).fetchone()
    
    if issue and issue['status'] == 'active':
        now = datetime.now().strftime('%Y-%m-%d')
        db.execute(
            "UPDATE issues SET status = 'returned', returned_at = ? WHERE id = ?",
            (now, issue_id)
        )
        db.execute('UPDATE books SET available = 1 WHERE id = ?', (issue['book_id'],))
        db.commit()
        flash('Book returned successfully!', 'success')
    else:
        flash('Issue not found or already returned.', 'error')
    
    return redirect(url_for('admin_issues'))


# ─── Student/Catalog Routes ────────────────────────────────────────────────

@app.route('/catalog')
@login_required
def catalog():
    db = get_db()
    search = request.args.get('search', '').strip()
    
    if search:
        books = db.execute(
            'SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY id',
            (f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        books = db.execute('SELECT * FROM books ORDER BY id').fetchall()
    
    return render_template('catalog.html', books=books, search=search)


@app.route('/catalog/borrow/<int:book_id>', methods=['GET', 'POST'])
@login_required
def borrow_book(book_id):
    if request.method == 'GET':
        return redirect(url_for('catalog'))
        
    db = get_db()
    try:
        book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
        
        if not book:
            flash('Book not found.', 'error')
            return redirect(url_for('catalog'))
        
        if not book['available']:
            flash('This book is currently unavailable.', 'error')
            return redirect(url_for('catalog'))
        
        # Check if user already has this book
        existing = db.execute(
            "SELECT id FROM issues WHERE book_id = ? AND user_id = ? AND status = 'active'",
            (book_id, session['user_id'])
        ).fetchone()
        
        if existing:
            flash('You already have this book borrowed.', 'error')
            return redirect(url_for('catalog'))
        
        now = datetime.now()
        due = now + timedelta(days=14)
        
        db.execute(
            'INSERT INTO issues (book_id, user_id, issued_at, due_date, status) VALUES (?, ?, ?, ?, ?)',
            (book_id, session['user_id'], now.strftime('%Y-%m-%d'), due.strftime('%Y-%m-%d'), 'active')
        )
        db.execute('UPDATE books SET available = 0 WHERE id = ?', (book_id,))
        db.commit()
        
        flash(f'Successfully borrowed "{book["title"]}"!', 'success')
        return redirect(url_for('my_books'))
    except sqlite3.IntegrityError as e:
        app.logger.error(f"IntegrityError in borrow_book: {e}")
        flash('Operation failed. Your session might be stale. Please log in again.', 'error')
        return redirect(url_for('login'))
    except Exception as e:
        app.logger.error(f"Unexpected error in borrow_book: {e}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('catalog'))


@app.route('/my-books')
@login_required
def my_books():
    db = get_db()
    active_loans = db.execute('''
        SELECT i.*, b.title as book_title, b.author as book_author
        FROM issues i
        JOIN books b ON i.book_id = b.id
        WHERE i.user_id = ? AND i.status = 'active'
        ORDER BY i.issued_at DESC
    ''', (session['user_id'],)).fetchall()
    
    history = db.execute('''
        SELECT i.*, b.title as book_title, b.author as book_author
        FROM issues i
        JOIN books b ON i.book_id = b.id
        WHERE i.user_id = ? AND i.status = 'returned'
        ORDER BY i.returned_at DESC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('my_books.html', active_loans=active_loans, history=history)


@app.route('/my-books/return/<int:issue_id>', methods=['POST'])
@login_required
def return_book(issue_id):
    db = get_db()
    issue = db.execute(
        'SELECT * FROM issues WHERE id = ? AND user_id = ?',
        (issue_id, session['user_id'])
    ).fetchone()
    
    if issue and issue['status'] == 'active':
        now = datetime.now().strftime('%Y-%m-%d')
        db.execute(
            "UPDATE issues SET status = 'returned', returned_at = ? WHERE id = ?",
            (now, issue_id)
        )
        db.execute('UPDATE books SET available = 1 WHERE id = ?', (issue['book_id'],))
        db.commit()
        flash('Book returned successfully!', 'success')
    else:
        flash('Issue not found or already returned.', 'error')
    
    return redirect(url_for('my_books'))


# ─── Template Filters ───────────────────────────────────────────────────────

@app.template_filter('format_date')
def format_date(value):
    """Format a date string to 'Mon DD, YYYY'."""
    if not value:
        return '—'
    try:
        if isinstance(value, str):
            dt = datetime.strptime(value.split(' ')[0], '%Y-%m-%d')
        else:
            dt = value
        return dt.strftime('%b %-d, %Y')
    except:
        return value


# ─── Initialize & Run ───────────────────────────────────────────────────────

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"CRITICAL: Failed to initialize database: {e}")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
