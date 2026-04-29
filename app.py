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

# ─── Twilio SMS Auto-Reply ────────────────────────────────────────────────────

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')  # Set in Render env vars

@app.route('/sms/webhook', methods=['GET', 'POST'])
def sms_webhook():
    """Twilio SMS webhook — receives texts and auto-replies with FAQ answers."""
    if request.method == 'GET':
        # Twilio validation request
        return '', 200

    from twilio.rest import Client
    from twilio.request_validator import RequestValidator

    # Validate Twilio signature in production
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        signature = request.headers.get('X-Twilio-Signature', '')
        url = request.url
        if not validator.validate(url, request.form, signature):
            return 'Forbidden', 403

    # Parse incoming SMS
    from_number = request.form.get('From', '')
    body = request.form.get('Body', '').strip().lower()

    # Find best FAQ match
    answer = find_best_faq_answer(body)

    # Send auto-reply via Twilio
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=answer,
                from_=TWILIO_PHONE_NUMBER,
                to=from_number
            )
        except Exception as e:
            app.logger.error(f'Twilio error: {e}')

    # Respond with TwiML
    from twilio.twiml import MessagingResponse
    resp = MessagingResponse()
    resp.message(answer)
    return str(resp), 200, {'Content-Type': 'text/xml'}

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
        # Bonus: query words appearing in question/answer
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
