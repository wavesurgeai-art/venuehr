#!/usr/bin/env python3
"""Seed VenueHR with realistic test data:
   - 3 admin users (Owner, Coordinator, Administrator)
   - 20 potential hires (bartenders, servers)
   - 6 contractors (Caterer, Photographer, DJ, Florist, Videographer, Officiant)
"""
import sqlite3, uuid, os
from datetime import datetime, date

DB_PATH = '/home/team/shared/hraas.db'
VENUE_ID = 'default'

def d(sym, m, dy):
    dt = date(2025, m, dy)
    return dt.isoformat()

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ── Admin / Staff Records ─────────────────────────────────────────────────────

STAFF = [
    # ── Owner ──────────────────────────────────────────────────────────────
    ('owner-001', VENUE_ID, 'Margaret E. Hollister',    'margaret@wavesurgeai.com',    '+1 317-555-0101', 'Owner',              d(0,3,1),  uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    # ── Coordinator ───────────────────────────────────────────────────────
    ('coord-001', VENUE_ID, 'Tyler J. Brennan',         'tyler@wavesurgeai.com',       '+1 317-555-0102', 'Coordinator',        d(0,3,15), uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    # ── Administrator ──────────────────────────────────────────────────────
    ('admin-001', VENUE_ID, 'Samantha R. Whitfield',     'samantha@wavesurgeai.com',    '+1 317-555-0103', 'Administrator',      d(0,4,1),  uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),

    # ── Bartenders ────────────────────────────────────────────────────────
    ('bart-001', VENUE_ID, 'Darius L. Morrison',         'dmorrison@gmail.com',         '+1 317-555-0201', 'Bartender',          d(0,5,10), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('bart-002', VENUE_ID, 'Caitlin M. O\'Brien',        'cobrien@gmail.com',           '+1 317-555-0202', 'Bartender',          d(0,5,12), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('bart-003', VENUE_ID, 'Ethan R. Caldwell',           'ecaldwell@gmail.com',         '+1 317-555-0203', 'Bartender',          d(0,5,14), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('bart-004', VENUE_ID, 'Nia K. Franklin',            'nia.franklin@gmail.com',      '+1 317-555-0204', 'Bartender',          d(0,5,16), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),

    # ── Servers ────────────────────────────────────────────────────────────
    ('serv-001', VENUE_ID, 'Brandon T. Holloway',        'bholloway@gmail.com',         '+1 317-555-0301', 'Server',             d(0,6,1),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-002', VENUE_ID, 'Kayla D. Seymour',           'kseymour@gmail.com',          '+1 317-555-0302', 'Server',             d(0,6,3),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-003', VENUE_ID, 'Marcus J. Navarro',          'mnavarro@gmail.com',          '+1 317-555-0303', 'Server',             d(0,6,5),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-004', VENUE_ID, 'Aaliyah B. Reyes',           'areyes@gmail.com',            '+1 317-555-0304', 'Server',             d(0,6,7),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-005', VENUE_ID, 'Jordan L. Cummins',         'jcummins@gmail.com',          '+1 317-555-0305', 'Server',             d(0,6,9),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-006', VENUE_ID, 'Amara S. Patel',             'apatel@gmail.com',            '+1 317-555-0306', 'Server',             d(0,6,11), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-007', VENUE_ID, 'Tyler Q.华盛顿',            't washington@gmail.com',      '+1 317-555-0307', 'Server',             d(0,6,13), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-008', VENUE_ID, 'Destiny R. Garcia',          'dgarcia@gmail.com',           '+1 317-555-0308', 'Server',             d(0,6,15), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-009', VENUE_ID, 'Andre M. Lawson',            'alawson@gmail.com',           '+1 317-555-0309', 'Server',             d(0,6,17), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-010', VENUE_ID, 'Imani C. Brooks',            'imbrooks@gmail.com',          '+1 317-555-0310', 'Server',             d(0,6,19), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-011', VENUE_ID, 'Kevin J. Fletcher',          'kfletcher@gmail.com',        '+1 317-555-0311', 'Server',             d(0,6,21), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-012', VENUE_ID, 'Jasmine L. Ortega',         'jortega@gmail.com',           '+1 317-555-0312', 'Server',             d(0,6,23), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-013', VENUE_ID, 'Noah P. Santiago',           'nsantiago@gmail.com',         '+1 317-555-0313', 'Server',             d(0,6,25), uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-014', VENUE_ID, 'Maya T. Underwood',          'munderwood@gmail.com',        '+1 317-555-0314', 'Server',             d(0,7,1),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-015', VENUE_ID, 'Luis A. Vega',               'lvega@gmail.com',             '+1 317-555-0315', 'Server',             d(0,7,3),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
    ('serv-016', VENUE_ID, 'Rachel K. Newman',          'rnewman@gmail.com',           '+1 317-555-0316', 'Server',             d(0,7,5),  uuid.uuid4().hex, 'pending', datetime.utcnow().isoformat()),
]

CONTRACTORS = [
    ('cont-001', VENUE_ID, 'Gourmet & Grace Catering — Rachel Stern',    'rachel@gourmetgrace.com',        '+1 317-555-0401', 'Caterer',       d(0,1,15), uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    ('cont-002', VENUE_ID, 'Focus & Light Photography — David Chen',      'david@focuslightphoto.com',       '+1 317-555-0402', 'Photographer',  d(0,1,20), uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    ('cont-003', VENUE_ID, 'BeatDrop DJ Services — Marcus Thompson',       'marcus@beatdropservices.com',    '+1 317-555-0403', 'DJ',            d(0,2,1),  uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    ('cont-004', VENUE_ID, 'Bloom & Wild Florals — Aisha Williams',        'aisha@bloomwildflorals.com',     '+1 317-555-0404', 'Florist',       d(0,2,5),  uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    ('cont-005', VENUE_ID, 'Cinema Stories Videography — Jose Rivera',      'jose@cinemastories.com',         '+1 317-555-0405', 'Videographer',  d(0,2,10), uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
    ('cont-006', VENUE_ID, 'Ceremony & Soul Officiant — Rev. Patricia Cole','patricia@ceremonyandsoul.com',   '+1 317-555-0406', 'Officiant',     d(0,2,15), uuid.uuid4().hex, 'signed', datetime.utcnow().isoformat()),
]

INSERT_SQL = """INSERT OR IGNORE INTO staff (id, venue_id, name, email, phone, role, hire_date, onboarding_token, agreement_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

all_records = STAFF + CONTRACTORS
for row in all_records:
    c.execute(INSERT_SQL, row)

conn.commit()
print(f"✅ Seeded {len(STAFF)} staff members + {len(CONTRACTORS)} contractors = {len(all_records)} total")

# Quick count
c.execute("SELECT role, COUNT(*) FROM staff GROUP BY role")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")
conn.close()