"""
VenueHR — HRaaS Platform for Wedding Venues
Flask application entry point.
"""

import os
import uuid
import json
import re
import hashlib
from datetime import datetime, timedelta, date
from functools import wraps

import bcrypt
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, jsonify, make_response
)
from urllib.parse import urlencode

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
    c.execute('''CREATE TABLE IF NOT EXISTS faqs (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        keywords TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS onboarding_state (
        phone TEXT PRIMARY KEY,
        step TEXT NOT NULL,
        data_json TEXT NOT NULL DEFAULT '{}',
        dob TEXT,
        assigned_role TEXT,
        updated_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS venue_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        venue_name TEXT NOT NULL DEFAULT 'Our Venue'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        name TEXT NOT NULL,
        guest_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_staffing (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        staff_id TEXT NOT NULL,
        role TEXT NOT NULL,
        confirmed INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (event_id) REFERENCES events(id),
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS availability_requests (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        phone TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        responded INTEGER NOT NULL DEFAULT 0,
        response TEXT,
        FOREIGN KEY (event_id) REFERENCES events(id)
    )''')
    # Seed default venue config
    c.execute('INSERT OR IGNORE INTO venue_config (id, venue_name) VALUES (1, ?)', ('Our Venue',))
    # Create default admin if none exists (PIN: 1234)
    c.execute('SELECT id FROM admins LIMIT 1')
    if c.fetchone() is None:
        admin_id = str(uuid.uuid4())
        pin_hash = bcrypt.hashpw('1234'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute(
            'INSERT INTO admins (id, name, pin_hash, created_at) VALUES (?, ?, ?, ?)',
            (admin_id, 'Venue Manager', pin_hash, datetime.utcnow().isoformat())
        )
    # Seed default FAQs if none exist
    c.execute('SELECT COUNT(*) as count FROM faqs')
    if c.fetchone()['count'] == 0:
        now = datetime.utcnow().isoformat()
        faqs = [
            ('Logistics', 'Where do I park?', 'Staff parking is located at the rear entrance. Please do not park in the client lot or designated guest spaces.', 'parking,park,lot,where', now),
            ('Logistics', 'Where do I check in when I arrive?', 'Check in at the Lead Coordinator station at the main entrance. Your shift supervisor will greet you there.', 'check in,arrive,where,start,shift', now),
            ('Schedule', 'What time should I arrive for my shift?', 'Please arrive 30 minutes before your scheduled start time to allow for check-in and uniform inspection.', 'time,when,arrive,shift start,schedule', now),
            ('Schedule', 'How do I request time off?', 'Submit time-off requests at least 48 hours in advance through the venue manager portal or speak directly with your Lead Coordinator.', 'time off,request,absence,off', now),
            ('Food & Beverage', 'Where are the staff meal and break areas?', 'Staff meals are served in the back kitchen area. Breaks are limited to 10 minutes in the designated break room only.', 'food,meal,break,eat,drink,staff meal', now),
            ('Food & Beverage', 'Can I eat or drink on the floor?', 'No eating, drinking (other than water in designated areas), or smoking/vaping is permitted in view of guests.', 'eat,floor,dining,breakfast,lunch,dinner', now),
            ('Safety & Emergency', 'What is the emergency exit plan?', 'Emergency exits are marked with illuminated signs. In case of evacuation, proceed calmly to the nearest exit and meet at the designated assembly point in the parking lot.', 'emergency,evacuation,fire,exit,safety', now),
            ('Safety & Emergency', 'Who do I contact in case of a medical emergency?', 'Call 911 immediately, then notify the Lead Coordinator. Do not attempt to move an injured person unless there is immediate danger.', 'medical,emergency,injury,hurt,911', now),
            ('Task Specifics', 'What are my duties as a bartender?', 'Bartenders must follow Indiana ATC guidelines at all times. Do not over-pour drinks, never consume alcohol on venue property, and ensure all bottles are accounted for at shift end.', 'bartender,duties,drinks,alcohol,bar', now),
            ('Task Specifics', 'What if a guest makes an inappropriate request?', 'Politely decline and say: "I\'m here to ensure you have a wonderful evening — let me get my Lead Coordinator to assist you." Then alert your Lead Coordinator immediately.', 'inappropriate,request,complaint,guest issue', now),
            ('Task Specifics', 'Can I use my phone during the event?', 'No. Cell phones must be kept in the staff locker or your vehicle. No texting or social media use is permitted on the floor.', 'phone,cell,text,social media,device', now),
            ('Task Specifics', 'What should I wear?', 'Solid black button-down shirt, black dress slacks, and black non-slip dress shoes. Clothing must be pressed, clean, and free of lint or pet hair. No visible headphones, heavy fragrances, or excessive jewelry.', 'wear,uniform,clothes,shoes,appearance,grooming', now),
        ]
        for faq in faqs:
            c.execute('INSERT INTO faqs (id, category, question, answer, keywords, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                      (str(uuid.uuid4()), faq[0], faq[1], faq[2], faq[3], faq[4]))
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
    # Onboarding status
    c.execute("SELECT COUNT(*) as total FROM onboarding_state")
    onboarding_total = c.fetchone()['total']
    c.execute("SELECT COUNT(*) as complete FROM onboarding_state WHERE step = 'COMPLETE'")
    onboarding_complete = c.fetchone()['complete']
    # Get recent onboarding states
    c.execute('SELECT phone, step, dob, assigned_role, updated_at FROM onboarding_state ORDER BY updated_at DESC LIMIT 10')
    onboarding_recent = c.fetchall()
    conn.close()
    compliance_rate = int((signed / total * 100)) if total > 0 else 0
    return render_template('admin_dashboard.html',
                           total=total, pending=pending, signed=signed,
                           compliance_rate=compliance_rate, admin_name=session.get('admin_name'),
                           onboarding_total=onboarding_total, onboarding_complete=onboarding_complete,
                           onboarding_recent=onboarding_recent)

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

# ─── FAQ Routes ────────────────────────────────────────────────────────────────

@app.route('/faq')
def faq_page():
    """Public FAQ page for staff."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT DISTINCT category FROM faqs ORDER BY category')
    categories = [row['category'] for row in c.fetchall()]
    c.execute('SELECT * FROM faqs ORDER BY category, question')
    faqs = c.fetchall()
    conn.close()
    return render_template('faq_page.html', faqs=faqs, categories=categories)

@app.route('/faq/search')
def faq_search():
    """Search FAQs by keyword."""
    q = request.args.get('q', '').lower().strip()
    conn = get_db()
    c = conn.cursor()
    if q:
        c.execute("SELECT * FROM faqs ORDER BY category, question")
        all_faqs = c.fetchall()
        # Score each FAQ by keyword match
        scored = []
        for faq in all_faqs:
            keywords = faq['keywords'].lower().split(',')
            score = sum(1 for kw in keywords if kw.strip() in q) + sum(1 for kw in keywords if q in kw.strip())
            if score > 0:
                scored.append((score, faq))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [f for _, f in scored[:5]]
    else:
        results = []
    conn.close()
    return render_template('faq_search.html', results=results, query=q)

@app.route('/admin/faqs')
@login_required
def admin_faqs():
    """Admin FAQ management page."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT DISTINCT category FROM faqs ORDER BY category')
    categories = [row['category'] for row in c.fetchall()]
    c.execute('SELECT * FROM faqs ORDER BY category, question')
    faqs = c.fetchall()
    conn.close()
    return render_template('admin_faqs.html', faqs=faqs, categories=categories, admin_name=session.get('admin_name'))

@app.route('/admin/faqs/add', methods=['POST'])
@login_required
def admin_faq_add():
    """Add a new FAQ."""
    conn = get_db()
    c = conn.cursor()
    faq_id = str(uuid.uuid4())
    c.execute('INSERT INTO faqs (id, category, question, answer, keywords, created_at) VALUES (?, ?, ?, ?, ?, ?)',
              (faq_id, request.form.get('category'), request.form.get('question'),
               request.form.get('answer'), request.form.get('keywords'), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    flash('FAQ added successfully.', 'success')
    return redirect(url_for('admin_faqs'))

@app.route('/admin/faqs/<faq_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_faq_edit(faq_id):
    """Edit an existing FAQ."""
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        c.execute('UPDATE faqs SET category=?, question=?, answer=?, keywords=? WHERE id=?',
                  (request.form.get('category'), request.form.get('question'),
                   request.form.get('answer'), request.form.get('keywords'), faq_id))
        conn.commit()
        conn.close()
        flash('FAQ updated.', 'success')
        return redirect(url_for('admin_faqs'))
    c.execute('SELECT * FROM faqs WHERE id = ?', (faq_id,))
    faq = c.fetchone()
    c.execute('SELECT DISTINCT category FROM faqs ORDER BY category')
    categories = [row['category'] for row in c.fetchall()]
    conn.close()
    if not faq:
        flash('FAQ not found.', 'error')
        return redirect(url_for('admin_faqs'))
    return render_template('admin_faq_edit.html', faq=faq, categories=categories, admin_name=session.get('admin_name'))

@app.route('/admin/faqs/<faq_id>/delete', methods=['POST'])
@login_required
def admin_faq_delete(faq_id):
    """Delete an FAQ."""
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM faqs WHERE id = ?', (faq_id,))
    conn.commit()
    conn.close()
    flash('FAQ deleted.', 'success')
    return redirect(url_for('admin_faqs'))

# ─── Staffing Matrix Routes ───────────────────────────────────────────────────

@app.route('/admin/staffing', methods=['GET', 'POST'])
@login_required
def staffing_matrix():
    """Staffing calculator and event staffing management."""
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_event':
            event_id = str(uuid.uuid4())
            c.execute('''INSERT INTO events (id, date, name, guest_count, created_at)
                         VALUES (?, ?, ?, ?, ?)''',
                     (event_id, request.form.get('date'), request.form.get('name'),
                      int(request.form.get('guest_count', 0)), datetime.utcnow().isoformat()))
            conn.commit()
            flash(f'Event created.', 'success')
        elif action == 'assign_staff':
            event_id = request.form.get('event_id')
            staff_id = request.form.get('staff_id')
            role = request.form.get('role')
            c.execute('SELECT id FROM event_staffing WHERE event_id=? AND staff_id=?', (event_id, staff_id))
            if not c.fetchone():
                c.execute('INSERT INTO event_staffing (id, event_id, staff_id, role, confirmed) VALUES (?, ?, ?, ?, 0)',
                          (str(uuid.uuid4()), event_id, staff_id, role))
                conn.commit()
                flash('Staff assigned.', 'success')
        elif action == 'confirm_staff':
            staffing_id = request.form.get('staffing_id')
            c.execute('UPDATE event_staffing SET confirmed=1 WHERE id=?', (staffing_id,))
            conn.commit()
            flash('Staff confirmed.', 'success')
        elif action == 'remove_staff':
            staffing_id = request.form.get('staffing_id')
            c.execute('DELETE FROM event_staffing WHERE id=?', (staffing_id,))
            conn.commit()
            flash('Staff removed.', 'success')
        conn.close()
        return redirect(url_for('staffing_matrix'))

    # Load events
    c.execute('SELECT * FROM events ORDER BY date DESC')
    events = c.fetchall()

    # Load staff pool
    c.execute('SELECT * FROM staff ORDER BY name')
    all_staff = c.fetchall()

    conn.close()
    return render_template('admin_staffing.html', events=events, all_staff=all_staff, admin_name=session.get('admin_name'))

@app.route('/admin/staffing/<event_id>')
@login_required
def staffing_detail(event_id):
    """Staffing plan for a specific event."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=?', (event_id,))
    event = c.fetchone()
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('staffing_matrix'))
    c.execute('''SELECT es.*, s.name as staff_name, s.phone as staff_phone
                 FROM event_staffing es JOIN staff s ON es.staff_id=s.id
                 WHERE es.event_id=?''', (event_id,))
    assignments = c.fetchall()
    c.execute('SELECT * FROM staff ORDER BY name')
    all_staff = c.fetchall()
    conn.close()

    guest_count = event['guest_count']
    # Staffing ratios
    required = {
        'Server': max(1, guest_count // 20),
        'Bartender': max(1, guest_count // 50),
        'Event Lead': 1 if guest_count > 50 else 0,
        'Security/Parking': max(1, guest_count // 100),
    }
    # Compute gaps
    assigned_by_role = {}
    for a in assignments:
        assigned_by_role[a['role']] = assigned_by_role.get(a['role'], 0) + 1
    gaps = []
    for role, needed in required.items():
        if needed > 0:
            have = assigned_by_role.get(role, 0)
            if have < needed:
                gaps.append({'role': role, 'needed': needed, 'have': have, 'short': needed - have})

    return render_template('admin_staffing_detail.html', event=event, assignments=assignments,
                           all_staff=all_staff, required=required, gaps=gaps, admin_name=session.get('admin_name'))

@app.route('/admin/staffing/<event_id>/broadcast', methods=['POST'])
@login_required
def staffing_broadcast(event_id):
    """Send availability SMS to all unassigned staff."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=?', (event_id,))
    event = c.fetchone()
    if not event:
        flash('Event not found.', 'error')
        conn.close()
        return redirect(url_for('staffing_matrix'))

    c.execute('''SELECT s.* FROM staff s
                 WHERE s.id NOT IN (SELECT staff_id FROM event_staffing WHERE event_id=?)
                 ORDER BY s.name''', (event_id,))
    unassigned = c.fetchall()
    conn.close()

    # Send SMS to each
    venue_name = get_venue_name()
    msg = (f"Hi! {venue_name} needs staff for an upcoming event.\n\n"
           f"Event: {event['name']}\n"
           f"Date: {event['date']}\n"
           f"Guests: {event['guest_count']}\n\n"
           f"Reply CONFIRM if you're available, or DECLINE if not.")

    sent = 0
    for staff in unassigned:
        if staff['phone']:
            send_sms_alert(staff['phone'], msg)
            sent += 1

    flash(f'Availability request sent to {sent} staff members.', 'success')
    return redirect(url_for('staffing_detail', event_id=event_id))

@app.route('/admin/events', methods=['GET', 'POST'])
@login_required
def events_list():
    """List and manage events."""
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        event_id = str(uuid.uuid4())
        c.execute('INSERT INTO events (id, date, name, guest_count, created_at) VALUES (?, ?, ?, ?, ?)',
                  (event_id, request.form.get('date'), request.form.get('name'),
                   int(request.form.get('guest_count', 0)), datetime.utcnow().isoformat()))
        conn.commit()
        flash('Event created.', 'success')
    c.execute('SELECT * FROM events ORDER BY date DESC')
    events = c.fetchall()
    conn.close()
    return render_template('admin_events.html', events=events, admin_name=session.get('admin_name'))

def send_sms_alert(phone, message):
    """Send an outbound SMS (uses Twilio if configured)."""
    if not phone:
        return
    try:
        from twilio.rest import Client
        from twilio.twiml.messaging_response import MessagingResponse
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.messages.create(body=message, from_=TWILIO_PHONE_NUMBER, to=phone)
    except Exception:
        app.logger.warning(f'Could not send SMS to {phone}')



TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')

@app.route('/sms/webhook', methods=['GET', 'POST'])
def sms_webhook():
    """Twilio SMS webhook — routes to onboarding bot or FAQ auto-reply."""
    try:
        if request.method == 'GET':
            return '', 200

        from twilio.request_validator import RequestValidator

        # Validate Twilio signature (skip if DISABLE_TWILIO_VALIDATION=1)
        skip_validation = os.environ.get('DISABLE_TWILIO_VALIDATION', '').lower() == '1'
        if not skip_validation and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            signature = request.headers.get('X-Twilio-Signature', '')
            url = request.url
            if not validator.validate(url, request.form, signature):
                return 'Forbidden', 403

        from_number = request.form.get('From', '')
        body = request.form.get('Body', '').strip()
        upper_body = body.upper()

        # Route: onboarding bot vs. FAQ lookup
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT step, data_json, dob, assigned_role FROM onboarding_state WHERE phone = ?', (from_number,))
        row = c.fetchone()
        conn.close()

        # If user is in onboarding flow, check global commands first
        if row and row['step'] != 'COMPLETE':
            # Global commands even while onboarding
            if upper_body in ('HELP', 'FAQ', '?'):
                answer, next_step = HELP_TEXT, None
            elif upper_body == 'STATUS':
                answer, next_step = get_onboarding_status(from_number)
            elif upper_body == 'QUIT':
                answer, next_step = quit_onboarding(from_number)
            else:
                answer, next_step = handle_onboarding_state(from_number, body, row)
        elif upper_body == 'START' or upper_body.startswith('START '):
            answer, next_step = start_onboarding(from_number, body)
        elif upper_body in ('HELP', 'FAQ', '?'):
            answer, next_step = HELP_TEXT, None
        elif upper_body == 'STATUS':
            answer, next_step = get_onboarding_status(from_number)
        elif upper_body == 'QUIT':
            answer, next_step = quit_onboarding(from_number)
        else:
            # Hand off to FAQ bot
            answer = find_best_faq_answer(body)
            next_step = None

        # Persist state if step changed
        if next_step is not None:
            save_onboarding_state(from_number, next_step, {})

        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        resp.message(answer)
        return str(resp), 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        app.logger.error(f'SMS webhook error: {e}')
        return f'SMS error: {e}', 500


# ─── Onboarding State Machine ───────────────────────────────────────────────────

STAGES = ['WELCOME', 'START_RECEIVED', 'DOB_VERIFIED', 'BASIC_INFO', 'TAX_INFO', 'COMPLIANCE_PHOTOS', 'PAYROLL', 'COMPLETE']

HELP_TEXT = ("Commands:\n"
             "START [DOB] - Begin onboarding (e.g. START 01/15/2000)\n"
             "STATUS - See your onboarding progress\n"
             "BACK - Go to previous step\n"
             "QUIT - Exit and save progress\n"
             "For other questions, I'll try to find an FAQ answer!")

def get_venue_name() -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT venue_name FROM venue_config WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return row['venue_name'] if row else 'Our Venue'

def parse_dob(dob_str: str):
    """Parse MM/DD/YYYY or MM-DD-YYYY date of birth. Returns date or None."""
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', dob_str.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None

def age_from_dob(dob: date) -> int:
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return age

def determine_role(age: int) -> str:
    if age >= 21:
        return 'Bartender/Lead'
    elif age >= 18:
        return 'Server'
    return 'Under 18'

def start_onboarding(phone: str, body: str):
    """Initiate onboarding: parse DOB, determine role, send welcome + first question."""
    dob_str = re.sub(r'^START\s*', '', body.strip(), flags=re.IGNORECASE).strip()
    dob = parse_dob(dob_str) if dob_str else None

    if not dob:
        msg = ("To get started, I need your Date of Birth.\n\n"
               "Please reply with START followed by your DOB in MM/DD/YYYY format.\n"
               "For example: START 01/15/2000")
        return msg, 'START_RECEIVED'

    age = age_from_dob(dob)
    if age < 18:
        return ("I'm sorry, but you must be at least 18 years old to work at our venue. "
                "Please contact the venue manager directly if you believe this is an error."), None

    role = determine_role(age)
    venue_name = get_venue_name()

    # Save state — move directly to BASIC_INFO
    data = json.dumps({'role': role})
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO onboarding_state (phone, step, data_json, dob, assigned_role, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
             (phone, 'BASIC_INFO', data, dob.strftime('%m/%d/%Y'), role, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    welcome = (f"Hi! Congratulations on joining the team at {venue_name}. "
               f"I am your AI Onboarding Assistant. My job is to get you set up in our system "
               f"as quickly as possible so you can get on the schedule and get paid.\n\n"
               f"To stay compliant with Indiana labor laws and venue safety standards, "
               f"I'm going to guide you through a few quick steps. "
               f"Here is what we need to tackle today:\n"
               f"Basic Info, Tax Documents, Compliance, Payroll.\n\n"
               f"This usually takes about 5-10 minutes. You can stop and start at any time — "
               f"I'll remember where we left off.\n\n"
               f"I've determined you'll be joining as a: {role}\n\n"
               f"Let's get started!\n\n"
               f"Reply with your Full Legal Name (as it appears on your ID):")

    return welcome, 'BASIC_INFO'

def handle_onboarding_state(phone: str, body: str, row):
    """Process the next message in the onboarding state machine."""
    step = row['step']
    data = json.loads(row['data_json']) if row['data_json'] else {}
    dob = row['dob']
    assigned_role = row['assigned_role']
    upper_body = body.upper()

    # Global commands
    if upper_body == 'QUIT':
        return quit_onboarding(phone)

    if upper_body == 'STATUS':
        return get_onboarding_status(phone)

    if upper_body == 'BACK':
        return handle_back(phone, step, data)

    # Step-specific handlers
    if step == 'START_RECEIVED':
        return start_onboarding(phone, body)

    elif step == 'BASIC_INFO':
        return collect_basic_info(phone, body, data, assigned_role, dob)

    elif step == 'TAX_INFO':
        return collect_tax_info(phone, body, data, assigned_role, dob)

    elif step == 'COMPLIANCE_PHOTOS':
        return collect_compliance_photos(phone, body, data, assigned_role, dob)

    elif step == 'PAYROLL':
        return collect_payroll(phone, body, data, assigned_role, dob)

    elif step == 'COMPLETE':
        return ("You've already completed your onboarding! If you have questions, "
                "reply HELP or contact your Lead Coordinator."), None

    return ("I'm not sure what step you're on. Reply STATUS to see your progress, "
            "or START to begin again."), None

def collect_basic_info(phone, body, data, role, dob):
    data['name'] = body.strip()
    msg = (f"Got it, {data['name']}!\n\n"
           f"Reply with your Email Address:")
    data['step'] = 'TAX_INFO'
    save_onboarding_state(phone, 'TAX_INFO', data)
    return msg, 'TAX_INFO'

def collect_tax_info(phone, body, data, role, dob):
    email = body.strip()
    if '@' not in email or '.' not in email:
        return ("That doesn't look like a valid email. Please reply with a valid email address:"), 'TAX_INFO'
    data['email'] = email
    data['step'] = 'COMPLIANCE_PHOTOS'
    save_onboarding_state(phone, 'COMPLIANCE_PHOTOS', data)
    return ("Great!\n\n"
            "Next, Compliance Photos.\n\n"
            "Please reply with a photo of yourself in your work uniform "
            "(solid black button-down shirt, black dress slacks, black non-slip shoes). "
            "This will be used for your staff ID badge."), 'COMPLIANCE_PHOTOS'

def collect_compliance_photos(phone, body, data, role, dob):
    # Body contains media URL if photo was sent, or a text response
    num_photos = data.get('photo_count', 0) + 1
    data['photo_count'] = num_photos
    data['step'] = 'PAYROLL'
    save_onboarding_state(phone, 'PAYROLL', data)
    return ("Thanks! Your compliance photo has been received.\n\n"
            "Finally, Payroll.\n\n"
            "Do you have Direct Deposit set up?\n\n"
            "Reply YES if you want to provide bank info now, or REPLY LATER to skip."), 'PAYROLL'

def collect_payroll(phone, body, data, role, dob):
    upper = body.strip().upper()
    if upper in ('YES', 'Y'):
        data['payroll'] = 'pending_bank_info'
        save_onboarding_state(phone, 'PAYROLL', data)
        return ("Great! Please provide your bank info:\n\n"
                "Bank Name:"), 'PAYROLL'
    elif upper in ('LATER', 'NO', 'N', 'SKIP'):
        data['payroll'] = 'later'
        return finish_onboarding(phone, data)
    else:
        return ("Please reply YES to provide bank info now, or LATER to skip:"), 'PAYROLL'

def handle_back(phone, step, data):
    """Go back one step in the onboarding flow."""
    step_order = ['WELCOME', 'START_RECEIVED', 'DOB_VERIFIED', 'BASIC_INFO', 'TAX_INFO', 'COMPLIANCE_PHOTOS', 'PAYROLL', 'COMPLETE']
    try:
        idx = step_order.index(step)
    except ValueError:
        return ("I'm not sure what step you're on. Reply STATUS to check your progress."), None

    if idx <= 1:
        return ("You're at the beginning! Reply START to begin onboarding."), step

    prev_step = step_order[idx - 1]
    # Reset data for the previous step
    save_onboarding_state(phone, prev_step, {})
    return (f"No problem! Let's go back.\n\n"
            f"(Returned to: {prev_step.replace('_', ' ').title()})\n\n"
            f"Reply BACK again to go further back, or continue when ready."), prev_step

def get_onboarding_status(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT step, data_json, dob, assigned_role FROM onboarding_state WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()

    if not row:
        return ("You haven't started onboarding yet. Reply START to begin!"), None

    step = row['step']
    data = json.loads(row['data_json']) if row['data_json'] else {}
    role = row['assigned_role'] or 'Unknown'

    if step == 'COMPLETE':
        return (f"Onboarding Status: COMPLETE ✓\n\n"
                f"Your onboarding is all done! Welcome to the team.\n\n"
                f"Reply HELP if you need assistance."), None

    steps_display = {
        'WELCOME': 'Welcome',
        'START_RECEIVED': 'Awaiting DOB',
        'DOB_VERIFIED': 'DOB Verified',
        'BASIC_INFO': 'Basic Info',
        'TAX_INFO': 'Tax Info',
        'COMPLIANCE_PHOTOS': 'Compliance Photos',
        'PAYROLL': 'Payroll',
    }

    status = f"Step: {steps_display.get(step, step)}\nRole: {role}\n\n"
    remaining = {
        'DOB_VERIFIED': 'Basic Info, Tax Documents, Compliance, Payroll',
        'BASIC_INFO': 'Tax Documents, Compliance, Payroll',
        'TAX_INFO': 'Compliance, Payroll',
        'COMPLIANCE_PHOTOS': 'Payroll',
        'PAYROLL': 'Finish up!',
    }
    if step in remaining:
        status += f"Remaining: {remaining[step]}\n\n"
    status += "Reply BACK to go to previous step, or QUIT to save and exit."

    return status, None

def quit_onboarding(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT step FROM onboarding_state WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()
    if row and row['step'] != 'COMPLETE':
        return ("Your progress has been saved! Reply STATUS to pick up where you left off, "
                "or START to begin again."), None
    return ("You've quit onboarding. Reply START when you're ready to begin again."), None

def finish_onboarding(phone, data):
    """Complete onboarding — save final data and send completion message."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE onboarding_state SET step = 'COMPLETE', updated_at = ? WHERE phone = ?''',
              (datetime.utcnow().isoformat(), phone))
    conn.commit()
    conn.close()
    name = data.get('name', 'there')
    return (f"Congratulations, {name}! 🎉\n\n"
            f"You've completed your onboarding!\n\n"
            f"What's next?\n"
            f"1. Check your email for a link to sign your Staff Agreement\n"
            f"2. Complete the uniform compliance form\n"
            f"3. You're ready to be added to the schedule!\n\n"
            f"Questions? Reply HELP or contact your Lead Coordinator.\n\n"
            f"Welcome to the team!"), 'COMPLETE'

def save_onboarding_state(phone: str, step: str, data: dict):
    """Persist onboarding state to DB."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT data_json, dob, assigned_role FROM onboarding_state WHERE phone = ?', (phone,))
    row = c.fetchone()
    dob = row['dob'] if row else None
    assigned_role = row['assigned_role'] if row else None
    if step == 'DOB_VERIFIED' and isinstance(data, dict) and 'role' in data:
        assigned_role = data['role']
    merged = dict(json.loads(row['data_json'])) if row and row['data_json'] and row['data_json'] not in ('', '{}') else {}
    merged.update(data)
    c.execute('''INSERT OR REPLACE INTO onboarding_state (phone, step, data_json, dob, assigned_role, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
             (phone, step, json.dumps(merged), dob, assigned_role, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def find_best_faq_answer(query: str) -> str:
    """Search FAQ database for best matching answer."""
    if not query:
        return ("Hi! Thank you for reaching out. For questions about your shift, "
                "uniform, parking, or any other topic, please visit our FAQ page: "
                f"{request.host_url}faq\n\n"
                "For immediate assistance, contact your Lead Coordinator.")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM faqs')
    all_faqs = c.fetchall()
    conn.close()

    query_words = set(query.lower().split())
    best_score = 0
    best_answer = None

    for faq in all_faqs:
        keywords = [kw.strip().lower() for kw in faq['keywords'].split(',')]
        score = 0
        for word in query_words:
            for kw in keywords:
                if word == kw:
                    score += 3
                elif word in kw or kw in word:
                    score += 1
        full_text = (faq['question'] + ' ' + faq['answer']).lower()
        for word in query_words:
            if word in full_text:
                score += 0.5
        if score > best_score:
            best_score = score
            best_answer = faq['answer']

    if best_score > 0:
        header = ("Hi! Here's what I found in our FAQ:\n\n")
        return header + best_answer + (
            f"\n\nFor more questions, visit: {request.host_url}faq\n"
            "For immediate help, contact your Lead Coordinator.")

    return ("I'm not sure I understood that. For help, please contact your Lead Coordinator "
            f"or visit our FAQ page: {request.host_url}faq")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
