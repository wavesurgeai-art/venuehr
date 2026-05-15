# VenueHR — Product Roadmap

**Last Updated:** May 2024  
**Version:** 1.0  

---

## Vision
VenueHR is an HRaaS (HR-as-a-Service) platform built for service-industry businesses that rely on hourly event or shift workers. The initial target is wedding venues; the platform is architected to expand to golf courses, landscaping, event staffing, hospitality, and any business with recurring seasonal workers who need onboarding, compliance tracking, scheduling, and payroll support.

---

## Product Tiers

### Essential — $49/month
- Staff roster (unlimited staff)
- Digital Staff Uniform & Professional Conduct Agreement with e-signature
- SMS Onboarding Bot (staff complete compliance steps via text)
- FAQ database with SMS auto-reply
- **Best for:** Small venues (1–2 events/week)

### Professional — $99/month
- Everything in Essential
- Staffing Matrix with event headcount calculator
- SMS availability broadcasts + CONFIRM/DECLINE routing
- Clock IN/OUT/BREAK SMS commands with break compliance tracking
- Incident & Issue Log with severity tracking
- Shift Swap Request system (SMS + admin approval)
- Tip Reporting + Tipout Calculator
- Performance Rating system
- Weekly payroll CSV export
- **Best for:** Mid-size venues (3–5 events/week)

### Enterprise — $199/month
- Everything in Professional
- **Multi-tenant management** — manage multiple venue locations under one account
- **QuickBooks Payroll API integration** — push timesheet data directly to QuickBooks Payroll
- **Scheduled SMS shift reminders** — automated day-before/event-day notifications via background scheduler
- Custom industry template library (Wedding, Golf, Landscaping, Events)
- API access for third-party integrations
- **Best for:** Large venues or multi-location operators (6+ events/week)

---

## Phase 1 — MVP Launch ✅ *(COMPLETE)*
**Goal:** Get a working product in the hands of the first wedding venue customer.

- [x] Staff Uniform & Professional Conduct Agreement (digital signature)
- [x] Staff roster with onboarding link generation
- [x] PIN-based admin authentication
- [x] SMS Onboarding Bot (state machine: DOB → role → tax → photo → payroll)
- [x] FAQ database with keyword SMS auto-reply
- [x] Staffing Matrix with headcount calculator and availability SMS broadcast
- [x] Clock IN/OUT/BREAK SMS commands with break compliance flagging
- [x] Tip Reporting + Tipout Calculator
- [x] Incident & Issue Log with severity detection
- [x] Shift Swap Request system with manager APPROVE/DENY
- [x] Performance Rating system (1–5 stars)
- [x] Weekly payroll CSV export
- [x] Event-triggered shift reminders (SMS broadcast on event day)
- [x] HR document templates (Agreement, Handbook, Onboarding Checklist, Customization Guide)
- [x] Landing page for Netlify

**Stack:** Flask + SQLite + Twilio SMS + Tailwind CSS  
**Deployed:** https://venuehr.onrender.com (PIN: 1234)  
**GitHub:** https://github.com/wavesurgeai-art/venuehr  

---

## Phase 2 — First Revenue & Customer Validation
**Goal:** Land first paying customer, gather real-world feedback.

- [ ] Set up Stripe billing (Essential/Professional/Enterprise tiers)
- [ ] Create terms of service and privacy policy
- [ ] Deploy landing page to Netlify
- [ ] Connect domain (venuehr.com or similar)
- [ ] First customer onboarding call + demo
- [ ] Collect testimonials and case study data

**Est. effort:** 5–8 hours + Stripe account approval

---

## Phase 3 — SaaS Multi-Tenancy
**Goal:** Allow multiple venues to self-serve on a single platform with isolated data.

- [ ] Tenant settings table (industry type, venue name, manager phone, branding)
- [ ] Staff/agreement/event data scoped by venue_id
- [ ] Tenant signup flow with industry selection
- [ ] Admin dashboard shows only current tenant's data
- [ ] White-label option (remove VenueHR branding per tenant)
- [ ] Multi-venue dashboard for Enterprise tier

**Depends on:** Phase 2 revenue milestone  
**Est. effort:** 15–20 hours

---

## Phase 4 — Payroll API Integrations
**Goal:** Push payroll data directly to QuickBooks, Gusto, ADP, or Paychex instead of manual CSV exports.

- [ ] QuickBooks Online OAuth registration with Intuit
- [ ] Timesheet data mapped to QuickBooks Payroll format
- [ ] Push-on-demand payroll export to QuickBooks
- [ ] Gusto API integration (alternative)
- [ ] ADP API integration (alternative)
- [ ] Webhook confirmation back to VenueHR

**Depends on:** 5+ paying customers with payroll needs  
**Est. effort:** 20–30 hours (per integration)  
**Note:** QuickBooks Payroll API requires a paid QuickBooks Payroll subscription on the customer's side

---

## Phase 5 — Industry Expansion
**Goal:** Serve golf courses, landscaping companies, event staffing agencies, and hospitality groups.

- [ ] Industry template library:
  - [ ] Wedding Venue — ✅ (live)
  - [ ] Golf Course — polo/khaki dress code, tee-time scheduling, cart assignments
  - [ ] Landscaping — safety gear, site check-in, equipment assignments
  - [ ] Event Staffing Agency — cross-venue staffing, credentialing
- [ ] Per-industry FAQ sets (pre-seeded)
- [ ] Per-industry staffing formulas (configurable ratios)
- [ ] Industry selector at signup (maps to correct templates + SMS wording)
- [ ] Custom agreement template builder (drag-and-drop clause library)

**Depends on:** 2+ non-wedding customers expressing interest  
**Est. effort:** 3–5 hours per industry, once the template structure is proven

---

## Phase 6 — Advanced Automation
**Goal:** Reduce manual management work for venue operators.

- [ ] Scheduled SMS shift reminders (cron-based, not event-triggered only)
- [ ] Automated onboarding follow-up SMS if staff hasn't completed steps
- [ ] Manager alert escalation (unresponded shift swap → text → email)
- [ ] Weekly payroll summary SMS to managers
- [ ] Performance-based auto-scheduling suggestions
- [ ] AI-powered FAQ answering (GPT integration for custom questions)

**Depends on:** Phase 3 (multi-tenancy) + customer demand  
**Est. effort:** 10–15 hours per feature

---

## Future Considerations

| Idea | Notes |
|---|---|
| Mobile app for staff | Push notifications for shift assignments |
| Worker self-schedule portal | Staff pick up open shifts |
| Background check integration | Checkr,轩 Global |
| Worker's comp insurance API | Policygenius, Simply Business |
| Tip pool splitting engine | Auto-calculate house take, tipouts per role |
| Tip reporting 1099 generation | Automate contractor tip tax forms |

---

## Twilio A2P 10DLC Status

- **Phone:** +1 (240) 916-2545
- **Campaign Status:** Pending approval
- **Action Required:** Await Twilio review email, then outgoing SMS fully functional
- **Workaround:** `DISABLE_TWILIO_VALIDATION=1` for local testing

---

## Platform Specs

- **Framework:** Flask (Python)
- **Database:** SQLite via Turso
- **SMS:** Twilio webhook (`/sms/webhook`)
- **Email:** Gmail SMTP (wavesurgeai@gmail.com)
- **Frontend:** Tailwind CSS (CDN), vanilla JS canvas signatures
- **Auth:** PIN-based admin (default 1234, bcrypt hashed)
- **Templates:** 22 HTML templates, Jinja2
- **Codebase:** ~1,700 lines in app.py

---

*End of Roadmap*
