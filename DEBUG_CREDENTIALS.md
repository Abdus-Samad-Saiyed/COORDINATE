# Campus Nexus — Debug & Administrative Credentials Reference

> **Confidential Institutional Development Reference**  
> **Last Updated:** 2026-10-14  
> **Environment:** Local Development & Testing (`DEBUG=True`)

---

## 1. Identity & Namespace Architecture

To prevent collision between actual enrolled students and automated/manual testing accounts, Campus Nexus enforces a strict namespace boundary:

- **Synthetic Debug Accounts (`20XX...`):** Reserved prefix for branch testing accounts. These accounts automatically bypass Two-Factor Authentication (2FA) and phone OTP verification to streamline developer workflows.
- **Personal Superaccount (`2024BCSE065`):** Registered to student administrator **Abdus Samad Saiyed**. Holds full institute superuser and staff permissions, with production-grade security enforcement (2FA, phone OTP verification, and 10-minute session grace windows).
- **Real Student Accounts (`2024...`, `2025...`, etc.):** Enforce physical enrollment verification, mandatory phone OTP at signup, single-session concurrency, and optional passkey/2FA protection.

---

## 2. Personal Superaccount

| Field | Detail |
| :--- | :--- |
| **Enrollment Number** | `2024BCSE065` |
| **Full Name** | **Abdus Samad Saiyed** |
| **Institutional Email** | `asaiyed_2024bcse065@nitsri.ac.in` |
| **Password** | `AbSm72000@123` |
| **Registered Phone** | `+917355463857` |
| **Roles & Permissions** | Superuser, Staff, Operations Administrator, Verification Officer |
| **2FA Verification** | Enabled (Phone SMS OTP, Email OTP, or Passkey) |
| **Security Window** | 10-Minute authenticated grace window for credential modifications |

---

## 3. Synthetic Branch Debug Accounts

All synthetic debug accounts share the password **`Debug@123`**. They are pre-verified, bypass 2FA OTP requirements, and can be used to test peer-to-peer features (ride sharing, direct messaging, seat bookings, reviews).

| Enrollment ID | Department / Branch | Student Name | Institutional Email | Registered Phone | Gender | 2FA Bypass |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| `20XXBCSE001` | Computer Science & Engineering | Debug CSE Student | `20xxbcse001@nitsri.ac.in` | `+919876543210` | M | ✅ Yes |
| `20XXBECE001` | Electronics & Communication | Debug ECE Student | `20xxbece001@nitsri.ac.in` | `+919876543211` | F | ✅ Yes |
| `20XXBCIV001` | Civil Engineering | Debug Civil Student | `20xxbciv001@nitsri.ac.in` | `+919876543212` | M | ✅ Yes |
| `20XXBELE001` | Electrical Engineering | Debug Electrical Student | `20xxbele001@nitsri.ac.in` | `+919876543213` | F | ✅ Yes |
| `20XXBMEC001` | Mechanical Engineering | Debug Mechanical Student | `20xxbmec001@nitsri.ac.in` | `+919876543214` | M | ✅ Yes |

---

## 4. Authentication & Security Behavior Matrix

| Feature | Superaccount (`2024BCSE065`) | Debug Accounts (`20XX...`) | Student Accounts (`2024...`) |
| :--- | :---: | :---: | :---: |
| **2FA at Login** | Supported (SMS / Passkey) | ⚡ Bypassed | Required if enabled |
| **Profile Security OTP** | Required (10m Grace) | ⚡ Bypassed | Required (10m Grace) |
| **Single Active Session** | Enforced | Enforced | Enforced |
| **Soft Deletion Safety** | Protected | Protected | Preserved in Audit Logs |
| **Physical Verification** | Verification Officer | N/A | Supported via Ops Desk |

---

## 5. Management Commands

To populate, verify, or reset debug accounts and the personal superaccount:

```bash
# Create or sync all accounts
python manage.py create_debug_accounts

# Purge legacy debug accounts and recreate fresh synthetic accounts
python manage.py create_debug_accounts --reset
```
