# Campus Nexus & COORDINATE — System Documentation Hub

> **Institution:** National Institute of Technology Srinagar (NIT Srinagar)  
> **Platform Version:** 2.4.0 (Dual-Channel Verification & Mechanical Zen Release)  
> **Repository:** [Campus Nexus](https://github.com/abdus-samad-saiyed/Campus-Nexus)  
> **Maintainer:** Abdus Samad Saiyed (`2024BCSE065`)  

---

## 1. Documentation Structure & Sitemap

Welcome to the central documentation suite for **Campus Nexus** and its flagship transit module **COORDINATE**. This directory provides technical blueprints, security specifications, operational procedures, and API references.

| Document | Primary Audience | Core Topics Covered |
| :--- | :--- | :--- |
| [**`ARCHITECTURE.md`**](file:///s:/Campus-Project/docs/ARCHITECTURE.md) | Developers, Architects | Django 5 + Channels ASGI architecture, WebSockets, umbrella service catalogue, ERD database schema, and telemetry middleware. |
| [**`AUTHENTICATION_AND_SECURITY.md`**](file:///s:/Campus-Project/docs/AUTHENTICATION_AND_SECURITY.md) | Security Auditors, Devs | Dual-channel OTP (MIME/SMTP + SMS), Single-session enforcer, WebAuthn/FIDO2 passkeys, 10-minute grace windows, and threat mitigation. |
| [**`OPERATIONS_AND_ADMINISTRATION.md`**](file:///s:/Campus-Project/docs/OPERATIONS_AND_ADMINISTRATION.md) | Campus Admins, Staff | Operations dashboard, in-person physical verification desk, account soft-deletion with audit preservation, and data exports. |
| [**`MECHANICAL_ZEN_AND_THEMES.md`**](file:///s:/Campus-Project/docs/MECHANICAL_ZEN_AND_THEMES.md) | Frontend Engineers, Designers | Real-time SVG clockwork hands, ambient gear physics, foreground scatter animation with hesitation/rocket exit, eccentric light mode dialogues, and inter-page transitions. |
| [**`DEPLOYMENT_AND_PRODUCTION.md`**](file:///s:/Campus-Project/docs/DEPLOYMENT_AND_PRODUCTION.md) | DevOps, System Admins | Production checklist, PostgreSQL migration, Redis channel clustering, Nginx reverse proxy, Daphne systemd services, and DLT/SMTP setup. |
| [**`API_REFERENCE.md`**](file:///s:/Campus-Project/docs/API_REFERENCE.md) | Mobile/Client Devs | Versioned REST API (v1) endpoints, JSON schemas, authentication challenge workflows, and Channels WebSocket packet protocol. |
| [**`FUTURE_ROADMAP.md`**](file:///s:/Campus-Project/docs/FUTURE_ROADMAP.md) | Product Owners, Leads | Upcoming modules: PRINT HUB, LOST & FOUND, MESS MATE, DigiLocker integration, and institutional Google Workspace SSO. |

---

## 2. Platform Architecture Overview

```
                               +----------------------------------------+
                               |          CAMPUS NEXUS UMBRELLA         |
                               +-------------------+--------------------+
                                                   |
                 +--------------------+------------+------------+--------------------+
                 |                    |                         |                    |
                 v                    v                         v                    v
          [ COORDINATE ]        [ PRINT HUB ]            [ LOST & FOUND ]       [ MESS MATE ]
       (Live — Ridesharing)   (In Development)          (In Development)      (In Development)
                 |
                 +---> Dual-Channel OTP (MIME/SMTP Email + Carrier SMS)
                 +---> WebAuthn / FIDO2 Passkeys (Windows Hello / Touch ID)
                 +---> Single-Session Device Enforcer
                 +---> Physical Operations Desk & In-Person Verification
                 +---> Clockwork Watermark & Zen Transition Engine
```

---

## 3. Quickstart & Verification Commands

### Environment Setup
```powershell
# Activate Python Virtual Environment
.\venv\Scripts\activate

# Install Dependencies
pip install -r requirements.txt

# Run Database Migrations
python manage.py migrate

# Seed Debug Accounts & Superaccount
python manage.py create_debug_accounts --reset
```

### Automated Audit & Test Suites
```powershell
# Run 142/142 Django Unit & Workflow Tests
python manage.py test

# Run Deep Platform Crawler (64/64 E2E Checks)
python test_full_platform_e2e.py

# Run Live HTTP Route Audit
python audit_platform.py
```

### Launch Development Server
```powershell
python manage.py runserver 127.0.0.1:8000
```
