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

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

import logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = '/home/team/shared/static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

# ─── Email (Zoho SMTP) ───────────────────────────────────────────────────────────
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM = os.environ.get('MAIL_USERNAME', 'wavesurgeai@gmail.com')

def send_email(to, subject, body):
    """Send email via Resend API (HTTPS) — works on Render (port 443 only)."""
    import urllib.request, json

    resend_api_key = os.environ.get('RESEND_API_KEY', '')
    if not resend_api_key:
        app.logger.warning('RESEND_API_KEY env var not set')
        return False

    # From address — must be a verified domain in Resend, or a free sandbox address
    from_address = os.environ.get('RESEND_FROM_EMAIL', 'VenueHR <onboarding@resend.dev>')

    payload = json.dumps({
        'from': from_address,
        'to': [to],
        'subject': subject,
        'text': body
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=payload,
        headers={
            'Authorization': f'Bearer {resend_api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'VenueHR/1.0'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode() or '{}')
            app.logger.info(f"Email sent to {to}: {subject} (Resend id={result.get('id', 'n/a')})")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:200]
        app.logger.error(f'Resend API error for {to}: HTTP {e.code} — {error_body}')
        return False
    except Exception as e:
        app.logger.error(f'Resend failed for {to}: {e}')
        return False

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


# ─── Onboarding Document Texts ────────────────────────────────────────────────

HANDBOOK_TEXT = """EMPLOYEE HANDBOOK ACKNOWLEDGMENT

This Handbook summarizes the standards every team member is expected to uphold. Please review each section before acknowledging.

1. UNIFORM & GROOMING (THE BRAND STANDARD)
You are part of the decor. Solid black button-down shirt, black dress slacks, and black non-slip shoes — clean, pressed, and free of lint. Keep jewelry minimal and avoid heavy fragrances. No visible smartwatches or earbuds during service.

2. SERVICE EXCELLENCE (THE INVISIBLE STANDARD)
Strive for seamless, unobtrusive service. Guests always have the right of way. If you do not know an answer, say "I will find out for you immediately," and follow through. Keep personal conversations away from guest areas, and the floor clear of personal items.

3. PROFESSIONAL BOUNDARIES & ALCOHOL
You are there to serve the wedding, not to join it. No fraternizing, dancing, drinking, or personal photography during events. No staff member may consume alcohol while on the clock or on venue property. Bartenders must follow all Indiana ATC regulations; over-serving or unauthorized heavy pours are grounds for immediate dismissal.

4. PRIVACY & SOCIAL MEDIA
Event details, guest lists, and overheard conversations are strictly confidential. Do not capture or share any event content — including behind-the-scenes shots — on personal accounts. All official social media is handled by the Venue Manager.

By acknowledging below, you confirm you have received, read, and understand this Handbook and agree to follow its policies."""

DIRECT_DEPOSIT_TEXT = """DIRECT DEPOSIT AUTHORIZATION

To receive your pay by direct deposit, provide your bank account details below. Your pay will be deposited electronically each pay period to the account you designate.

• Double-check your routing and account numbers — incorrect information can delay your pay.
• Your routing number is the 9-digit number on the bottom-left of a check.
• You may change or cancel this authorization at any time by notifying the Venue Manager in writing.

This authorization remains in effect until you provide written notice of a change. By signing, you authorize the venue and its payroll provider to deposit your wages to the account below."""

W4_TEXT = """FORM W-4 — EMPLOYEE'S WITHHOLDING CERTIFICATE (Federal)

Complete the fields below so the correct amount of federal income tax is withheld from your pay. This is a simplified representation of the IRS Form W-4 for onboarding; your legal name and Social Security number are captured on the official signed IRS form and are not stored in this system.

• Step 1c — Filing status determines your standard withholding.
• Step 2 — Check the box only if you hold more than one job at a time, or you are married filing jointly and your spouse also works.
• Step 3 — Enter the total dollar amount for dependents you wish to claim.
• Step 4 — Enter any other income, extra deductions, or additional per-paycheck withholding.
• Exemption — Check only if you meet BOTH conditions for exemption from withholding.

Under penalties of perjury, you declare that the information you provide is true, correct, and complete."""

I9_TEXT = """FORM I-9 — EMPLOYMENT ELIGIBILITY VERIFICATION

Federal law requires every employee to attest to their identity and authorization to work in the United States. This step records your attestation and the documents you will present; physical document examination is completed in person on or before your first day, as required by U.S. Citizenship and Immigration Services.

• Select the citizenship / immigration status that applies to you.
• Select the document(s) you will present — either one document from List A, or one from List B plus one from List C.
• Bring the actual documents (unexpired and original) to your first shift for verification.

You attest, under penalty of perjury, that the information you provide is true and correct, and you are aware that federal law provides for imprisonment and/or fines for false statements or use of false documents."""

EMERGENCY_TEXT = """EMERGENCY CONTACT INFORMATION

In the event of an emergency during a shift, who should we contact on your behalf? Please provide someone who is typically reachable by phone. You can update this information at any time by contacting the Venue Manager."""


# ─── Onboarding Wizard Step Definitions ───────────────────────────────────────
# Each step renders through templates/onboard_step.html. Order = completion order.
ONBOARDING_STEPS = [
    {
        'key': 'agreement',
        'title': 'Staff Uniform & Professional Conduct Agreement',
        'subtitle': 'Please read carefully and sign below',
        'body': AGREEMENT_TEXT,
        'ack': 'I have read and understand the Staff Uniform & Professional Conduct Agreement above, and I agree to comply with all terms.',
        'signature': True,
        'fields': [],
    },
    {
        'key': 'handbook',
        'title': 'Employee Handbook Acknowledgment',
        'subtitle': 'Confirm you have reviewed the staff handbook',
        'body': HANDBOOK_TEXT,
        'ack': 'I acknowledge that I have received, read, and understand the Employee Handbook and agree to follow its policies.',
        'signature': True,
        'fields': [],
    },
    {
        'key': 'direct_deposit',
        'title': 'Direct Deposit Authorization',
        'subtitle': 'Set up electronic payroll deposit',
        'body': DIRECT_DEPOSIT_TEXT,
        'ack': 'I authorize direct deposit of my pay to the account below and confirm the information is accurate.',
        'signature': True,
        'fields': [
            {'name': 'account_holder', 'label': 'Name on account', 'type': 'text', 'required': True},
            {'name': 'bank_name', 'label': 'Bank name', 'type': 'text', 'required': True},
            {'name': 'account_type', 'label': 'Account type', 'type': 'select', 'options': ['Checking', 'Savings'], 'required': True},
            {'name': 'routing_number', 'label': 'Routing number (9 digits)', 'type': 'text', 'required': True, 'placeholder': '123456789'},
            {'name': 'account_number', 'label': 'Account number', 'type': 'text', 'required': True},
        ],
    },
    {
        'key': 'w4',
        'title': 'Form W-4 — Federal Tax Withholding',
        'subtitle': 'Tell us how to withhold federal income tax',
        'body': W4_TEXT,
        'ack': 'Under penalties of perjury, I declare that this withholding information is true, correct, and complete.',
        'signature': True,
        'fields': [
            {'name': 'filing_status', 'label': 'Filing status (Step 1c)', 'type': 'select',
             'options': ['Single or Married filing separately',
                         'Married filing jointly or Qualifying surviving spouse',
                         'Head of household'], 'required': True},
            {'name': 'multiple_jobs', 'label': 'Multiple jobs, or spouse also works (Step 2)', 'type': 'checkbox', 'required': False},
            {'name': 'dependents_amount', 'label': 'Claim dependents — total $ (Step 3)', 'type': 'text', 'required': False, 'placeholder': '0.00'},
            {'name': 'other_income', 'label': 'Other income, not from jobs (Step 4a)', 'type': 'text', 'required': False, 'placeholder': '0.00'},
            {'name': 'deductions', 'label': 'Deductions beyond standard (Step 4b)', 'type': 'text', 'required': False, 'placeholder': '0.00'},
            {'name': 'extra_withholding', 'label': 'Extra withholding per paycheck (Step 4c)', 'type': 'text', 'required': False, 'placeholder': '0.00'},
            {'name': 'exempt', 'label': 'I claim exemption from withholding for this year', 'type': 'checkbox', 'required': False},
        ],
    },
    {
        'key': 'i9',
        'title': 'Form I-9 — Employment Eligibility',
        'subtitle': 'Attest to your eligibility to work in the U.S.',
        'body': I9_TEXT,
        'ack': 'I attest, under penalty of perjury, that the information above is true and correct, and I am aware that federal law provides penalties for false statements.',
        'signature': True,
        'fields': [
            {'name': 'citizenship_status', 'label': 'Citizenship / immigration status', 'type': 'select',
             'options': ['A citizen of the United States',
                         'A noncitizen national of the United States',
                         'A lawful permanent resident',
                         'An alien authorized to work'], 'required': True},
            {'name': 'id_documents', 'label': 'Documents you will present', 'type': 'select',
             'options': ['List A — U.S. Passport or Passport Card',
                         'List A — Permanent Resident Card (Green Card)',
                         'List A — Employment Authorization Document',
                         "List B + C — Driver's License + Social Security Card",
                         'List B + C — State ID + Birth Certificate'], 'required': True},
        ],
    },
    {
        'key': 'emergency_contact',
        'title': 'Emergency Contact',
        'subtitle': 'Who should we call in an emergency?',
        'body': EMERGENCY_TEXT,
        'ack': 'I confirm the emergency contact information above is accurate.',
        'signature': False,
        'fields': [
            {'name': 'contact_name', 'label': 'Emergency contact name', 'type': 'text', 'required': True},
            {'name': 'contact_phone', 'label': 'Emergency contact phone', 'type': 'tel', 'required': True},
            {'name': 'relationship', 'label': 'Relationship to you', 'type': 'text', 'required': True},
        ],
    },
    {
        'key': 'license',
        'title': 'Licenses & Certifications',
        'subtitle': 'Add any work-related license or certification (optional)',
        'body': (
            "Use this step to record any work-related license or certification you hold. "
            "Examples: an Indiana Alcohol & Tobacco Commission (ATC) Employee Permit if you serve or sell alcohol, "
            "alcohol server training (TIPS, Learn2Serve, or the ATC's free course), a food handler card, or a security guard license.\n\n"
            "In Indiana, anyone who serves or sells alcohol \u2014 and, as of July 2025, door security who check IDs \u2014 must "
            "complete certified server training and hold an ATC Employee Permit within 120 days of hire. Unrestricted permits "
            "(age 21+) are valid three years; restricted permits (age 18\u201320) about two years.\n\n"
            "This information is optional. If you have nothing to add, leave the fields blank and continue. VenueHR records "
            "what you enter for your venue's reference \u2014 it does not verify or issue any license."
        ),
        'ack': ('I have reviewed the information above and confirm it is accurate and complete. '
                'If I have no license or certification to add, I am intentionally leaving the fields blank.'),
        'signature': False,
        'fields': [
            {'name': 'license_type', 'label': 'License / certification type', 'type': 'select',
             'options': ['Indiana ATC Employee Permit (Unrestricted, 21+)',
                         'Indiana ATC Restricted Employee Permit (18-20)',
                         'Alcohol Server Training (TIPS / Learn2Serve / ATC)',
                         'Food Handler Certification',
                         'Security Guard License',
                         'Other'], 'required': False},
            {'name': 'license_number', 'label': 'License / permit / certificate number', 'type': 'text', 'required': False},
            {'name': 'license_state', 'label': 'Issuing state or authority', 'type': 'text', 'required': False,
             'placeholder': 'e.g. IN - Alcohol & Tobacco Commission'},
            {'name': 'license_expires', 'label': 'Expiration date (if any)', 'type': 'date', 'required': False},
        ],
    },
]

ONBOARDING_STEP_KEYS = [s['key'] for s in ONBOARDING_STEPS]

# ─── DB helpers (PostgreSQL via psycopg2, SQLite-compatible shim) ──────────────

import psycopg2
import psycopg2.extras
import psycopg2.extensions

DATABASE_URL = os.environ.get('DATABASE_URL')


def _translate(sql):
    """Translate this app's SQLite dialect into PostgreSQL at execute() time.

    1. '?' positional placeholders -> '%s'. Every '?' in this codebase's query
       strings is a bind placeholder; the only '?' chars in literal text live in
       parameter VALUES, never in the SQL string, so a blanket replace is safe.
    2. 'INSERT OR IGNORE' -> 'INSERT ... ON CONFLICT DO NOTHING' (matches
       SQLite's ignore-on-any-uniqueness-conflict semantics).
    """
    sql = sql.replace('?', '%s')
    head = sql.lstrip()
    if head[:21].upper() == 'INSERT OR IGNORE INTO':
        idx = sql.upper().find('INSERT OR IGNORE INTO')
        sql = sql[:idx] + 'INSERT INTO' + sql[idx + len('INSERT OR IGNORE INTO'):]
        sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return sql


class _ShimCursor(psycopg2.extras.DictCursor):
    """Cursor that translates SQLite SQL and yields dict-like rows.

    DictRow supports both integer and string indexing like sqlite3.Row, so the
    existing ~125 execute()/fetchone()['col'] call sites are unchanged.
    """
    def execute(self, query, vars=None):
        return super().execute(_translate(query), vars)


class _ShimConnection(psycopg2.extensions.connection):
    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', _ShimCursor)
        return super().cursor(*args, **kwargs)


def get_db():
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL environment variable is not set')
    return psycopg2.connect(DATABASE_URL, connection_factory=_ShimConnection)

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
        employment_type TEXT DEFAULT 'w2',
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
        venue_name TEXT NOT NULL DEFAULT 'Our Venue',
        manager_phone TEXT DEFAULT '',
        tip_pool_enabled INTEGER DEFAULT 0,
        tipout_rate REAL DEFAULT 0.20,
        tip_model TEXT NOT NULL DEFAULT 'equal_pool'
    )''')
    # Existing-DB migration: add tip_model if venue_config predates this column.
    # IF NOT EXISTS is idempotent and safe to run on every boot (no tx abort).
    c.execute("ALTER TABLE venue_config ADD COLUMN IF NOT EXISTS tip_model TEXT NOT NULL DEFAULT 'equal_pool'")
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        name TEXT NOT NULL,
        guest_count INTEGER NOT NULL DEFAULT 0,
        start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '',
        setup_date TEXT DEFAULT '',
        setup_time TEXT DEFAULT '',
        teardown_date TEXT DEFAULT '',
        teardown_time TEXT DEFAULT '',
        space TEXT DEFAULT '',
        location TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        tip_model TEXT NOT NULL DEFAULT 'equal_pool',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL
    )''')
    # Existing-DB migrations: add event columns if the table predates them.
    # ADD COLUMN IF NOT EXISTS is idempotent and never raises, so it can't abort
    # the surrounding schema transaction (unlike a bare ALTER on a present column).
    for _ddl in [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS start_time TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS end_time TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS setup_date TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS setup_time TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS teardown_date TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS teardown_time TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS space TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS tip_model TEXT NOT NULL DEFAULT 'equal_pool'",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'",
    ]:
        c.execute(_ddl)
    c.execute('''CREATE TABLE IF NOT EXISTS event_staffing (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        staff_id TEXT NOT NULL,
        role TEXT NOT NULL,
        confirmed INTEGER NOT NULL DEFAULT 0,
        pay_type TEXT DEFAULT 'hourly',
        rate REAL DEFAULT 0.0,
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
    c.execute('''CREATE TABLE IF NOT EXISTS timesheet_entries (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        event_id TEXT,
        clock_in TEXT,
        clock_out TEXT,
        break_start TEXT,
        break_end TEXT,
        break_compliant INTEGER NOT NULL DEFAULT 1,
        total_hours REAL,
        notes TEXT,
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tip_entries (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        event_id TEXT,
        amount REAL NOT NULL,
        tip_type TEXT NOT NULL DEFAULT 'cash',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tipout_records (
        id TEXT PRIMARY KEY,
        event_id TEXT,
        total_tips REAL NOT NULL,
        tipout_rate REAL NOT NULL,
        tipout_amount REAL NOT NULL,
        staff_count INTEGER NOT NULL,
        calculated_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id)
    )''')
    # Per-staff tip distribution rows (equal-pool, hours-weighted). Replaces the
    # event-summary tipout_records (orphaned, lacked staff_id). One row per staffer
    # per event = their calculated share of that event's pooled tips.
    c.execute('''CREATE TABLE IF NOT EXISTS tip_distributions (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        staff_id TEXT NOT NULL,
        tip_model TEXT NOT NULL DEFAULT 'equal_pool',
        hours_used REAL NOT NULL DEFAULT 0,
        hours_imputed INTEGER NOT NULL DEFAULT 0,
        pool_total REAL NOT NULL DEFAULT 0,
        share_amount REAL NOT NULL DEFAULT 0,
        calculated_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id),
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        event_id TEXT,
        description TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'low',
        resolved INTEGER NOT NULL DEFAULT 0,
        reported_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS venue_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        tip_pool_enabled INTEGER NOT NULL DEFAULT 0,
        tipout_rate REAL NOT NULL DEFAULT 20.0,
        manager_phone TEXT,
        venue_address TEXT,
        venue_phone TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS shift_swap_requests (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        event_id TEXT,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS performance_ratings (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        event_id TEXT,
        rating INTEGER NOT NULL,
        comment TEXT,
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS staff_profiles (
        staff_id TEXT PRIMARY KEY,
        emergency_contact_name TEXT,
        emergency_contact_phone TEXT,
        emergency_contact_relationship TEXT,
        bank_name TEXT,
        bank_routing TEXT,
        bank_account TEXT,
        license_type TEXT,
        license_number TEXT,
        license_state TEXT,
        license_expires TEXT,
        tax_withholding TEXT,
        notes TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS onboarding_documents (
        id TEXT PRIMARY KEY,
        staff_id TEXT NOT NULL,
        doc_type TEXT NOT NULL,
        signed_at TEXT NOT NULL,
        ip_address TEXT,
        signature_image TEXT,
        data_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE (staff_id, doc_type),
        FOREIGN KEY (staff_id) REFERENCES staff(id)
    )''')
    conn.commit()  # commit schema before seeding so table creation is durable
    # Seed default venue config
    c.execute('INSERT OR IGNORE INTO venue_config (id, venue_name) VALUES (1, ?)', ('Our Venue',))
    c.execute('INSERT OR IGNORE INTO venue_settings (id, tip_pool_enabled, tipout_rate) VALUES (1, 0, 20.0)')
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



def normalize_phone(raw):
    """Normalize a US phone number to E.164 (+1XXXXXXXXXX).
    Strips spaces/dashes/parens so '+1 317-555-0410' and '(317) 555-0410'
    both become '+13175550410'. Non-US/odd input is returned trimmed, unchanged."""
    if not raw:
        return ''
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return '+1' + digits
    return str(raw).strip()


def _phone_digits(raw):
    """Last 10 digits of a phone, for format-agnostic matching."""
    d = re.sub(r'\D', '', str(raw or ''))
    if len(d) == 11 and d.startswith('1'):
        d = d[1:]
    return d


def find_staff_by_phone(c, phone, columns='id, name'):
    """Look up a staff row by phone, tolerant of stored formatting differences.
    1) exact match on the incoming (E.164) value;
    2) fallback: compare digit-only forms across active staff;
    On a fallback hit, self-heal by rewriting that row's phone to clean E.164.
    Returns the row (sqlite/psycopg dict row) or None."""
    c.execute(f'SELECT {columns} FROM staff WHERE phone = ?', (phone,))
    row = c.fetchone()
    if row:
        return row
    target = _phone_digits(phone)
    if len(target) != 10:
        return None
    # Scan staff for a digit-equal phone (small table; fine to iterate).
    c.execute('SELECT id, phone FROM staff')
    candidates = c.fetchall()
    match_id = None
    for cand in candidates:
        if _phone_digits(cand['phone']) == target:
            match_id = cand['id']
            break
    if not match_id:
        return None
    # Self-heal: store the clean E.164 form so future lookups hit the fast path.
    try:
        c.execute('UPDATE staff SET phone = ? WHERE id = ?', (normalize_phone(phone), match_id))
    except Exception:
        pass
    c.execute(f'SELECT {columns} FROM staff WHERE id = ?', (match_id,))
    return c.fetchone()


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
        phone = normalize_phone(request.form.get('phone', ''))
        role = request.form.get('role')
        hire_date = request.form.get('hire_date', '')
        now = datetime.utcnow().isoformat()
        employment_type = request.form.get('employment_type', 'w2')
        c.execute('''INSERT INTO staff (id, venue_id, name, email, phone, role, employment_type, hire_date, onboarding_token, agreement_status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
                  (staff_id, 'default', name, email, phone, role, employment_type, hire_date, token, now))
        conn.commit()
        onboarding_link = f'{request.host_url}onboard/{token}'
        venue_name = get_venue_name()
        # Send welcome email with onboarding link
        email_body = f"""Hi {name},

        Welcome to {venue_name}! We're excited to have you on the team.

        Please complete your onboarding by clicking the link below:
        {onboarding_link}

        This link will take you to your Staff Uniform & Professional Conduct Agreement. After signing, you'll receive SMS instructions to complete the remaining steps.

        📱 SMS Opt-In:
        Before you receive shift texts, please confirm your SMS consent here:
        https://wavesurgeai.com/sms-opt-in

        If you have any questions, please contact your manager.

        See you soon!
        """
        if email:
            send_email(email, f'Welcome to {venue_name} — Onboarding', email_body)
        flash(f'Staff member added. Onboarding link: {onboarding_link}', 'success')
        conn.close()
        return redirect(url_for('staff_list'))
    ensure_staff_archive_schema()
    show_archived = request.args.get('archived') == '1'
    flag = 1 if show_archived else 0
    c.execute('SELECT * FROM staff WHERE COALESCE(archived, 0) = ? ORDER BY created_at DESC', (flag,))
    staff_members = c.fetchall()
    c.execute('SELECT COUNT(*) AS n FROM staff WHERE COALESCE(archived, 0) = 1')
    archived_count = c.fetchone()['n']
    conn.close()
    return render_template('staff_list.html', staff=staff_members,
                           show_archived=show_archived, archived_count=archived_count,
                           admin_name=session.get('admin_name'))



@app.route('/admin/staff/<staff_id>/archive', methods=['POST'])
@login_required
def archive_staff(staff_id):
    """Soft-delete: drop a staffer off the active roster but keep all records
    (signed I-9/W-4, agreements, timesheets) intact and restorable."""
    ensure_staff_archive_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM staff WHERE id = ?', (staff_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list'))
    c.execute('UPDATE staff SET archived = 1 WHERE id = ?', (staff_id,))
    conn.commit()
    conn.close()
    flash(f'{row["name"]} archived. Records retained \u2014 restore anytime from the Archived view.', 'success')
    return redirect(url_for('staff_list'))


@app.route('/admin/staff/<staff_id>/restore', methods=['POST'])
@login_required
def restore_staff(staff_id):
    """Bring an archived staffer back onto the active roster."""
    ensure_staff_archive_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM staff WHERE id = ?', (staff_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list', archived=1))
    c.execute('UPDATE staff SET archived = 0 WHERE id = ?', (staff_id,))
    conn.commit()
    conn.close()
    flash(f'{row["name"]} restored to the active roster.', 'success')
    return redirect(url_for('staff_list'))


@app.route('/admin/staff/<staff_id>/purge', methods=['POST'])
@login_required
def purge_staff(staff_id):
    """Hard-delete an archived staffer and ALL their records. Irreversible.
    Reserved for genuine test/junk records (only reachable from Archived view).
    Destroys signed compliance docs -- never expose this for active staff."""
    ensure_staff_archive_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, archived, phone FROM staff WHERE id = ?', (staff_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list', archived=1))
    # Guard: refuse to purge an active staffer -- must be archived first.
    if not row['archived']:
        conn.close()
        flash('Archive this staff member before deleting permanently.', 'error')
        return redirect(url_for('staff_list'))
    name = row['name']
    # Cascade: remove dependent records across all staff-scoped tables.
    for tbl in ('onboarding_documents', 'staff_profiles', 'agreements',
                'event_staffing', 'timesheet_entries', 'tip_entries',
                'tip_distributions', 'shift_swap_requests',
                'performance_ratings', 'incidents'):
        try:
            c.execute(f'DELETE FROM {tbl} WHERE staff_id = ?', (staff_id,))
        except Exception:
            pass
    # onboarding_state is keyed by phone, not staff_id
    try:
        if row['phone']:
            c.execute('DELETE FROM onboarding_state WHERE phone = ?', (row['phone'],))
    except Exception:
        pass
    try:
        c.execute('DELETE FROM staff WHERE id = ?', (staff_id,))
    except Exception:
        pass
    conn.commit()
    conn.close()
    flash(f'{name} and all associated records permanently deleted.', 'success')
    return redirect(url_for('staff_list', archived=1))


@app.route('/admin/staff/<staff_id>', methods=['GET', 'POST'])
@login_required
def staff_detail(staff_id):
    ensure_onboarding_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE id = ?', (staff_id,))
    staff_member = c.fetchone()
    if not staff_member:
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list'))

    # Load profile if exists
    c.execute('SELECT * FROM staff_profiles WHERE staff_id = ?', (staff_id,))
    profile = c.fetchone()

    if request.method == 'POST':
        emergency_name = request.form.get('emergency_contact_name', '')
        emergency_phone = request.form.get('emergency_contact_phone', '')
        emergency_rel = request.form.get('emergency_contact_relationship', '')
        bank_name = request.form.get('bank_name', '')
        bank_routing = request.form.get('bank_routing', '')
        bank_account = request.form.get('bank_account', '')
        license_type = request.form.get('license_type', '')
        license_number = request.form.get('license_number', '')
        license_state = request.form.get('license_state', '')
        license_expires = request.form.get('license_expires', '')
        tax_withholding = request.form.get('tax_withholding', '')
        notes = request.form.get('notes', '')
        now = datetime.utcnow().isoformat()
        c.execute('''INSERT INTO staff_profiles
                     (staff_id, emergency_contact_name, emergency_contact_phone,
                      emergency_contact_relationship, bank_name, bank_routing, bank_account,
                      license_type, license_number, license_state, license_expires,
                      tax_withholding, notes, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT (staff_id) DO UPDATE SET
                         emergency_contact_name = EXCLUDED.emergency_contact_name,
                         emergency_contact_phone = EXCLUDED.emergency_contact_phone,
                         emergency_contact_relationship = EXCLUDED.emergency_contact_relationship,
                         bank_name = EXCLUDED.bank_name,
                         bank_routing = EXCLUDED.bank_routing,
                         bank_account = EXCLUDED.bank_account,
                         license_type = EXCLUDED.license_type,
                         license_number = EXCLUDED.license_number,
                         license_state = EXCLUDED.license_state,
                         license_expires = EXCLUDED.license_expires,
                         tax_withholding = EXCLUDED.tax_withholding,
                         notes = EXCLUDED.notes,
                         updated_at = EXCLUDED.updated_at''',
                  (staff_id, emergency_name, emergency_phone, emergency_rel,
                   bank_name, bank_routing, bank_account,
                   license_type, license_number, license_state, license_expires,
                   tax_withholding, notes, now))
        conn.commit()
        flash('Profile saved.', 'success')
        # Reload profile
        c.execute('SELECT * FROM staff_profiles WHERE staff_id = ?', (staff_id,))
        profile = c.fetchone()

    # Onboarding document progress for admin visibility
    c.execute('SELECT doc_type, signed_at FROM onboarding_documents WHERE staff_id = ?', (staff_id,))
    _rows = {r['doc_type']: r['signed_at'] for r in c.fetchall()}
    _done = dict(_rows)
    if staff_member['agreement_status'] == 'signed':
        c.execute('SELECT signed_at FROM agreements WHERE staff_id = ? ORDER BY signed_at DESC LIMIT 1', (staff_id,))
        _agr = c.fetchone()
        _done['agreement'] = _agr['signed_at'] if _agr else None
    onboarding_docs = [{'key': s['key'], 'title': s['title'], 'done': s['key'] in _done,
                        'viewable': s['key'] in _rows, 'signed_at': _done.get(s['key'])}
                       for s in ONBOARDING_STEPS]
    onboarding_complete = all(d['done'] for d in onboarding_docs)
    conn.close()
    return render_template('staff_detail.html', staff=staff_member, profile=profile,
                          onboarding_docs=onboarding_docs, onboarding_complete=onboarding_complete,
                          admin_name=session.get('admin_name'))



@app.route('/admin/staff/<staff_id>/edit', methods=['POST'])
@login_required
def edit_staff_core(staff_id):
    """Edit a staffer's core fields (name, email, phone, role, type, hire date).
    Separate from the staff_detail profile save, which only writes staff_profiles."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM staff WHERE id = ?', (staff_id,))
    if not c.fetchone():
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list'))

    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip()
    phone = normalize_phone(request.form.get('phone') or '')
    role = (request.form.get('role') or '').strip()
    employment_type = (request.form.get('employment_type') or 'w2').strip()
    hire_date = (request.form.get('hire_date') or '').strip()

    if not name or not email or not role:
        conn.close()
        flash('Name, email, and role are required.', 'error')
        return redirect(url_for('staff_detail', staff_id=staff_id))

    # Title-case the display name so "jeff hackett" -> "Jeff Hackett".
    name = name.title()

    c.execute('''UPDATE staff
                 SET name = ?, email = ?, phone = ?, role = ?,
                     employment_type = ?, hire_date = ?
                 WHERE id = ?''',
              (name, email, phone, role, employment_type, hire_date, staff_id))
    conn.commit()
    conn.close()
    flash('Staff details updated.', 'success')
    return redirect(url_for('staff_detail', staff_id=staff_id))


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


@app.route('/admin/staff/<staff_id>/onboarding/<doc_type>')
@login_required
def view_onboarding_doc(staff_id, doc_type):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE id = ?', (staff_id,))
    staff_member = c.fetchone()
    if not staff_member:
        conn.close()
        flash('Staff member not found.', 'error')
        return redirect(url_for('staff_list'))
    c.execute('SELECT * FROM onboarding_documents WHERE staff_id = ? AND doc_type = ?', (staff_id, doc_type))
    doc = c.fetchone()
    conn.close()
    if not doc:
        flash('That onboarding document has not been completed yet.', 'error')
        return redirect(url_for('staff_detail', staff_id=staff_id))
    step = next((s for s in ONBOARDING_STEPS if s['key'] == doc_type), None)
    try:
        data = json.loads(doc['data_json']) if doc['data_json'] else {}
    except Exception:
        data = {}
    field_rows = []
    if step:
        for f in step['fields']:
            val = data.get(f['name'], '')
            if f['type'] == 'checkbox':
                val = 'Yes' if val == 'yes' else 'No'
            field_rows.append({'label': f['label'], 'value': val or '—'})
    return render_template('view_onboarding_doc.html', staff=staff_member, doc=doc, step=step,
                           field_rows=field_rows, admin_name=session.get('admin_name'))

@app.route('/admin/staff/<staff_id>/resend-link', methods=['POST'])
@login_required
def resend_link(staff_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, email, onboarding_token FROM staff WHERE id = ?', (staff_id,))
    row = c.fetchone()
    if row:
        token = row['onboarding_token']
        onboarding_link = f'{request.host_url}onboard/{token}'
        if row['email']:
            venue_name = get_venue_name()
            email_body = f"""Hi {row['name']},

        Here is your onboarding link for {venue_name}:
        {onboarding_link}

        This link will take you to your Staff Uniform & Professional Conduct Agreement and the rest of your onboarding documents. If you have any questions, please contact your manager.
        """
            sent = send_email(row['email'], f'Your {venue_name} Onboarding Link', email_body)
            if sent:
                flash(f"Onboarding link emailed to {row['email']}.", 'success')
            else:
                flash(f"Could not email {row['email']} - link: {onboarding_link}", 'error')
        else:
            flash(f'Onboarding link: {onboarding_link}', 'success')
    conn.close()
    return redirect(url_for('staff_list'))

_onboarding_schema_ready = False

# Tracks whether the staff.archived column has been ensured this process.
_staff_archive_schema_ready = False


def ensure_staff_archive_schema():
    """Idempotently ensure staff.archived exists (soft-delete flag).
    archived = 0 -> active roster; archived = 1 -> hidden in Archived view.
    Self-heals on the live DB without a manual migration."""
    global _staff_archive_schema_ready
    if _staff_archive_schema_ready:
        return
    try:
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE staff ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except Exception:
            pass  # column already exists
        conn.close()
        _staff_archive_schema_ready = True
    except Exception:
        pass  # leave flag False so the next request retries


def ensure_onboarding_schema():
    """Idempotently ensure the onboarding_documents table exists.
    Self-heals if a boot-time init_db did not create it (e.g. transient DB hiccup)."""
    global _onboarding_schema_ready
    if _onboarding_schema_ready:
        return
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS onboarding_documents (
            id TEXT PRIMARY KEY,
            staff_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            signed_at TEXT NOT NULL,
            ip_address TEXT,
            signature_image TEXT,
            data_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE (staff_id, doc_type),
            FOREIGN KEY (staff_id) REFERENCES staff(id)
        )''')
        conn.commit()
        conn.close()
        _onboarding_schema_ready = True
    except Exception:
        pass  # leave flag False so the next request retries


def _completed_onboarding_docs(c, staff_member):
    """Set of completed onboarding doc_type keys for a staff member."""
    c.execute('SELECT doc_type FROM onboarding_documents WHERE staff_id = ?', (staff_member['id'],))
    done = {r['doc_type'] for r in c.fetchall()}
    # Back-compat: a pre-existing signed agreement counts as the agreement step
    if staff_member['agreement_status'] == 'signed':
        done.add('agreement')
    return done


def _upsert_profile(c, staff_id, fields):
    """Update only the given staff_profiles columns, creating the row if needed.
    Column names come from server-side step definitions (never user input)."""
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO staff_profiles (staff_id, updated_at) VALUES (?, ?) ON CONFLICT (staff_id) DO NOTHING",
              (staff_id, now))
    if fields:
        assigns = ', '.join(f"{col} = ?" for col in fields) + ", updated_at = ?"
        params = list(fields.values()) + [now, staff_id]
        c.execute(f"UPDATE staff_profiles SET {assigns} WHERE staff_id = ?", params)


@app.route('/onboard/<token>', methods=['GET', 'POST'])
def onboard(token):
    ensure_onboarding_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE onboarding_token = ?', (token,))
    staff_member = c.fetchone()
    if not staff_member:
        conn.close()
        return "Invalid or expired onboarding link.", 404

    if request.method == 'POST':
        step_key = request.form.get('step_key')
        step = next((s for s in ONBOARDING_STEPS if s['key'] == step_key), None)
        if not step:
            conn.close()
            return redirect(url_for('onboard', token=token))

        # Collect + validate fields
        field_data = {}
        for f in step['fields']:
            if f['type'] == 'checkbox':
                field_data[f['name']] = 'yes' if request.form.get(f['name']) else 'no'
            else:
                val = (request.form.get(f['name']) or '').strip()
                if f.get('required') and not val:
                    flash(f"{f['label']} is required.", 'error')
                    conn.close()
                    return redirect(url_for('onboard', token=token))
                field_data[f['name']] = val

        # Validate signature when required
        signature_data = request.form.get('signature_data', '')
        if step['signature'] and (not signature_data or ',' not in signature_data):
            flash('Your signature is required.', 'error')
            conn.close()
            return redirect(url_for('onboard', token=token))

        now = datetime.utcnow().isoformat()
        # Store the signed document — signature kept as a base64 data URL in the DB
        c.execute('''INSERT INTO onboarding_documents (id, staff_id, doc_type, signed_at, ip_address, signature_image, data_json)
                     VALUES (?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT (staff_id, doc_type) DO UPDATE SET
                         signed_at = EXCLUDED.signed_at,
                         ip_address = EXCLUDED.ip_address,
                         signature_image = EXCLUDED.signature_image,
                         data_json = EXCLUDED.data_json''',
                  (str(uuid.uuid4()), staff_member['id'], step_key, now,
                   request.remote_addr, signature_data or None, json.dumps(field_data)))

        # Step-specific side effects
        if step_key == 'agreement':
            c.execute('''INSERT INTO agreements (id, staff_id, signed_at, ip_address, signature_image, agreement_text)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (str(uuid.uuid4()), staff_member['id'], now, request.remote_addr,
                       signature_data or None, AGREEMENT_TEXT))
            c.execute("UPDATE staff SET agreement_status = 'signed' WHERE id = ?", (staff_member['id'],))
        elif step_key == 'direct_deposit':
            _upsert_profile(c, staff_member['id'], {
                'bank_name': field_data.get('bank_name', ''),
                'bank_routing': field_data.get('routing_number', ''),
                'bank_account': field_data.get('account_number', ''),
            })
        elif step_key == 'w4':
            _upsert_profile(c, staff_member['id'], {'tax_withholding': field_data.get('filing_status', '')})
        elif step_key == 'emergency_contact':
            _upsert_profile(c, staff_member['id'], {
                'emergency_contact_name': field_data.get('contact_name', ''),
                'emergency_contact_phone': field_data.get('contact_phone', ''),
                'emergency_contact_relationship': field_data.get('relationship', ''),
            })
        elif step_key == 'license':
            _upsert_profile(c, staff_member['id'], {
                'license_type': field_data.get('license_type', ''),
                'license_number': field_data.get('license_number', ''),
                'license_state': field_data.get('license_state', ''),
                'license_expires': field_data.get('license_expires', ''),
            })

        conn.commit()
        conn.close()
        return redirect(url_for('onboard', token=token))

    # GET — advance to the first incomplete step
    done = _completed_onboarding_docs(c, staff_member)
    conn.close()
    next_step = next((s for s in ONBOARDING_STEPS if s['key'] not in done), None)
    if next_step is None:
        return redirect(url_for('onboard_thanks', token=token))
    step_index = ONBOARDING_STEP_KEYS.index(next_step['key'])
    return render_template('onboard_step.html', staff=staff_member, step=next_step,
                           step_number=step_index + 1, total_steps=len(ONBOARDING_STEPS))


@app.route('/onboard/<token>/thanks')
def onboard_thanks(token):
    ensure_onboarding_schema()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM staff WHERE onboarding_token = ?', (token,))
    staff_member = c.fetchone()
    if not staff_member:
        conn.close()
        return "Invalid link.", 404
    done = _completed_onboarding_docs(c, staff_member)
    conn.close()
    steps = [{'title': s['title'], 'done': s['key'] in done} for s in ONBOARDING_STEPS]
    all_done = all(st['done'] for st in steps)
    return render_template('onboard_thanks.html', staff=staff_member, steps=steps, all_done=all_done)

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

    # Load events (hide cancelled/archived from the active staffing list)
    c.execute("SELECT * FROM events WHERE status <> 'cancelled' ORDER BY date DESC")
    events = c.fetchall()

    # Load staff pool
    c.execute('SELECT * FROM staff ORDER BY name')
    all_staff = c.fetchall()

    conn.close()
    return render_template('admin_staffing.html', events=events, all_staff=all_staff, admin_name=session.get('admin_name'))

@app.route('/admin/staffing/<event_id>', methods=['GET', 'POST'])
@login_required
def staffing_detail(event_id):
    """Staffing plan for a specific event."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id=?', (event_id,))
    event = c.fetchone()
    if not event:
        flash('Event not found.', 'error')
        conn.close()
        return redirect(url_for('staffing_matrix'))

    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        role = request.form.get('role')
        if staff_id and role:
            # Check for duplicate assignment
            c.execute('SELECT id FROM event_staffing WHERE event_id=? AND staff_id=? AND role=?',
                     (event_id, staff_id, role))
            if c.fetchone():
                flash(f'{role} is already assigned to this event.', 'error')
            else:
                c.execute('INSERT INTO event_staffing (id, event_id, staff_id, role, confirmed) VALUES (?, ?, ?, ?, 0)',
                         (str(uuid.uuid4()), event_id, staff_id, role))
                conn.commit()
                flash(f'{role} assigned.', 'success')
        conn.close()
        return redirect(url_for('staffing_detail', event_id=event_id))

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
    """List and create events."""
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        tip_model = request.form.get('tip_model', 'equal_pool')
        if tip_model not in TIP_MODEL_VALUES:
            tip_model = 'equal_pool'
        event_id = str(uuid.uuid4())
        c.execute('''INSERT INTO events
                     (id, date, name, guest_count, start_time, end_time,
                      setup_date, setup_time, teardown_date, teardown_time,
                      space, location, notes, tip_model, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)''',
                  (event_id, request.form.get('date'), request.form.get('name'),
                   int(request.form.get('guest_count') or 0),
                   request.form.get('start_time', ''), request.form.get('end_time', ''),
                   request.form.get('setup_date', ''), request.form.get('setup_time', ''),
                   request.form.get('teardown_date', ''), request.form.get('teardown_time', ''),
                   request.form.get('space', '').strip(), request.form.get('location', '').strip(),
                   request.form.get('notes', '').strip(), tip_model,
                   datetime.utcnow().isoformat()))
        conn.commit()
        flash('Event created.', 'success')
        conn.close()
        return redirect(url_for('events_list'))
    c.execute("SELECT * FROM events ORDER BY (status = 'cancelled'), date DESC")
    events = c.fetchall()
    # Distinct, non-blank spaces already used -> datalist suggestions for consistency.
    c.execute("SELECT DISTINCT space FROM events WHERE space IS NOT NULL AND space <> '' ORDER BY space")
    spaces = [r['space'] for r in c.fetchall()]
    conn.close()
    return render_template('admin_events.html', events=events, spaces=spaces,
                           tip_models=TIP_MODEL_CHOICES, admin_name=session.get('admin_name'))


@app.route('/admin/events/<event_id>/edit', methods=['GET', 'POST'])
@login_required
def event_edit(event_id):
    """Edit all details of a single event, including its tip model."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id = ?', (event_id,))
    event = c.fetchone()
    if not event:
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events_list'))

    if request.method == 'POST':
        tip_model = request.form.get('tip_model', 'equal_pool')
        if tip_model not in TIP_MODEL_VALUES:
            tip_model = 'equal_pool'
        c.execute('''UPDATE events SET
                       name = ?, date = ?, guest_count = ?,
                       start_time = ?, end_time = ?,
                       setup_date = ?, setup_time = ?,
                       teardown_date = ?, teardown_time = ?,
                       space = ?, location = ?, notes = ?, tip_model = ?
                     WHERE id = ?''',
                  (request.form.get('name'), request.form.get('date'),
                   int(request.form.get('guest_count') or 0),
                   request.form.get('start_time', ''), request.form.get('end_time', ''),
                   request.form.get('setup_date', ''), request.form.get('setup_time', ''),
                   request.form.get('teardown_date', ''), request.form.get('teardown_time', ''),
                   request.form.get('space', '').strip(), request.form.get('location', '').strip(),
                   request.form.get('notes', '').strip(), tip_model, event_id))
        conn.commit()
        conn.close()
        flash('Event updated.', 'success')
        return redirect(url_for('events_list'))

    c.execute("SELECT DISTINCT space FROM events WHERE space IS NOT NULL AND space <> '' ORDER BY space")
    spaces = [r['space'] for r in c.fetchall()]
    conn.close()
    return render_template('admin_event_edit.html', event=event, spaces=spaces,
                           tip_models=TIP_MODEL_CHOICES, admin_name=session.get('admin_name'))


@app.route('/admin/events/<event_id>/cancel', methods=['POST'])
@login_required
def event_cancel(event_id):
    """Cancel (archive) or restore an event. Guarded soft-delete: the row and its
    timesheets/tips are preserved for recordkeeping; we just flip status."""
    action = request.form.get('action', 'cancel')
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT status FROM events WHERE id = ?', (event_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events_list'))
    new_status = 'active' if action == 'restore' else 'cancelled'
    c.execute('UPDATE events SET status = ? WHERE id = ?', (new_status, event_id))
    conn.commit()
    conn.close()
    flash('Event restored.' if new_status == 'active' else 'Event cancelled (archived).', 'success')
    return redirect(url_for('events_list'))

@app.route('/admin/timesheets', methods=['GET'])
@login_required
def timesheets():
    """View clock entries and timesheet summary."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT t.id, t.clock_in, t.clock_out, t.break_compliant, t.total_hours,
                        t.recorded_at, s.name, s.role
                 FROM timesheet_entries t
                 LEFT JOIN staff s ON t.staff_id = s.id
                 ORDER BY t.recorded_at DESC LIMIT 50''')
    entries = c.fetchall()
    conn.close()
    return render_template('admin_timesheets.html', entries=entries, admin_name=session.get('admin_name'))

@app.route('/admin/incidents')
@login_required
def admin_incidents():
    """View incident log."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT i.*, s.name as staff_name, e.name as event_name
                 FROM incidents i
                 LEFT JOIN staff s ON i.staff_id=s.id
                 LEFT JOIN events e ON i.event_id=e.id
                 ORDER BY i.reported_at DESC LIMIT 100''')
    incidents = c.fetchall()
    c.execute('SELECT severity, COUNT(*) as count FROM incidents GROUP BY severity')
    counts = {row['severity']: row['count'] for row in c.fetchall()}
    high_count = counts.get('high', 0)
    medium_count = counts.get('medium', 0)
    low_count = counts.get('low', 0)
    conn.close()
    return render_template('admin_incidents.html', incidents=incidents,
                          high_count=high_count, medium_count=medium_count, low_count=low_count,
                          admin_name=session.get('admin_name'))

@app.route('/admin/tips', methods=['GET'])
@login_required
def admin_tips():
    """Tip dashboard: raw tip log + per-event pools with hours-weighted splits."""
    conn = get_db()
    c = conn.cursor()

    # Raw tip log (unchanged) -- recent individual TIP submissions.
    c.execute('''SELECT ti.id, ti.amount, ti.recorded_at, ti.event_id, s.name, s.role
                 FROM tip_entries ti
                 LEFT JOIN staff s ON ti.staff_id = s.id
                 ORDER BY ti.recorded_at DESC LIMIT 50''')
    tips = c.fetchall()

    # Per-event pools: every event that has at least one logged tip.
    c.execute('''SELECT e.id, e.name, e.date,
                        COALESCE(SUM(ti.amount), 0) AS pool_total,
                        COUNT(ti.id) AS tip_count
                 FROM events e
                 JOIN tip_entries ti ON ti.event_id = e.id
                 GROUP BY e.id, e.name, e.date
                 ORDER BY e.date DESC''')
    pool_rows = c.fetchall()

    # Already-calculated distributions, grouped by event for display.
    c.execute('''SELECT td.event_id, td.staff_id, td.hours_used, td.hours_imputed,
                        td.share_amount, td.pool_total, td.calculated_at,
                        s.name, s.role
                 FROM tip_distributions td
                 LEFT JOIN staff s ON td.staff_id = s.id
                 ORDER BY td.share_amount DESC''')
    dist_rows = c.fetchall()
    conn.close()

    distributions = {}
    for r in dist_rows:
        distributions.setdefault(r['event_id'], []).append(r)

    events = []
    for p in pool_rows:
        events.append({
            'id': p['id'], 'name': p['name'], 'date': p['date'],
            'pool_total': p['pool_total'], 'tip_count': p['tip_count'],
            'distribution': distributions.get(p['id'], []),
        })

    return render_template('admin_tips.html', tips=tips, events=events,
                           admin_name=session.get('admin_name'))


@app.route('/admin/tips/distribute/<event_id>', methods=['POST'])
@login_required
def admin_tips_distribute(event_id):
    """Calculate (or recalculate) the hours-weighted equal-pool split for an event."""
    result = distribute_event_tips(event_id)
    if result['ok']:
        basis_map = {
            'hours': 'equal pool, split by hours worked',
            'even': 'equal pool, split evenly (no hours logged)',
            'keep_own': 'keep-your-own (no redistribution)',
            'tipout': 'tip-out to support staff',
        }
        basis = basis_map.get(result['basis'], result['basis'])
        flash(f"Tip pool of ${result['pool_total']:.2f} distributed ({basis}) across "
              f"{len(result['rows'])} staff.", 'success')
    else:
        flash(result['error'] or 'Could not calculate tip split.', 'error')
    return redirect(url_for('admin_tips'))

@app.route('/admin/payroll_export')
@login_required
def payroll_export():
    """Export timesheet data as CSV."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT s.name, s.id as employee_id, e.name as event_name,
                       t.clock_in, t.clock_out, t.total_hours, t.break_compliant
                FROM timesheet_entries t
                JOIN staff s ON t.staff_id=s.id
                LEFT JOIN events e ON t.event_id=e.id
                WHERE t.clock_out IS NOT NULL
                ORDER BY t.clock_in DESC''')
    rows = c.fetchall()
    conn.close()
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Employee Name', 'Employee ID', 'Event', 'Clock In', 'Clock Out', 'Total Hours', 'Break Compliant'])
    for r in rows:
        writer.writerow([r['name'], r['employee_id'], r['event_name'] or '',
                         r['clock_in'] or '', r['clock_out'] or '',
                         r['total_hours'] or 0, 'Yes' if r['break_compliant'] else 'No'])
    output.seek(0)
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=payroll_export.csv'
    }

@app.route('/admin/swaps')
@login_required
def admin_swaps():
    """View and manage shift swap requests."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT r.id AS swap_id, s.id, s.name, s.phone, r.event_id, r.reason, r.status, r.created_at
                 FROM shift_swap_requests r
                 JOIN staff s ON r.staff_id=s.id
                 ORDER BY r.created_at DESC LIMIT 50''')
    swaps = c.fetchall()
    c.execute('''SELECT status, COUNT(*) as count FROM shift_swap_requests GROUP BY status''')
    counts = {row['status']: row['count'] for row in c.fetchall()}
    pending_count = counts.get('pending', 0)
    approved_count = counts.get('approved', 0)
    denied_count = counts.get('denied', 0)
    conn.close()
    return render_template('admin_swaps.html', swaps=swaps,
                          pending_count=pending_count, approved_count=approved_count,
                          denied_count=denied_count,
                          admin_name=session.get('admin_name'))


@app.route('/admin/swaps/<swap_id>/<action>', methods=['POST'])
@login_required
def update_swap(swap_id, action):
    """Approve or deny a shift swap request."""
    if action not in ('approve', 'deny'):
        flash('Invalid action.', 'error')
        return redirect(url_for('admin_swaps'))
    new_status = 'approved' if action == 'approve' else 'denied'
    conn = get_db()
    c = conn.cursor()
    # Look up the requester so we can notify them
    c.execute('''SELECT s.name, s.phone, r.status
                 FROM shift_swap_requests r JOIN staff s ON r.staff_id = s.id
                 WHERE r.id = ?''', (swap_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        flash('Swap request not found.', 'error')
        return redirect(url_for('admin_swaps'))
    c.execute("UPDATE shift_swap_requests SET status = ? WHERE id = ?", (new_status, swap_id))
    conn.commit()
    conn.close()
    # Best-effort SMS notification to the requester (no-op if Twilio not configured)
    try:
        msg = (f"Your shift swap request has been {new_status}." if new_status == 'approved'
               else f"Your shift swap request was {new_status}. Please contact your Lead Coordinator with questions.")
        send_sms_alert(row['phone'], msg)
    except Exception:
        pass
    flash(f"Swap request {new_status} for {row['name']}.", 'success')
    return redirect(url_for('admin_swaps'))

@app.route('/admin/ratings')
@login_required
def admin_ratings():
    """View performance ratings by staff."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT AVG(r.rating) as avg_rating, COUNT(*) as count, s.name, s.role
                 FROM performance_ratings r
                 JOIN staff s ON r.staff_id=s.id
                 GROUP BY r.staff_id, s.name, s.role
                 ORDER BY avg_rating DESC''')
    ratings = c.fetchall()
    c.execute('SELECT COUNT(*) as total, AVG(rating) as overall FROM performance_ratings')
    row = c.fetchone()
    total_ratings = row['total'] if row else 0
    overall_avg = round(row['overall'], 1) if row and row['overall'] else 0
    conn.close()
    return render_template('admin_ratings.html', ratings=ratings,
                          total_ratings=total_ratings, overall_avg=overall_avg,
                          admin_name=session.get('admin_name'))


@app.route('/rate/<event_id>', methods=['GET', 'POST'])
def rate_event(event_id):
    """Public, anonymous guest rating page for an event's staff (reached via QR)."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id = ?', (event_id,))
    event = c.fetchone()
    if not event:
        conn.close()
        return "This rating link is not available.", 404
    c.execute('''SELECT DISTINCT s.id, s.name, s.role
                 FROM event_staffing es JOIN staff s ON es.staff_id = s.id
                 WHERE es.event_id = ? AND es.confirmed = 1
                 ORDER BY s.role, s.name''', (event_id,))
    staff = c.fetchall()
    if request.method == 'POST':
        now = datetime.utcnow().isoformat()
        for member in staff:
            raw = request.form.get(f'rating_{member["id"]}', '')
            if raw.isdigit() and 1 <= int(raw) <= 5:
                comment = (request.form.get(f'comment_{member["id"]}') or '').strip()[:500]
                c.execute('''INSERT INTO performance_ratings (id, staff_id, event_id, rating, comment, recorded_at)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (str(uuid.uuid4()), member['id'], event_id, int(raw), comment, now))
        conn.commit()
        conn.close()
        return redirect(url_for('rate_event_thanks', event_id=event_id))
    conn.close()
    return render_template('rate_event.html', event=event, staff=staff)


@app.route('/rate/<event_id>/thanks')
def rate_event_thanks(event_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id = ?', (event_id,))
    event = c.fetchone()
    conn.close()
    return render_template('rate_event_thanks.html', event=event)


@app.route('/admin/events/<event_id>/qr')
@login_required
def event_qr(event_id):
    """Printable QR code linking guests to the anonymous rating page for an event."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM events WHERE id = ?', (event_id,))
    event = c.fetchone()
    conn.close()
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('events_list'))
    rate_url = url_for('rate_event', event_id=event_id, _external=True)
    import qrcode
    import qrcode.image.svg
    import io as _io
    qr = qrcode.QRCode(box_size=14, border=2)
    qr.add_data(rate_url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = _io.BytesIO()
    img.save(buf)
    qr_svg = buf.getvalue().decode('utf-8')
    if qr_svg.startswith('<?xml'):
        qr_svg = qr_svg.split('?>', 1)[1].lstrip()
    return render_template('event_qr.html', event=event, rate_url=rate_url, qr_svg=qr_svg)

@app.route('/admin/seed', methods=['GET'])
@login_required
def seed_data():
    """Seed database with demo staff and contractors for demo purposes."""
    import uuid
    from datetime import datetime as dt

    conn = get_db()
    c = conn.cursor()

    now = dt.utcnow().isoformat()
    venue_id = 'default'

    staff_records = [
        ('owner-001', venue_id, 'Margaret E. Hollister',    'margaret@wavesurgeai.com',   '+1 317-555-0101', 'Owner',         '2025-03-01', uuid.uuid4().hex, 'signed', now),
        ('coord-001', venue_id, 'Tyler J. Brennan',          'tyler@wavesurgeai.com',      '+1 317-555-0102', 'Coordinator',   '2025-03-15', uuid.uuid4().hex, 'signed', now),
        ('admin-001', venue_id, 'Samantha R. Whitfield',     'samantha@wavesurgeai.com',   '+1 317-555-0103', 'Administrator', '2025-04-01', uuid.uuid4().hex, 'signed', now),
        ('bart-001', venue_id, 'Darius L. Morrison',         'dmorrison@gmail.com',        '+1 317-555-0201', 'Bartender',     '2025-05-10', uuid.uuid4().hex, 'pending', now),
        ('bart-002', venue_id, "Caitlin M. O'Brien",        'cobrien@gmail.com',          '+1 317-555-0202', 'Bartender',     '2025-05-12', uuid.uuid4().hex, 'pending', now),
        ('bart-003', venue_id, 'Ethan R. Caldwell',          'ecaldwell@gmail.com',        '+1 317-555-0203', 'Bartender',     '2025-05-14', uuid.uuid4().hex, 'pending', now),
        ('bart-004', venue_id, 'Nia K. Franklin',            'nia.franklin@gmail.com',     '+1 317-555-0204', 'Bartender',     '2025-05-16', uuid.uuid4().hex, 'pending', now),
        ('serv-001', venue_id, 'Brandon T. Holloway',        'bholloway@gmail.com',        '+1 317-555-0301', 'Server',        '2025-06-01', uuid.uuid4().hex, 'pending', now),
        ('serv-002', venue_id, 'Kayla D. Seymour',           'kseymour@gmail.com',         '+1 317-555-0302', 'Server',        '2025-06-03', uuid.uuid4().hex, 'pending', now),
        ('serv-003', venue_id, 'Marcus J. Navarro',           'mnavarro@gmail.com',         '+1 317-555-0303', 'Server',        '2025-06-05', uuid.uuid4().hex, 'pending', now),
        ('serv-004', venue_id, 'Aaliyah B. Reyes',           'areyes@gmail.com',           '+1 317-555-0304', 'Server',        '2025-06-07', uuid.uuid4().hex, 'pending', now),
        ('serv-005', venue_id, 'Jordan L. Cummins',          'jcummins@gmail.com',         '+1 317-555-0305', 'Server',        '2025-06-09', uuid.uuid4().hex, 'pending', now),
        ('serv-006', venue_id, 'Amara S. Patel',             'apatel@gmail.com',           '+1 317-555-0306', 'Server',        '2025-06-11', uuid.uuid4().hex, 'pending', now),
        ('serv-007', venue_id, 'Tyler Q. Washington',        'twashington@gmail.com',      '+1 317-555-0307', 'Server',        '2025-06-13', uuid.uuid4().hex, 'pending', now),
        ('serv-008', venue_id, 'Destiny R. Garcia',          'dgarcia@gmail.com',          '+1 317-555-0308', 'Server',        '2025-06-15', uuid.uuid4().hex, 'pending', now),
        ('serv-009', venue_id, 'Andre M. Lawson',            'alawson@gmail.com',          '+1 317-555-0309', 'Server',        '2025-06-17', uuid.uuid4().hex, 'pending', now),
        ('serv-010', venue_id, 'Imani C. Brooks',            'imbrooks@gmail.com',         '+1 317-555-0310', 'Server',        '2025-06-19', uuid.uuid4().hex, 'pending', now),
        ('serv-011', venue_id, 'Kevin J. Fletcher',          'kfletcher@gmail.com',        '+1 317-555-0311', 'Server',        '2025-06-21', uuid.uuid4().hex, 'pending', now),
        ('serv-012', venue_id, 'Jasmine L. Ortega',          'jortega@gmail.com',          '+1 317-555-0312', 'Server',        '2025-06-23', uuid.uuid4().hex, 'pending', now),
        ('serv-013', venue_id, 'Noah P. Santiago',           'nsantiago@gmail.com',        '+1 317-555-0313', 'Server',        '2025-06-25', uuid.uuid4().hex, 'pending', now),
        ('serv-014', venue_id, 'Maya T. Underwood',          'munderwood@gmail.com',       '+1 317-555-0314', 'Server',        '2025-07-01', uuid.uuid4().hex, 'pending', now),
        ('serv-015', venue_id, 'Luis A. Vega',               'lvega@gmail.com',            '+1 317-555-0315', 'Server',        '2025-07-03', uuid.uuid4().hex, 'pending', now),
        ('serv-016', venue_id, 'Rachel K. Newman',           'rnewman@gmail.com',          '+1 317-555-0316', 'Server',        '2025-07-05', uuid.uuid4().hex, 'pending', now),
        ('cont-001', venue_id, 'Gourmet & Grace Catering — Rachel Stern',    'rachel@gourmetgrace.com',   '+1 317-555-0401', 'Caterer',      '2025-01-15', uuid.uuid4().hex, 'signed', now),
        ('cont-002', venue_id, 'Focus & Light Photography — David Chen',    'david@focuslightphoto.com', '+1 317-555-0402', 'Photographer', '2025-01-20', uuid.uuid4().hex, 'signed', now),
        ('cont-003', venue_id, 'BeatDrop DJ Services — Marcus Thompson',   'marcus@beatdropservices.com','+1 317-555-0403', 'DJ',           '2025-02-01', uuid.uuid4().hex, 'signed', now),
        ('cont-004', venue_id, 'Bloom & Wild Florals — Aisha Williams',    'aisha@bloomwildflorals.com', '+1 317-555-0404', 'Florist',      '2025-02-05', uuid.uuid4().hex, 'signed', now),
        ('cont-005', venue_id, 'Cinema Stories Videography — Jose Rivera', 'jose@cinemastories.com',    '+1 317-555-0405', 'Videographer', '2025-02-10', uuid.uuid4().hex, 'signed', now),
        ('cont-006', venue_id, 'Ceremony & Soul Officiant — Rev. Patricia Cole', 'patricia@ceremonyandsoul.com', '+1 317-555-0406', 'Officiant', '2025-02-15', uuid.uuid4().hex, 'signed', now),
    ]

    count = 0
    for row in staff_records:
        try:
            c.execute("""INSERT OR IGNORE INTO staff (id, venue_id, name, email, phone, role, hire_date, onboarding_token, agreement_status, created_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row)
            count += 1
        except Exception:
            pass

    conn.commit()
    conn.close()

    flash(f'Demo data seeded — {count} staff/contractors added.', 'success')
    return redirect(url_for('staff_list'))

@app.route('/demo', methods=['GET'])
@login_required
def demo_mode():
    """Set up a full demo state: seed staff, create venue, create event, seed timesheets, tips, swaps, ratings, incidents."""
    import uuid
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    venue_id = 'default'

    conn = get_db()
    c = conn.cursor()

    # ── Idempotent reset ───────────────────────────────────────────────────────
    # /demo previously stacked a NEW random-UUID "Johnson Wedding Reception" event
    # (plus its tips/staffing/timesheets) on every run -> duplicate events all
    # showing the same $182 pool. Clear prior demo event(s) and everything scoped
    # to them first, so re-running /demo resets to ONE clean event instead of N.
    # Scoped by event name -> any real events created via the UI are preserved.
    try:
        c.execute("SELECT id FROM events WHERE name = ?", ('Johnson Wedding Reception',))
        _demo_event_ids = [r['id'] for r in c.fetchall()]
    except Exception:
        _demo_event_ids = []
    if _demo_event_ids:
        _ph = ','.join(['?'] * len(_demo_event_ids))
        for _tbl in ('tip_distributions', 'tip_entries', 'timesheet_entries',
                     'event_staffing', 'shift_swap_requests',
                     'performance_ratings', 'incidents'):
            try:
                c.execute(f"DELETE FROM {_tbl} WHERE event_id IN ({_ph})", _demo_event_ids)
            except Exception:
                pass
        try:
            c.execute(f"DELETE FROM events WHERE id IN ({_ph})", _demo_event_ids)
        except Exception:
            pass
        conn.commit()

    # ── Seed demo staff ────────────────────────────────────────────────────────
    staff_records = [
        # Venue staff (admin)
        ('owner-001', venue_id, 'Margaret E. Hollister',    'margaret@wavesurgeai.com',   '+1 317-555-0101', 'Owner',         '2025-03-01', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('coord-001', venue_id, 'Tyler J. Brennan',          'tyler@wavesurgeai.com',      '+1 317-555-0102', 'Coordinator',   '2025-03-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('admin-001', venue_id, 'Samantha R. Whitfield',     'samantha@wavesurgeai.com',   '+1 317-555-0103', 'Administrator', '2025-04-01', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Bartenders (primary)
        ('bart-001', venue_id, 'Darius L. Morrison',         'dmorrison@gmail.com',        '+1 317-555-0201', 'Bartender',     '2025-05-10', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-002', venue_id, "Caitlin M. O'Brien",        'cobrien@gmail.com',          '+1 317-555-0202', 'Bartender',     '2025-05-12', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-003', venue_id, 'Ethan R. Caldwell',          'ecaldwell@gmail.com',        '+1 317-555-0203', 'Bartender',     '2025-05-14', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-004', venue_id, 'Nia K. Franklin',             'nia.franklin@gmail.com',     '+1 317-555-0204', 'Bartender',     '2025-05-16', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-005', venue_id, 'Victor R. Okonkwo',          'vokonkwo@gmail.com',         '+1 317-555-0205', 'Bartender',     '2025-06-01', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-006', venue_id, 'Travis W. Barlow',           'tbarlow@gmail.com',         '+1 317-555-0206', 'Bartender',     '2025-06-03', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-007', venue_id, 'Chloe A. Vance',             'cvance@gmail.com',           '+1 317-555-0207', 'Bartender',     '2025-06-05', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('bart-008', venue_id, 'Rashad K. Ellis',            'rellis@gmail.com',           '+1 317-555-0208', 'Bartender',     '2025-06-07', uuid.uuid4().hex, 'pending', now.isoformat()),
        # Servers (primary)
        ('serv-001', venue_id, 'Brandon T. Holloway',        'bholloway@gmail.com',        '+1 317-555-0301', 'Server',        '2025-06-01', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-002', venue_id, 'Kayla D. Seymour',           'kseymour@gmail.com',         '+1 317-555-0302', 'Server',        '2025-06-03', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-003', venue_id, 'Marcus J. Navarro',           'mnavarro@gmail.com',         '+1 317-555-0303', 'Server',        '2025-06-05', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-004', venue_id, 'Aaliyah B. Reyes',           'areyes@gmail.com',           '+1 317-555-0304', 'Server',        '2025-06-07', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-005', venue_id, 'Jordan L. Cummins',          'jcummins@gmail.com',         '+1 317-555-0305', 'Server',        '2025-06-09', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-006', venue_id, 'Amara S. Patel',             'apatel@gmail.com',           '+1 317-555-0306', 'Server',        '2025-06-11', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-007', venue_id, 'Tyler Q. Washington',        'twashington@gmail.com',      '+1 317-555-0307', 'Server',        '2025-06-13', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-008', venue_id, 'Destiny R. Garcia',          'dgarcia@gmail.com',          '+1 317-555-0308', 'Server',        '2025-06-15', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-009', venue_id, 'Andre M. Lawson',            'alawson@gmail.com',          '+1 317-555-0309', 'Server',        '2025-06-17', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-010', venue_id, 'Imani C. Brooks',            'imbrooks@gmail.com',         '+1 317-555-0310', 'Server',        '2025-06-19', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-011', venue_id, 'Kevin J. Fletcher',          'kfletcher@gmail.com',        '+1 317-555-0311', 'Server',        '2025-06-21', uuid.uuid4().hex, 'pending', now.isoformat()),
        ('serv-012', venue_id, 'Latrice M. Harmon',         'lharmon@gmail.com',           '+1 317-555-0312', 'Server',        '2025-06-23', uuid.uuid4().hex, 'pending', now.isoformat()),
        # Event Lead
        ('lead-001', venue_id, 'Patricia D. Nguyen',        'pnguyen@gmail.com',          '+1 317-555-0501', 'Event Lead',    '2025-02-01', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Security/Parking — primary
        ('sec-001', venue_id, 'Darnell K. Odom',            'domod@gmail.com',            '+1 317-555-0601', 'Security',      '2025-02-10', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('sec-002', venue_id, 'Sandra L. Moody',            'smoody@gmail.com',           '+1 317-555-0602', 'Security',      '2025-02-10', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Multi-role staff: Security + Bartender
        ('secbart-001', venue_id, 'Marcus T. Webb',         'mwebb@gmail.com',            '+1 317-555-0603', 'Security/Bartender', '2025-02-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Multi-role staff: Security + Server
        ('secserv-001', venue_id, 'Tamika D. Frye',         'tfrye@gmail.com',            '+1 317-555-0604', 'Security/Server',   '2025-02-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('secserv-002', venue_id, 'Damon R. Stoudt',        'dstoudt@gmail.com',          '+1 317-555-0605', 'Security/Server',   '2025-02-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Primary contractors
        ('cont-001', venue_id, 'Gourmet & Grace Catering — Rachel Stern',    'rachel@gourmetgrace.com',   '+1 317-555-0401', 'Caterer',      '2025-01-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-002', venue_id, 'Focus & Light Photography — David Chen',    'david@focuslightphoto.com', '+1 317-555-0402', 'Photographer', '2025-01-20', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-003', venue_id, 'BeatDrop DJ Services — Marcus Thompson',   'marcus@beatdropservices.com','+1 317-555-0403', 'DJ',           '2025-02-01', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Alternate contractors
        ('cont-004', venue_id, 'Silver Service Catering — Owen Bell',        'owen@silverservicecatering.com', '+1 317-555-0404', 'Caterer',      '2025-02-01', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-005', venue_id, 'Golden Hour Photos — Simone Laurent',       'simone@goldenhourphotos.com',    '+1 317-555-0405', 'Photographer', '2025-02-05', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-006', venue_id, 'Precision Beats DJ — Jerome Clarke',     'jerome@precisionbeats.com',      '+1 317-555-0406', 'DJ',           '2025-02-10', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-007', venue_id, 'Bloom & Wild Florals — Aisha Williams',    'aisha@bloomwildflorals.com',   '+1 317-555-0407', 'Florist',      '2025-02-05', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-008', venue_id, 'Cinema Stories Videography — Jose Rivera', 'jose@cinemastories.com',       '+1 317-555-0408', 'Videographer', '2025-02-10', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-009', venue_id, 'Ceremony & Soul Officiant — Rev. Patricia Cole','patricia@ceremonyandsoul.com','+1 317-555-0409', 'Officiant',    '2025-02-15', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Additional caterers
        ('cont-010', venue_id, 'Harvest & Hearth Catering — Bianca Russo',     'bianca@harvesthearth.com',       '+1 317-555-0410', 'Caterer',      '2025-02-18', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-011', venue_id, 'Saffron Table Catering — Devin Okafor',       'devin@saffrontable.com',         '+1 317-555-0411', 'Caterer',      '2025-02-20', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Additional videographers
        ('cont-012', venue_id, 'Evergreen Wedding Films — Holly Tran',        'holly@evergreenfilms.com',       '+1 317-555-0412', 'Videographer', '2025-02-22', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-013', venue_id, 'Heartframe Films — Andre Castillo',           'andre@heartframefilms.com',      '+1 317-555-0413', 'Videographer', '2025-02-25', uuid.uuid4().hex, 'signed', now.isoformat()),
        # Additional photographers
        ('cont-014', venue_id, 'Lumen & Lace Photography — Priya Desai',      'priya@lumenlace.com',            '+1 317-555-0414', 'Photographer', '2025-02-28', uuid.uuid4().hex, 'signed', now.isoformat()),
        ('cont-015', venue_id, 'Stillwater Studios — Cole Bennett',           'cole@stillwaterstudios.com',     '+1 317-555-0415', 'Photographer', '2025-03-03', uuid.uuid4().hex, 'signed', now.isoformat()),
    ]
    for row in staff_records:
        try:
            c.execute("""INSERT OR IGNORE INTO staff (id, venue_id, name, email, phone, role, hire_date, onboarding_token, agreement_status, created_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row)
        except Exception:
            pass

    # ── Set venue name ─────────────────────────────────────────────────────────
    c.execute("""INSERT INTO venue_config (id, venue_name, manager_phone, tip_pool_enabled, tipout_rate) VALUES (1, ?, '+13175550101', 0, 20.0)
                 ON CONFLICT (id) DO UPDATE SET venue_name = EXCLUDED.venue_name, manager_phone = EXCLUDED.manager_phone""",
               ('Willowmere Gardens',))

    # ── Create demo event ─────────────────────────────────────────────────────
    event_id = str(uuid.uuid4())
    event_date = (now + timedelta(days=14)).strftime('%Y-%m-%d')
    setup_date = (now + timedelta(days=13)).strftime('%Y-%m-%d')      # night-before setup
    teardown_date = (now + timedelta(days=15)).strftime('%Y-%m-%d')   # morning-after teardown
    try:
        c.execute("""INSERT OR IGNORE INTO events
                      (id, date, name, guest_count, start_time, end_time,
                       setup_date, setup_time, teardown_date, teardown_time,
                       space, location, notes, tip_model, status, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                  (event_id, event_date, 'Johnson Wedding Reception', 150,
                   '17:00', '23:00', setup_date, '14:00', teardown_date, '09:00',
                   'Glass Barn', 'Willowmere Gardens', 'Plated dinner; 6 vendor tables.',
                   'equal_pool', now.isoformat()))
    except Exception:
        pass

    # ── Pre-confirm some staff for the event ──────────────────────────────────
    confirmed_pairs = [
        (str(uuid.uuid4()), event_id, 'bart-001', 'Bartender', 1),
        (str(uuid.uuid4()), event_id, 'bart-002', 'Bartender', 1),
        (str(uuid.uuid4()), event_id, 'serv-001', 'Server',    1),
        (str(uuid.uuid4()), event_id, 'serv-002', 'Server',    1),
        (str(uuid.uuid4()), event_id, 'serv-003', 'Server',    1),
        (str(uuid.uuid4()), event_id, 'cont-001', 'Caterer',   1),
        (str(uuid.uuid4()), event_id, 'cont-002', 'Photographer', 1),
        (str(uuid.uuid4()), event_id, 'cont-003', 'DJ',        1),
    ]
    for row in confirmed_pairs:
        try:
            c.execute("INSERT OR IGNORE INTO event_staffing (id, event_id, staff_id, role, confirmed) VALUES (?, ?, ?, ?, ?)", row)
        except Exception:
            pass

    # ── Seed timesheet entries (clock in/out for today) ─────────────────────────
    today = now.strftime('%Y-%m-%d')
    timesheet_entries = [
        (str(uuid.uuid4()), 'bart-001', event_id, f'{today} 14:00', f'{today} 22:30', 8.5, 1, now.isoformat()),
        (str(uuid.uuid4()), 'serv-001', event_id, f'{today} 13:30', f'{today} 22:00', 8.5, 1, now.isoformat()),
        (str(uuid.uuid4()), 'serv-002', event_id, f'{today} 13:30', f'{today} 22:00', 8.5, 1, now.isoformat()),
        (str(uuid.uuid4()), 'serv-003', event_id, f'{today} 14:00', f'{today} 22:30', 8.5, 1, now.isoformat()),
    ]
    for row in timesheet_entries:
        try:
            c.execute("""INSERT OR IGNORE INTO timesheet_entries (id, staff_id, event_id, clock_in, clock_out, total_hours, break_compliant, recorded_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", row)
        except Exception:
            pass

    # ── Seed tip entries ───────────────────────────────────────────────────────
    tip_entries = [
        (str(uuid.uuid4()), 'bart-001', event_id, 85.00, 'cash', now.isoformat()),
        (str(uuid.uuid4()), 'serv-001', event_id, 45.00, 'cash', now.isoformat()),
        (str(uuid.uuid4()), 'serv-002', event_id, 52.00, 'cash', now.isoformat()),
    ]
    for row in tip_entries:
        try:
            c.execute("""INSERT OR IGNORE INTO tip_entries (id, staff_id, event_id, amount, tip_type, recorded_at)
                          VALUES (?, ?, ?, ?, ?, ?)""", row)
        except Exception:
            pass

    # ── Seed a swap request ────────────────────────────────────────────────────
    swap_id = str(uuid.uuid4())
    try:
        c.execute("""INSERT OR IGNORE INTO shift_swap_requests (id, staff_id, event_id, reason, status, created_at)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                  (swap_id, 'serv-003', event_id, 'Family reunion that weekend — can someone cover?', 'pending', now.isoformat()))
    except Exception:
        pass

    # ── Seed a performance rating ──────────────────────────────────────────────
    rating_id = str(uuid.uuid4())
    try:
        c.execute("""INSERT OR IGNORE INTO performance_ratings (id, staff_id, event_id, rating, comment, recorded_at)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                  (rating_id, 'bart-001', event_id, 5, 'Excellent service — very professional throughout the event.', now.isoformat()))
    except Exception:
        pass

    # ── Seed an incident ───────────────────────────────────────────────────────
    incident_id = str(uuid.uuid4())
    try:
        c.execute("""INSERT OR IGNORE INTO incidents (id, staff_id, event_id, description, severity, reported_at)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                  (incident_id, 'serv-002', event_id, 'Minor spill in the garden patio area. Cleaned up immediately with no guest complaints.', 'low', now.isoformat()))
    except Exception:
        pass

   # ── Sign agreements + complete full onboarding packet for "signed" staff ──
    try:
        demo_sig = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHdpZHRoPSczMjAnIGhlaWdodD0nOTAnIHZpZXdCb3g9JzAgMCAzMjAgOTAnPjxyZWN0IHdpZHRoPSczMjAnIGhlaWdodD0nOTAnIGZpbGw9J3doaXRlJy8+PHBhdGggZD0nTTE4IDYyIEM0MCAyMCwgNTIgNzgsIDcwIDQ2IFMxMDQgMTgsIDEyMCA1NCBDMTMyIDgwLCAxNDggMzAsIDE2MiA1MiBDMTc2IDcyLCAxOTYgMjgsIDIxNCA1MCBDMjI4IDY2LCAyNDYgMzQsIDI2MiA1MiBDMjc2IDY2LCAyOTIgNDQsIDMwNCA1MCcgZmlsbD0nbm9uZScgc3Ryb2tlPScjMWYyOTM3JyBzdHJva2Utd2lkdGg9JzIuNCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJy8+PHBhdGggZD0nTTE1MCA3MCBDMTkwIDY2LCAyNDAgNjYsIDMwMCA2OCcgZmlsbD0nbm9uZScgc3Ryb2tlPScjMWYyOTM3JyBzdHJva2Utd2lkdGg9JzEuNCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJyBvcGFjaXR5PScwLjcnLz48L3N2Zz4="
        _filings = ['Single or Married filing separately',
                    'Married filing jointly or Qualifying surviving spouse',
                    'Head of household']
        _citizen = ['A citizen of the United States',
                    'A citizen of the United States',
                    'A lawful permanent resident']
        _id_docs = ["List B + C — Driver's License + Social Security Card",
                    'List A — U.S. Passport or Passport Card',
                    'List B + C — State ID + Birth Certificate']
        _rels = ['Spouse', 'Parent', 'Sibling', 'Partner']
        _lic_exp = ['2028-04-15', '2026-08-30', '2027-11-01', '2026-07-20', '2029-01-10']
        c.execute("SELECT id, name, phone, role FROM staff WHERE agreement_status = 'signed'")
        for i, srow in enumerate(c.fetchall()):
            sid = srow['id']
            sname = srow['name'] or 'Staff Member'
            sphone = srow['phone'] or ''
            last4 = sphone[-4:] if len(sphone) >= 4 else '4821'
            srole = srow['role'] or ''
            if ('Bartender' in srole) or ('Security' in srole):
                lic = {'license_type': 'Indiana ATC Employee Permit (Unrestricted, 21+)',
                       'license_number': 'EP-' + str(100000 + i),
                       'license_state': 'IN - Alcohol & Tobacco Commission',
                       'license_expires': _lic_exp[i % len(_lic_exp)]}
            else:
                lic = {'license_type': '', 'license_number': '', 'license_state': '', 'license_expires': ''}
            # Agreement (separate table + dedicated viewer)
            c.execute('SELECT id FROM agreements WHERE staff_id = ?', (sid,))
            if not c.fetchone():
                c.execute("""INSERT INTO agreements (id, staff_id, signed_at, ip_address, signature_image, agreement_text)
                               VALUES (?, ?, ?, '127.0.0.1', ?, ?)""",
                           (str(uuid.uuid4()), sid, now.isoformat(), demo_sig,
                            'Staff Uniform & Professional Conduct Agreement — Willowmere Gardens'))
            # Remaining five wizard documents (full demo packet)
            packet = [
                ('handbook', {}, demo_sig),
                ('direct_deposit', {'account_holder': sname, 'bank_name': 'First Midwest Bank',
                                    'account_type': 'Checking', 'routing_number': '071000013',
                                    'account_number': 'xxxxxx' + last4}, demo_sig),
                ('w4', {'filing_status': _filings[i % len(_filings)], 'multiple_jobs': 'no',
                        'dependents_amount': '0.00', 'other_income': '0.00', 'deductions': '0.00',
                        'extra_withholding': '0.00', 'exempt': 'no'}, demo_sig),
                ('i9', {'citizenship_status': _citizen[i % len(_citizen)],
                        'id_documents': _id_docs[i % len(_id_docs)]}, demo_sig),
                ('emergency_contact', {'contact_name': 'Emergency Contact',
                                       'contact_phone': '+1 317-555-0' + str(700 + i),
                                       'relationship': _rels[i % len(_rels)]}, None),
                ('license', lic, None),
            ]
            for dtype, data, sig in packet:
                c.execute('SELECT id FROM onboarding_documents WHERE staff_id = ? AND doc_type = ?', (sid, dtype))
                if not c.fetchone():
                    c.execute('''INSERT INTO onboarding_documents (id, staff_id, doc_type, signed_at, ip_address, signature_image, data_json)
                                 VALUES (?, ?, ?, ?, '127.0.0.1', ?, ?)''',
                              (str(uuid.uuid4()), sid, dtype, now.isoformat(), sig, json.dumps(data)))
    except Exception:
        pass

    # ── Mirror onboarding doc data into staff_profiles (profile card) ─────────
    try:
        c.execute("SELECT id FROM staff WHERE agreement_status = 'signed'")
        for prow in c.fetchall():
            pid = prow['id']
            ec, dd, w4 = {}, {}, {}
            c.execute("SELECT data_json FROM onboarding_documents WHERE staff_id = ? AND doc_type = 'emergency_contact'", (pid,))
            r = c.fetchone()
            if r and r['data_json']:
                ec = json.loads(r['data_json'])
            c.execute("SELECT data_json FROM onboarding_documents WHERE staff_id = ? AND doc_type = 'direct_deposit'", (pid,))
            r = c.fetchone()
            if r and r['data_json']:
                dd = json.loads(r['data_json'])
            c.execute("SELECT data_json FROM onboarding_documents WHERE staff_id = ? AND doc_type = 'w4'", (pid,))
            r = c.fetchone()
            if r and r['data_json']:
                w4 = json.loads(r['data_json'])
            lic = {}
            c.execute("SELECT data_json FROM onboarding_documents WHERE staff_id = ? AND doc_type = 'license'", (pid,))
            r = c.fetchone()
            if r and r['data_json']:
                lic = json.loads(r['data_json'])
            tax_pref = w4.get('filing_status', '')
            if w4.get('exempt') == 'yes':
                tax_pref = (tax_pref + ' — Exempt').strip(' —')
            c.execute('''INSERT INTO staff_profiles
                         (staff_id, emergency_contact_name, emergency_contact_phone, emergency_contact_relationship,
                          bank_name, bank_routing, bank_account, tax_withholding,
                          license_type, license_number, license_state, license_expires, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                         ON CONFLICT (staff_id) DO UPDATE SET
                             emergency_contact_name = EXCLUDED.emergency_contact_name,
                             emergency_contact_phone = EXCLUDED.emergency_contact_phone,
                             emergency_contact_relationship = EXCLUDED.emergency_contact_relationship,
                             bank_name = EXCLUDED.bank_name,
                             bank_routing = EXCLUDED.bank_routing,
                             bank_account = EXCLUDED.bank_account,
                             tax_withholding = EXCLUDED.tax_withholding,
                             license_type = EXCLUDED.license_type,
                             license_number = EXCLUDED.license_number,
                             license_state = EXCLUDED.license_state,
                             license_expires = EXCLUDED.license_expires,
                             updated_at = EXCLUDED.updated_at''',
                      (pid, ec.get('contact_name', ''), ec.get('contact_phone', ''), ec.get('relationship', ''),
                       dd.get('bank_name', ''), dd.get('routing_number', ''), dd.get('account_number', ''),
                       tax_pref, lic.get('license_type', ''), lic.get('license_number', ''),
                       lic.get('license_state', ''), lic.get('license_expires', ''), now.isoformat()))
    except Exception:
        pass

    conn.commit()
    conn.close()

    flash('Demo data ready — Willowmere Gardens, Johnson Wedding, pre-populated staff and activity.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def venue_settings():
    """Manage venue settings."""
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        venue_name = request.form.get('venue_name', 'Our Venue')
        manager_phone = request.form.get('manager_phone', '')
        tip_pool = request.form.get('tip_pool_enabled', '')
        tip_rate = request.form.get('tipout_rate', '0.20')
        c.execute('DELETE FROM venue_config WHERE id = 1')
        c.execute('INSERT INTO venue_config (id, venue_name, manager_phone, tip_pool_enabled, tipout_rate) VALUES (1, ?, ?, ?, ?)',
                  (venue_name, manager_phone, 1 if tip_pool else 0, float(tip_rate)))
        conn.commit()
        flash('Settings saved.', 'success')
    c.execute('SELECT * FROM venue_config WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return render_template('admin_settings.html', settings=row, admin_name=session.get('admin_name'))

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')
TWILIO_MESSAGING_SERVICE_SID = os.environ.get('TWILIO_MESSAGING_SERVICE_SID', '')

# ─── Helpers ─────────────────────────────────────────────────────────────────────

def get_manager_phone() -> str:
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT manager_phone FROM venue_settings WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return row['manager_phone'] if row and row['manager_phone'] else None

def send_sms_alert(to_phone: str, message: str):
    """Send an outbound SMS via Twilio.

    Prefers the approved A2P Messaging Service so traffic routes through the
    registered 10DLC campaign. Falls back to the bare from-number if no
    Messaging Service SID is set.
    """
    if not to_phone or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        app.logger.warning('SMS skipped: missing recipient or Twilio credentials')
        return
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        kwargs = {'body': message, 'to': to_phone}
        if TWILIO_MESSAGING_SERVICE_SID:
            kwargs['messaging_service_sid'] = TWILIO_MESSAGING_SERVICE_SID
        elif TWILIO_PHONE_NUMBER:
            kwargs['from_'] = TWILIO_PHONE_NUMBER
        else:
            app.logger.warning('SMS skipped: no Messaging Service SID or from-number set')
            return
        msg = client.messages.create(**kwargs)
        app.logger.info(f'SMS sent to {to_phone} sid={msg.sid}')
    except Exception as e:
        app.logger.error(f'Failed to send SMS to {to_phone}: {e}')

# ─── Timesheet Handlers ──────────────────��──────────────────────────────────────



def resolve_staff_event(c, staff_id, ref_date=None, window_days=1):
    """Find the single event a staffer is confirmed on, within +/- window_days
    of ref_date (defaults to today). Supports night-before setup and
    night-after teardown without binding to an exact event date.

    Returns (status, event) where status is:
      'ok'       -> exactly one match; event is the row {id, name, date}
      'none'     -> no confirmed event in the window; event is None
      'multiple' -> more than one; event is None (caller refuses, Piece 2 later)
    """
    from datetime import datetime, timedelta
    if ref_date is None:
        ref_date = datetime.utcnow().date()
    elif isinstance(ref_date, str):
        ref_date = datetime.strptime(ref_date[:10], '%Y-%m-%d').date()
    lo = (ref_date - timedelta(days=window_days)).strftime('%Y-%m-%d')
    hi = (ref_date + timedelta(days=window_days)).strftime('%Y-%m-%d')
    c.execute('''SELECT e.id, e.name, e.date FROM events e
                 JOIN event_staffing es ON es.event_id = e.id
                 WHERE es.staff_id = ? AND es.confirmed = 1
                   AND e.date >= ? AND e.date <= ?
                 ORDER BY e.date''', (staff_id, lo, hi))
    rows = c.fetchall()
    if not rows:
        return 'none', None
    if len(rows) > 1:
        return 'multiple', None
    return 'ok', rows[0]


# Standard refusal messages so all three handlers speak the same way.
EVENT_NONE_MSG = ("You're not assigned to an event around today, so there's nothing to "
                  "record this against. Please contact your coordinator.")
EVENT_MULTI_MSG = ("You're assigned to more than one event right now, so I can't tell which "
                   "this belongs to. Please contact your coordinator to sort it out.")


def handle_clock(phone: str, body: str, action: str):
    """Handle IN or OUT SMS commands."""
    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    conn.close()
    if not staff:
        return "I don't recognize that phone number. Please contact your manager.", None

    staff_id = staff['id']
    staff_name = staff['name']
    now = datetime.utcnow()
    today = now.strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()

    if action == 'IN':
        # Check if already clocked in today
        c.execute('''SELECT id FROM timesheet_entries
                     WHERE staff_id=? AND LEFT(clock_in, 10)=? AND clock_out IS NULL''',
                  (staff_id, today))
        existing = c.fetchone()
        if existing:
            conn.close()
            return (f"You're already clocked in, {staff_name}.\n"
                    "Reply OUT when your shift ends.\n"
                    "Reply BREAK to start a break."), None

        # Resolve the single confirmed event in the +/-1 day window (setup/teardown safe).
        status, event = resolve_staff_event(c, staff_id)
        if status == 'none':
            conn.close()
            return ("You're not assigned to an event around today, so I can't clock you in. "
                    "Please contact your coordinator."), None
        if status == 'multiple':
            conn.close()
            return ("You're assigned to more than one event right now, so I can't tell which "
                    "to clock you into. Please contact your coordinator."), None
        event_id = event['id']

        entry_id = str(uuid.uuid4())
        c.execute('''INSERT INTO timesheet_entries (id, staff_id, event_id, clock_in, recorded_at)
                     VALUES (?, ?, ?, ?, ?)''',
                  (entry_id, staff_id, event_id, now.isoformat(), now.isoformat()))
        conn.commit()
        conn.close()
        event_info = f"\nEvent: {event['name']}" if event else ""
        return (f"✅ Clocked in at {now.strftime('%I:%M %p')}, {staff_name}.{event_info}\n"
                "Enjoy your shift! Reply BREAK to start a break."), None

    else:  # OUT
        c.execute('''SELECT id, clock_in, break_start FROM timesheet_entries
                     WHERE staff_id=? AND LEFT(clock_in, 10)=? AND clock_out IS NULL
                     ORDER BY clock_in DESC LIMIT 1''',
                  (staff_id, today))
        entry = c.fetchone()
        if not entry:
            conn.close()
            return (f"You haven't clocked in today, {staff_name}.\n"
                    "Reply IN to start your shift."), None

        entry_id = entry['id']
        clock_in_time = datetime.fromisoformat(entry['clock_in'])

        # Auto-end break if one is active
        break_start = entry['break_start']
        compliant = 1
        if break_start:
            break_end = now
            break_duration = (break_end - datetime.fromisoformat(break_start)).total_seconds() / 3600
            if break_duration < 0.5:
                compliant = 0

        total_hours = (now - clock_in_time).total_seconds() / 3600
        c.execute('''UPDATE timesheet_entries
                     SET clock_out=?, break_end=?, break_compliant=?, total_hours=?
                     WHERE id=?''',
                  (now.isoformat(), now.isoformat() if break_start else None, compliant, round(total_hours, 2), entry_id))
        conn.commit()
        conn.close()
        return (f"✅ Clocked out at {now.strftime('%I:%M %p')}, {staff_name}.\n"
                f"Total shift: {round(total_hours, 2)} hours."), None

def handle_break_response(phone: str, body: str):
    """Handle YES/NO break response."""
    upper = body.upper().strip()
    today = datetime.utcnow().strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    if not staff:
        conn.close()
        return "I don't recognize that phone number."

    staff_id = staff['id']
    staff_name = staff['name']

    c.execute('''SELECT id, clock_in, break_start FROM timesheet_entries
                 WHERE staff_id=? AND LEFT(clock_in, 10)=? AND clock_out IS NULL
                 ORDER BY clock_in DESC LIMIT 1''', (staff_id, today))
    entry = c.fetchone()
    conn.close()

    if not entry:
        return f"No active shift found for {staff_name}. Reply IN to start."

    now = datetime.utcnow()

    if upper in ('YES', 'Y'):
        if entry['break_start']:
            return "You're already on break."
        c.execute = conn.cursor()  # no, use normal cursor
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE timesheet_entries SET break_start=? WHERE id=?',
                  (now.isoformat(), entry['id']))
        conn.commit()
        conn.close()
        return (f"☕ Break started at {now.strftime('%I:%M %p')}.\n"
                "Reply YES when you're back to end your break.\n"
                "NOTE: Breaks under 30 min are logged as non-compliant.")
    else:
        if not entry['break_start']:
            return "You haven't started a break. Reply BREAK to start one."
        break_start = datetime.fromisoformat(entry['break_start'])
        break_duration = (now - break_start).total_seconds() / 3600
        compliant = 1 if break_duration >= 0.5 else 0
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE timesheet_entries SET break_end=?, break_compliant=? WHERE id=?',
                  (now.isoformat(), compliant, entry['id']))
        conn.commit()
        conn.close()
        if compliant:
            return (f"✅ Break ended at {now.strftime('%I:%M %p')}.\n"
                    f"Break duration: {round(break_duration, 2)} hrs — compliant. ✅")
        else:
            return (f"⚠️ Break ended at {now.strftime('%I:%M %p')}.\n"
                    f"Break was {round(break_duration, 2)} hrs — under 30 min. Marked non-compliant.")

# ─── Tip Handler ────────────────────────────────────────────────────────────────

# --- Tip distribution models -------------------------------------------------
# equal_pool is implemented (hours-weighted, see distribute_event_tips).
# The other two are roadmap stubs so the venue-config dropdown is a drop-in later
# (same pattern as the planned VERTICALS block). Do not wire them until a pilot
# pulls them -- during a demo we say "configurable to however your venue splits
# tips" and show the working equal-pool model.
TIP_MODELS = {
    'equal_pool': {
        'label': 'Equal Pool (hours-weighted)',
        'live': True,
        'desc': "All tips for an event pool together and split across the crew "
                "weighted by hours worked. Anyone without a logged timesheet is "
                "counted at the crew's average hours.",
    },
    'tipout_pct': {
        'label': 'Tipout % to Support Staff',
        'live': False,
        'desc': "Tipped earners contribute a set percentage to a support pool. "
                "Roadmap -- not yet built.",
    },
    'keep_own': {
        'label': 'Keep Your Own',
        'live': False,
        'desc': "Each staffer keeps the tips they personally logged. "
                "Roadmap -- not yet built.",
    },
}


# Tip-out role policy (per Jeff's call). Front-of-house tipped roles contribute a
# percentage of their own logged tips into a pool shared by the support roles.
# Centralized here so the multi-vertical VERTICALS work can later override per vertical.
TIPOUT_CONTRIBUTE_ROLES = {'Server', 'Bartender'}
TIPOUT_SUPPORT_ROLES = {'Event Lead', 'Security/Parking'}

# (value, label, help) for the per-event tip-model selector.
TIP_MODEL_CHOICES = [
    ('equal_pool', 'Equal Pool (hours-weighted)',
     'All tips pooled, split across the crew by hours worked.'),
    ('keep_own', 'Keep Your Own',
     'Each staffer keeps the tips they personally logged. No redistribution.'),
    ('tipout_pct', 'Tip-Out % to Support',
     'Servers/Bartenders keep their tips minus a set % that pools to Event Lead/Security.'),
]
TIP_MODEL_VALUES = {v for v, _, _ in TIP_MODEL_CHOICES}


def _normalize_tipout_rate(raw):
    """Return a fraction in [0,1]. Tolerates both seed conventions: 0.20 and 20.0
    (and 20 percentage points typed as 20). Values > 1 are treated as percent."""
    try:
        r = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    if r > 1:
        r = r / 100.0
    if r < 0:
        r = 0.0
    if r > 1:
        r = 1.0
    return r


def _event_tip_model(c, event_id):
    """Resolve the tip model for an event: the event's own setting wins; fall back
    to the venue-wide default in venue_config; final fallback 'equal_pool'."""
    c.execute('SELECT tip_model FROM events WHERE id = ?', (event_id,))
    row = c.fetchone()
    model = (row['tip_model'] if row and row['tip_model'] else '').strip()
    if model in ('equal_pool', 'keep_own', 'tipout_pct'):
        return model
    c.execute('SELECT tip_model FROM venue_config WHERE id = 1')
    cfg = c.fetchone()
    model = (cfg['tip_model'] if cfg and cfg['tip_model'] else '').strip()
    return model if model in ('equal_pool', 'keep_own', 'tipout_pct') else 'equal_pool'


def distribute_event_tips(event_id):
    """Compute and persist per-staff tip shares for one event, using the event's
    selected tip model. Clears any prior calc for the event first.

    Models:
      - equal_pool: pool every logged tip, split hours-weighted across participants
        (confirmed crew UNION tip-loggers). Missing hours imputed at crew average;
        if nobody logged hours, split evenly.
      - keep_own: no redistribution; each staffer's share = the tips they logged.
      - tipout_pct: contributors (Server/Bartender) keep their own logged tips minus
        a rate; the withheld amount pools to support roles (Event Lead/Security),
        split hours-weighted. No support staff present => no tip-out taken.

    Returns dict: {ok, model, pool_total, rows:[...], basis, error}.
    """
    conn = get_db()
    c = conn.cursor()

    model = _event_tip_model(c, event_id)

    # Pool = sum of all tips logged for this event.
    c.execute('SELECT COALESCE(SUM(amount), 0) AS pool FROM tip_entries WHERE event_id = ?',
              (event_id,))
    pool_total = float(c.fetchone()['pool'] or 0)

    # Participants = confirmed crew on the event UNION anyone who logged a tip for it.
    c.execute('''SELECT DISTINCT s.id AS staff_id, s.name, s.role
                 FROM staff s
                 WHERE s.id IN (
                     SELECT staff_id FROM event_staffing
                     WHERE event_id = ? AND confirmed = 1
                     UNION
                     SELECT staff_id FROM tip_entries WHERE event_id = ?
                 )''', (event_id, event_id))
    participants = c.fetchall()

    if pool_total <= 0 or not participants:
        conn.close()
        return {'ok': False, 'model': model, 'pool_total': pool_total, 'rows': [],
                'basis': 'none',
                'error': 'No tips logged for this event yet.' if pool_total <= 0
                         else 'No confirmed crew or tip-loggers on this event.'}

    # Per-participant logged tips (their own contribution to the pool).
    own = {}
    for p in participants:
        c.execute('SELECT COALESCE(SUM(amount), 0) AS a FROM tip_entries '
                  'WHERE staff_id = ? AND event_id = ?', (p['staff_id'], event_id))
        own[p['staff_id']] = float(c.fetchone()['a'] or 0)

    # Hours per participant (None => no timesheet hours logged for this event).
    hours = {}
    for p in participants:
        c.execute('SELECT COALESCE(SUM(total_hours), 0) AS h FROM timesheet_entries '
                  'WHERE staff_id = ? AND event_id = ?', (p['staff_id'], event_id))
        h = float(c.fetchone()['h'] or 0)
        hours[p['staff_id']] = h if h > 0 else None

    now = datetime.utcnow().isoformat()
    shares = {}      # staff_id -> dollars
    hours_used = {}  # staff_id -> hours figure stored for transparency
    imputed = {}     # staff_id -> bool

    def _hours_weighted(ids, amount):
        """Split `amount` across `ids` weighted by hours; impute missing at the
        average of those who have hours; even split if nobody does. Mutates
        hours_used/imputed for the ids and returns {id: dollars}."""
        sub = {i: hours[i] for i in ids}
        real = [h for h in sub.values() if h is not None]
        avg = (sum(real) / len(real)) if real else None
        w = {}
        for i, h in sub.items():
            if h is not None:
                w[i] = h
                hours_used[i] = round(h, 2)
                imputed[i] = False
            elif avg is not None:
                w[i] = avg
                hours_used[i] = round(avg, 2)
                imputed[i] = True
            else:
                w[i] = 1.0
                hours_used[i] = 0.0
                imputed[i] = True
        total_w = sum(w.values()) or 1.0
        out, running, ordered = {}, 0.0, list(ids)
        for idx, i in enumerate(ordered):
            if idx < len(ordered) - 1:
                d = round(amount * (w[i] / total_w), 2)
                running += d
            else:
                d = round(amount - running, 2)  # last absorbs rounding remainder
            out[i] = d
        return out

    all_ids = [p['staff_id'] for p in participants]

    if model == 'keep_own':
        basis = 'keep_own'
        for sid in all_ids:
            shares[sid] = round(own[sid], 2)
            hours_used[sid] = round(hours[sid], 2) if hours[sid] is not None else 0.0
            imputed[sid] = False

    elif model == 'tipout_pct':
        basis = 'tipout'
        c.execute('SELECT tipout_rate FROM venue_config WHERE id = 1')
        rcfg = c.fetchone()
        rate = _normalize_tipout_rate(rcfg['tipout_rate'] if rcfg else 0)
        roles = {p['staff_id']: p['role'] for p in participants}
        support_ids = [i for i in all_ids if roles.get(i) in TIPOUT_SUPPORT_ROLES]
        # Contributors give up `rate` of their own tips IF there's support to receive it.
        tipout_pool = 0.0
        for sid in all_ids:
            if roles.get(sid) in TIPOUT_CONTRIBUTE_ROLES and support_ids:
                contrib = round(own[sid] * rate, 2)
                shares[sid] = round(own[sid] - contrib, 2)
                tipout_pool += contrib
            else:
                # Non-contributors (and contributors when no support present) keep own.
                shares[sid] = round(own[sid], 2)
            hours_used[sid] = round(hours[sid], 2) if hours[sid] is not None else 0.0
            imputed[sid] = False
        if support_ids and tipout_pool > 0:
            for sid, d in _hours_weighted(support_ids, round(tipout_pool, 2)).items():
                shares[sid] = round(shares.get(sid, 0.0) + d, 2)

    else:  # equal_pool (default)
        model = 'equal_pool'
        dist = _hours_weighted(all_ids, pool_total)
        real = [h for h in hours.values() if h is not None]
        basis = 'hours' if real else 'even'
        for sid in all_ids:
            shares[sid] = dist[sid]

    # Persist: clear any prior calc for this event, then insert fresh rows.
    c.execute('DELETE FROM tip_distributions WHERE event_id = ?', (event_id,))
    rows = []
    for p in participants:
        sid = p['staff_id']
        share = shares.get(sid, 0.0)
        hu = hours_used.get(sid, 0.0)
        im = 1 if imputed.get(sid) else 0
        c.execute('INSERT INTO tip_distributions '
                  '(id, event_id, staff_id, tip_model, hours_used, hours_imputed, '
                  'pool_total, share_amount, calculated_at) '
                  'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (str(uuid.uuid4()), event_id, sid, model, hu, im,
                   pool_total, share, now))
        rows.append({'staff_id': sid, 'name': p['name'], 'role': p['role'],
                     'hours': hu, 'imputed': bool(im), 'own': round(own[sid], 2),
                     'share': share})

    conn.commit()
    conn.close()
    return {'ok': True, 'model': model, 'pool_total': round(pool_total, 2),
            'rows': rows, 'basis': basis, 'error': None}


def handle_tip(phone: str, body: str):
    """Handle 'TIP [amount]' SMS command."""
    m = re.match(r'^TIP\s+(\d+(?:\.\d{1,2})?)', body.strip(), re.IGNORECASE)
    if not m:
        return ("To log a tip, reply TIP followed by the amount.\n"
                "Example: TIP 45.00\n"
                "For cash tips, reply TIP [amount].\n"
                "Example: TIP 25"), None

    amount = float(m.group(1))
    if amount <= 0:
        return "Amount must be greater than $0.", None

    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    if not staff:
        conn.close()
        return "I don't recognize that phone number. Please contact your manager.", None

    staff_id = staff['id']
    staff_name = staff['name']
    today = datetime.utcnow().strftime('%Y-%m-%d')

    status, event = resolve_staff_event(c, staff_id)
    if status == 'none':
        conn.close()
        return ("You're not assigned to an event around today, so there's no tip pool to add "
                "this to. Please contact your coordinator."), None
    if status == 'multiple':
        conn.close()
        return ("You're assigned to more than one event right now, so I can't tell which tip "
                "pool this belongs to. Please contact your coordinator."), None
    event_id = event['id']
    event_name = event['name']

    # Get tip pool config (single source of truth = venue_config; venue_settings retired)
    c.execute('SELECT tip_pool_enabled, tip_model FROM venue_config WHERE id=1')
    cfg = c.fetchone()
    tip_pool = cfg['tip_pool_enabled'] if cfg else 0
    tip_model = cfg['tip_model'] if cfg else 'equal_pool'
    conn.close()

    tip_id = str(uuid.uuid4())
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO tip_entries (id, staff_id, event_id, amount, tip_type, recorded_at)
                 VALUES (?, ?, ?, ?, 'cash', ?)''',
              (tip_id, staff_id, event_id, amount, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    msg = (f"✅ Tip recorded: ${amount:.2f}\nEvent: {event_name}\nStaff: {staff_name}")
    if tip_pool and event_id and tip_model == 'equal_pool':
        msg += ("\nAdded to the event tip pool — your final share is split by "
                "hours worked and calculated at event close.")
    elif tip_pool and event_id:
        msg += "\nAdded to the event tip pool."
    return msg, None

# ─── Incident Handler ──────────────────────────────────────────────────────────

def handle_incident(phone: str, body: str):
    """Handle 'INCIDENT [description]' SMS command."""
    m = re.match(r'^INCIDENT\s+(.+)', body.strip(), re.IGNORECASE)
    if not m:
        return ("To report an incident, reply INCIDENT followed by a description.\n"
                "Example: INCIDENT Guest became aggressive.\n\n"
                "Severity levels: LOW | MEDIUM | HIGH — include if needed.\n"
                "Example: INCIDENT HIGH Guest complaint."), None

    raw_desc = m.group(1).strip()
    upper_desc = raw_desc.upper()
    if 'CRITICAL' in upper_desc or 'EMERGENCY' in upper_desc or 'ALCOHOL' in upper_desc:
        severity = 'high'
    elif 'HIGH' in upper_desc or 'AGGRESSIVE' in upper_desc:
        severity = 'medium'
    else:
        severity = 'low'

    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    if not staff:
        conn.close()
        return "I don't recognize that phone number. Please contact your manager.", None

    staff_id = staff['id']
    staff_name = staff['name']
    status, event = resolve_staff_event(c, staff_id)
    if status == 'none':
        conn.close()
        return ("You're not assigned to an event around today, so I can't file this incident "
                "against one. Please contact your coordinator."), None
    if status == 'multiple':
        conn.close()
        return ("You're assigned to more than one event right now, so I can't tell which this "
                "incident belongs to. Please contact your coordinator."), None
    event_id = event['id']
    event_name = event['name']

    incident_id = str(uuid.uuid4())
    c.execute('''INSERT INTO incidents (id, staff_id, event_id, description, severity, reported_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (incident_id, staff_id, event_id, raw_desc, severity, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    manager_phone = get_manager_phone()
    if manager_phone:
        sev_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}[severity]
        msg = (f"{sev_emoji} INCIDENT REPORT\n\nStaff: {staff_name}\n"
               f"Event: {event_name}\nSeverity: {severity.upper()}\nDescription: {raw_desc}")
        send_sms_alert(manager_phone, msg)

    sev_label = {'high': '🔴 HIGH', 'medium': '🟡 MEDIUM', 'low': '🟢 LOW'}[severity]
    return (f"✅ Incident logged.\nSeverity: {sev_label}\n"
            "Your manager has been notified. Thank you."), None

# ─── Shift Swap Request ───────────────────────────────────────────────────────

def handle_swap_request(phone: str, body: str):
    """Handle 'SWAP [event_id] [reason]' SMS command."""
    m = re.match(r'^SWAP\s+(\S+)(?:\s+(.+))?', body.strip(), re.IGNORECASE)
    if not m:
        return ("To request a shift swap, reply SWAP followed by the event ID and reason.\n"
                "Example: SWAP ABC123 Needs to attend a family event\n"
                "Your manager will review and respond."), None

    event_id = m.group(1).strip()
    reason = (m.group(2) or 'No reason provided').strip()

    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    if not staff:
        conn.close()
        return "I don't recognize that phone number. Please contact your manager.", None

    staff_id = staff['id']
    staff_name = staff['name']

    swap_id = str(uuid.uuid4())
    now = datetime.utcnow()
    c.execute('''INSERT INTO shift_swap_requests (id, staff_id, event_id, reason, status, created_at)
                 VALUES (?, ?, ?, ?, 'pending', ?)''',
              (swap_id, staff_id, event_id, reason, now.isoformat()))
    conn.commit()
    conn.close()

    manager_phone = get_manager_phone()
    if manager_phone:
        msg = (f"🔄 SHIFT SWAP REQUEST\n\nStaff: {staff_name}\n"
               f"Event ID: {event_id}\nReason: {reason}\n"
               "Reply APPROVE or DENY to this request.")
        send_sms_alert(manager_phone, msg)

    return (f"✅ Shift swap request submitted.\n"
            f"Event: {event_id}\nReason: {reason}\n"
            "Your manager has been notified. You'll receive a response shortly."), None

# ─── Performance Rating ───────────────────────────────────────────────────────

def handle_rating(phone: str, body: str):
    """Handle 'RATE [1-5] [comment]' SMS command."""
    m = re.match(r'^RATE\s+([1-5])(?:\s+(.+))?', body.strip(), re.IGNORECASE)
    if not m:
        return ("To rate your shift, reply RATE followed by a number 1-5 and an optional comment.\n"
                "Example: RATE 5 Great team atmosphere!\n"
                "5 = Excellent | 1 = Poor"), None

    rating = int(m.group(1))
    comment = (m.group(2) or '').strip()
    today = datetime.utcnow().strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()
    staff = find_staff_by_phone(c, phone)
    if not staff:
        conn.close()
        return "I don't recognize that phone number.", None

    staff_id = staff['id']

    # Find today's event
    c.execute('''SELECT e.id, e.name FROM events e
                 JOIN event_staffing es ON es.event_id=e.id
                 WHERE es.staff_id=? AND es.confirmed=1 AND e.date=?
                 LIMIT 1''', (staff_id, today))
    event = c.fetchone()
    event_id = event['id'] if event else None

    rating_id = str(uuid.uuid4())
    c.execute('''INSERT INTO performance_ratings (id, staff_id, event_id, rating, comment, recorded_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (rating_id, staff_id, event_id, rating, comment, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    stars = '⭐' * rating
    return (f"✅ Rating recorded: {stars}\n"
            f"Comment: {comment if comment else '(no comment)'}\n"
            "Thank you for your feedback!"), None

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
            # Behind Render's proxy, rebuild the exact public URL Twilio signed.
            url = os.environ.get('TWILIO_WEBHOOK_URL', '').strip() or request.url
            if url.startswith('http://'):
                url = 'https://' + url[len('http://'):]
            if not validator.validate(url, request.form, signature):
                app.logger.warning('Twilio signature validation failed')
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
            elif upper_body in ('EXIT', 'QUIT'):
                answer, next_step = quit_onboarding(from_number)
            else:
                answer, next_step = handle_onboarding_state(from_number, body, row)
        elif upper_body == 'START' or upper_body.startswith('START '):
            answer, next_step = start_onboarding(from_number, body)
        elif upper_body in ('HELP', 'FAQ', '?'):
            answer, next_step = HELP_TEXT, None
        elif upper_body == 'STATUS':
            answer, next_step = get_onboarding_status(from_number)
        elif upper_body in ('EXIT', 'QUIT'):
            answer, next_step = quit_onboarding(from_number)
        elif upper_body in ('IN', 'OUT'):
            if upper_body == 'IN':
                answer, next_step = handle_clock(from_number, body, 'IN')
            else:
                answer, next_step = handle_clock(from_number, body, 'OUT')
        elif upper_body in ('YES', 'NO', 'Y', 'N'):
            answer = handle_break_response(from_number, body)
            next_step = None
        elif upper_body.startswith('BREAK'):
            answer = "Reply YES to start a break, or NO to cancel."
            next_step = None
        elif upper_body.startswith('TIP'):
            answer, next_step = handle_tip(from_number, body)
        elif upper_body.startswith('INCIDENT'):
            answer, next_step = handle_incident(from_number, body)
        elif upper_body.startswith('SWAP'):
            answer, next_step = handle_swap_request(from_number, body)
        elif upper_body.startswith('RATE '):
            answer, next_step = handle_rating(from_number, body)
        elif upper_body.startswith('PAYROLL'):
            link = request.host_url + 'admin/payroll_export'
            answer = (f"Payroll Export\n\nDownload your payroll report:\n{link}\n"
                      "This link covers the current month.")
            next_step = None
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

STAGES = ['WELCOME', 'START_RECEIVED', 'DOB_VERIFIED', 'BASIC_INFO', 'TAX_INFO', 'PAYROLL', 'COMPLETE']

HELP_TEXT = ("Commands:\n"
             "START [DOB] - Begin onboarding (e.g. START 01/15/2000)\n"
             "STATUS - See your onboarding progress\n"
             "BACK - Go to previous step\n"
             "EXIT - Exit and save progress\n"
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
    c.execute('''INSERT INTO onboarding_state (phone, step, data_json, dob, assigned_role, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT (phone) DO UPDATE SET
                     step = EXCLUDED.step,
                     data_json = EXCLUDED.data_json,
                     dob = EXCLUDED.dob,
                     assigned_role = EXCLUDED.assigned_role,
                     updated_at = EXCLUDED.updated_at''',
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
    if upper_body in ('EXIT', 'QUIT'):
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
    data['step'] = 'PAYROLL'
    save_onboarding_state(phone, 'PAYROLL', data)
    return ("Great!\n\n"
            "Finally, Payroll.\n\n"
            "Do you have Direct Deposit set up?\n\n"
            "Reply YES if you want to provide bank info now, or REPLY LATER to skip."), 'PAYROLL'

# ─── PARKED: SMS compliance-photo capture (badge photo via MMS) ───────────────────
# Removed from the live onboarding flow Jun 23. The previous handler was a STUB:
# it replied "photo received" without ever reading, downloading, or storing an
# image. Real capture is a future build (read NumMedia / MediaUrl0 from the
# inbound webhook, fetch from Twilio with auth, store base64 in Postgres like the
# signed onboarding docs). To re-enable: restore 'COMPLIANCE_PHOTOS' in STAGES /
# step_order / status maps, point collect_tax_info's next step back to it, and
# implement the real handler below. See Master Brief backlog entry.
#
# def collect_compliance_photos(phone, body, data, role, dob):
#     # Body contains media URL if photo was sent, or a text response
#     num_photos = data.get('photo_count', 0) + 1
#     data['photo_count'] = num_photos
#     data['step'] = 'PAYROLL'
#     save_onboarding_state(phone, 'PAYROLL', data)
#     return ("Thanks! Your compliance photo has been received.\n\n"
#             "Finally, Payroll.\n\n"
#             "Do you have Direct Deposit set up?\n\n"
#             "Reply YES if you want to provide bank info now, or REPLY LATER to skip."), 'PAYROLL'

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
    step_order = ['WELCOME', 'START_RECEIVED', 'DOB_VERIFIED', 'BASIC_INFO', 'TAX_INFO', 'PAYROLL', 'COMPLETE']
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
        'PAYROLL': 'Payroll',
    }

    status = f"Step: {steps_display.get(step, step)}\nRole: {role}\n\n"
    remaining = {
        'DOB_VERIFIED': 'Basic Info, Tax Documents, Payroll',
        'BASIC_INFO': 'Tax Documents, Payroll',
        'TAX_INFO': 'Payroll',
        'PAYROLL': 'Finish up!',
    }
    if step in remaining:
        status += f"Remaining: {remaining[step]}\n\n"
    status += "Reply BACK to go to previous step, or EXIT to save and exit."

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
    c.execute('''INSERT INTO onboarding_state (phone, step, data_json, dob, assigned_role, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT (phone) DO UPDATE SET
                     step = EXCLUDED.step,
                     data_json = EXCLUDED.data_json,
                     dob = EXCLUDED.dob,
                     assigned_role = EXCLUDED.assigned_role,
                     updated_at = EXCLUDED.updated_at''',
             (phone, step, json.dumps(merged), dob, assigned_role, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# ─── Public Pages ─────────────────────────────────────────────────────────────

@app.route('/roadmap')
def roadmap():
    """Serve the project roadmap."""
    with open(os.path.join(app.root_path, 'ROADMAP.md'), 'r') as f:
        content = f.read()
    return make_response(content, 200, {'Content-Type': 'text/markdown'})

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

# Ensure the schema exists at import time so tables are created under gunicorn
# on Render, where __main__ never runs. Idempotent (CREATE TABLE IF NOT EXISTS +
# ON CONFLICT DO NOTHING seeds), so repeated/concurrent worker startup is safe.
try:
    init_db()
except Exception:
    import traceback
    traceback.print_exc()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
