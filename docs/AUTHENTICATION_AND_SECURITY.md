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

## 7. Early Launch Mode: Accelerated Self-Declaration vs Physical Desk

To accommodate high-stakes, time-sensitive campus situations (such as end-of-term transit rushes where thousands of students need to arrange shared transport before semester closing), Campus Nexus supports an **Early Launch Mode**.

### 7.1 Comparison of Operational Modes

| Dimension | Standard Verification Mode | Early Launch Mode (`--early-launch`) |
| :--- | :--- | :--- |
| **Activation Trigger** | Default operational state (`EARLY_LAUNCH_MODE=False`). | Started via `manage.py runserver --early-launch` or `EARLY_LAUNCH_MODE=True`. |
| **Registration Flow** | Student submits application + validates phone/email OTP -> Application queues in `AccountApplication` -> Admin verifies physical ID card. | Student submits self-declaration form with enrollment, name, gender, phone, and password -> Account is activated immediately. |
| **Initial Account Status** | `verified=False`, `is_active=False` until physical desk sign-off. | `verified=True`, `is_active=True` upon form submission. |
| **Login Session** | Student must wait for approval before logging in. | Student is automatically logged in and redirected to `/dashboard/`. |
| **Pending Applications** | Queued in `AccountApplication` table awaiting review. | Any pre-existing pending applications for that enrollment are purged automatically. |
| **COORDINATE Access** | Requires `user.verified=True`. | Granted via `user.verified=True` and `is_verified_student` policy waiver. |
| **Audit Trail** | `APPLICATION_SUBMITTED`, `PHYSICAL_VERIFICATION_RESOLVED`. | `EARLY_LAUNCH_SELF_DECLARATION` logged to `AuditEvent`. |

### 7.2 Safety Guarantees Maintained During Early Launch
Even though physical verification queues are waived during Early Launch, mutual security inside rides remains strictly intact:
1. **Enrollment Format Validation:** All enrollment numbers must match official NIT Srinagar regex (`^(?:\d{4}|20XX)[BMP][A-Z]{3}\d{3}$`).
2. **Normalized Phone Numbers:** All contact numbers are validated and stored in E.164-compatible format, ensuring reachable WhatsApp and cellular connectivity.
3. **Gender Preference Enforcement:** Gender selection is mandatory, preserving safety comfort settings for female-only rides.
4. **Zero Anonymity Inside Cabs:** Co-passengers and ride hosts mutually inspect each other's full name, enrollment number, and phone number upon joining a ride.
5. **Rate Limiting:** Registration endpoint is throttled to 5 requests per 60 seconds to protect against automated account generation.
6. **Post-Exam Physical Protocol:** A physical audit is conducted by the Proctorial Board at the start of the subsequent academic term.
