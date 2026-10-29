# Campus Nexus / COORDINATE — Development & Debug Accounts

These accounts are seeded automatically using the management command:

```bash
python manage.py create_debug_accounts
```

To wipe and recreate:
```bash
python manage.py create_debug_accounts --reset
```

All accounts use the password: `Debug@123`

---

### Account Directory

| Enrollment No. | Full Name | Branch & Degree | Gender | Roles / Privileges | Purpose |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **`2024BCSE065`** | Abdus Samad Saiyed | CSE (Bachelors) | M | **Superuser**, Staff, Verified | Primary Administrator, Operations, Superuser Control |
| **`20XXBCSE001`** | Debug CSE Student | CSE (Bachelors) | M | Verified Student | Creating & joining rides, driver / peer testing |
| **`20XXBECE001`** | Debug ECE Student | ECE (Bachelors) | F | Verified Student | Girls Only rides, mixed rides, multi-passenger ride validation |
| **`20XXBCIV001`** | Debug Civil Student | Civil (Bachelors) | M | Verified Student | Friend requests, social graph testing, chat |
| **`20XXBELE001`** | Debug Electrical Student | Electrical (Bachelors) | F | Verified Student | Reviews, grievances, attendance metrics |
| **`20XXBMEC001`** | Debug Mechanical Student | Mechanical (Bachelors) | M | Verified Student | Lifecycle edge cases (leave, kick, waitlist, terminate) |

---

### Quick Reference Sign-In Credentials

- **Primary Superuser / Admin Login:**
  - Enrollment Number: `2024BCSE065`
  - Password: `Debug@123`
  - 2FA: Disabled by default in dev (can be enabled via profile)
- **Student Login 1 (Male - CSE):**
  - Enrollment Number: `20XXBCSE001`
  - Password: `Debug@123`
- **Student Login 2 (Female - ECE):**
  - Enrollment Number: `20XXBECE001`
  - Password: `Debug@123`
- **Student Login 3 (Male - Civil):**
  - Enrollment Number: `20XXBCIV001`
  - Password: `Debug@123`
- **Student Login 4 (Female - Electrical):**
  - Enrollment Number: `20XXBELE001`
  - Password: `Debug@123`
- **Student Login 5 (Male - Mechanical):**
  - Enrollment Number: `20XXBMEC001`
  - Password: `Debug@123`
