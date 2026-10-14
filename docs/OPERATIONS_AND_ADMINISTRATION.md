# Campus Nexus — Operations, Governance & Desk Manual

---

## 1. Operational Command Center (`/operations/`)

Campus administrators and authorized staff manage platform health, identity queues, and student safety via the **Operational Dashboard**.

```
[ Admin Console: /operations/ ]
  |-- Active Concurrent Sessions vs Unique Users
  |-- Ride Volume, Status Distribution & Completion Ratios
  |-- Time-Series 7-Day User Growth & Ride Creation Charts
  |-- Physical Desk Queue (Pending In-Person Password / Phone Resets)
  |-- Pending Applications Queue (New Registrations)
  |-- Superuser Privilege Control & Audit Event Feeds
  `-- Secure CSV Data Exports (Rides, Students, Applications)
```

---

## 2. In-Person Physical Verification Desk

### 2.1 Problem Solved
When a student loses their phone, has their SIM deactivated, or loses access to their institutional email account, self-service automated OTP recovery is impossible. Campus Nexus provides a secure, physical in-person verification desk to prevent account abandonment.

### 2.2 End-to-End Workflow

```
1. Student files In-Person Request at /forgot-password/ (Tab 2: In-Person Desk)
   Records: Enrollment number, alternative contact phone, and reason for desk visit.
   System creates: PhysicalVerificationRequest (Status: PENDING)
          |
          v
2. Student physically visits Campus Operations Desk
   Presents official Institute ID Card and Government Photo Identification.
          |
          v
3. Verification Officer inspects ticket on /operations/
   Actions available to Administrator:
   a. "Verify & Reset Password": Enters a temporary password for the student.
      -> Terminate any active sessions.
      -> Updates user password hash.
      -> Marks PhysicalVerificationRequest as VERIFIED.
      -> Logs PHYSICAL_VERIFICATION_RESOLVED audit event.
   b. "Verify & Update Phone": Corrects student's registered mobile number.
      -> Updates user.phone_number in database.
      -> Marks ticket as VERIFIED.
      -> Logs ADMIN_PHONE_UPDATE audit event.
   c. "Reject": Rejects request if student fails ID card verification.
```

---

## 3. Account Soft-Deletion & Historical Retention

### 3.1 Policy
Campus regulations require that student accounts can be closed/deleted upon graduation, withdrawal, or disciplinary action, but **past trip logs, driver reviews, and behavioral complaints must be retained permanently** for legal and institutional compliance.

### 3.2 Implementation (`admin_delete_account`)
When an administrator clicks **Delete Account** on `/operations/`:
1. **Account Closure:** The account is flagged `is_deleted = True` and `is_active = False`. `deleted_at` timestamp is recorded.
2. **Session Termination:** All active browser and mobile sessions associated with `current_session_key` are deleted from session storage.
3. **Storage Sanitization:** Uploaded avatars (`profile_photo`) are deleted from media storage to free up server disk space.
4. **Historical Preservation:**
   - The user record remains in the database.
   - Past completed rides still list their enrollment number and full name.
   - Punctuality ratings and peer reviews written by or for the user remain visible in historical ride summaries.
5. **Audit Logging:** An immutable `ACCOUNT_DELETED` entry is added to `AuditEvent` recording the actor enrollment and deletion reason.

---

## 4. Superuser Governance & Lockout Protection

Superuser privileges are managed at `/operations/superusers/`:
- **Promotion:** Any verified student account can be promoted to superuser/staff status with justification.
- **Revocation:** Superuser permissions can be stripped at any time.
- **Lockout Prevention:** The system calculates `active_superusers = User.objects.filter(is_superuser=True, is_active=True).count()`. If only one active superuser remains, any attempt to revoke their permissions or delete their account is blocked with an alert: *"Cannot revoke the sole active superuser."*

---

## 5. Contributor Management (`/contributors/`)

Platform maintainers and developers are honored in the public Contributors directory:
- **Peer Nominations (`/contributors/nominate/`):** Active contributors can nominate fellow student developers, designers, or moderators.
- **Admin Revocation (`/contributors/<id>/remove/`):** Administrators have authority to remove or deactivate contributor entries if nominations violate platform conduct.

---

## 6. Secure Operational Data Exports

Administrators can download sanitized CSV datasets for institutional reporting:
- **Export Rides (`/operations/export/rides/`):** Route, departure time, total spots, confirmed passengers, completion status, and creation timestamps.
- **Export Students (`/operations/export/users/`):** Enrollment ID, branch, degree, joining year, verification status, completed rides, and punctuality rate.
- **Export Applications (`/operations/export/applications/`):** Application number, applicant enrollment, submission date, phone verification status, and decision outcome.
- Every export action logs an `EXPORT_GENERATED` audit event.
