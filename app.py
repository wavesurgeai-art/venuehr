"""
VenueHR — HRaaS Platform for Wedding Venues
Flask application entry point.
"""

import os
import uuid
import hashlib
from datetime import datetime, timedelta
from functools import wraps

import bcrypt
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, jsonify
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = '/home/team/shared/static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── Agreement Text ──────────────────────────────────────────────────────────

AGREEMENT_TEXT = """STAFF UNIFORM & PROFESSIONAL CONDUCT AGREEMENT

1. THE "BRAND STANDARD" (UNIFORM)

Our clients are paying for a "once-in-a-lifetime" experience. As a member of the service team, you are part of the decor.

THE LOOK: Solid black button-down shirt, black dress slacks, and black non-slip dress shoes.

GROOMING: Clothing must be pressed, clean, and free of lint or pet hair.

VISIBLE ITEMS: No visible headphones/AirPods, heavy fragrances, or excessive jewelry that interferes with service.

---

2. THE "INVISIBLE" SERVICE STANDARD

The best service is the kind the guests don't notice until they need something.

CELL PHONE POLICY: Cell phones are to be kept in the staff locker or your vehicle. No texting or social media use is permitted on the floor.

GUEST INTERACTION: Always yield the right of way to guests. If a guest asks a question you cannot answer, say: "I will find out for you immediately," and alert the Lead Coordinator.

CONSUMPTION: No eating, drinking (other than water in designated areas), or smoking/vaping is permitted in view of guests.

---

3. PROFESSIONAL BOUNDARIES

THE "NO-FRATERNIZATION" RULE: You are there to serve the wedding, not join it. Do not accept drinks from guests, do not join the dance floor, and do not request photos with the wedding party or high-profile guests.

ALCOHOL SERVICE: If you are a bartender, you must strictly adhere to Indiana ATC guidelines. Never "over-pour" for a guest, and never consume alcohol during or after your shift on venue property.

---

4. SOCIAL MEDIA & PRIVACY

PRIVACY: Do not post photos or videos of the wedding party, their decor, or their guests to your personal social media accounts without explicit permission from the Venue Manager.

CONFIDENTIALITY: Respect the privacy of our clients. What you hear or see at a private event stays at the event."""

# ─── Simple DB helpers (SQLite) ───────────────────────────────────────────────

import sqlite3

DB_PATH = '/home/team/shared/hraas.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        pin_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS staff (
        id TEXT PRIMARY KEY,
        venue_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL,
        hire_date TEXT,
        onboarding_token TEXT UNIQUE,
        agreement_status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS agreements (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        signed_at TEXT NOT NULL,
        ip_address TEXT,
        signature_image TEXT,
        agreement_text TEXT,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    # Create default admin if none exists (PIN: 1234)
    c.execute('SELECT id FROM admins LIMIT 1')
    if c.fetchone() is None:
        admin_id = str(uuid.uuid4())
        pin_hash = bcrypt.hashpw('1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute(
            'INSERT INTO admins (id, name, pin_hash, created_at) VALUES (?, ?, ?, ?)',
            (admin_id, 'Venue Manager', pin_hash, datetime.utcnow().isoformat())
        )
    conn.commit()
    conn.close()

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pin = request.form.get('pin', '')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, name, pin_hash FROM admins LIMIT 1')
        admin = c.fetchone()
        conn.close()
        if admin and bcrypt.checkpw(pin.encode('utf-8'), admin['pin_hash'].encode('utf-8')):
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid PIN. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as total FROM staff')
    total = c.fetchone()['total']
    c.execute("SELECT COUNT(*) as pending FROM staff WHERE agreement_status = 'pending'")
    pending = c.fetchone()['pending']
    c.execute("SELECT COUNT(*) as signed FROM staff WHERE agreement_status = 'signed'")
    signed = c.fetchone()['signed']
    conn.close()
    compliance_rate = int((signed / total * 100)) if total > 0 else 0
    return render_template('admin_dashboard.html',
                           total=total, pending=pending, signed=signed,
                           compliance_rate=compliance_rate, admin_name=session.get('admin_name'))

@app.route('/admin/staff', methods=['GET', 'POST'])
@login_required
def staff_list():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        staff_id = str(uuid.uuid4())
        token = str(uuid.uuid4())
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone', '')
        role = request.form.get('role')
        hire_date = request.form.get('hire_date', '')
        now = datetime.utcnow().isoformat()
        c.execute('''INSERT INTO staff (id, venue_id, name, email, phone, role, hire_date, onboarding_token, agreement_status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
                  (staff_id, 'default', name, email, phone, role, hire_date, token, now))
        conn.commit()
        flash(f'Staff member added. Onboarding link: {request.host_url}onboard/{token}', 'success')
        conn.close()
        return redirect(url_for('staff_list'))
    c.execute('SELECT * FROM staff ORDER BY created_at DESC')
    staff_members = c.fetchall()
    conn.close()
    return render_template('staff_list.html', staff=staff_members, admin_name=session.get('admin_name'))

@app.route('/admin/staff/<staff_id>')
@login_required
def staff_detail(staff_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE id = ?', (staff_id,))
    staff_member = c.fetchone()
    conn.close()
    if not staff_member:
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list'))
    return render_template('staff_detail.html', staff=staff_member, admin_name=session.get('admin_name'))

@app.route('/admin/staff/<staff_id>/agreement')
@login_required
def view_agreement(staff_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM agreements WHERE staff_id = ?', (staff_id,))
    agreement = c.fetchone()
    conn.close()
    if not agreement:
        flash('Agreement not found.', 'error')
        return redirect(url_for('staff_detail', staff_id=staff_id))
    return render_template('view_agreement.html', agreement=agreement, admin_name=session.get('admin_name'))

@app.route('/admin/staff/<staff_id>/resend-link', methods=['POST'])
@login_required
def resend_link(staff_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT onboarding_token FROM staff WHERE id = ?', (staff_id,))
    row = c.fetchone()
    if row:
        token = row['onboarding_token']
        flash(f'Onboarding link: {request.host_url}onboard/{token}', 'success')
    conn.close()
    return redirect(url_for('staff_list'))

@app.route('/onboard/<token>', methods=['GET', 'POST'])
def onboard(token):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE onboarding_token = ?', (token,))
    staff_member = c.fetchone()
    conn.close()
    if not staff_member:
        return "Invalid or expired onboarding link.", 404
    if staff_member['agreement_status'] == 'signed':
        return redirect(url_for('onboard_thanks', token=token))
    if request.method == 'POST':
        signature_data = request.form.get('signature_data')
        if not signature_data:
            flash('Signature is required.', 'error')
            return render_template('agreement.html', staff=staff_member, agreement_text=AGREEMENT_TEXT)
        # Decode and save signature image
        import base64
        sig_bytes = base64.b64decode(signature_data.split(',')[1])
        sig_filename = f'sig_{staff_member["id"]}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.png'
        sig_path = os.path.join(app.config['UPLOAD_FOLDER'], sig_filename)
        with open(sig_path, 'wb') as f:
            f.write(sig_bytes)
        # Save agreement
        conn = get_db()
        c = conn.cursor()
        agreement_id = str(uuid.uuid4())
        c.execute('''INSERT INTO agreements (id, staff_id, signed_at, ip_address, signature_image, agreement_text)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (agreement_id, staff_member['id'], datetime.utcnow().isoformat(),
                   request.remote_addr, sig_filename, AGREEMENT_TEXT))
        c.execute("UPDATE staff SET agreement_status = 'signed' WHERE id = ?", (staff_member['id'],))
        conn.commit()
        conn.close()
        return redirect(url_for('onboard_thanks', token=token))
    return render_template('agreement.html', staff=staff_member, agreement_text=AGREEMENT_TEXT)

@app.route('/onboard/<token>/thanks')
def onboard_thanks(token):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE onboarding_token = ?', (token,))
    staff_member = c.fetchone()
    conn.close()
    if not staff_member:
        return "Invalid link.", 404
    return render_template('onboard_thanks.html', staff=staff_member)

@app.route('/static/uploads/<filename>')
def serve_signature(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5002, debug=False)
