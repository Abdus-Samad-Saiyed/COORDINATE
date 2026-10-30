# Campus Nexus — Technical Roadmap & Module Specifications

---

## 1. Vision & Strategic Roadmap

Campus Nexus is expanding from its core transit foundation (**COORDINATE**) into an institutional digital nervous system for **NIT Srinagar**. Below are the architectural specifications for the four upcoming phases.

```
       [ Phase 1: PRINT HUB ]        ---> Queueless Xerox & PDF Assignment Submission
                |
       [ Phase 2: LOST & FOUND ]      ---> Campus Property Directory & Security Booth Handover
                |
       [ Phase 3: MESS MATE ]         ---> Hostel Dining Calendars, Feedback & Hygiene Tracking
                |
       [ Phase 4: INSTITUTIONAL SSO ] ---> Google Workspace & DigiLocker Federated Identity
```

---

## 2. Phase 1: PRINT HUB (Campus Queueless Printing)

### 2.1 The Problem
During mid-term and end-term project weeks, campus stationery and Xerox booths suffer from 40+ student queues, manual USB drive transfers (which propagate malware across institute computers), and lost paper printouts.

### 2.2 System Architecture
- **PDF Ingestion Engine:** Direct browser upload of PDFs, lab manuals, and assignments. Uses Python's `pypdf` to calculate exact page count, color vs black-and-white page distribution, and double-sided formatting.
- **Automated Price Calculator:** Computes billing based on institutional stationery vendor rates (e.g. ₹1.50/B&W page, ₹5/Color page).
- **Vendor Dispatch Terminal:** Campus shopkeepers receive an optimized queue view showing incoming document tokens.
- **Ready-for-Pickup Token Dispatch:** When the shopkeeper marks the job printed, the dual-channel OTP engine dispatches an SMS and Email pickup token to the student:
  ```text
  Your Print Hub order #PRT-8192 is ready for pickup at Main Academic Block Xerox.
  ```

---

## 3. Phase 2: LOST & FOUND (Campus Property Directory)

### 3.1 The Problem
Misplaced College ID cards, scientific calculators, notebooks, and electronics are posted haphazardly on informal WhatsApp groups where they are quickly buried and unsearchable.

### 3.2 System Architecture
- **Categorized Directory:** Listings for Identity Cards, Electronics, Documents, Keys, and Apparel.
- **Smart Roster Auto-Matching:** If an uploaded item contains an enrollment number (e.g. an NIT ID card or exam hall ticket), the platform runs an automated database lookup and directly alerts the owner via Email and SMS:
  ```text
  Notice: Your Institute ID Card was reported found near Library Ground Floor. Please visit Main Security Gate Booth to claim.
  ```
- **Proctorial Booth Verification:** Handover requires entering the security officer's verification pin, logging an immutable audit record of custody transfer.

---

## 4. Phase 3: MESS MATE (Hostel Dining & Hygiene Tracker)

### 4.1 The Problem
Hostel residents (Chenab, Indus, Jhelum, Habba Khatoon) lack advance notice of daily meal schedules, dietary warnings, or an official channel for submitting hygiene concerns to the Chief Warden.

### 4.2 System Architecture
- **Weekly Meal Matrix:** Dynamic schedule of breakfast, lunch, evening tea, and dinner menus published by hostel mess committees.
- **Special Occasion & Feast Alerts:** Automated alerts for festive dinners or menu modifications.
- **Student Quality Rating Log:** Daily 1-to-5 star student ratings for food quality, hygiene, and timeliness.
- **Chief Warden Incident Escalation:** Sustained low ratings (< 2.5 stars over 3 consecutive days) trigger an automated escalation notification to the Chief Warden's operational dashboard.

---

## 5. Phase 4: Institutional Single Sign-On (SSO) & DigiLocker

### 5.1 Architecture
- **OpenID Connect / SAML 2.0:** Direct federation with NIT Srinagar's institutional Google Workspace domain (`@nitsri.ac.in`). Students sign into Campus Nexus with one click using their college Google account.
- **DigiLocker Integration:** Integration with the National Academic Depository (NAD) via DigiLocker API to verify authentic enrollment and degree status without requiring manual admin approval queues.
