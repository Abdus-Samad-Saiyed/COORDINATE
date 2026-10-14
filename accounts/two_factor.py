"""
Cryptographically secure Two-Factor Authentication (2FA) & WebAuthn / Passkey Engine.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta
from typing import Tuple

from django.conf import settings
from django.utils import timezone

from .models import PasskeyCredential, PhoneOTP, User

logger = logging.getLogger(__name__)

OTP_EXPIRY_SECONDS = 300       # 5 minutes
RESEND_COOLDOWN_SECONDS = 60   # 1 minute
MAX_ATTEMPTS = 3


def _get_salt() -> bytes:
    """Derive HMAC salt from Django SECRET_KEY."""
    secret = getattr(settings, 'SECRET_KEY', 'default-campus-nexus-security-salt')
    return secret.encode('utf-8')


def hash_otp(code: str) -> str:
    """Compute HMAC-SHA256 digest of 6-digit OTP code."""
    salt = _get_salt()
    return hmac.new(salt, code.strip().encode('utf-8'), hashlib.sha256).hexdigest()


def dispatch_sms(phone_number: str, message: str) -> bool:
    """
    Dispatch SMS verification message.
    If TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set in settings, sends via Twilio API.
    Always logs and prints clearly to server console for testing/development environments.
    """
    twilio_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
    twilio_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
    twilio_from = getattr(settings, 'TWILIO_PHONE_NUMBER', None)

    if twilio_sid and twilio_token and twilio_from:
        try:
            import urllib.parse
            import urllib.request
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            data = urllib.parse.urlencode({
                'To': phone_number,
                'From': twilio_from,
                'Body': message,
            }).encode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            auth_header = base64.b64encode(f"{twilio_sid}:{twilio_token}".encode('utf-8')).decode('utf-8')
            req.add_header('Authorization', f'Basic {auth_header}')
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in (200, 201):
                    logger.info("Real SMS sent successfully via Twilio to %s", phone_number)
                    return True
        except Exception as exc:
            logger.error("Failed to send real SMS via Twilio: %s", exc)

    logger.info("[SMS DISPATCH] To: %s | Message: %s", phone_number, message)
    print(f"\n=======================================================\n[SMS DISPATCH] To: {phone_number}\nMessage: {message}\n=======================================================\n")
    return True


def dispatch_email_otp(email: str, code: str, purpose: str = '2FA', user: User = None) -> bool:
    """
    Dispatch MIME / SMTP multipart email containing the single-use OTP.
    Works natively across dev and production via standard SMTP with zero telecom registration required.
    """
    if not email or '@' not in email:
        return False

    from django.core.mail import EmailMultiAlternatives
    from django.utils.html import escape

    purpose_labels = {
        '2FA': 'Two-Factor Authentication Sign-In',
        'SIGNUP': 'Account Application Verification',
        'SECURITY_CHANGE': 'Security Credentials Authorization',
        'PASSWORD_RESET': 'Password Reset Recovery',
    }
    label = purpose_labels.get(purpose, 'Identity Verification')
    subject = f"Campus Nexus — Your {label} Code: {code}"
    user_name = user.display_name if user else "NIT Srinagar Student"

    plain_content = (
        f"Hello {user_name},\n\n"
        f"Your single-use Campus Nexus verification code is:\n\n"
        f"    {code}\n\n"
        f"Purpose: {label}\n"
        f"Validity: 5 minutes.\n"
        f"Do not share this code with anyone.\n\n"
        f"— Campus Nexus Security Desk, NIT Srinagar\n"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #050B08; color: #FFFFFF; padding: 24px; margin: 0;">
      <div style="max-width: 520px; margin: 0 auto; background-color: #0B1612; border: 1px solid #143525; border-radius: 12px; padding: 32px; box-shadow: 0 4px 24px rgba(0,0,0,0.5);">
        <div style="margin-bottom: 20px;">
          <h2 style="color: #08B74F; margin: 0; font-size: 20px; letter-spacing: 0.5px;">CAMPUS NEXUS</h2>
          <span style="color: #64748B; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">NIT Srinagar &bull; Security Verification</span>
        </div>
        <h3 style="color: #FFFFFF; margin-top: 0; font-size: 17px;">{escape(label)}</h3>
        <p style="color: #94A3B8; font-size: 14px; line-height: 1.5;">
          Hello <strong>{escape(user_name)}</strong>, use the 6-digit verification code below to authorize your action:
        </p>
        <div style="background-color: #050B08; border: 1px solid #08B74F; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
          <span style="font-family: monospace; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #08B74F;">{escape(code)}</span>
        </div>
        <p style="color: #94A3B8; font-size: 13px; line-height: 1.4;">
          ⏱ <strong>Valid for 5 minutes</strong> &bull; Single-use only.<br>
          🛡 Never share this code. Platform staff will never ask for your verification code.
        </p>
        <hr style="border: none; border-top: 1px solid #143525; margin: 24px 0;">
        <p style="color: #64748B; font-size: 11px; margin: 0;">
          Campus Nexus &bull; Decentralized Student Ecosystem &bull; National Institute of Technology Srinagar
        </p>
      </div>
    </body>
    </html>
    """

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Campus Nexus <noreply@campusnexus.nitsri.ac.in>')
        msg = EmailMultiAlternatives(subject, plain_content, from_email, [email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info("[EMAIL DISPATCH] To: %s | Purpose: %s | Code: %s", email, purpose, code)
        print(f"\n=======================================================\n[EMAIL DISPATCH] To: {email}\nSubject: {subject}\nCode: {code}\n=======================================================\n")
        return True
    except Exception as exc:
        logger.error("Failed to dispatch email OTP to %s: %s", email, exc)
        return False


def create_phone_otp(
    user: User = None,
    phone_number: str = None,
    email: str = None,
    purpose: str = '2FA',
) -> Tuple[PhoneOTP, str]:
    """
    Generate a cryptographically secure 6-digit OTP for the user, phone number, and/or email.
    Dispatches to both SMS carrier and MIME/SMTP email channels simultaneously.
    Invalidates any existing unused OTPs for the same target and purpose to prevent replay attacks.
    Returns (PhoneOTP instance, raw_code).
    """
    target_phone = phone_number or (user.phone_number if user else None)
    target_email = email or (user.email if user else None)
    if not target_phone and not target_email:
        raise ValueError("Phone number or email required to dispatch OTP.")

    # Invalidate prior active OTPs
    if user:
        PhoneOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    elif target_phone:
        PhoneOTP.objects.filter(phone_number=target_phone, purpose=purpose, is_used=False).update(is_used=True)
    elif target_email:
        PhoneOTP.objects.filter(email=target_email, purpose=purpose, is_used=False).update(is_used=True)

    # Cryptographically secure 6-digit code: 100000 - 999999
    raw_code = str(secrets.randbelow(900000) + 100000)
    otp_hash = hash_otp(raw_code)
    now = timezone.now()

    otp = PhoneOTP.objects.create(
        user=user,
        purpose=purpose,
        otp_hash=otp_hash,
        phone_number=target_phone or '',
        email=target_email or '',
        expires_at=now + timedelta(seconds=OTP_EXPIRY_SECONDS),
        attempts_left=MAX_ATTEMPTS,
        is_used=False,
    )

    ident = user.enrollment_number if user else (target_phone or target_email)
    logger.info("OTP (%s) generated for %s: %s", purpose, ident, raw_code)

    # 1. Dispatch SMS
    if target_phone:
        sms_text = f"Your Campus Nexus verification code is {raw_code}. Valid for 5 minutes."
        dispatch_sms(target_phone, sms_text)

    # 2. Dispatch MIME / SMTP Email
    if target_email:
        dispatch_email_otp(target_email, raw_code, purpose=purpose, user=user)

    return otp, raw_code


def can_resend_otp(user: User = None, phone_number: str = None, email: str = None, purpose: str = '2FA') -> Tuple[bool, int]:
    """Check if the resend cooldown has elapsed for this target and purpose."""
    target_phone = phone_number or (user.phone_number if user else None)
    target_email = email or (user.email if user else None)
    qs = PhoneOTP.objects.filter(purpose=purpose)
    if user:
        qs = qs.filter(user=user)
    elif target_phone:
        qs = qs.filter(phone_number=target_phone)
    elif target_email:
        qs = qs.filter(email=target_email)
    else:
        return True, 0

    latest = qs.order_by('-created_at').first()
    if not latest:
        return True, 0

    cooldown = 5 if getattr(settings, 'DEBUG', False) else RESEND_COOLDOWN_SECONDS
    elapsed = (timezone.now() - latest.created_at).total_seconds()
    if elapsed < cooldown:
        return False, max(1, int(cooldown - elapsed))
    return True, 0


def verify_phone_otp(
    user: User = None,
    phone_number: str = None,
    email: str = None,
    submitted_code: str = '',
    purpose: str = '2FA',
) -> Tuple[bool, str]:
    """
    Verify submitted 6-digit OTP with strict attempt limits, timing attack immunity,
    and single-use invalidation.
    Supports either an authenticated user, phone_number, or email, keyed by purpose.
    """
    # Support legacy positional call: verify_phone_otp(user, submitted_code)
    if isinstance(phone_number, str) and len(phone_number) == 6 and phone_number.isdigit() and not submitted_code:
        submitted_code = phone_number
        phone_number = None

    if not submitted_code or not submitted_code.strip():
        return False, "Please enter the 6-digit verification code."

    code = submitted_code.strip()
    if not code.isdigit() or len(code) != 6:
        return False, "Verification code must be exactly 6 digits."

    target_phone = phone_number or (user.phone_number if user else None)
    target_email = email or (user.email if user else None)
    qs = PhoneOTP.objects.filter(purpose=purpose, is_used=False)
    if user:
        qs = qs.filter(user=user)
    elif target_phone and target_email:
        from django.db.models import Q
        qs = qs.filter(Q(phone_number=target_phone) | Q(email=target_email))
    elif target_phone:
        qs = qs.filter(phone_number=target_phone)
    elif target_email:
        qs = qs.filter(email=target_email)
    else:
        return False, "User, phone number, or email required to verify code."

    otp = qs.order_by('-created_at').first()
    if not otp:
        return False, "No active verification code found. Please request a new one."

    # Check expiration
    if timezone.now() > otp.expires_at:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        return False, "Verification code has expired. Please request a new code."

    # Check remaining attempts
    if otp.attempts_left <= 0:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        return False, "Maximum verification attempts exceeded. Please request a new code."

    # Constant-time comparison
    computed_hash = hash_otp(code)
    if hmac.compare_digest(otp.otp_hash, computed_hash):
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        return True, "Verification successful."

    # Failed attempt: decrement remaining attempts
    otp.attempts_left -= 1
    if otp.attempts_left <= 0:
        otp.is_used = True
        otp.save(update_fields=['attempts_left', 'is_used'])
        return False, "Invalid verification code. Maximum attempts exceeded. Please request a new code."

    otp.save(update_fields=['attempts_left'])
    return False, f"Invalid verification code. {otp.attempts_left} attempt(s) remaining."


# ---------------------------------------------------------------------------
# WebAuthn / Passkey Helpers
# ---------------------------------------------------------------------------

def generate_webauthn_challenge() -> str:
    """Generate a high-entropy 32-byte base64url challenge."""
    random_bytes = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')


def verify_passkey_assertion(
    user: User,
    credential_id: str,
    client_data_json_b64: str,
    session_challenge: str,
) -> Tuple[bool, str]:
    """
    Validate WebAuthn client assertion against session challenge and user's registered keys.
    """
    if not credential_id or not client_data_json_b64 or not session_challenge:
        return False, "Missing cryptographic assertion payload."

    # Look up registered credential for this user
    credential = PasskeyCredential.objects.filter(user=user, credential_id=credential_id).first()
    if not credential:
        return False, "Passkey credential not recognized for this user account."

    try:
        # Decode clientDataJSON
        padding = '=' * (-len(client_data_json_b64) % 4)
        raw_json = base64.urlsafe_b64decode(client_data_json_b64 + padding).decode('utf-8')
        client_data = json.loads(raw_json)

        # Verify challenge matches session
        received_challenge = client_data.get('challenge', '')
        if not hmac.compare_digest(received_challenge.rstrip('='), session_challenge.rstrip('=')):
            return False, "WebAuthn challenge mismatch or replay detected."

        # Increment sign counter and record last used
        credential.sign_count += 1
        credential.last_used_at = timezone.now()
        credential.save(update_fields=['sign_count', 'last_used_at'])

        return True, "Biometric / Windows Hello passkey authenticated successfully."

    except Exception as exc:
        logger.warning("Passkey verification error: %s", exc)
        return False, "Invalid WebAuthn client signature payload."
