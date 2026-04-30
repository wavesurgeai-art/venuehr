# HRaaS Platform for Wedding Venues — Specification

## Overview

**Product Name:** VenueHR — Staff Management & Compliance Platform  
**Type:** HR as a Service (HRaaS) Web Application  
**Core Functionality:** Enable wedding venues to onboard staff, distribute Staff Uniform & Professional Conduct Agreements, capture digital signatures, and track compliance via an admin dashboard.  
**Target Users:** Wedding venue managers (admins) and event staff (employees)

---

## 1. Architecture

### Stack
- **Backend:** Python Flask (lightweight, SQLite-compatible)
- **Database:** SQLite via `team-db` / Turso
- **Frontend:** HTML5 + Tailwind CSS (via CDN) + vanilla JavaScript
- **Digital Signatures:** Canvas-based signature pad (no external service required)
- **File Storage:** Local filesystem (`/home/team/shared/uploads/`)

### Application Structure
```
/home/team/shared/
├── SPEC.md
├── app.py                  # Flask application entry point
├── hraas.db                # SQLite database (gitignored, managed via team-db)
├── templates/              # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── admin_dashboard.html
│   ├── staff_list.html
│   ├── staff_detail.html
│   ├── agreement.html
│   ├── view_agreement.html
│   ├── onboard_thanks.html
│   ├── faq_page.html       # Public FAQ for staff
│   ├── faq_search.html    # FAQ search results
│   ├── admin_faqs.html    # Admin FAQ management
│   └── admin_faq_edit.html # Admin FAQ edit form
├── static/
│   └── uploads/            # Signature images
└── requirements.txt
```

---

## 2. Features & Workflows

### 2.1 Admin Authentication
- Simple PIN-based login for venue managers (stored hashed in DB)
- Default admin PIN set via environment variable or first-run setup
- Session management with Flask-Login

### 2.2 Staff Onboarding Workflow
1. **Admin creates staff record** — name, email, phone, role (bartender, server, coordinator, etc.), hire date
2. **System generates unique onboarding link** — sent via email placeholder (displayed to admin to copy)
3. **Staff member clicks link** — lands on agreement page
4. **Staff reads and signs agreement** — full legal text displayed, canvas signature captured
5. **Signed agreement stored** — timestamp, IP address, signature image
6. **Admin notified** — dashboard shows pending/completed agreements

### 2.3 Staff Uniform & Professional Conduct Agreement
The agreement text (all 4 sections):

**Section 1: Brand Standard (Uniform)**
> Our clients are paying for a "once-in-a-lifetime" experience. As a member of the service team, you are part of the decor.
> 
> **The Look:** Solid black button-down shirt, black dress slacks, and black non-slip dress shoes.
> 
> **Grooming:** Clothing must be pressed, clean, and free of lint or pet hair.
> 
> **Visible Items:** No visible headphones/AirPods, heavy fragrances, or excessive jewelry that interferes with service.

**Section 2: The "Invisible" Service Standard**
> The best service is the kind the guests don't notice until they need something.
> 
> **Cell Phone Policy:** Cell phones are to be kept in the staff locker or your vehicle. No texting or social media use is permitted on the floor.
> 
> **Guest Interaction:** Always yield the right of way to guests. If a guest asks a question you cannot answer, say: "I will find out for you immediately," and alert the Lead Coordinator.
> 
> **Consumption:** No eating, drinking (other than water in designated areas), or smoking/vaping is permitted in view of guests.

**Section 3: Professional Boundaries**
> The "No-Fraternization" Rule: You are there to serve the wedding, not join it. Do not accept drinks from guests, do not join the dance floor, and do not request photos with the wedding party or high-profile guests.
> 
> **Alcohol Service:** If you are a bartender, you must strictly adhere to Indiana ATC guidelines. Never "over-pour" for a guest, and never consume alcohol during or after your shift on venue property.

**Section 4: Social Media & Privacy**
> **Privacy:** Do not post photos or videos of the wedding party, their decor, or their guests to your personal social media accounts without explicit permission from the Venue Manager.
> 
> **Confidentiality:** Respect the privacy of our clients. What you hear or see at a private event stays at the event.

### 2.4 Admin Dashboard
- **Compliance Overview:** Total staff, pending agreements, signed agreements, expired (if renewal enabled)
- **Staff Roster Table:** Name, role, hire date, agreement status, actions (view, resend link)
- **Quick Stats Cards:** Visual indicators of compliance rate
- **Filter/Search:** By name, role, agreement status

### 2.5 Staff Portal (Onboarding Link)
- Read-only agreement display
- Digital signature canvas
- Acknowledgment checkbox ("I have read and agree to the terms")
- Submit → redirects to thank-you page

---

## 3. Database Schema

### Tables

**admins**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| name | TEXT | Admin's name |
| pin_hash | TEXT | bcrypt hash of PIN |
| created_at | TEXT | ISO timestamp |

**staff**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| venue_id | TEXT | FK to config.venue_id |
| name | TEXT | Staff full name |
| email | TEXT | Email address |
| phone | TEXT | Phone number |
| role | TEXT | bartender/server/coordinator/other |
| hire_date | TEXT | YYYY-MM-DD |
| onboarding_token | TEXT | Unique token for onboarding link |
| agreement_status | TEXT | pending/signed/expired |
| created_at | TEXT | ISO timestamp |

**agreements**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| staff_id | TEXT | FK to staff.id |
| signed_at | TEXT | ISO timestamp |
| ip_address | TEXT | Signer's IP |
| signature_image | TEXT | Path to signature PNG |
| agreement_text | TEXT | Snapshot of agreement content at signing |

**faqs**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| category | TEXT | FAQ category (Logistics, Schedule, etc.) |
| question | TEXT | Question text |
| answer | TEXT | Answer text |
| keywords | TEXT | Comma-separated keyword tags for search |
| created_at | TEXT | ISO timestamp |

**onboarding_state**
| Column | Type | Description |
|--------|------|-------------|
| phone | TEXT | Primary key — staff phone number |
| step | TEXT | Current state: WELCOME → START_RECEIVED → DOB_VERIFIED → BASIC_INFO → TAX_INFO → COMPLIANCE_PHOTOS → PAYROLL → COMPLETE |
| data_json | TEXT | JSON blob — collected name, email, role, photo count, payroll choice |
| dob | TEXT | Date of birth (MM/DD/YYYY) |
| assigned_role | TEXT | Server (18+) or Bartender/Lead (21+) |
| updated_at | TEXT | ISO timestamp |

**venue_config**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key (always 1) |
| venue_name | TEXT | Venue display name used in SMS messages |

---

## 4. SMS Onboarding Bot

The platform includes a **conversational SMS onboarding bot** accessible via Twilio webhooks at `/sms/webhook`.

### Welcome Message (exact text sent on START)
```
Hi [Employee Name]! Congratulations on joining the team at [Venue Name]. I am your AI Onboarding Assistant. My job is to get you set up in our system as quickly as possible so you can get on the schedule and get paid. To stay compliant with Indiana labor laws and venue safety standards, I'm going to guide you through a few quick steps. Here is what we need to tackle today: Basic Info, Tax Documents, Compliance, Payroll. This usually takes about 5-10 minutes. You can stop and start at any time — I'll remember where we left off. Whenever you're ready to start, just reply with 'START' and your Date of Birth (MM/DD/YYYY).
```

### State Machine
```
WELCOME → START_RECEIVED → DOB_VERIFIED → BASIC_INFO → TAX_INFO → COMPLIANCE_PHOTOS → PAYROLL → COMPLETE
```

### Role Assignment Logic
- **18+** → Server role
- **21+** → Bartender/Lead role
- **Under 18** → Rejected with contact-manager message

### Commands
| Command | Description |
|---------|-------------|
| `START [DOB]` | Begin onboarding (e.g. `START 01/15/2000`) |
| `BACK` | Go back one step |
| `STATUS` | Show current step and remaining items |
| `QUIT` | Save progress and pause |
| `HELP` | Show command list |
| (any other text) | Falls back to FAQ auto-reply |

### Admin View
The `/admin` dashboard includes an **Onboarding Status** table showing all active SMS onboarding sessions — phone, assigned role, current step, and last update time.

---

## 5. Staffing Matrix

Venue managers can create events, assign staff, and calculate required headcount using staffing ratios.

### Staffing Ratios
| Role | Ratio |
|------|-------|
| Servers | 1 per 20 guests |
| Bartenders | 1 per 50 guests |
| Event Leads | 1 if event exceeds 50 guests |
| Security/Parking | 1 per 100 guests |

### New Tables
**events** — stores event metadata (date, name, guest_count)

**event_staffing** — tracks which staff are assigned to which event and whether confirmed

**availability_requests** — logs broadcast SMS sent to staff asking for availability

### Routes
- `GET /admin/staffing` — Staffing calculator with event list and create form
- `GET /admin/staffing/<event_id>` — Per-event staffing plan with required vs. assigned counts, gap detection, and assign/confirm/remove actions
- `POST /admin/staffing/<event_id>/broadcast` — Sends availability SMS to all unassigned staff; staff reply CONFIRM or DECLINE (Twilio required)
- `GET/POST /admin/events` — Event management (list/create)

---

## 6. Timesheet & Payroll

Staff clock in/out via SMS (text IN/OUT) and managers export payroll as CSV.

### SMS Commands
| Command | Description |
|---------|-------------|
| `IN` | Clock in (verifies staff is on confirmed list for today's event) |
| `OUT` | Clock out, calculates hours (rounded to nearest 15 min), asks break compliance |
| `YES/NO` | Respond to breaktaken compliance question |
| `PAYROLL EXPORT` | Reply with link to CSV download |

### Clock-In Rules
- Staff must be on the **confirmed** staff list for **today's event**
- Already-clock-in blocked with existing timestamp
- Records timestamp + GPS location if available

### Clock-Out Rules
- Calculates hours worked (rounded to nearest 15 min)
- Prompts for 30-minute break compliance (YES/NO)
- Break responses stored in `clock_entries.break_taken`

### Manager Alert
- If staff is clocked in 12+ hours with no clock-out → SMS alert to `venue_config.manager_phone`
- `manager_phone` added to `venue_config` table

### Payroll Export
- CSV columns: Employee ID | Name | Role | Date | Clock In | Clock Out | Hours Worked | Break Taken | Hourly Rate | Total Pay
- Default hourly rates: Bartender $18, Server $15, Event Lead $22, Security $16
- Rounds to nearest 15 min
- Admin downloads from `/admin/payroll_export`

### New Tables
- `clock_entries` — clock_in, clock_out, location, break_taken per staff/event
- `manager_alerts` — logs 12-hour shift alerts sent to manager

### Routes
- `GET /admin/timesheets` — Admin view of all timesheet entries
- `GET /admin/payroll_export` — Download payroll CSV
- `POST /sms/webhook` — Handles IN/OUT/YES/NO/PAYROLL EXPORT commands

---

## 7. API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Landing page |
| GET | `/login` | None | Admin login page |
| POST | `/login` | None | Process login |
| GET | `/logout` | Admin | End session |
| GET | `/admin` | Admin | Dashboard |
| GET | `/admin/staff` | Admin | Staff roster |
| POST | `/admin/staff` | Admin | Create staff record |
| GET | `/admin/staff/<id>` | Admin | View staff details |
| GET | `/admin/staff/<id>/agreement` | Admin | View signed agreement |
| POST | `/admin/staff/<id>/resend-link` | Admin | Regenerate onboarding link |
| GET | `/onboard/<token>` | Staff | Onboarding/agreement page |
| POST | `/onboard/<token>` | Staff | Submit signed agreement |
| GET | `/onboard/<token>/thanks` | Staff | Thank you page |
| GET | `/faq` | None | Public FAQ page for staff |
| GET | `/faq/search` | None | Search FAQs by keyword |
| GET | `/admin/faqs` | Admin | FAQ management dashboard |
| POST | `/admin/faqs/add` | Admin | Add new FAQ |
| GET | `/admin/faqs/<id>/edit` | Admin | Edit FAQ form |
| POST | `/admin/faqs/<id>/edit` | Admin | Submit FAQ edit |
| POST | `/admin/faqs/<id>/delete` | Admin | Delete FAQ |
| GET/POST | `/sms/webhook` | None | Twilio SMS webhook for auto-reply |

---

## 5. UI/UX Design

- **Style:** Clean, professional, minimal — matching wedding venue elegance
- **Colors:** White (#FFFFFF) background, charcoal (#374151) text, rose (#F43F5E) accent
- **Typography:** System sans-serif stack (clean, fast-loading)
- **Layout:** Centered card layout for forms; sidebar navigation for admin dashboard
- **Mobile:** Responsive, works on phones for staff signing on-the-go

---

## 6. Security Considerations

- PIN stored as bcrypt hash (not plaintext)
- Onboarding tokens are cryptographically random UUIDs
- Signature images stored outside web root, served via protected endpoint
- All forms CSRF-protected via Flask-WTF tokens
- Admin sessions expire after 8 hours of inactivity

---

## 7. Out of Scope (Phase 1)

- Email delivery (links displayed/copied manually)
- Multi-venue support (single venue per instance)
- Agreement version history
- PDF export of agreements
- Staff shift scheduling
- Payroll integration

---

## 8. FAQ Database

### Overview
A searchable knowledge base of frequently asked questions, accessible to staff via a public page or SMS auto-reply.

### Categories
- **Logistics** — Parking, check-in, venue directions
- **Schedule** — Shift times, time-off requests
- **Food & Beverage** — Staff meals, break areas, floor rules
- **Safety & Emergency** — Evacuation plans, medical emergencies
- **Task Specifics** — Bartender duties, guest interactions, phone policy, uniform

### Database Schema
**faqs**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT (UUID) | Primary key |
| category | TEXT | FAQ category |
| question | TEXT | Question text |
| answer | TEXT | Full answer |
| keywords | TEXT | Comma-separated keywords for SMS matching |
| created_at | TEXT | ISO timestamp |

### Staff FAQ Page (`/faq`)
- Public page accessible to all staff
- Questions grouped by category with collapsible accordions
- Real-time search bar filters FAQs by keyword
- Link shared in onboarding welcome message

### Admin FAQ Management (`/admin/faqs`)
- CRUD operations: Add, edit, delete FAQs
- Keyword field drives SMS auto-reply matching
- Instant updates to live FAQ and SMS responses

---

## 9. Staff SMS Auto-Reply (Twilio)

### Overview
When a staff member texts the venue's Twilio phone number, the system automatically replies with the most relevant FAQ answer.

### Configuration
Environment variables (set in production deployment):
- `TWILIO_ACCOUNT_SID` — Twilio Account SID
- `TWILIO_AUTH_TOKEN` — Twilio Auth Token
- `TWILIO_PHONE_NUMBER` — Venue's Twilio phone number

### Webhook Endpoint
**POST /sms/webhook** — Twilio posts incoming SMS here
**GET /sms/webhook** — Twilio validation request (returns 200)

### Auto-Reply Logic
1. Parse incoming SMS body (lowercase, stripped)
2. Search FAQ database using keyword scoring:
   - Exact keyword match: +3 points
   - Partial keyword match: +1 point
   - Query word appears in question/answer text: +0.5 point
3. Return best match with header: "Hi! Here's what I found in our FAQ:"
4. If no match: Return "contact your coordinator" message with FAQ page URL
5. Twilio signature validation enforced when credentials are set

### TwiML Response
Always returns valid TwiML (`MessagingResponse`) to acknowledge receipt to Twilio.
