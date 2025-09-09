from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from functools import wraps
import random
import string

app = Flask(__name__)
app.secret_key = 'your_strong_secret_key_here'

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'migrant_health_db'
}

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    return mysql.connector.connect(**db_config)

def login_required(role=None):
    """Decorator to protect routes that require authentication and specific roles."""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                flash("Please log in to access this page.", "error")
                return redirect(url_for('login'))
            if role and session.get('role') not in role:
                flash("You don't have permission to access this page.", "error")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

@app.route('/toggle_theme')
def toggle_theme():
    """Toggles the dark mode theme and stores the preference in the session."""
    if 'theme' not in session:
        session['theme'] = 'dark'
    else:
        session.pop('theme')
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Check for username and plain password
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user'] = user['username']
            session['user_id'] = user['id']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', "error")
    return render_template('login.html', theme=session.get('theme'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required()
def dashboard():
    role = session.get('role')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    records = []
    doctors = []

    if role in ('admin', 'doctor'):
        # For admins and doctors, fetch all records with doctor information
        cursor.execute('''
            SELECT mhr.*, u.username AS doctor_name
            FROM migrant_health_records mhr
            LEFT JOIN users u ON mhr.user_id = u.id
            ORDER BY mhr.id DESC
        ''')
        records = cursor.fetchall()
    elif role == 'patient':
        # For patients, fetch their records with the doctor's name
        cursor.execute('''
            SELECT mhr.*, u.username AS doctor_name
            FROM migrant_health_records mhr
            LEFT JOIN users u ON mhr.user_id = u.id
            WHERE mhr.user_id = %s
            ORDER BY mhr.id DESC
        ''', (session['user_id'],))
        records = cursor.fetchall()
    
    if role == 'admin':
        # Admins can also see a list of doctors
        cursor.execute("SELECT id, username FROM users WHERE role = 'doctor' ORDER BY username")
        doctors = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('dashboard.html', records=records, role=role, doctors=doctors, theme=session.get('theme'))

@app.route('/add', methods=['GET', 'POST'])
@login_required(role=['admin', 'doctor'])
def add_record():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form.get('age') or None
        gender = request.form['gender']
        origin = request.form['origin']
        health_status = request.form['health_status']
        last_checkup_date = request.form.get('last_checkup_date') or None
        notes = request.form['notes']
        
        # New field from add_record.html template
        prescription_date = request.form.get('prescription_date') or None

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Step 1: Create a new patient user automatically
            # Generate a username (e.g., first part of name + random digits)
            username_base = name.split()[0].lower() if ' ' in name else name.lower()
            random_suffix = ''.join(random.choices(string.digits, k=4))
            new_username = f"{username_base}{random_suffix}"
            
            # Use plain password instead of hashed password
            raw_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

            # Insert the new user into the database
            cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (new_username, raw_password, 'patient'))
            conn.commit()
            
            # Get the ID of the newly created user
            new_user_id = cursor.lastrowid

            # Step 2: Add the health record linked to the new user ID
            cursor.execute('''
                INSERT INTO migrant_health_records (name, age, gender, origin, health_status, last_checkup_date, notes, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (name, age, gender, origin, health_status, last_checkup_date, notes, new_user_id))
            conn.commit()
            
            flash(f"Patient record for '{name}' created successfully! A new user account has been created. Username: {new_username}, Temporary Password: {raw_password}", "success")

        except mysql.connector.Error as err:
            flash(f"Error adding record: {err.msg}", "error")
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('dashboard'))

    return render_template('add_record.html', theme=session.get('theme'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required(role=['admin', 'doctor'])
def edit_record(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age'] or None
        gender = request.form['gender']
        origin = request.form['origin']
        health_status = request.form['health_status']
        last_checkup_date = request.form['last_checkup_date'] or None
        notes = request.form['notes']
        
        cursor.execute('''
            UPDATE migrant_health_records
            SET name=%s, age=%s, gender=%s, origin=%s, health_status=%s, last_checkup_date=%s, notes=%s
            WHERE id=%s
        ''', (name, age, gender, origin, health_status, last_checkup_date, notes, id))
        conn.commit()
        
        flash("Health record updated successfully!", "success")
        
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))

    cursor.execute('SELECT * FROM migrant_health_records WHERE id = %s', (id,))
    record = cursor.fetchone()

    # Fetch all prescriptions for this record
    cursor.execute('''
        SELECT p.*, u.username AS doctor_name
        FROM prescriptions p
        JOIN users u ON p.doctor_id = u.id
        WHERE p.record_id = %s
        ORDER BY p.prescription_date DESC
    ''', (id,))
    prescriptions = cursor.fetchall()
    
    cursor.close()
    conn.close()

    if not record:
        flash("Record not found.", "error")
        return redirect(url_for('dashboard'))

    return render_template('edit_record.html', record=record, prescriptions=prescriptions, theme=session.get('theme'))

@app.route('/add_prescription/<int:record_id>', methods=['POST'])
@login_required(role=['admin', 'doctor'])
def add_prescription(record_id):
    medication = request.form['medication']
    notes = request.form['notes']
    prescription_date = request.form['prescription_date']
    doctor_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO prescriptions (record_id, doctor_id, medication, notes, prescription_date)
        VALUES (%s, %s, %s, %s, %s)
    ''', (record_id, doctor_id, medication, notes, prescription_date))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("Prescription added successfully!", "success")
    return redirect(url_for('edit_record', id=record_id))

@app.route('/delete/<int:id>', methods=['POST'])
@login_required(role=['admin'])
def delete_record(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM migrant_health_records WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Health record deleted successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/create_user', methods=['GET', 'POST'])
@login_required(role=['admin'])
def create_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Insert the plain password directly
            cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, role))
            conn.commit()
            flash(f"User '{username}' created successfully!", "success")
        except mysql.connector.Error as err:
            flash(f"Error: {err.msg}", "error")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('dashboard'))
    return render_template('create_user.html', theme=session.get('theme'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required(role=['patient'])
def change_password():
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        user_id = session.get('user_id')

        if not user_id:
            flash("User not logged in.", "error")
            return redirect(url_for('login'))

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for('change_password'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Fetch the user's current plain password
            cursor.execute('SELECT password FROM users WHERE id = %s', (user_id,))
            user = cursor.fetchone()

            if user and user['password'] == old_password:
                # Update with the new plain password
                cursor.execute('UPDATE users SET password = %s WHERE id = %s', (new_password, user_id))
                conn.commit()
                flash("Your password has been changed successfully.", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid old password.", "error")
                return redirect(url_for('change_password'))
        
        except mysql.connector.Error as err:
            flash(f"Error changing password: {err.msg}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template('change_password.html', theme=session.get('theme'))

if __name__ == '__main__':
    app.run(debug=True)