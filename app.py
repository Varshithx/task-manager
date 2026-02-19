"""
app.py — Flask Application

Works with BOTH:
  - MySQL (your local computer)
  - PostgreSQL (Render.com free hosting)

Just change the DATABASE_URL and it works with either one.

LOCAL (MySQL):
  DATABASE_URL=mysql+pymysql://root:ilensys@123@localhost:3306/task_manager_db

RENDER (PostgreSQL):
  DATABASE_URL=postgresql://user:pass@host/dbname  (Render gives you this)
"""

import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

# ── Create the Flask app ──
app = Flask(__name__)

# ── Settings ──
app.secret_key = os.environ.get('SECRET_KEY', 'your-super-secret-key-change-this')

# DATABASE_URL — set this as environment variable
# Locally: mysql+pymysql://root:yourpassword@localhost:3306/task_manager_db
# Render: postgresql://... (Render gives you this automatically)
database_url = os.environ.get('DATABASE_URL', 'mysql+pymysql://root:ilensys%40123@localhost:3306/task_manager_db')

# Render uses "postgres://" but SQLAlchemy needs "postgresql://"
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── Initialize Database ──
db = SQLAlchemy(app)


# ============================================================
#  DATABASE MODELS — These become tables automatically
# ============================================================

class User(db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    email         = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tasks = db.relationship('Task', backref='owner', lazy=True)


class Task(db.Model):
    __tablename__ = 'tasks'

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    content    = db.Column(db.Text, default='')
    done       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


# ============================================================
#  PAGE ROUTES
# ============================================================

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')


# ============================================================
#  API ROUTES
# ============================================================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'message': 'All fields are required.', 'success': False}), 400

    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters.', 'success': False}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already taken.', 'success': False}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already registered.', 'success': False}), 409

    try:
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'message': 'Registration successful!', 'success': True}), 201

    except Exception as e:
        db.session.rollback()
        print(f"Register error: {e}")
        return jsonify({'message': 'Server error.', 'success': False}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        session['username'] = user.username

        return jsonify({
            'message': f"Welcome back, {user.username}!",
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            }
        }), 200
    else:
        return jsonify({'message': 'Invalid username or password.', 'success': False}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully.', 'success': True}), 200


@app.route('/api/me')
def api_me():
    if 'user_id' in session:
        return jsonify({
            'success': True,
            'user': {
                'id': session['user_id'],
                'username': session['username']
            }
        }), 200
    else:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401


@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    tasks = Task.query.filter_by(user_id=session['user_id']).order_by(Task.created_at.desc()).all()

    tasks_list = []
    for task in tasks:
        tasks_list.append({
            'id': task.id,
            'title': task.title,
            'content': task.content or '',
            'done': task.done,
            'created_at': task.created_at.strftime('%Y-%m-%dT%H:%M:%S'),
            'user_id': task.user_id
        })

    return jsonify({'success': True, 'tasks': tasks_list}), 200


@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    data = request.get_json()
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title:
        return jsonify({'message': 'Task title cannot be empty.', 'success': False}), 400

    try:
        new_task = Task(title=title, content=content, user_id=session['user_id'])
        db.session.add(new_task)
        db.session.commit()
        return jsonify({'message': 'Task created!', 'success': True}), 201

    except Exception as e:
        db.session.rollback()
        print(f"Create task error: {e}")
        return jsonify({'message': 'Server error.', 'success': False}), 500


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    task = Task.query.get(task_id)

    if not task or task.user_id != session['user_id']:
        return jsonify({'message': 'Task not found.', 'success': False}), 404

    data = request.get_json()
    new_title = data.get('title', '').strip()
    new_content = data.get('content', '').strip()

    if not new_title:
        return jsonify({'message': 'Task title cannot be empty.', 'success': False}), 400

    try:
        task.title = new_title
        task.content = new_content
        db.session.commit()
        return jsonify({'message': 'Task updated!', 'success': True}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Update task error: {e}")
        return jsonify({'message': 'Server error.', 'success': False}), 500


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    task = Task.query.get(task_id)

    if not task or task.user_id != session['user_id']:
        return jsonify({'message': 'Task not found.', 'success': False}), 404

    try:
        db.session.delete(task)
        db.session.commit()
        return jsonify({'message': 'Task deleted.', 'success': True}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Delete task error: {e}")
        return jsonify({'message': 'Server error.', 'success': False}), 500


@app.route('/api/tasks/<int:task_id>/toggle', methods=['PUT'])
def api_toggle_task(task_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    task = Task.query.get(task_id)

    if not task or task.user_id != session['user_id']:
        return jsonify({'message': 'Task not found.', 'success': False}), 404

    try:
        task.done = not task.done
        db.session.commit()
        status = "done" if task.done else "not done"
        return jsonify({'message': f'Task marked as {status}.', 'success': True}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Toggle task error: {e}")
        return jsonify({'message': 'Server error.', 'success': False}), 500


# ============================================================
#  CREATE TABLES & RUN
# ============================================================
with app.app_context():
    db.create_all()  # Auto-creates tables — no need for setup_database.sql!

if __name__ == '__main__':
    app.run(debug=True, port=5000)
