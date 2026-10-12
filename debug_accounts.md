# COORDINATE — Development & Debug Accounts

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
| **`2024BCSE001`** | Abdus Samad | CSE (Bachelors) | M | **Superuser**, Staff, Verified | Admin dashboard, approvals, management |
| **`2024BCSE002`** | Raza Khan | CSE (Bachelors) | M | Verified Student | Creating & joining rides, peer testing |
| **`2024BCSE003`** | Aisha Wani | CSE (Bachelors) | F | Verified Student | Girls Only rides, mixed rides testing |
| **`2024BECE004`** | Umar Farooq | ECE (Bachelors) | M | Verified Student | Friend requests, social graph testing |
| **`2024BECE005`** | Fatima Sheikh | ECE (Bachelors) | F | Verified Student | Reviews, multi-passenger ride validation |
| **`2024BCIV006`** | Bilal Ahmad | Civil (Bachelors) | M | Verified Student | Edge cases (leave, kick, terminate ride) |

---

### Test Credentials Quick Reference

- **Admin Login:**
  - Enrollment Number: `2024BCSE001`
  - Password: `Debug@123`
- **Student Login 1:**
  - Enrollment Number: `2024BCSE002`
  - Password: `Debug@123`
- **Student Login 2 (Female):**
  - Enrollment Number: `2024BCSE003`
  - Password: `Debug@123`
