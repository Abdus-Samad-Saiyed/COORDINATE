# Campus Nexus — Authentication, Identity & Security Specification

---

## 1. Identity Namespace & Academic Enrollment Standard

Student identity is bound to official NIT Srinagar enrollment numbers. The platform enforces strict structural parsing using Python and Django regular expression validators:

```regex
^(?:\d{4}|20XX)[BMP][A-Z]{3}\d{3}$
```

### 1.1 Structural Decomposition
- **Joining Year (`[0:4]`):** Either a 4-digit academic cohort year (e.g., `2024`, `2025`) or the synthetic debug prefix `20XX`.
- **Degree Code (`[4]`):** `B` (Bachelors / B.Tech), `M` (Masters / M.Tech), or `P` (Doctoral / PhD).
- **Branch Code (`[5:8]`):** Institutional engineering discipline: `CSE`, `ECE`, `CIV`, `ELE`, `MEC`, `CHE`, `IT`, etc.
- **Roll Number (`[8:11]`):** 3-digit student roll identifier (e.g., `065`).

### 1.2 Account Classification & Isolation

| Account Tier | Enrollment Pattern | Verification Model | 2FA Policy | SMS / Email Carrier Dispatch |
| :--- | :--- | :--- | :--- | :--- |
| **Real Student Cohorts** | `2024BCSE001`... | Physical ID verification, mandatory Phone & Email OTP at application. | Optional / Recommended (Mandatory for sensitive profile updates). | **Active:** Dispatches codes to registered mobile & email. |
| **Personal Superaccount** | `2024BCSE065` | Superuser / Staff status with institutional email `asaiyed_2024bcse065@nitsri.ac.in`. | Mandatory 2FA & 10-minute session grace windows. | **Active:** Dispatches codes to registered mobile & email. |
| **Synthetic Debug Accounts** | `20XXBCSE001`... `20XXBMEC001` | Pre-verified, seeded developer fixtures. Password: `Debug@123`. | **Bypassed:** Bypasses 2FA checks and rate-limits to facilitate local testing. | **Suppressed:** Suppresses outbound SMS/Email dispatch. |

---

## 2. Dual-Channel Cryptographic OTP Engine (`accounts.two_factor`)

To provide zero-failure identity verification without dependency on Indian telecom DLT approvals, Campus Nexus implements a **Dual-Channel OTP Dispatch Engine**:

```
                    +------------------------------------+
                    |  create_phone_otp(phone, email)   |
                    +-----------------+------------------+
                                      |
                      Generate 6-Digit Cryptographic Code
                         secrets.randbelow(900000)
                                      |
                  +-------------------+-------------------+
                  |                                       |
                  v                                       v
         [ Carrier SMS Gateway ]                [ MIME / SMTP Gateway ]
       (Twilio / MSG91 / DLT)                 (Google SMTP / Amazon SES)
                  |                                       |
                  v                                       v
          Student Phone SMS                       Student Email Inbox
                  |                                       |
                  +-------------------+-------------------+
                                      |
                                      v
                        [ verify_phone_otp(...) ]
                  (Matches code against Phone OR Email)
```

### 2.1 Security Parameters
- **Entropy & Randomness:** Generated using Python's hardware-backed `secrets.randbelow(900000) + 100000`.
- **Zero-Plaintext Storage:** The raw code is **never stored in plaintext** in the database. Only its PBKDF2-SHA256 salted hash is persisted in `PhoneOTP.otp_hash`.
- **Zero-Payload Leaks:** JSON responses from `send_signup_otp` or `send_security_otp` never include the code in API payloads.
- **Validity & Expiry:** Hard expiration after **5 minutes** (`expires_at = now + 5 minutes`).
- **Brute-Force Lockout:** Maximum **3 failed attempts** allowed. On the 4th failure, the record is immediately invalidated (`is_used = True`).
- **Dispatch Rate Throttling:** Rapid resend requests within **15 seconds** are rejected with HTTP 429 Too Many Requests.
- **Interchangeable Verification:** `verify_phone_otp` matches the code whether the student verifies against their registered mobile number or their registered email address.

---

## 3. WebAuthn / FIDO2 Passkey Integration

Students can enroll biometric authenticators (Windows Hello, Touch ID, Apple Face ID, YubiKeys) for instant passwordless 2FA verification:

```
[ Browser Client ]                                          [ Campus Nexus Server ]
        |                                                              |
        | --- 1. GET /passkey/reg/challenge/ ------------------------> |
        | <--- 2. JSON: { challenge: Base64URL, rp_id: Domain } ------ |
        |                                                              |
        | [ Hardware Prompt: Touch Sensor / Windows Hello PIN ]        |
        |                                                              |
        | --- 3. POST /passkey/reg/verify/ (Credential + Signature) -> |
        |                                                              |
        |                                      Verify Public Key & Nonce
        |                                      Save PasskeyCredential Record
        | <--- 4. JSON: { success: true } ---------------------------- |
```

- Handled using standard FIDO2 Web Authentication API (`navigator.credentials.create` and `navigator.credentials.get`).
- Server validates challenge nonce freshness stored in user session to prevent replay attacks.
- Passkey public keys stored in `PasskeyCredential` table.

---

## 4. Single-Session Active Device Enforcer (`accounts.middleware`)

To prevent credential sharing, unauthorized account lending, or concurrent multi-device logins, Campus Nexus enforces strict **Single-Session Concurrency**:

```python
class SingleSessionMiddleware:
    def __call__(self, request):
        if request.user.is_authenticated:
            expected_key = getattr(request.user, 'current_session_key', '')
            actual_key = request.session.session_key
            if expected_key and actual_key and expected_key != actual_key:
                logout(request)
                messages.warning(request, "Logged out: This account was signed into from another device.")
                return redirect('login')
        return self.get_response(request)
```

- When a student signs in from Device B, Device B's session key is written to `user.current_session_key`.
- When Device A makes any subsequent request, the middleware detects the key mismatch, immediately flushes Device A's session, logs them out, and displays a security alert.

---

## 5. Ten-Minute Session Grace Window

To eliminate OTP verification fatigue when a student is updating multiple profile fields:
- Entering a valid OTP for a security action sets `request.session['security_otp_verified_until'] = (now + 10 minutes)`.
- During this 10-minute active window, the student can modify their password, phone number, email, or 2FA toggles directly without re-triggering repetitive SMS/Email dispatches.
- Once the 10 minutes expire, any subsequent security modification mandates a fresh OTP dispatch.

---

## 6. Threat Mitigation Matrix

| Threat Vector | Mitigation Strategy |
| :--- | :--- |
| **Credential Stuffing / Brute Force** | Rate-limiting decorators (`@rate_limit(limit=5, period=60)`), PBKDF2-SHA256 password hashing with 1,000,000 iterations. |
| **Session Hijacking** | `SingleSessionMiddleware` locks account to single active session; `django.middleware.csrf.CsrfViewMiddleware` enforces Anti-CSRF tokens on all mutating HTTP POST/DELETE requests. |
| **SIM Swapping / Lost Phone** | Dual-channel email OTP fallback; physical operations desk verification requiring government/institute photo ID card. |
| **Data Scraping / Enumeration** | `hide_from_search` privacy switch; pagination limits; phone numbers masked to non-friends (`***-***-1234`). |


---

## 7. Early Launch Mode: Untrusted Self-Declaration & Temporary Storage

To accommodate high-stakes, time-sensitive campus situations (such as end-of-term transit rushes where thousands of students need to arrange shared transport before semester closing), Campus Nexus supports an **Early Launch Mode**.

Because self-declared credentials cannot be physically authenticated in real time, early access accounts are classified as **untrusted**, stored in an isolated temporary database (`temp_early_access.sqlite3`), and explicitly prevented from polluting or colliding with permanent accounts.

### 7.1 Comparison of Operational Modes

| Dimension | Standard Verification Mode | Early Launch Mode (`--early-launch`) |
| :--- | :--- | :--- |
| **Activation Trigger** | Default operational state (`EARLY_LAUNCH_MODE=False`). | Started via `manage.py runserver --early-launch` or `EARLY_LAUNCH_MODE=True`. |
| **Database Target** | Permanent database (`db.sqlite3` / PostgreSQL). | Isolated temporary database (`temp_early_access.sqlite3`), with `permanent` alias active. |
| **Registration Pathways** | Single pathway: Official student registration requiring OTP & physical ID check. | **Dual Registration Pathways:**<br>1. *Fast-Track Early Access:* Immediate self-declaration in temp DB (untrusted).<br>2. *Official Permanent Application:* Full OTP & ID verification queued to both temp and permanent DBs. |
| **Account Trust Status** | `verified=True` once physically approved. | Self-declared: `verified=False` (`Untrusted • Early Access`). Upgraded to `verified=True` upon admin approval. |
| **Account Retention** | Permanent institutional record. | Fast-track accounts: temporary. Official permanent applications: mirrored to permanent DB and preserved. |
| **Conflict Potential** | N/A (single source of truth). | **Zero Conflict:** Temp DB is completely isolated; permanent records are untouched. |
| **Login Session** | Student must wait for approval before logging in. | Fast-track: student is logged in immediately. Official application: queued for desk review. |
| **COORDINATE Access** | Requires `user.verified=True`. | Granted via `is_verified_student` policy waiver for the duration of early launch. |
| **Audit Trail** | `APPLICATION_SUBMITTED`, `APP_APPROVED`, `APP_REJECTED`. | `EARLY_LAUNCH_SELF_DECLARATION`, `APP_APPROVED`, `APP_REJECTED` logged to `AuditEvent`. |

### 7.2 Dual Registration & In-Flight Upgrade Workflow

During Early Launch, registration is not forced into a temporary-only silo. Students have complete autonomy to choose their onboarding flow:

1. **Fast-Track Early Access (Transit Rush):**
   - Available via `/apply/?mode=early` or the default early launch tab.
   - Skips verification desk queues for rapid cab coordination.
   - Stored in `temp_early_access.sqlite3` with `verified=False`.

2. **Official Permanent Account Application:**
   - Available via `/apply/?mode=permanent` at all times.
   - Requires phone and email OTP verification and admin physical ID review.
   - When submitted under `--early-launch`, the application is stored in the current running DB (`default`) so administrators can review it immediately in the admin queue, and **mirrored directly to `permanent`** (`db.sqlite3` / PostgreSQL) to ensure it survives database purges.

3. **In-Flight Upgrade from Untrusted to Verified:**
   - A student who initially created an untrusted early access account can log into their dashboard and click *"Apply for Permanent Verified ID"*, or visit `/apply/?mode=permanent`.
   - Form fields are pre-filled with their active credentials.
   - `AccountApplicationForm` allows unverified self-declared accounts to apply without duplicate key blocks.
   - When an administrator reviews and approves the application via `approve_application`:
     - The existing untrusted account is upgraded: `user.verified = True`.
     - Credentials (password, name, contact) are updated from the verified application.
     - The verified student record is synced to `permanent` (`db.sqlite3`).
     - The pending application is cleared from both databases.

### 7.3 Safety Guarantees Maintained During Early Launch
Even though physical verification queues are waived for fast-track participants during Early Launch, mutual security inside rides remains strictly intact:
1. **Enrollment Format Validation:** All enrollment numbers must match official NIT Srinagar regex (`^(?:\d{4}|20XX)[BMP][A-Z]{3}\d{3}$`).
2. **Normalized Phone Numbers:** All contact numbers are validated and stored in E.164-compatible format, ensuring reachable WhatsApp and cellular connectivity.
3. **Gender Preference Enforcement:** Gender selection is mandatory, preserving safety comfort settings for female-only rides.
4. **Zero Anonymity Inside Cabs:** Co-passengers and ride hosts mutually inspect each other's full name, enrollment number, and phone number upon joining a ride.
5. **Rate Limiting:** Registration endpoint is throttled to 5 requests per 60 seconds to protect against automated account generation.
6. **Untrusted Visual Badging:** Profile pages, search results, and ride rosters explicitly mark early access participants with `Untrusted • Early Access`.
7. **Post-Exam Physical Protocol:** When the new term begins, students undergo standard in-person verification to establish trusted, permanent accounts.
